import numpy as np
import pandas as pd

from bot.indicators import adx, align_to_base, atr, ema, resample_ohlc
from fakes import make_bars


def test_ema_matches_pandas():
    s = pd.Series(np.arange(50, dtype=float))
    out = ema(s, 10)
    assert out.iloc[:9].isna().all()
    expected = s.ewm(span=10, adjust=False).mean()
    assert np.isclose(out.iloc[-1], expected.iloc[-1])


def test_atr_constant_range():
    df = make_bars(60)  # high-low = 1, 종가 변화 0
    assert np.isclose(atr(df, 14).iloc[-1], 1.0)


def test_adx_high_in_strong_trend():
    df = make_bars(200, step=1.0)
    assert adx(df, 14).iloc[-1] > 50


def test_align_to_base_has_no_lookahead():
    base_idx = pd.date_range("2026-01-05 09:00", periods=8, freq="15min")  # 09:00 ~ 10:45
    htf = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-05 09:00", "2026-01-05 10:00"]))
    out = align_to_base(htf, "H1", base_idx, "M15")
    # 09:00 H1 봉은 10:00 에 완성 → 09:45 봉(10:00 완성)부터 사용 가능
    assert out.iloc[:3].isna().all()
    assert list(out.iloc[3:7]) == [1.0, 1.0, 1.0, 1.0]
    assert out.iloc[7] == 2.0  # 10:45 봉은 11:00 완성 → 10:00 H1 봉 사용 가능


def test_resample_ohlc():
    df = make_bars(8, start="2026-01-05 09:00", step=1.0)
    h1 = resample_ohlc(df, "H1")
    assert len(h1) == 2
    first = h1.iloc[0]
    assert first["open"] == 100 and first["close"] == 103
    assert first["high"] == 103.5 and first["low"] == 99.5
    assert first["tick_volume"] == 400
