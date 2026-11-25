from __future__ import annotations

from .config import CONFIG
from .database import Database
from .domain import StrategySettings, StrategyType, TradingMode, User, UserPreferences
from .security import hash_password, validate_username, verify_password


DEFAULT_SETTINGS = {
    StrategyType.SCALPING: StrategySettings(
        strategy_type=StrategyType.SCALPING,
        entry_threshold=0.75,
        stop_loss_rate=0.012,
        take_profit_rate=0.025,
        trailing_activation=0.015,
        trailing_gap=0.007,
        max_holding_minutes=45,
    ),
    StrategyType.SWING: StrategySettings(
        strategy_type=StrategyType.SWING,
        entry_threshold=0.70,
        stop_loss_rate=0.05,
        take_profit_rate=0.12,
        trailing_activation=0.08,
        trailing_gap=0.03,
        max_holding_minutes=60 * 24 * 20,
    ),
}


class UserManager:
    def __init__(self, db: Database):
        self.db = db

    def register(self, username: str, password: str, initial_cash: float | None = None) -> User:
        username = username.strip()
        validate_username(username)
        record = hash_password(password)
        cash = float(initial_cash if initial_cash is not None else CONFIG.paper_initial_balance)
        if cash <= 0:
            raise ValueError("초기 모의투자 자금은 0보다 커야 합니다.")

        with self.db.transaction(immediate=True) as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
            if exists:
                raise ValueError("이미 사용 중인 아이디입니다.")

            cursor = conn.execute(
                """
                INSERT INTO users(username, password_salt, password_hash, password_iterations)
                VALUES (?, ?, ?, ?)
                """,
                (username, record.salt_b64, record.hash_b64, record.iterations),
            )
            user_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO user_preferences(user_id) VALUES (?)",
                (user_id,),
            )
            for settings in DEFAULT_SETTINGS.values():
                conn.execute(
                    """
                    INSERT INTO strategy_settings(
                        user_id, strategy_type, entry_threshold, stop_loss_rate,
                        take_profit_rate, trailing_activation, trailing_gap, max_holding_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        settings.strategy_type.value,
                        settings.entry_threshold,
                        settings.stop_loss_rate,
                        settings.take_profit_rate,
                        settings.trailing_activation,
                        settings.trailing_gap,
                        settings.max_holding_minutes,
                    ),
                )
            conn.execute(
                "INSERT INTO paper_accounts(user_id, cash, initial_cash) VALUES (?, ?, ?)",
                (user_id, cash, cash),
            )
        return User(user_id, username, True)

    def authenticate(self, username: str, password: str) -> User | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, password_salt, password_hash, password_iterations, is_active
                FROM users WHERE username = ?
                """,
                (username.strip(),),
            ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if not verify_password(
            password,
            row["password_salt"],
            row["password_hash"],
            row["password_iterations"],
        ):
            return None
        return User(int(row["id"]), str(row["username"]), bool(row["is_active"]))

    def get_preferences(self, user_id: int) -> UserPreferences:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise KeyError("사용자 설정을 찾을 수 없습니다.")
        return UserPreferences(
            strategy_type=StrategyType(row["strategy_type"]),
            trading_mode=TradingMode(row["trading_mode"]),
            risk_per_trade=float(row["risk_per_trade"]),
            max_positions=int(row["max_positions"]),
            max_trades_per_day=int(row["max_trades_per_day"]),
        )

    def update_preferences(self, user_id: int, preferences: UserPreferences) -> None:
        if not 0 < preferences.risk_per_trade <= 0.10:
            raise ValueError("거래당 위험 비율은 0% 초과 10% 이하여야 합니다.")
        if not 1 <= preferences.max_positions <= 10:
            raise ValueError("최대 동시 보유 종목은 1~10개입니다.")
        if not 1 <= preferences.max_trades_per_day <= 50:
            raise ValueError("일일 최대 거래 횟수는 1~50회입니다.")
        if preferences.trading_mode is TradingMode.LIVE and not CONFIG.live_ready():
            raise ValueError("실거래 환경변수와 명시적 허용 설정이 완료되지 않았습니다.")

        with self.db.transaction(immediate=True) as conn:
            current = conn.execute(
                "SELECT strategy_type, trading_mode FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if current is None:
                raise KeyError("사용자 설정을 찾을 수 없습니다.")
            changing_execution_context = (
                current["strategy_type"] != preferences.strategy_type.value
                or current["trading_mode"] != preferences.trading_mode.value
            )
            if changing_execution_context:
                open_position = conn.execute(
                    "SELECT 1 FROM positions WHERE user_id = ? LIMIT 1",
                    (user_id,),
                ).fetchone()
                if open_position:
                    raise ValueError("보유 포지션이 있는 동안 전략 또는 거래 모드를 변경할 수 없습니다.")
            conn.execute(
                """
                UPDATE user_preferences
                SET strategy_type = ?, trading_mode = ?, risk_per_trade = ?,
                    max_positions = ?, max_trades_per_day = ?
                WHERE user_id = ?
                """,
                (
                    preferences.strategy_type.value,
                    preferences.trading_mode.value,
                    preferences.risk_per_trade,
                    preferences.max_positions,
                    preferences.max_trades_per_day,
                    user_id,
                ),
            )

    def get_strategy_settings(self, user_id: int, strategy_type: StrategyType) -> StrategySettings:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM strategy_settings WHERE user_id = ? AND strategy_type = ?",
                (user_id, strategy_type.value),
            ).fetchone()
        if row is None:
            return DEFAULT_SETTINGS[strategy_type]
        return StrategySettings(
            strategy_type=strategy_type,
            entry_threshold=float(row["entry_threshold"]),
            stop_loss_rate=float(row["stop_loss_rate"]),
            take_profit_rate=float(row["take_profit_rate"]),
            trailing_activation=float(row["trailing_activation"]),
            trailing_gap=float(row["trailing_gap"]),
            max_holding_minutes=int(row["max_holding_minutes"]),
        )

    def update_strategy_settings(self, user_id: int, settings: StrategySettings) -> None:
        for name, value in (
            ("진입 기준", settings.entry_threshold),
            ("손절률", settings.stop_loss_rate),
            ("익절률", settings.take_profit_rate),
            ("트레일링 시작률", settings.trailing_activation),
            ("트레일링 간격", settings.trailing_gap),
        ):
            if not 0 < value < 1:
                raise ValueError(f"{name}은 0과 1 사이의 소수로 입력하세요.")
        if settings.max_holding_minutes <= 0:
            raise ValueError("최대 보유 시간은 1분 이상이어야 합니다.")

        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                """
                INSERT INTO strategy_settings(
                    user_id, strategy_type, entry_threshold, stop_loss_rate,
                    take_profit_rate, trailing_activation, trailing_gap, max_holding_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, strategy_type) DO UPDATE SET
                    entry_threshold = excluded.entry_threshold,
                    stop_loss_rate = excluded.stop_loss_rate,
                    take_profit_rate = excluded.take_profit_rate,
                    trailing_activation = excluded.trailing_activation,
                    trailing_gap = excluded.trailing_gap,
                    max_holding_minutes = excluded.max_holding_minutes
                """,
                (
                    user_id,
                    settings.strategy_type.value,
                    settings.entry_threshold,
                    settings.stop_loss_rate,
                    settings.take_profit_rate,
                    settings.trailing_activation,
                    settings.trailing_gap,
                    settings.max_holding_minutes,
                ),
            )

    def get_trade_history(self, user_id: int, limit: int = 100) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trades WHERE user_id = ? ORDER BY closed_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def change_password(self, user_id: int, old_password: str, new_password: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT password_salt, password_hash, password_iterations FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None or not verify_password(
            old_password, row["password_salt"], row["password_hash"], row["password_iterations"]
        ):
            raise ValueError("현재 비밀번호가 일치하지 않습니다.")
        record = hash_password(new_password)
        with self.db.transaction(immediate=True) as conn:
            conn.execute(
                "UPDATE users SET password_salt = ?, password_hash = ?, password_iterations = ? WHERE id = ?",
                (record.salt_b64, record.hash_b64, record.iterations, user_id),
            )

    def withdraw(self, user_id: int, password: str) -> None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT password_salt, password_hash, password_iterations FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None or not verify_password(
            password, row["password_salt"], row["password_hash"], row["password_iterations"]
        ):
            raise ValueError("비밀번호가 일치하지 않습니다.")
        with self.db.transaction(immediate=True) as conn:
            open_position = conn.execute(
                "SELECT 1 FROM positions WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            if open_position:
                raise ValueError("보유 포지션을 먼저 청산한 뒤 탈퇴하세요.")
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
