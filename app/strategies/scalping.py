from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..cpp_adapter import scalping_entry, scalping_exit
from ..domain import Position, SignalAction, StrategyType, TradeSignal
from ..indicators import add_features
from .base import BaseStrategy


class ScalpingStrategy(BaseStrategy):
    strategy_type = StrategyType.SCALPING
    interval = "1m"
    period = "5d"
    freshness_minutes = 5
    polling_seconds = 15

    def evaluate_entry(self, df: pd.DataFrame) -> TradeSignal:
        features = add_features(df)
        if features.empty:
            return TradeSignal(SignalAction.HOLD, 0.0, "지표 계산에 필요한 데이터 부족")
        row = features.iloc[-1]
        decision = scalping_entry(
            rsi=float(row["rsi"]),
            macd_diff=float(row["macd_diff"]),
            ema_gap=float(row["ema_gap"]),
            vwap_dist=float(row["vwap_dist"]),
            volume_ratio=float(row["volume_ratio"]),
            bb_pband=float(row["bb_pband"]),
            disparity_5=float(row["disparity_5"]),
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
        if minutes_to_close is not None and minutes_to_close <= 5:
            return TradeSignal(SignalAction.SELL, 1.0, "장 마감 5분 전 강제 청산")
        if held_minutes >= self.settings.max_holding_minutes:
            return TradeSignal(SignalAction.SELL, 1.0, "스캘핑 최대 보유시간 초과")

        decision = scalping_exit(
            entry_price=position.entry_price,
            current_price=current_price,
            highest_price=highest_price,
            friction_rate=self.friction_rate,
            hard_stop=self.settings.stop_loss_rate,
            activation=self.settings.trailing_activation,
            initial_lock=max(0.001, self.settings.trailing_activation - self.settings.trailing_gap),
            step=0.004,
            take_profit=self.settings.take_profit_rate,
        )
        action = SignalAction.SELL if decision.should_exit else SignalAction.HOLD
        return TradeSignal(action, 1.0 if decision.should_exit else 0.0, decision.reason)
