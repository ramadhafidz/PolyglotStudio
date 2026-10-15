import os
import tempfile
import unittest
import tkinter as tk
from unittest.mock import MagicMock, patch

from gui.dialogs.romfs_folder_dialog import RomFSFolderDialog


class TestRomFSFolderDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dummy_romfs = self.temp_dir.name
        # Create arc/data.trpfd mock
        os.makedirs(os.path.join(self.dummy_romfs, "arc"), exist_ok=True)
        with open(os.path.join(self.dummy_romfs, "arc", "data.trpfd"), "wb") as f:
            f.write(b"TRPFD_TEST")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_default_preset(self):
        dialog = RomFSFolderDialog(
            self.root,
            romfs_path=self.dummy_romfs,
            current_subfolder="message/dat/English"
        )
        dialog.withdraw()

        self.assertEqual(dialog.title(), "Select RomFS Working Directory")
        self.assertEqual(dialog.selected_preset_var.get(), "message_en")
        self.assertTrue(dialog.moddable_only_var.get())
        self.assertIsNone(dialog.result)
        dialog.destroy()

    def test_select_ui_tex_preset_and_confirm(self):
        dialog = RomFSFolderDialog(
            self.root,
            romfs_path=self.dummy_romfs,
            current_subfolder="message/dat/English"
        )
        dialog.withdraw()

        dialog.selected_preset_var.set("ui_tex")
        dialog._confirm()

        self.assertIsNotNone(dialog.result)
        self.assertEqual(dialog.result["romfs_path"], os.path.abspath(self.dummy_romfs))
        self.assertEqual(dialog.result["subfolder"], "appli/tex")
        self.assertEqual(dialog.result["asset_filter"], "texture")
        self.assertTrue(dialog.result["moddable_only"])

    def test_select_custom_subfolder_and_confirm(self):
        dialog = RomFSFolderDialog(
            self.root,
            romfs_path=self.dummy_romfs,
            current_subfolder=""
        )
        dialog.withdraw()

        dialog.selected_preset_var.set("custom")
        dialog.custom_subfolder_var.set("pokemon/field_graphic")
        dialog.moddable_only_var.set(False)
        dialog._confirm()

        self.assertIsNotNone(dialog.result)
        self.assertEqual(dialog.result["subfolder"], "pokemon/field_graphic")
        self.assertEqual(dialog.result["asset_filter"], "all")
        self.assertFalse(dialog.result["moddable_only"])

    def test_select_entire_romfs_preset(self):
        dialog = RomFSFolderDialog(
            self.root,
            romfs_path=self.dummy_romfs,
            current_subfolder=""
        )
        dialog.withdraw()

        dialog.selected_preset_var.set("entire_romfs")
        dialog._confirm()

        self.assertIsNotNone(dialog.result)
        self.assertEqual(dialog.result["subfolder"], "")
        self.assertEqual(dialog.result["asset_filter"], "all")

    @patch("tkinter.messagebox.showerror")
    def test_invalid_path_confirm_error(self, mock_error):
        dialog = RomFSFolderDialog(
            self.root,
            romfs_path="C:/non_existent_folder_path_xyz",
            current_subfolder="message/dat/English"
        )
        dialog.withdraw()

        dialog._confirm()
        self.assertIsNone(dialog.result)
        mock_error.assert_called_once()
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
