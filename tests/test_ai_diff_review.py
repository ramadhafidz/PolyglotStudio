import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui.app_window import ClassicDATStudioApp
from core.icons import Icons

class TestAIDiffReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Prevent opening actual GUI window
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"):
            cls.app = ClassicDATStudioApp()
            cls.app.withdraw()  # Hide window during test

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def setUp(self):
        self.app.file_items = [{
            "filename": "test.dat",
            "rel_path": "test.dat",
            "dat_path": "dummy/test.dat",
            "status": "untranslated",
            "diffs": 0,
            "total": 3,
            "status_override": None,
            "is_manual": False
        }]
        self.app.current_file_index = 0
        self.app.current_orig_lines = ["Hello", "World", "Pikachu"]
        self.app.current_trans_lines = ["Hello", "World", "Pikachu"]
        self.app.pending_ai_diffs = {}
        self.app.undo_stack = []
        self.app.redo_stack = []

    def test_initial_state_empty_diffs(self):
        self.assertEqual(len(self.app.pending_ai_diffs), 0)
        self.assertFalse(self.app.review_bar.winfo_ismapped())

    def test_staging_ai_diffs(self):
        # Simulate AI translation returned with 2 changes
        ai_result = ["Halo", "Dunia", "Pikachu"]
        diffs_found = {}
        for i, new_line in enumerate(ai_result):
            cur = self.app.current_trans_lines[i]
            if new_line != cur:
                diffs_found[i] = new_line

        self.assertEqual(len(diffs_found), 2)
        self.assertIn(0, diffs_found)
        self.assertIn(1, diffs_found)
        self.assertNotIn(2, diffs_found)

        self.app.pending_ai_diffs = diffs_found
        self.app.update_table_display()
        self.app.update_review_bar()

        # Check table items
        children = self.app.table.get_children()
        self.assertEqual(len(children), 3)

        # Line 0 should have checkmark and diff tag
        row0_vals = self.app.table.item(children[0], "values")
        self.assertEqual(str(row0_vals[0]), "0")
        self.assertEqual(row0_vals[1], Icons.ACCEPT)
        self.assertEqual(row0_vals[3], "Halo")
        self.assertIn("diff_pending_even", self.app.table.item(children[0], "tags"))

        # Line 2 (unchanged) should NOT have checkmark
        row2_vals = self.app.table.item(children[2], "values")
        self.assertEqual(row2_vals[1], "")
        self.assertIn("even", self.app.table.item(children[2], "tags"))

    @patch.object(ClassicDATStudioApp, "auto_save")
    def test_accept_single_ai_diff(self, mock_auto_save):
        self.app.pending_ai_diffs = {0: "Halo", 1: "Dunia"}
        self.app.update_table_display()
        self.app.update_review_bar()

        # Accept line 0 only
        self.app.accept_single_ai_diff(0)

        # Line 0 should be updated in current_trans_lines
        self.assertEqual(self.app.current_trans_lines[0], "Halo")
        # Line 1 should still be original until accepted
        self.assertEqual(self.app.current_trans_lines[1], "World")
        # Line 0 removed from pending
        self.assertNotIn(0, self.app.pending_ai_diffs)
        self.assertIn(1, self.app.pending_ai_diffs)

        # Auto-save MUST have been called!
        mock_auto_save.assert_called_once()

    @patch.object(ClassicDATStudioApp, "auto_save")
    def test_accept_all_ai_diffs(self, mock_auto_save):
        self.app.pending_ai_diffs = {0: "Halo", 1: "Dunia"}
        self.app.update_table_display()
        self.app.update_review_bar()

        self.app.accept_all_ai_diffs()

        self.assertEqual(self.app.current_trans_lines[0], "Halo")
        self.assertEqual(self.app.current_trans_lines[1], "Dunia")
        self.assertEqual(len(self.app.pending_ai_diffs), 0)

        mock_auto_save.assert_called_once()

    @patch.object(ClassicDATStudioApp, "auto_save")
    def test_discard_single_ai_diff(self, mock_auto_save):
        self.app.pending_ai_diffs = {0: "Halo", 1: "Dunia"}
        self.app.update_table_display()
        self.app.update_review_bar()

        self.app.discard_single_ai_diff(0)

        # Line 0 should NOT be changed
        self.assertEqual(self.app.current_trans_lines[0], "Hello")
        self.assertNotIn(0, self.app.pending_ai_diffs)
        self.assertIn(1, self.app.pending_ai_diffs)

        # Auto save should NOT be called on discard
        mock_auto_save.assert_not_called()

    @patch.object(ClassicDATStudioApp, "auto_save")
    def test_discard_all_ai_diffs(self, mock_auto_save):
        self.app.pending_ai_diffs = {0: "Halo", 1: "Dunia"}
        self.app.update_table_display()
        self.app.update_review_bar()

        self.app.discard_all_ai_diffs()

        self.assertEqual(self.app.current_trans_lines[0], "Hello")
        self.assertEqual(self.app.current_trans_lines[1], "World")
        self.assertEqual(len(self.app.pending_ai_diffs), 0)

        mock_auto_save.assert_not_called()

if __name__ == "__main__":
    unittest.main()
