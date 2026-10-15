import os
import json
from typing import Dict, Any, List, Tuple
from core.icons import Icons

class StatusTracker:
    """
    Binary Status Tracker for Game Localization:
    - Sudah (Completed): All dialogue lines translated
    - Belum (Untranslated): Not yet translated or incomplete
    """

    @classmethod
    def calculate_status(cls, orig_lines: List[str], trans_lines: List[str]) -> Tuple[str, int, int]:
        if not trans_lines:
            return "untranslated", 0, len(orig_lines)

        diffs = 0
        total_text_lines = 0

        for o, t in zip(orig_lines, trans_lines):
            o_clean = o.strip()
            t_clean = t.strip()
            # Ignore empty lines or pure game engine control codes like [~ 14]
            if o_clean and not o_clean.startswith("[~"):
                total_text_lines += 1
                if o_clean != t_clean:
                    diffs += 1

        if total_text_lines == 0:
            return "untranslated", 0, 0

        if diffs == total_text_lines:
            return "completed", diffs, total_text_lines
        else:
            return "untranslated", diffs, total_text_lines

    @classmethod
    def parse_txt_lines(cls, txt_path: str) -> List[str]:
        """Read a text file and strip header comments/metadata."""
        if not os.path.exists(txt_path):
            return []
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                raw = f.readlines()
            start = 0
            for i, line in enumerate(raw):
                if "~~~~~~~~~~~~~~~" in line and i > 0:
                    start = i + 1
                    break
            return [l.rstrip('\r\n') for l in raw[start:] if not l.startswith("~~~~~~~~~~~~~~~")]
        except Exception:
            return []

    @classmethod
    def get_display_info(cls, status: str, diffs: int = 0, total: int = 0, is_manual: bool = False) -> Tuple[str, str, str]:
        """
        Returns (icon, label_text, hex_color).
        Only 2 statuses: 'Sudah' and 'Belum'.
        """
        if status == "completed":
            return Icons.STATUS_DONE, "Sudah", "#2E7D32"
        else:
            return Icons.STATUS_TODO, "Belum", "#757575"

    @classmethod
    def load_cache(cls, cache_file: str) -> Dict[str, Any]:
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @classmethod
    def save_cache(cls, cache_file: str, data: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(cache_file)), exist_ok=True)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

