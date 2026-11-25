#pragma once

#include <string>

struct EntryResult {
    bool should_enter = false;
    bool used_ai = false;
    double rule_score = 0.0;
    double final_probability = 0.0;
    std::string reason = "보유";
};

struct ExitResult {
    bool should_exit = false;
    bool trailing_active = false;
    double lock_return = 0.0;
    double net_return = 0.0;
    std::string reason = "보유";
};

struct PositionSizeResult {
    int quantity = 0;
    int by_cash = 0;
    int by_risk = 0;
    double allocated_cash = 0.0;
    double risk_budget = 0.0;
    std::string reason = "주문 가능";
};

struct PaperFillResult {
    double fill_price = 0.0;
    double gross_amount = 0.0;
    double fee_amount = 0.0;
    double cash_delta = 0.0;
};

struct TradeMathResult {
    double gross_pnl = 0.0;
    double total_fees = 0.0;
    double net_pnl = 0.0;
    double invested_amount = 0.0;
    double net_return = 0.0;
};

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
);

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
);

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
);

ExitResult evaluate_swing_exit(
    double entry_price,
    double current_price,
    double highest_price,
    double friction_rate,
    double stop_loss,
    double take_profit,
    double trailing_activation,
    double trailing_gap
);

PositionSizeResult calculate_position_size(
    double cash,
    double price,
    double risk_per_trade,
    double stop_loss_rate,
    int max_positions,
    double reserve_rate
);

PaperFillResult calculate_paper_fill(
    double reference_price,
    int quantity,
    bool is_buy,
    double fee_rate,
    double slippage_rate
);

TradeMathResult calculate_trade_math(
    double entry_price,
    double exit_price,
    int quantity,
    double entry_fee,
    double exit_fee
);

std::string engine_version();
