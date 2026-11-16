"""라이브(기본: 드라이런) 봇 실행.

    python run_bot.py --config config.yaml          # 계속 실행
    python run_bot.py --config config.yaml --once   # 한 사이클만 실행 (점검용)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

from bot.broker import DryRunBroker, MT5Broker
from bot.config import ConfigError, load_config
from bot.engine import Engine
from bot.notify import TelegramNotifier, TradeLog


def setup_logging(log_dir) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)


def main() -> int:
    ap = argparse.ArgumentParser(description="MT5 나스닥/금 자동매매 봇")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--once", action="store_true", help="한 사이클만 실행")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}")
        return 2

    setup_logging(cfg.log_dir)
    log = logging.getLogger("run_bot")
    mode = "DRY-RUN" if cfg.dry_run else "LIVE"
    notifier = TelegramNotifier.from_env(cfg.telegram_enabled, prefix=f"[MT5봇 {mode}]")

    market = MT5Broker(
        terminal_path=cfg.terminal_path,
        login=os.environ.get("MT5_LOGIN"),
        password=os.environ.get("MT5_PASSWORD"),
        server=os.environ.get("MT5_SERVER"),
    )
    broker = DryRunBroker(market, cfg.dry_run_state_file, cfg.dry_run_balance) if cfg.dry_run else market
    broker.connect()

    acct = broker.account_summary()
    log.info("계좌: %s", acct)
    if not cfg.dry_run and acct.get("trade_mode") == "real":
        log.warning("!!! 실계좌(real)에 실주문을 냅니다 !!!")
    notifier.send(
        f"시작 ({mode}) 계좌 {acct.get('login')}@{acct.get('server')} [{acct.get('trade_mode')}] "
        f"잔고 {acct.get('balance')} {acct.get('currency')} / 종목 {[s.key for s in cfg.symbols]}"
    )

    engine = Engine(cfg, broker, notifier, TradeLog(cfg.log_dir / "trades.csv", mode))
    try:
        while True:
            try:
                market.ensure_connected()
                engine.run_once()
            except Exception as exc:
                log.exception("사이클 오류")
                notifier.send(f"사이클 오류: {exc}", dedupe=True)
            if args.once:
                break
            time.sleep(cfg.poll_seconds)
    except KeyboardInterrupt:
        log.info("사용자 중지")
    finally:
        notifier.send(f"종료 ({mode})")
        broker.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
