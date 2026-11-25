from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
MODEL_DIR = BASE_DIR / "models"
DB_PATH = DATA_DIR / "trading_app.db"
TARGETS_PATH = DATA_DIR / "today_targets.json"

for directory in (DATA_DIR, LOG_DIR, MODEL_DIR):
    directory.mkdir(parents=True, exist_ok=True)

load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    database_path: Path = DB_PATH
    paper_initial_balance: float = float(os.getenv("PAPER_INITIAL_BALANCE", "10000"))
    paper_fee_rate: float = float(os.getenv("PAPER_FEE_RATE", "0.0010"))
    paper_slippage_rate: float = float(os.getenv("PAPER_SLIPPAGE_RATE", "0.0005"))
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "").strip()
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    allow_live_trading: bool = os.getenv("ALLOW_LIVE_TRADING", "false").lower() == "true"
    toss_access_token: str = os.getenv("TOSS_ACCESS_TOKEN", "").strip()
    toss_account_seq: str = os.getenv("TOSS_ACCOUNT_SEQ", "").strip()
    toss_base_url: str = os.getenv("TOSS_BASE_URL", "https://openapi.tossinvest.com/v1").rstrip("/")
    toss_balance_path: str = os.getenv("TOSS_BALANCE_PATH", "").strip()
    toss_order_status_path: str = os.getenv("TOSS_ORDER_STATUS_PATH", "").strip()
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5"))
    restrict_entry_to_regular_session: bool = (
        os.getenv("RESTRICT_ENTRY_TO_REGULAR_SESSION", "false").lower() == "true"
    )
    require_cpp_engine: bool = os.getenv("REQUIRE_CPP_ENGINE", "true").lower() == "true"

    def live_ready(self) -> bool:
        return bool(
            self.allow_live_trading
            and self.toss_access_token
            and self.toss_account_seq
            and self.toss_balance_path
            and self.toss_order_status_path
            and "{order_id}" in self.toss_order_status_path
        )


CONFIG = AppConfig()
