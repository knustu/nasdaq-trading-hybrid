from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from .brokers import create_broker
from .config import CONFIG
from .cpp_adapter import calculate_position_size, engine_backend_name
from .data_feed import DataFeed
from .database import Database
from .domain import SignalAction, StrategyType, TradingMode, User
from .market_clock import ET, MarketClock
from .notifier import TelegramNotifier
from .scanner import MarketScanner
from .strategies import create_strategy
from .user_manager import UserManager

logger = logging.getLogger(__name__)
EventCallback = Callable[[str], None]


class TradingService:
    def __init__(
        self,
        db: Database,
        user: User,
        *,
        event_callback: EventCallback | None = None,
    ):
        self.db = db
        self.user = user
        self.user_manager = UserManager(db)
        self.data_feed = DataFeed()
        self.market_clock = MarketClock("NYSE")
        self.scanner = MarketScanner()
        self.notifier = TelegramNotifier(CONFIG.telegram_token, CONFIG.telegram_chat_id)
        self.event_callback = event_callback or (lambda _: None)
        self.stop_event = threading.Event()
        self.halted = False
        self._candidate_cache: tuple[str, StrategyType, list[str]] | None = None

    def emit(self, message: str) -> None:
        logger.info(message)
        self.event_callback(message)

    def stop(self) -> None:
        self.stop_event.set()

    def run_forever(self) -> None:
        self.stop_event.clear()
        self.halted = False
        self.emit(f"자동매매 반복 실행을 시작합니다. 계산 엔진: {engine_backend_name()}")
        if CONFIG.restrict_entry_to_regular_session:
            self.emit("진입 시간 제한이 활성화되어 정규장에서만 신규 진입합니다.")
        else:
            self.emit("진입 시간 제한 해제: 정규장·프리마켓·애프터마켓에서 새 봉과 진입 확률만으로 판단합니다.")
        while not self.stop_event.is_set() and not self.halted:
            try:
                wait_seconds = self.run_cycle()
            except Exception as exc:
                logger.exception("거래 사이클 오류")
                self.emit(f"오류 발생: {exc}")
                wait_seconds = 30
            self.stop_event.wait(max(1, wait_seconds))
        self.emit("자동매매 실행이 중단되었습니다.")

    def run_cycle(self) -> int:
        preferences = self.user_manager.get_preferences(self.user.id)
        settings = self.user_manager.get_strategy_settings(self.user.id, preferences.strategy_type)
        broker = create_broker(self.db, preferences.trading_mode)
        friction = (
            CONFIG.paper_fee_rate * 2 + CONFIG.paper_slippage_rate * 2
            if preferences.trading_mode is TradingMode.PAPER
            else 0.0022
        )
        strategy = create_strategy(
            preferences.strategy_type,
            settings,
            allow_rule_fallback=preferences.trading_mode is TradingMode.PAPER,
            friction_rate=friction,
        )
        market = self.market_clock.state()

        positions = broker.list_positions(self.user.id, preferences.strategy_type)
        for position in positions:
            frame = self.data_feed.fetch(
                position.ticker,
                period=strategy.period,
                interval=strategy.interval,
                prepost=True,
            )
            if frame.empty or not self.data_feed.is_fresh(frame, max_age_minutes=strategy.freshness_minutes):
                self.emit(f"{position.ticker}: 가격 데이터가 오래되었거나 비어 있어 청산 판단을 보류합니다.")
                continue
            current = self.data_feed.latest_price(frame)
            highest = max(position.highest_price, float(frame["high"].iloc[-1]), current)
            broker.update_highest(position.id, highest)
            signal = strategy.evaluate_exit(
                position,
                current_price=current,
                highest_price=highest,
                now_et=market.now_et,
                minutes_to_close=(
                    self.market_clock.minutes_to_close(market.now_et)
                    if market.is_regular_session
                    else None
                ),
            )
            net_return = current / position.entry_price - 1.0 - friction
            self.emit(
                f"{position.ticker} 보유중 | 현재 ${current:,.2f} | 추정 순수익률 {net_return:+.2%} | {signal.reason}"
            )
            if signal.action is SignalAction.SELL:
                result = broker.place_order(
                    user_id=self.user.id,
                    strategy_type=preferences.strategy_type,
                    ticker=position.ticker,
                    side="SELL",
                    quantity=position.quantity,
                    reference_price=current,
                    reason=signal.reason,
                )
                self.emit(self._format_order_result(result))
                if result.status == "UNKNOWN":
                    self.halted = True
                    self.notifier.send(f"긴급 중단: {position.ticker} 주문 상태를 확인할 수 없습니다.")
                    return strategy.polling_seconds

        positions = broker.list_positions(self.user.id, preferences.strategy_type)
        if len(positions) >= preferences.max_positions:
            return strategy.polling_seconds

        if not self._entry_session_allowed(market):
            if not market.is_trading_day:
                self.emit(f"{market.now_et:%Y-%m-%d}은 미국 증시 거래일이 아니어서 신규 진입을 보류합니다.")
            else:
                self.emit(f"정규장 시간이 아니어서 신규 진입을 보류합니다. 현재 뉴욕시간 {market.now_et:%H:%M:%S %Z}")
            return strategy.polling_seconds

        start_et = datetime.combine(market.now_et.date(), time.min, tzinfo=ET).astimezone(timezone.utc)
        filled_buys = broker.count_filled_buys_since(self.user.id, start_et)
        if filled_buys >= preferences.max_trades_per_day:
            self.emit("오늘의 최대 매수 횟수에 도달했습니다.")
            return strategy.polling_seconds

        candidates = self._get_candidates(preferences.strategy_type, market.now_et)
        held_symbols = {position.ticker for position in positions}
        for ticker in candidates:
            if ticker in held_symbols:
                continue
            if len(positions) >= preferences.max_positions:
                break
            if filled_buys >= preferences.max_trades_per_day:
                break

            frame = self.data_feed.fetch(
                ticker,
                period=strategy.period,
                interval=strategy.interval,
                prepost=True,
            )
            if frame.empty or not self.data_feed.is_fresh(frame, max_age_minutes=strategy.freshness_minutes):
                continue
            if not self.data_feed.is_new_bar(ticker, strategy.interval, frame):
                continue
            current = self.data_feed.latest_price(frame)
            signal = strategy.evaluate_entry(frame)
            self.emit(f"{ticker} 진입 분석 {signal.confidence:.1%} | {signal.reason}")
            if signal.action is not SignalAction.BUY:
                continue

            cash = broker.available_balance(self.user.id)
            size = calculate_position_size(
                cash=cash,
                price=current,
                risk_per_trade=preferences.risk_per_trade,
                stop_loss_rate=strategy.stop_loss_rate,
                max_positions=preferences.max_positions,
                reserve_rate=0.003,
            )
            quantity = size.quantity
            if quantity <= 0:
                self.emit(f"{ticker}: 주문 가능한 수량이 없습니다. {size.reason}")
                continue
            result = broker.place_order(
                user_id=self.user.id,
                strategy_type=preferences.strategy_type,
                ticker=ticker,
                side="BUY",
                quantity=quantity,
                reference_price=current,
                reason=signal.reason,
            )
            self.emit(self._format_order_result(result))
            if result.success:
                positions = broker.list_positions(self.user.id, preferences.strategy_type)
                filled_buys += 1
                self.notifier.send(
                    f"{preferences.strategy_type.value} 매수 체결: {ticker} {quantity}주 @ ${result.fill_price:,.2f}"
                )
            elif result.status == "UNKNOWN":
                self.halted = True
                self.notifier.send(f"긴급 중단: {ticker} 주문 상태를 확인할 수 없습니다.")
                break

        return strategy.polling_seconds

    def _get_candidates(self, strategy_type: StrategyType, now_et: datetime) -> list[str]:
        date_key = now_et.strftime("%Y-%m-%d")
        if self._candidate_cache and self._candidate_cache[:2] == (date_key, strategy_type):
            return self._candidate_cache[2]
        candidates = self.scanner.scan(strategy_type, limit=10)
        self._candidate_cache = (date_key, strategy_type, candidates)
        self.emit(f"{strategy_type.value} 후보 종목: {', '.join(candidates)}")
        return candidates

    @staticmethod
    def _entry_session_allowed(market) -> bool:
        """기본값은 시간 제한 없음. 환경변수로 정규장 전용을 다시 켤 수 있습니다."""
        return market.is_regular_session or not CONFIG.restrict_entry_to_regular_session

    @staticmethod
    def _format_order_result(result) -> str:
        if result.success:
            return (
                f"{result.status}: {result.ticker} {result.side} {result.quantity}주 "
                f"@ ${result.fill_price:,.4f} | 비용 ${result.fee_amount:,.2f}"
            )
        return f"{result.status}: {result.ticker} {result.side} 실패 | {result.message}"
