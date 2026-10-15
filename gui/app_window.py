import os
import sys
import json
import time
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont
from tkinter.scrolledtext import ScrolledText
from typing import Dict, Any, List, Optional

from core.logger import log
from formats.pokemon_dat import PokemonDatCodec
from core.tag_guard import TagGuard
from core.universal_ai import UniversalAIClient
from core.emu_detector import EmuDetector
from core.status_tracker import StatusTracker
from core.db_manager import ProjectDB
from core.icons import Icons
from core.syntax_highlighter import DialogueSyntaxHighlighter
from core.asset_classifier import AssetClassifier, AssetType
from core.trpfs_client import TrpfsClient
from gui.viewers.texture_viewer import TextureViewer

class ClassicDATStudioApp(tk.Tk):
    """
    Classic Tkinter/TTK Interface with:
    - Left Panel: Resizable File Explorer Treeview (Folders & Files with status & Search)
    - Right Panel: Side-by-side Table Editor (Line | English | Indonesian)
    - Universal AI Translation (Custom Endpoint, Key, Model, Custom Prompt)
    - High-Performance SQLite Project Database (project.db)
    - One-click Eden Mod Deployer & Mod Manager
    - Robust Error Logging to studio.log
    """

    def __init__(self):
        log.info("Initializing PolyglotStudioApp...")
        super().__init__()
        self.title("Polyglot Studio — Nintendo Switch Game Localization & Mod Suite")
        self.geometry("1200x760")
        self.minsize(980, 640)

        # Settings & Core
        self.settings_file = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
        self.settings = self.load_settings()
        self.codec = PokemonDatCodec()
        self.ai = UniversalAIClient(
            provider=self.settings.get("ai_provider", "openai"),
            endpoint=self.settings.get("ai_endpoint", "https://api.openai.com/v1"),
            api_key=self.settings.get("ai_key", ""),
            model=self.settings.get("ai_model", "gpt-4o-mini"),
            custom_prompt=self.settings.get("custom_prompt", "")
        )

        # Workspace & SQLite Project Database
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.workspace_dir = os.path.join(self.base_dir, "workspace", "PokemonScarlet_0100A3D008C5C000")
        self.db_path = os.path.join(self.workspace_dir, "project.db")
        self.db = ProjectDB(self.db_path)
        try:
            self.db.seed_default_glossary()
        except Exception as e:
            log.warning(f"Could not seed default glossary: {e}")
        self.mod_assets_dir = os.path.join(self.workspace_dir, "assets")
        os.makedirs(self.mod_assets_dir, exist_ok=True)

        # State flags
        self._syncing_tree = False

        # File and editor state
        self.file_items: List[Dict[str, Any]] = []
        self.current_file_index = -1
        self.current_orig_lines: List[str] = []
        self.current_trans_lines: List[str] = []

        # Staged / Pending AI translations waiting for user review (git diff mode)
        # Mapping: {line_index: proposed_ai_translation_string}
        self.pending_ai_diffs: Dict[int, str] = {}

        # Undo / Redo history stacks
        self.undo_stack: List[List[str]] = []
        self.redo_stack: List[List[str]] = []

        # Search state for table
        self.search_results = []
        self.current_search_index = -1

        # Tree node mapping
        self.tree_item_to_index: Dict[str, int] = {}
        self._folder_pending_items: Dict[str, List[int]] = {}

        # Active background AI translation tasks: {filename: task_metadata_dict}
        self.active_ai_tasks: Dict[str, Dict[str, Any]] = {}

        # Multi-file pending AI diffs cache waiting for user review: {filename: {line_idx: new_text}}
        self.file_pending_ai_diffs: Dict[str, Dict[int, str]] = {}
        self.file_pending_ai_meta: Dict[str, Dict[str, Any]] = {}

        # RomFS Virtual Explorer Client
        self.trpfs_client = TrpfsClient()
        self.is_romfs_mode = False
        self.current_romfs_path: Optional[str] = None
        self.protocol("WM_DELETE_WINDOW", self.on_close_window)

        # Build UI layout with PanedWindow
        self.create_layout()

        # Keyboard Shortcuts
        self.bind('<Control-z>', self.undo)
        self.bind('<Control-Z>', self.undo)
        self.bind('<Control-y>', self.redo)
        self.bind('<Control-Y>', self.redo)
        self.bind('<Control-Shift-z>', self.redo)
        self.bind('<Control-Shift-Z>', self.redo)
        self.bind('<Control-s>', lambda e: self.save_file(silent=False))
        self.bind('<Control-S>', lambda e: self.save_file(silent=False))
        self.bind('<Control-f>', lambda e: (self.search_entry.focus_set(), self.search_entry.select_range(0, tk.END)))
        self.bind('<Control-F>', lambda e: (self.search_entry.focus_set(), self.search_entry.select_range(0, tk.END)))

        # Auto-detect RomFS dump or fallback to legacy English directory
        default_dump = os.path.join(self.settings.get("eden_dump_path", ""), self.settings.get("active_game_id", ""), "romfs")
        default_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"

        if os.path.isdir(default_dump) and os.path.exists(os.path.join(default_dump, "arc", "data.trpfd")):
            log.info(f"Default dumped RomFS found at {default_dump}, scheduling async RomFS load...")
            self.after(50, lambda: self.load_romfs_directory(default_dump))
        elif os.path.exists(default_dir):
            log.info(f"Default English directory exists, scheduling async load: {default_dir}")
            self.after(50, lambda: self.load_directory(default_dir))
        else:
            log.warning(f"Neither RomFS dump nor default English directory found.")

    def on_close_window(self):
        active_count = len(getattr(self, 'active_ai_tasks', {}))
        pending_files = [f for f, diffs in getattr(self, 'file_pending_ai_diffs', {}).items() if diffs]
        if self.pending_ai_diffs and self.current_file_index >= 0:
            cur_f = self.file_items[self.current_file_index]['filename']
            if cur_f not in pending_files:
                pending_files.append(cur_f)

        if active_count > 0 or pending_files:
            msg_parts = []
            if active_count > 0:
                msg_parts.append(f"• {active_count} AI translation task(s) are still running in the background.")
            if pending_files:
                names = ", ".join(pending_files[:3])
                if len(pending_files) > 3:
                    names += f", and {len(pending_files) - 3} other file(s)"
                msg_parts.append(f"• There are unaccepted AI translations awaiting review in: {names}.")
            msg_text = "\n".join(msg_parts) + "\n\nAre you sure you want to exit now?"
            if not messagebox.askyesno("Confirm Exit", msg_text):
                return
        self.destroy()

    confirm_exit = on_close_window

    def destroy(self):
        if hasattr(self, 'trpfs_client') and self.trpfs_client:
            try:
                self.trpfs_client.close()
            except Exception:
                pass
        super().destroy()

    def load_settings(self) -> Dict[str, Any]:
        from core.env_manager import EnvManager
        defaults = {
            "eden_load_path": os.path.expanduser(r"~\AppData\Roaming\eden\load"),
            "eden_dump_path": r"E:\Modding\eden\dump",
            "active_game_id": "0100A3D008C5C000",
            "ai_provider": "openai",
            "ai_endpoint": "https://api.openai.com/v1",
            "ai_key": "",
            "ai_model": "gpt-4o-mini",
            "target_language": "Indonesian",
            "custom_prompt": ""
        }
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    defaults.update(json.load(f))
                log.info(f"Settings loaded successfully from {self.settings_file}")
            except Exception as e:
                log.error(f"Failed to read settings file: {e}", exc_info=True)

        # Load environment variables from .env (overrides settings for security)
        env_vars = EnvManager.load_env()
        if env_vars:
            log.info(f"Loaded {len(env_vars)} configuration values from .env")

        env_map = {
            "AI_PROVIDER": "ai_provider",
            "AI_ENDPOINT": "ai_endpoint",
            "AI_KEY": "ai_key",
            "AI_API_KEY": "ai_key",
            "AI_MODEL": "ai_model",
            "TARGET_LANGUAGE": "target_language",
            "EDEN_LOAD_PATH": "eden_load_path",
            "EDEN_DUMP_PATH": "eden_dump_path",
            "ACTIVE_GAME_ID": "active_game_id",
            "TRINITY_OUTPUT_PATH": "trinity_output_path",
        }
        for env_k, settings_k in env_map.items():
            val = EnvManager.get(env_k)
            if val is not None and val != "":
                defaults[settings_k] = val

        return defaults

    def save_settings(self):
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
            log.info("Settings saved successfully.")
        except Exception as e:
            log.error(f"Failed to save settings: {e}", exc_info=True)

    def create_layout(self):
        log.debug("Creating window layout widgets...")

        # Configure modern Treeview table style (rowheight, font & selection)
        self.style = ttk.Style()
        self.style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.style.map(
            "Treeview",
            background=[("selected", "#0078D7")],
            foreground=[("selected", "#FFFFFF")]
        )

        # ----------------- Top Menu Bar -----------------
        menubar = tk.Menu(self)

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open RomFS...", command=self.open_romfs)
        file_menu.add_command(label="Open Folder...", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=lambda: self.save_file(silent=False))
        file_menu.add_separator()
        file_menu.add_command(label="Export TXT...", command=self.export_txt)
        file_menu.add_command(label="Import TXT...", command=self.import_txt)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Alt+F4", command=self.confirm_exit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Auto-Fix All Tags", command=self.auto_fix_all_tags)
        edit_menu.add_command(
            label="Find in File...", 
            accelerator="Ctrl+F", 
            command=lambda: (self.search_entry.focus_set(), self.search_entry.select_range(0, tk.END))
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # AI & Tools Menu
        ai_menu = tk.Menu(menubar, tearoff=0)
        ai_menu.add_command(label="Translate Active File (AI)", command=self.translate_with_ai)
        ai_menu.add_command(label="Batch AI Translation...", command=self.open_batch_translate_dialog)
        ai_menu.add_separator()
        ai_menu.add_command(label="Glossary / Terminology...", command=self.open_glossary_dialog)
        ai_menu.add_command(label="AI Settings...", command=self.open_settings_modal)
        menubar.add_cascade(label="AI & Tools", menu=ai_menu)

        # Modding Menu
        modding_menu = tk.Menu(menubar, tearoff=0)
        modding_menu.add_command(label="1-Click LayeredFS Mod Deployer...", command=self.deploy_to_eden)
        modding_menu.add_command(label="Mod Manager...", command=self.open_mod_manager)
        menubar.add_cascade(label="Modding", menu=modding_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About Polyglot Studio", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

        # ----------------- Top Toolbar Frame -----------------
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=4)

        def _add_sep():
            sep = ttk.Separator(top_frame, orient=tk.VERTICAL)
            sep.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # Group 1: File Operations
        ttk.Button(top_frame, text=f"{Icons.ROMFS} Open RomFS", command=self.open_romfs).pack(side=tk.LEFT, padx=1)
        ttk.Button(top_frame, text=f"{Icons.FOLDER} Open Folder", command=self.open_folder).pack(side=tk.LEFT, padx=1)
        self.save_btn = ttk.Button(top_frame, text=f"{Icons.SAVE} Save", command=self.save_file, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=1)
        self.export_btn = ttk.Button(top_frame, text=f"{Icons.EXPORT} Export TXT", command=self.export_txt, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=1)
        self.import_btn = ttk.Button(top_frame, text=f"{Icons.IMPORT} Import TXT", command=self.import_txt, state=tk.DISABLED)
        self.import_btn.pack(side=tk.LEFT, padx=1)

        _add_sep()

        # Group 2: History (Undo/Redo)
        self.undo_btn = ttk.Button(top_frame, text=f"{Icons.UNDO} Undo", command=self.undo, state=tk.DISABLED)
        self.undo_btn.pack(side=tk.LEFT, padx=1)
        self.redo_btn = ttk.Button(top_frame, text=f"{Icons.REDO} Redo", command=self.redo, state=tk.DISABLED)
        self.redo_btn.pack(side=tk.LEFT, padx=1)

        _add_sep()

        # Group 3: AI & Translation Tools
        self.ai_btn = ttk.Button(top_frame, text=f"{Icons.AI_SPARKLE} Translate AI", command=self.translate_with_ai, state=tk.DISABLED)
        self.ai_btn.pack(side=tk.LEFT, padx=1)
        self.batch_btn = ttk.Button(top_frame, text=f"{Icons.BATCH} Batch AI", command=self.open_batch_translate_dialog, state=tk.NORMAL)
        self.batch_btn.pack(side=tk.LEFT, padx=1)
        self.qa_fix_btn = ttk.Button(top_frame, text=f"{Icons.REPAIR} Fix Tags", command=self.auto_fix_all_tags, state=tk.NORMAL)
        self.qa_fix_btn.pack(side=tk.LEFT, padx=1)
        ttk.Button(top_frame, text=f"{Icons.GLOSSARY} Glossary", command=self.open_glossary_dialog).pack(side=tk.LEFT, padx=1)

        _add_sep()

        # Group 4: Modding & Deployment
        self.deploy_btn = ttk.Button(top_frame, text=f"{Icons.DEPLOY} Deploy Mod", command=self.deploy_to_eden, state=tk.NORMAL)
        self.deploy_btn.pack(side=tk.LEFT, padx=1)
        ttk.Button(top_frame, text=f"{Icons.PACKAGE} Mod Manager", command=self.open_mod_manager).pack(side=tk.LEFT, padx=1)

        _add_sep()

        # Group 5: Settings
        ttk.Button(top_frame, text=f"{Icons.SETTINGS} Settings", command=self.open_settings_modal).pack(side=tk.LEFT, padx=1)

        # AI Badge on Top Right
        self.ai_badge_lbl = ttk.Label(
            top_frame, 
            text=f"{Icons.AI_BOT} {self.ai.model}", 
            foreground="#6A1B9A", 
            font=("Arial", 9, "bold")
        )
        self.ai_badge_lbl.pack(side=tk.RIGHT, padx=10)

        # ----------------- Main Resizable PanedWindow -----------------
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=(2, 5))

        # =============================================================
        # LEFT PANE: File Explorer
        # =============================================================
        self.left_frame = ttk.Frame(self.paned, width=300)
        self.paned.add(self.left_frame, weight=1)

        # File Explorer Header
        fe_header = ttk.Frame(self.left_frame)
        fe_header.pack(fill=tk.X, padx=5, pady=(5, 3))
        ttk.Label(fe_header, text=f"{Icons.FOLDER} File Explorer", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        self.progress_lbl = ttk.Label(fe_header, text="", foreground="#007ACC", font=("Arial", 9))
        self.progress_lbl.pack(side=tk.RIGHT)

        # File Search & Filter
        search_filter_f = ttk.Frame(self.left_frame)
        search_filter_f.pack(fill=tk.X, padx=5, pady=2)

        self.fe_search_var = tk.StringVar()
        self.fe_search_var.trace_add("write", lambda *args: self.filter_file_tree())
        fe_search_entry = ttk.Entry(search_filter_f, textvariable=self.fe_search_var)
        fe_search_entry.pack(fill=tk.X, pady=(0, 2))

        self.fe_filter_var = tk.StringVar(value="All Status")
        filter_cb = ttk.Combobox(
            search_filter_f, 
            textvariable=self.fe_filter_var, 
            values=["All Status", "Untranslated", "Completed"], 
            state="readonly"
        )
        filter_cb.pack(fill=tk.X, pady=(0, 2))
        filter_cb.bind('<<ComboboxSelected>>', lambda e: self.filter_file_tree())

        self.asset_filter_var = tk.StringVar(value=AssetClassifier.CATEGORY_LABELS[0])
        asset_cb = ttk.Combobox(
            search_filter_f,
            textvariable=self.asset_filter_var,
            values=AssetClassifier.CATEGORY_LABELS,
            state="readonly"
        )
        asset_cb.pack(fill=tk.X)
        asset_cb.bind('<<ComboboxSelected>>', lambda e: self.filter_file_tree())

        # Treeview for File Explorer
        tree_container = ttk.Frame(self.left_frame)
        tree_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=4)

        self.file_tree = ttk.Treeview(tree_container, selectmode='browse', show='tree')
        fe_v_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.file_tree.yview)
        fe_h_scroll = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.file_tree.xview)
        self.file_tree.configure(yscrollcommand=fe_v_scroll.set, xscrollcommand=fe_h_scroll.set)

        self.file_tree.grid(row=0, column=0, sticky='nsew')
        fe_v_scroll.grid(row=0, column=1, sticky='ns')
        fe_h_scroll.grid(row=1, column=0, sticky='ew')
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        self.file_tree.bind('<<TreeviewSelect>>', self.on_file_tree_select)
        self.file_tree.bind('<<TreeviewOpen>>', self.on_tree_item_open)
        self.file_tree.bind('<Button-3>', self.show_tree_context_menu)  # Right-click context menu

        # Context Menu for Treeview
        self.tree_context_menu = tk.Menu(self, tearoff=0)
        self.tree_context_menu.add_command(label=f"{Icons.STATUS_DONE} Mark as Completed", command=lambda: self.set_context_status("completed"))
        self.tree_context_menu.add_command(label=f"{Icons.STATUS_TODO} Mark as Untranslated", command=lambda: self.set_context_status("untranslated"))

        # =============================================================
        # RIGHT PANE: Editor (Table, Navigation, Search)
        # =============================================================
        self.right_frame = ttk.Frame(self.paned, width=880)
        self.paned.add(self.right_frame, weight=4)

        # File Selection / Current Info Bar
        info_bar = ttk.Frame(self.right_frame)
        info_bar.pack(fill=tk.X, padx=5, pady=(5, 3))

        ttk.Button(info_bar, text=Icons.PREV, width=3, command=self.prev_file).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(info_bar, text=Icons.NEXT, width=3, command=self.next_file).pack(side=tk.LEFT, padx=(0, 6))

        self.cur_file_lbl = ttk.Label(info_bar, text="Loading file...", font=("Arial", 10, "bold"))
        self.cur_file_lbl.pack(side=tk.LEFT)

        # Status Checkbox on Right of info_bar
        status_frame = ttk.Frame(info_bar)
        status_frame.pack(side=tk.RIGHT, padx=5)

        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=(0, 4))
        self.status_done_var = tk.BooleanVar(value=False)
        self.status_chk = ttk.Checkbutton(
            status_frame,
            text=f"{Icons.STATUS_TODO} Untranslated",
            variable=self.status_done_var,
            command=self.on_status_checkbox_toggled
        )
        self.status_chk.pack(side=tk.LEFT)

        # AI Diff Review Banner Bar (shown only when pending AI translations exist)
        self.review_bar = tk.Frame(self.right_frame, bg="#E6FFEC", relief="solid", bd=1, padx=6, pady=4)
        
        self.review_info_lbl = tk.Label(
            self.review_bar, 
            text=f"{Icons.SEARCH} AI Translation changes ready for review:", 
            bg="#E6FFEC", 
            fg="#155724", 
            font=("Segoe UI", 9, "bold")
        )
        self.review_info_lbl.pack(side=tk.LEFT, padx=5)

        self.review_discard_all_btn = ttk.Button(
            self.review_bar, 
            text=f"{Icons.DISCARD} Discard All", 
            command=self.discard_all_ai_diffs
        )
        self.review_discard_all_btn.pack(side=tk.RIGHT, padx=4)

        self.review_accept_all_btn = ttk.Button(
            self.review_bar, 
            text=f"{Icons.ACCEPT} Accept All", 
            command=self.accept_all_ai_diffs
        )
        self.review_accept_all_btn.pack(side=tk.RIGHT, padx=4)

        # =============================================================
        # Workspace 1: Dialogue Text Editor (Table + Search + Inspector)
        # =============================================================
        self.text_editor_container = ttk.Frame(self.right_frame)
        self.text_editor_container.pack(fill=tk.BOTH, expand=True)

        # Search Bar
        self.search_frame = ttk.Frame(self.text_editor_container)
        self.search_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(self.search_frame, text="Search Text:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind('<KeyRelease>', self.search_text)

        ttk.Button(self.search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=3)

        nav_frame = ttk.Frame(self.search_frame)
        nav_frame.pack(side=tk.LEFT, padx=6)
        ttk.Button(nav_frame, text=Icons.UP, width=2, command=self.prev_search_result).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text=Icons.DOWN, width=2, command=self.next_search_result).pack(side=tk.LEFT)

        self.search_status = ttk.Label(self.search_frame, text="")
        self.search_status.pack(side=tk.LEFT, padx=5)

        # Paned Window for Table + Live Dialogue Inspector
        self.right_paned = ttk.PanedWindow(self.text_editor_container, orient=tk.VERTICAL)
        self.right_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # Upper Pane: Main Table (Treeview)
        table_frame = ttk.Frame(self.right_paned)
        self.right_paned.add(table_frame, weight=3)

        self.table = ttk.Treeview(
            table_frame, 
            columns=('index', 'accept', 'orig_text', 'trans_text'), 
            show='headings', 
            selectmode='browse'
        )

        self.table.heading('index', text='Line')
        self.table.column('index', width=45, minwidth=45, anchor='center', stretch=False)

        self.table.heading('accept', text=Icons.ACCEPT, command=self.accept_all_ai_diffs)
        self.table.column('accept', width=35, minwidth=35, anchor='center', stretch=False)

        self.table.heading('orig_text', text='Original (English)')
        self.table.column('orig_text', width=400, minwidth=250, anchor='w', stretch=False)

        self.table.heading('trans_text', text='Translation')
        self.table.column('trans_text', width=450, minwidth=250, anchor='w', stretch=True)

        v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.table.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.table.xview)
        self.table.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.table.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.table.bind('<Double-1>', self.on_double_click)
        self.table.bind('<Button-1>', self.on_table_click)
        self.table.bind('<Motion>', self.on_table_motion)
        self.table.bind('<Button-3>', self.show_table_context_menu)
        self.table.bind('<<TreeviewSelect>>', self.on_table_select)
        self.table.bind('<Return>', lambda e: self.open_current_selected_edit_dialog())

        def _on_shift_mousewheel(event):
            if event.delta:
                self.table.xview_scroll(int(-1 * (event.delta / 120)), "units")
        self.table.bind('<Shift-MouseWheel>', _on_shift_mousewheel)

        # Context menu for Table
        self.table_context_menu = tk.Menu(self, tearoff=0)

        # Git Diff & Table Styling Tags
        self.table.tag_configure("even", background="#FFFFFF", foreground="#000000")
        self.table.tag_configure("odd", background="#F3F5F8", foreground="#000000")
        self.table.tag_configure("diff_pending_even", background="#E6FFEC", foreground="#155724")
        self.table.tag_configure("diff_pending_odd", background="#D4EDDA", foreground="#155724")
        self.table.tag_configure("search_highlight", background="#FFF59D", foreground="#000000")
        self.table.tag_configure("tag_error", background="#FFCDD2", foreground="#900C3F")
        self.table.tag_configure("tag_warning", background="#FFF3E0", foreground="#E65100")

        # Lower Pane: Live Dialogue Inspector (Syntax Highlight Preview)
        self.inspector_visible = True
        self.inspector_frame = ttk.LabelFrame(
            self.right_paned, 
            text=f" {Icons.EDIT} Dialogue Inspector & Syntax Highlight ", 
            padding=(6, 4)
        )
        self.right_paned.add(self.inspector_frame, weight=1)

        insp_header = ttk.Frame(self.inspector_frame)
        insp_header.pack(fill=tk.X, pady=(0, 2))

        self.inspector_title_lbl = ttk.Label(
            insp_header, 
            text="Select a table line to view dialogue syntax highlighting.", 
            font=("Segoe UI", 9, "bold")
        )
        self.inspector_title_lbl.pack(side=tk.LEFT)

        self.inspector_tag_lbl = ttk.Label(insp_header, text="", font=("Segoe UI", 9))
        self.inspector_tag_lbl.pack(side=tk.LEFT, padx=12)

        self.inspector_edit_btn = ttk.Button(
            insp_header, 
            text=f"{Icons.EDIT} Edit Line", 
            command=self.open_current_selected_edit_dialog
        )
        self.inspector_edit_btn.pack(side=tk.RIGHT)

        insp_content = ttk.Frame(self.inspector_frame)
        insp_content.pack(fill=tk.BOTH, expand=True)
        insp_content.grid_columnconfigure(0, weight=1)
        insp_content.grid_columnconfigure(1, weight=1)
        insp_content.grid_rowconfigure(1, weight=1)

        ttk.Label(insp_content, text="Original (English):", font=("Segoe UI", 8, "bold"), foreground="#555555").grid(row=0, column=0, sticky=tk.W, padx=2)
        ttk.Label(insp_content, text="Translation:", font=("Segoe UI", 8, "bold"), foreground="#555555").grid(row=0, column=1, sticky=tk.W, padx=2)

        self.inspector_orig_box = ScrolledText(insp_content, wrap=tk.WORD, height=3, font=("Consolas", 10), background="#F8F9FA")
        self.inspector_orig_box.grid(row=1, column=0, sticky="nsew", padx=(0, 3), pady=1)
        DialogueSyntaxHighlighter.configure_tags(self.inspector_orig_box)
        self.inspector_orig_box.config(state=tk.DISABLED)

        self.inspector_trans_box = ScrolledText(insp_content, wrap=tk.WORD, height=3, font=("Consolas", 10), background="#FFFFFF")
        self.inspector_trans_box.grid(row=1, column=1, sticky="nsew", padx=(3, 0), pady=1)
        DialogueSyntaxHighlighter.configure_tags(self.inspector_trans_box)
        self.inspector_trans_box.config(state=tk.DISABLED)

        self.inspector_orig_box.bind("<Double-1>", lambda e: self.open_current_selected_edit_dialog())
        self.inspector_trans_box.bind("<Double-1>", lambda e: self.open_current_selected_edit_dialog())

        # Bottom Bar for Text Editor
        bottom_frame = ttk.Frame(self.text_editor_container)
        bottom_frame.pack(fill=tk.X, padx=5, pady=4)

        ttk.Button(bottom_frame, text="Add Line", command=self.add_line).pack(side=tk.LEFT)
        ttk.Button(bottom_frame, text="Remove Line", command=self.remove_line).pack(side=tk.LEFT, padx=5)
        self.toggle_inspector_btn = ttk.Button(bottom_frame, text="Hide Inspector", command=self.toggle_inspector)
        self.toggle_inspector_btn.pack(side=tk.LEFT, padx=5)

        self.info_status_lbl = ttk.Label(bottom_frame, text="Ready.", foreground="green")
        self.info_status_lbl.pack(side=tk.RIGHT, padx=10)

        # =============================================================
        # Workspace 2: Texture & Image Localization Viewer
        # =============================================================
        self.texture_viewer = TextureViewer(self.right_frame, on_status_change=self.on_texture_status_change)
        log.debug("Layout created with multi-workspace support.")

    # ----------------- File Loading & Tree Building -----------------
    def open_romfs(self):
        folder_path = filedialog.askdirectory(title="Select RomFS Dump Folder (containing 'arc' folder)")
        if folder_path:
            self.load_romfs_directory(folder_path)

    def load_romfs_directory(self, romfs_path: str):
        romfs_path = os.path.abspath(romfs_path)
        log.info(f"Opening RomFS directory: {romfs_path}")

        trpfd = os.path.join(romfs_path, "arc", "data.trpfd")
        if not os.path.exists(trpfd):
            messagebox.showerror(
                "Invalid RomFS", 
                f"Selected folder does not contain 'arc/data.trpfd':\n{romfs_path}\n\nPlease select the root directory of the dumped RomFS."
            )
            return

        self.info_status_lbl.config(text=f"{Icons.SYNC} Loading RomFS...", foreground="#007ACC")
        self.update_idletasks()

        def _worker():
            t0 = time.time()
            ok, msg = self.trpfs_client.load_romfs(romfs_path)
            if not ok:
                try:
                    self.after(0, lambda: messagebox.showerror("Failed to Load RomFS", msg))
                    self.after(0, lambda: self.info_status_lbl.config(text=f"{Icons.DISCARD} Failed to load RomFS", foreground="red"))
                except Exception:
                    pass
                return

            raw_files = self.trpfs_client.list_files("message/dat/English")
            log.info(f"Retrieved {len(raw_files)} files from RomFS in {(time.time()-t0)*1000:.1f}ms")

            try:
                self.after(0, lambda: self._on_romfs_files_loaded(romfs_path, raw_files, t0))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_romfs_files_loaded(self, romfs_path: str, raw_files: List[Dict[str, str]], t0: float):
        self.is_romfs_mode = True
        self.current_romfs_path = romfs_path
        self.file_items = []
        db_statuses = self.db.get_all_file_statuses()

        prefix = "message/dat/English/"
        for item in raw_files:
            vpath = item["rel_path"]
            fname = item["filename"]

            # Filter to dialogue .dat files (skip internal Game Freak .tbl tables)
            if not fname.lower().endswith(".dat"):
                continue

            if vpath.startswith(prefix):
                disp_rel = vpath[len(prefix):]
            else:
                disp_rel = vpath

            atype = AssetClassifier.get_asset_type(fname)
            db_info = db_statuses.get(fname)
            if db_info:
                status = db_info["status"]
                diffs = db_info["diffs"]
                total = db_info["total_lines"]
                status_override = db_info.get("status_override")
                is_manual = db_info.get("is_manual", False)
            else:
                status = "untranslated"
                diffs = 0
                total = 0
                status_override = None
                is_manual = False

            self.file_items.append({
                "filename": fname,
                "rel_path": disp_rel,
                "romfs_path": vpath,
                "dat_path": vpath,
                "file_path": vpath,
                "asset_type": atype,
                "status": status,
                "diffs": diffs,
                "total": total,
                "status_override": status_override,
                "is_manual": is_manual,
                "is_virtual": True,
                "file_hash": item["hash"]
            })

        dt = (time.time() - t0) * 1000
        self.save_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        self.import_btn.config(state=tk.NORMAL)
        self.ai_btn.config(state=tk.NORMAL)

        self.update_progress_summary()
        self.populate_file_tree()

        self.info_status_lbl.config(
            text=f"{Icons.ROMFS} RomFS active ({len(self.file_items)} .dat files, {dt:.0f}ms)", 
            foreground="#2E7D32"
        )
        log.info(f"RomFS populated with {len(self.file_items)} files in {dt:.1f}ms")

        if self.file_items:
            self.load_file(0)

    def open_folder(self):
        folder_path = filedialog.askdirectory(title="Select Game Folder (.dat or Assets)")
        if folder_path:
            self.load_directory(folder_path)

    def load_directory(self, folder_path: str):
        # Auto-detect if user pointed to a RomFS dump folder
        if os.path.exists(os.path.join(folder_path, "arc", "data.trpfd")):
            log.info(f"Detected RomFS dump in {folder_path}, switching to load_romfs_directory.")
            self.load_romfs_directory(folder_path)
            return

        self.is_romfs_mode = False
        log.info(f"Scanning folder: {folder_path}")
        t0 = time.time()
        self.file_items = []
        db_statuses = self.db.get_all_file_statuses()

        try:
            for root, _, files in os.walk(folder_path):
                for f in sorted(files):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in AssetClassifier.EXT_MAP:
                        full_p = os.path.join(root, f)
                        rel = os.path.relpath(full_p, folder_path)
                        atype = AssetClassifier.get_asset_type(f)

                        db_info = db_statuses.get(f)
                        if db_info:
                            status = db_info["status"]
                            diffs = db_info["diffs"]
                            total = db_info["total_lines"]
                            status_override = db_info.get("status_override")
                            is_manual = db_info.get("is_manual", False)
                        else:
                            if atype == AssetType.TEXTURE:
                                trans_p = self.get_translated_asset_path(rel)
                                has_trans = bool(trans_p and os.path.exists(trans_p) and os.path.getsize(trans_p) > 0)
                                status = "completed" if has_trans else "untranslated"
                            else:
                                status = "untranslated"
                            diffs = 0
                            total = 0
                            status_override = None
                            is_manual = False

                        self.file_items.append({
                            "filename": f,
                            "rel_path": rel,
                            "dat_path": full_p,
                            "file_path": full_p,
                            "asset_type": atype,
                            "status": status,
                            "diffs": diffs,
                            "total": total,
                            "status_override": status_override,
                            "is_manual": is_manual
                        })
        except Exception as e:
            log.error(f"Error scanning folder {folder_path}: {e}", exc_info=True)
            messagebox.showerror("Error", f"Failed to read folder:\n{e}")
            return

        elapsed = time.time() - t0
        log.info(f"Scanned {len(self.file_items)} files in {elapsed*1000:.1f}ms (loaded from SQLite)")

        if not self.file_items:
            messagebox.showerror("Error", "No supported game files found in selected folder")
            return


        self.save_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        self.import_btn.config(state=tk.NORMAL)
        self.ai_btn.config(state=tk.NORMAL)

        # Update progress summary badge
        self.update_progress_summary()

        self.populate_file_tree()

        if self.file_items:
            self.load_file(0)

    def update_progress_summary(self):
        c_done = sum(1 for it in self.file_items if it.get("status") == "completed")
        c_untr = len(self.file_items) - c_done
        self.progress_lbl.config(text=f"{Icons.STATUS_DONE} {c_done}  {Icons.STATUS_TODO} {c_untr}")

    def populate_file_tree(self):
        log.debug("Populating file tree with virtual lazy loading...")
        t0 = time.time()

        # 1. Save existing folder open/collapse states
        open_states = {}
        for r in self.file_tree.get_children():
            text = self.file_tree.item(r, "text")
            if self.file_tree.get_children(r) or text.startswith(Icons.FOLDER):
                open_states[text] = bool(self.file_tree.item(r, "open"))
            self.file_tree.delete(r)
        self.tree_item_to_index.clear()
        self._folder_pending_items.clear()

        query = self.fe_search_var.get().lower().strip()
        filter_mode = self.fe_filter_var.get()
        asset_cat = self.asset_filter_var.get() if hasattr(self, 'asset_filter_var') else "All Files"

        # Separate items into matching groups
        folder_groups: Dict[str, List[int]] = {}
        root_items: List[int] = []
        is_search_active = bool(query)

        for idx, item in enumerate(self.file_items):
            rel = item["rel_path"].replace("/", os.sep)
            stat = item.get("status", "untranslated")

            # Filtering
            if query and query not in item["filename"].lower() and query not in rel.lower():
                continue
            if ("Untranslated" in filter_mode or "Belum" in filter_mode) and stat != "untranslated":
                continue
            if ("Completed" in filter_mode or "Sudah" in filter_mode) and stat != "completed":
                continue
            if not AssetClassifier.matches_category_filter(item["filename"], asset_cat):
                continue

            parts = rel.split(os.sep)
            if len(parts) > 1:
                folder_name = parts[0]
                if folder_name not in folder_groups:
                    folder_groups[folder_name] = []
                folder_groups[folder_name].append(idx)
            else:
                root_items.append(idx)

        # Insert root level files directly
        for idx in root_items:
            item = self.file_items[idx]
            item_text = self._get_tree_item_text(item)
            leaf_id = self.file_tree.insert('', 'end', text=item_text)
            self.tree_item_to_index[leaf_id] = idx

        # Determine which folder to expand by default
        first_folder = list(folder_groups.keys())[0] if folder_groups else None

        # Insert folder nodes with on-demand lazy child loading
        for folder_name, indices in folder_groups.items():
            folder_text = f"{Icons.FOLDER} {folder_name}"
            if is_search_active:
                was_open = True
            elif open_states:
                was_open = open_states.get(folder_text, False)
            else:
                # Default: active first folder open, other folders collapsed
                was_open = (folder_name == first_folder)

            node_id = self.file_tree.insert('', 'end', text=folder_text, open=was_open)

            if was_open:
                # Render children directly for open folder
                for idx in indices:
                    item = self.file_items[idx]
                    item_text = self._get_tree_item_text(item)
                    leaf_id = self.file_tree.insert(node_id, 'end', text=item_text)
                    self.tree_item_to_index[leaf_id] = idx
            else:
                # Virtual Lazy-Loading: Add placeholder dummy child
                self.file_tree.insert(node_id, 'end', text="__dummy__")
                self._folder_pending_items[node_id] = indices

        log.debug(f"Populated tree with {len(self.tree_item_to_index)} visible items in {(time.time()-t0)*1000:.1f}ms")

    def _get_tree_item_text(self, item: Dict[str, Any]) -> str:
        """Returns the formatted item label with icon, reflecting active background AI tasks or pending review diffs."""
        fname = item.get("filename", "")
        if fname in getattr(self, "active_ai_tasks", {}):
            status_icon = Icons.SYNC
        elif fname in getattr(self, "file_pending_ai_diffs", {}) and self.file_pending_ai_diffs[fname]:
            status_icon = Icons.AI_SPARKLE
        else:
            status_icon, _, _ = StatusTracker.get_display_info(
                item.get("status", "untranslated"), 
                item.get("diffs", 0), 
                item.get("total", 0), 
                is_manual=item.get("is_manual", False)
            )
        return f"{status_icon} {fname}"

    def on_tree_item_open(self, event=None):
        """Lazy load children when a folder node is expanded."""
        if not hasattr(self, "_folder_pending_items") or not self._folder_pending_items:
            return

        to_remove = []
        for node_id, indices in self._folder_pending_items.items():
            try:
                if self.file_tree.item(node_id, "open"):
                    children = self.file_tree.get_children(node_id)
                    for ch in children:
                        if self.file_tree.item(ch, "text") == "__dummy__":
                            self.file_tree.delete(ch)
                    for idx in indices:
                        item = self.file_items[idx]
                        item_text = self._get_tree_item_text(item)
                        leaf_id = self.file_tree.insert(node_id, 'end', text=item_text)
                        self.tree_item_to_index[leaf_id] = idx
                    to_remove.append(node_id)
            except Exception:
                pass

        for nid in to_remove:
            if nid in self._folder_pending_items:
                del self._folder_pending_items[nid]

    def filter_file_tree(self):
        self.populate_file_tree()

    def update_tree_item_display(self, index: int):
        """Update just a single item's icon/text in the tree without touching folder open/close states."""
        if index < 0 or index >= len(self.file_items):
            return
        item = self.file_items[index]
        stat = item.get("status", "untranslated")
        item_text = self._get_tree_item_text(item)

        filter_mode = self.fe_filter_var.get()
        # If active filter would hide this item, refresh the whole tree (with open_states preserved)
        if (("Untranslated" in filter_mode or "Belum" in filter_mode) and stat != "untranslated") or \
           (("Completed" in filter_mode or "Sudah" in filter_mode) and stat != "completed"):
            self.populate_file_tree()
            return

        # Otherwise update node in-place without rebuilding tree
        for node_id, idx in self.tree_item_to_index.items():
            if idx == index:
                self.file_tree.item(node_id, text=item_text)
                break

    def show_tree_context_menu(self, event):
        item_id = self.file_tree.identify_row(event.y)
        if item_id and item_id in self.tree_item_to_index:
            self._context_item_idx = self.tree_item_to_index[item_id]
            self.tree_context_menu.post(event.x_root, event.y_root)

    def set_context_status(self, override: Optional[str]):
        idx = getattr(self, "_context_item_idx", self.current_file_index)
        if 0 <= idx < len(self.file_items):
            self.apply_status_override(idx, override)

    def update_status_selector(self, status: str, diffs: int = 0, total: int = 0, is_manual: bool = False, unsaved: bool = False):
        """Update the status checkbox display."""
        is_done = (status == "completed")
        self.status_done_var.set(is_done)
        unsaved_tag = " [Unsaved]" if unsaved else ""
        if hasattr(self, 'status_chk'):
            icon, label_text, _ = StatusTracker.get_display_info(status)
            self.status_chk.config(text=f"{icon} {label_text}{unsaved_tag}")

    def on_status_checkbox_toggled(self):
        if self.current_file_index < 0:
            return
        is_done = self.status_done_var.get()
        override = "completed" if is_done else "untranslated"
        if hasattr(self, 'status_chk'):
            icon, label_text, _ = StatusTracker.get_display_info(override)
            self.status_chk.config(text=f"{icon} {label_text}")
        self.apply_status_override(self.current_file_index, override)

    def apply_status_override(self, index: int, override: Optional[str]):
        item = self.file_items[index]
        atype = item.get("asset_type", AssetType.TEXT)
        if atype != AssetType.TEXT:
            eff_status = override if override else "untranslated"
            is_manual = bool(override)
            self.db.upsert_asset_file(item["filename"], item["rel_path"], eff_status, atype)
        else:
            eff_status, is_manual = self.db.set_file_status_override(
                item["filename"], 
                item["rel_path"], 
                override
            )
        item["status"] = eff_status
        item["is_manual"] = is_manual
        item["status_override"] = override

        # If this is currently active file, update unified selector
        if index == self.current_file_index:
            self.update_status_selector(
                eff_status, 
                diffs=item.get("diffs", 0), 
                total=item.get("total", 0), 
                is_manual=is_manual
            )
            if atype == AssetType.TEXTURE and hasattr(self, 'texture_viewer'):
                trans_p = self.get_translated_asset_path(item["rel_path"])
                file_p = item.get("file_path", item.get("dat_path"))
                self.texture_viewer.load_texture(file_p, trans_p, item)

        # Refresh progress and update tree item in-place (no folder reset!)
        self.update_progress_summary()
        self.update_tree_item_display(index)
        log.info(f"Status override applied for {item['filename']}: {override} -> {eff_status}")

    def get_translated_asset_path(self, rel_path: str) -> str:
        return os.path.join(self.mod_assets_dir, rel_path)

    def on_texture_status_change(self, is_done: bool):
        if self.current_file_index < 0 or self.current_file_index >= len(self.file_items):
            return
        override = "completed" if is_done else "untranslated"
        self.apply_status_override(self.current_file_index, override)

    def on_file_tree_select(self, event):
        # Prevent recursive event execution
        if self._syncing_tree:
            return

        selected = self.file_tree.selection()
        if not selected:
            return
        node_id = selected[0]
        if node_id in self.tree_item_to_index:
            idx = self.tree_item_to_index[node_id]
            # Only trigger load if selecting a DIFFERENT file
            if idx != self.current_file_index:
                log.info(f"User clicked tree item #{idx}: {self.file_items[idx]['filename']}")
                self.load_file(idx)

    def load_file(self, index: int):
        if index < 0 or index >= len(self.file_items):
            log.warning(f"load_file called with invalid index: {index}")
            return

        # Preserve currently unreviewed AI diffs for previous file in multi-file staging cache
        if self.pending_ai_diffs and self.current_file_index >= 0 and self.current_file_index != index:
            cur_fname = self.file_items[self.current_file_index]['filename']
            self.file_pending_ai_diffs[cur_fname] = dict(self.pending_ai_diffs)
            self.update_tree_item_display(self.current_file_index)

        t0 = time.time()
        self.current_file_index = index
        item = self.file_items[index]
        target_fname = item["filename"]

        # Restore pending AI diffs for target file if any exist in staging cache
        if target_fname in getattr(self, "file_pending_ai_diffs", {}) and self.file_pending_ai_diffs[target_fname]:
            self.pending_ai_diffs = dict(self.file_pending_ai_diffs[target_fname])
        else:
            self.pending_ai_diffs = {}

        self.update_review_bar()
        atype = item.get("asset_type", AssetType.TEXT)
        log.info(f"Loading file [{index + 1}/{len(self.file_items)}]: {item['rel_path']} (Type: {atype})")

        # ----------------- Texture / Image Asset Branch -----------------
        if atype == AssetType.TEXTURE:
            if hasattr(self, 'text_editor_container'):
                self.text_editor_container.pack_forget()
            if hasattr(self, 'review_bar') and self.review_bar.winfo_ismapped():
                self.review_bar.pack_forget()
            if hasattr(self, 'texture_viewer'):
                self.texture_viewer.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
                trans_p = self.get_translated_asset_path(item["rel_path"])
                file_p = item.get("file_path", item.get("dat_path"))
                if item.get("is_virtual") and (not file_p or not os.path.exists(file_p)):
                    cache_dir = os.path.join(self.db.project_dir, "romfs_cache")
                    cache_orig_p = os.path.join(cache_dir, item["rel_path"])
                    os.makedirs(os.path.dirname(cache_orig_p), exist_ok=True)
                    if not os.path.exists(cache_orig_p):
                        self.trpfs_client.extract_file_to_disk(item.get("romfs_path", item["rel_path"]), cache_orig_p)
                    file_p = cache_orig_p
                self.texture_viewer.load_texture(file_p, trans_p, item)

            self.ai_btn.config(state=tk.DISABLED)
            self.save_btn.config(state=tk.DISABLED)
            self.export_btn.config(state=tk.DISABLED)
            self.import_btn.config(state=tk.DISABLED)
            self.cur_file_lbl.config(text=f"Image: {item['rel_path']}")
            self.update_status_selector(item["status"], is_manual=item.get("is_manual", False))
            self._sync_tree_selection(index)
            log.debug(f"Texture {item['filename']} loaded in {(time.time()-t0)*1000:.1f}ms")
            return

        # ----------------- Unsupported / Binary Asset Branch -----------------
        if atype not in (AssetType.TEXT, AssetType.TEXTURE):
            if hasattr(self, 'text_editor_container'):
                self.text_editor_container.pack_forget()
            if hasattr(self, 'texture_viewer'):
                self.texture_viewer.pack_forget()
            if hasattr(self, 'review_bar') and self.review_bar.winfo_ismapped():
                self.review_bar.pack_forget()
            self.ai_btn.config(state=tk.DISABLED)
            self.save_btn.config(state=tk.DISABLED)
            self.export_btn.config(state=tk.DISABLED)
            self.import_btn.config(state=tk.DISABLED)
            self.cur_file_lbl.config(text=f"Binary File: {item['rel_path']}")
            self.info_status_lbl.config(
                text=f"File format {atype.value} is not supported for editing as dialogue text.", 
                foreground="#721C24"
            )
            self._sync_tree_selection(index)
            return

        # ----------------- Dialogue Text Branch (.dat) -----------------
        if hasattr(self, 'texture_viewer'):
            self.texture_viewer.pack_forget()
        if hasattr(self, 'text_editor_container'):
            self.text_editor_container.pack(fill=tk.BOTH, expand=True)

        # Check if this file is actively being translated in background
        if item["filename"] in getattr(self, "active_ai_tasks", {}):
            self.ai_btn.config(state=tk.DISABLED, text=f"{Icons.SYNC} Translating...")
            task_info = self.active_ai_tasks[item["filename"]]
            self.info_status_lbl.config(
                text=task_info.get("progress_text", "Translating with AI..."), 
                foreground="#007ACC"
            )
        else:
            self.ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate AI")

        self.save_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        self.import_btn.config(state=tk.NORMAL)

        # 1. Check if SQLite already has this file's data (including preserved original English)
        db_data = self.db.get_file_full_data(item["filename"])
        if db_data is not None:
            db_orig, db_trans = db_data
            self.current_orig_lines = list(db_orig)
            self.current_trans_lines = list(db_trans)
        else:
            try:
                if item.get("is_virtual"):
                    vtarget = item.get("romfs_path", item["rel_path"])
                    raw_bytes = self.trpfs_client.extract_file_bytes(vtarget)
                    if raw_bytes is None:
                        raise ValueError(f"Failed to extract virtual file from RomFS: {item['filename']}")
                    self.current_orig_lines = self.codec.decode_bytes(raw_bytes)
                else:
                    self.current_orig_lines = self.codec.read_file(item["dat_path"])
            except Exception as e:
                log.error(f"Failed to decode binary .dat file {item['filename']}: {e}", exc_info=True)
                messagebox.showerror("Error", f"Failed to load .dat: {e}")
                return
            self.current_trans_lines = list(self.current_orig_lines)

        # Recalculate status for current file
        stat, diffs, total = StatusTracker.calculate_status(self.current_orig_lines, self.current_trans_lines)
        item["diffs"] = diffs
        item["total"] = total
        
        # If not manually overridden, update item status to calculated
        if not item.get("is_manual", False):
            item["status"] = stat

        self.update_table_display()
        self.update_review_bar()

        if self.pending_ai_diffs:
            meta = getattr(self, "file_pending_ai_meta", {}).get(target_fname, {})
            tm_hits = meta.get("tm_hits", 0)
            tm_info = f" ({tm_hits} lines via TM)" if tm_hits else ""
            self.info_status_lbl.config(
                text=f"{Icons.SEARCH} {len(self.pending_ai_diffs)} AI translated line(s) ready for review{tm_info} (click {Icons.ACCEPT} per line or Accept All)", 
                foreground="#155724"
            )

        self.cur_file_lbl.config(text=f"File: {item['rel_path']}")
        self.update_status_selector(
            item["status"], 
            diffs=diffs, 
            total=total, 
            is_manual=item.get("is_manual", False)
        )

        # Initialize undo/redo history for this file
        self.undo_stack = []
        self.redo_stack = []
        self._update_undo_buttons()

        # Synchronize selection in file_tree WITHOUT triggering recursive events
        self._sync_tree_selection(index)

        log.debug(f"File {item['filename']} loaded successfully in {(time.time()-t0)*1000:.1f}ms")

    def _sync_tree_selection(self, index: int):
        if not self._syncing_tree:
            self._syncing_tree = True
            try:
                for node_id, idx in self.tree_item_to_index.items():
                    if idx == index:
                        current_sel = self.file_tree.selection()
                        if not current_sel or current_sel[0] != node_id:
                            self.file_tree.selection_set(node_id)
                            self.file_tree.see(node_id)
                        break
            finally:
                self._syncing_tree = False

    def update_table_display(self):
        for row in self.table.get_children():
            self.table.delete(row)

        max_pending = (max(self.pending_ai_diffs.keys()) + 1) if self.pending_ai_diffs else 0
        any_fixable_errors = False
        max_len = max(len(self.current_orig_lines), len(self.current_trans_lines), max_pending)
        for i in range(max_len):
            orig = self.current_orig_lines[i] if i < len(self.current_orig_lines) else ""
            
            is_pending = (i in self.pending_ai_diffs)
            if is_pending:
                trans = self.pending_ai_diffs[i]
                accept_sym = Icons.ACCEPT
                row_tag = "diff_pending_even" if i % 2 == 0 else "diff_pending_odd"
            else:
                trans = self.current_trans_lines[i] if i < len(self.current_trans_lines) else ""
                accept_sym = ""
                row_tag = "even" if i % 2 == 0 else "odd"

            diag = TagGuard.validate_line_diagnostics(orig, trans)
            if not diag["is_valid"]:
                tags = (row_tag, "tag_error")
                if diag["can_auto_fix"]:
                    any_fixable_errors = True
            elif diag["warnings"]:
                tags = (row_tag, "tag_warning")
            else:
                tags = (row_tag,)

            self.table.insert('', 'end', values=(i, accept_sym, orig, trans), tags=tags)

        if hasattr(self, 'qa_fix_btn'):
            self.qa_fix_btn.config(state=tk.NORMAL if any_fixable_errors else tk.DISABLED)

        # Auto-calculate comfortable column widths based on longest text
        try:
            font = tkfont.nametofont("TkDefaultFont")
            orig_widths = [font.measure(l) for l in self.current_orig_lines] if self.current_orig_lines else [350]
            
            # Include pending translations in width estimation so text doesn't truncate
            all_trans = list(self.current_trans_lines)
            for idx, p_text in self.pending_ai_diffs.items():
                while len(all_trans) <= idx:
                    all_trans.append("")
                all_trans[idx] = p_text
            trans_widths = [font.measure(l) for l in all_trans] if all_trans else [400]

            min_orig_w = max(max(orig_widths) + 40, 350)
            min_trans_w = max(max(trans_widths) + 40, 400)

            self.table.column('index', width=45, minwidth=45, anchor='center', stretch=False)
            self.table.column('accept', width=35, minwidth=35, anchor='center', stretch=False)
            self.table.column('orig_text', width=min_orig_w, minwidth=min_orig_w, stretch=False)
            self.table.column('trans_text', width=min_trans_w, minwidth=min_trans_w, stretch=True)
        except Exception as e:
            log.warning(f"Failed to auto-adjust column widths: {e}")

        # Refresh Live Dialogue Inspector
        if hasattr(self, 'inspector_frame') and self.inspector_visible:
            selected = self.table.selection()
            if selected:
                self.on_table_select()
            elif self.table.get_children():
                first_row = self.table.get_children()[0]
                self.table.selection_set(first_row)
                self.on_table_select()
            else:
                self.clear_inspector()

    def prev_file(self):
        if self.current_file_index > 0:
            self.load_file(self.current_file_index - 1)

    def next_file(self):
        if self.current_file_index < len(self.file_items) - 1:
            self.load_file(self.current_file_index + 1)

    # ----------------- Live Dialogue Inspector Logic -----------------
    def toggle_inspector(self):
        if self.inspector_visible:
            self.right_paned.forget(self.inspector_frame)
            self.inspector_visible = False
            self.toggle_inspector_btn.config(text="Show Inspector")
        else:
            self.right_paned.add(self.inspector_frame, weight=1)
            self.inspector_visible = True
            self.toggle_inspector_btn.config(text="Hide Inspector")
            self.on_table_select()

    def on_table_select(self, event=None):
        selected = self.table.selection()
        if not selected:
            self.clear_inspector()
            return
        item_id = selected[0]
        vals = self.table.item(item_id, 'values')
        if not vals or len(vals) < 4:
            self.clear_inspector()
            return
        try:
            line_idx = int(vals[0])
            orig = str(vals[2])
            trans = str(vals[3])
            self.update_inspector(line_idx, orig, trans)
        except (ValueError, IndexError):
            self.clear_inspector()

    def update_inspector(self, line_idx: int, orig_text: str, trans_text: str):
        if not hasattr(self, 'inspector_orig_box'):
            return
        self.inspector_title_lbl.config(text=f"{Icons.EDIT} Dialogue Line {line_idx}")
        DialogueSyntaxHighlighter.set_text_with_highlight(self.inspector_orig_box, orig_text, editable=False)
        DialogueSyntaxHighlighter.set_text_with_highlight(self.inspector_trans_box, trans_text, editable=False)
        diag = TagGuard.validate_line_diagnostics(orig_text, trans_text)
        if not diag["is_valid"]:
            err_text = " | ".join(diag["errors"])
            self.inspector_tag_lbl.config(text=f"{Icons.ERROR} {err_text[:60]}", foreground="#C62828")
        elif diag["warnings"]:
            warn_text = " | ".join(diag["warnings"])
            self.inspector_tag_lbl.config(text=f"{Icons.WARNING} {warn_text[:60]}", foreground="#E65100")
        else:
            self.inspector_tag_lbl.config(text=f"{Icons.ACCEPT} Tags Match", foreground="#2E7D32")


    def clear_inspector(self):
        if not hasattr(self, 'inspector_orig_box'):
            return
        self.inspector_title_lbl.config(text="Select a table line to view dialogue syntax highlighting.")
        self.inspector_tag_lbl.config(text="")
        DialogueSyntaxHighlighter.set_text_with_highlight(self.inspector_orig_box, "", editable=False)
        DialogueSyntaxHighlighter.set_text_with_highlight(self.inspector_trans_box, "", editable=False)

    def open_current_selected_edit_dialog(self):
        selected = self.table.selection()
        if not selected:
            return
        item_id = selected[0]
        vals = self.table.item(item_id, 'values')
        if not vals or len(vals) < 4:
            return
        try:
            line_idx = int(vals[0])
            orig = str(vals[2])
            trans = str(vals[3])
            self.open_edit_dialog(line_idx, orig, trans, item_id)
        except (ValueError, IndexError):
            pass

    # ----------------- Editing Dialog (Double Click) -----------------
    def on_double_click(self, event):
        col = self.table.identify_column(event.x)
        if col == "#2":
            # Clicked directly on the accept column; let on_table_click handle accepting
            return
        selected = self.table.selection()
        if not selected:
            return
        item_id = selected[0]
        values = self.table.item(item_id, 'values')
        line_idx = int(values[0])
        orig_text = values[2]
        trans_text = values[3]

        self.open_edit_dialog(line_idx, orig_text, trans_text, item_id)

    def open_edit_dialog(self, line_idx: int, orig_text: str, trans_text: str, item_id):
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Line {line_idx}")
        dialog.geometry("640x480")
        dialog.transient(self)
        dialog.grab_set()

        # Original English Reference Box
        ttk.Label(dialog, text=f"Line {line_idx} - Original English:", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(8, 2))
        orig_box = ScrolledText(dialog, wrap=tk.WORD, height=4, background="#F8F9FA", font=("Consolas", 10))
        orig_box.pack(fill=tk.X, padx=10, pady=(0, 6))
        DialogueSyntaxHighlighter.configure_tags(orig_box)
        DialogueSyntaxHighlighter.set_text_with_highlight(orig_box, orig_text, editable=False)

        # Translated Target Language Box
        ttk.Label(dialog, text="Translation:", font=("Arial", 9, "bold")).pack(anchor=tk.W, padx=10, pady=(0, 2))
        trans_box = ScrolledText(dialog, wrap=tk.WORD, height=6, font=("Consolas", 10), undo=True, maxundo=50, autoseparators=True)
        trans_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))
        DialogueSyntaxHighlighter.configure_tags(trans_box)
        DialogueSyntaxHighlighter.set_text_with_highlight(trans_box, trans_text, editable=True)
        DialogueSyntaxHighlighter.bind_live_highlighting(trans_box)

        # Tag Matching Status Label
        validation_lbl = ttk.Label(dialog, text="", font=("Segoe UI", 9))
        validation_lbl.pack(anchor=tk.W, padx=10, pady=(0, 6))

        def validate_tags():
            cur_trans = trans_box.get('1.0', 'end-1c')
            valid, err = TagGuard.validate_line(orig_text, cur_trans)
            if valid:
                validation_lbl.config(text=f"{Icons.ACCEPT} All [VAR] tags and escape symbols match", foreground="#2E7D32")
            else:
                validation_lbl.config(text=f"{Icons.DISCARD} {err}", foreground="#C62828")

        validate_tags()
        trans_box.bind("<KeyRelease>", lambda e: (validation_lbl.after(50, validate_tags)), add="+")

        # Button Frame
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        def copy_text():
            self.clipboard_clear()
            self.clipboard_append(trans_box.get('1.0', tk.END).strip())

        def paste_text():
            trans_box.delete('1.0', tk.END)
            trans_box.insert('1.0', self.clipboard_get().strip())
            DialogueSyntaxHighlighter.highlight(trans_box)
            validate_tags()

        def translate_single():
            ai_btn.config(state=tk.DISABLED, text=f"{Icons.SYNC} Translating...")
            log.info(f"AI Translating single line {line_idx}...")
            def worker():
                try:
                    glossary_block = ""
                    try:
                        glossary_block = self.db.get_glossary_prompt_block()
                    except Exception:
                        pass
                    res = self.ai.translate_lines([orig_text], target_lang="Indonesian", glossary_block=glossary_block)
                    if res:
                        def update():
                            trans_box.delete('1.0', tk.END)
                            trans_box.insert('1.0', res[0])
                            DialogueSyntaxHighlighter.highlight(trans_box)
                            validate_tags()
                            ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate Line")
                        dialog.after(0, update)
                except Exception as e:
                    err_msg = str(e)
                    log.error(f"Single line translation error: {err_msg}", exc_info=True)
                    dialog.after(0, lambda msg=err_msg: (messagebox.showerror("AI Error", msg), ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate Line")))
            threading.Thread(target=worker, daemon=True).start()

        def save_changes():
            raw_text = trans_box.get('1.0', 'end-1c')
            new_text = TagGuard.sanitize_line(orig_text, raw_text)
            if line_idx < len(self.current_trans_lines):
                if self.current_trans_lines[line_idx] != new_text:
                    self.push_undo_state()
                    self.current_trans_lines[line_idx] = new_text
                    if line_idx in self.pending_ai_diffs:
                        del self.pending_ai_diffs[line_idx]
                        self.update_review_bar()
                    valid, _ = TagGuard.validate_line(orig_text, new_text)
                    row_tag = "even" if line_idx % 2 == 0 else "odd"
                    tags = (row_tag,) if valid else (row_tag, "tag_error")
                    self.table.item(item_id, values=(line_idx, "", orig_text, new_text), tags=tags)
                    self.auto_save()
                    self.update_inspector(line_idx, orig_text, new_text)
            dialog.destroy()

        ttk.Button(btn_frame, text="Copy", command=copy_text).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Paste", command=paste_text).pack(side=tk.LEFT, padx=5)
        ai_btn = ttk.Button(btn_frame, text=f"{Icons.AI_SPARKLE} Translate Line", command=translate_single)
        ai_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Cancel (Esc)", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Save (Ctrl+Enter)", command=save_changes).pack(side=tk.RIGHT)

        dialog.bind("<Control-Return>", lambda e: save_changes())
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    def add_line(self):
        self.push_undo_state()
        self.current_orig_lines.append("")
        self.current_trans_lines.append("New line")
        self.update_table_display()
        self.auto_save()

    def remove_line(self):
        selected = self.table.selection()
        if not selected:
            return
        idx = int(self.table.item(selected[0], 'values')[0])
        if messagebox.askyesno("Confirm", f"Delete line {idx}?"):
            self.push_undo_state()
            if idx in self.pending_ai_diffs:
                del self.pending_ai_diffs[idx]
                self.update_review_bar()
            if idx < len(self.current_orig_lines):
                del self.current_orig_lines[idx]
            if idx < len(self.current_trans_lines):
                del self.current_trans_lines[idx]
            self.update_table_display()
            self.auto_save()

    # ----------------- Undo / Redo & Auto-Save -----------------
    def _update_undo_buttons(self):
        can_undo = len(self.undo_stack) > 0
        can_redo = len(self.redo_stack) > 0
        if hasattr(self, 'undo_btn'):
            self.undo_btn.config(state=tk.NORMAL if can_undo else tk.DISABLED)
        if hasattr(self, 'redo_btn'):
            self.redo_btn.config(state=tk.NORMAL if can_redo else tk.DISABLED)

    def push_undo_state(self):
        """Snapshots current translation state into the undo stack before changes."""
        if hasattr(self, 'current_trans_lines') and self.current_trans_lines is not None:
            self.undo_stack.append(list(self.current_trans_lines))
            if len(self.undo_stack) > 50:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self._update_undo_buttons()

    def undo(self, event=None):
        """Revert to the previous translation state."""
        if self.current_file_index < 0:
            return
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, tk.Text, ScrolledText)):
            return  # Allow native widget undo

        if self.undo_stack:
            self.redo_stack.append(list(self.current_trans_lines))
            prev_state = self.undo_stack.pop()
            self.current_trans_lines = list(prev_state)
            self.update_table_display()
            self.auto_save()
            self._update_undo_buttons()
            self.info_status_lbl.config(text=f"{Icons.UNDO} Undo applied & saved", foreground="#007ACC")
            log.info(f"Undo applied for {self.file_items[self.current_file_index]['filename']}")

    def redo(self, event=None):
        """Re-apply the undone translation state."""
        if self.current_file_index < 0:
            return
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, tk.Text, ScrolledText)):
            return  # Allow native widget redo

        if self.redo_stack:
            self.undo_stack.append(list(self.current_trans_lines))
            next_state = self.redo_stack.pop()
            self.current_trans_lines = list(next_state)
            self.update_table_display()
            self.auto_save()
            self._update_undo_buttons()
            self.info_status_lbl.config(text=f"{Icons.REDO} Redo applied & saved", foreground="#007ACC")
            log.info(f"Redo applied for {self.file_items[self.current_file_index]['filename']}")

    def auto_save(self):
        """Silently persist the current translation to .dat and SQLite database."""
        if self.current_file_index < 0:
            return
        self.save_file(silent=True)

    # ----------------- Save, Export, Import -----------------
    def save_file(self, silent: bool = False):
        if self.current_file_index < 0:
            return
        item = self.file_items[self.current_file_index]

        # If user manually clicks Save .dat while there are unaccepted AI translations, ask to accept all
        if self.pending_ai_diffs and not silent:
            res = messagebox.askyesno(
                "Unaccepted AI Changes",
                f"There are {len(self.pending_ai_diffs)} pending AI translated line(s) awaiting review.\n\n"
                "Do you want to Accept All AI changes before saving?"
            )
            if res:
                self.accept_all_ai_diffs()

        try:
            # 1. Backup original .dat if on disk and not yet backed up
            bak_path = item["dat_path"] + ".bak"
            if not item.get("is_virtual") and not os.path.exists(bak_path) and os.path.exists(item["dat_path"]):
                try:
                    import shutil
                    shutil.copy2(item["dat_path"], bak_path)
                    log.info(f"Backup created: {bak_path}")
                except Exception as ex:
                    log.warning(f"Failed to backup {item['dat_path']}: {ex}")

            # 2. Compile to .dat binary
            if not item.get("is_virtual") and os.path.isabs(item["dat_path"]):
                self.codec.write_file(item["dat_path"], self.current_trans_lines)
            else:
                mod_dir = os.path.join(self.db.project_dir, "modified", os.path.dirname(item["rel_path"]))
                os.makedirs(mod_dir, exist_ok=True)
                mod_dat = os.path.join(mod_dir, item["filename"])
                self.codec.write_file(mod_dat, self.current_trans_lines)
                item["dat_path"] = mod_dat
            
            stat, diffs, total, is_manual = self.db.save_file_translation(
                item["filename"], 
                item["rel_path"], 
                self.current_orig_lines, 
                self.current_trans_lines
            )
            item["status"] = stat
            item["diffs"] = diffs
            item["total"] = total
            item["is_manual"] = is_manual

            # 2b. Automatically record translation pairs into Translation Memory (TM)
            if self.current_orig_lines and self.current_trans_lines:
                pairs = list(zip(self.current_orig_lines, self.current_trans_lines))
                self.db.add_batch_tm_entries(pairs, context_file=item["filename"])


            # 3. Update Status Dropdown & Tree in-place
            icon, label_text, _ = StatusTracker.get_display_info(stat, diffs, total, is_manual=is_manual)
            self.update_status_selector(stat, diffs=diffs, total=total, is_manual=is_manual)
            self.update_progress_summary()
            self.update_tree_item_display(self.current_file_index)

            now_str = time.strftime("%H:%M:%S")
            self.info_status_lbl.config(text=f"{Icons.SAVE} Auto-saved ({now_str})", foreground="#2E7D32")
            log.info(f"Successfully compiled and saved {item['filename']} to .dat and SQLite database (silent={silent}).")

            if not silent:
                messagebox.showinfo(
                    "Success", 
                    f"File '{item['filename']}' saved successfully!\nStatus: {icon} {label_text}\nSaved to SQLite Database."
                )
        except Exception as e:
            log.error(f"Failed to save {item['filename']}: {e}", exc_info=True)
            if not silent:
                messagebox.showerror("Error", f"Failed to save file:\n{e}")
            else:
                self.info_status_lbl.config(text=f"{Icons.DISCARD} Auto-save failed: {e}", foreground="red")

    def export_txt(self):
        if self.current_file_index < 0:
            return
        item = self.file_items[self.current_file_index]
        save_path = filedialog.asksaveasfilename(
            title="Export Text File",
            defaultextension=".txt",
            initialfile=f"{item['filename'][:-4]}.txt",
            filetypes=[("Text files", "*.txt")]
        )
        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write("~~~~~~~~~~~~~~~\n")
                f.write(f"Text File: {item['filename']}\n")
                f.write("~~~~~~~~~~~~~~~\n")
                for line in self.current_trans_lines:
                    f.write(line + '\n')
            log.info(f"Exported text to {save_path}")
            messagebox.showinfo("Success", "Text exported successfully")

    def import_txt(self):
        if self.current_file_index < 0:
            return
        file_path = filedialog.askopenfilename(
            title="Import Text File",
            filetypes=[("Text files", "*.txt")]
        )
        if file_path:
            imported = StatusTracker.parse_txt_lines(file_path)
            if imported:
                self.push_undo_state()
                self.current_trans_lines = imported
                self.update_table_display()
                self.auto_save()
                log.info(f"Imported {len(imported)} lines from {file_path}")
                messagebox.showinfo("Success", f"Successfully imported {len(imported)} lines from TXT & auto-saved!")

    # ----------------- AI Translate & Review Staging -----------------
    def translate_with_ai(self):
        if self.current_file_index < 0 or self.current_file_index >= len(self.file_items):
            return
        item = self.file_items[self.current_file_index]
        target_filename = item["filename"]
        target_rel_path = item["rel_path"]
        target_file_index = self.current_file_index

        # Guard against double-triggering the same file
        if target_filename in getattr(self, "active_ai_tasks", {}):
            messagebox.showinfo(
                "AI Busy", 
                f"File '{target_filename}' is already being translated by AI in the background."
            )
            return

        is_local = "localhost" in self.ai.endpoint or "127.0.0.1" in self.ai.endpoint
        if not is_local and not self.ai.api_key:
            messagebox.showwarning(
                "API Key Required", 
                f"AI API Key has not been configured!\nPlease click '{Icons.SETTINGS} Settings' to configure your API Key and Endpoint."
            )
            return

        # Snapshot data so any file switching or UI edits do not contaminate this background job
        target_orig_lines = list(self.current_orig_lines)
        target_trans_lines = list(self.current_trans_lines)
        tot_lines = len(target_orig_lines)

        if tot_lines == 0:
            messagebox.showinfo("Empty File", "No dialogue text lines to translate in this file.")
            return

        # Register active task
        self.active_ai_tasks[target_filename] = {
            "rel_path": target_rel_path,
            "progress_text": f"Connecting to AI ({self.ai.model})...",
            "lines_count": tot_lines
        }
        self.update_tree_item_display(target_file_index)

        self.ai_btn.config(state=tk.DISABLED, text=f"{Icons.SYNC} Translating...")
        self.info_status_lbl.config(text=f"Connecting to AI ({self.ai.model})...", foreground="#007ACC")
        log.info(f"Starting isolated AI translation for {target_filename} ({tot_lines} lines) via {self.ai.provider} ({self.ai.model})...")

        def worker():
            try:
                t0 = time.time()
                new_terms_recorded: List[str] = []

                # 1. Check Translation Memory (TM) for 100% exact matches (min_words=3)
                pre_filled = [None] * tot_lines
                untranslated_orig_lines = []
                untranslated_indices = []
                tm_hits = 0

                for i, orig_text in enumerate(target_orig_lines):
                    tm_match = self.db.get_exact_tm_match(orig_text, min_words=3)
                    if tm_match:
                        pre_filled[i] = tm_match
                        tm_hits += 1
                    else:
                        untranslated_orig_lines.append(orig_text)
                        untranslated_indices.append(i)

                if tm_hits > 0:
                    log.info(f"Translation Memory (TM) resolved {tm_hits}/{tot_lines} lines instantly for {target_filename} (0 API tokens).")

                if not untranslated_orig_lines:
                    result = pre_filled
                else:
                    # Load glossary terminology block for consistent translations
                    glossary_block = ""
                    try:
                        glossary_block = self.db.get_glossary_prompt_block()
                    except Exception:
                        pass

                    # Fetch contextual TM reference suggestions for AI
                    tm_prompt = ""
                    try:
                        tm_prompt = self.db.get_tm_prompt_block(untranslated_orig_lines, max_suggestions=10)
                    except Exception:
                        pass

                    combined_prompt = (glossary_block + "\n\n" + tm_prompt).strip()

                    def on_new_terms_found(terms: List[Dict[str, str]]):
                        for t in terms:
                            en = t.get("term_en")
                            id_val = t.get("term_id")
                            cat = t.get("category", "game_term")
                            notes = t.get("notes", "Learned automatically by AI during translation")
                            if en and id_val:
                                try:
                                    self.db.add_glossary_term(en, id_val, cat, notes)
                                    if en not in new_terms_recorded:
                                        new_terms_recorded.append(en)
                                except Exception:
                                    pass
                        if new_terms_recorded:
                            log.info(f"Auto-Glossary: AI discovered and recorded {len(new_terms_recorded)} new terms: {', '.join(new_terms_recorded[-5:])}")

                    def on_progress(cur: int, tot: int):
                        total_progress = tm_hits + cur
                        prog_text = f"Translating with AI ({self.ai.model}): {total_progress}/{tot_lines} lines... (TM: {tm_hits})"
                        if target_filename in self.active_ai_tasks:
                            self.active_ai_tasks[target_filename]["progress_text"] = prog_text
                        def update_ui():
                            # Only update status bar and button if user is STILL viewing this exact file
                            if (self.current_file_index >= 0 and 
                                self.current_file_index < len(self.file_items) and 
                                self.file_items[self.current_file_index]["filename"] == target_filename):
                                self.info_status_lbl.config(text=prog_text, foreground="#007ACC")
                                self.ai_btn.config(text=f"{Icons.SYNC} {total_progress}/{tot_lines}...")
                        self.after(0, update_ui)

                    ai_results = self.ai.translate_lines(
                        untranslated_orig_lines, 
                        target_lang="Indonesian",
                        progress_callback=on_progress,
                        glossary_block=combined_prompt,
                        on_new_terms=on_new_terms_found,
                        get_fresh_glossary_block=lambda: self.db.get_glossary_prompt_block(),
                        max_workers=3
                    )

                    for sub_i, res_l in enumerate(ai_results):
                        real_i = untranslated_indices[sub_i]
                        pre_filled[real_i] = TagGuard.sanitize_line(target_orig_lines[real_i], res_l)

                    result = pre_filled

                log.info(f"AI/TM translation finished in {time.time()-t0:.2f}s with {len(result)} lines for {target_filename} (TM hits: {tm_hits}, New terms: {len(new_terms_recorded)})")

                def on_success():
                    self.active_ai_tasks.pop(target_filename, None)

                    # Automatically record translation pairs into Translation Memory (TM)
                    valid_pairs = []
                    for o, t in zip(target_orig_lines, result):
                        if o and t and o != t and not o.startswith("[~"):
                            valid_pairs.append((o, t))
                    if valid_pairs:
                        try:
                            self.db.add_batch_tm_entries(valid_pairs, context_file=target_filename)
                        except Exception as tm_ex:
                            log.warning(f"Failed to record TM entries for {target_filename}: {tm_ex}")

                    # Find item index in self.file_items
                    matched_idx = -1
                    for idx, it in enumerate(self.file_items):
                        if it["filename"] == target_filename:
                            matched_idx = idx
                            break

                    is_user_still_on_file = (
                        self.current_file_index >= 0 and 
                        self.current_file_index < len(self.file_items) and 
                        self.file_items[self.current_file_index]["filename"] == target_filename
                    )

                    # Compute diffs between target_trans_lines and AI result
                    diffs_found: Dict[int, str] = {}
                    for i, new_line in enumerate(result):
                        cur_line = target_trans_lines[i] if i < len(target_trans_lines) else ""
                        if new_line != cur_line:
                            diffs_found[i] = new_line

                    if not diffs_found:
                        if is_user_still_on_file:
                            self.ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate AI")
                            self.info_status_lbl.config(
                                text="AI/TM completed: All lines match, no new changes.", 
                                foreground="#007ACC"
                            )
                            messagebox.showinfo(
                                "AI Translation Completed", 
                                "No lines changed. Translation result is identical to current text."
                            )
                        else:
                            self.info_status_lbl.config(
                                text=f"AI/TM '{target_filename}' completed: No new changes.", 
                                foreground="#007ACC"
                            )
                        if matched_idx >= 0:
                            self.update_tree_item_display(matched_idx)
                        return

                    # Stage the diffs into pending review cache for target_filename
                    self.file_pending_ai_diffs[target_filename] = diffs_found
                    self.file_pending_ai_meta[target_filename] = {
                        "tm_hits": tm_hits,
                        "new_terms": new_terms_recorded,
                        "result": result
                    }

                    extra_terms = f" ({len(new_terms_recorded)} new terms added to Glossary)" if new_terms_recorded else ""
                    tm_info = f" ({tm_hits} lines via TM)" if tm_hits else ""

                    if is_user_still_on_file:
                        # SCENARIO A: User is still on the same file -> Show green diffs & review bar immediately
                        self.ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate AI")
                        self.pending_ai_diffs = diffs_found
                        self.update_table_display()
                        self.update_review_bar()
                        self.info_status_lbl.config(
                            text=f"{Icons.SEARCH} {len(self.pending_ai_diffs)} AI translated lines ready for review{tm_info}{extra_terms} (click {Icons.ACCEPT} per line or Accept All)", 
                            foreground="#155724"
                        )
                    else:
                        # SCENARIO B: User navigated away -> Staged in cache, show sparkle in treeview!
                        log.info(f"AI translation for '{target_filename}' staged with {len(diffs_found)} diffs waiting for user review.")
                        self.info_status_lbl.config(
                            text=f"{Icons.AI_SPARKLE} AI translation of '{target_filename}' complete! {len(diffs_found)} lines ready for review when file is opened{tm_info}{extra_terms}.",
                            foreground="#155724"
                        )

                    if matched_idx >= 0:
                        self.update_tree_item_display(matched_idx)

                self.after(0, on_success)
            except Exception as e:
                err_msg = str(e)
                log.error(f"AI translation failed for {target_filename}: {err_msg}", exc_info=True)

                def on_fail(msg=err_msg):
                    self.active_ai_tasks.pop(target_filename, None)
                    matched_idx = -1
                    for idx, it in enumerate(self.file_items):
                        if it["filename"] == target_filename:
                            matched_idx = idx
                            break
                    if matched_idx >= 0:
                        self.update_tree_item_display(matched_idx)

                    is_user_still_on_file = (
                        self.current_file_index >= 0 and 
                        self.current_file_index < len(self.file_items) and 
                        self.file_items[self.current_file_index]["filename"] == target_filename
                    )
                    if is_user_still_on_file:
                        self.ai_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Translate AI")
                        self.info_status_lbl.config(text=f"{Icons.DISCARD} Translation failed", foreground="red")
                        messagebox.showerror("AI Translation Error", msg)
                    else:
                        self.info_status_lbl.config(
                            text=f"{Icons.DISCARD} Background translation failed for '{target_filename}': {msg[:60]}", 
                            foreground="red"
                        )

                self.after(0, on_fail)

        threading.Thread(target=worker, daemon=True).start()

    def open_batch_translate_dialog(self):
        """Opens the Batch Translation dialog for bulk translation across folders."""
        from gui.dialogs.batch_translate_dialog import BatchTranslateDialog
        dialog = BatchTranslateDialog(self, self)

    def auto_fix_all_tags(self):
        """Scans current file and automatically repairs any broken, missing, or malformed tags/tokens."""
        if self.current_file_index < 0 or not self.current_orig_lines or not self.current_trans_lines:
            return

        fixed_count = 0
        new_trans = list(self.current_trans_lines)
        for i in range(min(len(self.current_orig_lines), len(new_trans))):
            orig = self.current_orig_lines[i]
            trans = new_trans[i]
            diag = TagGuard.validate_line_diagnostics(orig, trans)
            if diag["can_auto_fix"]:
                new_trans[i] = diag["fixed_text"]
                fixed_count += 1

        if fixed_count > 0:
            self.push_undo_state()
            self.current_trans_lines = new_trans
            self.update_table_display()
            self.auto_save()
            self.info_status_lbl.config(
                text=f"{Icons.REPAIR} Auto-Fix: Fixed tags on {fixed_count} dialogue line(s)!",
                foreground="#2E7D32"
            )
            messagebox.showinfo(
                "Auto-Fix Tags Complete",
                f"Successfully fixed tags and control codes on {fixed_count} dialogue line(s)!\n"
                "Changes saved to database."
            )
        else:
            messagebox.showinfo(
                "All Tags Valid",
                "All dialogue tags and control codes ([VAR], [WAIT], \\n, \\r, \\c) match the original text 100%!"
            )


    def accept_single_ai_diff(self, line_idx: int):
        if line_idx not in self.pending_ai_diffs:
            return
        self.push_undo_state()
        new_text = self.pending_ai_diffs.pop(line_idx)
        while len(self.current_trans_lines) <= line_idx:
            self.current_trans_lines.append("")
        self.current_trans_lines[line_idx] = new_text

        cur_fname = self.file_items[self.current_file_index]['filename']
        if cur_fname in getattr(self, "file_pending_ai_diffs", {}):
            if self.pending_ai_diffs:
                self.file_pending_ai_diffs[cur_fname] = dict(self.pending_ai_diffs)
            else:
                self.file_pending_ai_diffs.pop(cur_fname, None)
                self.file_pending_ai_meta.pop(cur_fname, None)
                self.update_tree_item_display(self.current_file_index)

        self._update_table_row(line_idx)
        self.update_review_bar()
        self.auto_save()
        log.info(f"Accepted AI translation for line {line_idx} in {cur_fname}")

    def discard_single_ai_diff(self, line_idx: int):
        if line_idx not in self.pending_ai_diffs:
            return
        del self.pending_ai_diffs[line_idx]

        cur_fname = self.file_items[self.current_file_index]['filename']
        if cur_fname in getattr(self, "file_pending_ai_diffs", {}):
            if self.pending_ai_diffs:
                self.file_pending_ai_diffs[cur_fname] = dict(self.pending_ai_diffs)
            else:
                self.file_pending_ai_diffs.pop(cur_fname, None)
                self.file_pending_ai_meta.pop(cur_fname, None)
                self.update_tree_item_display(self.current_file_index)

        self._update_table_row(line_idx)
        self.update_review_bar()
        self.info_status_lbl.config(text=f"{Icons.DISCARD} Translation for line {line_idx} discarded.", foreground="#C62828")
        log.info(f"Discarded AI translation for line {line_idx}")

    def accept_all_ai_diffs(self):
        if not self.pending_ai_diffs:
            return
        self.push_undo_state()
        count = len(self.pending_ai_diffs)
        for idx, new_text in self.pending_ai_diffs.items():
            while len(self.current_trans_lines) <= idx:
                self.current_trans_lines.append("")
            self.current_trans_lines[idx] = new_text
        self.pending_ai_diffs.clear()

        cur_fname = self.file_items[self.current_file_index]['filename']
        if cur_fname in getattr(self, "file_pending_ai_diffs", {}):
            self.file_pending_ai_diffs.pop(cur_fname, None)
            self.file_pending_ai_meta.pop(cur_fname, None)

        self.update_table_display()
        self.update_review_bar()
        self.auto_save()
        self.update_tree_item_display(self.current_file_index)
        self.info_status_lbl.config(
            text=f"{Icons.ACCEPT} {count} AI translation line(s) accepted & saved!", 
            foreground="#2E7D32"
        )
        log.info(f"Accepted all {count} AI translations in {cur_fname}")

    def discard_all_ai_diffs(self):
        if not self.pending_ai_diffs:
            return
        count = len(self.pending_ai_diffs)
        self.pending_ai_diffs.clear()

        cur_fname = self.file_items[self.current_file_index]['filename']
        if cur_fname in getattr(self, "file_pending_ai_diffs", {}):
            self.file_pending_ai_diffs.pop(cur_fname, None)
            self.file_pending_ai_meta.pop(cur_fname, None)

        self.update_table_display()
        self.update_review_bar()
        self.update_tree_item_display(self.current_file_index)
        self.info_status_lbl.config(
            text=f"{Icons.DISCARD} {count} AI translation line(s) discarded.", 
            foreground="#C62828"
        )
        log.info(f"Discarded all {count} AI translations in {cur_fname}")

    def update_review_bar(self):
        count = len(self.pending_ai_diffs)
        if count > 0:
            self.review_info_lbl.config(
                text=f"{Icons.SEARCH} {count} AI translated line(s) awaiting review (git diff):"
            )
            self.review_accept_all_btn.config(text=f"{Icons.ACCEPT} Accept All ({count})")
            if not self.review_bar.winfo_manager():
                self.review_bar.pack(fill=tk.X, padx=5, pady=3, before=self.search_frame)
        else:
            if self.review_bar.winfo_manager():
                self.review_bar.pack_forget()

    def _update_table_row(self, line_idx: int):
        for row_id in self.table.get_children():
            vals = self.table.item(row_id, "values")
            if vals and int(vals[0]) == line_idx:
                orig = self.current_orig_lines[line_idx] if line_idx < len(self.current_orig_lines) else ""
                is_pending = (line_idx in self.pending_ai_diffs)
                if is_pending:
                    trans = self.pending_ai_diffs[line_idx]
                    accept_sym = Icons.ACCEPT
                    row_tag = "diff_pending_even" if line_idx % 2 == 0 else "diff_pending_odd"
                else:
                    trans = self.current_trans_lines[line_idx] if line_idx < len(self.current_trans_lines) else ""
                    accept_sym = ""
                    row_tag = "even" if line_idx % 2 == 0 else "odd"

                valid, _ = TagGuard.validate_line(orig, trans)
                tags = (row_tag,) if valid else (row_tag, "tag_error")
                self.table.item(row_id, values=(line_idx, accept_sym, orig, trans), tags=tags)
                selected = self.table.selection()
                if selected and selected[0] == row_id:
                    self.update_inspector(line_idx, orig, trans)
                break

    def on_table_click(self, event):
        region = self.table.identify_region(event.x, event.y)
        if region == "cell":
            col = self.table.identify_column(event.x)
            if col == "#2":  # Column 'accept'
                row_id = self.table.identify_row(event.y)
                if row_id:
                    vals = self.table.item(row_id, "values")
                    try:
                        line_idx = int(vals[0])
                        if line_idx in self.pending_ai_diffs:
                            self.accept_single_ai_diff(line_idx)
                            return "break"
                    except (ValueError, IndexError):
                        pass

    def on_table_motion(self, event):
        region = self.table.identify_region(event.x, event.y)
        if region == "cell":
            col = self.table.identify_column(event.x)
            if col == "#2":
                row_id = self.table.identify_row(event.y)
                if row_id:
                    vals = self.table.item(row_id, "values")
                    try:
                        line_idx = int(vals[0])
                        if line_idx in self.pending_ai_diffs:
                            self.table.config(cursor="hand2")
                            return
                    except (ValueError, IndexError):
                        pass
        self.table.config(cursor="")

    def show_table_context_menu(self, event):
        row_id = self.table.identify_row(event.y)
        if not row_id:
            return
        self.table.selection_set(row_id)
        vals = self.table.item(row_id, "values")
        try:
            line_idx = int(vals[0])
        except (ValueError, IndexError):
            return

        self.table_context_menu.delete(0, tk.END)
        if line_idx in self.pending_ai_diffs:
            self.table_context_menu.add_command(
                label=f"{Icons.ACCEPT} Accept Line {line_idx}", 
                command=lambda idx=line_idx: self.accept_single_ai_diff(idx)
            )
            self.table_context_menu.add_command(
                label=f"{Icons.DISCARD} Discard Line {line_idx}", 
                command=lambda idx=line_idx: self.discard_single_ai_diff(idx)
            )
            self.table_context_menu.add_separator()
            self.table_context_menu.add_command(
                label=f"{Icons.ACCEPT} Accept All ({len(self.pending_ai_diffs)} lines)", 
                command=self.accept_all_ai_diffs
            )
            self.table_context_menu.add_command(
                label=f"{Icons.DISCARD} Discard All", 
                command=self.discard_all_ai_diffs
            )
            self.table_context_menu.add_separator()

        self.table_context_menu.add_command(
            label=f"{Icons.EDIT} Edit Line...", 
            command=lambda: self.open_edit_dialog(
                line_idx, 
                vals[2], 
                vals[3], 
                row_id
            )
        )
        self.table_context_menu.post(event.x_root, event.y_root)

    # ----------------- 1-Click LayeredFS Mod Deployer -----------------
    def deploy_to_eden(self):
        """Opens the 1-Click LayeredFS Mod Deployer dialog."""
        from gui.dialogs.deploy_dialog import LayeredFSDeployDialog
        dialog = LayeredFSDeployDialog(self, self)


    # ----------------- Mod Manager Popup -----------------
    def open_mod_manager(self):
        log.info("Opening Eden Mod Manager window...")
        win = tk.Toplevel(self)
        win.title("Eden Mod Manager")
        win.geometry("600x450")
        win.transient(self)

        ttk.Label(win, text=f"{Icons.PACKAGE} Mods Installed in Eden Emulator", font=("Arial", 11, "bold")).pack(padx=10, pady=8, anchor=tk.W)

        tree = ttk.Treeview(win, columns=('status', 'name', 'type'), show='headings')
        tree.heading('status', text='Status')
        tree.column('status', width=70, anchor='center')
        tree.heading('name', text='Mod Name')
        tree.column('name', width=380, anchor='w')
        tree.heading('type', text='Type')
        tree.column('type', width=100, anchor='center')
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        title_id = self.settings.get("active_game_id", "0100A3D008C5C000")
        load_p = self.settings.get("eden_load_path")

        def refresh_table():
            for r in tree.get_children():
                tree.delete(r)
            mods = EmuDetector.get_mods_for_game(title_id, load_p)
            for m in mods:
                stat = f"{Icons.ACCEPT} Enabled" if m["is_enabled"] else f"{Icons.DISCARD} Disabled"
                tags = []
                if m["has_romfs"]: tags.append("RomFS")
                if m["has_exefs"]: tags.append("ExeFS")
                tag_str = "/".join(tags) if tags else "Misc"
                tree.insert('', 'end', values=(stat, m["display_name"], tag_str))

        refresh_table()

        btn_bar = ttk.Frame(win)
        btn_bar.pack(fill=tk.X, padx=10, pady=8)

        def toggle_sel():
            sel = tree.selection()
            if not sel: return
            val = tree.item(sel[0], 'values')[1]
            mods = EmuDetector.get_mods_for_game(title_id, load_p)
            for m in mods:
                if m["display_name"] == val:
                    log.info(f"Toggling mod: {m['display_name']}")
                    EmuDetector.toggle_mod(m)
                    break
            refresh_table()

        ttk.Button(btn_bar, text="Toggle On/Off", command=toggle_sel).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="Open Mod Folder", command=lambda: os.startfile(os.path.join(load_p, title_id))).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="Close", command=win.destroy).pack(side=tk.RIGHT)

    # ----------------- Settings Modal -----------------
    def open_settings_modal(self):
        log.info("Opening AI & Path Settings modal...")
        modal = tk.Toplevel(self)
        modal.title("AI & Polyglot Studio Settings")
        modal.geometry("640x700")
        modal.transient(self)
        modal.grab_set()

        ttk.Label(modal, text=f"{Icons.SETTINGS} AI & Path Settings", font=("Arial", 12, "bold")).pack(pady=10)

        main_f = ttk.Frame(modal)
        main_f.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Provider
        ttk.Label(main_f, text="AI Provider:").grid(row=0, column=0, sticky=tk.W, pady=4)
        prov_map = {
            "OpenAI Compatible (OpenAI, DeepSeek, Ollama, OpenRouter, LM Studio)": "openai",
            "Anthropic (Claude)": "anthropic",
            "Google (Gemini REST API)": "google"
        }
        rev_map = {v: k for k, v in prov_map.items()}
        prov_combo = ttk.Combobox(main_f, values=list(prov_map.keys()), state="readonly", width=55)
        cur_p = self.settings.get("ai_provider", "openai")
        prov_combo.set(rev_map.get(cur_p, list(prov_map.keys())[0]))
        prov_combo.grid(row=0, column=1, sticky=tk.W, pady=4)

        # Endpoint
        ttk.Label(main_f, text="Endpoint URL:").grid(row=1, column=0, sticky=tk.W, pady=4)
        endp_entry = ttk.Entry(main_f, width=58)
        endp_entry.insert(0, self.settings.get("ai_endpoint", "https://api.openai.com/v1"))
        endp_entry.grid(row=1, column=1, sticky=tk.W, pady=4)

        # Model
        ttk.Label(main_f, text="Model Name:").grid(row=2, column=0, sticky=tk.W, pady=4)
        model_entry = ttk.Entry(main_f, width=58)
        model_entry.insert(0, self.settings.get("ai_model", "gpt-4o-mini"))
        model_entry.grid(row=2, column=1, sticky=tk.W, pady=4)

        # API Key
        ttk.Label(main_f, text="API Key:").grid(row=3, column=0, sticky=tk.W, pady=4)
        key_entry = ttk.Entry(main_f, width=58, show="•")
        key_entry.insert(0, self.settings.get("ai_key", ""))
        key_entry.grid(row=3, column=1, sticky=tk.W, pady=4)

        def on_prov_change(event):
            p = prov_map[prov_combo.get()]
            endp_entry.delete(0, tk.END)
            endp_entry.insert(0, UniversalAIClient.PROVIDERS.get(p, {}).get("default_endpoint", ""))
            model_entry.delete(0, tk.END)
            model_entry.insert(0, UniversalAIClient.PROVIDERS.get(p, {}).get("default_model", ""))
        prov_combo.bind('<<ComboboxSelected>>', on_prov_change)

        # Custom Prompt
        ttk.Label(main_f, text="Custom Prompt:").grid(row=4, column=0, sticky=tk.NW, pady=4)
        prompt_box = ScrolledText(main_f, height=8, width=56, font=("Consolas", 9))
        c_prompt = self.settings.get("custom_prompt", "")
        if not c_prompt: c_prompt = UniversalAIClient.DEFAULT_PROMPT
        prompt_box.insert('1.0', c_prompt)
        prompt_box.grid(row=4, column=1, sticky=tk.W, pady=4)

        reset_btn = ttk.Button(
            main_f, 
            text="Reset to Default Prompt", 
            command=lambda: (prompt_box.delete('1.0', tk.END), prompt_box.insert('1.0', UniversalAIClient.DEFAULT_PROMPT))
        )
        reset_btn.grid(row=5, column=1, sticky=tk.W, pady=2)

        # Eden Load Path
        ttk.Label(main_f, text="Eden Mods Path:").grid(row=6, column=0, sticky=tk.W, pady=4)
        eden_entry = ttk.Entry(main_f, width=58)
        eden_entry.insert(0, self.settings.get("eden_load_path", ""))
        eden_entry.grid(row=6, column=1, sticky=tk.W, pady=4)

        # Test connection row
        test_status = ttk.Label(main_f, text="")
        test_status.grid(row=7, column=1, sticky=tk.W, pady=2)

        def test_conn():
            test_status.config(text="Testing connection...", foreground="blue")
            log.info("Testing AI connection from settings modal...")
            tester = UniversalAIClient(
                provider=prov_map[prov_combo.get()],
                endpoint=endp_entry.get().strip(),
                api_key=key_entry.get().strip(),
                model=model_entry.get().strip(),
                custom_prompt=prompt_box.get('1.0', tk.END).strip()
            )
            def worker():
                ok, msg = tester.test_connection()
                def ui():
                    if ok: 
                        log.info(f"AI Connection Test succeeded: {msg}")
                        test_status.config(text=f"{Icons.ACCEPT} {msg}", foreground="green")
                    else: 
                        log.warning(f"AI Connection Test failed: {msg}")
                        test_status.config(text=f"{Icons.DISCARD} {msg[:80]}", foreground="red")
                modal.after(0, ui)
            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(main_f, text=f"{Icons.AI_SPARKLE} Test Connection", command=test_conn).grid(row=8, column=1, sticky=tk.W, pady=4)

        # Save & Cancel Buttons
        btn_box = ttk.Frame(modal)
        btn_box.pack(fill=tk.X, padx=15, pady=10)

        def save_all():
            self.settings["ai_provider"] = prov_map[prov_combo.get()]
            self.settings["ai_endpoint"] = endp_entry.get().strip()
            self.settings["ai_model"] = model_entry.get().strip()
            self.settings["ai_key"] = key_entry.get().strip()
            self.settings["custom_prompt"] = prompt_box.get('1.0', tk.END).strip()
            self.settings["eden_load_path"] = eden_entry.get().strip()
            self.save_settings()

            self.ai.update_config(
                self.settings["ai_provider"],
                self.settings["ai_endpoint"],
                self.settings["ai_key"],
                self.settings["ai_model"],
                self.settings["custom_prompt"]
            )
            self.ai_badge_lbl.config(text=f"{Icons.AI_BOT} {self.ai.model}")
            modal.destroy()

        ttk.Button(btn_box, text="Save Settings", command=save_all).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Cancel", command=modal.destroy).pack(side=tk.RIGHT)

    # ----------------- Glossary Modal -----------------
    def open_glossary_dialog(self):
        log.info("Opening Glossary Management dialog...")
        from gui.dialogs.glossary_dialog import GlossaryDialog
        GlossaryDialog(self, self.db, ai=self.ai, current_lines=self.current_orig_lines)

    # ----------------- Table Search Logic -----------------
    def search_text(self, event=None):
        search_term = self.search_var.get().lower()
        self.search_results = []

        if not search_term:
            self.clear_search_highlight()
            self.search_status.config(text="")
            return

        for item in self.table.get_children():
            values = self.table.item(item, 'values')
            if (len(values) >= 3 and search_term in str(values[2]).lower()) or \
               (len(values) >= 4 and search_term in str(values[3]).lower()):
                self.search_results.append(item)

        if self.search_results:
            self.current_search_index = 0
            self.highlight_search_result()
            self.search_status.config(text=f"{self.current_search_index + 1}/{len(self.search_results)}")
        else:
            self.search_status.config(text="No results")
            self.current_search_index = -1

    def clear_search(self):
        self.search_var.set("")
        self.clear_search_highlight()
        self.search_status.config(text="")
        self.search_results = []
        self.current_search_index = -1

    def clear_search_highlight(self):
        for item in self.table.get_children():
            tags = list(self.table.item(item, 'tags'))
            if "search_highlight" in tags:
                tags.remove("search_highlight")
                self.table.item(item, tags=tuple(tags))

    def highlight_search_result(self):
        self.clear_search_highlight()
        if 0 <= self.current_search_index < len(self.search_results):
            item = self.search_results[self.current_search_index]
            tags = list(self.table.item(item, 'tags'))
            if "search_highlight" not in tags:
                tags.append("search_highlight")
            self.table.item(item, tags=tuple(tags))
            self.table.see(item)
            self.table.selection_set(item)

    def prev_search_result(self):
        if self.search_results:
            self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
            self.highlight_search_result()
            self.search_status.config(text=f"{self.current_search_index + 1}/{len(self.search_results)}")

    def next_search_result(self):
        if self.search_results:
            self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
            self.highlight_search_result()
            self.search_status.config(text=f"{self.current_search_index + 1}/{len(self.search_results)}")

    def show_about_dialog(self):
        messagebox.showinfo(
            "About Polyglot Studio",
            "Polyglot Studio (Switch Mod Studio)\n"
            "Version 2.0.0\n\n"
            "An advanced, AI-assisted localization & modding studio for Nintendo Switch RomFS assets.\n\n"
            "Features:\n"
            "• Direct TRPFS RomFS archive reading & writing\n"
            "• Native FlatBuffers .dat dialogue parser & compiler\n"
            "• Universal AI Translation (OpenAI, Gemini, Claude, Ollama, DeepSeek)\n"
            "• Translation Memory (TM) & Terminology Glossary\n"
            "• Multi-format Asset Viewer (Textures, Fonts, Audio)\n"
            "• 1-Click LayeredFS Mod Deployer for Eden Emulator & Switch SD Card\n\n"
            "Segoe Fluent UI & High Performance Architecture."
        )

# Alias
PolyglotStudioApp = ClassicDATStudioApp
SwitchModStudioApp = ClassicDATStudioApp
