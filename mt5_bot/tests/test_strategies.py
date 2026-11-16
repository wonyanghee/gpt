import numpy as np
import pandas as pd
import pytest

from bot.indicators import resample_ohlc
from bot.strategies import BreakoutStrategy, TrendStrategy, make_strategy


def bars_from_close(close, start="2026-01-05", freq="15min", wiggle=0.3):
    close = np.asarray(close, dtype=float)
    idx = pd.date_range(start, periods=len(close), freq=freq)
    open_ = np.r_[close[0], close[:-1]]
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + wiggle,
            "low": np.minimum(open_, close) - wiggle,
            "close": close,
            "tick_volume": 100.0,
        },
        index=idx,
    )


def test_trend_long_then_short_without_filters():
    close = np.r_[np.linspace(100, 80, 120), np.linspace(80, 130, 150), np.linspace(130, 90, 150)]
    df = bars_from_close(close)
    s = TrendStrategy(fast=5, slow=20, htf_ema=0, adx_min=0)
    sig = s.compute(df, None, "M15", None)
    entries = sig.loc[sig["entry"] != 0, "entry"].tolist()
    assert entries[:2] == [1, -1]
    # 진입 봉과 반대 청산 신호가 일치
    assert (sig["exit_short"] == (sig["entry"] == 1)).loc[sig["entry"] == 1].all()
    assert sig.loc[sig["entry"] == -1, "exit_long"].all()


def test_trend_htf_filter_blocks_counter_trend_entries():
    rng = np.random.default_rng(1)
    # 강한 상승 추세 + 노이즈: 하락 교차가 있어도 매도 진입은 막혀야 함
    close = 100 + np.arange(3000) * 0.05 + rng.normal(0, 1.5, 3000).cumsum() * 0.2
    df = bars_from_close(close)
    htf = resample_ohlc(df, "H1")
    s = TrendStrategy(fast=10, slow=30, htf_ema=50, adx_min=0)
    sig = s.compute(df, htf, "M15", "H1")
    from bot.indicators import align_to_base, ema

    bias = align_to_base(np.sign(htf["close"] - ema(htf["close"], 50)), "H1", df.index, "M15")
    assert (bias.loc[sig["entry"] == 1] > 0).all()
    assert (bias.loc[sig["entry"] == -1] < 0).all()
    assert (sig["entry"] != 0).sum() > 0


def test_breakout_entry_and_exit():
    flat = 100 + np.sin(np.arange(40)) * 0.5  # 박스권
    close = np.r_[flat, [103.0, 104.0, 105.0], np.linspace(105, 95, 15)]
    df = bars_from_close(close, wiggle=0.2)
    s = BreakoutStrategy(lookback=20, exit_lookback=5, max_box_atr=5.0, buffer_atr=0.1)
    sig = s.compute(df, None, "M15", None)
    first_entry = sig.index[sig["entry"] != 0][0]
    assert first_entry == df.index[40]
    assert sig.loc[first_entry, "entry"] == 1
    # 이후 하락 구간에서 반대 신호 청산이 나와야 함
    assert sig["exit_long"].iloc[43:].any()


def test_breakout_box_width_filter():
    close = np.r_[np.linspace(90, 110, 40), [115.0]]  # 박스가 아니라 추세 → 폭 필터에 걸림
    df = bars_from_close(close, wiggle=0.05)
    strict = BreakoutStrategy(lookback=20, max_box_atr=2.0).compute(df, None, "M15", None)
    loose = BreakoutStrategy(lookback=20, max_box_atr=0).compute(df, None, "M15", None)
    assert strict["entry"].iloc[-1] == 0
    assert loose["entry"].iloc[-1] == 1


def test_signals_do_not_change_when_future_bars_added():
    rng = np.random.default_rng(7)
    close = 100 + rng.normal(0, 1, 1500).cumsum()
    df = bars_from_close(close)
    for strat in (TrendStrategy(htf_ema=50), BreakoutStrategy()):
        full = strat.compute(df, resample_ohlc(df, "H1"), "M15", "H1")
        part_df = df.iloc[:1000]
        part = strat.compute(part_df, resample_ohlc(part_df, "H1"), "M15", "H1")
        pd.testing.assert_frame_equal(full.iloc[:1000], part)


def test_make_strategy_validation():
    with pytest.raises(ValueError):
        make_strategy("unknown")
    with pytest.raises(ValueError):
        make_strategy("trend", {"fast": 50, "slow": 20})
    with pytest.raises(ValueError):
        make_strategy("breakout", {"typo": 1})
