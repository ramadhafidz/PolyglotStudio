"""
1-Click LayeredFS Mod Deployer Dialog untuk Polyglot Studio.
Antarmuka visual modern untuk mengompilasi seluruh file yang diubah saja,
menghasilkan struktur LayeredFS siap pakai untuk Eden Emulator dan konsol Switch Atmosphere.
"""

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, List, Dict, Any

from core.icons import Icons
from core.logger import log
from core.mod_deployer import LayeredFSDeployer, DeployResult
from core.emu_detector import EmuDetector


class LayeredFSDeployDialog(tk.Toplevel):
    """
    Dialog modal untuk 1-Click Deploy mod ke struktur LayeredFS.
    """

    def __init__(self, parent, app):
        """
        Args:
            parent: Window induk (PolyglotStudioApp).
            app: Instance PolyglotStudioApp.
        """
        super().__init__(parent)
        self.parent = parent
        self.app = app
        self.db = app.db
        self.codec = app.codec

        title_id = app.settings.get("active_game_id", "0100A3D008C5C000")
        mod_name = app.settings.get("eden_mod_name", "[ID] Pokemon Scarlet Bahasa Indonesia")
        assets_dir = getattr(app, "mod_assets_dir", "")

        self.deployer = LayeredFSDeployer(
            db=self.db,
            codec=self.codec,
            title_id=title_id,
            mod_name=mod_name,
            mod_assets_dir=assets_dir
        )

        self.title("1-Click LayeredFS Mod Deployer")
        self.geometry("780x560")
        self.minsize(720, 500)
        self.transient(parent)

        self.last_result: Optional[DeployResult] = None
        self.modified_items = self.deployer.get_modified_items()

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
                    x = parent_x + (parent_w - 780) // 2
                    y = parent_y + (parent_h - 560) // 2
                    self.geometry(f"780x560+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build_ui(self):
        # Header banner
        header = ttk.Frame(self, padding=(14, 12))
        header.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header,
            text=f"{Icons.DEPLOY} 1-Click LayeredFS Mod Deployer",
            font=("Arial", 12, "bold"),
            foreground="#007ACC"
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ttk.Label(
            header,
            text="Hanya mengompilasi file yang telah dimodifikasi (diffs > 0 atau selesai), "
                 "menghasilkan struktur folder LayeredFS romfs/... yang bersih, kompatibel, dan siap pakai.",
            font=("Arial", 9),
            foreground="#555555",
            wraplength=740
        )
        desc_lbl.pack(anchor="w", pady=(2, 0))

        # Files Summary & List Frame
        list_frame = ttk.LabelFrame(self, text=f"Daftar File yang Dimodifikasi ({len(self.modified_items)} file)", padding=8)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)

        columns = ("filename", "type", "diffs", "romfs_path")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=7)
        self.tree.heading("filename", text="Nama File")
        self.tree.heading("type", text="Tipe")
        self.tree.heading("diffs", text="Perubahan")
        self.tree.heading("romfs_path", text="Target Path LayeredFS (romfs/...)")

        self.tree.column("filename", width=180, minwidth=140)
        self.tree.column("type", width=70, anchor="center")
        self.tree.column("diffs", width=85, anchor="center")
        self.tree.column("romfs_path", width=380)

        v_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._populate_tree()

        # Destination & Settings Options
        dest_frame = ttk.LabelFrame(self, text="Target Deployment & Pengaturan", padding=10)
        dest_frame.pack(fill=tk.X, padx=14, pady=6)

        self.target_mode_var = tk.StringVar(value="eden")

        # Radio 1: Eden Emulator
        eden_load = self.app.settings.get("eden_load_path") or EmuDetector.get_eden_load_path()
        r1 = ttk.Radiobutton(
            dest_frame,
            text=f"Eden Emulator Mod Folder ({eden_load or 'Belum diatur'})",
            variable=self.target_mode_var,
            value="eden"
        )
        r1.grid(row=0, column=0, columnspan=2, sticky="w", pady=2)

        # Radio 2: Custom Directory / Atmosphere SD Card
        r2 = ttk.Radiobutton(
            dest_frame,
            text="Folder Kustom / SD Card Switch (atmosphere/contents/...):",
            variable=self.target_mode_var,
            value="custom"
        )
        r2.grid(row=1, column=0, sticky="w", pady=2)

        self.custom_path_var = tk.StringVar()
        custom_entry = ttk.Entry(dest_frame, textvariable=self.custom_path_var, width=45)
        custom_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Button(
            dest_frame,
            text=f"{Icons.FOLDER_OPEN} Cari...",
            command=self._browse_custom_path
        ).grid(row=1, column=2, padx=5, pady=2)

        # Radio 3: Export ZIP
        r3 = ttk.Radiobutton(
            dest_frame,
            text="Export sebagai Paket ZIP (.zip) — Siap Ekstrak ke Root SD Card Atmosphere",
            variable=self.target_mode_var,
            value="zip"
        )
        r3.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        # Options checkboxes
        self.clean_old_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            dest_frame,
            text="Bersihkan file mod lama di tujuan sebelum compile (Clean Build)",
            variable=self.clean_old_var
        ).grid(row=3, column=0, sticky="w", pady=(6, 2))

        # Progress bar
        prog_frame = ttk.Frame(self, padding=(14, 2))
        prog_frame.pack(fill=tk.X)

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=2)

        self.status_lbl = ttk.Label(
            prog_frame,
            text=f"Siap mengompilasi {len(self.modified_items)} file modifikasi.",
            font=("Arial", 9),
            foreground="#333333"
        )
        self.status_lbl.pack(anchor="w")

        # Buttons footer
        btn_frame = ttk.Frame(self, padding=(14, 10))
        btn_frame.pack(fill=tk.X)

        self.deploy_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.DEPLOY} Deploy Mod Sekarang",
            command=self.run_deploy
        )
        self.deploy_btn.pack(side=tk.LEFT)

        self.open_folder_btn = ttk.Button(
            btn_frame,
            text=f"{Icons.FOLDER_OPEN} Buka Folder Mod",
            command=self.open_mod_directory,
            state=tk.DISABLED
        )
        self.open_folder_btn.pack(side=tk.LEFT, padx=6)

        self.close_btn = ttk.Button(
            btn_frame,
            text="Tutup",
            command=self.destroy
        )
        self.close_btn.pack(side=tk.RIGHT)

    def _populate_tree(self):
        for it in self.modified_items:
            diffs_str = f"{it['diffs']} baris" if it["asset_type"] == "text" else "Modified"
            self.tree.insert(
                "",
                "end",
                values=(
                    it["filename"],
                    it["asset_type"].upper(),
                    diffs_str,
                    f"romfs/{it['romfs_rel_path']}"
                )
            )

    def _browse_custom_path(self):
        folder = filedialog.askdirectory(title="Pilih Folder Output Mod")
        if folder:
            self.custom_path_var.set(folder)
            self.target_mode_var.set("custom")

    def run_deploy(self):
        if not self.modified_items:
            messagebox.showinfo(
                "Tidak Ada Perubahan",
                "Belum ada file yang diubah atau ditandai selesai. "
                "Silakan terjemahkan atau modifikasi setidaknya 1 file sebelum men-deploy."
            )
            return

        mode = self.target_mode_var.get()
        clean = self.clean_old_var.get()

        if mode == "eden":
            load_path = self.app.settings.get("eden_load_path") or EmuDetector.get_eden_load_path()
            if not load_path:
                messagebox.showerror(
                    "Path Eden Tidak Ditemukan",
                    "Path direktori 'eden_load_path' belum diisi!\n"
                    "Silakan atur path folder load emulator Eden Anda di menu AI Settings atau file .env."
                )
                return
            target_path = load_path
        elif mode == "custom":
            custom_dir = self.custom_path_var.get().strip()
            if not custom_dir:
                messagebox.showwarning("Pilih Folder", "Silakan pilih folder tujuan terlebih dahulu.")
                return
            target_path = custom_dir
        else: # zip
            zip_out = filedialog.asksaveasfilename(
                title="Simpan Paket Mod ZIP",
                defaultextension=".zip",
                initialfile=f"{self.deployer.mod_name}.zip",
                filetypes=[("ZIP Archive", "*.zip")]
            )
            if not zip_out:
                return
            target_path = zip_out

        self.deploy_btn.config(state=tk.DISABLED)
        self.open_folder_btn.config(state=tk.DISABLED)
        self.progress_bar.config(maximum=len(self.modified_items), value=0)
        self.status_lbl.config(text="Memulai kompilasi dan pembuatan struktur LayeredFS...", foreground="#007ACC")

        threading.Thread(target=self._worker, args=(mode, target_path, clean), daemon=True).start()

    def _worker(self, mode: str, target_path: str, clean: bool):
        def on_prog(cur, tot, fname):
            self.after(0, lambda c=cur, t=tot, f=fname: self._update_progress(c, t, f))

        try:
            if mode == "eden":
                res = self.deployer.deploy_to_emulator(target_path, clean_old=clean, progress_cb=on_prog)
            elif mode == "custom":
                # Deploy directly into custom folder with romfs/
                target_root = os.path.join(target_path, self.deployer.title_id, self.deployer.mod_name)
                res = self.deployer.deploy_to_directory(target_root, clean_old=clean, progress_cb=on_prog)
            else: # zip
                res = self.deployer.export_to_zip(target_path, atmosphere_layout=True, clean_old=clean, progress_cb=on_prog)

            self.last_result = res
            self.after(0, lambda: self._on_finish(res))

        except Exception as e:
            log.error(f"Deploy worker failed: {e}", exc_info=True)
            self.after(0, lambda err=str(e): self._on_error(err))

    def _update_progress(self, cur: int, tot: int, fname: str):
        self.progress_bar.config(value=cur)
        self.status_lbl.config(text=f"Mengompilasi [{cur}/{tot}]: {fname}...", foreground="#007ACC")

    def _on_finish(self, res: DeployResult):
        self.deploy_btn.config(state=tk.NORMAL)
        if res.success:
            self.progress_bar.config(value=res.total_files)
            self.open_folder_btn.config(state=tk.NORMAL)
            self.status_lbl.config(
                text=f"{Icons.ACCEPT} Selesai dalam {res.elapsed_ms:.0f}ms! "
                     f"{res.text_count} file .dat dikompilasi ({res.total_bytes / 1024:.1f} KB).",
                foreground="#2E7D32"
            )
            messagebox.showinfo(
                "LayeredFS Deploy Berhasil!",
                f"Mod berhasil dikompilasi dan di-deploy!\n\n"
                f"• File .dat teks: {res.text_count}\n"
                f"• File aset grafis: {res.asset_count}\n"
                f"• Total ukuran: {res.total_bytes / 1024:.1f} KB\n"
                f"• Waktu proses: {res.elapsed_ms:.1f} ms\n\n"
                f"Lokasi Mod:\n{res.mod_root}"
            )
        else:
            self.status_lbl.config(text=f"{Icons.DISCARD} Gagal: {res.error}", foreground="red")
            messagebox.showerror("Gagal Deploy", f"Terjadi kesalahan saat deploy:\n{res.error}")

    def _on_error(self, err: str):
        self.deploy_btn.config(state=tk.NORMAL)
        self.status_lbl.config(text=f"{Icons.DISCARD} Error: {err}", foreground="red")
        messagebox.showerror("Deploy Error", err)

    def open_mod_directory(self):
        if not self.last_result or not self.last_result.mod_root:
            return
        path = self.last_result.mod_root
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if os.path.exists(path):
            try:
                if os.name == "nt":
                    os.startfile(path)
                else:
                    subprocess.run(["xdg-open", path])
            except Exception as e:
                log.warning(f"Could not open mod directory: {e}")
