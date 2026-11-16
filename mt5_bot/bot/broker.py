"""브로커 연결 계층.

- Broker       : 엔진이 사용하는 공통 인터페이스
- MT5Broker    : MetaTrader5 공식 파이썬 라이브러리 (Windows + MT5 터미널 필요)
- DryRunBroker : 시세는 실제 MT5에서 받고, 주문은 보내지 않고 가상으로 체결/기록
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .config import SymbolConfig

log = logging.getLogger(__name__)


class BrokerError(RuntimeError):
    pass


@dataclass
class Position:
    ticket: int
    symbol: str
    direction: int  # +1 매수, -1 매도
    volume: float
    price_open: float
    sl: float
    profit: float = 0.0
    comment: str = ""


@dataclass
class Tick:
    bid: float
    ask: float
    time: datetime


@dataclass
class OrderResult:
    ok: bool
    ticket: int | None = None
    price: float | None = None
    volume: float | None = None
    sl: float | None = None
    message: str = ""


@dataclass
class StopEvent:
    """드라이런에서 비상 손절이 체결된 기록."""

    position: Position
    price: float
    profit: float


class Broker:
    def connect(self) -> None: ...
    def shutdown(self) -> None: ...
    def account_summary(self) -> dict: ...
    def account_balance(self) -> float: ...
    def resolve_symbol(self, sc: SymbolConfig) -> str: ...
    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame: ...
    def get_tick(self, symbol: str) -> Tick: ...
    def spread_points(self, symbol: str) -> float: ...
    def server_now(self, symbol: str) -> datetime: ...
    def positions(self, magic: int) -> list[Position]: ...
    def open_position(
        self, symbol: str, direction: int, volume: float, sl: float, magic: int, comment: str
    ) -> OrderResult: ...
    def close_position(self, position: Position, magic: int, comment: str) -> OrderResult: ...
    def calc_profit(
        self, symbol: str, direction: int, volume: float, price_open: float, price_close: float
    ) -> float: ...
    def daily_pnl(self, ref_symbol: str) -> tuple[date, float, float]:
        """(서버기준 오늘 날짜, 오늘 손익(실현+평가), 오늘 시작 잔고)"""
        ...

    def check_stops(self) -> list[StopEvent]:
        """실서버는 손절을 서버가 처리하므로 빈 목록. 드라이런만 직접 처리."""
        return []


# ---------------------------------------------------------------------------
# MetaTrader5
# ---------------------------------------------------------------------------


class MT5Broker(Broker):
    def __init__(
        self,
        terminal_path: str = "",
        login: str | None = None,
        password: str | None = None,
        server: str | None = None,
    ):
        try:
            import MetaTrader5 as mt5  # noqa: N813
        except ImportError as exc:
            raise BrokerError(
                "MetaTrader5 패키지가 없습니다. Windows 에서 `pip install MetaTrader5` 후 실행하세요."
            ) from exc
        self.mt5 = mt5
        self.terminal_path = terminal_path
        self.login = login
        self.password = password
        self.server = server

    # -- 연결 ---------------------------------------------------------------
    def connect(self) -> None:
        mt5 = self.mt5
        kwargs = {}
        if self.login:
            kwargs.update(login=int(self.login), password=self.password or "", server=self.server or "")
        ok = mt5.initialize(self.terminal_path, **kwargs) if self.terminal_path else mt5.initialize(**kwargs)
        if not ok:
            raise BrokerError(f"MT5 initialize 실패: {mt5.last_error()}")
        if mt5.account_info() is None:
            raise BrokerError(f"MT5 계좌 정보를 가져올 수 없습니다: {mt5.last_error()}")

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def ensure_connected(self) -> None:
        if self.mt5.terminal_info() is None:
            log.warning("MT5 연결이 끊겨 재접속합니다")
            self.connect()

    def account_summary(self) -> dict:
        info = self.mt5.account_info()
        if info is None:
            raise BrokerError(f"account_info 실패: {self.mt5.last_error()}")
        trade_mode = {0: "demo", 1: "contest", 2: "real"}.get(info.trade_mode, str(info.trade_mode))
        return {
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "equity": info.equity,
            "currency": info.currency,
            "trade_mode": trade_mode,
            "margin_mode": info.margin_mode,  # 0 netting(장외) / 1 exchange / 2 hedging
        }

    def account_balance(self) -> float:
        return float(self.account_summary()["balance"])

    # -- 종목 ---------------------------------------------------------------
    def _select(self, symbol: str):
        if not self.mt5.symbol_select(symbol, True):
            raise BrokerError(f"종목을 찾을 수 없습니다: {symbol} (브로커 종목명 확인)")
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise BrokerError(f"symbol_info 실패: {symbol} {self.mt5.last_error()}")
        return info

    def resolve_symbol(self, sc: SymbolConfig) -> str:
        if not sc.is_futures or sc.symbol:
            return sc.symbol
        # 선물: root 로 시작하는 종목 중 '만기까지 roll_days 이상 남은' 가장 가까운 월물
        cutoff = datetime.now(timezone.utc).timestamp() + sc.roll_days_before_expiry * 86400
        candidates = []
        for s in self.mt5.symbols_get(group=f"{sc.root}*") or ():
            if not s.name.startswith(sc.root):
                continue
            if s.trade_mode == self.mt5.SYMBOL_TRADE_MODE_DISABLED:
                continue
            if s.expiration_time and s.expiration_time > cutoff:
                candidates.append(s)
        if not candidates:
            raise BrokerError(
                f"[{sc.key}] {sc.root}* 에서 거래 가능한 월물을 찾지 못했습니다. "
                "MT5 종목명 또는 roll_days_before_expiry 를 확인하세요"
            )
        return min(candidates, key=lambda s: s.expiration_time).name

    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        self._select(symbol)
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}")
        # start_pos=1 : 현재 만들어지는 중인 봉은 제외하고 완성된 봉만
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1, count)
        if rates is None or len(rates) == 0:
            raise BrokerError(f"시세 조회 실패: {symbol} {timeframe} {self.mt5.last_error()}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df.set_index("time")[["open", "high", "low", "close", "tick_volume"]]

    def get_tick(self, symbol: str) -> Tick:
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise BrokerError(f"호가 조회 실패: {symbol} {self.mt5.last_error()}")
        return Tick(tick.bid, tick.ask, datetime.fromtimestamp(tick.time, tz=timezone.utc).replace(tzinfo=None))

    def spread_points(self, symbol: str) -> float:
        info = self._select(symbol)
        tick = self.get_tick(symbol)
        return (tick.ask - tick.bid) / info.point

    def server_now(self, symbol: str) -> datetime:
        return self.get_tick(symbol).time

    # -- 포지션/주문 -----------------------------------------------------------
    def positions(self, magic: int) -> list[Position]:
        out = []
        for p in self.mt5.positions_get() or ():
            if p.magic != magic:
                continue
            out.append(
                Position(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    direction=1 if p.type == self.mt5.POSITION_TYPE_BUY else -1,
                    volume=p.volume,
                    price_open=p.price_open,
                    sl=p.sl,
                    profit=p.profit,
                    comment=p.comment,
                )
            )
        return out

    def _filling(self, info) -> int:
        # symbol_info.filling_mode 비트: 1=FOK, 2=IOC
        if info.filling_mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if info.filling_mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    @staticmethod
    def _normalize_volume(info, volume: float) -> float:
        step = info.volume_step or 0.01
        vol = round(round(volume / step) * step, 8)
        return max(info.volume_min, min(info.volume_max, vol))

    def _send(self, request: dict) -> OrderResult:
        res = self.mt5.order_send(request)
        if res is None:
            return OrderResult(False, message=f"order_send 실패: {self.mt5.last_error()}")
        ok_codes = {
            self.mt5.TRADE_RETCODE_DONE,
            self.mt5.TRADE_RETCODE_DONE_PARTIAL,
            self.mt5.TRADE_RETCODE_PLACED,
        }
        if res.retcode not in ok_codes:
            return OrderResult(False, message=f"주문 거부 retcode={res.retcode} {res.comment}")
        return OrderResult(True, ticket=res.order, price=res.price, volume=res.volume, message=res.comment)

    def open_position(self, symbol, direction, volume, sl, magic, comment) -> OrderResult:
        info = self._select(symbol)
        tick = self.get_tick(symbol)
        price = tick.ask if direction > 0 else tick.bid
        min_dist = info.trade_stops_level * info.point
        sl = min(sl, price - min_dist) if direction > 0 else max(sl, price + min_dist)
        sl = round(sl, info.digits)
        vol = self._normalize_volume(info, volume)
        result = self._send(
            {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": vol,
                "type": self.mt5.ORDER_TYPE_BUY if direction > 0 else self.mt5.ORDER_TYPE_SELL,
                "price": price,
                "sl": sl,
                "deviation": 20,
                "magic": magic,
                "comment": comment[:31],
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self._filling(info),
            }
        )
        result.sl = sl
        result.volume = result.volume or vol
        return result

    def close_position(self, position, magic, comment) -> OrderResult:
        info = self._select(position.symbol)
        tick = self.get_tick(position.symbol)
        closing_buy = position.direction < 0
        return self._send(
            {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": self.mt5.ORDER_TYPE_BUY if closing_buy else self.mt5.ORDER_TYPE_SELL,
                "position": position.ticket,
                "price": tick.ask if closing_buy else tick.bid,
                "deviation": 20,
                "magic": magic,
                "comment": comment[:31],
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self._filling(info),
            }
        )

    def calc_profit(self, symbol, direction, volume, price_open, price_close) -> float:
        order_type = self.mt5.ORDER_TYPE_BUY if direction > 0 else self.mt5.ORDER_TYPE_SELL
        profit = self.mt5.order_calc_profit(order_type, symbol, volume, price_open, price_close)
        if profit is None:
            raise BrokerError(f"order_calc_profit 실패: {symbol} {self.mt5.last_error()}")
        return float(profit)

    def daily_pnl(self, ref_symbol: str) -> tuple[date, float, float]:
        mt5 = self.mt5
        now = self.server_now(ref_symbol)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        deals = mt5.history_deals_get(day_start, day_start + timedelta(days=1)) or ()
        realized = sum(
            d.profit + d.commission + d.swap + getattr(d, "fee", 0.0)
            for d in deals
            if d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
        )
        floating = sum(p.profit for p in mt5.positions_get() or ())
        balance = self.account_balance()
        return day_start.date(), realized + floating, balance - realized


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


class DryRunBroker(Broker):
    """실제 시세를 쓰되 주문은 가상으로 처리. 상태는 JSON 파일로 저장해 재시작해도 유지."""

    def __init__(self, market: Broker, state_file: Path, initial_balance: float | None = None):
        self.market = market
        self.state_file = Path(state_file)
        self.initial_balance = initial_balance
        self.state = {"balance": None, "next_ticket": 1, "positions": [], "realized": {}}

    # -- 상태 저장 -------------------------------------------------------------
    def _load(self) -> None:
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text(encoding="utf-8"))
        if self.state.get("balance") is None:
            self.state["balance"] = (
                float(self.initial_balance) if self.initial_balance is not None else self.market.account_balance()
            )
            self._save()

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    # -- 위임 ---------------------------------------------------------------
    def connect(self) -> None:
        self.market.connect()
        self._load()

    def shutdown(self) -> None:
        self.market.shutdown()

    def account_summary(self) -> dict:
        summary = dict(self.market.account_summary())
        summary["balance"] = self.state["balance"]
        summary["trade_mode"] = f"DRY-RUN (실계좌 모드: {summary.get('trade_mode')})"
        return summary

    def account_balance(self) -> float:
        return float(self.state["balance"])

    def resolve_symbol(self, sc):
        return self.market.resolve_symbol(sc)

    def get_rates(self, symbol, timeframe, count):
        return self.market.get_rates(symbol, timeframe, count)

    def get_tick(self, symbol):
        return self.market.get_tick(symbol)

    def spread_points(self, symbol):
        return self.market.spread_points(symbol)

    def server_now(self, symbol):
        return self.market.server_now(symbol)

    def calc_profit(self, symbol, direction, volume, price_open, price_close):
        return self.market.calc_profit(symbol, direction, volume, price_open, price_close)

    # -- 가상 주문 -------------------------------------------------------------
    def _today_key(self, symbol: str) -> str:
        return self.market.server_now(symbol).date().isoformat()

    def positions(self, magic: int) -> list[Position]:
        out = []
        for raw in self.state["positions"]:
            if raw.get("magic") != magic:
                continue
            p = Position(**{k: v for k, v in raw.items() if k != "magic"})
            tick = self.market.get_tick(p.symbol)
            close_price = tick.bid if p.direction > 0 else tick.ask
            p.profit = self.market.calc_profit(p.symbol, p.direction, p.volume, p.price_open, close_price)
            out.append(p)
        return out

    def open_position(self, symbol, direction, volume, sl, magic, comment) -> OrderResult:
        tick = self.market.get_tick(symbol)
        price = tick.ask if direction > 0 else tick.bid
        ticket = int(self.state["next_ticket"])
        self.state["next_ticket"] = ticket + 1
        pos = Position(ticket, symbol, direction, volume, price, sl, 0.0, comment[:31])
        self.state["positions"].append({**asdict(pos), "magic": magic})
        self._save()
        return OrderResult(True, ticket=ticket, price=price, volume=volume, sl=sl, message="dry-run")

    def _close(self, position: Position, price: float) -> float:
        profit = self.market.calc_profit(
            position.symbol, position.direction, position.volume, position.price_open, price
        )
        self.state["positions"] = [p for p in self.state["positions"] if p["ticket"] != position.ticket]
        day = self._today_key(position.symbol)
        self.state["realized"][day] = self.state["realized"].get(day, 0.0) + profit
        self.state["balance"] = float(self.state["balance"]) + profit
        self._save()
        return profit

    def close_position(self, position, magic, comment) -> OrderResult:
        if not any(p["ticket"] == position.ticket for p in self.state["positions"]):
            return OrderResult(False, message=f"가상 포지션 없음: {position.ticket}")
        tick = self.market.get_tick(position.symbol)
        price = tick.bid if position.direction > 0 else tick.ask
        profit = self._close(position, price)
        return OrderResult(True, ticket=position.ticket, price=price, volume=position.volume,
                           message=f"dry-run profit={profit:.2f}")

    def check_stops(self) -> list[StopEvent]:
        events = []
        for raw in list(self.state["positions"]):
            p = Position(**{k: v for k, v in raw.items() if k != "magic"})
            if not p.sl:
                continue
            tick = self.market.get_tick(p.symbol)
            hit = (p.direction > 0 and tick.bid <= p.sl) or (p.direction < 0 and tick.ask >= p.sl)
            if hit:
                profit = self._close(p, p.sl)
                events.append(StopEvent(p, p.sl, profit))
        return events

    def daily_pnl(self, ref_symbol: str) -> tuple[date, float, float]:
        today = self.market.server_now(ref_symbol).date()
        realized = float(self.state["realized"].get(today.isoformat(), 0.0))
        floating = 0.0
        magics = {p.get("magic") for p in self.state["positions"]}
        for m in magics:
            floating += sum(p.profit for p in self.positions(m))
        balance = float(self.state["balance"])
        return today, realized + floating, balance - realized
