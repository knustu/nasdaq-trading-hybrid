from __future__ import annotations

import getpass

from .config import CONFIG
from .database import Database
from .domain import StrategyType, TradingMode, UserPreferences
from .trading_service import TradingService
from .user_manager import UserManager


def run_cli(db: Database) -> None:
    users = UserManager(db)
    while True:
        print("\n=== 고객 관리형 자동매매 ===")
        print("1. 로그인\n2. 회원가입\n0. 종료")
        choice = input("선택: ").strip()
        if choice == "0":
            return
        if choice == "2":
            try:
                username = input("아이디: ").strip()
                password = getpass.getpass("비밀번호: ")
                confirm = getpass.getpass("비밀번호 확인: ")
                if password != confirm:
                    print("비밀번호가 일치하지 않습니다.")
                    continue
                cash = float(input(f"모의 초기자금 [{CONFIG.paper_initial_balance:.0f}]: ") or CONFIG.paper_initial_balance)
                user = users.register(username, password, cash)
                print(f"{user.username} 회원가입 완료")
            except Exception as exc:
                print(f"회원가입 실패: {exc}")
            continue
        if choice != "1":
            continue
        username = input("아이디: ").strip()
        password = getpass.getpass("비밀번호: ")
        user = users.authenticate(username, password)
        if user is None:
            print("로그인 실패")
            continue
        _user_menu(db, users, user)


def _user_menu(db: Database, users: UserManager, user) -> None:
    while True:
        preferences = users.get_preferences(user.id)
        print(f"\n[{user.username}] 전략={preferences.strategy_type.value}, 모드={preferences.trading_mode.value}")
        print("1. 전략 선택\n2. 1회 실행\n3. 연속 실행\n4. 거래내역\n0. 로그아웃")
        choice = input("선택: ").strip()
        if choice == "0":
            return
        if choice == "1":
            strategy_text = input("SCALPING 또는 SWING: ").strip().upper()
            mode_text = input("PAPER 또는 LIVE [PAPER]: ").strip().upper() or "PAPER"
            try:
                updated = UserPreferences(
                    strategy_type=StrategyType(strategy_text),
                    trading_mode=TradingMode(mode_text),
                    risk_per_trade=preferences.risk_per_trade,
                    max_positions=preferences.max_positions,
                    max_trades_per_day=preferences.max_trades_per_day,
                )
                users.update_preferences(user.id, updated)
                print("전략을 저장했습니다.")
            except Exception as exc:
                print(f"설정 실패: {exc}")
        elif choice == "2":
            service = TradingService(db, user, event_callback=print)
            try:
                service.run_cycle()
            except Exception as exc:
                print(f"실행 오류: {exc}")
        elif choice == "3":
            service = TradingService(db, user, event_callback=print)
            print("Ctrl+C로 중지합니다.")
            try:
                service.run_forever()
            except KeyboardInterrupt:
                service.stop()
        elif choice == "4":
            for trade in users.get_trade_history(user.id):
                print(
                    trade["closed_at"],
                    trade["strategy_type"],
                    trade["ticker"],
                    f"{trade['net_pnl']:+.2f}",
                    f"{trade['net_return']:+.2%}",
                )
