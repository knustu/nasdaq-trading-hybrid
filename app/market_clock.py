from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

try:
    import pandas_market_calendars as mcal
except ImportError:  # pragma: no cover - requirements 설치 전 안전 폴백
    mcal = None


@dataclass(frozen=True)
class MarketState:
    now_et: datetime
    is_trading_day: bool
    is_regular_session: bool
    session_open: datetime | None
    session_close: datetime | None


class MarketClock:
    def __init__(self, exchange: str = "NYSE"):
        self.exchange = exchange
        self.calendar = mcal.get_calendar(exchange) if mcal is not None else None
        if self.calendar is None:
            logger.warning("pandas_market_calendars 미설치: 미국 휴장일 검증은 제한됩니다.")

    def state(self, now: datetime | None = None) -> MarketState:
        now_et = (now or datetime.now(ET)).astimezone(ET)
        if self.calendar is None:
            trading_day = now_et.weekday() < 5
            opening = datetime.combine(now_et.date(), time(9, 30), ET) if trading_day else None
            closing = datetime.combine(now_et.date(), time(16, 0), ET) if trading_day else None
            regular = bool(opening and closing and opening <= now_et < closing)
            return MarketState(now_et, trading_day, regular, opening, closing)

        schedule = self.calendar.schedule(
            start_date=now_et.date() - timedelta(days=1),
            end_date=now_et.date() + timedelta(days=1),
        )
        matching = schedule[schedule.index.date == now_et.date()]
        if matching.empty:
            return MarketState(now_et, False, False, None, None)
        row = matching.iloc[0]
        opening = row["market_open"].to_pydatetime().astimezone(ET)
        closing = row["market_close"].to_pydatetime().astimezone(ET)
        return MarketState(now_et, True, opening <= now_et < closing, opening, closing)

    def minutes_to_close(self, now: datetime | None = None) -> float | None:
        state = self.state(now)
        if state.session_close is None:
            return None
        return (state.session_close - state.now_et).total_seconds() / 60.0
