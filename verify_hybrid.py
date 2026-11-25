from app.cpp_adapter import (
    calculate_position_size,
    engine_backend_name,
    require_cpp_engine,
    scalping_entry,
)


def main() -> None:
    require_cpp_engine()
    entry = scalping_entry(
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
    size = calculate_position_size(
        cash=10_000,
        price=100,
        risk_per_trade=0.01,
        stop_loss_rate=0.02,
        max_positions=2,
    )
    print(f"backend={engine_backend_name()}")
    print(f"entry={entry.should_enter}, probability={entry.final_probability:.4f}")
    print(f"quantity={size.quantity}, by_cash={size.by_cash}, by_risk={size.by_risk}")
    print("HYBRID_ENGINE_OK")


if __name__ == "__main__":
    main()
