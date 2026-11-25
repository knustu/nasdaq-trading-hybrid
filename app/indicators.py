from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import VolumeWeightedAveragePrice

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")
FEATURE_COLUMNS = (
    "rsi",
    "bb_pband",
    "macd_diff",
    "disparity_5",
    "disparity_20",
    "ema_gap",
    "vwap_dist",
    "volume_ratio",
    "atr_pct",
)


def normalize_ohlcv(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = df.copy()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = result.columns.get_level_values(0)
    result.columns = [str(column).lower().replace(" ", "_") for column in result.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in result.columns]
    if missing:
        logger.error("필수 OHLCV 컬럼 누락: %s", missing)
        return pd.DataFrame()
    for column in REQUIRED_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=list(REQUIRED_COLUMNS)).sort_index()
    result = result[~result.index.duplicated(keep="last")]
    return result


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    result = normalize_ohlcv(df)
    if result.empty or len(result) < 40:
        return pd.DataFrame()

    close = result["close"]
    result["rsi"] = RSIIndicator(close=close, window=14).rsi()
    bb = BollingerBands(close=close, window=20, window_dev=2)
    result["bb_pband"] = bb.bollinger_pband()
    result["macd_diff"] = MACD(close=close).macd_diff()
    result["sma_5"] = close.rolling(5).mean()
    result["sma_20"] = close.rolling(20).mean()
    result["disparity_5"] = close / result["sma_5"] - 1.0
    result["disparity_20"] = close / result["sma_20"] - 1.0
    ema_9 = EMAIndicator(close=close, window=9).ema_indicator()
    ema_21 = EMAIndicator(close=close, window=21).ema_indicator()
    result["ema_gap"] = ema_9 / ema_21 - 1.0

    try:
        vwap = VolumeWeightedAveragePrice(
            high=result["high"],
            low=result["low"],
            close=close,
            volume=result["volume"],
            window=14,
        ).volume_weighted_average_price()
        result["vwap_dist"] = close / vwap - 1.0
    except Exception:
        typical = (result["high"] + result["low"] + close) / 3.0
        cumulative_volume = result["volume"].rolling(14).sum()
        result["vwap_dist"] = close / (
            (typical * result["volume"]).rolling(14).sum() / cumulative_volume
        ) - 1.0

    average_volume = result["volume"].rolling(20).mean().replace(0, np.nan)
    result["volume_ratio"] = result["volume"] / average_volume
    atr = AverageTrueRange(
        high=result["high"], low=result["low"], close=close, window=14
    ).average_true_range()
    result["atr_pct"] = atr / close
    return result.dropna()
