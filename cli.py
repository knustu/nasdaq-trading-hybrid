from app.cli import run_cli
from app.config import CONFIG
from app.database import Database
from app.cpp_adapter import require_cpp_engine
from app.logging_utils import setup_logging


if __name__ == "__main__":
    setup_logging("cli")
    if CONFIG.require_cpp_engine:
        require_cpp_engine()
    run_cli(Database(CONFIG.database_path))
