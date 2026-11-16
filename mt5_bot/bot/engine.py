"""라이브(드라이런 포함) 매매 엔진. 한 번의 run_once() 가 한 사이클이다."""
from __future__ import annotations

import logging
from datetime import date, datetime

import pandas as pd

from .broker import Broker, Position
from .config import BotConfig, SymbolConfig
from .indicators import atr
from .notify import Notifier, TradeLog
from .sessions import in_session
from .sizing import risk_based_volume
from .strategies import Strategy, make_strategy

log = logging.getLogger(__name__)

DIR_NAME = {1: "매수", -1: "매도"}


def fmt_price(x: float) -> str:
    return f"{x:.5f}".rstrip("0").rstrip(".")


class RiskManager:
    """일일 최대손실 도달 시 그날은 신규 진입을 멈춘다."""

    def __init__(self, daily_max_loss_pct: float):
        self.daily_max_loss_pct = daily_max_loss_pct
        self.halted_day: date | None = None

    def is_halted(self, broker: Broker, ref_symbol: str) -> tuple[bool, bool, float, float]:
        """(정지 여부, 이번에 새로 정지됐는지, 오늘 손익, 시작 잔고)"""
        day, pnl, start_balance = broker.daily_pnl(ref_symbol)
        if self.halted_day == day:
            return True, False, pnl, start_balance
        if self.daily_max_loss_pct > 0 and start_balance > 0:
            if -pnl >= start_balance * self.daily_max_loss_pct / 100:
                self.halted_day = day
                return True, True, pnl, start_balance
        return False, False, pnl, start_balance


class Engine:
    def __init__(
        self,
        cfg: BotConfig,
        broker: Broker,
        notifier: Notifier,
        trade_log: TradeLog,
        strategies: dict[str, dict[str, Strategy]] | None = None,
    ):
        self.cfg = cfg
        self.broker = broker
        self.notifier = notifier
        self.trade_log = trade_log
        self.strategies = strategies or {
            sc.key: {name: make_strategy(name, cfg.params_for(sc, name)) for name in sc.strategies}
            for sc in cfg.symbols
        }
        self.risk = RiskManager(cfg.risk.daily_max_loss_pct)
        self.last_bar: dict[str, pd.Timestamp] = {}
        self.known_positions: dict[int, Position] = {}
        self.active_symbols: dict[str, str] = {}

    # ------------------------------------------------------------------
    def run_once(self) -> None:
        magic = self.cfg.magic

        # 1) 드라이런 비상손절 처리 / 실서버에서 사라진 포지션 감지
        for ev in self.broker.check_stops():
            self.known_positions.pop(ev.position.ticket, None)
            self._record("stop", ev.position, ev.price, ev.position.comment, "비상손절", ev.profit)
        current = {p.ticket: p for p in self.broker.positions(magic)}
        for ticket, p in list(self.known_positions.items()):
            if ticket not in current:
                self._record("closed_by_server", p, None, p.comment, "서버측 청산(비상손절 등 추정)", None)
                self.known_positions.pop(ticket)
        self.known_positions.update(current)

        # 2) 일일 손실 한도
        ref_symbol = self._ref_symbol()
        halted, newly, pnl, start_bal = self.risk.is_halted(self.broker, ref_symbol)
        if newly:
            self.notifier.send(
                f"일일 최대손실 도달: 오늘 손익 {pnl:,.2f} / 시작잔고 {start_bal:,.2f} "
                f"({self.cfg.risk.daily_max_loss_pct}%). 오늘 신규 진입 중단"
            )
            if self.cfg.risk.close_all_on_daily_limit:
                for p in self.broker.positions(magic):
                    self._close(p, p.comment, "일일손실한도 전량청산")

        # 3) 종목별 처리
        for sc in self.cfg.symbols:
            try:
                self._process_symbol(sc, halted)
            except Exception as exc:
                log.exception("[%s] 처리 중 오류", sc.key)
                self._notify_error(f"[{sc.key}] 오류: {exc}")

    # ------------------------------------------------------------------
    def _ref_symbol(self) -> str:
        sc = self.cfg.symbols[0]
        if sc.key not in self.active_symbols:
            self.active_symbols[sc.key] = self.broker.resolve_symbol(sc)
        return self.active_symbols[sc.key]

    def _process_symbol(self, sc: SymbolConfig, halted: bool) -> None:
        magic = self.cfg.magic
        symbol = self.broker.resolve_symbol(sc)
        prev_active = self.active_symbols.get(sc.key)
        self.active_symbols[sc.key] = symbol
        if prev_active and prev_active != symbol:
            self.notifier.send(f"[{sc.key}] 활성 월물 변경: {prev_active} → {symbol}")

        strategies = self.strategies[sc.key]
        warmup = max(s.warmup_bars() for s in strategies.values())
        df = self.broker.get_rates(symbol, sc.timeframe, sc.history_bars)
        if len(df) < warmup:
            log.warning("[%s] 봉 개수 부족 %d < %d", sc.key, len(df), warmup)
            return
        htf = (
            self.broker.get_rates(symbol, sc.htf_timeframe, sc.htf_history_bars)
            if sc.htf_timeframe
            else None
        )

        mine = [p for p in self.broker.positions(magic) if sc.owns_symbol(p.symbol, symbol)]

        # 선물 롤오버: 이전 월물 포지션을 청산하고 (옵션) 새 월물로 같은 방향 재진입
        if sc.is_futures:
            for p in [p for p in mine if p.symbol != symbol]:
                if not self._close(p, p.comment, f"롤오버 청산 → {symbol}"):
                    continue
                if sc.roll_reopen:
                    a = atr(df, self.cfg.risk.sl_atr_period).iloc[-1]
                    self._open(sc, symbol, p.direction, a, p.comment or sc.strategies[0], "롤오버 재진입",
                               volume=p.volume)
            mine = [p for p in self.broker.positions(magic) if sc.owns_symbol(p.symbol, symbol)]

        # 새 봉이 완성됐을 때만 신호 판단
        bar_time = df.index[-1]
        if self.last_bar.get(sc.key) == bar_time:
            return
        self.last_bar[sc.key] = bar_time

        signals = {
            name: s.compute(df, htf, sc.timeframe, sc.htf_timeframe).iloc[-1]
            for name, s in strategies.items()
        }
        log.info(
            "[%s] %s 봉 %s 신호 %s", sc.key, symbol, bar_time,
            {n: int(sig["entry"]) for n, sig in signals.items()},
        )

        pos = next((p for p in mine if p.symbol == symbol), None)

        # 반대 신호 청산
        if pos is not None:
            name = pos.comment if pos.comment in signals else sc.strategies[0]
            sig = signals[name]
            if (pos.direction > 0 and bool(sig["exit_long"])) or (pos.direction < 0 and bool(sig["exit_short"])):
                if not self._close(pos, name, "반대 신호"):
                    return
                pos = None

        # 신규 진입 (종목당 1포지션)
        if pos is not None:
            return
        if halted:
            log.info("[%s] 일일손실 한도로 진입 보류", sc.key)
            return
        if not self._in_session(sc, symbol):
            if any(int(sig["entry"]) != 0 for sig in signals.values()):
                log.info("[%s] 매매 시간대(%s, %s) 밖이라 진입 보류", sc.key, sc.sessions, sc.session_timezone)
            return
        for name in sc.strategies:
            sig = signals[name]
            direction = int(sig["entry"])
            if direction == 0 or pd.isna(sig["atr"]):
                continue
            if sc.max_spread_points > 0:
                spread = self.broker.spread_points(symbol)
                if spread > sc.max_spread_points:
                    self.notifier.send(
                        f"[{sc.key}] {name} {DIR_NAME[direction]} 신호 있으나 스프레드 {spread:.0f}pt "
                        f"> {sc.max_spread_points:.0f}pt 로 보류"
                    )
                    return
            self._open(sc, symbol, direction, float(sig["atr"]), name, "진입 신호")
            return

    # ------------------------------------------------------------------
    def _in_session(self, sc: SymbolConfig, symbol: str) -> bool:
        windows = sc.session_windows
        if not windows:
            return True
        if sc.session_timezone == "server":
            now = self.broker.server_now(symbol)
        else:
            from zoneinfo import ZoneInfo

            now = datetime.now(ZoneInfo(sc.session_timezone))
        return in_session(now, windows)

    def _volume(self, sc: SymbolConfig, symbol: str, direction: int, price: float, sl: float) -> float:
        """주문 수량. risk_pct 모드에서 최소 수량으로도 위험 한도를 넘으면 0."""
        risk = self.cfg.risk
        if risk.sizing != "risk_pct":
            return sc.lot
        loss_per_lot = abs(self.broker.calc_profit(symbol, direction, 1.0, price, sl))
        vmin, vstep, vmax = self.broker.volume_limits(symbol)
        balance = self.broker.account_balance()
        volume = risk_based_volume(balance, risk.risk_per_trade_pct, loss_per_lot, vmin, vstep, vmax, sc.max_lot)
        if volume <= 0:
            self.notifier.send(
                f"[{sc.key}] {symbol} {DIR_NAME[direction]} 진입 보류: 최소 수량 {vmin}랏의 손절 손실 "
                f"{loss_per_lot * vmin:,.2f} 이 위험 한도 {balance * risk.risk_per_trade_pct / 100:,.2f} "
                f"(잔고의 {risk.risk_per_trade_pct}%) 를 넘습니다"
            )
        else:
            log.info(
                "[%s] 수량 %.4g랏 = 잔고 %.2f x %.2f%% / 1랏 손절손실 %.2f",
                sc.key, volume, balance, risk.risk_per_trade_pct, loss_per_lot,
            )
        return volume

    def _open(self, sc: SymbolConfig, symbol: str, direction: int, atr_value: float,
              strategy: str, reason: str, volume: float | None = None) -> bool:
        tick = self.broker.get_tick(symbol)
        price = tick.ask if direction > 0 else tick.bid
        sl = price - direction * atr_value * self.cfg.risk.sl_atr_mult
        if volume is None:  # 롤오버 재진입은 기존 수량 유지
            volume = self._volume(sc, symbol, direction, price, sl)
            if volume <= 0:
                return False
        res = self.broker.open_position(symbol, direction, volume, sl, self.cfg.magic, strategy)
        if not res.ok:
            self._notify_error(f"[{sc.key}] {symbol} {DIR_NAME[direction]} 진입 실패: {res.message}")
            return False
        pos = Position(res.ticket or 0, symbol, direction, res.volume or volume,
                       res.price or price, res.sl or sl, 0.0, strategy)
        if res.ticket:
            self.known_positions[res.ticket] = pos
        self._record("open", pos, pos.price_open, strategy, reason, None, key=sc.key)
        return True

    def _close(self, pos: Position, strategy: str, reason: str) -> bool:
        res = self.broker.close_position(pos, self.cfg.magic, f"{strategy} exit")
        if not res.ok:
            self._notify_error(f"{pos.symbol} 청산 실패(#{pos.ticket}): {res.message}")
            return False
        self.known_positions.pop(pos.ticket, None)
        self._record("close", pos, res.price, strategy, reason, pos.profit)
        return True

    def _record(self, action, pos: Position, price, strategy, reason, profit, key: str = "") -> None:
        self.trade_log.write(
            key=key, symbol=pos.symbol, action=action, direction=DIR_NAME.get(pos.direction, pos.direction),
            volume=pos.volume, price=price, sl=pos.sl, strategy=strategy, reason=reason,
            ticket=pos.ticket, profit=profit,
        )
        label = {"open": "진입", "close": "청산", "stop": "손절", "closed_by_server": "종료"}.get(action, action)
        text = f"{label} {pos.symbol} {DIR_NAME.get(pos.direction, '')} {pos.volume}랏"
        if price is not None:
            text += f" @ {fmt_price(price)}"
        if action == "open":
            text += f" (SL {fmt_price(pos.sl)})"
        if profit is not None:
            text += f" 손익 {profit:,.2f}"
        text += f" [{strategy}] {reason}"
        self.notifier.send(text)

    def _notify_error(self, text: str) -> None:
        self.notifier.send(text, dedupe=True)
