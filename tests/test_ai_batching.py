import unittest
from unittest.mock import MagicMock, patch
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.universal_ai import UniversalAIClient
from gui.app_window import ClassicDATStudioApp
from core.asset_classifier import AssetType

class TestAIBatchingAndFiltering(unittest.TestCase):
    def setUp(self):
        self.ai = UniversalAIClient(
            provider="openai",
            endpoint="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-4o-mini"
        )

    def test_single_batch_translation(self):
        lines = [f"Line {i}" for i in range(5)]
        expected = [f"Baris {i}" for i in range(5)]
        
        progress_calls = []
        def cb(cur, tot):
            progress_calls.append((cur, tot))

        with patch.object(self.ai, "_translate_batch", return_value=expected) as mock_batch:
            res = self.ai.translate_lines(lines, target_lang="Indonesian", batch_size=20, progress_callback=cb)
            self.assertEqual(res, expected)
            self.assertEqual(mock_batch.call_count, 1)
            self.assertEqual(progress_calls, [(5, 5)])

    def test_multi_batch_translation(self):
        lines = [f"Line {i}" for i in range(55)]
        batch_1 = [f"Baris {i}" for i in range(0, 20)]
        batch_2 = [f"Baris {i}" for i in range(20, 40)]
        batch_3 = [f"Baris {i}" for i in range(40, 55)]

        progress_calls = []
        def cb(cur, tot):
            progress_calls.append((cur, tot))

        with patch.object(self.ai, "_translate_batch", side_effect=[batch_1, batch_2, batch_3]) as mock_batch:
            res = self.ai.translate_lines(lines, target_lang="Indonesian", batch_size=20, progress_callback=cb)
            self.assertEqual(len(res), 55)
            self.assertEqual(mock_batch.call_count, 3)
            self.assertEqual(progress_calls, [(20, 55), (40, 55), (55, 55)])
            self.assertEqual(res[0], "Baris 0")
            self.assertEqual(res[54], "Baris 54")

    def test_romfs_loader_filters_out_tbl(self):
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"):
            app = ClassicDATStudioApp()
            app.withdraw()

        try:
            raw_files = [
                {"filename": "bbschool.dat", "rel_path": "message/dat/English/script/bbschool.dat", "hash": 1},
                {"filename": "ymap_mission_add.tbl", "rel_path": "message/dat/English/common/ymap_mission_add.tbl", "hash": 2},
                {"filename": "field_event.dat", "rel_path": "message/dat/English/script/field_event.dat", "hash": 3},
            ]
            with patch.object(app, "load_file"):
                app._on_romfs_files_loaded("dummy_romfs", raw_files, 0.0)

            filenames = [item["filename"] for item in app.file_items]
            self.assertIn("bbschool.dat", filenames)
            self.assertIn("field_event.dat", filenames)
            self.assertNotIn("ymap_mission_add.tbl", filenames)
            self.assertEqual(len(app.file_items), 2)
        finally:
            try:
                app.destroy()
            except Exception:
                pass

    def test_load_file_unsupported_asset_graceful(self):
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"):
            app = ClassicDATStudioApp()
            app.withdraw()

        try:
            app.file_items = [{
                "filename": "mission.tbl",
                "rel_path": "common/mission.tbl",
                "asset_type": AssetType.BINARY,
                "status": "untranslated",
                "diffs": 0,
                "total": 0,
                "status_override": None,
                "is_manual": False
            }]
            # Should not raise exception
            app.load_file(0)
            self.assertTrue("File format" in app.info_status_lbl.cget("text") or "Format berkas" in app.info_status_lbl.cget("text"))
        finally:
            try:
                app.destroy()
            except Exception:
                pass

if __name__ == "__main__":
    unittest.main()
