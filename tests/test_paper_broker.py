from pathlib import Path

from app.brokers.paper import PaperBroker
from app.database import Database
from app.domain import StrategyType
from app.user_manager import UserManager


def test_buy_and_sell_are_persistent(tmp_path: Path):
    db = Database(tmp_path / "paper.db")
    user = UserManager(db).register("paper_user", "Password123", 1000)
    broker = PaperBroker(db, fee_rate=0.001, slippage_rate=0.0)

    buy = broker.place_order(
        user_id=user.id,
        strategy_type=StrategyType.SCALPING,
        ticker="AAPL",
        side="BUY",
        quantity=2,
        reference_price=100,
        reason="test entry",
    )
    assert buy.success
    assert len(broker.list_positions(user.id, StrategyType.SCALPING)) == 1

    invalid_sell = broker.place_order(
        user_id=user.id,
        strategy_type=StrategyType.SCALPING,
        ticker="AAPL",
        side="SELL",
        quantity=3,
        reference_price=110,
        reason="too many",
    )
    assert not invalid_sell.success

    sell = broker.place_order(
        user_id=user.id,
        strategy_type=StrategyType.SCALPING,
        ticker="AAPL",
        side="SELL",
        quantity=2,
        reference_price=110,
        reason="test exit",
    )
    assert sell.success
    assert broker.list_positions(user.id, StrategyType.SCALPING) == []
    with db.connect() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE user_id = ?", (user.id,)).fetchone()
    assert trade is not None
    assert trade["net_pnl"] > 0


def test_strategy_change_is_blocked_while_position_is_open(tmp_path: Path):
    from app.domain import TradingMode, UserPreferences

    db = Database(tmp_path / "locked.db")
    manager = UserManager(db)
    user = manager.register("locked_user", "Password123", 1000)
    broker = PaperBroker(db, fee_rate=0.0, slippage_rate=0.0)
    broker.place_order(
        user_id=user.id,
        strategy_type=StrategyType.SCALPING,
        ticker="MSFT",
        side="BUY",
        quantity=1,
        reference_price=100,
        reason="open",
    )
    current = manager.get_preferences(user.id)
    try:
        manager.update_preferences(
            user.id,
            UserPreferences(
                strategy_type=StrategyType.SWING,
                trading_mode=TradingMode.PAPER,
                risk_per_trade=current.risk_per_trade,
                max_positions=current.max_positions,
                max_trades_per_day=current.max_trades_per_day,
            ),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("open position must block strategy change")
