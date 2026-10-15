import os
from typing import List, Dict, Any, Optional

class EmuDetector:
    """
    Detects emulator directories (Eden, Ryujinx, Yuzu, Atmosphere)
    and handles mod directory queries and toggle operations.
    """

    DEFAULT_EDEN_LOAD = os.path.expanduser(r"~\AppData\Roaming\eden\load")
    DEFAULT_EDEN_DUMP = r"E:\Modding\eden\dump"

    @classmethod
    def get_eden_load_path(cls) -> str:
        if os.path.exists(cls.DEFAULT_EDEN_LOAD):
            return cls.DEFAULT_EDEN_LOAD
        return ""

    @classmethod
    def get_installed_game_ids(cls, load_path: Optional[str] = None) -> List[str]:
        path = load_path or cls.get_eden_load_path()
        if not path or not os.path.exists(path):
            return []

        title_ids = []
        for name in os.listdir(path):
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path) and len(name) == 16 and all(c in "0123456789ABCDEFabcdef" for c in name):
                title_ids.append(name.upper())
        return title_ids

    @classmethod
    def get_mods_for_game(cls, title_id: str, load_path: Optional[str] = None) -> List[Dict[str, Any]]:
        path = load_path or cls.get_eden_load_path()
        game_path = os.path.join(path, title_id)
        if not os.path.exists(game_path):
            return []

        mods = []
        for name in os.listdir(game_path):
            mod_path = os.path.join(game_path, name)
            if os.path.isdir(mod_path):
                is_disabled = name.endswith(".disabled")
                display_name = name[:-9] if is_disabled else name

                # Detect type of mod (romfs, exefs, etc.)
                has_romfs = os.path.exists(os.path.join(mod_path, "romfs"))
                has_exefs = os.path.exists(os.path.join(mod_path, "exefs"))

                mods.append({
                    "folder_name": name,
                    "display_name": display_name,
                    "path": mod_path,
                    "is_enabled": not is_disabled,
                    "has_romfs": has_romfs,
                    "has_exefs": has_exefs
                })
        return mods

    @classmethod
    def toggle_mod(cls, mod_info: Dict[str, Any]) -> bool:
        current_path = mod_info["path"]
        parent_dir = os.path.dirname(current_path)
        current_name = os.path.basename(current_path)

        if mod_info["is_enabled"]:
            new_name = current_name + ".disabled"
        else:
            if current_name.endswith(".disabled"):
                new_name = current_name[:-9]
            else:
                new_name = current_name

        new_path = os.path.join(parent_dir, new_name)
        try:
            os.rename(current_path, new_path)
            mod_info["path"] = new_path
            mod_info["folder_name"] = new_name
            mod_info["is_enabled"] = not mod_info["is_enabled"]
            return True
        except Exception:
            return False
