from __future__ import annotations

import inspect
import tkinter as tk

from app.gui import TradingApp


def test_gui_does_not_shadow_tkinter_internal_methods():
    inherited_names: set[str] = set()
    for base in tk.Tk.mro()[1:]:
        inherited_names.update(base.__dict__)

    own_methods = {
        name
        for name, value in TradingApp.__dict__.items()
        if inspect.isfunction(value)
    }

    # __init__ is intentionally overridden; Tkinter private internals must not be.
    collisions = (own_methods & inherited_names) - {"__init__"}
    assert collisions == set(), f"Tkinter method name collision: {sorted(collisions)}"
