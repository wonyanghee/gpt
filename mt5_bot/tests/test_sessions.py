from datetime import datetime, time
from pathlib import Path

import numpy as np
import pytest

from bot.config import ConfigError, config_from_dict
from bot.backtest import run_backtest
from bot.engine import Engine
from bot.notify import TradeLog
from bot.sessions import in_session, parse_sessions
from fakes import FakeBroker, FakeStrategy, RecordingNotifier, make_bars
from test_backtest import ScriptedStrategy, frame


def test_parse_and_membership():
    w = parse_sessions(["09:00-12:00", "22:00-02:00"])
    assert in_session(time(9, 0), w) and in_session(time(11, 59), w)
    assert not in_session(time(12, 0), w)  # 종료 시각 제외
    assert in_session(time(23, 30), w) and in_session(time(1, 59), w)
    assert not in_session(time(2, 0), w) and not in_session(time(15, 0), w)
    assert in_session(time(3, 0), [])  # 비어 있으면 제한 없음
    assert in_session(time(23, 59), parse_sessions("08:00-24:00"))


@pytest.mark.parametrize("bad", ["9-17", "25:00-26:00", "09:00-09:00", "09:60-10:00", "abc"])
def test_parse_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        parse_sessions([bad])


def cfg_with(sessions, tz="server"):
    return config_from_dict({"symbols": [{
        "key": "NASDAQ", "symbol": "US100", "lot": 0.1, "htf_timeframe": None,
        "strategies": ["trend"], "sessions": sessions, "session_timezone": tz,
    }]})


def test_config_validation():
    with pytest.raises(ConfigError):
        cfg_with(["nope"])
    with pytest.raises(ConfigError):
        cfg_with(["09:00-10:00"], tz="Mars/Olympus")
    assert cfg_with("09:00-10:00").symbols[0].sessions == ["09:00-10:00"]
    assert cfg_with(["09:00-10:00"], tz="Asia/Seoul").symbols[0].session_timezone == "Asia/Seoul"


def engine_for(tmp_path, cfg, strat):
    broker = FakeBroker()  # server_now = 12:00
    broker.set_symbol("US100")
    eng = Engine(cfg, broker, RecordingNotifier(), TradeLog(tmp_path / "t.csv", "TEST"),
                 strategies={"NASDAQ": {"trend": strat}})
    return eng, broker


def test_engine_blocks_entry_outside_session(tmp_path):
    eng, broker = engine_for(tmp_path, cfg_with(["13:00-15:00"]), FakeStrategy(entry=1))
    eng.run_once()
    assert broker.open_positions == []


def test_engine_allows_entry_inside_session(tmp_path):
    eng, broker = engine_for(tmp_path, cfg_with(["09:00-13:00"]), FakeStrategy(entry=1))
    eng.run_once()
    assert len(broker.open_positions) == 1


def test_engine_still_exits_outside_session(tmp_path):
    strat = FakeStrategy(entry=1)
    cfg = cfg_with(["09:00-13:00"])
    eng, broker = engine_for(tmp_path, cfg, strat)
    eng.run_once()
    assert len(broker.open_positions) == 1
    cfg.symbols[0].sessions = ["13:00-15:00"]  # 이제 시간대 밖
    strat.entry, strat.exit_long = -1, True
    broker.rates["US100"] = make_bars(101)
    eng.run_once()
    assert broker.open_positions == []  # 청산은 되고, 반대 방향 신규 진입은 막힘


def test_engine_named_timezone(tmp_path, monkeypatch):
    import bot.engine as engine_mod

    class FixedDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 1, 5, 22, 30, tzinfo=tz)

    monkeypatch.setattr(engine_mod, "datetime", FixedDT)
    eng, broker = engine_for(tmp_path, cfg_with(["22:00-23:00"], tz="Asia/Seoul"), FakeStrategy(entry=1))
    eng.run_once()
    assert len(broker.open_positions) == 1  # 서버 시간(12:00)이 아니라 지정 시간대(22:30) 기준


def test_backtest_respects_sessions():
    # 15분봉 00:00 시작. 봉 i 는 (i+1)*15분에 완성 → 봉1 완성 00:30, 봉5 완성 01:30
    df = frame(np.arange(100.0, 112.0))
    strat = ScriptedStrategy(entries={1: 1, 5: 1}, exits_long={3, 8})
    sc = cfg_with(["01:00-02:00"]).symbols[0]
    res = run_backtest(df, sc, {"s": strat}, sl_atr_mult=50)
    assert len(res.trades) == 1
    assert res.trades.iloc[0]["entry_time"] == df.index[6]  # 봉5 신호 → 봉6 시가 진입
    sc_all = cfg_with([]).symbols[0]
    assert len(run_backtest(df, sc_all, {"s": strat}, sl_atr_mult=50).trades) == 2
