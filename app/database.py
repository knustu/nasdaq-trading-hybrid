from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA secure_delete = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_iterations INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id INTEGER PRIMARY KEY,
    strategy_type TEXT NOT NULL DEFAULT 'SCALPING' CHECK(strategy_type IN ('SCALPING', 'SWING')),
    trading_mode TEXT NOT NULL DEFAULT 'PAPER' CHECK(trading_mode IN ('PAPER', 'LIVE')),
    risk_per_trade REAL NOT NULL DEFAULT 0.01 CHECK(risk_per_trade > 0 AND risk_per_trade <= 0.10),
    max_positions INTEGER NOT NULL DEFAULT 1 CHECK(max_positions BETWEEN 1 AND 10),
    max_trades_per_day INTEGER NOT NULL DEFAULT 1 CHECK(max_trades_per_day BETWEEN 1 AND 50),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS strategy_settings (
    user_id INTEGER NOT NULL,
    strategy_type TEXT NOT NULL CHECK(strategy_type IN ('SCALPING', 'SWING')),
    entry_threshold REAL NOT NULL,
    stop_loss_rate REAL NOT NULL,
    take_profit_rate REAL NOT NULL,
    trailing_activation REAL NOT NULL,
    trailing_gap REAL NOT NULL,
    max_holding_minutes INTEGER NOT NULL,
    PRIMARY KEY(user_id, strategy_type),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paper_accounts (
    user_id INTEGER PRIMARY KEY,
    cash REAL NOT NULL,
    initial_cash REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    strategy_type TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    entry_price REAL NOT NULL CHECK(entry_price > 0),
    highest_price REAL NOT NULL CHECK(highest_price > 0),
    entry_fee REAL NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, strategy_type, ticker),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    strategy_type TEXT NOT NULL,
    mode TEXT NOT NULL,
    broker_order_id TEXT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity INTEGER NOT NULL,
    requested_price REAL,
    fill_price REAL,
    fee_amount REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    strategy_type TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    fees REAL NOT NULL,
    net_pnl REAL NOT NULL,
    net_return REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    exit_reason TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trades_user_closed ON trades(user_id, closed_at);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA secure_delete = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def initialize(self) -> None:
        with self._lock, self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self.connect()
            try:
                conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
