from __future__ import annotations

from datetime import datetime

from app.config import CONFIG
from app.market_clock import ET, MarketState
from app.trading_service import TradingService


def test_entry_time_restriction_is_disabled_by_default():
    assert CONFIG.restrict_entry_to_regular_session is False
    market = MarketState(
        now_et=datetime(2026, 6, 10, 20, 0, tzinfo=ET),
        is_trading_day=True,
        is_regular_session=False,
        session_open=None,
        session_close=None,
    )
    assert TradingService._entry_session_allowed(market) is True
