from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from .config import TARGETS_PATH
from .domain import StrategyType

logger = logging.getLogger(__name__)

MASTER_UNIVERSE = [
    "TQQQ", "SQQQ", "SOXL", "SOXS", "UPRO", "SPXU", "TECL", "TECS",
    "NVDA", "AAPL", "TSLA", "MSFT", "AMD", "META", "AMZN", "GOOGL", "AVGO", "TSM",
    "INTC", "MU", "SMCI", "QCOM", "ARM", "ASML", "ORCL", "CSCO", "ANET", "SNPS",
    "CDNS", "KLAC", "LRCX", "AMAT", "MRVL", "PLTR", "SNOW", "CRWD", "MDB", "DDOG",
    "OKTA", "ZS", "FTNT", "COIN", "MARA", "RIOT", "MSTR", "HOOD", "PYPL", "SOFI",
    "AFRM", "RIVN", "LCID", "GME", "AMC", "RDDT", "IONQ",
]


class MarketScanner:
    def __init__(self, universe: list[str] | None = None):
        self.universe = list(dict.fromkeys(universe or MASTER_UNIVERSE))

    @staticmethod
    def _extract_symbol(batch: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if batch.empty:
            return pd.DataFrame()
        if not isinstance(batch.columns, pd.MultiIndex):
            result = batch.copy()
        else:
            if ticker in batch.columns.get_level_values(1):
                result = batch.xs(ticker, axis=1, level=1).copy()
            elif ticker in batch.columns.get_level_values(0):
                result = batch.xs(ticker, axis=1, level=0).copy()
            else:
                return pd.DataFrame()
        result.columns = [str(column).lower() for column in result.columns]
        return result.dropna(how="all")

    def scan(self, strategy_type: StrategyType, *, limit: int = 10) -> list[str]:
        if strategy_type is StrategyType.SCALPING:
            candidates = self._scan_scalping(limit)
        else:
            candidates = self._scan_swing(limit)
        if not candidates:
            candidates = ["QQQ", "NVDA"] if strategy_type is StrategyType.SWING else ["TQQQ", "SOXL"]
        self.save_atomic(candidates, TARGETS_PATH)
        return candidates

    def _scan_scalping(self, limit: int) -> list[str]:
        logger.info("스캘핑 후보 스캔 시작")
        batch = yf.download(
            " ".join(self.universe),
            period="5d",
            interval="5m",
            progress=False,
            auto_adjust=False,
            prepost=True,
            group_by="column",
            threads=True,
        )
        scored: list[tuple[str, float]] = []
        for ticker in self.universe:
            data = self._extract_symbol(batch, ticker)
            if len(data) < 30:
                continue
            close = pd.to_numeric(data["close"], errors="coerce")
            volume = pd.to_numeric(data["volume"], errors="coerce")
            price = float(close.iloc[-1])
            if not 5 <= price <= 1000:
                continue
            dollar_volume = float((close.tail(20) * volume.tail(20)).mean())
            if dollar_volume < 2_000_000:
                continue
            volume_average = float(volume.tail(20).mean())
            volume_ratio = float(volume.iloc[-1] / volume_average) if volume_average > 0 else 0.0
            momentum = float(close.iloc[-1] / close.iloc[-13] - 1.0)
            if momentum <= 0:
                continue
            score = momentum * 100.0 + min(volume_ratio, 5.0) * 0.3 + np.log10(dollar_volume) * 0.05
            scored.append((ticker, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [ticker for ticker, _ in scored[:limit]]

    def _scan_swing(self, limit: int) -> list[str]:
        logger.info("스윙 후보 스캔 시작")
        batch = yf.download(
            " ".join(self.universe),
            period="1y",
            interval="1d",
            progress=False,
            auto_adjust=False,
            group_by="column",
            threads=True,
        )
        scored: list[tuple[str, float]] = []
        for ticker in self.universe:
            data = self._extract_symbol(batch, ticker)
            if len(data) < 60:
                continue
            close = pd.to_numeric(data["close"], errors="coerce")
            volume = pd.to_numeric(data["volume"], errors="coerce")
            price = float(close.iloc[-1])
            if not 5 <= price <= 2000:
                continue
            ema20 = close.ewm(span=20, adjust=False).mean()
            ema50 = close.ewm(span=50, adjust=False).mean()
            momentum20 = float(close.iloc[-1] / close.iloc[-21] - 1.0)
            dollar_volume = float((close.tail(20) * volume.tail(20)).mean())
            if ema20.iloc[-1] <= ema50.iloc[-1] or momentum20 <= 0 or dollar_volume < 5_000_000:
                continue
            score = momentum20 * 100.0 + float(ema20.iloc[-1] / ema50.iloc[-1] - 1.0) * 50.0
            scored.append((ticker, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [ticker for ticker, _ in scored[:limit]]

    @staticmethod
    def save_atomic(tickers: list[str], path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(tickers, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
