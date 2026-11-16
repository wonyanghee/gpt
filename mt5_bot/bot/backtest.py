"""백테스트: 라이브와 같은 전략 코드를 과거 봉 데이터에 적용한다.

체결 가정
- 봉 데이터는 Bid 가격 기준. 매수 진입/매도 청산은 Ask(= Bid + spread)로 체결.
- 신호는 봉 종가에서 판단하고 '다음 봉 시가'에 체결.
- 비상 손절(ATR x sl_atr_mult)은 봉 내부 고가/저가로 체크하고, 시가 갭이면 시가로 체결.
- 같은 봉에서 청산 후 반대 방향 진입 허용 (라이브와 동일).
- 일일 손실 한도/스프레드 필터는 반영하지 않는다(고정 스프레드 사용).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import SymbolConfig
from .indicators import resample_ohlc
from .strategies import Strategy


@dataclass
class Trade:
    strategy: str
    direction: int
    entry_time: pd.Timestamp
    entry_price: float
    sl: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    reason: str = ""
    pnl: float = 0.0


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    equity: pd.Series
    stats: dict

    def save(self, out_dir: Path, prefix: str) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.trades.to_csv(out_dir / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")
        self.equity.to_csv(out_dir / f"{prefix}_equity.csv", header=["equity"], encoding="utf-8-sig")


def load_csv(path: str | Path) -> pd.DataFrame:
    """일반 CSV(time,open,high,low,close[,tick_volume]) 또는 MT5 '봉 내보내기' CSV 를 읽는다."""
    path = Path(path)
    sep = "\t" if path.read_text(encoding="utf-8-sig", errors="ignore")[:500].count("\t") > 2 else ","
    df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]
    if "date" in df.columns and "time" in df.columns:
        df["time"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    elif "date" in df.columns:
        df["time"] = pd.to_datetime(df["date"])
    else:
        raise ValueError("CSV 에 time(또는 date) 컬럼이 필요합니다")
    df = df.rename(columns={"tickvol": "tick_volume", "vol": "volume"})
    if "tick_volume" not in df.columns and "volume" in df.columns:
        df["tick_volume"] = df["volume"]
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"CSV 에 필요한 컬럼이 없습니다: {sorted(missing)}")
    cols = ["open", "high", "low", "close"] + (["tick_volume"] if "tick_volume" in df.columns else [])
    df = df.set_index("time")[cols].astype(float).sort_index()
    return df[~df.index.duplicated(keep="last")]


def run_backtest(
    df: pd.DataFrame,
    sc: SymbolConfig,
    strategies: dict[str, Strategy],
    sl_atr_mult: float,
    initial_balance: float = 10000.0,
) -> BacktestResult:
    if not strategies:
        raise ValueError("전략이 없습니다")
    htf = resample_ohlc(df, sc.htf_timeframe) if sc.htf_timeframe else None
    order = list(strategies)
    sigs = {n: strategies[n].compute(df, htf, sc.timeframe, sc.htf_timeframe) for n in order}
    entry = {n: sigs[n]["entry"].to_numpy() for n in order}
    exit_l = {n: sigs[n]["exit_long"].to_numpy() for n in order}
    exit_s = {n: sigs[n]["exit_short"].to_numpy() for n in order}
    atr_ = {n: sigs[n]["atr"].to_numpy() for n in order}
    warmup = max(s.warmup_bars() for s in strategies.values())

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()  # noqa: E741
    c = df["close"].to_numpy()
    t = df.index
    spread = sc.backtest.spread
    size = sc.lot * sc.backtest.contract_size
    commission = sc.backtest.commission_per_lot * sc.lot

    trades: list[Trade] = []
    pos: Trade | None = None
    pending_exit = False
    pending_entry: tuple[int, str, float] | None = None

    def close(trade: Trade, i: int, price: float, reason: str) -> None:
        trade.exit_time = t[i]
        trade.exit_price = price
        trade.reason = reason
        trade.pnl = (price - trade.entry_price) * trade.direction * size - commission
        trades.append(trade)

    for i in range(len(df)):
        # 1) 직전 봉에서 예약된 주문을 이번 봉 시가에 체결
        if pending_exit and pos is not None:
            close(pos, i, o[i] if pos.direction > 0 else o[i] + spread, "반대 신호")
            pos = None
        if pending_entry is not None and pos is None:
            d, name, a = pending_entry
            price = o[i] + spread if d > 0 else o[i]
            pos = Trade(name, d, t[i], price, price - d * a * sl_atr_mult)
        pending_exit = False
        pending_entry = None

        # 2) 봉 내부 비상 손절
        if pos is not None:
            if pos.direction > 0 and l[i] <= pos.sl:
                close(pos, i, min(o[i], pos.sl), "비상손절")
                pos = None
            elif pos.direction < 0 and h[i] + spread >= pos.sl:
                close(pos, i, max(o[i] + spread, pos.sl), "비상손절")
                pos = None

        if i < warmup or i == len(df) - 1:
            continue

        # 3) 종가 기준 신호 판단 → 다음 봉에 체결
        if pos is not None:
            n = pos.strategy
            if (pos.direction > 0 and exit_l[n][i]) or (pos.direction < 0 and exit_s[n][i]):
                pending_exit = True
        if pos is None or pending_exit:
            for n in order:
                d = int(entry[n][i])
                if d != 0 and not np.isnan(atr_[n][i]):
                    pending_entry = (d, n, float(atr_[n][i]))
                    break

    if pos is not None:
        last = len(df) - 1
        close(pos, last, c[last] if pos.direction > 0 else c[last] + spread, "기간 종료")

    trades_df = pd.DataFrame([asdict(tr) for tr in trades])
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=list(Trade.__dataclass_fields__))
        equity = pd.Series([initial_balance], index=[t[0]] if len(t) else [0])
    else:
        equity = pd.Series(
            initial_balance + trades_df["pnl"].cumsum().to_numpy(), index=trades_df["exit_time"]
        )
    return BacktestResult(trades_df, equity, compute_stats(trades_df, equity, initial_balance))


def compute_stats(trades: pd.DataFrame, equity: pd.Series, initial_balance: float) -> dict:
    if trades.empty:
        return {"거래수": 0}
    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    curve = pd.concat([pd.Series([initial_balance]), pd.Series(equity.to_numpy())], ignore_index=True)
    peak = curve.cummax()
    dd = curve - peak
    max_dd = float(dd.min())
    max_dd_pct = float((dd / peak).min() * 100)
    stats = {
        "거래수": int(len(pnl)),
        "승률(%)": round(len(wins) / len(pnl) * 100, 1),
        "순손익": round(float(pnl.sum()), 2),
        "수익률(%)": round(float(pnl.sum()) / initial_balance * 100, 2),
        "Profit Factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else float("inf"),
        "평균수익": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "평균손실": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "최대낙폭": round(max_dd, 2),
        "최대낙폭(%)": round(max_dd_pct, 2),
        "비상손절 횟수": int((trades["reason"] == "비상손절").sum()),
    }
    by_strategy = {}
    for name, g in trades.groupby("strategy"):
        p = g["pnl"].astype(float)
        by_strategy[name] = {
            "거래수": int(len(p)),
            "승률(%)": round(float((p > 0).mean() * 100), 1),
            "순손익": round(float(p.sum()), 2),
        }
    stats["전략별"] = by_strategy
    return stats
