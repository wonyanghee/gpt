"""MT5 없이 봇을 돌려보는 시뮬레이션 브로커와 가상 시세 생성기 (데모/학습용).

SimBroker 는 미리 준비한 봉 데이터를 한 봉씩 재생한다.
- 커서 i : 봉 0..i 가 완성된 상태. 현재 시각 = 봉 i 의 마감 시각, 현재가 = 봉 i 의 종가
- 비상 손절은 봉의 고가/저가로 체크 (갭이면 시가 체결)
라이브와 같은 Engine 을 그대로 연결해 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

from .broker import Broker, BrokerError, OrderResult, Position, StopEvent, Tick
from .config import SymbolConfig
from .indicators import resample_ohlc, tf_minutes


def make_synthetic_bars(
    n: int,
    start_price: float,
    bar_vol: float,
    seed: int,
    start: str = "2026-01-05 00:00",
    timeframe: str = "M15",
) -> pd.DataFrame:
    """추세 구간과 횡보 구간이 번갈아 나오는 가상 봉 데이터 (주말 제외).

    실제 시장 데이터가 아니다. 봇 동작을 눈으로 확인하기 위한 용도이며
    여기서 나온 손익은 전략 성능의 근거가 될 수 없다.
    """
    rng = np.random.default_rng(seed)
    drift = np.empty(n)
    vol = np.empty(n)
    i = 0
    while i < n:
        length = int(rng.integers(40, 260))
        kind = rng.choice(["up", "down", "range"], p=[0.3, 0.3, 0.4])
        d = {"up": 0.12, "down": -0.12, "range": 0.0}[kind] * bar_vol * rng.uniform(0.6, 1.4)
        v = bar_vol * (rng.uniform(0.5, 0.8) if kind == "range" else rng.uniform(0.8, 1.3))
        drift[i : i + length] = d
        vol[i : i + length] = v
        i += length
    close = start_price + np.cumsum(drift + rng.normal(0, 1, n) * vol)
    open_ = np.r_[start_price, close[:-1]]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.35, n)) * vol
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.35, n)) * vol

    step = pd.Timedelta(minutes=tf_minutes(timeframe))
    idx = pd.date_range(start, periods=int(n * 1.5) + 10, freq=step)
    idx = idx[idx.dayofweek < 5][:n]
    return pd.DataFrame(
        {"open": open_.round(2), "high": high.round(2), "low": low.round(2), "close": close.round(2),
         "tick_volume": rng.integers(80, 600, n).astype(float)},
        index=idx,
    )


@dataclass
class SimSymbol:
    bars: pd.DataFrame
    timeframe: str
    contract_size: float
    spread: float
    point: float = 0.01
    volume_min: float = 0.01
    volume_step: float = 0.01
    volume_max: float = 100.0


@dataclass
class ClosedTrade:
    ticket: int
    symbol: str
    direction: int
    volume: float
    strategy: str
    entry_time: datetime
    entry_price: float
    sl: float
    exit_time: datetime
    exit_price: float
    reason: str  # "signal" | "stop"
    pnl: float


class SimBroker(Broker):
    def __init__(self, symbols: dict[str, SimSymbol], balance: float = 10000.0, start_index: int = 0):
        if not symbols:
            raise ValueError("symbols 가 비어 있습니다")
        lengths = {len(s.bars) for s in symbols.values()}
        if len(lengths) != 1:
            raise ValueError("모든 종목의 봉 개수가 같아야 합니다")
        self.symbols = symbols
        self.n = lengths.pop()
        self.i = start_index
        self.balance = balance
        self._positions: list[Position] = []
        self._opened_at: dict[int, tuple[int, datetime]] = {}
        self._stop_checked = -1
        self._next_ticket = 1
        self._realized: dict[date, float] = {}
        self.closed: list[ClosedTrade] = []
        self._htf_cache: dict[tuple[str, str], pd.DataFrame] = {}

    # -- 시간 진행 -------------------------------------------------------------
    def advance(self) -> bool:
        """다음 봉으로. 데이터가 끝나면 False."""
        if self.i + 1 >= self.n:
            return False
        self.i += 1
        return True

    def _sym(self, symbol: str) -> SimSymbol:
        try:
            return self.symbols[symbol]
        except KeyError as exc:
            raise BrokerError(f"시뮬레이션에 없는 종목: {symbol}") from exc

    def now(self, symbol: str | None = None) -> datetime:
        s = self._sym(symbol) if symbol else next(iter(self.symbols.values()))
        return (s.bars.index[self.i] + pd.Timedelta(minutes=tf_minutes(s.timeframe))).to_pydatetime()

    # -- Broker 인터페이스 --------------------------------------------------------
    def account_summary(self) -> dict:
        return {"login": "SIM", "server": "simulation", "balance": self.balance,
                "equity": self.equity(), "currency": "USD", "trade_mode": "SIMULATION"}

    def account_balance(self) -> float:
        return self.balance

    def equity(self) -> float:
        return self.balance + sum(p.profit for p in self.positions(0))

    def resolve_symbol(self, sc: SymbolConfig) -> str:
        return sc.symbol or sc.root

    def get_rates(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        s = self._sym(symbol)
        if timeframe == s.timeframe:
            return s.bars.iloc[max(0, self.i + 1 - count) : self.i + 1]
        key = (symbol, timeframe)
        if key not in self._htf_cache:
            self._htf_cache[key] = resample_ohlc(s.bars, timeframe)
        htf = self._htf_cache[key]
        # 현재 시각까지 '완성된' 상위봉만
        last_start = pd.Timestamp(self.now(symbol)) - pd.Timedelta(minutes=tf_minutes(timeframe))
        end = htf.index.searchsorted(last_start, side="right")
        return htf.iloc[max(0, end - count) : end]

    def get_tick(self, symbol: str) -> Tick:
        s = self._sym(symbol)
        bid = float(s.bars["close"].iloc[self.i])
        return Tick(bid, bid + s.spread, self.now(symbol))

    def spread_points(self, symbol: str) -> float:
        s = self._sym(symbol)
        return s.spread / s.point

    def volume_limits(self, symbol: str) -> tuple[float, float, float]:
        s = self._sym(symbol)
        return s.volume_min, s.volume_step, s.volume_max

    def server_now(self, symbol: str) -> datetime:
        return self.now(symbol)

    def calc_profit(self, symbol, direction, volume, price_open, price_close) -> float:
        return (price_close - price_open) * direction * volume * self._sym(symbol).contract_size

    def positions(self, magic: int) -> list[Position]:
        out = []
        for p in self._positions:
            tick = self.get_tick(p.symbol)
            price = tick.bid if p.direction > 0 else tick.ask
            p.profit = self.calc_profit(p.symbol, p.direction, p.volume, p.price_open, price)
            out.append(p)
        return out

    def open_position(self, symbol, direction, volume, sl, magic, comment) -> OrderResult:
        tick = self.get_tick(symbol)
        price = tick.ask if direction > 0 else tick.bid
        sl = round(sl, 2)
        ticket = self._next_ticket
        self._next_ticket += 1
        self._positions.append(Position(ticket, symbol, direction, volume, price, sl, 0.0, comment))
        self._opened_at[ticket] = (self.i, self.now(symbol))
        return OrderResult(True, ticket=ticket, price=price, volume=volume, sl=sl, message="sim")

    def _finish(self, p: Position, price: float, reason: str) -> float:
        pnl = self.calc_profit(p.symbol, p.direction, p.volume, p.price_open, price)
        self._positions = [x for x in self._positions if x.ticket != p.ticket]
        _, entry_time = self._opened_at.pop(p.ticket)
        now = self.now(p.symbol)
        self.balance += pnl
        self._realized[now.date()] = self._realized.get(now.date(), 0.0) + pnl
        self.closed.append(ClosedTrade(p.ticket, p.symbol, p.direction, p.volume, p.comment,
                                       entry_time, p.price_open, p.sl, now, price, reason, pnl))
        return pnl

    def close_position(self, position, magic, comment) -> OrderResult:
        if not any(p.ticket == position.ticket for p in self._positions):
            return OrderResult(False, message=f"포지션 없음: {position.ticket}")
        tick = self.get_tick(position.symbol)
        price = tick.bid if position.direction > 0 else tick.ask
        pnl = self._finish(position, price, "signal")
        return OrderResult(True, ticket=position.ticket, price=price, volume=position.volume,
                           message=f"sim profit={pnl:.2f}")

    def check_stops(self) -> list[StopEvent]:
        """현재 봉(커서)의 고가/저가로 손절 체크. 봉마다 한 번만."""
        if self._stop_checked == self.i:
            return []
        self._stop_checked = self.i
        events = []
        for p in list(self._positions):
            opened_i, _ = self._opened_at[p.ticket]
            if self.i <= opened_i or not p.sl:
                continue
            s = self._sym(p.symbol)
            bar = s.bars.iloc[self.i]
            if p.direction > 0 and bar["low"] <= p.sl:
                price = min(float(bar["open"]), p.sl)
            elif p.direction < 0 and bar["high"] + s.spread >= p.sl:
                price = max(float(bar["open"]) + s.spread, p.sl)
            else:
                continue
            events.append(StopEvent(p, price, self._finish(p, price, "stop")))
        return events

    def daily_pnl(self, ref_symbol: str) -> tuple[date, float, float]:
        today = self.now(ref_symbol).date()
        realized = self._realized.get(today, 0.0)
        floating = sum(p.profit for p in self.positions(0))
        return today, realized + floating, self.balance - realized
