#include "engine.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace {
constexpr double kNoAiProbability = -0.5;

double clamp01(double value) {
    if (!std::isfinite(value)) {
        return 0.0;
    }
    return std::clamp(value, 0.0, 1.0);
}

bool has_ai_probability(double value) {
    return std::isfinite(value) && value >= 0.0 && value <= 1.0;
}

EntryResult finalize_entry(
    double rule_score,
    double ai_probability,
    double threshold,
    bool allow_rule_fallback,
    const std::string& strategy_name
) {
    EntryResult result;
    result.rule_score = clamp01(rule_score);
    const double safe_threshold = clamp01(threshold);

    if (has_ai_probability(ai_probability)) {
        result.used_ai = true;
        result.final_probability = clamp01(ai_probability * 0.75 + result.rule_score * 0.25);
        result.should_enter = result.final_probability >= safe_threshold;
        result.reason = strategy_name + (result.should_enter ? " 진입 승인: AI+규칙 결합" : " 기준 미달: AI+규칙 결합");
        return result;
    }

    if (!allow_rule_fallback) {
        result.used_ai = false;
        result.final_probability = 0.0;
        result.should_enter = false;
        result.reason = "검증된 AI 모델이 없어 진입 차단";
        return result;
    }

    result.used_ai = false;
    result.final_probability = result.rule_score;
    result.should_enter = result.final_probability >= safe_threshold;
    result.reason = strategy_name + (result.should_enter ? " 진입 승인: 규칙 기반 PAPER 판단" : " 기준 미달: 규칙 기반 PAPER 판단");
    return result;
}

bool invalid_prices(double entry_price, double current_price, double highest_price) {
    return !std::isfinite(entry_price) || !std::isfinite(current_price) || !std::isfinite(highest_price)
        || entry_price <= 0.0 || current_price <= 0.0 || highest_price <= 0.0;
}
}

EntryResult evaluate_scalping_entry(
    double rsi,
    double macd_diff,
    double ema_gap,
    double vwap_dist,
    double volume_ratio,
    double bb_pband,
    double disparity_5,
    double ai_probability,
    double entry_threshold,
    bool allow_rule_fallback
) {
    double score = 0.0;
    score += (rsi >= 48.0 && rsi <= 68.0) ? 0.20 : 0.0;
    score += macd_diff > 0.0 ? 0.20 : 0.0;
    score += ema_gap > 0.0 ? 0.15 : 0.0;
    score += vwap_dist > 0.0 ? 0.15 : 0.0;
    score += volume_ratio >= 1.2 ? 0.15 : 0.0;
    score += (bb_pband >= 0.35 && bb_pband <= 0.95) ? 0.10 : 0.0;
    score += disparity_5 > 0.0 ? 0.05 : 0.0;
    return finalize_entry(score, ai_probability, entry_threshold, allow_rule_fallback, "스캘핑");
}

EntryResult evaluate_swing_entry(
    double rsi,
    double macd_diff,
    double disparity_20,
    double ema_gap,
    double current_close,
    double previous_close,
    double volume_ratio,
    double atr_pct,
    double ai_probability,
    double entry_threshold,
    bool allow_rule_fallback
) {
    double score = 0.0;
    score += (rsi >= 45.0 && rsi <= 65.0) ? 0.20 : 0.0;
    score += macd_diff > 0.0 ? 0.20 : 0.0;
    score += disparity_20 > 0.0 ? 0.20 : 0.0;
    score += ema_gap > 0.0 ? 0.15 : 0.0;
    score += current_close > previous_close ? 0.10 : 0.0;
    score += volume_ratio >= 0.8 ? 0.10 : 0.0;
    score += atr_pct < 0.08 ? 0.05 : 0.0;
    return finalize_entry(score, ai_probability, entry_threshold, allow_rule_fallback, "스윙");
}

ExitResult evaluate_scalping_exit(
    double entry_price,
    double current_price,
    double highest_price,
    double friction_rate,
    double hard_stop,
    double activation,
    double initial_lock,
    double step,
    double take_profit
) {
    ExitResult result;
    if (invalid_prices(entry_price, current_price, highest_price)) {
        result.reason = "가격 입력 오류";
        return result;
    }

    result.net_return = current_price / entry_price - 1.0 - std::max(0.0, friction_rate);
    const double highest_net = highest_price / entry_price - 1.0 - std::max(0.0, friction_rate);

    if (result.net_return <= -std::abs(hard_stop)) {
        result.should_exit = true;
        result.reason = "손절 기준 도달";
        return result;
    }
    if (result.net_return >= std::max(0.0, take_profit)) {
        result.should_exit = true;
        result.trailing_active = highest_net >= std::max(0.0, activation);
        result.lock_return = std::max(0.0, take_profit);
        result.reason = "고정 익절 기준 도달";
        return result;
    }
    if (highest_net < std::max(0.0, activation)) {
        result.reason = "보유";
        return result;
    }

    result.trailing_active = true;
    const double safe_step = std::max(std::abs(step), 0.000001);
    const int steps = std::max(0, static_cast<int>(std::floor((highest_net - std::max(0.0, activation)) / safe_step)));
    result.lock_return = std::max(0.0, initial_lock) + static_cast<double>(steps) * safe_step;
    if (result.net_return <= result.lock_return) {
        result.should_exit = true;
        result.reason = "스텝업 트레일링 스탑 도달";
    } else {
        result.reason = "트레일링 중";
    }
    return result;
}

ExitResult evaluate_swing_exit(
    double entry_price,
    double current_price,
    double highest_price,
    double friction_rate,
    double stop_loss,
    double take_profit,
    double trailing_activation,
    double trailing_gap
) {
    ExitResult result;
    if (invalid_prices(entry_price, current_price, highest_price)) {
        result.reason = "가격 입력 오류";
        return result;
    }

    result.net_return = current_price / entry_price - 1.0 - std::max(0.0, friction_rate);
    const double highest_net = highest_price / entry_price - 1.0 - std::max(0.0, friction_rate);

    if (result.net_return <= -std::abs(stop_loss)) {
        result.should_exit = true;
        result.reason = "스윙 손절 기준 도달";
        return result;
    }
    if (result.net_return >= std::max(0.0, take_profit)) {
        result.should_exit = true;
        result.trailing_active = highest_net >= std::max(0.0, trailing_activation);
        result.lock_return = std::max(0.0, take_profit);
        result.reason = "스윙 목표수익률 도달";
        return result;
    }
    if (highest_net >= std::max(0.0, trailing_activation)) {
        result.trailing_active = true;
        result.lock_return = highest_net - std::abs(trailing_gap);
        if (result.net_return <= result.lock_return) {
            result.should_exit = true;
            result.reason = "스윙 트레일링 스탑 도달";
        } else {
            result.reason = "스윙 트레일링 중";
        }
    }
    return result;
}

PositionSizeResult calculate_position_size(
    double cash,
    double price,
    double risk_per_trade,
    double stop_loss_rate,
    int max_positions,
    double reserve_rate
) {
    PositionSizeResult result;
    if (!std::isfinite(cash) || !std::isfinite(price) || !std::isfinite(risk_per_trade)
        || !std::isfinite(stop_loss_rate) || cash <= 0.0 || price <= 0.0
        || risk_per_trade <= 0.0 || stop_loss_rate <= 0.0 || max_positions <= 0) {
        result.reason = "수량 계산 입력값 오류";
        return result;
    }

    result.allocated_cash = cash / static_cast<double>(max_positions);
    result.risk_budget = cash * std::clamp(risk_per_trade, 0.0, 1.0);
    const double reserved_price = price * (1.0 + std::max(0.0, reserve_rate));
    result.by_cash = static_cast<int>(std::floor(result.allocated_cash / reserved_price));
    result.by_risk = static_cast<int>(std::floor(result.risk_budget / (price * stop_loss_rate)));
    result.quantity = std::max(0, std::min(result.by_cash, result.by_risk));
    result.reason = result.quantity > 0 ? "주문 가능" : "현금 또는 위험예산 부족";
    return result;
}

PaperFillResult calculate_paper_fill(
    double reference_price,
    int quantity,
    bool is_buy,
    double fee_rate,
    double slippage_rate
) {
    if (!std::isfinite(reference_price) || reference_price <= 0.0 || quantity <= 0) {
        throw std::invalid_argument("가격 또는 수량 오류");
    }
    PaperFillResult result;
    const double safe_fee = std::max(0.0, fee_rate);
    const double safe_slippage = std::max(0.0, slippage_rate);
    const double direction = is_buy ? 1.0 : -1.0;
    result.fill_price = reference_price * (1.0 + direction * safe_slippage);
    result.gross_amount = result.fill_price * static_cast<double>(quantity);
    result.fee_amount = result.gross_amount * safe_fee;
    result.cash_delta = is_buy
        ? -(result.gross_amount + result.fee_amount)
        : (result.gross_amount - result.fee_amount);
    return result;
}

TradeMathResult calculate_trade_math(
    double entry_price,
    double exit_price,
    int quantity,
    double entry_fee,
    double exit_fee
) {
    if (!std::isfinite(entry_price) || !std::isfinite(exit_price) || entry_price <= 0.0
        || exit_price <= 0.0 || quantity <= 0) {
        throw std::invalid_argument("거래 손익 입력값 오류");
    }
    TradeMathResult result;
    result.gross_pnl = (exit_price - entry_price) * static_cast<double>(quantity);
    result.total_fees = std::max(0.0, entry_fee) + std::max(0.0, exit_fee);
    result.net_pnl = result.gross_pnl - result.total_fees;
    result.invested_amount = entry_price * static_cast<double>(quantity) + std::max(0.0, entry_fee);
    result.net_return = result.invested_amount > 0.0 ? result.net_pnl / result.invested_amount : 0.0;
    return result;
}

std::string engine_version() {
    return "2.0.1-hybrid";
}
