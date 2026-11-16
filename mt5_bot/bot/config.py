"""설정 파일(YAML) 로딩과 검증."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .indicators import TIMEFRAME_MINUTES
from .sessions import parse_sessions
from .strategies import STRATEGIES

LIVE_CONFIRM_PHRASE = "I_UNDERSTAND_THE_RISK"


class ConfigError(ValueError):
    pass


@dataclass
class BacktestSymbolConfig:
    contract_size: float = 1.0  # 가격 1 변동 시 1랏(1계약) 손익
    spread: float = 0.0  # 가격 단위 스프레드
    commission_per_lot: float = 0.0  # 왕복 수수료 (1랏당)
    volume_min: float = 0.01  # 최소 주문 수량 (risk_pct 수량 계산용)
    volume_step: float = 0.01  # 수량 단위


@dataclass
class SymbolConfig:
    key: str
    type: str = "cfd"  # cfd | futures
    symbol: str | None = None  # CFD 종목명, 선물이면 특정 월물 고정 시 사용
    root: str | None = None  # 선물 루트 (예: MNQ, MGC)
    timeframe: str = "M15"
    htf_timeframe: str | None = "H1"
    lot: float = 0.01  # sizing=fixed 일 때 주문 수량
    max_lot: float = 0.0  # sizing=risk_pct 일 때 수량 상한 (0 = 상한 없음)
    max_spread_points: float = 0.0  # 0 이면 스프레드 필터 끔
    sessions: list[str] = field(default_factory=list)  # 신규 진입 허용 시간대, 비우면 제한 없음
    session_timezone: str = "server"  # server(브로커 서버 시간) 또는 IANA 시간대 (예: Asia/Seoul)
    strategies: list[str] = field(default_factory=lambda: ["trend"])
    params: dict = field(default_factory=dict)
    roll_days_before_expiry: int = 5
    roll_reopen: bool = True
    history_bars: int = 600
    htf_history_bars: int = 500
    backtest: BacktestSymbolConfig = field(default_factory=BacktestSymbolConfig)

    @property
    def is_futures(self) -> bool:
        return self.type == "futures"

    @property
    def session_windows(self) -> list[tuple[int, int]]:
        return parse_sessions(self.sessions)

    def owns_symbol(self, name: str, active_symbol: str) -> bool:
        """이 설정이 관리하는 포지션인지 (선물은 이전 월물 포함)."""
        if name == active_symbol:
            return True
        return bool(self.is_futures and self.root and name.startswith(self.root))


@dataclass
class RiskConfig:
    daily_max_loss_pct: float = 3.0  # 0 이면 끔
    close_all_on_daily_limit: bool = False
    sl_atr_mult: float = 3.0  # 비상 손절 = ATR x 배수
    sl_atr_period: int = 14  # 롤오버 재진입 시 손절 계산용
    sizing: str = "fixed"  # fixed(고정 랏) | risk_pct(계좌 위험 % 기준)
    risk_per_trade_pct: float = 1.0  # risk_pct: 비상손절 시 잃을 잔고 비율(%)


@dataclass
class BotConfig:
    symbols: list[SymbolConfig]
    dry_run: bool = True
    poll_seconds: float = 10.0
    magic: int = 240001
    terminal_path: str = ""
    risk: RiskConfig = field(default_factory=RiskConfig)
    telegram_enabled: bool = False
    log_dir: Path = Path("logs")
    dry_run_state_file: Path = Path("logs/dry_run_state.json")
    dry_run_balance: float | None = None
    backtest_initial_balance: float = 10000.0
    strategy_params: dict = field(default_factory=dict)

    def params_for(self, sc: SymbolConfig, strategy_name: str) -> dict:
        return {**self.strategy_params.get(strategy_name, {}), **sc.params.get(strategy_name, {})}

    def symbol(self, key: str) -> SymbolConfig:
        for sc in self.symbols:
            if sc.key == key:
                return sc
        raise ConfigError(f"설정에 없는 종목 key: {key} (있는 key: {[s.key for s in self.symbols]})")


def _symbol_from_dict(d: dict) -> SymbolConfig:
    d = dict(d)
    if "key" not in d:
        raise ConfigError("symbols 항목마다 key 가 필요합니다")
    bt = BacktestSymbolConfig(**(d.pop("backtest", None) or {}))
    try:
        sc = SymbolConfig(**d, backtest=bt)
    except TypeError as exc:
        raise ConfigError(f"symbols[{d.get('key')}] 설정 오류: {exc}") from exc

    if sc.type not in ("cfd", "futures"):
        raise ConfigError(f"[{sc.key}] type 은 cfd 또는 futures 여야 합니다")
    if sc.type == "cfd" and not sc.symbol:
        raise ConfigError(f"[{sc.key}] CFD 는 symbol 이 필요합니다")
    if sc.type == "futures" and not (sc.root or sc.symbol):
        raise ConfigError(f"[{sc.key}] 선물은 root(또는 고정 symbol)가 필요합니다")
    for tf in (sc.timeframe, sc.htf_timeframe):
        if tf is not None and tf not in TIMEFRAME_MINUTES:
            raise ConfigError(f"[{sc.key}] 지원하지 않는 시간봉: {tf}")
    if sc.htf_timeframe and TIMEFRAME_MINUTES[sc.htf_timeframe] <= TIMEFRAME_MINUTES[sc.timeframe]:
        raise ConfigError(f"[{sc.key}] htf_timeframe 은 timeframe 보다 커야 합니다")
    if not sc.strategies:
        raise ConfigError(f"[{sc.key}] strategies 가 비어 있습니다")
    for name in sc.strategies:
        if name not in STRATEGIES:
            raise ConfigError(f"[{sc.key}] 알 수 없는 전략: {name}")
    if isinstance(sc.sessions, str):
        sc.sessions = [sc.sessions]
    try:
        parse_sessions(sc.sessions)
    except ValueError as exc:
        raise ConfigError(f"[{sc.key}] sessions {exc}") from exc
    if sc.session_timezone != "server":
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(sc.session_timezone)
        except Exception as exc:
            raise ConfigError(
                f"[{sc.key}] session_timezone 을 찾을 수 없습니다: {sc.session_timezone} "
                "(예: Asia/Seoul, America/New_York. Windows 는 `pip install tzdata` 필요)"
            ) from exc
    if sc.lot <= 0:
        raise ConfigError(f"[{sc.key}] lot 은 0보다 커야 합니다")
    if sc.max_lot < 0:
        raise ConfigError(f"[{sc.key}] max_lot 은 0 이상이어야 합니다")
    if bt.volume_step <= 0 or bt.volume_min <= 0:
        raise ConfigError(f"[{sc.key}] backtest.volume_min/volume_step 은 0보다 커야 합니다")
    return sc


def config_from_dict(raw: dict, base_dir: Path | None = None) -> BotConfig:
    base_dir = base_dir or Path.cwd()
    mode = raw.get("mode", {}) or {}
    dry_run = bool(mode.get("dry_run", True))
    if not dry_run and mode.get("live_confirm") != LIVE_CONFIRM_PHRASE:
        raise ConfigError(
            "실거래(dry_run: false)를 쓰려면 mode.live_confirm 에 "
            f'"{LIVE_CONFIRM_PHRASE}" 를 입력해야 합니다'
        )

    symbols = [_symbol_from_dict(s) for s in raw.get("symbols", []) or []]
    if not symbols:
        raise ConfigError("symbols 가 비어 있습니다")
    keys = [s.key for s in symbols]
    if len(keys) != len(set(keys)):
        raise ConfigError("symbols 의 key 가 중복됩니다")

    logging_cfg = raw.get("logging", {}) or {}
    log_dir = base_dir / logging_cfg.get("dir", "logs")
    state_file = logging_cfg.get("dry_run_state_file")
    state_path = base_dir / state_file if state_file else log_dir / "dry_run_state.json"

    try:
        risk = RiskConfig(**(raw.get("risk", {}) or {}))
    except TypeError as exc:
        raise ConfigError(f"risk 설정 오류: {exc}") from exc

    if risk.sizing not in ("fixed", "risk_pct"):
        raise ConfigError("risk.sizing 은 fixed 또는 risk_pct 여야 합니다")
    if not 0 < risk.risk_per_trade_pct <= 10:
        raise ConfigError("risk.risk_per_trade_pct 는 0 초과 10 이하여야 합니다 (보통 0.5~2)")
    if risk.sl_atr_mult <= 0:
        raise ConfigError("risk.sl_atr_mult 는 0보다 커야 합니다")

    strategy_params = raw.get("strategy_params", {}) or {}
    for name in strategy_params:
        if name not in STRATEGIES:
            raise ConfigError(f"strategy_params 에 알 수 없는 전략: {name}")

    cfg = BotConfig(
        symbols=symbols,
        dry_run=dry_run,
        poll_seconds=float(raw.get("poll_seconds", 10)),
        magic=int(raw.get("magic", 240001)),
        terminal_path=(raw.get("mt5", {}) or {}).get("terminal_path", "") or "",
        risk=risk,
        telegram_enabled=bool((raw.get("telegram", {}) or {}).get("enabled", False)),
        log_dir=log_dir,
        dry_run_state_file=state_path,
        dry_run_balance=mode.get("dry_run_balance"),
        backtest_initial_balance=float((raw.get("backtest", {}) or {}).get("initial_balance", 10000)),
        strategy_params=strategy_params,
    )
    # 전략 파라미터 오류를 시작 시점에 잡는다
    from .strategies import make_strategy

    for sc in cfg.symbols:
        for name in sc.strategies:
            try:
                make_strategy(name, cfg.params_for(sc, name))
            except ValueError as exc:
                raise ConfigError(f"[{sc.key}] {exc}") from exc
    return cfg


def load_config(path: str | Path) -> BotConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"설정 파일이 없습니다: {path} (config.example.yaml 을 복사해 만드세요)")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return config_from_dict(raw, base_dir=path.resolve().parent)
