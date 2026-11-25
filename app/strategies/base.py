from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

from ..ai_analyzer import AIAnalyzer
from ..domain import Position, StrategySettings, StrategyType, TradeSignal


class BaseStrategy(ABC):
    strategy_type: StrategyType
    interval: str
    period: str
    freshness_minutes: int
    polling_seconds: int

    def __init__(
        self,
        settings: StrategySettings,
        analyzer: AIAnalyzer,
        *,
        allow_rule_fallback: bool,
        friction_rate: float,
    ):
        self.settings = settings
        self.analyzer = analyzer
        self.allow_rule_fallback = allow_rule_fallback
        self.friction_rate = friction_rate

    @property
    def stop_loss_rate(self) -> float:
        return self.settings.stop_loss_rate

    def ai_probability(self, df: pd.DataFrame) -> float | None:
        return self.analyzer.predict_probability(df, self.interval)

    @abstractmethod
    def evaluate_entry(self, df: pd.DataFrame) -> TradeSignal:
        raise NotImplementedError

    @abstractmethod
    def evaluate_exit(
        self,
        position: Position,
        *,
        current_price: float,
        highest_price: float,
        now_et: datetime,
        minutes_to_close: float | None,
    ) -> TradeSignal:
        raise NotImplementedError
