"""포지션 수량 계산.

- fixed    : 종목 설정의 lot 을 그대로 사용
- risk_pct : 비상 손절에 닿았을 때 손실이 잔고의 risk_per_trade_pct % 가 되도록 수량 계산
             수량 = (잔고 x 위험%) / (1랏 기준 손절 시 손실)
             거래 단위(volume_step)로 내림하고, 최소 수량 미만이면 0(진입 안 함)을 반환
"""
from __future__ import annotations

import math


def floor_to_step(volume: float, step: float) -> float:
    if step <= 0:
        return volume
    return round(math.floor(volume / step + 1e-9) * step, 8)


def risk_based_volume(
    balance: float,
    risk_pct: float,
    loss_per_lot: float,
    volume_min: float,
    volume_step: float,
    volume_max: float = 0.0,
    max_lot: float = 0.0,
) -> float:
    """손절 시 손실이 잔고의 risk_pct % 이하가 되는 최대 수량. 최소 수량도 안 되면 0."""
    if balance <= 0 or risk_pct <= 0 or loss_per_lot <= 0:
        return 0.0
    volume = balance * risk_pct / 100 / loss_per_lot
    if max_lot > 0:
        volume = min(volume, max_lot)
    if volume_max > 0:
        volume = min(volume, volume_max)
    volume = floor_to_step(volume, volume_step)
    return volume if volume >= volume_min - 1e-12 else 0.0
