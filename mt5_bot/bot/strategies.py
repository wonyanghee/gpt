"""매매 전략.

모든 전략은 '완성된 봉' 데이터프레임을 받아 봉마다 아래 컬럼을 계산한다.
  - entry      : +1 매수 진입, -1 매도 진입, 0 없음
  - exit_long  : True 이면 보유 중인 매수 포지션 청산 (반대 신호)
  - exit_short : True 이면 보유 중인 매도 포지션 청산 (반대 신호)
  - atr        : 비상 손절 계산용 ATR
라이브 봇은 마지막 행만, 백테스트는 전체 행을 사용하므로 두 환경의 로직이 동일하다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import adx, align_to_base, atr, ema


class Strategy:
    name: str = "base"
    defaults: dict = {}

    def __init__(self, **params):
        unknown = set(params) - set(self.defaults)
        if unknown:
            raise ValueError(f"{self.name} 전략에 알 수 없는 파라미터: {sorted(unknown)}")
        self.params = {**self.defaults, **params}

    def warmup_bars(self) -> int:
        raise NotImplementedError

    def compute(
        self,
        df: pd.DataFrame,
        htf_df: pd.DataFrame | None,
        base_tf: str,
        htf_tf: str | None,
    ) -> pd.DataFrame:
        raise NotImplementedError

    @staticmethod
    def _frame(index, entry, exit_long, exit_short, atr_series) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "entry": np.asarray(entry, dtype=int),
                "exit_long": np.asarray(exit_long, dtype=bool),
                "exit_short": np.asarray(exit_short, dtype=bool),
                "atr": np.asarray(atr_series, dtype=float),
            },
            index=index,
        )


class TrendStrategy(Strategy):
    """추세추종: EMA 교차 + 상위봉 EMA 방향 필터 + ADX 횡보 필터.

    진입: 빠른 EMA가 느린 EMA를 상향(하향) 돌파하고,
          상위봉 종가가 상위봉 EMA 위(아래)이며, ADX >= adx_min 일 때.
    청산: 반대 방향 교차 (필터와 무관하게 청산).
    """

    name = "trend"
    defaults = {
        "fast": 20,
        "slow": 50,
        "htf_ema": 200,  # 0 이면 상위봉 필터 끔
        "adx_period": 14,
        "adx_min": 20.0,  # 0 이면 ADX 필터 끔
        "atr_period": 14,
    }

    def __init__(self, **params):
        super().__init__(**params)
        if self.params["fast"] >= self.params["slow"]:
            raise ValueError("trend: fast 는 slow 보다 작아야 합니다")

    def warmup_bars(self) -> int:
        p = self.params
        return max(p["slow"], p["adx_period"] * 2, p["atr_period"]) + 1

    def compute(self, df, htf_df, base_tf, htf_tf):
        p = self.params
        close = df["close"]
        fast = ema(close, p["fast"])
        slow = ema(close, p["slow"])
        cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        cross_dn = (fast < slow) & (fast.shift(1) >= slow.shift(1))

        if p["htf_ema"] > 0 and htf_df is not None and htf_tf and len(htf_df) > 0:
            htf_ema = ema(htf_df["close"], p["htf_ema"])
            bias = np.sign(htf_df["close"] - htf_ema)
            bias = align_to_base(bias, htf_tf, df.index, base_tf)
            long_ok = bias > 0
            short_ok = bias < 0
        else:
            long_ok = pd.Series(True, index=df.index)
            short_ok = pd.Series(True, index=df.index)

        if p["adx_min"] > 0:
            adx_ok = adx(df, p["adx_period"]) >= p["adx_min"]
        else:
            adx_ok = pd.Series(True, index=df.index)

        entry = np.where(
            cross_up & long_ok & adx_ok, 1, np.where(cross_dn & short_ok & adx_ok, -1, 0)
        )
        return self._frame(df.index, entry, cross_dn, cross_up, atr(df, p["atr_period"]))


class BreakoutStrategy(Strategy):
    """N봉 박스권 돌파.

    박스: 직전 lookback 개 봉의 최고가/최저가.
    진입: 종가가 박스 상단 + buffer_atr*ATR 을 넘으면 매수, 하단 - buffer 아래면 매도.
          박스 폭이 max_box_atr*ATR 이하일 때만(=실제 횡보 박스일 때만) 인정.
          volume_mult > 0 이면 틱거래량이 평균의 volume_mult 배 이상일 때만 인정.
    청산: 반대 신호 = 종가가 직전 exit_lookback 개 봉의 반대편 극값을 돌파.
    """

    name = "breakout"
    defaults = {
        "lookback": 20,
        "exit_lookback": 10,
        "atr_period": 14,
        "max_box_atr": 5.0,  # 0 이면 박스 폭 필터 끔
        "buffer_atr": 0.1,
        "volume_mult": 0.0,  # 0 이면 거래량 필터 끔
        "volume_period": 20,
    }

    def warmup_bars(self) -> int:
        p = self.params
        return max(p["lookback"], p["exit_lookback"], p["atr_period"], p["volume_period"]) + 2

    def compute(self, df, htf_df, base_tf, htf_tf):
        p = self.params
        high, low, close = df["high"], df["low"], df["close"]
        a = atr(df, p["atr_period"])
        a_prev = a.shift(1)

        box_high = high.rolling(p["lookback"]).max().shift(1)
        box_low = low.rolling(p["lookback"]).min().shift(1)

        if p["max_box_atr"] > 0:
            box_ok = (box_high - box_low) <= p["max_box_atr"] * a_prev
        else:
            box_ok = pd.Series(True, index=df.index)

        if p["volume_mult"] > 0 and "tick_volume" in df.columns:
            vol = df["tick_volume"]
            vol_ok = vol >= vol.rolling(p["volume_period"]).mean().shift(1) * p["volume_mult"]
        else:
            vol_ok = pd.Series(True, index=df.index)

        up = close > box_high + p["buffer_atr"] * a_prev
        dn = close < box_low - p["buffer_atr"] * a_prev
        entry = np.where(up & box_ok & vol_ok, 1, np.where(dn & box_ok & vol_ok, -1, 0))

        exit_long = close < low.rolling(p["exit_lookback"]).min().shift(1)
        exit_short = close > high.rolling(p["exit_lookback"]).max().shift(1)
        return self._frame(df.index, entry, exit_long, exit_short, a)


STRATEGIES = {cls.name: cls for cls in (TrendStrategy, BreakoutStrategy)}


def make_strategy(name: str, params: dict | None = None) -> Strategy:
    try:
        cls = STRATEGIES[name]
    except KeyError as exc:
        raise ValueError(f"알 수 없는 전략: {name} (지원: {list(STRATEGIES)})") from exc
    return cls(**(params or {}))
