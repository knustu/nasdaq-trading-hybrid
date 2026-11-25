from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class StrategyType(str, Enum):
    SCALPING = "SCALPING"
    SWING = "SWING"


class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class User:
    id: int
    username: str
    is_active: bool


@dataclass(frozen=True)
class UserPreferences:
    strategy_type: StrategyType
    trading_mode: TradingMode
    risk_per_trade: float
    max_positions: int
    max_trades_per_day: int


@dataclass(frozen=True)
class StrategySettings:
    strategy_type: StrategyType
    entry_threshold: float
    stop_loss_rate: float
    take_profit_rate: float
    trailing_activation: float
    trailing_gap: float
    max_holding_minutes: int


@dataclass(frozen=True)
class TradeSignal:
    action: SignalAction
    confidence: float
    reason: str


@dataclass(frozen=True)
class Position:
    id: int
    user_id: int
    strategy_type: StrategyType
    ticker: str
    quantity: int
    entry_price: float
    highest_price: float
    opened_at: datetime


@dataclass(frozen=True)
class OrderResult:
    success: bool
    status: str
    ticker: str
    side: str
    quantity: int
    fill_price: float = 0.0
    fee_amount: float = 0.0
    broker_order_id: str = ""
    message: str = ""
