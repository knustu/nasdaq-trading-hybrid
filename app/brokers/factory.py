from __future__ import annotations

from ..config import CONFIG
from ..database import Database
from ..domain import TradingMode
from .base import BaseBroker
from .paper import PaperBroker
from .toss import TossLiveBroker


def create_broker(db: Database, mode: TradingMode) -> BaseBroker:
    if mode is TradingMode.PAPER:
        return PaperBroker(
            db,
            fee_rate=CONFIG.paper_fee_rate,
            slippage_rate=CONFIG.paper_slippage_rate,
        )
    return TossLiveBroker(db, CONFIG)
