from pathlib import Path

import pytest

from bot.config import LIVE_CONFIRM_PHRASE, ConfigError, config_from_dict, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_example_config_loads():
    cfg = load_config(ROOT / "config.example.yaml")
    assert cfg.dry_run is True
    assert [s.key for s in cfg.symbols] == ["NASDAQ", "GOLD"]
    assert cfg.params_for(cfg.symbols[0], "trend")["fast"] == 20


def base(**mode):
    return {"mode": mode, "symbols": [{"key": "A", "symbol": "US100", "lot": 0.1}]}


def test_live_requires_confirmation():
    with pytest.raises(ConfigError):
        config_from_dict(base(dry_run=False))
    cfg = config_from_dict(base(dry_run=False, live_confirm=LIVE_CONFIRM_PHRASE))
    assert cfg.dry_run is False


@pytest.mark.parametrize("sym", [
    {"key": "A", "type": "cfd", "lot": 1},  # symbol 없음
    {"key": "A", "type": "futures", "lot": 1},  # root 없음
    {"key": "A", "symbol": "X", "timeframe": "H1", "htf_timeframe": "M15"},
    {"key": "A", "symbol": "X", "strategies": ["nope"]},
    {"key": "A", "symbol": "X", "params": {"trend": {"fast": 60}}},  # fast >= slow
])
def test_invalid_symbol_configs(sym):
    with pytest.raises(ConfigError):
        config_from_dict({"symbols": [sym]})


def test_per_symbol_params_override():
    cfg = config_from_dict({
        "strategy_params": {"trend": {"adx_min": 20}},
        "symbols": [{"key": "A", "symbol": "X", "params": {"trend": {"adx_min": 30}}}],
    })
    assert cfg.params_for(cfg.symbols[0], "trend") == {"adx_min": 30}
