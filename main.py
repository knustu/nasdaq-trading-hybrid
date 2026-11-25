from app.config import CONFIG
from app.database import Database
from app.cpp_adapter import require_cpp_engine
from app.gui import TradingApp
from app.logging_utils import setup_logging


def main() -> None:
    setup_logging("desktop")
    if CONFIG.require_cpp_engine:
        require_cpp_engine()
    db = Database(CONFIG.database_path)
    app = TradingApp(db)
    app.mainloop()


if __name__ == "__main__":
    main()
