from pathlib import Path

import pytest

from app.database import Database
from app.domain import StrategyType
from app.user_manager import UserManager


def test_register_and_authenticate(tmp_path: Path):
    manager = UserManager(Database(tmp_path / "test.db"))
    user = manager.register("tester_1", "Password123", 5000)
    assert manager.authenticate("tester_1", "Password123") == user
    assert manager.authenticate("tester_1", "wrong-password") is None
    assert manager.get_preferences(user.id).strategy_type is StrategyType.SCALPING


def test_duplicate_username_is_rejected(tmp_path: Path):
    manager = UserManager(Database(tmp_path / "test.db"))
    manager.register("tester_2", "Password123", 5000)
    with pytest.raises(ValueError):
        manager.register("tester_2", "Password456", 5000)
