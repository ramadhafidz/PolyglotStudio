import os
import threading
import customtkinter as ctk
from tkinter import messagebox
from formats.pokemon_dat import PokemonDatCodec

class ToolsTab(ctk.CTkFrame):
    def __init__(self, master, app_state):
        super().__init__(master, fg_color="transparent")
        self.app_state = app_state
        self.codec = PokemonDatCodec()

        self.setup_ui()

    def setup_ui(self):
        container = ctk.CTkScrollableFrame(self, label_text="🛠️ RomFS & Batch Automation Tools", corner_radius=10)
        container.pack(fill="both", expand=True, padx=20, pady=15)

        # ----------------- SECTION 1: Batch Operations -----------------
        sec1 = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8)
        sec1.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(sec1, text="⚡ Operasi Batch Massal", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkLabel(sec1, text="Ekspor atau kompilasi seluruh 913 file teks game secara otomatis dalam 2 detik.", text_color="#94A3B8").pack(anchor="w", padx=15, pady=(0, 10))

        btn_row1 = ctk.CTkFrame(sec1, fg_color="transparent")
        btn_row1.pack(fill="x", padx=15, pady=(0, 15))

        self.batch_export_btn = ctk.CTkButton(
            btn_row1, 
            text="📤 Batch Export Semua .dat ➔ .txt", 
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self.run_batch_export
        )
        self.batch_export_btn.pack(side="left", padx=(0, 10))

        self.batch_repack_btn = ctk.CTkButton(
            btn_row1, 
            text="📥 Batch Repack Semua .txt ➔ .dat", 
            fg_color="#10B981",
            hover_color="#059669",
            command=self.run_batch_repack
        )
        self.batch_repack_btn.pack(side="left")

        # ----------------- SECTION 2: Quick Directory Access -----------------
        sec2 = ctk.CTkFrame(container, fg_color="#1E293B", corner_radius=8)
        sec2.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(sec2, text="📂 Pintasan Akses Folder Cepat", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))

        dirs = [
            ("📁 RomFS Dump Asli", r"E:\Modding\eden\dump\0100A3D008C5C000\romfs"),
            ("📁 Folder Mod Eden Emulator", self.app_state.get("settings", {}).get("eden_load_path", "")),
            ("📁 Folder File .dat (English)", r"D:\Environtment\utilities\trinity\output\message\dat\English"),
            ("📁 Folder File .txt Terjemahan", r"D:\Environtment\utilities\trinity\output\dat-text-editor"),
            ("📁 Folder Trinity File Explorer", r"D:\Environtment\utilities\trinity\fileexplorer"),
            ("📁 Folder Backup 39 File Aman", r"E:\Modding\SwitchModStudio\backup_39_files")
        ]

        for label, path in dirs:
            row = ctk.CTkFrame(sec2, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=4)

            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(weight="bold"), width=220, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=path, text_color="#94A3B8", anchor="w").pack(side="left", fill="x", expand=True, padx=10)

            open_btn = ctk.CTkButton(
                row, 
                text="Buka", 
                width=70, 
                height=26,
                fg_color="#334155", 
                hover_color="#475569",
                command=lambda p=path: self.open_folder(p)
            )
            open_btn.pack(side="right")

        # Status Label
        self.tool_status = ctk.CTkLabel(container, text="", text_color="#94A3B8")
        self.tool_status.pack(pady=10)

    def open_folder(self, path: str):
        if os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Folder Tidak Ada", f"Folder tidak ditemukan:\n{path}")

    def run_batch_export(self):
        english_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"
        txt_dir = r"D:\Environtment\utilities\trinity\output\dat-text-editor"
        os.makedirs(txt_dir, exist_ok=True)

        self.batch_export_btn.configure(state="disabled", text="⏳ Mengekspor...")
        self.tool_status.configure(text="Mengekspor file .dat ke .txt...", text_color="#38BDF8")

        def worker():
            exported = 0
            skipped = 0
            for root, _, files in os.walk(english_dir):
                for f in files:
                    if f.endswith('.dat'):
                        dat_path = os.path.join(root, f)
                        base_name = f[:-4]
                        txt_path = os.path.join(txt_dir, f"{base_name}.txt")

                        if os.path.exists(txt_path):
                            skipped += 1
                            continue

                        try:
                            self.codec.export_to_txt(dat_path, txt_path)
                            exported += 1
                        except Exception:
                            pass

            self.after(0, lambda: self.on_export_done(exported, skipped))

        threading.Thread(target=worker, daemon=True).start()

    def on_export_done(self, exported: int, skipped: int):
        self.batch_export_btn.configure(state="normal", text="📤 Batch Export Semua .dat ➔ .txt")
        self.tool_status.configure(text=f"✅ Selesai: {exported} file baru diekspor, {skipped} file lama dilindungi (tidak ditimpa).", text_color="#10B981")
        messagebox.showinfo("Export Selesai", f"Berhasil mengekspor:\n• {exported} file .txt baru\n• {skipped} file lama aman tidak ditimpa.")

    def run_batch_repack(self):
        english_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"
        txt_dir = r"D:\Environtment\utilities\trinity\output\dat-text-editor"

        self.batch_repack_btn.configure(state="disabled", text="⏳ Mengompilasi...")
        self.tool_status.configure(text="Mengompilasi file .txt ke .dat...", text_color="#38BDF8")

        def worker():
            repacked = 0
            errors = 0
            for root, _, files in os.walk(english_dir):
                for f in files:
                    if f.endswith('.dat'):
                        dat_path = os.path.join(root, f)
                        base_name = f[:-4]
                        txt_path = os.path.join(txt_dir, f"{base_name}.txt")

                        if os.path.exists(txt_path):
                            try:
                                self.codec.import_from_txt(txt_path, dat_path)
                                repacked += 1
                            except Exception:
                                errors += 1

            self.after(0, lambda: self.on_repack_done(repacked, errors))

        threading.Thread(target=worker, daemon=True).start()

    def on_repack_done(self, repacked: int, errors: int):
        self.batch_repack_btn.configure(state="normal", text="📥 Batch Repack Semua .txt ➔ .dat")
        self.tool_status.configure(text=f"✅ Selesai: {repacked} file .dat berhasil dikompilasi (Gagal: {errors}).", text_color="#10B981")
        messagebox.showinfo("Repack Selesai", f"Berhasil mengompilasi {repacked} file .dat ke folder game!\nGagal: {errors}")
