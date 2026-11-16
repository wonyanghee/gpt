"""기술적 지표와 시간봉 유틸리티 (외부 TA 라이브러리 없이 pandas만 사용)."""
from __future__ import annotations

import numpy as np
import pandas as pd

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def tf_minutes(timeframe: str) -> int:
    try:
        return TIMEFRAME_MINUTES[timeframe]
    except KeyError as exc:
        raise ValueError(f"지원하지 않는 시간봉: {timeframe} (지원: {list(TIMEFRAME_MINUTES)})") from exc


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder 방식 ATR."""
    return true_range(df).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder 방식 ADX."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    alpha = 1 / period
    atr_ = true_range(df).ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def align_to_base(
    htf_series: pd.Series,
    htf_timeframe: str,
    base_index: pd.DatetimeIndex,
    base_timeframe: str,
) -> pd.Series:
    """상위봉 값을 하위봉에 붙인다. 미래 참조를 막기 위해 '완성된' 상위봉 값만 사용한다.

    상위봉(시가 시각 t)은 t + 상위봉길이 시점에 완성되고,
    하위봉(시가 시각 b)은 b + 하위봉길이 시점에 완성된다.
    하위봉이 완성되는 시점까지 완성된 가장 최근 상위봉 값을 사용한다.
    """
    avail = pd.Series(
        htf_series.to_numpy(),
        index=htf_series.index + pd.Timedelta(minutes=tf_minutes(htf_timeframe)),
    )
    avail = avail[~avail.index.duplicated(keep="last")].sort_index()
    close_times = base_index + pd.Timedelta(minutes=tf_minutes(base_timeframe))
    aligned = avail.reindex(close_times, method="ffill")
    return pd.Series(aligned.to_numpy(), index=base_index)


def resample_ohlc(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """하위봉 데이터를 상위봉으로 합친다 (백테스트용)."""
    rule = f"{tf_minutes(timeframe)}min"
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "tick_volume" in df.columns:
        agg["tick_volume"] = "sum"
    out = df.resample(rule, label="left", closed="left").agg(agg)
    return out.dropna(subset=["open"])
