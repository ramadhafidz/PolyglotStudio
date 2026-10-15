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
        self.title("Kamus Istilah (Glossary)")
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
            text=f"{Icons.GLOSSARY} Kamus Istilah (Glossary)",
            font=("Segoe UI", 11, "bold")
        )
        title_lbl.pack(side=tk.LEFT)

        # Filter Kategori Dropdown di Header
        self.filter_cat_var = tk.StringVar(value="Semua Kategori")
        cat_filter_combo = ttk.Combobox(
            header_frame,
            textvariable=self.filter_cat_var,
            values=["Semua Kategori", "general", "pokemon", "game_term", "location", "character"],
            state="readonly",
            width=14
        )
        cat_filter_combo.pack(side=tk.RIGHT, padx=(4, 0))
        cat_filter_combo.bind("<<ComboboxSelected>>", self.apply_filter)

        ttk.Label(header_frame, text="Kategori:").pack(side=tk.RIGHT, padx=(8, 2))

        # Kotak Pencarian Teks
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filter())

        search_entry = ttk.Entry(header_frame, textvariable=self.search_var, width=18)
        search_entry.pack(side=tk.RIGHT, padx=(2, 4))

        search_icon_lbl = ttk.Label(
            header_frame,
            text=f"{Icons.SEARCH} Cari:",
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
        form_frame = ttk.LabelFrame(main_frame, text=" Formulir Istilah ", padding=(10, 8))
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

        # ----------------- Tombol Aksi -----------------
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        # Tombol Tambah
        self.add_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.ACCEPT} Tambah",
            command=self.add_term
        )
        self.add_btn.pack(side=tk.LEFT, padx=(0, 4))

        # Tombol Ubah
        self.update_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.EDIT} Ubah",
            command=self.update_term
        )
        self.update_btn.pack(side=tk.LEFT, padx=4)

        # Tombol Hapus
        self.delete_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.DISCARD} Hapus",
            command=self.delete_term
        )
        self.delete_btn.pack(side=tk.LEFT, padx=4)

        # Tombol Bersihkan Pilihan
        self.clear_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.REFRESH} Bersihkan",
            command=self.clear_form
        )
        self.clear_btn.pack(side=tk.LEFT, padx=4)

        # Tombol Pindai Kosakata dengan AI (jika AI dan dialog saat ini tersedia)
        if self.ai and self.current_lines:
            self.scan_btn = ttk.Button(
                btn_frame,
                text=f"{Icons.AI_SPARKLE} Pindai Dialog AI",
                command=self.scan_with_ai
            )
            self.scan_btn.pack(side=tk.LEFT, padx=8)

        # Tombol Tutup
        self.close_btn = ttk.Button(
            btn_frame,
            text="Tutup",
            command=self.destroy
        )
        self.close_btn.pack(side=tk.RIGHT)

        # ----------------- Status Bar -----------------
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_lbl = ttk.Label(
            status_frame,
            text="Total: 0 istilah terdaftar",
            font=("Segoe UI", 9)
        )
        self.status_lbl.pack(side=tk.LEFT)

    def refresh_table(self):
        """Memuat ulang data glosarium dari database ke tabel Treeview."""
        try:
            self.all_terms = self.db.get_glossary()
        except Exception as e:
            log.error(f"Gagal mengambil glosarium dari database: {e}", exc_info=True)
            self.all_terms = []

        self.apply_filter()

    def apply_filter(self, event=None):
        """Menyaring tampilan istilah di tabel berdasarkan pencarian teks dan kategori."""
        # Bersihkan baris tabel yang ada
        for item in self.tree.get_children():
            self.tree.delete(item)

        query = self.search_var.get().strip().lower()
        selected_cat = self.filter_cat_var.get()

        filtered: List[Dict[str, Any]] = []
        for term in self.all_terms:
            cat = str(term.get("category", "")).strip()
            if selected_cat and selected_cat != "Semua Kategori" and cat != selected_cat:
                continue

            if query:
                en_match = query in str(term.get("term_en", "")).lower()
                id_match = query in str(term.get("term_id", "")).lower()
                notes_match = query in str(term.get("notes", "")).lower()
                if not (en_match or id_match or notes_match):
                    continue

            filtered.append(term)

        # Masukkan baris yang lolos filter
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

        # Perbarui status jumlah istilah
        total = len(self.all_terms)
        if query or (selected_cat and selected_cat != "Semua Kategori"):
            self.status_lbl.config(
                text=f"Menampilkan {len(filtered)} dari {total} istilah terdaftar"
            )
        else:
            self.status_lbl.config(
                text=f"Total: {total} istilah terdaftar"
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
        """Membaca formulir input dan menambahkan istilah baru ke glosarium."""
        term_en = self.en_entry.get().strip()
        term_id = self.id_entry.get().strip()
        category = self.cat_combo.get().strip() or "general"
        notes = self.notes_entry.get().strip()

        if not term_en:
            messagebox.showwarning(
                "Peringatan",
                "Istilah Bahasa Inggris (English Term) tidak boleh kosong!",
                parent=self
            )
            self.en_entry.focus_set()
            return

        if not term_id:
            messagebox.showwarning(
                "Peringatan",
                "Istilah Bahasa Indonesia (Indonesian Term) tidak boleh kosong!",
                parent=self
            )
            self.id_entry.focus_set()
            return

        try:
            self.db.add_glossary_term(term_en, term_id, category, notes)
            log.info(f"Glosarium: Istilah baru '{term_en}' -> '{term_id}' berhasil ditambahkan")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Berhasil menambahkan istilah: '{term_en}'")
        except Exception as e:
            log.error(f"Gagal menambahkan istilah glosarium: {e}", exc_info=True)
            messagebox.showerror(
                "Kesalahan",
                f"Gagal menambahkan istilah ke database:\n{e}",
                parent=self
            )

    def update_term(self):
        """Membaca formulir input dan memperbarui istilah glosarium yang dipilih."""
        if self.selected_id is None:
            messagebox.showwarning(
                "Peringatan",
                "Silakan pilih istilah yang ingin diubah terlebih dahulu dari tabel!",
                parent=self
            )
            return

        term_en = self.en_entry.get().strip()
        term_id = self.id_entry.get().strip()
        category = self.cat_combo.get().strip() or "general"
        notes = self.notes_entry.get().strip()

        if not term_en:
            messagebox.showwarning(
                "Peringatan",
                "Istilah Bahasa Inggris (English Term) tidak boleh kosong!",
                parent=self
            )
            self.en_entry.focus_set()
            return

        if not term_id:
            messagebox.showwarning(
                "Peringatan",
                "Istilah Bahasa Indonesia (Indonesian Term) tidak boleh kosong!",
                parent=self
            )
            self.id_entry.focus_set()
            return

        try:
            self.db.update_glossary_term(self.selected_id, term_en, term_id, category, notes)
            log.info(f"Glosarium: Istilah ID {self.selected_id} ('{term_en}') berhasil diperbarui")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Berhasil memperbarui istilah: '{term_en}'")
        except Exception as e:
            log.error(f"Gagal memperbarui istilah glosarium: {e}", exc_info=True)
            messagebox.showerror(
                "Kesalahan",
                f"Gagal memperbarui istilah di database:\n{e}",
                parent=self
            )

    def delete_term(self):
        """Menghapus istilah glosarium yang sedang dipilih setelah konfirmasi."""
        if self.selected_id is None:
            messagebox.showwarning(
                "Peringatan",
                "Silakan pilih istilah yang ingin dihapus terlebih dahulu dari tabel!",
                parent=self
            )
            return

        term_en = self.en_entry.get().strip()
        confirm_text = (
            f"Apakah Anda yakin ingin menghapus istilah '{term_en}' dari glosarium?"
            if term_en else "Apakah Anda yakin ingin menghapus istilah terpilih dari glosarium?"
        )

        if not messagebox.askyesno("Konfirmasi Hapus", confirm_text, parent=self):
            return

        try:
            self.db.delete_glossary_term(self.selected_id)
            log.info(f"Glosarium: Istilah ID {self.selected_id} ('{term_en}') berhasil dihapus")
            self.clear_form()
            self.refresh_table()
            self.status_lbl.config(text=f"Istilah '{term_en}' berhasil dihapus dari glosarium.")
        except Exception as e:
            log.error(f"Gagal menghapus istilah glosarium: {e}", exc_info=True)
            messagebox.showerror(
                "Kesalahan",
                f"Gagal menghapus istilah dari database:\n{e}",
                parent=self
            )

    def clear_form(self):
        """Membersihkan formulir input dan melepaskan pilihan pada tabel."""
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
        """Memindai dialog file saat ini untuk mengekstrak dan mencatat kosakata baru secara otomatis dengan AI."""
        if not self.ai or not self.current_lines:
            messagebox.showwarning("Peringatan", "Tidak ada baris dialog yang sedang dimuat untuk dipindai.", parent=self)
            return

        if hasattr(self, 'scan_btn'):
            self.scan_btn.config(state=tk.DISABLED, text=f"{Icons.SYNC} Memindai...")
        self.status_lbl.config(text="AI sedang menganalisis dialog untuk menemukan kosakata khas...")

        def _worker():
            try:
                new_terms = self.ai.extract_glossary_terms(self.current_lines, self.all_terms)
                added_count = 0
                for item in new_terms:
                    en = item.get("term_en")
                    id_val = item.get("term_id")
                    cat = item.get("category", "game_term")
                    notes = item.get("notes", "Otomatis dipindai AI dari dialog")
                    if en and id_val:
                        self.db.add_glossary_term(en, id_val, cat, notes)
                        added_count += 1

                def _finish():
                    if hasattr(self, 'scan_btn'):
                        self.scan_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Pindai Dialog AI")
                    self.refresh_table()
                    if added_count > 0:
                        messagebox.showinfo(
                            "Pindai Selesai",
                            f"AI berhasil menemukan dan menambahkan {added_count} kosakata baru ke Kamus Istilah!",
                            parent=self
                        )
                    else:
                        messagebox.showinfo(
                            "Pindai Selesai",
                            "AI tidak menemukan istilah khas baru yang belum terdaftar di kamus.",
                            parent=self
                        )
                self.after(0, _finish)
            except Exception as e:
                err_msg = str(e)
                log.error(f"Gagal memindai istilah dengan AI: {err_msg}", exc_info=True)
                def _err():
                    if hasattr(self, 'scan_btn'):
                        self.scan_btn.config(state=tk.NORMAL, text=f"{Icons.AI_SPARKLE} Pindai Dialog AI")
                    self.refresh_table()
                    messagebox.showerror("Kesalahan Pindai AI", f"Gagal memindai istilah:\n{err_msg}", parent=self)
                self.after(0, _err)

        import threading
        threading.Thread(target=_worker, daemon=True).start()
