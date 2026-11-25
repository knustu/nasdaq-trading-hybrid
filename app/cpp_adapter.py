from __future__ import annotations

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import trading_engine  # type: ignore
except ImportError:
    trading_engine = None

NO_AI_PROBABILITY = -1.0


@dataclass(frozen=True)
class EntryDecision:
    should_enter: bool
    used_ai: bool
    rule_score: float
    final_probability: float
    reason: str


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    trailing_active: bool
    lock_return: float
    net_return: float
    reason: str


@dataclass(frozen=True)
class PositionSizeDecision:
    quantity: int
    by_cash: int
    by_risk: int
    allocated_cash: float
    risk_budget: float
    reason: str


@dataclass(frozen=True)
class PaperFillDecision:
    fill_price: float
    gross_amount: float
    fee_amount: float
    cash_delta: float


@dataclass(frozen=True)
class TradeMathDecision:
    gross_pnl: float
    total_fees: float
    net_pnl: float
    invested_amount: float
    net_return: float


def engine_available() -> bool:
    return trading_engine is not None


def engine_backend_name() -> str:
    if trading_engine is None:
        return "PYTHON_FALLBACK"
    try:
        return f"C++/{trading_engine.engine_version()}"
    except Exception:
        return "C++/UNKNOWN"


def require_cpp_engine() -> None:
    if trading_engine is None:
        raise RuntimeError(
            "C++ 거래 엔진이 빌드되지 않았습니다. build_cpp.bat을 실행한 뒤 다시 시작하세요."
        )


def _safe_probability(value: float | None) -> float:
    if value is None or not math.isfinite(value):
        return NO_AI_PROBABILITY
    return max(0.0, min(1.0, float(value)))


def _finalize_entry(
    *,
    rule_score: float,
    ai_probability: float | None,
    threshold: float,
    allow_rule_fallback: bool,
    strategy_name: str,
) -> EntryDecision:
    rule_score = max(0.0, min(1.0, rule_score))
    if ai_probability is not None and math.isfinite(ai_probability):
        probability = max(0.0, min(1.0, ai_probability * 0.75 + rule_score * 0.25))
        enter = probability >= max(0.0, min(1.0, threshold))
        return EntryDecision(
            enter,
            True,
            rule_score,
            probability,
            f"{strategy_name} {'진입 승인' if enter else '기준 미달'}: AI+규칙 결합",
        )
    if not allow_rule_fallback:
        return EntryDecision(False, False, rule_score, 0.0, "검증된 AI 모델이 없어 진입 차단")
    enter = rule_score >= max(0.0, min(1.0, threshold))
    return EntryDecision(
        enter,
        False,
        rule_score,
        rule_score,
        f"{strategy_name} {'진입 승인' if enter else '기준 미달'}: 규칙 기반 PAPER 판단",
    )


def scalping_entry(
    *,
    rsi: float,
    macd_diff: float,
    ema_gap: float,
    vwap_dist: float,
    volume_ratio: float,
    bb_pband: float,
    disparity_5: float,
    ai_probability: float | None,
    entry_threshold: float,
    allow_rule_fallback: bool,
) -> EntryDecision:
    if trading_engine is not None:
        result = trading_engine.evaluate_scalping_entry(
            rsi,
            macd_diff,
            ema_gap,
            vwap_dist,
            volume_ratio,
            bb_pband,
            disparity_5,
            _safe_probability(ai_probability),
            entry_threshold,
            allow_rule_fallback,
        )
        return EntryDecision(
            bool(result.should_enter),
            bool(result.used_ai),
            float(result.rule_score),
            float(result.final_probability),
            str(result.reason),
        )

    score = 0.0
    score += 0.20 if 48 <= rsi <= 68 else 0.0
    score += 0.20 if macd_diff > 0 else 0.0
    score += 0.15 if ema_gap > 0 else 0.0
    score += 0.15 if vwap_dist > 0 else 0.0
    score += 0.15 if volume_ratio >= 1.2 else 0.0
    score += 0.10 if 0.35 <= bb_pband <= 0.95 else 0.0
    score += 0.05 if disparity_5 > 0 else 0.0
    return _finalize_entry(
        rule_score=score,
        ai_probability=ai_probability,
        threshold=entry_threshold,
        allow_rule_fallback=allow_rule_fallback,
        strategy_name="스캘핑",
    )


def swing_entry(
    *,
    rsi: float,
    macd_diff: float,
    disparity_20: float,
    ema_gap: float,
    current_close: float,
    previous_close: float,
    volume_ratio: float,
    atr_pct: float,
    ai_probability: float | None,
    entry_threshold: float,
    allow_rule_fallback: bool,
) -> EntryDecision:
    if trading_engine is not None:
        result = trading_engine.evaluate_swing_entry(
            rsi,
            macd_diff,
            disparity_20,
            ema_gap,
            current_close,
            previous_close,
            volume_ratio,
            atr_pct,
            _safe_probability(ai_probability),
            entry_threshold,
            allow_rule_fallback,
        )
        return EntryDecision(
            bool(result.should_enter),
            bool(result.used_ai),
            float(result.rule_score),
            float(result.final_probability),
            str(result.reason),
        )

    score = 0.0
    score += 0.20 if 45 <= rsi <= 65 else 0.0
    score += 0.20 if macd_diff > 0 else 0.0
    score += 0.20 if disparity_20 > 0 else 0.0
    score += 0.15 if ema_gap > 0 else 0.0
    score += 0.10 if current_close > previous_close else 0.0
    score += 0.10 if volume_ratio >= 0.8 else 0.0
    score += 0.05 if atr_pct < 0.08 else 0.0
    return _finalize_entry(
        rule_score=score,
        ai_probability=ai_probability,
        threshold=entry_threshold,
        allow_rule_fallback=allow_rule_fallback,
        strategy_name="스윙",
    )


def scalping_exit(
    *,
    entry_price: float,
    current_price: float,
    highest_price: float,
    friction_rate: float,
    hard_stop: float,
    activation: float,
    initial_lock: float,
    step: float,
    take_profit: float,
) -> ExitDecision:
    if trading_engine is not None:
        result = trading_engine.evaluate_scalping_exit(
            entry_price,
            current_price,
            highest_price,
            friction_rate,
            hard_stop,
            activation,
            initial_lock,
            step,
            take_profit,
        )
        return ExitDecision(
            bool(result.should_exit),
            bool(result.trailing_active),
            float(result.lock_return),
            float(result.net_return),
            str(result.reason),
        )

    if entry_price <= 0 or current_price <= 0 or highest_price <= 0:
        return ExitDecision(False, False, 0.0, 0.0, "가격 입력 오류")
    net_return = current_price / entry_price - 1.0 - max(0.0, friction_rate)
    highest_net = highest_price / entry_price - 1.0 - max(0.0, friction_rate)
    if net_return <= -abs(hard_stop):
        return ExitDecision(True, False, 0.0, net_return, "손절 기준 도달")
    if net_return >= max(0.0, take_profit):
        return ExitDecision(True, highest_net >= activation, take_profit, net_return, "고정 익절 기준 도달")
    if highest_net < max(0.0, activation):
        return ExitDecision(False, False, 0.0, net_return, "보유")
    safe_step = max(abs(step), 0.000001)
    steps = max(0, int(math.floor((highest_net - max(0.0, activation)) / safe_step)))
    lock_return = max(0.0, initial_lock) + steps * safe_step
    if net_return <= lock_return:
        return ExitDecision(True, True, lock_return, net_return, "스텝업 트레일링 스탑 도달")
    return ExitDecision(False, True, lock_return, net_return, "트레일링 중")


def swing_exit(
    *,
    entry_price: float,
    current_price: float,
    highest_price: float,
    friction_rate: float,
    stop_loss: float,
    take_profit: float,
    trailing_activation: float,
    trailing_gap: float,
) -> ExitDecision:
    if trading_engine is not None:
        result = trading_engine.evaluate_swing_exit(
            entry_price,
            current_price,
            highest_price,
            friction_rate,
            stop_loss,
            take_profit,
            trailing_activation,
            trailing_gap,
        )
        return ExitDecision(
            bool(result.should_exit),
            bool(result.trailing_active),
            float(result.lock_return),
            float(result.net_return),
            str(result.reason),
        )

    if entry_price <= 0 or current_price <= 0 or highest_price <= 0:
        return ExitDecision(False, False, 0.0, 0.0, "가격 입력 오류")
    net_return = current_price / entry_price - 1.0 - max(0.0, friction_rate)
    highest_net = highest_price / entry_price - 1.0 - max(0.0, friction_rate)
    if net_return <= -abs(stop_loss):
        return ExitDecision(True, False, 0.0, net_return, "스윙 손절 기준 도달")
    if net_return >= max(0.0, take_profit):
        return ExitDecision(True, highest_net >= trailing_activation, take_profit, net_return, "스윙 목표수익률 도달")
    if highest_net >= max(0.0, trailing_activation):
        lock_return = highest_net - abs(trailing_gap)
        if net_return <= lock_return:
            return ExitDecision(True, True, lock_return, net_return, "스윙 트레일링 스탑 도달")
        return ExitDecision(False, True, lock_return, net_return, "스윙 트레일링 중")
    return ExitDecision(False, False, 0.0, net_return, "보유")


def calculate_position_size(
    *,
    cash: float,
    price: float,
    risk_per_trade: float,
    stop_loss_rate: float,
    max_positions: int,
    reserve_rate: float = 0.003,
) -> PositionSizeDecision:
    if trading_engine is not None:
        result = trading_engine.calculate_position_size(
            cash,
            price,
            risk_per_trade,
            stop_loss_rate,
            max_positions,
            reserve_rate,
        )
        return PositionSizeDecision(
            int(result.quantity),
            int(result.by_cash),
            int(result.by_risk),
            float(result.allocated_cash),
            float(result.risk_budget),
            str(result.reason),
        )

    if cash <= 0 or price <= 0 or risk_per_trade <= 0 or stop_loss_rate <= 0 or max_positions <= 0:
        return PositionSizeDecision(0, 0, 0, 0.0, 0.0, "수량 계산 입력값 오류")
    allocated = cash / max_positions
    risk_budget = cash * min(1.0, max(0.0, risk_per_trade))
    by_cash = int(allocated // (price * (1.0 + max(0.0, reserve_rate))))
    by_risk = int(risk_budget // (price * stop_loss_rate))
    quantity = max(0, min(by_cash, by_risk))
    return PositionSizeDecision(
        quantity,
        by_cash,
        by_risk,
        allocated,
        risk_budget,
        "주문 가능" if quantity > 0 else "현금 또는 위험예산 부족",
    )


def calculate_paper_fill(
    *,
    reference_price: float,
    quantity: int,
    is_buy: bool,
    fee_rate: float,
    slippage_rate: float,
) -> PaperFillDecision:
    if trading_engine is not None:
        result = trading_engine.calculate_paper_fill(
            reference_price, quantity, is_buy, fee_rate, slippage_rate
        )
        return PaperFillDecision(
            float(result.fill_price),
            float(result.gross_amount),
            float(result.fee_amount),
            float(result.cash_delta),
        )
    if reference_price <= 0 or quantity <= 0:
        raise ValueError("가격 또는 수량 오류")
    direction = 1.0 if is_buy else -1.0
    fill_price = reference_price * (1.0 + direction * max(0.0, slippage_rate))
    gross = fill_price * quantity
    fee = gross * max(0.0, fee_rate)
    cash_delta = -(gross + fee) if is_buy else gross - fee
    return PaperFillDecision(fill_price, gross, fee, cash_delta)


def calculate_trade_math(
    *,
    entry_price: float,
    exit_price: float,
    quantity: int,
    entry_fee: float,
    exit_fee: float,
) -> TradeMathDecision:
    if trading_engine is not None:
        result = trading_engine.calculate_trade_math(
            entry_price, exit_price, quantity, entry_fee, exit_fee
        )
        return TradeMathDecision(
            float(result.gross_pnl),
            float(result.total_fees),
            float(result.net_pnl),
            float(result.invested_amount),
            float(result.net_return),
        )
    if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
        raise ValueError("거래 손익 입력값 오류")
    gross_pnl = (exit_price - entry_price) * quantity
    total_fees = max(0.0, entry_fee) + max(0.0, exit_fee)
    net_pnl = gross_pnl - total_fees
    invested = entry_price * quantity + max(0.0, entry_fee)
    return TradeMathDecision(
        gross_pnl,
        total_fees,
        net_pnl,
        invested,
        net_pnl / invested if invested > 0 else 0.0,
    )
