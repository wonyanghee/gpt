"""테스트용 가짜 브로커/전략 (MT5 없이 엔진 로직 검증)."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from bot.broker import Broker, OrderResult, Position, Tick
from bot.strategies import Strategy


def make_bars(n=100, start="2026-01-05 00:00", freq="15min", base=100.0, step=0.0):
    idx = pd.date_range(start, periods=n, freq=freq)
    close = base + np.arange(n) * step
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "tick_volume": 100.0},
        index=idx,
    )


class FakeStrategy(Strategy):
    name = "fake"
    defaults = {}

    def __init__(self, entry=0, exit_long=False, exit_short=False, atr=1.0):
        super().__init__()
        self.entry, self.exit_long, self.exit_short, self.atr = entry, exit_long, exit_short, atr

    def warmup_bars(self):
        return 5

    def compute(self, df, htf_df, base_tf, htf_tf):
        n = len(df)
        entry = np.zeros(n, dtype=int)
        entry[-1] = self.entry
        el = np.zeros(n, dtype=bool)
        el[-1] = self.exit_long
        es = np.zeros(n, dtype=bool)
        es[-1] = self.exit_short
        return self._frame(df.index, entry, el, es, np.full(n, self.atr))


class FakeBroker(Broker):
    def __init__(self):
        self.rates: dict[str, pd.DataFrame] = {}
        self.ticks: dict[str, Tick] = {}
        self.open_positions: list[Position] = []
        self.active: dict[str, str] = {}
        self.spread = 10.0
        self.pnl = 0.0
        self.start_balance = 10000.0
        self.day = date(2026, 1, 5)
        self.next_ticket = 100
        self.orders: list[tuple] = []
        self.fail_open = False
        self.vol_limits = (0.01, 0.01, 100.0)

    def set_symbol(self, symbol, bars=None, bid=100.0, ask=100.2):
        self.rates[symbol] = bars if bars is not None else make_bars()
        self.ticks[symbol] = Tick(bid, ask, datetime(2026, 1, 5, 12))

    def resolve_symbol(self, sc):
        return self.active.get(sc.key, sc.symbol)

    def get_rates(self, symbol, timeframe, count):
        return self.rates[symbol].tail(count)

    def get_tick(self, symbol):
        return self.ticks[symbol]

    def spread_points(self, symbol):
        return self.spread

    def volume_limits(self, symbol):
        return self.vol_limits

    def server_now(self, symbol):
        return datetime(2026, 1, 5, 12)

    def account_balance(self):
        return self.start_balance

    def positions(self, magic):
        return list(self.open_positions)

    def open_position(self, symbol, direction, volume, sl, magic, comment):
        self.orders.append(("open", symbol, direction, volume, sl, comment))
        if self.fail_open:
            return OrderResult(False, message="rejected")
        tick = self.ticks[symbol]
        price = tick.ask if direction > 0 else tick.bid
        self.next_ticket += 1
        self.open_positions.append(Position(self.next_ticket, symbol, direction, volume, price, sl, 0.0, comment))
        return OrderResult(True, ticket=self.next_ticket, price=price, volume=volume, sl=sl)

    def close_position(self, position, magic, comment):
        self.orders.append(("close", position.symbol, position.ticket, comment))
        self.open_positions = [p for p in self.open_positions if p.ticket != position.ticket]
        tick = self.ticks[position.symbol]
        return OrderResult(True, ticket=position.ticket, price=tick.bid if position.direction > 0 else tick.ask)

    def calc_profit(self, symbol, direction, volume, price_open, price_close):
        return (price_close - price_open) * direction * volume * 100

    def daily_pnl(self, ref_symbol):
        return self.day, self.pnl, self.start_balance


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    def send(self, text, dedupe=False):
        self.messages.append(text)
