"""
RomFS Working Directory & Asset Category Selector Dialog for Polyglot Studio.
Allows users to choose which subfolder (dialogue, UI textures, fonts, scripts, audio)
or entire RomFS archive to explore and edit in the workspace.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Dict, Any

from core.icons import Icons
from core.logger import log


class RomFSFolderDialog(tk.Toplevel):
    """
    Modal dialog for selecting RomFS subfolders and asset filters.
    """

    PRESETS = [
        {
            "id": "message_en",
            "name": "Dialogue Text (English Scripts)",
            "subfolder": "message/dat/English",
            "filter": "text",
            "icon": Icons.EDIT,
            "desc": "FlatBuffers (.dat) story, NPC, battle, and menu dialogue scripts (913 files)."
        },
        {
            "id": "message_all",
            "name": "Dialogue Text (All Regional Languages)",
            "subfolder": "message/dat",
            "filter": "text",
            "icon": Icons.EDIT,
            "desc": "All regional language scripts across Japanese, English, French, German, etc. (9,247 files)."
        },
        {
            "id": "ui_tex",
            "name": "UI Textures, Logos & Menu Graphics",
            "subfolder": "appli/tex",
            "filter": "texture",
            "icon": Icons.IMAGE,
            "desc": "User interface textures, HUD icons, logos, brand graphics, and maps (.bntx, .png)."
        },
        {
            "id": "ui_font",
            "name": "UI Fonts & System Typography",
            "subfolder": "appli/font",
            "filter": "font",
            "icon": Icons.FONT,
            "desc": "Game typography and glyph sets (.bffnt, .bfotf)."
        },
        {
            "id": "scripts",
            "name": "Game Event Scripts",
            "subfolder": "script",
            "filter": "all",
            "icon": Icons.PACKAGE,
            "desc": "Game event scripts and story logic files."
        },
        {
            "id": "audio",
            "name": "Audio & Sound Effects",
            "subfolder": "audio",
            "filter": "audio",
            "icon": Icons.AUDIO,
            "desc": "Voice cues, BGM, and sound effect archives."
        },
        {
            "id": "all_appli",
            "name": "Full Application Assets (appli/)",
            "subfolder": "appli",
            "filter": "all",
            "icon": Icons.FOLDER,
            "desc": "All application resources including textures, fonts, and UI layouts."
        },
        {
            "id": "entire_romfs",
            "name": "Entire RomFS Archive (Root / All Moddable Assets)",
            "subfolder": "",
            "filter": "all",
            "icon": Icons.ROMFS,
            "desc": "Explore all game assets across the entire RomFS directory structure."
        },
        {
            "id": "custom",
            "name": "Custom RomFS Subfolder Path",
            "subfolder": "",
            "filter": "all",
            "icon": Icons.FOLDER_OPEN,
            "desc": "Specify any custom subfolder inside the RomFS (e.g. pokemon, chara, field_graphic)."
        }
    ]

    def __init__(self, parent, romfs_path: str, current_subfolder: str = "message/dat/English", trpfs_client: Optional[Any] = None):
        super().__init__(parent)
        self.parent = parent
        self.romfs_path = os.path.abspath(romfs_path) if romfs_path else ""
        self.current_subfolder = current_subfolder or "message/dat/English"
        self.trpfs_client = trpfs_client
        self.result: Optional[Dict[str, Any]] = None

        self.title("Select RomFS Working Directory")
        self.geometry("720x620")
        self.minsize(680, 560)
        self.transient(parent)

        self._center_on_parent(parent)
        self._build_ui()

        self.grab_set()

    def _center_on_parent(self, parent):
        self.update_idletasks()
        try:
            if parent:
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                parent_x = parent.winfo_rootx()
                parent_y = parent.winfo_rooty()
                if parent_w > 100 and parent_h > 100:
                    x = parent_x + (parent_w - 720) // 2
                    y = parent_y + (parent_h - 620) // 2
                    self.geometry(f"720x620+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build_ui(self):
        # 1. Header Banner
        header = ttk.Frame(self, padding=(16, 12))
        header.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header,
            text=f"{Icons.ROMFS} RomFS Working Directory & Category Selector",
            font=("Segoe UI", 12, "bold"),
            foreground="#007ACC"
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ttk.Label(
            header,
            text="Choose which RomFS directory and asset categories you want to explore or localize in your project. "
                 "Your previous translations in SQLite remain permanently safe and intact.",
            font=("Segoe UI", 9),
            foreground="#555555",
            wraplength=680
        )
        desc_lbl.pack(anchor="w", pady=(3, 0))

        # 2. RomFS Dump Location Box
        dump_frame = ttk.LabelFrame(self, text=" RomFS Source Dump Location ", padding=(10, 8))
        dump_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        dump_path_box = ttk.Frame(dump_frame)
        dump_path_box.pack(fill=tk.X)

        self.path_var = tk.StringVar(value=self.romfs_path)
        path_entry = ttk.Entry(dump_path_box, textvariable=self.path_var, state="readonly", font=("Consolas", 9))
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ttk.Button(
            dump_path_box,
            text=f"{Icons.FOLDER_OPEN} Change Dump...",
            command=self._browse_romfs_dump
        ).pack(side=tk.RIGHT)

        stats_text = "RomFS Archive loaded"
        if self.trpfs_client and getattr(self.trpfs_client, "is_loaded", False):
            named = getattr(self.trpfs_client, "named_count", 0)
            stats_text = f"Archive Loaded: {named:,} named game assets indexed"
        self.stats_lbl = ttk.Label(dump_frame, text=stats_text, foreground="#2E7D32", font=("Segoe UI", 8, "italic"))
        self.stats_lbl.pack(anchor="w", pady=(4, 0))

        # 3. Presets & Subfolder Selection Frame
        presets_frame = ttk.LabelFrame(self, text=" Select Working Directory / Subfolder ", padding=(10, 8))
        presets_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        # Determine initial selection
        initial_id = "custom"
        for p in self.PRESETS:
            if p["subfolder"] == self.current_subfolder:
                initial_id = p["id"]
                break

        self.selected_preset_var = tk.StringVar(value=initial_id)
        self.custom_subfolder_var = tk.StringVar(value=self.current_subfolder if initial_id == "custom" else "")

        # Scrollable container for presets list
        canvas = tk.Canvas(presets_frame, highlightthickness=0)
        v_scroll = ttk.Scrollbar(presets_frame, orient=tk.VERTICAL, command=canvas.yview)
        inner_frame = ttk.Frame(canvas)

        inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scroll.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for p in self.PRESETS:
            p_id = p["id"]
            row = ttk.Frame(inner_frame, padding=(4, 3))
            row.pack(fill=tk.X, expand=True)

            rb = ttk.Radiobutton(
                row,
                text=f"{p['icon']}  {p['name']}",
                value=p_id,
                variable=self.selected_preset_var,
                command=self._on_preset_change
            )
            rb.pack(anchor="w")

            desc = ttk.Label(
                row,
                text=f"       Path: romfs/{p['subfolder'] if p['subfolder'] else '(root)'} — {p['desc']}",
                foreground="#666666",
                font=("Segoe UI", 8)
            )
            desc.pack(anchor="w")

            if p_id == "custom":
                custom_entry_frame = ttk.Frame(row, padding=(24, 4))
                custom_entry_frame.pack(fill=tk.X)
                ttk.Label(custom_entry_frame, text="Subfolder Path:", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT, padx=(0, 6))
                self.custom_entry = ttk.Entry(custom_entry_frame, textvariable=self.custom_subfolder_var, width=38, font=("Consolas", 9))
                self.custom_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 4. Filter Options
        filter_frame = ttk.Frame(self, padding=(16, 4))
        filter_frame.pack(fill=tk.X)

        self.moddable_only_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            filter_frame,
            text="Filter to moddable game assets only (skip internal Game Freak .tbl/.bin tables)",
            variable=self.moddable_only_var
        ).pack(anchor="w")

        # 5. Buttons Footer
        btn_frame = ttk.Frame(self, padding=(16, 12))
        btn_frame.pack(fill=tk.X)

        self.open_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.ROMFS} Open Folder in Studio",
            command=self._confirm
        )
        self.open_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(
            btn_frame,
            text="Cancel",
            command=self.destroy
        )
        self.cancel_btn.pack(side=tk.RIGHT)

    def _on_preset_change(self):
        sel = self.selected_preset_var.get()
        if sel == "custom":
            self.custom_entry.focus_set()

    def _browse_romfs_dump(self):
        folder = filedialog.askdirectory(title="Select RomFS Dump Folder (containing 'arc' folder)", parent=self)
        if folder:
            trpfd = os.path.join(folder, "arc", "data.trpfd")
            if not os.path.exists(trpfd):
                messagebox.showerror(
                    "Invalid RomFS",
                    f"Selected folder does not contain 'arc/data.trpfd':\n{folder}",
                    parent=self
                )
                return
            self.romfs_path = os.path.abspath(folder)
            self.path_var.set(self.romfs_path)
            if self.trpfs_client:
                ok, msg = self.trpfs_client.load_romfs(self.romfs_path)
                if ok:
                    named = getattr(self.trpfs_client, "named_count", 0)
                    self.stats_lbl.config(text=f"Archive Loaded: {named:,} named game assets indexed", foreground="#2E7D32")
                else:
                    self.stats_lbl.config(text=f"Failed to load: {msg}", foreground="red")

    def _confirm(self):
        if not self.romfs_path or not os.path.exists(self.romfs_path):
            messagebox.showerror("Error", "Please select a valid RomFS source directory first.", parent=self)
            return

        sel = self.selected_preset_var.get()
        subfolder = ""
        asset_filter = "all"

        if sel == "custom":
            subfolder = self.custom_subfolder_var.get().strip().replace("\\", "/")
            asset_filter = "all"
        else:
            for p in self.PRESETS:
                if p["id"] == sel:
                    subfolder = p["subfolder"]
                    asset_filter = p["filter"]
                    break

        self.result = {
            "romfs_path": self.romfs_path,
            "subfolder": subfolder,
            "asset_filter": asset_filter,
            "moddable_only": self.moddable_only_var.get()
        }
        self.destroy()
