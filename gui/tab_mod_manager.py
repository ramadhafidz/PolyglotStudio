import os
import subprocess
import customtkinter as ctk
from typing import Dict, Any, List
from core.emu_detector import EmuDetector

class ModManagerTab(ctk.CTkFrame):
    def __init__(self, master, app_state):
        super().__init__(master, fg_color="transparent")
        self.app_state = app_state
        self.mod_widgets: List[Dict[str, Any]] = []

        self.setup_ui()
        self.refresh_mods()

    def setup_ui(self):
        # Header / Controls
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=(15, 10))

        title_lbl = ctk.CTkLabel(
            top_bar, 
            text="📦 Pengelola Mod Game (Eden Emulator)", 
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_lbl.pack(side="left")

        refresh_btn = ctk.CTkButton(
            top_bar, 
            text="🔄 Refresh Mod", 
            width=120, 
            command=self.refresh_mods
        )
        refresh_btn.pack(side="right", padx=5)

        open_folder_btn = ctk.CTkButton(
            top_bar, 
            text="📂 Buka Folder Mod", 
            width=140, 
            fg_color="#3B82F6", 
            hover_color="#2563EB",
            command=self.open_mod_folder
        )
        open_folder_btn.pack(side="right", padx=5)

        # Mod List Scrollable Frame
        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Daftar Mod Terpasang", corner_radius=10)
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=10)

        # Status Footer
        self.status_lbl = ctk.CTkLabel(self, text="", text_color="gray")
        self.status_lbl.pack(side="bottom", anchor="w", padx=20, pady=5)

    def refresh_mods(self):
        # Clear existing widgets
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.mod_widgets.clear()

        title_id = self.app_state.get("active_game_id", "0100A3D008C5C000")
        load_path = self.app_state.get("settings", {}).get("eden_load_path")

        mods = EmuDetector.get_mods_for_game(title_id, load_path)

        if not mods:
            no_mods_lbl = ctk.CTkLabel(
                self.scroll_frame, 
                text="Tidak ada mod yang ditemukan untuk game ini di folder Eden Emulator.", 
                text_color="gray",
                font=ctk.CTkFont(size=14)
            )
            no_mods_lbl.pack(pady=40)
            self.status_lbl.configure(text=f"Folder: {load_path}\\{title_id} (0 Mod)")
            return

        for mod in mods:
            row_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=8, fg_color="#1E293B")
            row_frame.pack(fill="x", padx=5, pady=5)

            # Switch for enable/disable
            switch_var = ctk.BooleanVar(value=mod["is_enabled"])
            switch = ctk.CTkSwitch(
                row_frame, 
                text="", 
                variable=switch_var,
                width=50,
                command=lambda m=mod, v=switch_var: self.on_toggle_mod(m, v)
            )
            switch.pack(side="left", padx=15, pady=12)

            # Name and type tags
            info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=5, pady=8)

            name_color = "white" if mod["is_enabled"] else "gray"
            name_lbl = ctk.CTkLabel(
                info_frame, 
                text=mod["display_name"], 
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color=name_color,
                anchor="w"
            )
            name_lbl.pack(fill="x")

            # Tags (RomFS, ExeFS)
            tags_text = []
            if mod["has_romfs"]:
                tags_text.append("[RomFS]")
            if mod["has_exefs"]:
                tags_text.append("[ExeFS]")
            tag_str = " ".join(tags_text) if tags_text else "[Misc]"

            tag_lbl = ctk.CTkLabel(
                info_frame, 
                text=f"{tag_str}  •  Folder: {mod['folder_name']}", 
                font=ctk.CTkFont(size=12),
                text_color="#94A3B8",
                anchor="w"
            )
            tag_lbl.pack(fill="x")

            # Folder explore button
            exp_btn = ctk.CTkButton(
                row_frame, 
                text="📁", 
                width=40, 
                height=32, 
                fg_color="#334155", 
                hover_color="#475569",
                command=lambda p=mod["path"]: self.open_folder(p)
            )
            exp_btn.pack(side="right", padx=15, pady=10)

        self.status_lbl.configure(text=f"Total: {len(mods)} mod terpasang untuk {title_id}")

    def on_toggle_mod(self, mod: Dict[str, Any], switch_var: ctk.BooleanVar):
        success = EmuDetector.toggle_mod(mod)
        if success:
            self.refresh_mods()
        else:
            switch_var.set(not switch_var.get())

    def open_folder(self, path: str):
        if os.path.exists(path):
            os.startfile(path)

    def open_mod_folder(self):
        title_id = self.app_state.get("active_game_id", "0100A3D008C5C000")
        load_path = self.app_state.get("settings", {}).get("eden_load_path")
        game_path = os.path.join(load_path, title_id)
        os.makedirs(game_path, exist_ok=True)
        os.startfile(game_path)
