from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..database import Database
from ..domain import OrderResult, Position, StrategyType


class BaseBroker(ABC):
    def __init__(self, db: Database):
        self.db = db

    @abstractmethod
    def available_balance(self, user_id: int) -> float:
        raise NotImplementedError

    @abstractmethod
    def place_order(
        self,
        *,
        user_id: int,
        strategy_type: StrategyType,
        ticker: str,
        side: str,
        quantity: int,
        reference_price: float,
        reason: str,
    ) -> OrderResult:
        raise NotImplementedError

    def list_positions(self, user_id: int, strategy_type: StrategyType) -> list[Position]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE user_id = ? AND strategy_type = ? ORDER BY opened_at",
                (user_id, strategy_type.value),
            ).fetchall()
        result: list[Position] = []
        for row in rows:
            opened = datetime.fromisoformat(row["opened_at"])
            if opened.tzinfo is None:
                opened = opened.replace(tzinfo=timezone.utc)
            result.append(
                Position(
                    id=int(row["id"]),
                    user_id=int(row["user_id"]),
                    strategy_type=StrategyType(row["strategy_type"]),
                    ticker=str(row["ticker"]),
                    quantity=int(row["quantity"]),
                    entry_price=float(row["entry_price"]),
                    highest_price=float(row["highest_price"]),
                    opened_at=opened,
                )
            )
        return result

    def update_highest(self, position_id: int, price: float) -> None:
        if price <= 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                UPDATE positions
                SET highest_price = MAX(highest_price, ?), updated_at = ?
                WHERE id = ?
                """,
                (price, now, position_id),
            )

    def count_filled_buys_since(self, user_id: int, since_utc: datetime) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM orders
                WHERE user_id = ? AND side = 'BUY' AND status = 'FILLED' AND created_at >= ?
                """,
                (user_id, since_utc.astimezone(timezone.utc).isoformat()),
            ).fetchone()
        return int(row["count"] if row else 0)
