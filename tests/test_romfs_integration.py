import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.app_window import ClassicDATStudioApp
from core.asset_classifier import AssetType

class TestAppRomFSIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"), \
             patch("gui.app_window.TrpfsClient"):
            cls.app = ClassicDATStudioApp()
            cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_romfs_attributes_exist(self):
        self.assertTrue(hasattr(self.app, "trpfs_client"))
        self.assertTrue(hasattr(self.app, "open_romfs"))
        self.assertTrue(hasattr(self.app, "load_romfs_directory"))

    def test_romfs_virtual_files_loading_and_routing(self):
        raw_files = [
            {
                "hash": "000a6f0dc7e4e2ea",
                "rel_path": "message/dat/English/script/field_event.dat",
                "filename": "field_event.dat"
            },
            {
                "hash": "000c120205691072",
                "rel_path": "message/dat/English/script/s1_other_area.dat",
                "filename": "s1_other_area.dat"
            }
        ]

        self.app.db.get_all_file_statuses.return_value = {}

        # Simulate RomFS files loaded
        with patch.object(self.app, "load_file") as mock_load:
            self.app._on_romfs_files_loaded("dummy/romfs", raw_files, 0.0)

        self.assertEqual(len(self.app.file_items), 2)
        item0 = self.app.file_items[0]
        self.assertTrue(item0["is_virtual"])
        self.assertEqual(item0["rel_path"], "script/field_event.dat")
        self.assertEqual(item0["romfs_path"], "message/dat/English/script/field_event.dat")

        # Test on-demand loading of virtual item
        self.app.db.get_file_full_data.return_value = None
        self.app.trpfs_client.extract_file_bytes.return_value = b"\x01\x00\x01\x00..."
        self.app.codec.decode_bytes.return_value = ["Line 1", "Line 2"]

        with patch.object(self.app, "update_table_display"):
            self.app.load_file(0)

        self.app.trpfs_client.extract_file_bytes.assert_called_with("message/dat/English/script/field_event.dat")
        self.app.codec.decode_bytes.assert_called_with(b"\x01\x00\x01\x00...")
        self.assertEqual(self.app.current_orig_lines, ["Line 1", "Line 2"])

if __name__ == "__main__":
    unittest.main()
