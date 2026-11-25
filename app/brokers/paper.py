from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..cpp_adapter import calculate_paper_fill, calculate_trade_math
from ..database import Database
from ..domain import OrderResult, StrategyType
from .base import BaseBroker

logger = logging.getLogger(__name__)


class PaperBroker(BaseBroker):
    """SQLite 상태 관리는 Python, 가격·수수료·손익 산술은 C++ 엔진이 담당한다."""

    def __init__(self, db: Database, *, fee_rate: float, slippage_rate: float):
        super().__init__(db)
        self.fee_rate = max(0.0, fee_rate)
        self.slippage_rate = max(0.0, slippage_rate)

    def available_balance(self, user_id: int) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT cash FROM paper_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
        return float(row["cash"] if row else 0.0)

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
        symbol = ticker.upper().strip()
        normalized_side = side.upper().strip()
        if normalized_side not in {"BUY", "SELL"}:
            return OrderResult(False, "REJECTED", symbol, normalized_side, quantity, message="잘못된 주문 방향")
        if quantity <= 0 or reference_price <= 0:
            return OrderResult(False, "REJECTED", symbol, normalized_side, quantity, message="수량 또는 가격 오류")

        fill = calculate_paper_fill(
            reference_price=reference_price,
            quantity=quantity,
            is_buy=normalized_side == "BUY",
            fee_rate=self.fee_rate,
            slippage_rate=self.slippage_rate,
        )
        fill_price = round(fill.fill_price, 6)
        gross_amount = fill.gross_amount
        fee = fill.fee_amount
        now = datetime.now(timezone.utc).isoformat()

        try:
            with self.db.transaction(immediate=True) as conn:
                account = conn.execute(
                    "SELECT cash FROM paper_accounts WHERE user_id = ?", (user_id,)
                ).fetchone()
                if account is None:
                    raise RuntimeError("모의 계좌가 없습니다.")
                cash = float(account["cash"])

                if normalized_side == "BUY":
                    existing = conn.execute(
                        """
                        SELECT 1 FROM positions
                        WHERE user_id = ? AND strategy_type = ? AND ticker = ?
                        """,
                        (user_id, strategy_type.value, symbol),
                    ).fetchone()
                    if existing:
                        raise ValueError("이미 보유 중인 종목은 추가 매수하지 않습니다.")
                    total_cost = -fill.cash_delta
                    if cash + 1e-9 < total_cost:
                        raise ValueError(f"모의 잔고 부족: 필요 ${total_cost:,.2f}, 보유 ${cash:,.2f}")
                    conn.execute(
                        "UPDATE paper_accounts SET cash = ?, updated_at = ? WHERE user_id = ?",
                        (cash + fill.cash_delta, now, user_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO positions(
                            user_id, strategy_type, ticker, quantity, entry_price,
                            highest_price, entry_fee, opened_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            strategy_type.value,
                            symbol,
                            quantity,
                            fill_price,
                            fill_price,
                            fee,
                            now,
                            now,
                        ),
                    )
                else:
                    position = conn.execute(
                        """
                        SELECT * FROM positions
                        WHERE user_id = ? AND strategy_type = ? AND ticker = ?
                        """,
                        (user_id, strategy_type.value, symbol),
                    ).fetchone()
                    if position is None:
                        raise ValueError("보유하지 않은 종목은 매도할 수 없습니다.")
                    held = int(position["quantity"])
                    if quantity > held:
                        raise ValueError(f"보유수량 부족: 주문 {quantity}주, 보유 {held}주")

                    conn.execute(
                        "UPDATE paper_accounts SET cash = ?, updated_at = ? WHERE user_id = ?",
                        (cash + fill.cash_delta, now, user_id),
                    )
                    entry_fee = float(position["entry_fee"]) * (quantity / held)
                    math_result = calculate_trade_math(
                        entry_price=float(position["entry_price"]),
                        exit_price=fill_price,
                        quantity=quantity,
                        entry_fee=entry_fee,
                        exit_fee=fee,
                    )
                    conn.execute(
                        """
                        INSERT INTO trades(
                            user_id, strategy_type, ticker, quantity, entry_price,
                            exit_price, fees, net_pnl, net_return, opened_at, closed_at, exit_reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            strategy_type.value,
                            symbol,
                            quantity,
                            float(position["entry_price"]),
                            fill_price,
                            math_result.total_fees,
                            math_result.net_pnl,
                            math_result.net_return,
                            position["opened_at"],
                            now,
                            reason,
                        ),
                    )
                    if quantity == held:
                        conn.execute("DELETE FROM positions WHERE id = ?", (position["id"],))
                    else:
                        conn.execute(
                            """
                            UPDATE positions SET quantity = ?, entry_fee = ?, updated_at = ? WHERE id = ?
                            """,
                            (held - quantity, float(position["entry_fee"]) - entry_fee, now, position["id"]),
                        )

                conn.execute(
                    """
                    INSERT INTO orders(
                        user_id, strategy_type, mode, ticker, side, quantity,
                        requested_price, fill_price, fee_amount, status, message, created_at
                    ) VALUES (?, ?, 'PAPER', ?, ?, ?, ?, ?, ?, 'FILLED', ?, ?)
                    """,
                    (
                        user_id,
                        strategy_type.value,
                        symbol,
                        normalized_side,
                        quantity,
                        reference_price,
                        fill_price,
                        fee,
                        reason,
                        now,
                    ),
                )
            logger.info("[PAPER/C++] %s %s %s주 @ %.4f", symbol, normalized_side, quantity, fill_price)
            return OrderResult(True, "FILLED", symbol, normalized_side, quantity, fill_price, fee, message=reason)
        except Exception as exc:
            logger.warning("[PAPER] 주문 거절: %s", exc)
            self._record_rejection(
                user_id, strategy_type, symbol, normalized_side, quantity, reference_price, str(exc)
            )
            return OrderResult(False, "REJECTED", symbol, normalized_side, quantity, message=str(exc))

    def _record_rejection(
        self,
        user_id: int,
        strategy_type: StrategyType,
        ticker: str,
        side: str,
        quantity: int,
        requested_price: float,
        message: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO orders(
                    user_id, strategy_type, mode, ticker, side, quantity,
                    requested_price, status, message, created_at
                ) VALUES (?, ?, 'PAPER', ?, ?, ?, ?, 'REJECTED', ?, ?)
                """,
                (user_id, strategy_type.value, ticker, side, quantity, requested_price, message, now),
            )

    def reset_account(self, user_id: int) -> None:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT initial_cash FROM paper_accounts WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None:
                raise KeyError("모의 계좌가 없습니다.")
            conn.execute("DELETE FROM positions WHERE user_id = ?", (user_id,))
            conn.execute(
                "UPDATE paper_accounts SET cash = ?, updated_at = ? WHERE user_id = ?",
                (float(row["initial_cash"]), datetime.now(timezone.utc).isoformat(), user_id),
            )
