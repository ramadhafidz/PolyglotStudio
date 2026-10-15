import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import tkinter as tk
from PIL import Image

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.viewers.texture_viewer import TextureViewer
from gui.app_window import ClassicDATStudioApp
from core.asset_classifier import AssetType


class TestTextureViewer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

        # Create temporary dummy test images
        cls.temp_dir = tempfile.mkdtemp()
        cls.orig_img_path = os.path.join(cls.temp_dir, "test_logo.png")
        cls.trans_img_path = os.path.join(cls.temp_dir, "test_logo_id.png")

        # Save 64x64 RGBA dummy images
        img_orig = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
        img_orig.save(cls.orig_img_path)

        img_trans = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
        img_trans.save(cls.trans_img_path)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass
        # Clean up temp files
        try:
            import shutil
            shutil.rmtree(cls.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_texture_viewer_init_and_load(self):
        status_mock = MagicMock()
        viewer = TextureViewer(self.root, on_status_change=status_mock)

        viewer.load_texture(self.orig_img_path, self.trans_img_path)

        self.assertIsNotNone(viewer.orig_image_obj)
        self.assertIsNotNone(viewer.trans_image_obj)
        self.assertEqual(viewer.orig_image_obj.size, (64, 64))
        self.assertIn("64 x 64", viewer.meta_lbl.cget("text"))

    def test_zoom_controls(self):
        viewer = TextureViewer(self.root)
        self.assertEqual(viewer.zoom_level, 1.0)

        viewer.zoom_in()
        self.assertEqual(viewer.zoom_level, 1.25)
        self.assertEqual(viewer.zoom_lbl.cget("text"), "125%")

        viewer.zoom_out()
        self.assertEqual(viewer.zoom_level, 1.0)
        self.assertEqual(viewer.zoom_lbl.cget("text"), "100%")

        viewer.reset_zoom()
        self.assertEqual(viewer.zoom_level, 1.0)


class TestAppMultiWorkspaceRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"):
            cls.app = ClassicDATStudioApp()
            cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_multi_workspace_widgets_exist(self):
        self.assertTrue(hasattr(self.app, "text_editor_container"))
        self.assertTrue(hasattr(self.app, "texture_viewer"))
        self.assertTrue(hasattr(self.app, "asset_filter_var"))

    def test_texture_file_switches_workspace(self):
        # Setup dummy file items: 0 = text, 1 = texture
        self.app.file_items = [
            {
                "filename": "msg.dat",
                "rel_path": "msg.dat",
                "dat_path": "dummy/msg.dat",
                "file_path": "dummy/msg.dat",
                "asset_type": AssetType.TEXT,
                "status": "untranslated",
                "diffs": 0,
                "total": 1,
                "is_manual": False
            },
            {
                "filename": "banner.png",
                "rel_path": "banner.png",
                "dat_path": "dummy/banner.png",
                "file_path": "dummy/banner.png",
                "asset_type": AssetType.TEXTURE,
                "status": "untranslated",
                "diffs": 0,
                "total": 0,
                "is_manual": False
            }
        ]

        # Load file 1 (Texture)
        with patch.object(self.app.texture_viewer, "load_texture"):
            self.app.load_file(1)

        # Texture viewer should be packed, text editor container should be unpacked
        self.assertEqual(self.app.texture_viewer.winfo_manager(), "pack")
        self.assertEqual(self.app.text_editor_container.winfo_manager(), "")
        self.assertTrue("Image:" in self.app.cur_file_lbl.cget("text") or "Gambar:" in self.app.cur_file_lbl.cget("text"))

        # Switch back to file 0 (Text)
        self.app.db.get_file_full_data.return_value = (["Hello"], ["Halo"])
        with patch.object(self.app, "update_table_display"):
            self.app.load_file(0)
        self.assertEqual(self.app.text_editor_container.winfo_manager(), "pack")
        self.assertEqual(self.app.texture_viewer.winfo_manager(), "")

    def test_virtual_bntx_triggers_extract_texture_png(self):
        self.app.file_items = [
            {
                "filename": "logo_brand_8076.bntx",
                "rel_path": "logo_brand/logo_brand_8076.bntx",
                "romfs_path": "appli/tex/logo_brand/logo_brand_8076/logo_brand_8076.bntx",
                "asset_type": AssetType.TEXTURE,
                "status": "untranslated",
                "is_virtual": True,
                "is_manual": False
            }
        ]

        exists_map = {
            "extract_called": False
        }

        def _mock_exists(path):
            if str(path).endswith(".png"):
                # First check returns False to trigger extraction, then True
                return exists_map["extract_called"]
            return False

        def _mock_extract(src, dst):
            exists_map["extract_called"] = True
            return True

        with patch.object(self.app.trpfs_client, "extract_texture_png", side_effect=_mock_extract) as mock_extract, \
             patch.object(self.app.texture_viewer, "load_texture") as mock_load, \
             patch("os.makedirs"), \
             patch("os.path.exists", side_effect=_mock_exists):
            self.app.load_file(0)
            mock_extract.assert_called_once()
            args = mock_extract.call_args[0]
            self.assertEqual(args[0], "appli/tex/logo_brand/logo_brand_8076/logo_brand_8076.bntx")
            self.assertTrue(args[1].endswith(".png"))
            mock_load.assert_called_once()

    def test_bntx_translated_asset_path(self):
        bntx_rel = "appli/tex/logo_brand/logo_brand_8076.bntx"
        trans_path = self.app.get_translated_asset_path(bntx_rel)
        # Should look for .png replacement by default
        self.assertTrue(trans_path.endswith(".png"))


if __name__ == "__main__":
    unittest.main()

