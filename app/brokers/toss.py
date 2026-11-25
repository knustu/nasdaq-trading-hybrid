from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from ..config import AppConfig
from ..database import Database
from ..domain import OrderResult, StrategyType
from .base import BaseBroker

logger = logging.getLogger(__name__)


class TossLiveBroker(BaseBroker):
    """토스증권 Open API 어댑터.

    주문 POST는 네트워크 오류가 발생해도 자동 재전송하지 않는다. 서버에는 접수됐지만
    응답만 유실된 경우 중복 주문이 생길 수 있기 때문이다. 잔고/주문 상태 경로는 계정에
    제공된 최신 공식 명세를 확인한 뒤 .env에 입력해야 한다.
    """

    def __init__(self, db: Database, config: AppConfig):
        super().__init__(db)
        self.config = config
        if not config.live_ready():
            raise RuntimeError("실거래가 명시적으로 허용되지 않았거나 토스 인증정보가 없습니다.")
        if not config.toss_balance_path or not config.toss_order_status_path:
            raise RuntimeError(
                "실거래 안전을 위해 TOSS_BALANCE_PATH와 TOSS_ORDER_STATUS_PATH 설정이 필요합니다."
            )
        if "{order_id}" not in config.toss_order_status_path:
            raise RuntimeError("TOSS_ORDER_STATUS_PATH에는 {order_id} 자리표시자가 필요합니다.")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {config.toss_access_token}",
                "X-Tossinvest-Account": config.toss_account_seq,
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.config.toss_base_url}/{path.lstrip('/')}"

    @staticmethod
    def _find_number(payload: Any, keys: tuple[str, ...]) -> float | None:
        if isinstance(payload, dict):
            for key in keys:
                if key in payload:
                    try:
                        return float(payload[key])
                    except (TypeError, ValueError):
                        pass
            for value in payload.values():
                found = TossLiveBroker._find_number(value, keys)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = TossLiveBroker._find_number(value, keys)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _find_text(payload: Any, keys: tuple[str, ...]) -> str | None:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if value not in (None, ""):
                    return str(value)
            for value in payload.values():
                found = TossLiveBroker._find_text(value, keys)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = TossLiveBroker._find_text(value, keys)
                if found:
                    return found
        return None

    def available_balance(self, user_id: int) -> float:
        response = self.session.get(
            self._url(self.config.toss_balance_path), timeout=self.config.request_timeout_seconds
        )
        response.raise_for_status()
        amount = self._find_number(
            response.json(),
            ("availableUsdAmount", "available_usd_amount", "availableAmount", "cashBalance"),
        )
        if amount is None:
            raise RuntimeError("잔고 응답에서 주문 가능 금액을 찾지 못했습니다.")
        return amount

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
        created_at = datetime.now(timezone.utc).isoformat()
        if normalized_side not in {"BUY", "SELL"} or quantity <= 0 or reference_price <= 0:
            result = OrderResult(False, "REJECTED", symbol, normalized_side, quantity, message="주문값 오류")
            self._record_order_only(user_id, strategy_type, result, reference_price, reason, created_at)
            return result

        payload = {
            "symbol": symbol,
            "side": normalized_side,
            "orderType": "LIMIT",
            "quantity": quantity,
            "price": round(reference_price, 4),
        }

        try:
            # 중복 주문 위험 때문에 POST 자체는 단 한 번만 수행한다.
            response = self.session.post(
                self._url("orders"),
                json=payload,
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            order_id = self._find_text(body, ("orderId", "order_id", "id"))
            if not order_id:
                result = OrderResult(
                    False,
                    "UNKNOWN",
                    symbol,
                    normalized_side,
                    quantity,
                    message="주문 응답에서 주문 ID를 찾지 못했습니다. 증권사 앱에서 확인하세요.",
                )
            else:
                result = self._verify_order(order_id, symbol, normalized_side, quantity)
        except requests.Timeout:
            result = OrderResult(
                False,
                "UNKNOWN",
                symbol,
                normalized_side,
                quantity,
                message="주문 응답 시간 초과: 자동 재주문하지 않습니다. 증권사 앱에서 확인하세요.",
            )
        except Exception as exc:
            result = OrderResult(False, "REJECTED", symbol, normalized_side, quantity, message=str(exc))

        self._record_order_only(user_id, strategy_type, result, reference_price, reason, created_at)
        if result.success and result.status == "FILLED":
            try:
                self._sync_filled_order(user_id, strategy_type, result, reason, created_at)
            except Exception as exc:
                logger.critical("실거래는 체결됐지만 로컬 포지션 동기화 실패: %s", exc)
                return OrderResult(
                    False,
                    "UNKNOWN",
                    result.ticker,
                    result.side,
                    result.quantity,
                    fill_price=result.fill_price,
                    fee_amount=result.fee_amount,
                    broker_order_id=result.broker_order_id,
                    message=f"실거래 체결 후 로컬 동기화 실패: {exc}",
                )
        if result.status == "UNKNOWN":
            logger.critical(result.message)
        return result

    def _verify_order(self, order_id: str, ticker: str, side: str, quantity: int) -> OrderResult:
        path = self.config.toss_order_status_path.format(order_id=order_id)
        for _ in range(10):
            response = self.session.get(self._url(path), timeout=self.config.request_timeout_seconds)
            response.raise_for_status()
            body = response.json()
            status = (self._find_text(body, ("status", "orderStatus", "order_status")) or "").upper()
            if status in {"EXECUTED", "FILLED", "COMPLETED"}:
                price = self._find_number(body, ("averagePrice", "average_price", "filledPrice", "price"))
                if price is None or price <= 0:
                    return OrderResult(
                        False,
                        "UNKNOWN",
                        ticker,
                        side,
                        quantity,
                        broker_order_id=order_id,
                        message="체결 상태지만 체결가는 확인되지 않음",
                    )
                return OrderResult(True, "FILLED", ticker, side, quantity, price, broker_order_id=order_id)
            if status in {"REJECTED", "CANCELED", "CANCELLED", "EXPIRED"}:
                return OrderResult(False, status, ticker, side, quantity, broker_order_id=order_id, message="주문 미체결")
            time.sleep(0.5)
        return OrderResult(
            False,
            "UNKNOWN",
            ticker,
            side,
            quantity,
            broker_order_id=order_id,
            message="체결 상태 확인 시간 초과; 자동 재주문 금지",
        )

    def _record_order_only(
        self,
        user_id: int,
        strategy_type: StrategyType,
        result: OrderResult,
        reference_price: float,
        reason: str,
        created_at: str,
    ) -> None:
        try:
            with self.db.transaction(immediate=True) as conn:
                conn.execute(
                    """
                    INSERT INTO orders(
                        user_id, strategy_type, mode, broker_order_id, ticker, side, quantity,
                        requested_price, fill_price, fee_amount, status, message, created_at
                    ) VALUES (?, ?, 'LIVE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        strategy_type.value,
                        result.broker_order_id or None,
                        result.ticker,
                        result.side,
                        result.quantity,
                        reference_price,
                        result.fill_price or None,
                        result.fee_amount,
                        result.status,
                        f"{reason} | {result.message}",
                        created_at,
                    ),
                )
        except Exception as exc:
            logger.critical("실거래 주문 기록 저장 실패: %s", exc)

    def _sync_filled_order(
        self,
        user_id: int,
        strategy_type: StrategyType,
        result: OrderResult,
        reason: str,
        created_at: str,
    ) -> None:
        with self.db.transaction(immediate=True) as conn:
            if result.side == "BUY":
                existing = conn.execute(
                    "SELECT 1 FROM positions WHERE user_id = ? AND strategy_type = ? AND ticker = ?",
                    (user_id, strategy_type.value, result.ticker),
                ).fetchone()
                if existing:
                    raise RuntimeError("이미 같은 종목의 로컬 포지션이 존재합니다.")
                conn.execute(
                    """
                    INSERT INTO positions(
                        user_id, strategy_type, ticker, quantity, entry_price, highest_price,
                        entry_fee, opened_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        strategy_type.value,
                        result.ticker,
                        result.quantity,
                        result.fill_price,
                        result.fill_price,
                        result.fee_amount,
                        created_at,
                        created_at,
                    ),
                )
                return

            position = conn.execute(
                "SELECT * FROM positions WHERE user_id = ? AND strategy_type = ? AND ticker = ?",
                (user_id, strategy_type.value, result.ticker),
            ).fetchone()
            if position is None or int(position["quantity"]) != result.quantity:
                raise RuntimeError("로컬 포지션과 실계좌 매도 수량이 일치하지 않습니다.")
            fees = float(position["entry_fee"]) + result.fee_amount
            net_pnl = (result.fill_price - float(position["entry_price"])) * result.quantity - fees
            invested = float(position["entry_price"]) * result.quantity + float(position["entry_fee"])
            net_return = net_pnl / invested if invested > 0 else 0.0
            conn.execute(
                """
                INSERT INTO trades(
                    user_id, strategy_type, ticker, quantity, entry_price, exit_price,
                    fees, net_pnl, net_return, opened_at, closed_at, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    strategy_type.value,
                    result.ticker,
                    result.quantity,
                    float(position["entry_price"]),
                    result.fill_price,
                    fees,
                    net_pnl,
                    net_return,
                    position["opened_at"],
                    created_at,
                    reason,
                ),
            )
            conn.execute("DELETE FROM positions WHERE id = ?", (position["id"],))
