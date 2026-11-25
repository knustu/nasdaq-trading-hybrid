from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .brokers.paper import PaperBroker
from .config import CONFIG
from .cpp_adapter import engine_backend_name
from .database import Database
from .domain import StrategySettings, StrategyType, TradingMode, UserPreferences
from .trading_service import TradingService
from .user_manager import UserManager


class TradingApp(tk.Tk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.user_manager = UserManager(db)
        self.current_user = None
        self.service: TradingService | None = None
        self.worker: threading.Thread | None = None
        self.event_queue: queue.Queue[str] = queue.Queue()
        self.title("회원 관리형 스캘핑·스윙 자동매매")
        self.geometry("980x720")
        self.minsize(860, 640)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.container = ttk.Frame(self, padding=16)
        self.container.pack(fill="both", expand=True)
        self.show_login()
        self.after(200, self._drain_events)

    def clear(self) -> None:
        for child in self.container.winfo_children():
            child.destroy()

    def show_login(self) -> None:
        self.clear()
        self.current_user = None
        title = ttk.Label(self.container, text="자동매매 고객 관리", font=("맑은 고딕", 22, "bold"))
        title.pack(pady=(30, 20))
        notebook = ttk.Notebook(self.container)
        notebook.pack(fill="x", padx=180)

        login_tab = ttk.Frame(notebook, padding=24)
        register_tab = ttk.Frame(notebook, padding=24)
        notebook.add(login_tab, text="로그인")
        notebook.add(register_tab, text="회원가입")

        login_id = tk.StringVar()
        login_pw = tk.StringVar()
        self._labeled_entry(login_tab, "아이디", login_id, 0)
        self._labeled_entry(login_tab, "비밀번호", login_pw, 1, show="*")
        ttk.Button(
            login_tab,
            text="로그인",
            command=lambda: self._login(login_id.get(), login_pw.get()),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=16)

        register_id = tk.StringVar()
        register_pw = tk.StringVar()
        register_confirm = tk.StringVar()
        register_cash = tk.StringVar(value=f"{CONFIG.paper_initial_balance:.0f}")
        self._labeled_entry(register_tab, "아이디", register_id, 0)
        self._labeled_entry(register_tab, "비밀번호", register_pw, 1, show="*")
        self._labeled_entry(register_tab, "비밀번호 확인", register_confirm, 2, show="*")
        self._labeled_entry(register_tab, "모의투자 초기자금($)", register_cash, 3)
        ttk.Button(
            register_tab,
            text="회원가입",
            command=lambda: self._register_user(
                register_id.get(), register_pw.get(), register_confirm.get(), register_cash.get()
            ),
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=16)

        note = ttk.Label(
            self.container,
            text="기본값은 PAPER 모드입니다. 실거래는 환경변수와 공식 API 경로를 별도로 설정해야 합니다.",
        )
        note.pack(pady=20)

    @staticmethod
    def _labeled_entry(parent, label: str, variable: tk.Variable, row: int, show: str | None = None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        entry = ttk.Entry(parent, textvariable=variable, show=show or "", width=28)
        entry.grid(row=row, column=1, sticky="ew", pady=7)
        parent.columnconfigure(1, weight=1)
        return entry

    def _register_user(self, username: str, password: str, confirm: str, cash_text: str) -> None:
        if password != confirm:
            messagebox.showerror("회원가입 실패", "비밀번호 확인이 일치하지 않습니다.")
            return
        try:
            cash = float(cash_text)
            user = self.user_manager.register(username, password, cash)
            messagebox.showinfo("회원가입 완료", f"{user.username} 계정이 생성되었습니다.")
            self.current_user = user
            self.show_dashboard()
        except Exception as exc:
            messagebox.showerror("회원가입 실패", str(exc))

    def _login(self, username: str, password: str) -> None:
        user = self.user_manager.authenticate(username, password)
        if user is None:
            messagebox.showerror("로그인 실패", "아이디 또는 비밀번호가 올바르지 않습니다.")
            return
        self.current_user = user
        self.show_dashboard()

    def show_dashboard(self) -> None:
        if self.current_user is None:
            self.show_login()
            return
        self.clear()
        preferences = self.user_manager.get_preferences(self.current_user.id)

        header = ttk.Frame(self.container)
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"{self.current_user.username}님의 자동매매 대시보드",
            font=("맑은 고딕", 18, "bold"),
        ).pack(side="left")
        ttk.Button(header, text="로그아웃", command=self._logout).pack(side="right")
        ttk.Label(
            header,
            text=f"계산 엔진: {engine_backend_name()}",
        ).pack(side="right", padx=(0, 14))

        body = ttk.Panedwindow(self.container, orient="horizontal")
        body.pack(fill="both", expand=True, pady=(14, 0))
        settings_frame = ttk.LabelFrame(body, text="전략 및 위험 설정", padding=14)
        monitor_frame = ttk.LabelFrame(body, text="실행 모니터", padding=14)
        body.add(settings_frame, weight=1)
        body.add(monitor_frame, weight=2)

        self.strategy_var = tk.StringVar(value=preferences.strategy_type.value)
        self.mode_var = tk.StringVar(value=preferences.trading_mode.value)
        self.risk_var = tk.StringVar(value=f"{preferences.risk_per_trade * 100:.2f}")
        self.max_positions_var = tk.StringVar(value=str(preferences.max_positions))
        self.max_trades_var = tk.StringVar(value=str(preferences.max_trades_per_day))

        row = 0
        ttk.Label(settings_frame, text="전략").grid(row=row, column=0, sticky="w", pady=5)
        strategy_box = ttk.Combobox(
            settings_frame,
            textvariable=self.strategy_var,
            values=[item.value for item in StrategyType],
            state="readonly",
            width=18,
        )
        strategy_box.grid(row=row, column=1, sticky="ew", pady=5)
        strategy_box.bind("<<ComboboxSelected>>", lambda _: self._load_strategy_fields())
        row += 1

        ttk.Label(settings_frame, text="거래 모드").grid(row=row, column=0, sticky="w", pady=5)
        ttk.Combobox(
            settings_frame,
            textvariable=self.mode_var,
            values=[item.value for item in TradingMode],
            state="readonly",
            width=18,
        ).grid(row=row, column=1, sticky="ew", pady=5)
        row += 1

        for label, variable in (
            ("거래당 위험(%)", self.risk_var),
            ("최대 동시 보유", self.max_positions_var),
            ("일일 최대 매수", self.max_trades_var),
        ):
            ttk.Label(settings_frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(settings_frame, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
            row += 1

        ttk.Separator(settings_frame).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10)
        row += 1
        self.entry_threshold_var = tk.StringVar()
        self.stop_loss_var = tk.StringVar()
        self.take_profit_var = tk.StringVar()
        self.trailing_activation_var = tk.StringVar()
        self.trailing_gap_var = tk.StringVar()
        self.max_holding_var = tk.StringVar()
        for label, variable in (
            ("진입 기준(%)", self.entry_threshold_var),
            ("손절률(%)", self.stop_loss_var),
            ("익절률(%)", self.take_profit_var),
            ("트레일링 시작(%)", self.trailing_activation_var),
            ("트레일링 간격(%)", self.trailing_gap_var),
            ("최대 보유(분)", self.max_holding_var),
        ):
            ttk.Label(settings_frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(settings_frame, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=5)
            row += 1
        self._load_strategy_fields()

        ttk.Button(settings_frame, text="설정 저장", command=self._save_settings).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=(14, 5)
        )
        row += 1
        ttk.Button(settings_frame, text="계좌/포지션 새로고침", command=self._refresh_account).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=5
        )
        row += 1
        ttk.Button(settings_frame, text="모의계좌 초기화", command=self._reset_paper).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=5
        )
        row += 1
        ttk.Button(settings_frame, text="거래내역 보기", command=self._show_history).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=5
        )
        settings_frame.columnconfigure(1, weight=1)

        self.account_label = ttk.Label(monitor_frame, text="")
        self.account_label.pack(anchor="w")
        controls = ttk.Frame(monitor_frame)
        controls.pack(fill="x", pady=10)
        self.run_once_button = ttk.Button(controls, text="1회 실행", command=self._run_once)
        self.run_once_button.pack(side="left", padx=(0, 6))
        self.start_button = ttk.Button(controls, text="연속 실행", command=self._start_continuous)
        self.start_button.pack(side="left", padx=6)
        self.stop_button = ttk.Button(controls, text="중지", command=self._stop_service, state="disabled")
        self.stop_button.pack(side="left", padx=6)
        self.log_text = tk.Text(monitor_frame, wrap="word", height=25, state="disabled")
        self.log_text.pack(fill="both", expand=True)
        self._refresh_account()
        self._append_log("로그인 완료. 전략 설정을 확인한 뒤 실행하세요.")

    def _load_strategy_fields(self) -> None:
        if self.current_user is None:
            return
        strategy_type = StrategyType(self.strategy_var.get())
        settings = self.user_manager.get_strategy_settings(self.current_user.id, strategy_type)
        self.entry_threshold_var.set(f"{settings.entry_threshold * 100:.2f}")
        self.stop_loss_var.set(f"{settings.stop_loss_rate * 100:.2f}")
        self.take_profit_var.set(f"{settings.take_profit_rate * 100:.2f}")
        self.trailing_activation_var.set(f"{settings.trailing_activation * 100:.2f}")
        self.trailing_gap_var.set(f"{settings.trailing_gap * 100:.2f}")
        self.max_holding_var.set(str(settings.max_holding_minutes))

    def _save_settings(self) -> None:
        if self.current_user is None:
            return
        try:
            preferences = UserPreferences(
                strategy_type=StrategyType(self.strategy_var.get()),
                trading_mode=TradingMode(self.mode_var.get()),
                risk_per_trade=float(self.risk_var.get()) / 100.0,
                max_positions=int(self.max_positions_var.get()),
                max_trades_per_day=int(self.max_trades_var.get()),
            )
            settings = StrategySettings(
                strategy_type=preferences.strategy_type,
                entry_threshold=float(self.entry_threshold_var.get()) / 100.0,
                stop_loss_rate=float(self.stop_loss_var.get()) / 100.0,
                take_profit_rate=float(self.take_profit_var.get()) / 100.0,
                trailing_activation=float(self.trailing_activation_var.get()) / 100.0,
                trailing_gap=float(self.trailing_gap_var.get()) / 100.0,
                max_holding_minutes=int(self.max_holding_var.get()),
            )
            self.user_manager.update_preferences(self.current_user.id, preferences)
            self.user_manager.update_strategy_settings(self.current_user.id, settings)
            self._append_log("전략 및 위험 설정을 저장했습니다.")
            messagebox.showinfo("저장 완료", "설정이 저장되었습니다.")
        except Exception as exc:
            messagebox.showerror("설정 오류", str(exc))

    def _new_service(self) -> TradingService:
        if self.current_user is None:
            raise RuntimeError("로그인이 필요합니다.")
        self._save_settings_silent()
        return TradingService(self.db, self.current_user, event_callback=self.event_queue.put)

    def _save_settings_silent(self) -> None:
        if self.current_user is None:
            return
        preferences = UserPreferences(
            strategy_type=StrategyType(self.strategy_var.get()),
            trading_mode=TradingMode(self.mode_var.get()),
            risk_per_trade=float(self.risk_var.get()) / 100.0,
            max_positions=int(self.max_positions_var.get()),
            max_trades_per_day=int(self.max_trades_var.get()),
        )
        settings = StrategySettings(
            strategy_type=preferences.strategy_type,
            entry_threshold=float(self.entry_threshold_var.get()) / 100.0,
            stop_loss_rate=float(self.stop_loss_var.get()) / 100.0,
            take_profit_rate=float(self.take_profit_var.get()) / 100.0,
            trailing_activation=float(self.trailing_activation_var.get()) / 100.0,
            trailing_gap=float(self.trailing_gap_var.get()) / 100.0,
            max_holding_minutes=int(self.max_holding_var.get()),
        )
        self.user_manager.update_preferences(self.current_user.id, preferences)
        self.user_manager.update_strategy_settings(self.current_user.id, settings)

    def _run_once(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            self.service = self._new_service()
        except Exception as exc:
            messagebox.showerror("실행 불가", str(exc))
            return
        self._set_running(True)

        def task():
            try:
                self.service.run_cycle()
            except Exception as exc:
                self.event_queue.put(f"실행 오류: {exc}")
            finally:
                self.after(0, lambda: self._set_running(False))
                self.after(0, self._refresh_account)

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def _start_continuous(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            self.service = self._new_service()
            preferences = self.user_manager.get_preferences(self.current_user.id)
            if preferences.trading_mode is TradingMode.LIVE:
                confirmed = messagebox.askyesno(
                    "실거래 확인",
                    "실제 주문이 제출됩니다. 공식 API 설정과 계좌를 직접 확인했습니까?",
                )
                if not confirmed:
                    return
        except Exception as exc:
            messagebox.showerror("실행 불가", str(exc))
            return
        self._set_running(True)

        def task():
            try:
                self.service.run_forever()
            finally:
                self.after(0, lambda: self._set_running(False))
                self.after(0, self._refresh_account)

        self.worker = threading.Thread(target=task, daemon=True)
        self.worker.start()

    def _stop_service(self) -> None:
        if self.service:
            self.service.stop()
        self._append_log("중지 요청을 보냈습니다.")

    def _set_running(self, running: bool) -> None:
        self.run_once_button.configure(state="disabled" if running else "normal")
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")

    def _refresh_account(self) -> None:
        if self.current_user is None or not hasattr(self, "account_label"):
            return
        prefs = self.user_manager.get_preferences(self.current_user.id)
        broker = PaperBroker(
            self.db,
            fee_rate=CONFIG.paper_fee_rate,
            slippage_rate=CONFIG.paper_slippage_rate,
        )
        cash = broker.available_balance(self.current_user.id)
        positions = broker.list_positions(self.current_user.id, prefs.strategy_type)
        position_text = ", ".join(f"{p.ticker} {p.quantity}주" for p in positions) or "없음"
        self.account_label.configure(
            text=f"모의 현금: ${cash:,.2f} | {prefs.strategy_type.value} 포지션: {position_text}"
        )

    def _reset_paper(self) -> None:
        if self.current_user is None:
            return
        if not messagebox.askyesno("초기화 확인", "모든 모의 포지션을 삭제하고 초기 현금으로 되돌릴까요?"):
            return
        broker = PaperBroker(
            self.db,
            fee_rate=CONFIG.paper_fee_rate,
            slippage_rate=CONFIG.paper_slippage_rate,
        )
        broker.reset_account(self.current_user.id)
        self._append_log("모의계좌를 초기화했습니다.")
        self._refresh_account()

    def _show_history(self) -> None:
        if self.current_user is None:
            return
        records = self.user_manager.get_trade_history(self.current_user.id)
        window = tk.Toplevel(self)
        window.title("거래내역")
        window.geometry("900x420")
        columns = ("closed_at", "strategy", "ticker", "qty", "entry", "exit", "pnl", "return", "reason")
        tree = ttk.Treeview(window, columns=columns, show="headings")
        headings = {
            "closed_at": "청산시간",
            "strategy": "전략",
            "ticker": "종목",
            "qty": "수량",
            "entry": "매수가",
            "exit": "매도가",
            "pnl": "순손익",
            "return": "순수익률",
            "reason": "청산사유",
        }
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=95 if column != "reason" else 200, anchor="center")
        for record in records:
            tree.insert(
                "",
                "end",
                values=(
                    record["closed_at"],
                    record["strategy_type"],
                    record["ticker"],
                    record["quantity"],
                    f"{record['entry_price']:.2f}",
                    f"{record['exit_price']:.2f}",
                    f"{record['net_pnl']:+.2f}",
                    f"{record['net_return']:+.2%}",
                    record["exit_reason"],
                ),
            )
        tree.pack(fill="both", expand=True)

    def _append_log(self, text: str) -> None:
        if not hasattr(self, "log_text"):
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                self._append_log(self.event_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(200, self._drain_events)

    def _logout(self) -> None:
        self._stop_service()
        self.show_login()

    def _on_close(self) -> None:
        self._stop_service()
        self.destroy()
