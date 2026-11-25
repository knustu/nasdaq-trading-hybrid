from __future__ import annotations

import argparse
import json

from app.ai_analyzer import AIAnalyzer
from app.config import MODEL_DIR
from app.logging_utils import setup_logging

SCALPING_TICKERS = ["AAPL", "MSFT", "NVDA", "AMD", "META", "TSLA", "QQQ", "TQQQ", "SOXL", "MU"]
SWING_TICKERS = ["AAPL", "MSFT", "NVDA", "AMD", "META", "TSLA", "AMZN", "GOOGL", "QQQ", "AVGO", "MU"]


def train_scalping() -> dict:
    analyzer = AIAnalyzer(
        MODEL_DIR / "scalping_xgb_model.json",
        expected_interval="1m",
        strategy_type="SCALPING",
    )
    return analyzer.train(
        tickers=SCALPING_TICKERS,
        period="28d",
        interval="1m",
        forward_bars=30,
        target_return=0.018,
        stop_loss_rate=0.012,
        live_threshold=0.75,
    )


def train_swing() -> dict:
    analyzer = AIAnalyzer(
        MODEL_DIR / "swing_xgb_model.json",
        expected_interval="1h",
        strategy_type="SWING",
    )
    return analyzer.train(
        tickers=SWING_TICKERS,
        period="2y",
        interval="1h",
        forward_bars=40,
        target_return=0.10,
        stop_loss_rate=0.05,
        live_threshold=0.70,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["SCALPING", "SWING", "BOTH"], default="BOTH")
    args = parser.parse_args()
    setup_logging("training")
    results = {}
    if args.strategy in {"SCALPING", "BOTH"}:
        results["SCALPING"] = train_scalping()
    if args.strategy in {"SWING", "BOTH"}:
        results["SWING"] = train_swing()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
