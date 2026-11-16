import pandas as pd
import pytest

from bot.config import config_from_dict
from bot.engine import Engine
from bot.notify import TradeLog
from bot.sim import SimBroker, SimSymbol, make_synthetic_bars
from fakes import RecordingNotifier, make_bars


def sim(bars=None, **kw):
    bars = bars if bars is not None else make_bars(50)
    return SimBroker({"X": SimSymbol(bars, "M15", contract_size=10, spread=0.2, **kw)}, balance=1000, start_index=10)


def test_synthetic_bars_are_valid_and_reproducible():
    a = make_synthetic_bars(3000, 2000, 1.5, seed=1)
    b = make_synthetic_bars(3000, 2000, 1.5, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 3000 and a.index.is_monotonic_increasing and a.index.is_unique
    assert (a.index.dayofweek < 5).all()
    assert (a["high"] >= a[["open", "close"]].max(axis=1)).all()
    assert (a["low"] <= a[["open", "close"]].min(axis=1)).all()


def test_rates_only_expose_completed_bars():
    bars = make_bars(50, start="2026-01-05 00:00")
    b = sim(bars)
    m15 = b.get_rates("X", "M15", 600)
    assert len(m15) == 11 and m15.index[-1] == bars.index[10]
    # 현재 시각 02:45 → 완성된 H1 봉은 00:00, 01:00 두 개 (02:00 봉은 진행 중)
    h1 = b.get_rates("X", "H1", 600)
    assert list(h1.index) == [pd.Timestamp("2026-01-05 00:00"), pd.Timestamp("2026-01-05 01:00")]


def test_open_close_and_balance():
    b = sim()
    r = b.open_position("X", 1, 0.5, 90.0, 1, "trend")
    assert r.price == pytest.approx(100.2)  # ask
    b.advance()
    p = b.positions(1)[0]
    assert p.profit == pytest.approx((100.0 - 100.2) * 0.5 * 10)
    b.close_position(p, 1, "exit")
    assert b.balance == pytest.approx(1000 - 1.0) and b.positions(1) == []
    assert b.closed[0].reason == "signal"


def test_stop_hits_on_later_bar_only():
    bars = make_bars(50)  # low = 99.5
    b = sim(bars)
    b.open_position("X", 1, 1.0, 99.8, 1, "trend")
    assert b.check_stops() == []  # 진입한 봉에서는 체크 안 함
    b.advance()
    ev = b.check_stops()
    assert len(ev) == 1 and ev[0].price == pytest.approx(99.8)
    assert ev[0].profit == pytest.approx((99.8 - 100.2) * 10)
    assert b.check_stops() == []  # 같은 봉 중복 체크 없음
    day, pnl, start = b.daily_pnl("X")
    assert pnl == pytest.approx(-4.0) and start == pytest.approx(1000)


def test_engine_runs_on_sim(tmp_path):
    cfg = config_from_dict({
        "risk": {"sizing": "risk_pct", "risk_per_trade_pct": 1.0},
        "symbols": [{"key": "GOLD", "symbol": "XAUUSD", "strategies": ["breakout", "trend"],
                     "backtest": {"contract_size": 100, "spread": 0.3}}],
    })
    bars = make_synthetic_bars(2400 + 960, 2650, 1.6, seed=3)
    b = SimBroker({"XAUUSD": SimSymbol(bars, "M15", 100, 0.3)}, balance=10000, start_index=2399)
    eng = Engine(cfg, b, RecordingNotifier(), TradeLog(tmp_path / "t.csv", "SIM"))
    while True:
        eng.run_once()
        if not b.advance():
            break
    assert len(b.closed) > 5
    assert len(b.positions(0)) <= 1
    # 손절 거래의 손실은 진입 당시 잔고의 1% 근처 (갭 없으면 이하)
    stops = [t for t in b.closed if t.reason == "stop"]
    assert all(t.pnl < 0 for t in stops)
    assert b.balance == pytest.approx(10000 + sum(t.pnl for t in b.closed))
