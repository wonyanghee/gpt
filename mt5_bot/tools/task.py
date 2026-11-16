"""작업 폴더와 작업대장을 관리한다 (감독관이 사용).

    python tools/task.py new "제목" --type research     # 작업 폴더 + 작업지시서 양식 생성
    python tools/task.py gate 20261116-01 collect pass "필수 항목 6개 모두 수집"
    python tools/task.py gate 20261116-01 verify redo "핵심 수치 2건 불일치 → 정리 단계로"
    python tools/task.py close 20261116-01 "채택 보류: 검증 구간 PF 1.05"
    python tools/task.py list

유형: research(연구·분석) / ops(운영 분석) / code(코드 변경)
단계: order, collect, organize, build, verify, report
판정: pass(통과) / redo(보완) / stop(중단, 사람에게 넘김)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

WORK = Path(__file__).resolve().parents[1] / "work"
LEDGER = WORK / "LEDGER.md"
TYPES = {"research": "연구·분석", "ops": "운영 분석", "code": "코드 변경"}
STAGES = {"order": "작업지시", "collect": "정보수집", "organize": "데이터 정리", "build": "구현",
          "verify": "감수/검증", "report": "최종검토 보고"}
VERDICTS = {"pass": "통과", "redo": "보완", "stop": "중단"}
MAX_ROUNDS = 3
LEDGER_HEAD = ("# 작업대장\n\n모든 작업의 기록입니다. `tools/task.py` 가 관리하므로 직접 고치지 않습니다.\n\n"
               "| ID | 제목 | 유형 | 상태 | 시작 | 종료 | 결과 |\n|---|---|---|---|---|---|---|\n")

ORDER = """# 작업지시서 — {title}

- 작업 ID: {tid}
- 유형: {type_name}
- 작성: 감독관 / {now}

## 1. 요청 원문
(사용자가 요청한 말을 그대로 옮긴다)

## 2. 완료 기준
(최종 보고가 답해야 할 질문. 확인 가능한 문장으로 쓴다)
- [ ]

## 3. 정보수집 조건
- 시작 조건: (수집을 시작해도 되는 상태. 예: 필요한 입력 파일이 있다)
- 범위: (어디까지 모으는가. 범위 밖은 무엇인가)
- 허용 출처: (코드 / 백테스트 실행 / 로그·거래 기록 / 웹 — 해당하는 것만)
- 필수 수집 항목:
  1.
- 종료 조건: 필수 항목을 모두 채웠거나, 아래 한도에 닿았을 때. 못 채운 항목은 "미수집 + 사유"로 남기고 끝낸다.
- 한도: (예: 백테스트 최대 12회 / 웹 출처 최대 8개)

## 4. 데이터 정리 조건
- 시작 조건: 정보수집 게이트 통과
- 산출 형식: (표의 열, 비교 기준, 단위)
- 종료 조건: 산출 형식을 모두 채웠고, 모든 수치에 출처(10-collect.md 의 항목 번호나 raw 파일)가 붙어 있다.

## 5. 구현 조건 (코드 변경 작업만)
- 바꿀 범위:
- 바꾸지 않을 것:
- 종료 조건: `python tools/check.py` 통과

## 6. 감수/검증 조건
- 검증 범위: (예: 핵심 수치 전부 재계산 + 나머지 중 표본 5개)
- 판정 기준: (무엇이 틀리면 보완, 무엇이 틀리면 중단인가)

## 7. 사람 승인이 필요한 것
- (예: 전략 채택, 설정값 변경 적용, main 브랜치 병합)
"""

STATUS = """# 진행 상태 — {title}

- 작업 ID: {tid}
- 현재 단계: 작업지시
- 반복 횟수: 0 / {max_rounds}

## 게이트 기록
| 시각 | 단계 | 판정 | 근거 |
|---|---|---|---|
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def find(tid: str) -> Path:
    matches = [p for p in WORK.glob(f"{tid}*") if p.is_dir()]
    if len(matches) != 1:
        sys.exit(f"작업 폴더를 찾을 수 없습니다: {tid}")
    return matches[0]


def update_ledger(tid: str, **fields) -> None:
    lines = LEDGER.read_text(encoding="utf-8").splitlines()
    cols = ["ID", "제목", "유형", "상태", "시작", "종료", "결과"]
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == tid:
            row = dict(zip(cols, cells))
            row.update(fields)
            lines[i] = "| " + " | ".join(row[c] for c in cols) + " |"
            break
    else:
        sys.exit(f"작업대장에 없는 ID: {tid}")
    LEDGER.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_new(args) -> None:
    WORK.mkdir(exist_ok=True)
    if not LEDGER.exists():
        LEDGER.write_text(LEDGER_HEAD, encoding="utf-8")
    day = datetime.now().strftime("%Y%m%d")
    n = 1 + sum(1 for p in WORK.glob(f"{day}-*") if p.is_dir())
    tid = f"{day}-{n:02d}"
    folder = WORK / tid  # 폴더 이름은 ID 만 (제목은 작업대장과 작업지시서에 있음)
    (folder / "raw").mkdir(parents=True)
    (folder / "raw" / ".gitkeep").write_text("", encoding="utf-8")
    ctx = dict(title=args.title, tid=tid, type_name=TYPES[args.type], now=now(), max_rounds=MAX_ROUNDS)
    (folder / "00-order.md").write_text(ORDER.format(**ctx), encoding="utf-8")
    (folder / "status.md").write_text(STATUS.format(**ctx), encoding="utf-8")
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(f"| {tid} | {args.title.replace('|', '/')} | {TYPES[args.type]} | 작업지시 | {now()} | - | - |\n")
    print(f"작업 ID: {tid}\n폴더: {folder}")


def cmd_gate(args) -> None:
    folder = find(args.id)
    status = folder / "status.md"
    text = status.read_text(encoding="utf-8")
    rounds = int(re.search(r"반복 횟수: (\d+)", text).group(1))
    verdict, note = args.verdict, args.note
    if verdict == "redo":
        rounds += 1
        if rounds >= MAX_ROUNDS:
            verdict = "stop"
            note += f" (보완 {MAX_ROUNDS}회 도달 → 자동 중단, 사람에게 넘김)"
    stage_name = STAGES[args.stage]
    if verdict == "pass":
        nxt = "완료 대기" if args.stage == "report" else f"{stage_name} 통과"
    elif verdict == "redo":
        nxt = f"{stage_name} 보완 중"
    else:
        nxt = "중단 (사람 확인 필요)"
    text = re.sub(r"현재 단계: .*", f"현재 단계: {nxt}", text)
    text = re.sub(r"반복 횟수: \d+", f"반복 횟수: {rounds}", text)
    text = text.rstrip("\n") + f"\n| {now()} | {stage_name} | {VERDICTS[verdict]} | {note.replace('|', '/')} |\n"
    status.write_text(text, encoding="utf-8")
    update_ledger(args.id, 상태=nxt)
    print(f"{args.id} {stage_name}: {VERDICTS[verdict]} (반복 {rounds}/{MAX_ROUNDS})")
    if verdict == "stop":
        sys.exit(3)


def cmd_close(args) -> None:
    folder = find(args.id)
    status = folder / "status.md"
    text = re.sub(r"현재 단계: .*", "현재 단계: 완료", status.read_text(encoding="utf-8"))
    status.write_text(text.rstrip("\n") + f"\n| {now()} | 종료 | 완료 | {args.result.replace('|', '/')} |\n", encoding="utf-8")
    update_ledger(args.id, 상태="완료", 종료=now(), 결과=args.result.replace("|", "/"))
    print(f"{args.id} 완료")


def cmd_list(_args) -> None:
    print(LEDGER.read_text(encoding="utf-8") if LEDGER.exists() else "작업이 없습니다")


def main() -> None:
    ap = argparse.ArgumentParser(description="작업 폴더·작업대장 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("title"); p.add_argument("--type", choices=TYPES, required=True); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("gate"); p.add_argument("id"); p.add_argument("stage", choices=STAGES)
    p.add_argument("verdict", choices=VERDICTS); p.add_argument("note"); p.set_defaults(fn=cmd_gate)
    p = sub.add_parser("close"); p.add_argument("id"); p.add_argument("result"); p.set_defaults(fn=cmd_close)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
