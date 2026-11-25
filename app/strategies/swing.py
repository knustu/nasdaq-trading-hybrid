from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..cpp_adapter import swing_entry, swing_exit
from ..domain import Position, SignalAction, StrategyType, TradeSignal
from ..indicators import add_features
from .base import BaseStrategy


class SwingStrategy(BaseStrategy):
    strategy_type = StrategyType.SWING
    interval = "1h"
    period = "2y"
    freshness_minutes = 180
    polling_seconds = 300

    def evaluate_entry(self, df: pd.DataFrame) -> TradeSignal:
        features = add_features(df)
        if features.empty:
            return TradeSignal(SignalAction.HOLD, 0.0, "지표 계산에 필요한 데이터 부족")
        row = features.iloc[-1]
        previous = features.iloc[-6] if len(features) >= 6 else features.iloc[0]
        decision = swing_entry(
            rsi=float(row["rsi"]),
            macd_diff=float(row["macd_diff"]),
            disparity_20=float(row["disparity_20"]),
            ema_gap=float(row["ema_gap"]),
            current_close=float(row["close"]),
            previous_close=float(previous["close"]),
            volume_ratio=float(row["volume_ratio"]),
            atr_pct=float(row["atr_pct"]),
            ai_probability=self.ai_probability(features),
            entry_threshold=self.settings.entry_threshold,
            allow_rule_fallback=self.allow_rule_fallback,
        )
        action = SignalAction.BUY if decision.should_enter else SignalAction.HOLD
        detail = (
            f"{decision.reason} | 최종 {decision.final_probability:.1%} "
            f"(규칙 {decision.rule_score:.1%}{', AI 사용' if decision.used_ai else ''})"
        )
        return TradeSignal(action, decision.final_probability, detail)

    def evaluate_exit(
        self,
        position: Position,
        *,
        current_price: float,
        highest_price: float,
        now_et: datetime,
        minutes_to_close: float | None,
    ) -> TradeSignal:
        opened = position.opened_at
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        held_minutes = (now_et.astimezone(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds() / 60
        if held_minutes >= self.settings.max_holding_minutes:
            return TradeSignal(SignalAction.SELL, 1.0, "스윙 최대 보유기간 초과")

        decision = swing_exit(
            entry_price=position.entry_price,
            current_price=current_price,
            highest_price=highest_price,
            friction_rate=self.friction_rate,
            stop_loss=self.settings.stop_loss_rate,
            take_profit=self.settings.take_profit_rate,
            trailing_activation=self.settings.trailing_activation,
            trailing_gap=self.settings.trailing_gap,
        )
        action = SignalAction.SELL if decision.should_exit else SignalAction.HOLD
        return TradeSignal(action, 1.0 if decision.should_exit else 0.0, decision.reason)
