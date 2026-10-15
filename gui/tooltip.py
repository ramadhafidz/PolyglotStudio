"""
Polyglot Studio — Modern Desktop Tooltip Component
Provides floating hover tooltips with progressive disclosure and accelerator hints.
"""

import tkinter as tk
from typing import Optional


class ToolTip:
    """
    Floating tooltip for Tkinter/ttk widgets.
    Adheres to modern desktop UX principles:
    - 350ms delay to avoid accidental triggers during rapid cursor movement
    - Dark fluent-style container (#1E1E1E with subtle border)
    - Off-screen collision detection
    - Auto-dismiss on click, leave, or widget unmap
    """

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.tip_window: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None

        self.widget.bind("<Enter>", self._on_enter, add="+")
        self.widget.bind("<Leave>", self._on_leave, add="+")
        self.widget.bind("<ButtonPress>", self._on_leave, add="+")
        self.widget.bind("<Destroy>", self._on_destroy, add="+")

    def _on_enter(self, event=None):
        self._cancel()
        if self.text:
            self._after_id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, event=None):
        self._cancel()
        self._hide()

    def _on_destroy(self, event=None):
        self._cancel()
        self._hide()

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self.tip_window or not self.text:
            return

        try:
            # Calculate coordinates
            x = self.widget.winfo_rootx() + 8
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6

            # Screen bounds check
            screen_w = self.widget.winfo_screenwidth()
            screen_h = self.widget.winfo_screenheight()

            self.tip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.attributes("-topmost", True)

            # Modern dark container
            frame = tk.Frame(
                tw,
                background="#1E1E1E",
                highlightthickness=1,
                highlightbackground="#3E3E42",
                highlightcolor="#3E3E42"
            )
            frame.pack(fill="both", expand=True)

            label = tk.Label(
                frame,
                text=self.text,
                justify=tk.LEFT,
                background="#1E1E1E",
                foreground="#F1F1F1",
                font=("Segoe UI", 9),
                padx=8,
                pady=4
            )
            label.pack()

            tw.update_idletasks()
            w = tw.winfo_width()
            h = tw.winfo_height()

            # Prevent rendering outside right or bottom screen edges
            if x + w > screen_w - 10:
                x = screen_w - w - 10
            if y + h > screen_h - 10:
                y = self.widget.winfo_rooty() - h - 6

            tw.wm_geometry(f"+{x}+{y}")
        except Exception:
            self._hide()

    def _hide(self):
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None

    def update_text(self, new_text: str):
        self.text = new_text
        if self.tip_window:
            self._hide()


def set_tooltip(widget: tk.Widget, text: str, delay_ms: int = 350) -> ToolTip:
    """Helper to attach a ToolTip to any widget."""
    return ToolTip(widget, text, delay_ms=delay_ms)
