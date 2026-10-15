"""
Batch Translation Dialog untuk Polyglot Studio.
Mendukung translasi otomatis berskala besar untuk folder atau seluruh file game,
dilengkapi integrasi Translation Memory (TM) dan auto-save ke SQLite.
"""

import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any, Callable

from core.icons import Icons
from core.logger import log
from core.tag_guard import TagGuard
from core.status_tracker import StatusTracker


class BatchTranslateDialog(tk.Toplevel):
    """
    Dialog modal untuk menjalankan translasi batch AI di latar belakang.
    """

    def __init__(self, parent, app):
        """
        Args:
            parent: Window induk (PolyglotStudioApp).
            app: Instance PolyglotStudioApp untuk akses file_items, db, ai, dan save_file.
        """
        super().__init__(parent)
        self.parent = parent
        self.app = app
        self.db = app.db
        self.ai = app.ai

        self.is_running = False
        self.stop_requested = False

        self.title("Batch AI Translation")
        self.geometry("740x540")
        self.minsize(680, 480)
        self.transient(parent)

        self._center_on_parent(parent)
        self._build_ui()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
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
                    x = parent_x + (parent_w - 740) // 2
                    y = parent_y + (parent_h - 540) // 2
                    self.geometry(f"740x540+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build_ui(self):
        # Header banner
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header,
            text=f"{Icons.BATCH} Large-Scale Batch Translation",
            font=("Arial", 12, "bold"),
            foreground="#007ACC"
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ttk.Label(
            header,
            text="Translate multiple dialogue files at scale using AI and Translation Memory (TM). "
                 "Files are automatically and safely saved to the SQLite database upon completion.",
            font=("Arial", 9),
            foreground="#555555",
            wraplength=700
        )
        desc_lbl.pack(anchor="w", pady=(2, 0))

        # Scope Options Frame
        opt_frame = ttk.LabelFrame(self, text="Translation Scope & Optimization", padding=10)
        opt_frame.pack(fill=tk.X, padx=12, pady=5)

        self.scope_var = tk.StringVar(value="untranslated")
        ttk.Radiobutton(
            opt_frame,
            text="Only Untranslated / Pending Files",
            variable=self.scope_var,
            value="untranslated"
        ).grid(row=0, column=0, sticky="w", pady=2)

        ttk.Radiobutton(
            opt_frame,
            text="All Files in Current Folder",
            variable=self.scope_var,
            value="current_folder"
        ).grid(row=1, column=0, sticky="w", pady=2)

        ttk.Radiobutton(
            opt_frame,
            text="All Registered Project Dialogue Files",
            variable=self.scope_var,
            value="all"
        ).grid(row=2, column=0, sticky="w", pady=2)

        # TM & Auto-save Checkboxes
        self.use_tm_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text=f"{Icons.MEMORY} Use Translation Memory (TM) — Auto-resolve identical sentences (Save Tokens)",
            variable=self.use_tm_var
        ).grid(row=0, column=1, sticky="w", padx=20, pady=2)

        self.auto_save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame,
            text=f"{Icons.SAVE} Auto-save to .dat & SQLite database as each file completes",
            variable=self.auto_save_var
        ).grid(row=1, column=1, sticky="w", padx=20, pady=2)

        # Progress Section
        prog_frame = ttk.LabelFrame(self, text="Translation Progress", padding=10)
        prog_frame.pack(fill=tk.X, padx=12, pady=5)

        self.status_lbl = ttk.Label(
            prog_frame,
            text="Ready to start.",
            font=("Arial", 9, "bold"),
            foreground="#333333"
        )
        self.status_lbl.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(6, 4))

        self.stats_lbl = ttk.Label(
            prog_frame,
            text="Files: 0/0 | AI Lines: 0 | TM Lines (Tokens Saved): 0",
            font=("Arial", 9),
            foreground="#007ACC"
        )
        self.stats_lbl.pack(anchor="w")

        # Log Output Frame
        log_frame = ttk.LabelFrame(self, text="Activity Log", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=5)

        self.log_text = tk.Text(log_frame, wrap="word", height=8, font=("Consolas", 9), state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Button Actions Bar
        btn_frame = ttk.Frame(self, padding=(12, 10))
        btn_frame.pack(fill=tk.X)

        self.start_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.DEPLOY} Start Batch Translation",
            command=self.start_batch_translation
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.DISCARD} Stop",
            command=self.stop_batch_translation,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=6)

        self.close_btn = ttk.Button(
            btn_frame,
            text="Close",
            command=self.on_close
        )
        self.close_btn.pack(side=tk.RIGHT)

    def log_msg(self, msg: str):
        def _append():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.after(0, _append)

    def get_target_files(self) -> List[Dict[str, Any]]:
        scope = self.scope_var.get()
        all_items = self.app.file_items
        active_idx = self.app.current_file_index

        current_folder = ""
        if 0 <= active_idx < len(all_items):
            rel = all_items[active_idx]["rel_path"].replace("/", os.sep)
            parts = rel.split(os.sep)
            if len(parts) > 1:
                current_folder = parts[0]

        filtered = []
        for item in all_items:
            fname = item["filename"].lower()
            if not fname.endswith(".dat"):
                continue

            stat = item.get("status", "untranslated")
            rel = item["rel_path"].replace("/", os.sep)
            parts = rel.split(os.sep)
            folder = parts[0] if len(parts) > 1 else ""

            if scope == "untranslated" and stat == "completed":
                continue
            if scope == "current_folder" and current_folder and folder != current_folder:
                continue

            filtered.append(item)

        return filtered

    def start_batch_translation(self):
        target_files = self.get_target_files()
        if not target_files:
            messagebox.showinfo("No Files Found", "No dialogue files match the selected filter criteria.")
            return

        is_local = "localhost" in self.ai.endpoint or "127.0.0.1" in self.ai.endpoint
        if not is_local and not self.ai.api_key:
            messagebox.showwarning(
                "API Key Required",
                "AI API Key has not been configured! Please configure your AI settings first."
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Batch Translation",
            f"Will begin automated translation for {len(target_files)} file(s).\n"
            f"Use TM: {'Yes' if self.use_tm_var.get() else 'No'}\n"
            f"Auto-Save: {'Yes' if self.auto_save_var.get() else 'No'}\n\n"
            "Proceed with batch translation now?"
        )
        if not confirm:
            return

        self.is_running = True
        self.stop_requested = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.close_btn.config(state=tk.DISABLED)

        self.progress_bar.config(maximum=len(target_files), value=0)
        self.log_msg(f"=== Starting Batch Translation ({len(target_files)} files) via {self.ai.model} ===")

        threading.Thread(target=self._batch_worker, args=(target_files,), daemon=True).start()

    def stop_batch_translation(self):
        if self.is_running:
            self.stop_requested = True
            self.status_lbl.config(text="Stopping after current file completes...", foreground="orange")
            self.log_msg("[WARNING] Process cancellation requested by user...")
            self.stop_btn.config(state=tk.DISABLED)

    def _batch_worker(self, target_files: List[Dict[str, Any]]):
        tot_files = len(target_files)
        ai_lines_count = 0
        tm_lines_count = 0
        use_tm = self.use_tm_var.get()
        auto_save = self.auto_save_var.get()

        for idx, item in enumerate(target_files, 1):
            if self.stop_requested:
                self.log_msg("Batch translation stopped by user.")
                break

            fname = item["filename"]
            rel_p = item["rel_path"]
            self.after(0, lambda i=idx, f=fname: self.status_lbl.config(
                text=f"Processing [{i}/{tot_files}]: {f}...",
                foreground="#007ACC"
            ))

            try:
                # 1. Load lines
                raw_bytes = None
                if item.get("is_virtual") and self.app.trpfs_client:
                    raw_bytes = self.app.trpfs_client.get_file(item["romfs_path"])
                elif os.path.exists(item.get("file_path", "")):
                    with open(item["file_path"], "rb") as f_in:
                        raw_bytes = f_in.read()

                if not raw_bytes:
                    self.log_msg(f"[{idx}/{tot_files}] Failed to read file data: {fname}")
                    continue

                orig_lines = self.app.codec.decode_bytes(raw_bytes)
                if not orig_lines:
                    self.log_msg(f"[{idx}/{tot_files}] Empty file: {fname}")
                    continue

                # 2. Check Translation Memory (TM) exact matches
                trans_lines = [""] * len(orig_lines)
                untranslated_indices = []
                file_tm_hits = 0

                for line_i, o_line in enumerate(orig_lines):
                    if use_tm:
                        tm_match = self.db.get_exact_tm_match(o_line, min_words=3)
                        if tm_match:
                            trans_lines[line_i] = tm_match
                            file_tm_hits += 1
                            continue
                    untranslated_indices.append(line_i)

                tm_lines_count += file_tm_hits

                # 3. Call AI for remaining lines
                if untranslated_indices:
                    needed_lines = [orig_lines[i] for i in untranslated_indices]
                    glossary_block = self.db.get_glossary_prompt_block()
                    tm_prompt = self.db.get_tm_prompt_block(needed_lines, max_suggestions=10)
                    combined_prompt = (glossary_block + "\n\n" + tm_prompt).strip()

                    ai_results = self.ai.translate_lines(
                        needed_lines,
                        target_lang="Indonesian",
                        glossary_block=combined_prompt,
                        max_workers=3
                    )

                    for orig_sub_i, res_line in enumerate(ai_results):
                        real_i = untranslated_indices[orig_sub_i]
                        # Sanitize tags via TagGuard
                        clean_line = TagGuard.sanitize_line(orig_lines[real_i], res_line)
                        trans_lines[real_i] = clean_line

                    ai_lines_count += len(needed_lines)

                # 4. Auto-learn pairs into Translation Memory
                pairs = list(zip(orig_lines, trans_lines))
                self.db.add_batch_tm_entries(pairs, context_file=fname)

                # 5. Auto-save to SQLite and .dat
                if auto_save:
                    compiled_bytes = self.app.codec.encode_lines(trans_lines)
                    out_path = os.path.join(self.app.workspace_dir, "translations", fname)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with open(out_path, "wb") as f_out:
                        f_out.write(compiled_bytes)

                    diffs, total = StatusTracker.count_diffs(orig_lines, trans_lines)
                    self.db.upsert_file_status(
                        filename=fname,
                        rel_path=rel_p,
                        total_lines=total,
                        diffs=diffs,
                        status="completed",
                        asset_type="text",
                        orig_lines=orig_lines,
                        trans_lines=trans_lines
                    )
                    item["status"] = "completed"
                    item["diffs"] = diffs
                    item["total"] = total

                tm_info = f" (TM: {file_tm_hits} lines)" if file_tm_hits else ""
                self.log_msg(f"[{idx}/{tot_files}] Completed: {fname} ({len(orig_lines)} lines){tm_info}")

            except Exception as e:
                self.log_msg(f"[{idx}/{tot_files}] ERROR on {fname}: {e}")
                log.error(f"Batch translation error on {fname}: {e}", exc_info=True)

            # Update progress UI
            self.after(0, lambda i=idx, tot=tot_files, a=ai_lines_count, t=tm_lines_count: self._update_ui_progress(i, tot, a, t))

        # Completion handler
        self.after(0, lambda a=ai_lines_count, t=tm_lines_count: self._on_batch_complete(a, t))

    def _update_ui_progress(self, cur_idx: int, tot_files: int, ai_lines: int, tm_lines: int):
        self.progress_bar.config(value=cur_idx)
        self.stats_lbl.config(
            text=f"Files: {cur_idx}/{tot_files} | AI Lines: {ai_lines} | TM Lines (Tokens Saved): {tm_lines}"
        )

    def _on_batch_complete(self, ai_lines: int, tm_lines: int):
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.close_btn.config(state=tk.NORMAL)

        self.status_lbl.config(text="Completed!", foreground="#2E7D32")
        self.log_msg(f"=== Batch Translation Completed: {ai_lines} lines translated by AI, {tm_lines} lines resolved instantly by TM! ===")

        # Refresh main app view
        try:
            self.app.update_progress_summary()
            self.app.populate_file_tree()
        except Exception:
            pass

        messagebox.showinfo(
            "Batch Completed",
            f"Batch translation process completed successfully!\n\n"
            f"• AI translated lines: {ai_lines}\n"
            f"• Lines saved via TM: {tm_lines}\n"
            f"• All results automatically saved to SQLite."
        )

    def on_close(self):
        if self.is_running:
            if not messagebox.askyesno("Task Running", "Batch translation is currently running in the background. Are you sure you want to exit?"):
                return
            self.stop_requested = True
        self.destroy()
