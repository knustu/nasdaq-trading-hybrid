from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from .indicators import normalize_ohlcv

logger = logging.getLogger(__name__)


class DataFeed:
    def __init__(self):
        self._last_bar: dict[tuple[str, str], pd.Timestamp] = {}

    def fetch(
        self,
        ticker: str,
        *,
        period: str,
        interval: str,
        prepost: bool = False,
    ) -> pd.DataFrame:
        symbol = ticker.upper().strip()
        if not symbol:
            return pd.DataFrame()
        try:
            raw = yf.download(
                symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                prepost=prepost,
                threads=False,
            )
            result = normalize_ohlcv(raw)
            if result.empty:
                logger.warning("%s %s 데이터가 비어 있습니다.", symbol, interval)
            return result
        except Exception as exc:
            logger.error("%s 데이터 수신 실패: %s", symbol, exc)
            return pd.DataFrame()

    @staticmethod
    def latest_price(df: pd.DataFrame) -> float:
        if df is None or df.empty:
            return 0.0
        return float(df["close"].iloc[-1])

    @staticmethod
    def last_bar_time(df: pd.DataFrame) -> pd.Timestamp | None:
        if df is None or df.empty:
            return None
        timestamp = pd.Timestamp(df.index[-1])
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize("America/New_York")
        return timestamp.tz_convert("UTC")

    def is_fresh(self, df: pd.DataFrame, *, max_age_minutes: int) -> bool:
        bar_time = self.last_bar_time(df)
        if bar_time is None:
            return False
        age = datetime.now(timezone.utc) - bar_time.to_pydatetime()
        return age.total_seconds() <= max_age_minutes * 60

    def is_new_bar(self, ticker: str, interval: str, df: pd.DataFrame) -> bool:
        timestamp = self.last_bar_time(df)
        if timestamp is None:
            return False
        key = (ticker.upper(), interval)
        previous = self._last_bar.get(key)
        if previous is not None and timestamp <= previous:
            return False
        self._last_bar[key] = timestamp
        return True
