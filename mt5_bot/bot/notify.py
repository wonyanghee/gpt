"""텔레그램 알림과 CSV 거래 기록."""
from __future__ import annotations

import csv
import json
import logging
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class Notifier:
    """기본 알림: 로그로만 남긴다."""

    def send(self, text: str, dedupe: bool = False) -> None:
        log.info("[알림] %s", text)


class TelegramNotifier(Notifier):
    """환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 를 사용. 전송 실패해도 봇은 멈추지 않는다."""

    def __init__(self, token: str, chat_id: str, prefix: str = "[MT5봇]", dedupe_seconds: float = 600):
        self.token = token
        self.chat_id = chat_id
        self.prefix = prefix
        self.dedupe_seconds = dedupe_seconds
        self._last_sent: dict[str, float] = {}

    @classmethod
    def from_env(cls, enabled: bool, prefix: str = "[MT5봇]") -> Notifier:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not enabled:
            return Notifier()
        if not token or not chat_id:
            log.warning("telegram.enabled=true 이지만 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 가 없어 로그로만 남깁니다")
            return Notifier()
        return cls(token, chat_id, prefix)

    def send(self, text: str, dedupe: bool = False) -> None:
        log.info("[알림] %s", text)
        now = time.monotonic()
        if dedupe:
            last = self._last_sent.get(text)
            if last is not None and now - last < self.dedupe_seconds:
                return
        self._last_sent[text] = now
        try:
            data = json.dumps({"chat_id": self.chat_id, "text": f"{self.prefix} {text}"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception as exc:  # 알림 실패가 매매를 막으면 안 됨
            log.warning("텔레그램 전송 실패: %s", exc)


class TradeLog:
    FIELDS = [
        "time", "mode", "key", "symbol", "action", "direction", "volume",
        "price", "sl", "strategy", "reason", "ticket", "profit",
    ]

    def __init__(self, path: Path, mode: str):
        self.path = Path(path)
        self.mode = mode
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, **row) -> None:
        new_file = not self.path.exists()
        row = {"time": datetime.now().isoformat(timespec="seconds"), "mode": self.mode, **row}
        with self.path.open("a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
