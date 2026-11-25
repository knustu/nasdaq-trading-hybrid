from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.ai_analyzer import AIAnalyzer
from app.config import CONFIG, MODEL_DIR
from app.data_feed import DataFeed
from app.domain import Position, SignalAction, StrategySettings, StrategyType
from app.strategies.scalping import ScalpingStrategy
from app.strategies.swing import SwingStrategy
from app.user_manager import DEFAULT_SETTINGS


@dataclass
class BacktestTrade:
    ticker: str
    strategy: str
    opened_at: str
    closed_at: str
    entry_price: float
    exit_price: float
    quantity: int
    net_pnl: float
    net_return: float
    exit_reason: str


class StrategyBacktester:
    def __init__(
        self,
        strategy_type: StrategyType,
        initial_cash: float,
        fee_rate: float,
        slippage_rate: float,
    ):
        self.strategy_type = strategy_type
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        settings = DEFAULT_SETTINGS[strategy_type]
        if strategy_type is StrategyType.SCALPING:
            analyzer = AIAnalyzer(
                MODEL_DIR / "scalping_xgb_model.json",
                expected_interval="1m",
                strategy_type="SCALPING",
            )
            self.strategy = ScalpingStrategy(
                settings,
                analyzer,
                allow_rule_fallback=True,
                friction_rate=(fee_rate + slippage_rate) * 2,
            )
        else:
            analyzer = AIAnalyzer(
                MODEL_DIR / "swing_xgb_model.json",
                expected_interval="1h",
                strategy_type="SWING",
            )
            self.strategy = SwingStrategy(
                settings,
                analyzer,
                allow_rule_fallback=True,
                friction_rate=(fee_rate + slippage_rate) * 2,
            )
        self.trades: list[BacktestTrade] = []

    def run(self, ticker: str, frame: pd.DataFrame) -> dict[str, float]:
        position: Position | None = None
        entry_fee = 0.0
        for index in range(50, len(frame)):
            history = frame.iloc[: index + 1]
            bar = frame.iloc[index]
            timestamp = pd.Timestamp(frame.index[index])
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize("UTC")
            now = timestamp.to_pydatetime()

            if position is None:
                signal = self.strategy.evaluate_entry(history)
                if signal.action is not SignalAction.BUY:
                    continue
                reference = float(bar["close"])
                fill = reference * (1 + self.slippage_rate)
                risk_budget = self.cash * 0.01
                by_risk = int(risk_budget // (fill * self.strategy.stop_loss_rate))
                by_cash = int(self.cash // (fill * (1 + self.fee_rate)))
                quantity = max(0, min(by_risk, by_cash))
                if quantity <= 0:
                    continue
                entry_fee = fill * quantity * self.fee_rate
                self.cash -= fill * quantity + entry_fee
                position = Position(
                    id=-1,
                    user_id=-1,
                    strategy_type=self.strategy_type,
                    ticker=ticker,
                    quantity=quantity,
                    entry_price=fill,
                    highest_price=fill,
                    opened_at=now.astimezone(timezone.utc),
                )
                continue

            prior_highest = position.highest_price
            low_price = float(bar["low"])
            high_price = float(bar["high"])
            close_price = float(bar["close"])

            # 보수적 가정: 같은 봉 안에서 손절 조건을 먼저 확인한다.
            signal = self.strategy.evaluate_exit(
                position,
                current_price=low_price,
                highest_price=prior_highest,
                now_et=now,
                minutes_to_close=None,
            )
            exit_price: float | None = None
            if signal.action is SignalAction.SELL:
                exit_price = low_price * (1 - self.slippage_rate)
            else:
                updated_highest = max(prior_highest, high_price)
                position = Position(
                    id=position.id,
                    user_id=position.user_id,
                    strategy_type=position.strategy_type,
                    ticker=position.ticker,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    highest_price=updated_highest,
                    opened_at=position.opened_at,
                )
                # 고가에서 트레일링이 활성화된 후 저가까지 밀린 상황도 보수적으로 검사한다.
                signal = self.strategy.evaluate_exit(
                    position,
                    current_price=low_price,
                    highest_price=updated_highest,
                    now_et=now,
                    minutes_to_close=None,
                )
                if signal.action is SignalAction.SELL:
                    exit_price = low_price * (1 - self.slippage_rate)
                else:
                    signal = self.strategy.evaluate_exit(
                        position,
                        current_price=close_price,
                        highest_price=updated_highest,
                        now_et=now,
                        minutes_to_close=None,
                    )
                    if signal.action is SignalAction.SELL:
                        exit_price = close_price * (1 - self.slippage_rate)

            if exit_price is not None:
                self._close(position, exit_price, entry_fee, now, signal.reason)
                position = None
                entry_fee = 0.0

        if position is not None:
            final_time = pd.Timestamp(frame.index[-1])
            if final_time.tzinfo is None:
                final_time = final_time.tz_localize("UTC")
            final_price = float(frame["close"].iloc[-1]) * (1 - self.slippage_rate)
            self._close(position, final_price, entry_fee, final_time.to_pydatetime(), "백테스트 종료 청산")

        return self.metrics()

    def _close(
        self,
        position: Position,
        exit_price: float,
        entry_fee: float,
        closed_at: datetime,
        reason: str,
    ) -> None:
        exit_fee = exit_price * position.quantity * self.fee_rate
        proceeds = exit_price * position.quantity - exit_fee
        self.cash += proceeds
        net_pnl = (exit_price - position.entry_price) * position.quantity - entry_fee - exit_fee
        invested = position.entry_price * position.quantity + entry_fee
        net_return = net_pnl / invested if invested else 0.0
        self.trades.append(
            BacktestTrade(
                ticker=position.ticker,
                strategy=position.strategy_type.value,
                opened_at=position.opened_at.isoformat(),
                closed_at=closed_at.isoformat(),
                entry_price=position.entry_price,
                exit_price=exit_price,
                quantity=position.quantity,
                net_pnl=net_pnl,
                net_return=net_return,
                exit_reason=reason,
            )
        )

    def metrics(self) -> dict[str, float]:
        if not self.trades:
            return {
                "trades": 0.0,
                "final_cash": self.cash,
                "total_return": self.cash / self.initial_cash - 1.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
            }
        returns = pd.Series([trade.net_return for trade in self.trades], dtype=float)
        pnl = pd.Series([trade.net_pnl for trade in self.trades], dtype=float)
        equity = self.initial_cash + pnl.cumsum()
        drawdown = equity / equity.cummax() - 1.0
        gross_profit = pnl[pnl > 0].sum()
        gross_loss = abs(pnl[pnl < 0].sum())
        return {
            "trades": float(len(self.trades)),
            "final_cash": self.cash,
            "total_return": self.cash / self.initial_cash - 1.0,
            "win_rate": float((returns > 0).mean()),
            "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
            "max_drawdown": float(drawdown.min()),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["SCALPING", "SWING"], required=True)
    parser.add_argument("--ticker", default="TQQQ")
    parser.add_argument("--cash", type=float, default=10_000)
    parser.add_argument("--output", default="data/backtest_trades.csv")
    args = parser.parse_args()

    strategy_type = StrategyType(args.strategy)
    feed = DataFeed()
    if strategy_type is StrategyType.SCALPING:
        frame = feed.fetch(args.ticker, period="7d", interval="1m")
    else:
        frame = feed.fetch(args.ticker, period="2y", interval="1h")
    if frame.empty:
        raise SystemExit("백테스트 데이터를 받지 못했습니다.")

    tester = StrategyBacktester(
        strategy_type,
        initial_cash=args.cash,
        fee_rate=CONFIG.paper_fee_rate,
        slippage_rate=CONFIG.paper_slippage_rate,
    )
    metrics = tester.run(args.ticker, frame)
    print("\n=== 백테스트 결과 ===")
    for key, value in metrics.items():
        if key in {"total_return", "win_rate", "max_drawdown"}:
            print(f"{key}: {value:.2%}")
        else:
            print(f"{key}: {value:,.4f}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([trade.__dict__ for trade in tester.trades]).to_csv(output, index=False, encoding="utf-8-sig")
    print(f"거래내역 저장: {output}")


if __name__ == "__main__":
    main()
