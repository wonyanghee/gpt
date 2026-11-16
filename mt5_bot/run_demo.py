"""MT5 없이 봇을 돌려보는 데모 (가상 시세 + 실제 매매 엔진).

    python run_demo.py                       # 가상 시세 20거래일을 빠르게 재생
    python run_demo.py --speed 0.05          # 봉 하나당 0.05초씩 천천히 (실시간 느낌)
    python run_demo.py --days 40 --seed 7    # 기간/시세 바꾸기
    python run_demo.py --export demo.json    # 결과를 JSON 으로 저장 (시각화용)

주의: 시세는 무작위로 만든 가상 데이터입니다. 여기서 나온 손익은 전략 성능의 근거가 아닙니다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from pathlib import Path

import pandas as pd

from bot.config import ConfigError, load_config
from bot.engine import Engine
from bot.indicators import ema, tf_minutes
from bot.notify import Notifier, TradeLog
from bot.sim import SimBroker, SimSymbol, make_synthetic_bars

HERE = Path(__file__).resolve().parent
# 종목별 가상 시세 기본값 (시작가, 봉당 변동폭)
PRICE_PROFILE = {"NASDAQ": (21000.0, 14.0), "GOLD": (2650.0, 1.6)}
WARMUP_BARS = 2400  # 지표 계산용 과거 봉 (1시간봉 EMA200 포함)


class DemoNotifier(Notifier):
    def __init__(self, broker: SimBroker, quiet: bool = False):
        self.broker = broker
        self.quiet = quiet
        self.events: list[dict] = []

    def send(self, text: str, dedupe: bool = False) -> None:
        now = self.broker.now()
        self.events.append({"t": now.isoformat(timespec="minutes"), "text": text})
        if not self.quiet:
            print(f"{now:%m-%d %H:%M}  {text}")


def main() -> int:
    ap = argparse.ArgumentParser(description="MT5 없이 돌려보는 자동매매 데모")
    ap.add_argument("--config", default=str(HERE / "config.demo.yaml"))
    ap.add_argument("--days", type=int, default=20, help="재생할 거래일 수")
    ap.add_argument("--seed", type=int, default=42, help="가상 시세 난수 시드")
    ap.add_argument("--speed", type=float, default=0.0, help="봉 하나당 대기 시간(초)")
    ap.add_argument("--export", help="결과 JSON 저장 경로")
    ap.add_argument("--quiet", action="store_true", help="매매 로그 출력 생략")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"설정 오류: {exc}")
        return 2
    logging.basicConfig(level=logging.WARNING)

    symbols: dict[str, SimSymbol] = {}
    run_bars = 0
    for n, sc in enumerate(cfg.symbols):
        price, vol = PRICE_PROFILE.get(sc.key, (1000.0, 1.0))
        per_day = 1440 // tf_minutes(sc.timeframe)
        run_bars = args.days * per_day
        bars = make_synthetic_bars(WARMUP_BARS + run_bars, price, vol, args.seed + n, timeframe=sc.timeframe)
        symbols[sc.symbol] = SimSymbol(
            bars, sc.timeframe, sc.backtest.contract_size, sc.backtest.spread,
            volume_min=sc.backtest.volume_min, volume_step=sc.backtest.volume_step,
        )

    start_balance = cfg.backtest_initial_balance
    broker = SimBroker(symbols, balance=start_balance, start_index=WARMUP_BARS - 1)
    notifier = DemoNotifier(broker, quiet=args.quiet)
    trade_log = TradeLog(HERE / "logs" / "demo_trades.csv", "DEMO")
    if trade_log.path.exists():
        trade_log.path.unlink()
    engine = Engine(cfg, broker, notifier, trade_log)

    print(f"=== 자동매매 데모 시작: 가상 시세 {args.days}거래일, 시작 잔고 {start_balance:,.0f} ===")
    print("(가상 데이터입니다. 손익은 전략 성능의 근거가 아닙니다)\n")
    equity = []
    while True:
        engine.run_once()
        equity.append(round(broker.equity(), 2))
        if args.speed > 0:
            time.sleep(args.speed)
        if not broker.advance():
            break

    trades = broker.closed
    wins = [t for t in trades if t.pnl > 0]
    open_pos = broker.positions(0)
    print("\n=== 데모 결과 ===")
    print(f"거래수 {len(trades)}건 / 승률 {len(wins) / len(trades) * 100:.1f}%" if trades else "거래 없음")
    print(f"비상손절 {sum(t.reason == 'stop' for t in trades)}건 / 미청산 포지션 {len(open_pos)}개")
    print(f"잔고 {start_balance:,.2f} → {broker.balance:,.2f} (평가금액 {broker.equity():,.2f})")
    for sym in symbols:
        st = [t for t in trades if t.symbol == sym]
        print(f"  {sym}: {len(st)}건, 손익 {sum(t.pnl for t in st):,.2f}")
    print(f"거래 기록: {trade_log.path}")

    if args.export:
        out = {
            "meta": {"days": args.days, "seed": args.seed, "start_balance": start_balance,
                     "risk_pct": cfg.risk.risk_per_trade_pct, "sizing": cfg.risk.sizing,
                     "sl_atr_mult": cfg.risk.sl_atr_mult},
            "symbols": {}, "equity": equity, "events": notifier.events,
            "open": [
                {"symbol": p.symbol, "dir": p.direction, "vol": p.volume, "strategy": p.comment,
                 "et": broker._opened_at[p.ticket][1].isoformat(timespec="minutes"),
                 "ep": round(p.price_open, 2), "sl": round(p.sl, 2)}
                for p in open_pos
            ],
            "trades": [
                {"symbol": t.symbol, "dir": t.direction, "vol": t.volume, "strategy": t.strategy,
                 "et": t.entry_time.isoformat(timespec="minutes"), "ep": round(t.entry_price, 2),
                 "sl": round(t.sl, 2), "xt": t.exit_time.isoformat(timespec="minutes"),
                 "xp": round(t.exit_price, 2), "reason": t.reason, "pnl": round(t.pnl, 2)}
                for t in trades
            ],
        }
        for sc in cfg.symbols:
            s = symbols[sc.symbol]
            p = cfg.params_for(sc, "trend")
            fast = ema(s.bars["close"], p.get("fast", 20)).iloc[WARMUP_BARS - 1:]
            slow = ema(s.bars["close"], p.get("slow", 50)).iloc[WARMUP_BARS - 1:]
            b = s.bars.iloc[WARMUP_BARS - 1:]
            close_t = b.index + pd.Timedelta(minutes=tf_minutes(sc.timeframe))
            out["symbols"][sc.symbol] = {
                "key": sc.key,
                "t": [x.isoformat(timespec="minutes") for x in close_t],
                "o": b["open"].round(2).tolist(), "h": b["high"].round(2).tolist(),
                "l": b["low"].round(2).tolist(), "c": b["close"].round(2).tolist(),
                "fast": fast.round(2).tolist(), "slow": slow.round(2).tolist(),
            }
        Path(args.export).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"JSON 저장: {args.export}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
