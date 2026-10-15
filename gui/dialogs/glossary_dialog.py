"""
Kamus Istilah (Glossary) Dialog untuk Switch Mod Studio.
Menyediakan antarmuka manajemen glosarium/kamus istilah untuk konsistensi terjemahan AI.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any

from core.icons import Icons
from core.logger import log


class GlossaryDialog(tk.Toplevel):
    """
    Dialog modal untuk mengelola glosarium (kamus istilah penerjemahan).
    Mendukung melihat, menambah, mengubah, dan menghapus istilah glosarium.
    """

    def __init__(self, parent, db, ai: Optional[Any] = None, current_lines: Optional[List[str]] = None):
        """
        Inisialisasi dialog Kamus Istilah.
        
        Args:
            parent: Komponen Tkinter induk (aplikasi utama).
            db: Instance ProjectDB untuk interaksi database SQLite.
            ai: Instance UniversalAIClient (opsional) untuk pemindaian istilah otomatis.
            current_lines: Daftar baris dialog file aktif untuk dipindai.
        """
        super().__init__(parent)
        self.parent = parent
        self.db = db
        self.ai = ai
        self.current_lines = current_lines or []
        self.selected_id: Optional[int] = None
        self.all_terms: List[Dict[str, Any]] = []

        # Konfigurasi jendela
        self.title("Glossary (Terminology)")
        self.geometry("700x500")
        self.minsize(650, 450)
        self.transient(parent)

        # Pusatkan dialog terhadap jendela induk
        self._center_on_parent(parent)

        # Bangun seluruh elemen antarmuka pengguna
        self._build_ui()

        # Muat data awal ke tabel
        self.refresh_table()

        # Jadikan dialog modal
        self.grab_set()
        self.focus_set()

    def _center_on_parent(self, parent):
        """Memposisikan dialog tepat di tengah jendela induk."""
        self.update_idletasks()
        try:
            if parent:
                parent_w = parent.winfo_width()
                parent_h = parent.winfo_height()
                parent_x = parent.winfo_rootx()
                parent_y = parent.winfo_rooty()

                if parent_w > 100 and parent_h > 100:
                    x = parent_x + (parent_w - 700) // 2
                    y = parent_y + (parent_h - 500) // 2
                    self.geometry(f"700x500+{max(0, x)}+{max(0, y)}")
                    return
            # Fallback jika parent belum siap/terlihat
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = max(0, (screen_w - 700) // 2)
            y = max(0, (screen_h - 500) // 2)
            self.geometry(f"700x500+{x}+{y}")
        except Exception as e:
            log.debug(f"Pusatkan dialog glossary gagal, menggunakan posisi default: {e}")

    def _build_ui(self):
        """Membangun tata letak UI dialog."""
        # Frame Kontainer Utama
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ----------------- Header & Pencarian -----------------
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        # Judul Dialog
        title_lbl = ttk.Label(
            header_frame,
            text=f"{Icons.GLOSSARY} Glossary (Terminology)",
            font=("Segoe UI", 11, "bold")
        )
        title_lbl.pack(side=tk.LEFT)

        # Filter Kategori Dropdown di Header
        self.filter_cat_var = tk.StringVar(value="All Categories")
        cat_filter_combo = ttk.Combobox(
            header_frame,
            textvariable=self.filter_cat_var,
            values=["All Categories", "general", "pokemon", "game_term", "location", "character"],
            state="readonly",
            width=14
        )
        cat_filter_combo.pack(side=tk.RIGHT, padx=(4, 0))
        cat_filter_combo.bind("<<ComboboxSelected>>", self.apply_filter)

        ttk.Label(header_frame, text="Category:").pack(side=tk.RIGHT, padx=(8, 2))

        # Kotak Pencarian Teks
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filter())

        search_entry = ttk.Entry(header_frame, textvariable=self.search_var, width=18)
        search_entry.pack(side=tk.RIGHT, padx=(2, 4))

        search_icon_lbl = ttk.Label(
            header_frame,
            text=f"{Icons.SEARCH} Search:",
            font=("Segoe Fluent Icons", 11)
        )
        search_icon_lbl.pack(side=tk.RIGHT, padx=(2, 2))

        # ----------------- Tabel Treeview -----------------
        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        columns = ("no", "term_en", "term_id", "category", "notes")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("no", text="No")
        self.tree.heading("term_en", text="English Term")
        self.tree.heading("term_id", text="Indonesian Term")
        self.tree.heading("category", text="Category")
        self.tree.heading("notes", text="Notes")

        self.tree.column("no", width=45, minwidth=35, anchor="center", stretch=False)
        self.tree.column("term_en", width=170, minwidth=110, anchor="w", stretch=True)
        self.tree.column("term_id", width=170, minwidth=110, anchor="w", stretch=True)
        self.tree.column("category", width=105, minwidth=85, anchor="center", stretch=False)
        self.tree.column("notes", width=160, minwidth=90, anchor="w", stretch=True)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # ----------------- Form Input Data -----------------
        form_frame = ttk.LabelFrame(main_frame, text=" Term Details ", padding=(10, 8))
        form_frame.pack(fill=tk.X, pady=(0, 8))

        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(3, weight=1)

        # Baris 0: English Term & Category
        ttk.Label(form_frame, text="English Term:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        self.en_entry = ttk.Entry(form_frame)
        self.en_entry.grid(row=0, column=1, sticky=tk.EW, padx=(0, 16), pady=3)

        ttk.Label(form_frame, text="Category:").grid(row=0, column=2, sticky=tk.W, padx=(0, 6), pady=3)
        self.cat_combo = ttk.Combobox(
            form_frame,
            values=["general", "pokemon", "game_term", "location", "character"],
            state="readonly",
            width=16
        )
        self.cat_combo.set("general")
        self.cat_combo.grid(row=0, column=3, sticky=tk.EW, pady=3)

        # Baris 1: Indonesian Term & Notes
        ttk.Label(form_frame, text="Indonesian Term:").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        self.id_entry = ttk.Entry(form_frame)
        self.id_entry.grid(row=1, column=1, sticky=tk.EW, padx=(0, 16), pady=3)

        ttk.Label(form_frame, text="Notes:").grid(row=1, column=2, sticky=tk.W, padx=(0, 6), pady=3)
        self.notes_entry = ttk.Entry(form_frame)
        self.notes_entry.grid(row=1, column=3, sticky=tk.EW, pady=3)

        # ----------------- Action Buttons -----------------
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        # Add Button
        self.add_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.ACCEPT} Add",
            command=self.add_term
        )
        self.add_btn.pack(side=tk.LEFT, padx=(0, 4))

        # Update Button
        self.update_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.EDIT} Update",
            command=self.update_term
        )
        self.update_btn.pack(side=tk.LEFT, padx=4)

        # Delete Button
        self.delete_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.DISCARD} Delete",
            command=self.delete_term
        )
        self.delete_btn.pack(side=tk.LEFT, padx=4)

        # Clear Form Button
        self.clear_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.REFRESH} Clear",
            command=self.clear_form
        )
        self.clear_btn.pack(side=tk.LEFT, padx=4)

        # Scan AI Dialogue Button
        if self.ai and self.current_lines:
            self.scan_btn = ttk.Button(
                btn_frame,
                text=f"{Icons.AI_SPARKLE} Scan AI Dialogue",
                command=self.scan_with_ai
            )
            self.scan_btn.pack(side=tk.LEFT, padx=8)

        # Close Button
        self.close_btn = ttk.Button(
            btn_frame,
            text="Close",
            command=self.destroy
        )
        self.close_btn.pack(side=tk.RIGHT)

        # ----------------- Status Bar -----------------
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_lbl = ttk.Label(
            status_frame,
            text="Total: 0 registered terms",
            font=("Segoe UI", 9)
        )
        self.status_lbl.pack(side=tk.LEFT)

    def refresh_table(self):
        """Reload glossary terms from database into Treeview table."""
        try:
            self.all_terms = self.db.get_glossary()
        except Exception as e:
            log.error(f"Failed to fetch glossary from database: {e}", exc_info=True)
            self.all_terms = []

        self.apply_filter()

    def apply_filter(self, event=None):
        """Filter terms in table based on search query and category."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        query = self.search_var.get().strip().lower()
        selected_cat = self.filter_cat_var.get()

        filtered: List[Dict[str, Any]] = []
        for term in self.all_terms:
            cat = str(term.get("category", "")).strip()
            if selected_cat and selected_cat not in ("All Categories", "Semua Kategori") and cat != selected_cat:
                continue

            if query:
                en_match = query in str(term.get("term_en", "")).lower()
                id_match = query in str(term.get("term_id", "")).lower()
                notes_match = query in str(term.get("notes", "")).lower()
                if not (en_match or id_match or notes_match):
                    continue

            filtered.append(term)

        # Insert filtered items
        for idx, term in enumerate(filtered, start=1):
            term_pk = term.get("id", idx)
            term_en = term.get("term_en", "")
            term_id = term.get("term_id", "")
            cat = term.get("category", "general")
            notes = term.get("notes", "")

            self.tree.insert(
                "",
                "end",
                iid=str(term_pk),
                values=(idx, term_en, term_id, cat, notes)
            )

        # Update count status
        total = len(self.all_terms)
        if query or (selected_cat and selected_cat not in ("All Categories", "Semua Kategori")):
            self.status_lbl.config(
                text=f"Showing {len(filtered)} of {total} registered terms"
            )
        else:
            self.status_lbl.config(
                text=f"Total: {total} registered terms"
            )

    def on_select(self, event=None):
        """Mengisi formulir input ketika salah satu baris di tabel dipilih."""
        selected = self.tree.selection()
        if not selected:
            return

        item_iid = selected[0]
        values = self.tree.item(item_iid, "values")
        if not values or len(values) < 5:
            return

        try:
            self.selected_id = int(item_iid)
        except (ValueError, TypeError):
            self.selected_id = None

        term_en = values[1]
        term_id = values[2]
        cat = values[3]
        notes = values[4] if len(values) > 4 else ""

        self.en_entry.delete(0, tk.END)
        self.en_entry.insert(0, term_en)

        self.id_entry.delete(0, tk.END)
        self.id_entry.insert(0, term_id)

        valid_cats = ["general", "pokemon", "game_term", "location", "character"]
        self.cat_combo.set(cat if cat in valid_cats else "general")

        self.notes_entry.delete(0, tk.END)
        self.notes_entry.insert(0, notes)

    def add_term(self):
        """Read input form and insert a new term into glossary."""
        term_en = self.en_entry.get().strip()
        term_id = self.id_entry.get().strip()
        category = self.cat_combo.get().strip() or "general"
        notes = self.notes_entry.get().strip()

        if not term_en:
            messagebox.showwarning(
                "Warning",
                "English Term cannot be empty!",
                parent=self
            )
            self.en_entry.focus_set()
            return

        if not term_id:
            messagebox.showwarning(
                "Warning",
                "Indonesian Term cannot be empty!",
                parent=self
            )
            self.id_entry.focus_set()
            return

        try:
            self.db.add_glossary_term(term_en, term_id, category, notes)
            log.info(f"Glossary: New term '{term_en}' -> '{term_id}' successfully added")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Successfully added term: '{term_en}'")
        except Exception as e:
            log.error(f"Failed to add glossary term: {e}", exc_info=True)
            messagebox.showerror(
                "Error",
                f"Failed to add term to database:\n{e}",
                parent=self
            )

    def update_term(self):
        """Read input form and update the selected glossary term."""
        if self.selected_id is None:
            messagebox.showwarning(
                "Warning",
                "Please select a term to update from the table first!",
                parent=self
            )
            return

        term_en = self.en_entry.get().strip()
        term_id = self.id_entry.get().strip()
        category = self.cat_combo.get().strip() or "general"
        notes = self.notes_entry.get().strip()

        if not term_en:
            messagebox.showwarning(
                "Warning",
                "English Term cannot be empty!",
                parent=self
            )
            self.en_entry.focus_set()
            return

        if not term_id:
            messagebox.showwarning(
                "Warning",
                "Indonesian Term cannot be empty!",
                parent=self
            )
            self.id_entry.focus_set()
            return

        try:
            self.db.update_glossary_term(self.selected_id, term_en, term_id, category, notes)
            log.info(f"Glossary: Term ID {self.selected_id} ('{term_en}') updated successfully")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Successfully updated term: '{term_en}'")
        except Exception as e:
            log.error(f"Failed to update glossary term: {e}", exc_info=True)
            messagebox.showerror(
                "Error",
                f"Failed to update term in database:\n{e}",
                parent=self
            )

    def delete_term(self):
        """Delete currently selected glossary term after user confirmation."""
        if self.selected_id is None:
            messagebox.showwarning(
                "Warning",
                "Please select a term to delete from the table first!",
                parent=self
            )
            return

        term_en = self.en_entry.get().strip()
        confirm_text = (
            f"Are you sure you want to delete term '{term_en}' from the glossary?"
            if term_en else "Are you sure you want to delete the selected term from the glossary?"
        )

        if not messagebox.askyesno("Confirm Delete", confirm_text, parent=self):
            return

        try:
            self.db.delete_glossary_term(self.selected_id)
            log.info(f"Glossary: Term ID {self.selected_id} ('{term_en}') deleted")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Term '{term_en}' deleted from glossary.")
        except Exception as e:
            log.error(f"Failed to delete glossary term: {e}", exc_info=True)
            messagebox.showerror(
                "Error",
                f"Failed to delete term from database:\n{e}",
                parent=self
            )

    def clear_form(self):
        """Clear form inputs and deselect table row."""
        self.selected_id = None
        self.en_entry.delete(0, tk.END)
        self.id_entry.delete(0, tk.END)
        self.cat_combo.set("general")
        self.notes_entry.delete(0, tk.END)

        selected = self.tree.selection()
        if selected:
            self.tree.selection_remove(selected)

        self.en_entry.focus_set()

    def scan_with_ai(self):
        """Scan active dialogue lines to extract and register domain terminology with AI."""
        if not self.ai or not self.current_lines:
            messagebox.showwarning("Warning", "No dialogue lines currently loaded to scan.", parent=self)
            return

        if hasattr(self, 'scan_btn'):
            self.scan_btn.config(state=tk.DISABLED, text=f"{Icons.SYNC} Scanning...")
        self.status_lbl.config(text="AI is analyzing dialogue to extract domain terminology...")

        def _worker():
            try:
                new_terms = self.ai.extract_glossary_terms(self.current_lines, self.all_terms)
                added_count = 0
                for item in new_terms:
                    en = item.get("term_en")
                    id_val = item.get("term_id")
                    cat = item.get("category", "game_term")
                    notes = item.get("notes", "Learned automatically by AI from dialogue")
                    if en and id_val:
                        self.db.add_glossary_term(en, id_val, cat, notes)
                        added_count += 1

                def _finish():
                    if hasattr(self, 'scan_btn'):
                        self.scan_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Scan AI Dialogue")
                    self.refresh_table()
                    if added_count > 0:
                        messagebox.showinfo(
                            "Scan Completed",
                            f"AI successfully found and added {added_count} new terms to the Glossary!",
                            parent=self
                        )
                    else:
                        messagebox.showinfo(
                            "Scan Completed",
                            "AI did not find any new unique terms not already in the glossary.",
                            parent=self
                        )
                self.after(0, _finish)
            except Exception as e:
                err_msg = str(e)
                log.error(f"Failed to scan terms with AI: {err_msg}", exc_info=True)
                def _err():
                    if hasattr(self, 'scan_btn'):
                        self.scan_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Scan AI Dialogue")
                    self.refresh_table()
                    messagebox.showerror("AI Scan Error", f"Failed to scan terms:\n{err_msg}", parent=self)
                self.after(0, _err)

        import threading
        threading.Thread(target=_worker, daemon=True).start()
