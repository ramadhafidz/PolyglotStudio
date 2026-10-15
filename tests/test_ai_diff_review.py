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

    def test_ai_translation_isolated_when_user_switches_file(self):
        """
        Verify Solution 2: When translating File 0, if the user switches to File 1 mid-flight:
        - File 1's UI and lines are NOT contaminated.
        - File 0's translation is auto-saved directly to SQLite.
        - File 0's status/diffs in file_items are updated.
        - active_ai_tasks is cleanly resolved.
        """
        import threading

        self.app.file_items = [
            {
                "filename": "file0.dat",
                "rel_path": "common/file0.dat",
                "dat_path": "dummy/file0.dat",
                "status": "untranslated",
                "diffs": 0,
                "total": 3,
                "is_manual": False
            },
            {
                "filename": "file1.dat",
                "rel_path": "common/file1.dat",
                "dat_path": "dummy/file1.dat",
                "status": "untranslated",
                "diffs": 0,
                "total": 1,
                "is_manual": False
            }
        ]

        # User is viewing File 0
        self.app.current_file_index = 0
        self.app.current_orig_lines = ["Hello", "World", "Pikachu"]
        self.app.current_trans_lines = ["Hello", "World", "Pikachu"]
        self.app.pending_ai_diffs = {}

        # Mock AI translation side effect: while translating, user navigates to File 1!
        def mock_translate(*args, **kwargs):
            # User navigated to File 1 (fewer lines than File 0)
            self.app.current_file_index = 1
            self.app.current_orig_lines = ["Good morning"]
            self.app.current_trans_lines = ["Good morning"]
            self.app.pending_ai_diffs = {}
            return ["Halo", "Dunia", "Pikachu"]

        self.app.ai.translate_lines = MagicMock(side_effect=mock_translate)
        self.app.db.save_file_translation = MagicMock(return_value=("completed", 2, 3, False))
        self.app.db.get_exact_tm_match = MagicMock(return_value=None)
        self.app.db.get_glossary_prompt_block = MagicMock(return_value="")
        self.app.db.get_tm_prompt_block = MagicMock(return_value="")

        # Synchronous execution of thread for deterministic testing
        real_thread_init = threading.Thread.__init__
        def sync_thread_init(thread_self, *args, **kwargs):
            real_thread_init(thread_self, *args, **kwargs)
            # Store target
            orig_run = thread_self.run
            def run_and_drain():
                orig_run()
                self.app.update()
            thread_self.run = run_and_drain

        with patch("threading.Thread.start", autospec=True) as mock_thread_start:
            # Let thread start run target synchronously
            mock_thread_start.side_effect = lambda t: t.run()
            self.app.translate_with_ai()

        # Process any pending tkinter callbacks
        self.app.update()

        # 1. File 1 MUST NOT be contaminated with File 0's translations
        self.assertEqual(self.app.current_file_index, 1)
        self.assertEqual(self.app.current_trans_lines, ["Good morning"])
        self.assertEqual(len(self.app.pending_ai_diffs), 0)

        # 2. File 0's diffs MUST be safely staged in file_pending_ai_diffs for user review (NOT auto-saved without consent)
        self.assertIn("file0.dat", self.app.file_pending_ai_diffs)
        self.assertEqual(self.app.file_pending_ai_diffs["file0.dat"], {0: "Halo", 1: "Dunia"})

        # 3. active_ai_tasks must be clean
        self.assertNotIn("file0.dat", self.app.active_ai_tasks)

        # 4. When user clicks back to File 0, pending diffs & green review bar MUST be restored!
        self.app.db.get_file_full_data = MagicMock(return_value=(
            ["Hello", "World", "Pikachu"],
            ["Hello", "World", "Pikachu"]
        ))
        self.app.load_file(0)

        self.assertEqual(self.app.current_file_index, 0)
        self.assertEqual(len(self.app.pending_ai_diffs), 2)
        self.assertIn(0, self.app.pending_ai_diffs)
        self.assertIn(1, self.app.pending_ai_diffs)
        self.assertEqual(self.app.review_bar.winfo_manager(), "pack")

        # 5. User reviews and accepts all diffs
        with patch.object(ClassicDATStudioApp, "auto_save"):
            self.app.accept_all_ai_diffs()

        self.assertEqual(self.app.current_trans_lines[0], "Halo")
        self.assertEqual(self.app.current_trans_lines[1], "Dunia")
        self.assertEqual(len(self.app.pending_ai_diffs), 0)
        self.assertNotIn("file0.dat", self.app.file_pending_ai_diffs)


if __name__ == "__main__":
    unittest.main()

