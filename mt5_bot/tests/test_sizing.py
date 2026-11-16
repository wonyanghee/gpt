import numpy as np
import pytest

from bot.backtest import run_backtest
from bot.broker import Position
from bot.config import ConfigError, config_from_dict
from bot.engine import Engine
from bot.notify import TradeLog
from bot.sizing import floor_to_step, risk_based_volume
from fakes import FakeBroker, FakeStrategy, RecordingNotifier
from test_backtest import ScriptedStrategy, frame


def test_risk_based_volume_basic():
    # 잔고 10000, 1% = 100. 1랏 손절손실 600 → 0.1666 → 0.16
    assert risk_based_volume(10000, 1.0, 600, 0.01, 0.01) == pytest.approx(0.16)
    assert risk_based_volume(10000, 1.0, 600, 0.1, 0.1) == pytest.approx(0.1)
    assert risk_based_volume(10000, 1.0, 600, 1, 1) == 0.0  # 최소 1계약도 위험 초과 → 진입 안 함
    assert risk_based_volume(10000, 2.0, 100, 0.01, 0.01, max_lot=0.5) == pytest.approx(0.5)
    assert risk_based_volume(10000, 2.0, 100, 0.01, 0.01, volume_max=1.0) == pytest.approx(1.0)
    assert risk_based_volume(0, 1.0, 600, 0.01, 0.01) == 0.0
    assert risk_based_volume(10000, 1.0, 0, 0.01, 0.01) == 0.0


def test_floor_to_step_never_rounds_up():
    assert floor_to_step(0.169, 0.01) == pytest.approx(0.16)
    assert floor_to_step(0.3, 0.1) == pytest.approx(0.3)  # 부동소수 오차로 0.2 가 되면 안 됨
    assert floor_to_step(2.9, 1) == 2


def make_cfg(sizing="risk_pct", pct=1.0, **sym):
    symbol = {"key": "NASDAQ", "symbol": "US100", "lot": 0.1, "htf_timeframe": None,
              "strategies": ["trend"], **sym}
    return config_from_dict({"symbols": [symbol],
                             "risk": {"sizing": sizing, "risk_per_trade_pct": pct, "sl_atr_mult": 3.0}})


def engine_for(tmp_path, cfg, strat, broker=None):
    broker = broker or FakeBroker()
    if not broker.rates:
        broker.set_symbol("US100")  # bid 100.0 / ask 100.2, calc_profit = 가격차 x 수량 x 100
    notifier = RecordingNotifier()
    eng = Engine(cfg, broker, notifier, TradeLog(tmp_path / "t.csv", "TEST"),
                 strategies={"NASDAQ": {"trend": strat}})
    return eng, broker, notifier


def test_engine_sizes_by_risk(tmp_path):
    eng, broker, _ = engine_for(tmp_path, make_cfg(), FakeStrategy(entry=1, atr=2.0))
    eng.run_once()
    p = broker.open_positions[0]
    assert p.volume == pytest.approx(0.16)  # SL 거리 6 x 100 = 600/랏, 위험 100
    # 실제 손절 시 손실이 한도 이하
    assert abs(broker.calc_profit("US100", 1, p.volume, p.price_open, p.sl)) <= 100 + 1e-9


def test_engine_risk_scales_with_balance_and_stop(tmp_path):
    broker = FakeBroker()
    broker.set_symbol("US100")
    broker.start_balance = 20000.0
    eng, broker, _ = engine_for(tmp_path, make_cfg(pct=0.5), FakeStrategy(entry=-1, atr=1.0), broker)
    eng.run_once()
    assert broker.open_positions[0].volume == pytest.approx(0.33)  # 100 / 300 = 0.333 → 0.33


def test_engine_respects_max_lot(tmp_path):
    eng, broker, _ = engine_for(tmp_path, make_cfg(pct=5.0, max_lot=0.2), FakeStrategy(entry=1, atr=2.0))
    eng.run_once()
    assert broker.open_positions[0].volume == pytest.approx(0.2)


def test_engine_skips_when_min_volume_too_risky(tmp_path):
    broker = FakeBroker()
    broker.set_symbol("US100")
    broker.vol_limits = (1.0, 1.0, 100.0)
    eng, broker, notifier = engine_for(tmp_path, make_cfg(), FakeStrategy(entry=1, atr=2.0), broker)
    eng.run_once()
    assert broker.open_positions == [] and broker.orders == []
    assert any("진입 보류" in m and "위험 한도" in m for m in notifier.messages)


def test_fixed_mode_unchanged(tmp_path):
    eng, broker, _ = engine_for(tmp_path, make_cfg(sizing="fixed"), FakeStrategy(entry=1, atr=2.0))
    eng.run_once()
    assert broker.open_positions[0].volume == 0.1


def test_rollover_keeps_existing_volume(tmp_path):
    cfg = make_cfg(type="futures", symbol=None, root="MNQ", lot=1)
    broker = FakeBroker()
    broker.set_symbol("MNQH27")
    broker.set_symbol("MNQZ26")
    broker.active["NASDAQ"] = "MNQH27"
    broker.open_positions.append(Position(1, "MNQZ26", 1, 3.0, 150.0, 140.0, 0.0, "trend"))
    eng, broker, _ = engine_for(tmp_path, cfg, FakeStrategy(entry=0), broker)
    eng.run_once()
    assert broker.open_positions[0].symbol == "MNQH27" and broker.open_positions[0].volume == 3.0


def test_config_validation():
    with pytest.raises(ConfigError):
        make_cfg(sizing="kelly")
    with pytest.raises(ConfigError):
        make_cfg(pct=0)
    with pytest.raises(ConfigError):
        make_cfg(pct=25)


def bt_symbol(**bt):
    return config_from_dict({"symbols": [{
        "key": "T", "symbol": "T", "lot": 1, "htf_timeframe": None, "strategies": ["trend"],
        "backtest": {"contract_size": 10, **bt},
    }]}).symbols[0]


def test_backtest_risk_sizing_and_compounding():
    # 거래1: 봉1 시가 100 진입, SL 거리 2(ATR1 x 2) → 1랏 손실 20 → 10000x1%/20 = 5랏. 손절로 -100
    # 거래2: 잔고 9900 → 99/20 = 4.95랏
    opens = [100, 100, 100, 100, 100, 100, 100]
    lows = [100, 100, 97, 100, 100, 100, 100]
    df = frame(opens, lows=lows)
    strat = ScriptedStrategy(entries={0: 1, 3: 1}, atr=1.0)
    res = run_backtest(df, bt_symbol(), {"s": strat}, sl_atr_mult=2,
                       initial_balance=10000, sizing="risk_pct", risk_per_trade_pct=1.0)
    tr = res.trades
    assert tr.iloc[0]["volume"] == pytest.approx(5.0)
    assert tr.iloc[0]["pnl"] == pytest.approx(-100.0)  # 정확히 잔고의 1%
    assert tr.iloc[1]["volume"] == pytest.approx(4.95)
    assert res.stats["평균수량"] == pytest.approx(4.975, abs=1e-3)


def test_backtest_skips_entry_below_min_volume():
    df = frame([100, 100, 100, 100])
    strat = ScriptedStrategy(entries={0: 1}, atr=100.0)  # 손절 거리 매우 큼
    res = run_backtest(df, bt_symbol(volume_min=1, volume_step=1), {"s": strat}, sl_atr_mult=3,
                       initial_balance=10000, sizing="risk_pct", risk_per_trade_pct=1.0)
    assert res.stats == {"거래수": 0, "수량부족 진입포기": 1}


def test_backtest_fixed_matches_previous_behaviour():
    df = frame([100, 101, 102, 103, 104, 105])
    strat = ScriptedStrategy(entries={1: 1}, exits_long={3})
    res = run_backtest(df, bt_symbol(), {"s": strat}, sl_atr_mult=3)
    assert res.trades.iloc[0]["volume"] == 1 and res.trades.iloc[0]["pnl"] == pytest.approx(20)
