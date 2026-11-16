"""백테스트 실행.

    # CSV 파일로 (MT5 '봉 내보내기' CSV 그대로 사용 가능)
    python run_backtest.py --config config.yaml --symbol NASDAQ --csv data/US100_M15.csv

    # MT5 에서 직접 과거 봉을 받아서 (Windows) - 받은 데이터는 data/ 에 CSV 로 저장
    python run_backtest.py --config config.yaml --symbol GOLD --from-mt5 --bars 50000

    # 전략 하나씩 비교
    python run_backtest.py --config config.yaml --symbol GOLD --csv gold.csv --strategies trend
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bot.backtest import load_csv, run_backtest
from bot.config import ConfigError, load_config
from bot.strategies import make_strategy


def main() -> int:
    ap = argparse.ArgumentParser(description="MT5 봇 백테스트")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--symbol", required=True, help="config 의 symbols[].key (예: NASDAQ, GOLD)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="과거 봉 CSV 경로")
    src.add_argument("--from-mt5", action="store_true", help="MT5 에서 과거 봉 다운로드")
    ap.add_argument("--bars", type=int, default=50000, help="--from-mt5 사용 시 봉 개수")
    ap.add_argument("--strategies", help="쉼표로 구분 (기본: config 의 strategies)")
    ap.add_argument("--out", default="backtest_results")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
        sc = cfg.symbol(args.symbol)
    except ConfigError as exc:
        print(f"설정 오류: {exc}")
        return 2

    if args.csv:
        df = load_csv(args.csv)
        symbol = sc.symbol or sc.root
    else:
        from bot.broker import MT5Broker

        broker = MT5Broker(cfg.terminal_path)
        broker.connect()
        try:
            symbol = broker.resolve_symbol(sc)
            df = broker.get_rates(symbol, sc.timeframe, args.bars)
        finally:
            broker.shutdown()
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        csv_path = data_dir / f"{symbol}_{sc.timeframe}.csv"
        df.to_csv(csv_path)
        print(f"MT5 데이터 저장: {csv_path}")

    names = args.strategies.split(",") if args.strategies else sc.strategies
    strategies = {n.strip(): make_strategy(n.strip(), cfg.params_for(sc, n.strip())) for n in names}

    print(f"[{sc.key}] {symbol} {sc.timeframe} {df.index[0]} ~ {df.index[-1]} ({len(df):,}봉)")
    print(f"전략: {list(strategies)} / 랏 {sc.lot} / 비상손절 ATR x {cfg.risk.sl_atr_mult}")
    result = run_backtest(df, sc, strategies, cfg.risk.sl_atr_mult, cfg.backtest_initial_balance)
    print(json.dumps(result.stats, ensure_ascii=False, indent=2))

    prefix = f"{sc.key}_{'+'.join(strategies)}"
    result.save(Path(args.out), prefix)
    print(f"결과 저장: {args.out}/{prefix}_trades.csv, {prefix}_equity.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
