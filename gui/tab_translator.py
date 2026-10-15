import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Dict, Any, List, Optional
from formats.pokemon_dat import PokemonDatCodec
from core.tag_guard import TagGuard
from core.universal_ai import UniversalAIClient

class TranslatorTab(ctk.CTkFrame):
    def __init__(self, master, app_state):
        super().__init__(master, fg_color="transparent")
        self.app_state = app_state
        self.codec = PokemonDatCodec()
        
        settings = app_state.get("settings", {})
        self.ai = UniversalAIClient(
            provider=settings.get("ai_provider", "openai"),
            endpoint=settings.get("ai_endpoint", "https://api.openai.com/v1"),
            api_key=settings.get("ai_key", ""),
            model=settings.get("ai_model", "gpt-4o-mini"),
            custom_prompt=settings.get("custom_prompt", "")
        )

        # File states
        self.file_items: List[Dict[str, Any]] = []
        self.filtered_items: List[Dict[str, Any]] = []
        self.current_item: Optional[Dict[str, Any]] = None
        self.current_orig_lines: List[str] = []
        self.current_trans_lines: List[str] = []

        self.setup_ui()
        self.load_file_catalog()

    def sync_ai_config(self):
        settings = self.app_state.get("settings", {})
        self.ai.update_config(
            provider=settings.get("ai_provider", "openai"),
            endpoint=settings.get("ai_endpoint", "https://api.openai.com/v1"),
            api_key=settings.get("ai_key", ""),
            model=settings.get("ai_model", "gpt-4o-mini"),
            custom_prompt=settings.get("custom_prompt", "")
        )
        self.update_ai_badge()

    def update_ai_badge(self):
        prov = self.ai.provider.upper()
        model = self.ai.model
        self.ai_badge_lbl.configure(text=f"AI: {prov} ({model})")

    def setup_ui(self):
        # Configure layout: 2 Columns (Left: File List, Right: Editor)
        self.grid_columnconfigure(0, weight=0, minsize=320)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ----------------- LEFT PANEL (File List & Progress) -----------------
        left_panel = ctk.CTkFrame(self, corner_radius=10, width=320, fg_color="#1E293B")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.grid_rowconfigure(3, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # Title & Progress
        prog_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        prog_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        self.progress_lbl = ctk.CTkLabel(
            prog_frame, 
            text="Progres: Memuat...", 
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.progress_lbl.pack(anchor="w")

        self.progress_bar = ctk.CTkProgressBar(prog_frame, height=10)
        self.progress_bar.pack(fill="x", pady=(5, 5))
        self.progress_bar.set(0)

        # Search Bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_files())
        search_entry = ctk.CTkEntry(
            left_panel, 
            placeholder_text="🔍 Cari nama file...", 
            textvariable=self.search_var
        )
        search_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        # Filter Dropdown
        self.filter_var = ctk.StringVar(value="Semua File")
        filter_opt = ctk.CTkOptionMenu(
            left_panel,
            values=["Semua File", "Belum Diterjemahkan", "Sudah Diterjemahkan"],
            variable=self.filter_var,
            command=lambda v: self.filter_files()
        )
        filter_opt.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))

        # Scrollable File List
        self.file_list_frame = ctk.CTkScrollableFrame(left_panel, label_text="Daftar File Teks", corner_radius=8)
        self.file_list_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)

        # ----------------- RIGHT PANEL (Side-by-Side Editor) -----------------
        right_panel = ctk.CTkFrame(self, corner_radius=10, fg_color="#0F172A")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right_panel.grid_rowconfigure(2, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_columnconfigure(1, weight=1)

        # Editor Top Bar
        top_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=15, pady=10)

        self.cur_file_lbl = ctk.CTkLabel(
            top_bar, 
            text="Pilih file dari daftar sebelah kiri", 
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.cur_file_lbl.pack(side="left")

        # Action Buttons
        self.deploy_btn = ctk.CTkButton(
            top_bar,
            text="🚀 Deploy ke Eden",
            fg_color="#10B981",
            hover_color="#059669",
            width=130,
            command=self.deploy_mod_to_eden
        )
        self.deploy_btn.pack(side="right", padx=5)

        self.save_btn = ctk.CTkButton(
            top_bar,
            text="💾 Simpan .dat",
            fg_color="#3B82F6",
            hover_color="#2563EB",
            width=110,
            command=self.save_current_file
        )
        self.save_btn.pack(side="right", padx=5)

        self.ai_btn = ctk.CTkButton(
            top_bar,
            text="✨ Translate AI",
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            width=120,
            command=self.translate_current_with_ai
        )
        self.ai_btn.pack(side="right", padx=5)

        self.ai_badge_lbl = ctk.CTkLabel(
            top_bar,
            text="",
            text_color="#A78BFA",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.ai_badge_lbl.pack(side="right", padx=10)
        self.update_ai_badge()

        # Sub-header labels
        hdr_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        hdr_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 5))
        hdr_frame.grid_columnconfigure(0, weight=1)
        hdr_frame.grid_columnconfigure(1, weight=1)

        lbl_en = ctk.CTkLabel(hdr_frame, text="Bahasa Inggris (Original Game)", text_color="#94A3B8", anchor="w")
        lbl_en.grid(row=0, column=0, sticky="w")

        lbl_id = ctk.CTkLabel(hdr_frame, text="Bahasa Indonesia (Hasil Terjemahan)", text_color="#94A3B8", anchor="w")
        lbl_id.grid(row=0, column=1, sticky="w")

        # Text Boxes Frame
        text_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        text_container.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=15, pady=5)
        text_container.grid_rowconfigure(0, weight=1)
        text_container.grid_columnconfigure(0, weight=1)
        text_container.grid_columnconfigure(1, weight=1)

        # Left Text (Original)
        self.txt_orig = ctk.CTkTextbox(
            text_container, 
            wrap="none", 
            font=("Consolas", 13),
            fg_color="#1E293B",
            text_color="#CBD5E1"
        )
        self.txt_orig.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Right Text (Translated)
        self.txt_trans = ctk.CTkTextbox(
            text_container, 
            wrap="none", 
            font=("Consolas", 13),
            fg_color="#1E293B",
            text_color="#F8FAFC"
        )
        self.txt_trans.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        # Bottom Validation / Info Bar
        self.val_lbl = ctk.CTkLabel(
            right_panel, 
            text="Siap.", 
            text_color="#94A3B8", 
            anchor="w",
            font=ctk.CTkFont(size=12)
        )
        self.val_lbl.grid(row=3, column=0, columnspan=2, sticky="ew", padx=20, pady=(5, 10))

    def load_file_catalog(self):
        english_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"
        txt_dir = r"D:\Environtment\utilities\trinity\output\dat-text-editor"

        if not os.path.exists(english_dir):
            self.progress_lbl.configure(text="Folder English DAT tidak ditemukan!")
            return

        self.file_items.clear()

        # Scan all .dat recursively
        for root, _, files in os.walk(english_dir):
            for file in files:
                if file.endswith('.dat'):
                    dat_path = os.path.join(root, file)
                    base_name = file[:-4]
                    txt_path = os.path.join(txt_dir, f"{base_name}.txt")

                    # Check if translated txt exists
                    is_translated = os.path.exists(txt_path)

                    self.file_items.append({
                        "name": file,
                        "base_name": base_name,
                        "dat_path": dat_path,
                        "txt_path": txt_path,
                        "is_translated": is_translated,
                        "rel_path": os.path.relpath(dat_path, english_dir)
                    })

        self.file_items.sort(key=lambda x: (not x["is_translated"], x["name"]))
        self.filter_files()
        self.update_progress()

    def update_progress(self):
        total = len(self.file_items)
        translated = sum(1 for x in self.file_items if x["is_translated"])
        pct = (translated / total) if total > 0 else 0

        self.progress_bar.set(pct)
        self.progress_lbl.configure(text=f"Progres: {translated} / {total} File ({pct*100:.1f}%)")

    def filter_files(self):
        query = self.search_var.get().lower()
        filter_mode = self.filter_var.get()

        for widget in self.file_list_frame.winfo_children():
            widget.destroy()

        self.filtered_items = []
        for item in self.file_items:
            if query and query not in item["name"].lower():
                continue
            if filter_mode == "Belum Diterjemahkan" and item["is_translated"]:
                continue
            if filter_mode == "Sudah Diterjemahkan" and not item["is_translated"]:
                continue
            self.filtered_items.append(item)

        # Render rows
        for item in self.filtered_items[:200]:  # Limit initial render for speed
            btn_color = "#065F46" if item["is_translated"] else "#334155"
            icon = "🟢" if item["is_translated"] else "⚪"

            btn = ctk.CTkButton(
                self.file_list_frame,
                text=f"{icon} {item['name']}",
                anchor="w",
                fg_color="transparent",
                hover_color="#1E293B",
                text_color="white",
                height=28,
                command=lambda it=item: self.open_file_item(it)
            )
            btn.pack(fill="x", padx=2, pady=1)

    def open_file_item(self, item: Dict[str, Any]):
        self.current_item = item
        self.cur_file_lbl.configure(text=f"File: {item['name']} ({item['rel_path']})")

        # Read original English .dat
        try:
            self.current_orig_lines = self.codec.read_file(item["dat_path"])
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membaca file .dat: {e}")
            return

        # Read translated if exists
        self.current_trans_lines = []
        if os.path.exists(item["txt_path"]):
            with open(item["txt_path"], 'r', encoding='utf-8') as f:
                lines = f.readlines()
            start = 0
            for i, l in enumerate(lines):
                if "~~~~~~~~~~~~~~~" in l and i > 0:
                    start = i + 1
                    break
            self.current_trans_lines = [l.rstrip('\r\n') for l in lines[start:] if not l.startswith("~~~~~~~~~~~~~~~")]

        # If not translated, mirror original lines
        if not self.current_trans_lines:
            self.current_trans_lines = list(self.current_orig_lines)

        # Populate Textboxes
        self.txt_orig.delete("1.0", "end")
        self.txt_orig.insert("1.0", "\n".join(self.current_orig_lines))

        self.txt_trans.delete("1.0", "end")
        self.txt_trans.insert("1.0", "\n".join(self.current_trans_lines))

        # Validate
        valid, errors = TagGuard.validate_file(self.current_orig_lines, self.current_trans_lines)
        if valid:
            self.val_lbl.configure(text="✅ Struktur baris dan tag [VAR] valid.", text_color="#10B981")
        else:
            self.val_lbl.configure(text=f"⚠️ {errors[0]}", text_color="#F59E0B")

    def save_current_file(self):
        if not self.current_item:
            return

        content = self.txt_trans.get("1.0", "end-1c")
        lines = content.split("\n")

        valid, errors = TagGuard.validate_file(self.current_orig_lines, lines)
        if not valid:
            if not messagebox.askyesno("Peringatan Tag", f"Ada perbedaan tag:\n{errors[0]}\nTetap simpan?"):
                return

        # 1. Save to .txt
        self.codec.export_to_txt(self.current_item["dat_path"], self.current_item["txt_path"])
        with open(self.current_item["txt_path"], 'w', encoding='utf-8') as f:
            f.write("~~~~~~~~~~~~~~~\n")
            f.write(f"Text File: {self.current_item['name']}\n")
            f.write("~~~~~~~~~~~~~~~\n")
            for line in lines:
                f.write(line + "\n")

        # 2. Save/Re-encrypt to .dat
        try:
            self.codec.write_file(self.current_item["dat_path"], lines)
            self.current_item["is_translated"] = True
            self.update_progress()
            self.filter_files()
            self.val_lbl.configure(text=f"✅ Berhasil disimpan ke .dat & .txt ({self.current_item['name']})", text_color="#10B981")
        except Exception as e:
            messagebox.showerror("Error", f"Gagal mengompilasi .dat: {e}")

    def translate_current_with_ai(self):
        if not self.current_item:
            messagebox.showwarning("Pilih File", "Pilih file terlebih dahulu.")
            return

        is_local = "localhost" in self.ai.endpoint or "127.0.0.1" in self.ai.endpoint
        if not is_local and not self.ai.api_key:
            messagebox.showwarning(
                "API Key Belum Diisi", 
                f"API Key untuk provider '{self.ai.provider}' belum diisi.\nSilakan buka menu ⚙️ Pengaturan di pojok kanan atas untuk memasukkan Endpoint & API Key."
            )
            return

        self.ai_btn.configure(state="disabled", text="⏳ Menerjemahkan...")
        self.val_lbl.configure(text=f"Menghubungi AI ({self.ai.provider}: {self.ai.model})...", text_color="#38BDF8")

        def worker():
            try:
                translated = self.ai.translate_lines(self.current_orig_lines)
                self.after(0, lambda: self.on_ai_success(translated))
            except Exception as e:
                self.after(0, lambda: self.on_ai_fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def on_ai_success(self, translated_lines: List[str]):
        self.ai_btn.configure(state="normal", text="✨ Translate AI")
        self.txt_trans.delete("1.0", "end")
        self.txt_trans.insert("1.0", "\n".join(translated_lines))
        self.val_lbl.configure(text="✅ Terjemahan AI selesai! Periksa dan klik 'Simpan .dat'.", text_color="#10B981")

    def on_ai_fail(self, error_msg: str):
        self.ai_btn.configure(state="normal", text="✨ Translate AI")
        self.val_lbl.configure(text=f"❌ {error_msg}", text_color="#EF4444")
        messagebox.showerror("AI Translation Error", error_msg)

    def deploy_mod_to_eden(self):
        title_id = self.app_state.get("active_game_id", "0100A3D008C5C000")
        load_path = self.app_state.get("settings", {}).get("eden_load_path")
        mod_name = "[ID] Pokemon Scarlet Bahasa Indonesia"

        target_dir = os.path.join(load_path, title_id, mod_name, "romfs", "message", "dat", "English")
        os.makedirs(target_dir, exist_ok=True)

        english_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"

        count = 0
        for root, _, files in os.walk(english_dir):
            for f in files:
                if f.endswith('.dat'):
                    src = os.path.join(root, f)
                    rel = os.path.relpath(src, english_dir)
                    dest = os.path.join(target_dir, rel)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(src, 'rb') as r, open(dest, 'wb') as w:
                        w.write(r.read())
                    count += 1

        messagebox.showinfo(
            "Deploy Berhasil!", 
            f"Berhasil men-deploy {count} file .dat ke folder mod Eden:\n{os.path.join(load_path, title_id, mod_name)}\n\nBuka Eden Emulator untuk memainkan game!"
        )
