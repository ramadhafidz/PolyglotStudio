"""
Texture and Image Viewer for Game Modding & Localization.
Provides side-by-side visual comparison between original and modified game textures,
resolution & format inspection, external editor launch (Photoshop/GIMP), and replacement tools.
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable, Tuple

from core.logger import log
from core.icons import Icons

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class TextureViewer(ttk.Frame):
    """
    Side-by-side visual comparison and editor frame for game textures and UI graphics.
    """

    def __init__(self, parent, on_status_change: Optional[Callable[[bool], None]] = None):
        super().__init__(parent)
        self.on_status_change = on_status_change

        self.current_orig_path: Optional[str] = None
        self.current_trans_path: Optional[str] = None
        self.current_item: Optional[dict] = None

        self.orig_image_obj: Optional[object] = None
        self.trans_image_obj: Optional[object] = None
        self.orig_photo: Optional[object] = None
        self.trans_photo: Optional[object] = None

        self.zoom_level: float = 1.0

        self._build_ui()

    def _build_ui(self):
        # 1. Top Header Bar (Info & Action buttons)
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=8, pady=(4, 6))

        # Title & Metadata
        info_frame = ttk.Frame(header)
        info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.title_lbl = ttk.Label(
            info_frame, 
            text=f"{Icons.IMAGE} Texture Comparator", 
            font=("Segoe UI", 11, "bold")
        )
        self.title_lbl.pack(anchor=tk.W)

        self.meta_lbl = ttk.Label(
            info_frame, 
            text="Select an image file to view details.", 
            foreground="#555555",
            font=("Segoe UI", 9)
        )
        self.meta_lbl.pack(anchor=tk.W)

        # Right Action Buttons
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)

        self.ext_edit_btn = ttk.Button(
            btn_frame, 
            text=f"{Icons.EXT_EDIT} Open in Editor", 
            command=self.open_in_external_editor
        )
        self.ext_edit_btn.pack(side=tk.LEFT, padx=3)

        self.replace_btn = ttk.Button(
            btn_frame, 
            text=f"{Icons.IMPORT} Replace Image...", 
            command=self.replace_image
        )
        self.replace_btn.pack(side=tk.LEFT, padx=3)

        self.export_btn = ttk.Button(
            btn_frame, 
            text=f"{Icons.EXPORT} Export...", 
            command=self.export_image
        )
        self.export_btn.pack(side=tk.LEFT, padx=3)

        self.revert_btn = ttk.Button(
            btn_frame, 
            text=f"{Icons.UNDO} Reset Original", 
            command=self.revert_to_original
        )
        self.revert_btn.pack(side=tk.LEFT, padx=3)

        # 2. Main Comparison Container (PanedWindow: Left = Original, Right = Translated)
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Left Pane: Original Texture
        self.left_frame = ttk.LabelFrame(
            self.paned, 
            text=" Original Game Graphic (English) ", 
            padding=4
        )
        self.paned.add(self.left_frame, weight=1)

        self.orig_canvas = tk.Canvas(self.left_frame, bg="#2A2A2A", highlightthickness=0)
        self.orig_canvas.pack(fill=tk.BOTH, expand=True)

        # Right Pane: Modified / Translated Texture
        self.right_frame = ttk.LabelFrame(
            self.paned, 
            text=" Modded / Translated Graphic ", 
            padding=4
        )
        self.paned.add(self.right_frame, weight=1)

        self.trans_canvas = tk.Canvas(self.right_frame, bg="#2A2A2A", highlightthickness=0)
        self.trans_canvas.pack(fill=tk.BOTH, expand=True)

        # Resize listeners
        self.orig_canvas.bind("<Configure>", lambda e: self._render_previews())
        self.trans_canvas.bind("<Configure>", lambda e: self._render_previews())

        # 3. Bottom Zoom & Status Bar
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=4)

        ttk.Label(bottom, text="Zoom:", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bottom, text=Icons.ZOOM_OUT, width=3, command=self.zoom_out).pack(side=tk.LEFT, padx=1)
        self.zoom_lbl = ttk.Label(bottom, text="100%", font=("Segoe UI", 9, "bold"), width=6, anchor="center")
        self.zoom_lbl.pack(side=tk.LEFT)
        ttk.Button(bottom, text=Icons.ZOOM_IN, width=3, command=self.zoom_in).pack(side=tk.LEFT, padx=1)
        ttk.Button(bottom, text="Fit View", command=self.reset_zoom).pack(side=tk.LEFT, padx=4)

        self.status_hint_lbl = ttk.Label(
            bottom, 
            text="Tip: Nintendo Switch BNTX, PNG, DDS, and TGA textures supported.", 
            foreground="#666666",
            font=("Segoe UI", 9)
        )
        self.status_hint_lbl.pack(side=tk.RIGHT, padx=6)

    def load_texture(self, orig_path: str, trans_path: Optional[str] = None, item_dict: Optional[dict] = None):
        """
        Loads and renders original and modified textures.
        """
        self.current_orig_path = orig_path
        self.current_trans_path = trans_path
        self.current_item = item_dict

        filename = item_dict.get("filename") if (item_dict and item_dict.get("filename")) else os.path.basename(orig_path)
        self.title_lbl.config(text=f"{Icons.IMAGE} {filename}")

        self.orig_image_obj = None
        self.trans_image_obj = None

        # Load Original Image
        orig_dims = ""
        orig_size_str = ""
        if os.path.exists(orig_path):
            size_kb = os.path.getsize(orig_path) / 1024
            orig_size_str = f"{size_kb:.1f} KB"
            if HAS_PIL:
                try:
                    self.orig_image_obj = Image.open(orig_path)
                    w, h = self.orig_image_obj.size
                    orig_dims = f"{w} x {h} px ({self.orig_image_obj.mode})"
                except Exception as e:
                    log.warning(f"Failed to load image via PIL: {e}")

        # Load Translated Image (if exists)
        has_trans = bool(trans_path and os.path.exists(trans_path) and os.path.getsize(trans_path) > 0)
        if has_trans and trans_path:
            if HAS_PIL:
                try:
                    self.trans_image_obj = Image.open(trans_path)
                except Exception as e:
                    log.warning(f"Failed to load translated image via PIL: {e}")

        # Update metadata header
        trans_status_str = f"{Icons.STATUS_DONE} Modified" if has_trans else f"{Icons.STATUS_TODO} Unmodified"
        self.meta_lbl.config(
            text=f"Dimensions: {orig_dims or 'Unknown'} | Size: {orig_size_str} | Status: {trans_status_str}"
        )

        self._render_previews()

    def _render_previews(self):
        """
        Renders the original and translated images onto their respective canvases.
        """
        self._render_canvas(self.orig_canvas, self.orig_image_obj, is_trans=False)
        self._render_canvas(self.trans_canvas, self.trans_image_obj, is_trans=True)

    def _render_canvas(self, canvas: tk.Canvas, img_obj, is_trans: bool = False):
        canvas.delete("all")
        c_w = canvas.winfo_width()
        c_h = canvas.winfo_height()

        if c_w <= 1 or c_h <= 1:
            return

        # Draw dark checkerboard pattern background for transparent textures
        self._draw_checkerboard(canvas, c_w, c_h)

        if img_obj is None:
            # Display helpful placeholder
            msg = (
                f"{Icons.IMAGE}\n\nNo modded/translated image yet.\n"
                "Click 'Replace Image...' or 'Open in Editor' to modify."
                if is_trans else
                "Original image cannot be displayed."
            )
            canvas.create_text(
                c_w // 2, c_h // 2, 
                text=msg, 
                fill="#AAAAAA", 
                font=("Segoe UI", 10), 
                justify="center"
            )
            return

        if not HAS_PIL:
            canvas.create_text(
                c_w // 2, c_h // 2, 
                text="Pillow (PIL) is required for complete texture rendering.", 
                fill="#FFAA00", 
                font=("Segoe UI", 10)
            )
            return

        # Calculate fitted scale with zoom
        orig_w, orig_h = img_obj.size
        scale = min(c_w / orig_w, c_h / orig_h, 1.0) * self.zoom_level
        new_w = max(int(orig_w * scale), 1)
        new_h = max(int(orig_h * scale), 1)

        try:
            resized = img_obj.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            if is_trans:
                self.trans_photo = photo
            else:
                self.orig_photo = photo

            x = (c_w - new_w) // 2
            y = (c_h - new_h) // 2
            canvas.create_image(x, y, anchor="nw", image=photo)
        except Exception as e:
            log.warning(f"Error rendering image to canvas: {e}")

    def _draw_checkerboard(self, canvas: tk.Canvas, width: int, height: int, cell_size: int = 16):
        """Draws subtle checkered transparency background like Photoshop."""
        canvas.create_rectangle(0, 0, width, height, fill="#222222", outline="")
        color1 = "#2A2A2A"
        color2 = "#333333"
        for y in range(0, height, cell_size):
            for x in range(0, width, cell_size):
                fill_c = color1 if ((x // cell_size) + (y // cell_size)) % 2 == 0 else color2
                canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill=fill_c, outline="")

    # ----------------- User Actions -----------------
    def open_in_external_editor(self):
        """Opens image in default system editor (Photoshop, GIMP, Paint)."""
        target_path = self.current_trans_path
        if not target_path or not os.path.exists(target_path):
            # If not yet modified, prepare a copy in trans_path
            if self.current_orig_path and os.path.exists(self.current_orig_path) and self.current_trans_path:
                os.makedirs(os.path.dirname(self.current_trans_path), exist_ok=True)
                shutil.copy2(self.current_orig_path, self.current_trans_path)
                target_path = self.current_trans_path
            else:
                target_path = self.current_orig_path

        if target_path and os.path.exists(target_path):
            try:
                log.info(f"Opening image in external editor: {target_path}")
                os.startfile(target_path)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open image editor:\n{e}")

    def replace_image(self):
        """Allows user to pick a new image from disk to replace this texture."""
        if not self.current_orig_path or not self.current_trans_path:
            messagebox.showwarning("Warning", "No texture file selected.")
            return

        file_types = [
            ("Image Files", "*.png;*.jpg;*.jpeg;*.dds;*.tga;*.bmp;*.webp"),
            ("PNG Image", "*.png"),
            ("DirectDraw Surface", "*.dds"),
            ("All Files", "*.*")
        ]
        picked = filedialog.askopenfilename(
            title="Select Modded / Translated Image",
            filetypes=file_types
        )
        if picked and os.path.exists(picked):
            try:
                os.makedirs(os.path.dirname(self.current_trans_path), exist_ok=True)
                shutil.copy2(picked, self.current_trans_path)
                log.info(f"Replaced texture {self.current_trans_path} from {picked}")

                # Reload preview
                self.load_texture(self.current_orig_path, self.current_trans_path, self.current_item)

                # Trigger status update to completed
                if self.on_status_change:
                    self.on_status_change(True)

                messagebox.showinfo("Success", "Modded image successfully installed!")
            except Exception as e:
                log.error(f"Failed to replace image: {e}", exc_info=True)
                messagebox.showerror("Error", f"Failed to replace image:\n{e}")

    def export_image(self):
        """Exports either the modified or original image as a copy."""
        src_path = self.current_trans_path if (self.current_trans_path and os.path.exists(self.current_trans_path)) else self.current_orig_path
        if not src_path or not os.path.exists(src_path):
            messagebox.showwarning("Warning", "No image to export.")
            return

        def_name = os.path.basename(src_path)
        dest = filedialog.asksaveasfilename(
            title="Export Image Copy",
            initialfile=def_name,
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")]
        )
        if dest:
            try:
                shutil.copy2(src_path, dest)
                messagebox.showinfo("Success", f"Image exported successfully to:\n{dest}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export image:\n{e}")

    def revert_to_original(self):
        """Removes the modified texture so the original game texture is used."""
        if self.current_trans_path and os.path.exists(self.current_trans_path):
            confirm = messagebox.askyesno(
                "Confirm Reset",
                "Are you sure you want to delete this modified texture and revert to the original game texture?"
            )
            if confirm:
                try:
                    os.remove(self.current_trans_path)
                    log.info(f"Reverted texture to original: {self.current_orig_path}")
                    self.load_texture(self.current_orig_path, None, self.current_item)
                    if self.on_status_change:
                        self.on_status_change(False)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to reset image:\n{e}")
        else:
            messagebox.showinfo("Info", "This file has not been modified yet.")

    # ----------------- Zoom Controls -----------------
    def zoom_in(self):
        if self.zoom_level < 4.0:
            self.zoom_level = round(self.zoom_level + 0.25, 2)
            self.zoom_lbl.config(text=f"{int(self.zoom_level * 100)}%")
            self._render_previews()

    def zoom_out(self):
        if self.zoom_level > 0.25:
            self.zoom_level = round(self.zoom_level - 0.25, 2)
            self.zoom_lbl.config(text=f"{int(self.zoom_level * 100)}%")
            self._render_previews()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.zoom_lbl.config(text="100%")
        self._render_previews()
