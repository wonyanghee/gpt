from datetime import datetime

import pytest

from bot.broker import DryRunBroker, Tick
from fakes import FakeBroker


def make(tmp_path):
    market = FakeBroker()
    market.set_symbol("XAUUSD", bid=2000.0, ask=2000.3)
    dry = DryRunBroker(market, tmp_path / "state.json", initial_balance=5000)
    dry.connect = lambda: dry._load()  # FakeBroker 는 connect 불필요
    dry.connect()
    return market, dry


def test_dry_run_open_close_tracks_balance(tmp_path):
    market, dry = make(tmp_path)
    res = dry.open_position("XAUUSD", 1, 0.01, 1990.0, 777, "breakout")
    assert res.ok and res.price == 2000.3
    assert market.orders == []  # 실제 시장 브로커에는 주문이 가지 않음
    market.ticks["XAUUSD"] = Tick(2010.0, 2010.3, datetime(2026, 1, 5, 12))
    pos = dry.positions(777)[0]
    assert pos.profit == pytest.approx((2010.0 - 2000.3) * 0.01 * 100)
    dry.close_position(pos, 777, "exit")
    assert dry.positions(777) == []
    assert dry.account_balance() == pytest.approx(5000 + 9.7)
    day, pnl, start = dry.daily_pnl("XAUUSD")
    assert pnl == pytest.approx(9.7) and start == pytest.approx(5000)


def test_dry_run_stop_and_persistence(tmp_path):
    market, dry = make(tmp_path)
    dry.open_position("XAUUSD", -1, 0.01, 2005.0, 777, "trend")
    market.ticks["XAUUSD"] = Tick(2005.0, 2005.3, datetime(2026, 1, 5, 12))
    events = dry.check_stops()
    assert len(events) == 1 and events[0].price == 2005.0
    assert events[0].profit == pytest.approx((2005.0 - 2000.0) * -1 * 0.01 * 100)
    # 재시작해도 상태 유지
    dry2 = DryRunBroker(market, tmp_path / "state.json")
    dry2._load()
    assert dry2.account_balance() == pytest.approx(5000 - 5.0)
    assert dry2.positions(777) == []
