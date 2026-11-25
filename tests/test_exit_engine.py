from app.cpp_adapter import scalping_exit, swing_exit


def test_scalping_hard_stop():
    result = scalping_exit(
        entry_price=100,
        current_price=98,
        highest_price=100,
        friction_rate=0,
        hard_stop=0.012,
        activation=0.015,
        initial_lock=0.008,
        step=0.004,
        take_profit=0.025,
    )
    assert result.should_exit
    assert "손절" in result.reason


def test_swing_trailing_stop():
    result = swing_exit(
        entry_price=100,
        current_price=106,
        highest_price=110,
        friction_rate=0,
        stop_loss=0.05,
        take_profit=0.12,
        trailing_activation=0.08,
        trailing_gap=0.03,
    )
    assert result.should_exit
    assert result.trailing_active
