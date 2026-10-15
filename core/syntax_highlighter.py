"""
Dialogue Syntax Highlighter for Pokemon Scarlet & Trinity engine text.
Provides real-time syntax highlighting for game control tokens:
- Variables: [VAR PKNAME(...)], [VAR COLOR(...)], [VAR ...]
- Escape characters: \\n, \\r, \\c, \\f, \\t
- Wait / Timing tags: [WAIT ...], [~ ...]
- Generic bracket tags: [...]
- Unclosed / broken tag warnings
"""

import re
import tkinter as tk
from typing import Optional


class DialogueSyntaxHighlighter:
    """
    Manages tag configuration and real-time syntax highlighting for Tkinter Text widgets.
    """

    # Regex patterns for dialogue tokens
    PATTERNS = {
        # Escape sequences (\n, \r, \c, \f, \t)
        "token_escape": re.compile(r'\\[nrcft]'),
        # Game Variables: [VAR ...]
        "token_var": re.compile(r'\[VAR\s+[^\]\n]+\]'),
        # Timing and wait commands: [WAIT ...], [~ ...]
        "token_wait": re.compile(r'\[(?:WAIT|~)\s+[^\]\n]+\]'),
        # Generic bracket tags: [...]
        "token_generic": re.compile(r'\[[^\]\n]+\]'),
        # Malformed or unclosed tag errors (e.g. [VAR without closing ])
        "token_error": re.compile(r'\[(?:VAR|WAIT|~)[^\]\n]*$'),
    }

    # Style definitions (foreground, background, weight)
    STYLES = {
        "token_escape": {
            "foreground": "#D84315",  # Deep orange
            "background": "#FBE9E7",  # Soft peach badge
            "weight": "bold",
        },
        "token_var": {
            "foreground": "#6A1B9A",  # Deep rich purple
            "background": "#F3E5F5",  # Soft lavender badge
            "weight": "bold",
        },
        "token_wait": {
            "foreground": "#00695C",  # Dark teal
            "background": "#E0F2F1",  # Soft mint badge
            "weight": "bold",
        },
        "token_generic": {
            "foreground": "#1565C0",  # Royal blue
            "background": "#E3F2FD",  # Soft sky blue badge
            "weight": "bold",
        },
        "token_error": {
            "foreground": "#C62828",  # Crimson red
            "background": "#FFCDD2",  # Red warning alert
            "weight": "bold",
        },
    }

    @classmethod
    def configure_tags(cls, text_widget: tk.Text, font_family: str = "Consolas", font_size: int = 10):
        """
        Configures syntax highlight tags on the specified tk.Text widget.
        """
        bold_font = (font_family, font_size, "bold")
        for tag_name, style in cls.STYLES.items():
            text_widget.tag_configure(
                tag_name,
                foreground=style["foreground"],
                background=style["background"],
                font=bold_font,
            )

    @classmethod
    def highlight(cls, text_widget: tk.Text):
        """
        Scans text_widget content and applies syntax highlight tags.
        """
        content = text_widget.get("1.0", "end-1c")
        if not content:
            # Remove existing tags if empty
            for tag_name in cls.PATTERNS.keys():
                text_widget.tag_remove(tag_name, "1.0", tk.END)
            return

        # 1. Clear previous syntax tags
        for tag_name in cls.PATTERNS.keys():
            text_widget.tag_remove(tag_name, "1.0", tk.END)

        # 2. Check for unclosed tag errors first
        err_m = cls.PATTERNS["token_error"].search(content)
        if err_m:
            start = f"1.0 + {err_m.start()} chars"
            end = f"1.0 + {err_m.end()} chars"
            text_widget.tag_add("token_error", start, end)

        # 3. Apply specific token tags
        # Variables [VAR ...]
        for m in cls.PATTERNS["token_var"].finditer(content):
            start = f"1.0 + {m.start()} chars"
            end = f"1.0 + {m.end()} chars"
            text_widget.tag_add("token_var", start, end)

        # Wait commands [WAIT ...] and [~ ...]
        for m in cls.PATTERNS["token_wait"].finditer(content):
            start = f"1.0 + {m.start()} chars"
            end = f"1.0 + {m.end()} chars"
            text_widget.tag_add("token_wait", start, end)

        # Generic brackets that are NOT VAR or WAIT
        for m in cls.PATTERNS["token_generic"].finditer(content):
            # If already tagged as var or wait, skip
            start = f"1.0 + {m.start()} chars"
            end = f"1.0 + {m.end()} chars"
            existing_tags = text_widget.tag_names(start)
            if "token_var" not in existing_tags and "token_wait" not in existing_tags:
                text_widget.tag_add("token_generic", start, end)

        # Escape sequences \n, \r, \c, \f, \t
        for m in cls.PATTERNS["token_escape"].finditer(content):
            start = f"1.0 + {m.start()} chars"
            end = f"1.0 + {m.end()} chars"
            text_widget.tag_add("token_escape", start, end)

    @classmethod
    def set_text_with_highlight(cls, text_widget: tk.Text, text: str, editable: bool = False):
        """
        Utility to safely replace content in a text widget and immediately apply highlighting.
        """
        was_disabled = str(text_widget.cget("state")) == tk.DISABLED
        if was_disabled:
            text_widget.config(state=tk.NORMAL)

        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", text)
        cls.highlight(text_widget)

        if not editable:
            text_widget.config(state=tk.DISABLED)
        elif was_disabled:
            text_widget.config(state=tk.NORMAL)

    @classmethod
    def bind_live_highlighting(cls, text_widget: tk.Text, debounce_ms: int = 40):
        """
        Binds key and modification events on text_widget for debounced, high-performance real-time syntax highlighting.
        """
        timer_id: Optional[str] = None

        def schedule_highlight(event=None):
            nonlocal timer_id
            if timer_id is not None:
                try:
                    text_widget.after_cancel(timer_id)
                except Exception:
                    pass
            timer_id = text_widget.after(debounce_ms, do_highlight)

        def do_highlight():
            nonlocal timer_id
            timer_id = None
            try:
                cls.highlight(text_widget)
            except Exception:
                pass

        text_widget.bind("<KeyRelease>", schedule_highlight)
        text_widget.bind("<<Paste>>", lambda e: text_widget.after(10, do_highlight))
