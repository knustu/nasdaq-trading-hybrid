from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import LOG_DIR

ET = ZoneInfo("America/New_York")


class EasternTimeFormatter(logging.Formatter):
    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=ET)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")


def setup_logging(username: str = "app", level: int = logging.INFO) -> Path:
    safe_name = "".join(ch for ch in username if ch.isalnum() or ch in "_-" ) or "app"
    date_text = datetime.now(ET).strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"{safe_name}_{date_text}.log"

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = EasternTimeFormatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    return log_path
