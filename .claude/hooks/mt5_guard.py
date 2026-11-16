#!/usr/bin/env python3
"""Claude Code PreToolUse 훅: 실거래와 관련된 두 가지를 막는다.

1. mt5_bot/config.yaml (운영 설정) 을 만들거나 고치는 것
2. run_bot.py 를 실행하는 것

실거래 설정과 봇 실행은 사람이 직접 한다. 종료 코드 2 는 도구 호출을 거부하고 사유를 에이전트에게 돌려준다.
"""
import json
import re
import sys

RUN_BOT = re.compile(r"(^|[\s;&|(`])(py|python[\w.]*)(\.exe)?\s+(-\S+\s+)*[\"']?(\S*[\\/])?run_bot\.py")
WRITE_CONFIG = re.compile(r"(>|\btee\b|\bcp\b|\bmv\b|\bsed\s+-i|\bcopy\b)[^|;&]*mt5_bot[\\/]config\.yaml")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    tool = event.get("tool_name", "")
    inp = event.get("tool_input", {}) or {}

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(inp.get("file_path", "")).replace("\\", "/")
        if path.endswith("mt5_bot/config.yaml"):
            print("차단: mt5_bot/config.yaml 은 운영 설정이라 사람만 수정합니다. "
                  "config.example.yaml 이나 스크래치 폴더의 사본을 쓰세요.", file=sys.stderr)
            return 2
    elif tool == "Bash":
        cmd = str(inp.get("command", ""))
        if RUN_BOT.search(cmd):
            print("차단: run_bot.py 는 사람이 직접 실행합니다. "
                  "에이전트는 pytest, run_backtest.py, run_demo.py 만 실행할 수 있습니다.", file=sys.stderr)
            return 2
        if WRITE_CONFIG.search(cmd):
            print("차단: mt5_bot/config.yaml 은 운영 설정이라 사람만 수정합니다.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
