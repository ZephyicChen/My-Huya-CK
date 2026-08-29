"""JSONL writers for raw URI events and channel status."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from . import SCHEMA_VERSION


class JsonlWriter:
    def __init__(self, path: Path, base_fields: dict):
        self.path = path
        self.base_fields = base_fields
        self.count = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "a", encoding="utf-8")

    def write(self, event: dict) -> None:
        record = dict(self.base_fields)
        record.update(event)
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()
        self.count += 1

    def close(self) -> None:
        try:
            self._file.flush()
        finally:
            self._file.close()


class CaptureLogger:
    def __init__(self, log_dir: str, room_id: str, room_url: str, run_id: str, session_id: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.session_id = session_id
        base = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "session_id": session_id,
            "room_id": room_id,
            "room_url": room_url,
        }
        self.raw = JsonlWriter(self.log_dir / f"{run_id}-raw.jsonl", base)
        self.channel = JsonlWriter(self.log_dir / f"{run_id}-channel.jsonl", base)

    @property
    def raw_path(self) -> Path:
        return self.raw.path

    @property
    def channel_path(self) -> Path:
        return self.channel.path

    def write_raw(self, event: dict) -> None:
        self.raw.write(event)

    def write_channel(self, event: dict) -> None:
        self.channel.write(event)

    def close(self) -> None:
        self.raw.close()
        self.channel.close()


def new_run_id(log_dir: str) -> str:
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    date_part = datetime.now().astimezone().strftime("%Y%m%d")
    max_seq = 0
    for path in log_path.iterdir():
        match = re.match(rf"{date_part}-(\d+)", path.name)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"{date_part}-{max_seq + 1:03d}"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def extract_room_id(room_url: str) -> str:
    match = re.search(r"huya\.com/(\w+)", room_url)
    return match.group(1) if match else ""


def fingerprint(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return hashlib.sha1(data).hexdigest()[:16]
