from datetime import datetime
from pathlib import Path

import pytest

from bot.broker import Position, Tick
from bot.config import config_from_dict
from bot.engine import Engine
from bot.notify import TradeLog
from fakes import FakeBroker, FakeStrategy, RecordingNotifier, make_bars


def make_cfg(**symbol_overrides):
    sym = {"key": "NASDAQ", "type": "cfd", "symbol": "US100", "lot": 0.1,
           "strategies": ["trend"], "htf_timeframe": None, **symbol_overrides}
    return config_from_dict({"symbols": [sym], "risk": {"sl_atr_mult": 3.0, "daily_max_loss_pct": 3.0}})


def make_engine(tmp_path: Path, cfg, strat: FakeStrategy, broker: FakeBroker | None = None, key="NASDAQ"):
    broker = broker or FakeBroker()
    if not broker.rates:
        broker.set_symbol("US100")
    notifier = RecordingNotifier()
    engine = Engine(cfg, broker, notifier, TradeLog(tmp_path / "trades.csv", "TEST"),
                    strategies={key: {"trend": strat}})
    return engine, broker, notifier


def new_bar(broker, symbol="US100"):
    df = broker.rates[symbol]
    broker.rates[symbol] = make_bars(len(df) + 1)


def test_long_entry_sets_emergency_stop(tmp_path):
    strat = FakeStrategy(entry=1, atr=2.0)
    engine, broker, notifier = make_engine(tmp_path, make_cfg(), strat)
    engine.run_once()
    assert len(broker.open_positions) == 1
    p = broker.open_positions[0]
    assert p.direction == 1 and p.volume == 0.1 and p.comment == "trend"
    assert p.sl == pytest.approx(100.2 - 2.0 * 3.0)  # ask - ATR*3
    assert any("진입" in m for m in notifier.messages)
    assert (tmp_path / "trades.csv").exists()


def test_short_entry_stop_above(tmp_path):
    engine, broker, _ = make_engine(tmp_path, make_cfg(), FakeStrategy(entry=-1, atr=1.0))
    engine.run_once()
    p = broker.open_positions[0]
    assert p.direction == -1 and p.sl == pytest.approx(100.0 + 3.0)


def test_signal_only_evaluated_once_per_bar(tmp_path):
    strat = FakeStrategy(entry=1)
    engine, broker, _ = make_engine(tmp_path, make_cfg(), strat)
    engine.run_once()
    broker.open_positions.clear()
    engine.run_once()  # 같은 봉 → 재진입 안 함
    assert broker.open_positions == []
    new_bar(broker)
    engine.run_once()
    assert len(broker.open_positions) == 1


def test_one_position_per_symbol(tmp_path):
    strat = FakeStrategy(entry=1)
    engine, broker, _ = make_engine(tmp_path, make_cfg(), strat)
    engine.run_once()
    new_bar(broker)
    engine.run_once()
    assert len(broker.open_positions) == 1


def test_opposite_signal_closes_and_reverses(tmp_path):
    strat = FakeStrategy(entry=1)
    engine, broker, _ = make_engine(tmp_path, make_cfg(), strat)
    engine.run_once()
    strat.entry, strat.exit_long = -1, True
    new_bar(broker)
    engine.run_once()
    assert [o[0] for o in broker.orders] == ["open", "close", "open"]
    assert len(broker.open_positions) == 1 and broker.open_positions[0].direction == -1


def test_exit_signal_without_new_entry(tmp_path):
    strat = FakeStrategy(entry=1)
    engine, broker, _ = make_engine(tmp_path, make_cfg(), strat)
    engine.run_once()
    strat.entry, strat.exit_long = 0, True
    new_bar(broker)
    engine.run_once()
    assert broker.open_positions == []


def test_daily_loss_limit_blocks_entries(tmp_path):
    engine, broker, notifier = make_engine(tmp_path, make_cfg(), FakeStrategy(entry=1))
    broker.pnl = -350.0  # 10000 의 -3.5%
    engine.run_once()
    assert broker.open_positions == []
    assert any("일일 최대손실" in m for m in notifier.messages)
    # 손실이 줄어도 같은 날은 계속 정지
    broker.pnl = 0.0
    new_bar(broker)
    engine.run_once()
    assert broker.open_positions == []


def test_spread_filter_blocks_entry(tmp_path):
    engine, broker, notifier = make_engine(tmp_path, make_cfg(max_spread_points=5), FakeStrategy(entry=1))
    broker.spread = 50
    engine.run_once()
    assert broker.open_positions == []
    assert any("스프레드" in m for m in notifier.messages)


def test_order_rejection_is_notified(tmp_path):
    engine, broker, notifier = make_engine(tmp_path, make_cfg(), FakeStrategy(entry=1))
    broker.fail_open = True
    engine.run_once()
    assert any("진입 실패" in m for m in notifier.messages)


def test_server_side_close_detected(tmp_path):
    engine, broker, notifier = make_engine(tmp_path, make_cfg(), FakeStrategy(entry=1))
    engine.run_once()
    broker.open_positions.clear()  # 서버에서 SL 체결됐다고 가정
    engine.run_once()
    assert any("서버측 청산" in m for m in notifier.messages)


def test_futures_rollover_closes_old_and_reopens(tmp_path):
    cfg = make_cfg(type="futures", symbol=None, root="MNQ", lot=1)
    broker = FakeBroker()
    broker.set_symbol("MNQH27", bid=200.0, ask=200.25)
    broker.set_symbol("MNQZ26", bid=199.0, ask=199.25)
    broker.active["NASDAQ"] = "MNQH27"
    broker.open_positions.append(Position(1, "MNQZ26", 1, 1, 150.0, 140.0, 0.0, "trend"))
    engine, broker, notifier = make_engine(tmp_path, cfg, FakeStrategy(entry=0), broker)
    engine.run_once()
    assert len(broker.open_positions) == 1
    p = broker.open_positions[0]
    assert p.symbol == "MNQH27" and p.direction == 1 and p.comment == "trend"
    assert any("롤오버" in m for m in notifier.messages)


def test_other_symbols_positions_are_ignored(tmp_path):
    broker = FakeBroker()
    broker.set_symbol("US100")
    broker.open_positions.append(Position(9, "XAUUSD", 1, 0.01, 2000, 1990, 0.0, "trend"))
    engine, broker, _ = make_engine(tmp_path, make_cfg(), FakeStrategy(entry=1), broker)
    engine.run_once()
    assert {p.symbol for p in broker.open_positions} == {"XAUUSD", "US100"}
