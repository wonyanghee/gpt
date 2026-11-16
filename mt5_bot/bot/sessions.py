"""매매 시간대(세션) 제한.

"HH:MM-HH:MM" 형식의 시간대 목록으로 신규 진입 가능 시간을 정한다.
- 시작 시각 포함, 종료 시각 제외
- 시작 > 종료 이면 자정을 넘기는 시간대 (예: "22:00-02:00")
- 목록이 비어 있으면 제한 없음
"""
from __future__ import annotations

import re
from datetime import datetime, time

_WINDOW_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")

Window = tuple[int, int]  # (시작 분, 종료 분) - 자정 기준


def parse_sessions(specs) -> list[Window]:
    if isinstance(specs, str):
        specs = [specs]
    windows: list[Window] = []
    for spec in specs or []:
        m = _WINDOW_RE.match(str(spec))
        if not m:
            raise ValueError(f'시간대 형식 오류: "{spec}" (예: "09:00-17:30")')
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 23 or m1 > 59 or m2 > 59 or h2 > 24 or (h2 == 24 and m2 != 0):
            raise ValueError(f'시간대 범위 오류: "{spec}"')
        start, end = h1 * 60 + m1, (h2 * 60 + m2) % 1440
        if start == end:
            raise ValueError(f'시작과 종료가 같습니다: "{spec}" (하루 종일이면 sessions 를 비우세요)')
        windows.append((start, end))
    return windows


def minute_in_session(minute_of_day: int, windows: list[Window]) -> bool:
    if not windows:
        return True
    for start, end in windows:
        if start < end:
            if start <= minute_of_day < end:
                return True
        elif minute_of_day >= start or minute_of_day < end:  # 자정 넘김
            return True
    return False


def in_session(moment: datetime | time, windows: list[Window]) -> bool:
    return minute_in_session(moment.hour * 60 + moment.minute, windows)
