from app.cpp_adapter import (
    calculate_paper_fill,
    calculate_position_size,
    calculate_trade_math,
    engine_available,
    scalping_entry,
    swing_entry,
)


def test_cpp_engine_is_loaded():
    assert engine_available(), "C++ 엔진을 먼저 빌드해야 합니다: build_cpp.bat"


def test_scalping_entry_and_ai_blend():
    result = scalping_entry(
        rsi=55,
        macd_diff=1,
        ema_gap=1,
        vwap_dist=1,
        volume_ratio=1.5,
        bb_pband=0.6,
        disparity_5=1,
        ai_probability=0.90,
        entry_threshold=0.80,
        allow_rule_fallback=False,
    )
    assert result.used_ai
    assert result.should_enter
    assert result.rule_score == 1.0
    assert result.final_probability == 0.925


def test_swing_rule_fallback():
    result = swing_entry(
        rsi=55,
        macd_diff=1,
        disparity_20=1,
        ema_gap=1,
        current_close=110,
        previous_close=100,
        volume_ratio=1.0,
        atr_pct=0.03,
        ai_probability=None,
        entry_threshold=0.75,
        allow_rule_fallback=True,
    )
    assert not result.used_ai
    assert result.should_enter
    assert result.rule_score == 1.0


def test_position_size_is_limited_by_cash_and_risk():
    result = calculate_position_size(
        cash=10_000,
        price=100,
        risk_per_trade=0.01,
        stop_loss_rate=0.02,
        max_positions=2,
    )
    assert result.by_cash == 49
    assert result.by_risk == 50
    assert result.quantity == 49


def test_paper_fill_and_trade_math():
    buy = calculate_paper_fill(
        reference_price=100,
        quantity=2,
        is_buy=True,
        fee_rate=0.001,
        slippage_rate=0.001,
    )
    sell = calculate_paper_fill(
        reference_price=110,
        quantity=2,
        is_buy=False,
        fee_rate=0.001,
        slippage_rate=0.001,
    )
    result = calculate_trade_math(
        entry_price=buy.fill_price,
        exit_price=sell.fill_price,
        quantity=2,
        entry_fee=buy.fee_amount,
        exit_fee=sell.fee_amount,
    )
    assert buy.cash_delta < 0
    assert sell.cash_delta > 0
    assert result.net_pnl > 0
    assert result.net_return > 0
