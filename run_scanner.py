from __future__ import annotations

import argparse

from app.domain import StrategyType
from app.logging_utils import setup_logging
from app.scanner import MarketScanner


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=["SCALPING", "SWING"], required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    setup_logging("scanner")
    results = MarketScanner().scan(StrategyType(args.strategy), limit=args.limit)
    print(results)
