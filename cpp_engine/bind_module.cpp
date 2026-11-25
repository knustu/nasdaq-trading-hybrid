#include <pybind11/pybind11.h>

#include "engine.hpp"

namespace py = pybind11;

PYBIND11_MODULE(trading_engine, module) {
    module.doc() = "C++ deterministic strategy, risk, and paper-order calculation engine";

    py::class_<EntryResult>(module, "EntryResult")
        .def_readonly("should_enter", &EntryResult::should_enter)
        .def_readonly("used_ai", &EntryResult::used_ai)
        .def_readonly("rule_score", &EntryResult::rule_score)
        .def_readonly("final_probability", &EntryResult::final_probability)
        .def_readonly("reason", &EntryResult::reason);

    py::class_<ExitResult>(module, "ExitResult")
        .def_readonly("should_exit", &ExitResult::should_exit)
        .def_readonly("trailing_active", &ExitResult::trailing_active)
        .def_readonly("lock_return", &ExitResult::lock_return)
        .def_readonly("net_return", &ExitResult::net_return)
        .def_readonly("reason", &ExitResult::reason);

    py::class_<PositionSizeResult>(module, "PositionSizeResult")
        .def_readonly("quantity", &PositionSizeResult::quantity)
        .def_readonly("by_cash", &PositionSizeResult::by_cash)
        .def_readonly("by_risk", &PositionSizeResult::by_risk)
        .def_readonly("allocated_cash", &PositionSizeResult::allocated_cash)
        .def_readonly("risk_budget", &PositionSizeResult::risk_budget)
        .def_readonly("reason", &PositionSizeResult::reason);

    py::class_<PaperFillResult>(module, "PaperFillResult")
        .def_readonly("fill_price", &PaperFillResult::fill_price)
        .def_readonly("gross_amount", &PaperFillResult::gross_amount)
        .def_readonly("fee_amount", &PaperFillResult::fee_amount)
        .def_readonly("cash_delta", &PaperFillResult::cash_delta);

    py::class_<TradeMathResult>(module, "TradeMathResult")
        .def_readonly("gross_pnl", &TradeMathResult::gross_pnl)
        .def_readonly("total_fees", &TradeMathResult::total_fees)
        .def_readonly("net_pnl", &TradeMathResult::net_pnl)
        .def_readonly("invested_amount", &TradeMathResult::invested_amount)
        .def_readonly("net_return", &TradeMathResult::net_return);

    module.def("evaluate_scalping_entry", &evaluate_scalping_entry,
        py::arg("rsi"), py::arg("macd_diff"), py::arg("ema_gap"), py::arg("vwap_dist"),
        py::arg("volume_ratio"), py::arg("bb_pband"), py::arg("disparity_5"),
        py::arg("ai_probability"), py::arg("entry_threshold"), py::arg("allow_rule_fallback"));

    module.def("evaluate_swing_entry", &evaluate_swing_entry,
        py::arg("rsi"), py::arg("macd_diff"), py::arg("disparity_20"), py::arg("ema_gap"),
        py::arg("current_close"), py::arg("previous_close"), py::arg("volume_ratio"),
        py::arg("atr_pct"), py::arg("ai_probability"), py::arg("entry_threshold"),
        py::arg("allow_rule_fallback"));

    module.def("evaluate_scalping_exit", &evaluate_scalping_exit,
        py::arg("entry_price"), py::arg("current_price"), py::arg("highest_price"),
        py::arg("friction_rate"), py::arg("hard_stop"), py::arg("activation"),
        py::arg("initial_lock"), py::arg("step"), py::arg("take_profit"));

    module.def("evaluate_swing_exit", &evaluate_swing_exit,
        py::arg("entry_price"), py::arg("current_price"), py::arg("highest_price"),
        py::arg("friction_rate"), py::arg("stop_loss"), py::arg("take_profit"),
        py::arg("trailing_activation"), py::arg("trailing_gap"));

    module.def("calculate_position_size", &calculate_position_size,
        py::arg("cash"), py::arg("price"), py::arg("risk_per_trade"),
        py::arg("stop_loss_rate"), py::arg("max_positions"), py::arg("reserve_rate") = 0.003);

    module.def("calculate_paper_fill", &calculate_paper_fill,
        py::arg("reference_price"), py::arg("quantity"), py::arg("is_buy"),
        py::arg("fee_rate"), py::arg("slippage_rate"));

    module.def("calculate_trade_math", &calculate_trade_math,
        py::arg("entry_price"), py::arg("exit_price"), py::arg("quantity"),
        py::arg("entry_fee"), py::arg("exit_fee"));

    module.def("engine_version", &engine_version);
}
