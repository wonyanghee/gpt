"""정해진 검사를 한 번에 돌린다 (에이전트가 아니라 스크립트가 판정).

    python tools/check.py                         # 전체 (약 40초)
    python tools/check.py --skip-demo             # 데모 회귀 생략 (빠름)
    python tools/check.py --out work/<작업>/20-check.md

검사 항목
1. pytest 전체 통과
2. 데모 회귀: 기본 시드 결과가 기준값(tools/baseline.json)과 같은가
3. 안전장치: 예시·데모 설정이 드라이런인가, 확인 문구 없는 실거래 설정이 거부되는가, 가드 훅이 등록돼 있는가
하나라도 실패하면 종료 코드 1.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
LIVE_CONFIG = "config" + ".yaml"  # 운영 설정 파일 이름


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_pytest() -> tuple[bool, str]:
    code, out = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    last = out.splitlines()[-1] if out else "(출력 없음)"
    return code == 0, last if code == 0 else out[-1500:]


def check_demo() -> tuple[bool, str]:
    base = json.loads((ROOT / "tools" / "baseline.json").read_text(encoding="utf-8"))
    code, out = run([sys.executable, "run_demo.py", "--quiet"])
    if code != 0:
        return False, out[-800:]
    m1 = re.search(r"거래수 (\d+)건", out)
    m2 = re.search(r"비상손절 (\d+)건", out)
    got = {"trades": int(m1.group(1)) if m1 else None, "stops": int(m2.group(1)) if m2 else None}
    ok = got == {"trades": base["trades"], "stops": base["stops"]}
    msg = f"거래 {got['trades']}건, 비상손절 {got['stops']}건 (기준: {base['trades']}건, {base['stops']}건)"
    if not ok:
        msg += " — 전략·엔진을 의도적으로 바꾼 것이면 tools/baseline.json 을 고치고 사유를 기록하세요"
    return ok, msg


def check_safety() -> tuple[bool, str]:
    from bot.config import ConfigError, config_from_dict, load_config

    problems = []
    for name in ("config.example.yaml", "config.demo.yaml"):
        if not load_config(ROOT / name).dry_run:
            problems.append(f"{name} 이 드라이런이 아님")
    try:
        config_from_dict({"mode": {"dry_run": False}, "symbols": [{"key": "A", "symbol": "X"}]})
        problems.append("확인 문구 없는 실거래 설정이 통과됨")
    except ConfigError:
        pass
    settings = REPO / ".claude" / "settings.json"
    if not settings.exists() or "mt5_guard.py" not in settings.read_text(encoding="utf-8"):
        problems.append("가드 훅(.claude/settings.json)이 등록돼 있지 않음")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", f"mt5_bot/{LIVE_CONFIG}"],
                             cwd=REPO, capture_output=True).returncode == 0
    if tracked:
        problems.append("운영 설정 파일이 git 에 올라가 있음")
    return not problems, "이상 없음" if not problems else "; ".join(problems)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-demo", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    checks = [("pytest", check_pytest), ("안전장치", check_safety)]
    if not args.skip_demo:
        checks.insert(1, ("데모 회귀", check_demo))
    rows, all_ok = [], True
    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as exc:  # 검사 자체가 깨져도 결과로 남긴다
            ok, msg = False, f"검사 실행 오류: {exc}"
        all_ok &= ok
        rows.append((name, ok, msg))
    lines = [f"# 자동 검사 결과 — {datetime.now():%Y-%m-%d %H:%M}", "",
             f"**판정: {'통과' if all_ok else '실패'}**" + (" (데모 회귀 생략)" if args.skip_demo else ""), "",
             "| 검사 | 결과 | 내용 |", "|---|---|---|"]
    for name, ok, msg in rows:
        first = msg.splitlines()[0] if msg else ""
        lines.append(f"| {name} | {'통과' if ok else '**실패**'} | {first.replace('|', '/')} |")
    for name, ok, msg in rows:
        if not ok and "\n" in msg:
            lines += ["", f"## {name} 실패 출력", "```", msg, "```"]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
