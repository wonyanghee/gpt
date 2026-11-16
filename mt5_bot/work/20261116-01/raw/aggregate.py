"""수집 항목 1,2,3,5 집계 (읽기 전용). 사용: python aggregate.py demo_trades.csv"""
import csv, sys
from collections import Counter, defaultdict
from decimal import Decimal

path = sys.argv[1]
with open(path, encoding="utf-8-sig", newline="") as f:
    r = csv.DictReader(f)
    cols = r.fieldnames
    rows = list(r)
print("file:", path)
print("columns:", cols)
print("data rows:", len(rows))
print("action counts:", dict(Counter(x["action"] for x in rows)))
print("mode counts:", dict(Counter(x["mode"] for x in rows)))
print("symbol x action:", dict(sorted(Counter((x["symbol"], x["action"]) for x in rows).items())))
print("empty profit by action:", dict(Counter(x["action"] for x in rows if x["profit"] == "")))
print("nonempty profit by action:", dict(Counter(x["action"] for x in rows if x["profit"] != "")))
for c in cols:
    n = sum(1 for x in rows if x[c] == "")
    if n: print(f"empty cells in {c}: {n}")
ex = [x for x in rows if x["action"] in ("close", "stop")]
print("--- item 2: by symbol (action in close/stop)")
for s in sorted({x["symbol"] for x in ex}):
    e = [x for x in ex if x["symbol"] == s]
    p = [Decimal(x["profit"]) for x in e]
    print(s, "rows", len(e), "profit>0", sum(1 for v in p if v > 0), "profit==0", sum(1 for v in p if v == 0),
          "profit<0", sum(1 for v in p if v < 0), "profit sum", sum(p))
p = [Decimal(x["profit"]) for x in ex]
print("ALL rows", len(ex), "profit>0", sum(1 for v in p if v > 0), "profit sum", sum(p))
print("--- item 3: by action")
for a in ("close", "stop"):
    e = [Decimal(x["profit"]) for x in ex if x["action"] == a]
    print(a, "rows", len(e), "profit sum", sum(e))
print("--- item 5: time")
t = [x["time"] for x in rows]
print("min", min(t), "max", max(t), "distinct", len(set(t)))
print("distinct time values:", dict(sorted(Counter(t).items())))
print("first row:", rows[0])
print("last row:", rows[-1])
