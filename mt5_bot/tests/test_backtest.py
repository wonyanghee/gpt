import numpy as np
import pandas as pd
import pytest

from bot.backtest import load_csv, run_backtest
from bot.config import config_from_dict
from bot.strategies import Strategy, make_strategy


class ScriptedStrategy(Strategy):
    """지정한 봉 번호에서 신호를 내는 전략."""

    name = "scripted"
    defaults = {}

    def __init__(self, entries=None, exits_long=(), exits_short=(), atr=1.0):
        super().__init__()
        self.entries = entries or {}
        self.exits_long, self.exits_short, self.atr = set(exits_long), set(exits_short), atr

    def warmup_bars(self):
        return 0

    def compute(self, df, htf_df, base_tf, htf_tf):
        n = len(df)
        entry = np.zeros(n, dtype=int)
        for i, d in self.entries.items():
            entry[i] = d
        el = np.array([i in self.exits_long for i in range(n)])
        es = np.array([i in self.exits_short for i in range(n)])
        return self._frame(df.index, entry, el, es, np.full(n, self.atr))


def symbol_cfg(spread=0.0, contract_size=1.0, commission=0.0):
    cfg = config_from_dict({"symbols": [{
        "key": "T", "symbol": "T", "lot": 1, "htf_timeframe": None, "strategies": ["trend"],
        "backtest": {"spread": spread, "contract_size": contract_size, "commission_per_lot": commission},
    }]})
    return cfg.symbols[0]


def frame(opens, highs=None, lows=None, closes=None):
    opens = np.asarray(opens, dtype=float)
    closes = np.asarray(closes if closes is not None else opens, dtype=float)
    highs = np.asarray(highs if highs is not None else np.maximum(opens, closes), dtype=float)
    lows = np.asarray(lows if lows is not None else np.minimum(opens, closes), dtype=float)
    idx = pd.date_range("2026-01-05", periods=len(opens), freq="15min")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx)


def test_entry_next_open_exit_on_signal_with_spread():
    df = frame([100, 101, 102, 103, 104, 105])
    strat = ScriptedStrategy(entries={1: 1}, exits_long={3})
    res = run_backtest(df, symbol_cfg(spread=0.5, contract_size=2), {"s": strat}, sl_atr_mult=3)
    t = res.trades.iloc[0]
    assert t["entry_price"] == 102.5  # 봉2 시가 + 스프레드
    assert t["exit_price"] == 104  # 봉4 시가 (Bid)
    assert t["pnl"] == pytest.approx((104 - 102.5) * 2)
    assert t["reason"] == "반대 신호"


def test_emergency_stop_hit_intrabar():
    df = frame([100, 100, 100, 100], lows=[99, 99, 96, 99])
    strat = ScriptedStrategy(entries={0: 1}, atr=1.0)
    res = run_backtest(df, symbol_cfg(), {"s": strat}, sl_atr_mult=3)
    t = res.trades.iloc[0]
    assert t["reason"] == "비상손절" and t["exit_price"] == 97
    assert t["pnl"] == pytest.approx(-3)


def test_stop_gap_fills_at_open():
    df = frame([100, 100, 90, 90], lows=[99, 99, 89, 89])
    res = run_backtest(df, symbol_cfg(), {"s": ScriptedStrategy(entries={0: 1})}, sl_atr_mult=3)
    assert res.trades.iloc[0]["exit_price"] == 90


def test_short_with_reverse_and_commission():
    df = frame([100, 100, 98, 96, 97, 99, 100])
    strat = ScriptedStrategy(entries={1: -1, 3: 1}, exits_short={3})
    res = run_backtest(df, symbol_cfg(commission=1.0), {"s": strat}, sl_atr_mult=10)
    tr = res.trades
    assert list(tr["direction"]) == [-1, 1]
    assert tr.iloc[0]["pnl"] == pytest.approx((98 - 97) * 1 - 1.0)
    assert tr.iloc[1]["reason"] == "기간 종료"
    assert res.stats["거래수"] == 2


def test_real_strategies_run_on_random_walk():
    rng = np.random.default_rng(3)
    close = 2000 + rng.normal(0, 2, 5000).cumsum()
    idx = pd.date_range("2026-01-05", periods=5000, freq="15min")
    df = pd.DataFrame({"open": np.r_[close[0], close[:-1]], "close": close}, index=idx)
    df["high"] = df[["open", "close"]].max(axis=1) + 0.5
    df["low"] = df[["open", "close"]].min(axis=1) - 0.5
    cfg = config_from_dict({"symbols": [{"key": "G", "symbol": "XAUUSD", "lot": 0.01,
                                         "strategies": ["trend", "breakout"],
                                         "backtest": {"contract_size": 100, "spread": 0.3}}]})
    sc = cfg.symbols[0]
    strats = {n: make_strategy(n, cfg.params_for(sc, n)) for n in sc.strategies}
    res = run_backtest(df, sc, strats, 3.0)
    assert res.stats["거래수"] > 10
    assert set(res.trades["strategy"]) <= {"trend", "breakout"}
    # 포지션이 겹치지 않음 (종목당 1포지션)
    tr = res.trades.sort_values("entry_time")
    assert (tr["entry_time"].iloc[1:].to_numpy() >= tr["exit_time"].iloc[:-1].to_numpy()).all()


def test_load_mt5_export_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(
        "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"
        "2026.01.05\t00:00:00\t1\t2\t0.5\t1.5\t10\t0\t5\n"
        "2026.01.05\t00:15:00\t1.5\t2.5\t1\t2\t12\t0\t5\n",
        encoding="utf-8",
    )
    df = load_csv(p)
    assert list(df.columns) == ["open", "high", "low", "close", "tick_volume"]
    assert df.index[1] == pd.Timestamp("2026-01-05 00:15")
