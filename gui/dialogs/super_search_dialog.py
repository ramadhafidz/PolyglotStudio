"""
Super Search & Replace Dialog for Polyglot Studio.
Provides global multi-file text searching across all game dialogue (.dat) files
in RomFS or local workspace, instant line navigation, and safe batch replacement.
"""

import os
import re
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any, Callable

from core.icons import Icons
from core.logger import log
from core.tag_guard import TagGuard
from gui.tooltip import ToolTip, set_tooltip


class SuperSearchDialog(tk.Toplevel):
    """
    Modern desktop dialog for global searching & replacing across all project files.
    Features:
    - Search in Original, Translated, or Both
    - Case-sensitive & Whole-word matching
    - Direct jump to line in main editor on double-click
    - Single-occurrence & Global multi-file Replace
    - Non-blocking background worker with cancellation
    """

    def __init__(self, parent, app, initial_query: str = ""):
        super().__init__(parent)
        self.parent = parent
        self.app = app
        self.db = app.db

        self.title("Super Search & Replace")
        self.geometry("980x640")
        self.minsize(820, 520)
        self.transient(parent)

        self.is_searching = False
        self.is_replacing = False
        self.stop_requested = False

        self.results: List[Dict[str, Any]] = []
        self.tree_item_to_index: Dict[str, int] = {}
        self._worker_thread: Optional[threading.Thread] = None

        self._center_on_parent(parent)
        self._build_ui()

        if initial_query:
            self.find_var.set(initial_query)
            self.after(150, self.start_search)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Escape>", lambda e: self.on_close())
        self.bind("<Control-Return>", lambda e: self.start_search())

    def _center_on_parent(self, parent):
        self.update_idletasks()
        try:
            if parent:
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                parent_x = parent.winfo_rootx()
                parent_y = parent.winfo_rooty()
                if parent_w > 100 and parent_h > 100:
                    x = parent_x + (parent_w - 980) // 2
                    y = parent_y + (parent_h - 640) // 2
                    self.geometry(f"980x640+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build_ui(self):
        # 1. Header Banner
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header,
            text=f"{Icons.SUPER_SEARCH} Super Search & Replace (All Files)",
            font=("Arial", 12, "bold"),
            foreground="#007ACC"
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ttk.Label(
            header,
            text="Search dialogue lines across all game files in the project. "
                 "Double-click any result to jump to that line in the editor.",
            font=("Arial", 9),
            foreground="#555555"
        )
        desc_lbl.pack(anchor="w", pady=(2, 0))

        # 2. Search & Replace Form Container
        ctrl_frame = ttk.LabelFrame(self, text="Search & Replace Parameters", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=12, pady=4)

        # Row 0: Find Input & Find Button
        row0 = ttk.Frame(ctrl_frame)
        row0.pack(fill=tk.X, pady=2)

        ttk.Label(row0, text="Find Text:", width=12).pack(side=tk.LEFT)
        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(row0, textvariable=self.find_var, width=38)
        self.find_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.find_entry.bind("<Return>", lambda e: self.start_search())
        self.find_entry.focus_set()

        clear_find_btn = ttk.Button(row0, text=Icons.DISCARD, width=3, command=lambda: self.find_var.set(""))
        clear_find_btn.pack(side=tk.LEFT, padx=(0, 10))
        set_tooltip(clear_find_btn, "Clear search text")

        self.case_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row0, text="Match Case", variable=self.case_var).pack(side=tk.LEFT, padx=4)

        self.word_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row0, text="Whole Word", variable=self.word_var).pack(side=tk.LEFT, padx=4)

        self.find_btn = ttk.Button(
            row0,
            text=f"{Icons.SEARCH} Find All",
            command=self.start_search
        )
        self.find_btn.pack(side=tk.LEFT, padx=(8, 0))
        set_tooltip(self.find_btn, "Search across selected files (Enter)")

        # Row 1: Replace Input & Replace Actions
        row1 = ttk.Frame(ctrl_frame)
        row1.pack(fill=tk.X, pady=4)

        ttk.Label(row1, text="Replace with:", width=12).pack(side=tk.LEFT)
        self.replace_var = tk.StringVar()
        self.replace_entry = ttk.Entry(row1, textvariable=self.replace_var, width=38)
        self.replace_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        clear_rep_btn = ttk.Button(row1, text=Icons.DISCARD, width=3, command=lambda: self.replace_var.set(""))
        clear_rep_btn.pack(side=tk.LEFT, padx=(0, 10))
        set_tooltip(clear_rep_btn, "Clear replace text")

        self.rep_sel_btn = ttk.Button(
            row1,
            text=f"{Icons.EDIT} Replace Selected",
            command=self.replace_selected,
            state=tk.DISABLED
        )
        self.rep_sel_btn.pack(side=tk.LEFT, padx=2)
        set_tooltip(self.rep_sel_btn, "Replace query in the currently selected row's translation")

        self.rep_file_btn = ttk.Button(
            row1,
            text="Replace in File",
            command=self.replace_in_file,
            state=tk.DISABLED
        )
        self.rep_file_btn.pack(side=tk.LEFT, padx=2)
        set_tooltip(self.rep_file_btn, "Replace all occurrences within the selected file")

        self.rep_all_btn = ttk.Button(
            row1,
            text=f"{Icons.REPLACE} Replace All...",
            command=self.replace_all,
            state=tk.DISABLED
        )
        self.rep_all_btn.pack(side=tk.LEFT, padx=(4, 0))
        set_tooltip(self.rep_all_btn, "Replace all occurrences across all project files")

        # Row 2: Scope & Target Selectors
        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill=tk.X, pady=(4, 0))

        ttk.Label(row2, text="Scope:").pack(side=tk.LEFT, padx=(0, 4))
        self.scope_var = tk.StringVar(value="all")
        scope_cb = ttk.Combobox(
            row2,
            textvariable=self.scope_var,
            values=["all", "current_folder", "current_file"],
            state="readonly",
            width=16
        )
        scope_cb.pack(side=tk.LEFT, padx=(0, 16))
        scope_cb.bind("<<ComboboxSelected>>", lambda e: None)

        ttk.Label(row2, text="Search in:").pack(side=tk.LEFT, padx=(0, 4))
        self.target_var = tk.StringVar(value="both")
        target_cb = ttk.Combobox(
            row2,
            textvariable=self.target_var,
            values=["both", "orig", "trans"],
            state="readonly",
            width=18
        )
        target_cb.pack(side=tk.LEFT)

        # 3. Progress & Status Banner
        prog_frame = ttk.Frame(self, padding=(12, 4))
        prog_frame.pack(fill=tk.X)

        self.status_lbl = ttk.Label(
            prog_frame,
            text="Ready. Type text and click 'Find All' or press Enter to search.",
            font=("Arial", 9)
        )
        self.status_lbl.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            prog_frame,
            text=f"{Icons.DISCARD} Stop",
            command=self.stop_operation,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=4)

        self.prog_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.prog_bar.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=8)

        # 4. Results Table (Treeview)
        results_container = ttk.Frame(self, padding=(12, 4))
        results_container.pack(fill=tk.BOTH, expand=True)

        cols = ("no", "filename", "folder", "line", "matched_in", "orig", "trans")
        self.tree = ttk.Treeview(results_container, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("no", text="#")
        self.tree.heading("filename", text="File")
        self.tree.heading("folder", text="Folder")
        self.tree.heading("line", text="Line")
        self.tree.heading("matched_in", text="Matched In")
        self.tree.heading("orig", text="Original Dialogue")
        self.tree.heading("trans", text="Translated Dialogue")

        self.tree.column("no", width=42, minwidth=40, anchor="center", stretch=False)
        self.tree.column("filename", width=145, minwidth=120, stretch=False)
        self.tree.column("folder", width=140, minwidth=110, stretch=False)
        self.tree.column("line", width=55, minwidth=50, anchor="center", stretch=False)
        self.tree.column("matched_in", width=95, minwidth=85, anchor="center", stretch=False)
        self.tree.column("orig", width=250, minwidth=180, stretch=True)
        self.tree.column("trans", width=250, minwidth=180, stretch=True)

        # Alternating row colors
        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F9FAFB")
        self.tree.tag_configure("both_match", foreground="#007ACC")

        v_scroll = ttk.Scrollbar(results_container, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(results_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        results_container.grid_rowconfigure(0, weight=1)
        results_container.grid_columnconfigure(0, weight=1)

        # Tree events
        self.tree.bind("<Double-1>", self.on_jump_to_result)
        self.tree.bind("<Return>", self.on_jump_to_result)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._show_context_menu)

        # 5. Context Menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(
            label=f"{Icons.VIEW} Jump to Line in Editor (Enter)",
            command=self.on_jump_to_result
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label=f"{Icons.EDIT} Replace Selected Occurrence",
            command=self.replace_selected
        )
        self.context_menu.add_separator()
        self.context_menu.add_command(
            label=f"{Icons.COPY} Copy Original Text",
            command=self._copy_orig_text
        )
        self.context_menu.add_command(
            label=f"{Icons.COPY} Copy Translated Text",
            command=self._copy_trans_text
        )

        # 6. Bottom Status & Actions Bar
        bot_bar = ttk.Frame(self, padding=(12, 10))
        bot_bar.pack(fill=tk.X)

        self.stats_lbl = ttk.Label(bot_bar, text="0 results found", font=("Arial", 9, "bold"), foreground="#007ACC")
        self.stats_lbl.pack(side=tk.LEFT)

        ttk.Button(bot_bar, text="Close (Esc)", command=self.on_close).pack(side=tk.RIGHT)

        self.jump_btn = ttk.Button(
            bot_bar,
            text=f"{Icons.VIEW} Jump to Line in Editor",
            command=self.on_jump_to_result,
            state=tk.DISABLED
        )
        self.jump_btn.pack(side=tk.RIGHT, padx=6)

    def _show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self._on_tree_select()
            self.context_menu.post(event.x_root, event.y_root)

    def _on_tree_select(self, event=None):
        has_sel = bool(self.tree.selection())
        state = tk.NORMAL if has_sel else tk.DISABLED
        self.jump_btn.config(state=state)
        self.rep_sel_btn.config(state=state)
        self.rep_file_btn.config(state=state)

    def _copy_orig_text(self):
        sel = self.tree.selection()
        if sel and sel[0] in self.tree_item_to_index:
            r = self.results[self.tree_item_to_index[sel[0]]]
            self.clipboard_clear()
            self.clipboard_append(r["orig"])

    def _copy_trans_text(self):
        sel = self.tree.selection()
        if sel and sel[0] in self.tree_item_to_index:
            r = self.results[self.tree_item_to_index[sel[0]]]
            self.clipboard_clear()
            self.clipboard_append(r["trans"])

    # ----------------- Target Files Resolution -----------------
    def _get_target_files(self, scope: str) -> List[Dict[str, Any]]:
        all_items = self.app.file_items
        active_idx = getattr(self.app, "current_file_index", -1)

        current_file_item = all_items[active_idx] if 0 <= active_idx < len(all_items) else None
        current_folder = ""
        if current_file_item:
            rel = current_file_item["rel_path"].replace("/", os.sep)
            parts = rel.split(os.sep)
            if len(parts) > 1:
                current_folder = parts[0]

        filtered = []
        for item in all_items:
            fname = item["filename"].lower()
            if not fname.endswith(".dat"):
                continue

            rel = item["rel_path"].replace("/", os.sep)
            parts = rel.split(os.sep)
            folder = parts[0] if len(parts) > 1 else ""

            if scope == "current_file":
                if current_file_item and item["filename"] != current_file_item["filename"]:
                    continue
            elif scope == "current_folder":
                if current_folder and folder != current_folder:
                    continue

            filtered.append(item)

        return filtered

    # ----------------- Search Execution -----------------
    def start_search(self):
        if self.is_searching or self.is_replacing:
            return

        query = self.find_var.get().strip()
        if not query:
            messagebox.showinfo("Search", "Please enter a search query.")
            self.find_entry.focus_set()
            return

        scope = self.scope_var.get()
        target = self.target_var.get()
        match_case = self.case_var.get()
        whole_word = self.word_var.get()

        target_files = self._get_target_files(scope)
        if not target_files:
            messagebox.showinfo("Search", "No dialogue files match the selected scope.")
            return

        # Clear existing results
        for r in self.tree.get_children():
            self.tree.delete(r)
        self.results.clear()
        self.tree_item_to_index.clear()

        self.is_searching = True
        self.stop_requested = False
        self.find_btn.config(state=tk.DISABLED)
        self.rep_all_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.prog_bar.config(maximum=len(target_files), value=0)
        self.status_lbl.config(
            text=f"Searching for '{query}' across {len(target_files)} file(s)...",
            foreground="#007ACC"
        )

        self._worker_thread = threading.Thread(
            target=self._search_worker,
            args=(query, target_files, target, match_case, whole_word),
            daemon=True
        )
        self._worker_thread.start()

    def stop_operation(self):
        if self.is_searching or self.is_replacing:
            self.stop_requested = True
            self.status_lbl.config(text="Stopping...", foreground="orange")
            self.stop_btn.config(state=tk.DISABLED)

    def _search_worker(
        self,
        query: str,
        target_files: List[Dict[str, Any]],
        target: str,
        match_case: bool,
        whole_word: bool
    ):
        t0 = time.time()
        tot_files = len(target_files)
        total_matches = 0
        matched_filenames = set()

        pattern = None
        if whole_word:
            flags = 0 if match_case else re.IGNORECASE
            pattern = re.compile(rf"\b{re.escape(query)}\b", flags)

        def check_match(text: str) -> bool:
            if not text:
                return False
            if pattern:
                return bool(pattern.search(text))
            if match_case:
                return query in text
            return query.lower() in text.lower()

        for idx, item in enumerate(target_files, 1):
            if self.stop_requested:
                break

            fname = item["filename"]
            rel_p = item["rel_path"]

            # Update progress UI periodically
            if idx % 15 == 0 or idx == tot_files:
                self.after(0, lambda i=idx, tot=tot_files, m=total_matches, f=len(matched_filenames): (
                    self.prog_bar.config(value=i),
                    self.status_lbl.config(text=f"Searching... [{i}/{tot} files] | Found {m} matches in {f} files")
                ))

            # 1. Fetch file lines (check SQLite first to get active translations)
            orig_lines = None
            trans_lines = None

            db_data = self.db.get_file_full_data(fname)
            if db_data is not None:
                orig_lines, trans_lines = db_data
            else:
                raw_bytes = None
                if item.get("is_virtual") and getattr(self.app, "trpfs_client", None):
                    vtarget = item.get("romfs_path") or rel_p
                    raw_bytes = self.app.trpfs_client.extract_file_bytes(vtarget)
                else:
                    fpath = item.get("dat_path") or item.get("file_path", "")
                    if fpath and os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as f_in:
                                raw_bytes = f_in.read()
                        except Exception:
                            raw_bytes = None

                if not raw_bytes:
                    continue

                try:
                    orig_lines = self.app.codec.decode_bytes(raw_bytes)
                    trans_lines = list(orig_lines)
                except Exception:
                    continue

            if not orig_lines:
                continue

            # 2. Search lines
            max_lines = max(len(orig_lines), len(trans_lines))
            file_had_match = False

            for line_idx in range(max_lines):
                o_line = orig_lines[line_idx] if line_idx < len(orig_lines) else ""
                t_line = trans_lines[line_idx] if line_idx < len(trans_lines) else o_line

                m_orig = check_match(o_line) if target in ("both", "orig") else False
                m_trans = check_match(t_line) if target in ("both", "trans") else False

                if m_orig or m_trans:
                    total_matches += 1
                    file_had_match = True

                    if m_orig and m_trans:
                        loc = "Both"
                    elif m_orig:
                        loc = "Original"
                    else:
                        loc = "Translated"

                    folder_name = os.path.dirname(rel_p).replace("\\", "/") or "Root"
                    res_entry = {
                        "no": total_matches,
                        "filename": fname,
                        "rel_path": rel_p,
                        "folder": folder_name,
                        "line": line_idx,
                        "location": loc,
                        "orig": o_line,
                        "trans": t_line,
                        "item": item
                    }
                    self.results.append(res_entry)
                    self.after(0, lambda r=res_entry: self._insert_result_row(r))

            if file_had_match:
                matched_filenames.add(fname)

        elapsed = time.time() - t0
        self.after(0, lambda m=total_matches, f=len(matched_filenames), e=elapsed, c=self.stop_requested: 
            self._on_search_complete(m, f, e, c)
        )

    def _insert_result_row(self, r: Dict[str, Any]):
        idx = len(self.tree_item_to_index)
        row_tag = "even" if idx % 2 == 0 else "odd"
        tags = [row_tag]
        if r["location"] == "Both":
            tags.append("both_match")

        disp_orig = r["orig"].replace("\n", " \\n ")
        disp_trans = r["trans"].replace("\n", " \\n ")

        node_id = self.tree.insert(
            "",
            "end",
            values=(r["no"], r["filename"], r["folder"], r["line"], r["location"], disp_orig, disp_trans),
            tags=tuple(tags)
        )
        self.tree_item_to_index[node_id] = idx
        self.stats_lbl.config(text=f"{len(self.results)} matches found")

    def _on_search_complete(self, total_matches: int, total_files: int, elapsed: float, cancelled: bool):
        self.is_searching = False
        self.find_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.rep_all_btn.config(state=tk.NORMAL if total_matches > 0 else tk.DISABLED)

        if cancelled:
            self.status_lbl.config(
                text=f"Search cancelled. Found {total_matches} matches across {total_files} file(s) ({elapsed:.2f}s).",
                foreground="orange"
            )
        else:
            self.prog_bar.config(value=self.prog_bar["maximum"])
            self.status_lbl.config(
                text=f"Search completed: {total_matches} matches found across {total_files} file(s) in {elapsed:.2f}s.",
                foreground="#2E7D32"
            )
        self.stats_lbl.config(text=f"{total_matches} matches in {total_files} file(s)")

    # ----------------- Jump to Editor Action -----------------
    def on_jump_to_result(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        if item_id not in self.tree_item_to_index:
            return

        r = self.results[self.tree_item_to_index[item_id]]
        fname = r["filename"]
        line_num = r["line"]

        try:
            success = self.app.jump_to_dialogue_line(fname, line_num)
            if success:
                self.status_lbl.config(
                    text=f"Jumped to {fname} : Line {line_num} in editor.",
                    foreground="#2E7D32"
                )
            else:
                self.status_lbl.config(
                    text=f"Could not jump to {fname}.",
                    foreground="#C62828"
                )
        except Exception as ex:
            log.warning(f"Error jumping to dialogue line: {ex}")

    # ----------------- Replace Actions -----------------
    def _perform_replacement_on_string(self, text: str, query: str, rep_text: str, match_case: bool, whole_word: bool) -> str:
        if whole_word:
            flags = 0 if match_case else re.IGNORECASE
            return re.sub(rf"\b{re.escape(query)}\b", rep_text, text, flags=flags)
        if match_case:
            return text.replace(query, rep_text)
        # Case insensitive replacement preserving unaffected text
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return pattern.sub(rep_text, text)

    def replace_selected(self):
        """Replaces the match in the currently highlighted result row's translation."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Replace", "Please select a result row from the list to replace.")
            return

        item_id = selected[0]
        if item_id not in self.tree_item_to_index:
            return

        query = self.find_var.get().strip()
        rep_text = self.replace_var.get()
        if not query:
            return

        r = self.results[self.tree_item_to_index[item_id]]
        fname = r["filename"]
        rel_p = r["rel_path"]
        line_num = r["line"]

        # Load current full data from DB
        db_data = self.db.get_file_full_data(fname)
        if db_data is not None:
            orig_lines, trans_lines = db_data
            orig_lines = list(orig_lines)
            trans_lines = list(trans_lines)
        else:
            # Load from virtual or disk
            item = r["item"]
            raw_bytes = None
            if item.get("is_virtual") and getattr(self.app, "trpfs_client", None):
                raw_bytes = self.app.trpfs_client.extract_file_bytes(item.get("romfs_path") or rel_p)
            else:
                fpath = item.get("dat_path") or item.get("file_path", "")
                if fpath and os.path.exists(fpath):
                    with open(fpath, "rb") as f_in:
                        raw_bytes = f_in.read()
            if not raw_bytes:
                messagebox.showerror("Error", f"Failed to read file data for {fname}.")
                return
            orig_lines = self.app.codec.decode_bytes(raw_bytes)
            trans_lines = list(orig_lines)

        while len(trans_lines) < len(orig_lines):
            trans_lines.append(orig_lines[len(trans_lines)])

        if line_num >= len(trans_lines):
            return

        old_t = trans_lines[line_num]
        new_t = self._perform_replacement_on_string(
            old_t, query, rep_text, self.case_var.get(), self.word_var.get()
        )

        # Sanitize tags
        clean_t = TagGuard.sanitize_line(orig_lines[line_num], new_t)
        trans_lines[line_num] = clean_t

        # Save to disk & DB
        self._save_modified_file(r["item"], fname, rel_p, orig_lines, trans_lines)

        # Update row display in tree
        r["trans"] = clean_t
        disp_trans = clean_t.replace("\n", " \\n ")
        self.tree.set(item_id, "trans", disp_trans)

        self.status_lbl.config(
            text=f"Replaced occurrence in {fname} : Line {line_num}",
            foreground="#2E7D32"
        )

    def replace_in_file(self):
        """Replaces all occurrences within the file of the selected result row."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Replace", "Please select a row to identify which file to replace in.")
            return

        item_id = selected[0]
        r = self.results[self.tree_item_to_index[item_id]]
        target_fname = r["filename"]

        query = self.find_var.get().strip()
        rep_text = self.replace_var.get()
        if not query:
            return

        file_results = [res for res in self.results if res["filename"] == target_fname]
        if not messagebox.askyesno(
            "Confirm Replace in File",
            f"Replace {len(file_results)} occurrence(s) of '{query}' with '{rep_text}' in {target_fname}?"
        ):
            return

        self._batch_replace_files([target_fname], query, rep_text)

    def replace_all(self):
        """Replaces all occurrences across all matched files in the project."""
        query = self.find_var.get().strip()
        rep_text = self.replace_var.get()
        if not query:
            messagebox.showinfo("Replace All", "Search query is empty.")
            return

        if not self.results:
            messagebox.showinfo("Replace All", "No search results to replace. Run 'Find All' first.")
            return

        matched_files = list(dict.fromkeys(r["filename"] for r in self.results))
        if not messagebox.askyesno(
            "Confirm Replace All Across Project",
            f"Are you sure you want to replace all {len(self.results)} occurrence(s) of:\n\n"
            f"'{query}'  →  '{rep_text}'\n\n"
            f"Across {len(matched_files)} dialogue file(s)?\n"
            f"All files will be compiled to workspace/modified and saved into SQLite."
        ):
            return

        self._batch_replace_files(matched_files, query, rep_text)

    def _batch_replace_files(self, filenames: List[str], query: str, rep_text: str):
        self.is_replacing = True
        self.stop_requested = False
        self.find_btn.config(state=tk.DISABLED)
        self.rep_all_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.prog_bar.config(maximum=len(filenames), value=0)

        def worker():
            t0 = time.time()
            total_replaced = 0
            match_case = self.case_var.get()
            whole_word = self.word_var.get()

            # Map filename to item dict
            items_by_name = {it["filename"]: it for it in self.app.file_items}

            for f_i, fname in enumerate(filenames, 1):
                if self.stop_requested:
                    break

                self.after(0, lambda i=f_i, tot=len(filenames), f=fname: (
                    self.prog_bar.config(value=i),
                    self.status_lbl.config(text=f"Replacing in [{i}/{tot}]: {f}...", foreground="#007ACC")
                ))

                item = items_by_name.get(fname)
                if not item:
                    continue

                rel_p = item["rel_path"]

                # Load full data
                db_data = self.db.get_file_full_data(fname)
                if db_data is not None:
                    orig_lines, trans_lines = db_data
                    orig_lines = list(orig_lines)
                    trans_lines = list(trans_lines)
                else:
                    raw_bytes = None
                    if item.get("is_virtual") and getattr(self.app, "trpfs_client", None):
                        raw_bytes = self.app.trpfs_client.extract_file_bytes(item.get("romfs_path") or rel_p)
                    else:
                        fpath = item.get("dat_path") or item.get("file_path", "")
                        if fpath and os.path.exists(fpath):
                            with open(fpath, "rb") as f_in:
                                raw_bytes = f_in.read()

                    if not raw_bytes:
                        continue
                    try:
                        orig_lines = self.app.codec.decode_bytes(raw_bytes)
                        trans_lines = list(orig_lines)
                    except Exception:
                        continue

                while len(trans_lines) < len(orig_lines):
                    trans_lines.append(orig_lines[len(trans_lines)])

                file_modified = False
                for line_i in range(len(trans_lines)):
                    cur_t = trans_lines[line_i]
                    new_t = self._perform_replacement_on_string(cur_t, query, rep_text, match_case, whole_word)
                    if new_t != cur_t:
                        clean_t = TagGuard.sanitize_line(orig_lines[line_i], new_t)
                        trans_lines[line_i] = clean_t
                        file_modified = True
                        total_replaced += 1

                if file_modified:
                    self._save_modified_file(item, fname, rel_p, orig_lines, trans_lines)

            elapsed = time.time() - t0
            self.after(0, lambda r=total_replaced, f=len(filenames), e=elapsed: self._on_batch_replace_complete(r, f, e))

        threading.Thread(target=worker, daemon=True).start()

    def _save_modified_file(self, item: Dict[str, Any], fname: str, rel_p: str, orig_lines: List[str], trans_lines: List[str]):
        # Write .dat
        if not item.get("is_virtual") and os.path.isabs(item.get("dat_path", "")):
            out_path = item["dat_path"]
        else:
            mod_dir = os.path.join(self.db.project_dir, "modified", os.path.dirname(rel_p))
            os.makedirs(mod_dir, exist_ok=True)
            out_path = os.path.join(mod_dir, fname)
            item["dat_path"] = out_path

        try:
            self.app.codec.write_file(out_path, trans_lines)
        except Exception as io_err:
            log.warning(f"Failed to write compiled .dat for {fname}: {io_err}")

        # SQLite update
        eff_status, diffs, total, is_manual = self.db.save_file_translation(
            filename=fname,
            rel_path=rel_p,
            orig_lines=orig_lines,
            trans_lines=trans_lines
        )
        item["status"] = eff_status
        item["diffs"] = diffs
        item["total"] = total
        item["is_manual"] = is_manual

        # Update main app if file is open
        try:
            if item in self.app.file_items:
                main_idx = self.app.file_items.index(item)
                self.after(0, lambda mi=main_idx: (
                    self.app.update_tree_item_display(mi),
                    self.app.update_progress_summary()
                ))
                if getattr(self.app, "current_file_index", -1) == main_idx:
                    self.after(0, lambda mi=main_idx: self.app.load_file(mi))
        except Exception:
            pass

    def _on_batch_replace_complete(self, total_replaced: int, file_count: int, elapsed: float):
        self.is_replacing = False
        self.find_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.rep_all_btn.config(state=tk.NORMAL)

        self.status_lbl.config(
            text=f"Replaced {total_replaced} occurrence(s) across {file_count} file(s) in {elapsed:.2f}s.",
            foreground="#2E7D32"
        )
        messagebox.showinfo(
            "Replace Complete",
            f"Successfully replaced {total_replaced} occurrence(s) across {file_count} file(s)!\n\n"
            f"All changes saved to SQLite and compiled into workspace/modified."
        )

        # Re-run search to refresh current results table
        self.start_search()

    def on_close(self):
        if self.is_searching or self.is_replacing:
            if not messagebox.askyesno("Task Running", "Search/Replace is still running in the background. Are you sure you want to close?"):
                return
            self.stop_requested = True
        self.destroy()
