from __future__ import annotations

from ..ai_analyzer import AIAnalyzer
from ..config import MODEL_DIR
from ..domain import StrategySettings, StrategyType
from .base import BaseStrategy
from .scalping import ScalpingStrategy
from .swing import SwingStrategy


def create_strategy(
    strategy_type: StrategyType,
    settings: StrategySettings,
    *,
    allow_rule_fallback: bool,
    friction_rate: float,
) -> BaseStrategy:
    if strategy_type is StrategyType.SCALPING:
        analyzer = AIAnalyzer(
            MODEL_DIR / "scalping_xgb_model.json",
            expected_interval="1m",
            strategy_type="SCALPING",
        )
        return ScalpingStrategy(
            settings,
            analyzer,
            allow_rule_fallback=allow_rule_fallback,
            friction_rate=friction_rate,
        )
    analyzer = AIAnalyzer(
        MODEL_DIR / "swing_xgb_model.json",
        expected_interval="1h",
        strategy_type="SWING",
    )
    return SwingStrategy(
        settings,
        analyzer,
        allow_rule_fallback=allow_rule_fallback,
        friction_rate=friction_rate,
    )
