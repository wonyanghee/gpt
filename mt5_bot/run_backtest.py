"""백테스트 실행.

    # CSV 파일로 (MT5 '봉 내보내기' CSV 그대로 사용 가능)
    python run_backtest.py --config config.yaml --symbol NASDAQ --csv data/US100_M15.csv

    # MT5 에서 직접 과거 봉을 받아서 (Windows) - 받은 데이터는 data/ 에 CSV 로 저장
    python run_backtest.py --config config.yaml --symbol GOLD --from-mt5 --bars 50000

    # 기간을 나눠 탐색/검증 (과최적화 방지)
    python run_backtest.py --symbol GOLD --csv gold.csv --end 2025-09-01     # 탐색 구간
    python run_backtest.py --symbol GOLD --csv gold.csv --start 2025-09-01   # 검증 구간

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
    ap.add_argument("--start", help="이 날짜부터 (예: 2025-01-01). 탐색/검증 구간을 나눌 때 사용")
    ap.add_argument("--end", help="이 날짜 전까지 (예: 2025-09-01, 해당 날짜는 제외)")
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

    if args.start:
        df = df[df.index >= args.start]
    if args.end:
        df = df[df.index < args.end]
    if len(df) < 500:
        print(f"봉이 너무 적습니다({len(df)}개). --start/--end 또는 데이터를 확인하세요")
        return 2

    names = args.strategies.split(",") if args.strategies else sc.strategies
    strategies = {n.strip(): make_strategy(n.strip(), cfg.params_for(sc, n.strip())) for n in names}

    print(f"[{sc.key}] {symbol} {sc.timeframe} {df.index[0]} ~ {df.index[-1]} ({len(df):,}봉)")
    sizing_desc = (
        f"잔고의 {cfg.risk.risk_per_trade_pct}% 위험" if cfg.risk.sizing == "risk_pct" else f"고정 {sc.lot}랏"
    )
    print(f"전략: {list(strategies)} / 수량 {sizing_desc} / 비상손절 ATR x {cfg.risk.sl_atr_mult}")
    if sc.sessions:
        if sc.session_timezone == "server":
            print(f"매매 시간대(서버 시간): {sc.sessions}")
        else:
            print(f"주의: session_timezone={sc.session_timezone} 는 백테스트에 반영되지 않습니다 "
                  "(server 시간대만 반영). 결과가 라이브와 다를 수 있습니다.")
    result = run_backtest(
        df, sc, strategies, cfg.risk.sl_atr_mult, cfg.backtest_initial_balance,
        sizing=cfg.risk.sizing, risk_per_trade_pct=cfg.risk.risk_per_trade_pct,
    )
    print(json.dumps(result.stats, ensure_ascii=False, indent=2))

    prefix = f"{sc.key}_{'+'.join(strategies)}"
    if args.start or args.end:
        prefix += f"_{args.start or ''}~{args.end or ''}"
    result.save(Path(args.out), prefix)
    print(f"결과 저장: {args.out}/{prefix}_trades.csv, {prefix}_equity.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
