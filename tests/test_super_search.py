import os
import tempfile
import unittest
import tkinter as tk
from unittest.mock import MagicMock, patch

from core.db_manager import ProjectDB
from formats.pokemon_dat import PokemonDatCodec
from gui.dialogs.super_search_dialog import SuperSearchDialog


class TestSuperSearchDialog(unittest.TestCase):
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
        self.db_path = os.path.join(self.temp_dir.name, "test_search.db")
        self.db = ProjectDB(self.db_path)
        self.codec = PokemonDatCodec()

        # Seed files into DB
        f1_orig = ["Welcome to Paldea!", "Pick your starter Pokémon.", "Let the journey begin!"]
        f1_trans = ["Selamat datang di Paldea!", "Pilih Pokémon pemulamu.", "Biarkan petualangan dimulai!"]
        self.db.save_file_translation("intro.dat", "script/intro.dat", f1_orig, f1_trans)

        f2_orig = ["Miraidon is looking at you.", "Koraidon is sleeping."]
        f2_trans = ["Miraidon sedang melihatmu.", "Koraidon sedang tidur."]
        self.db.save_file_translation("legend.dat", "event/legend.dat", f2_orig, f2_trans)

        # Mock app
        self.app = MagicMock()
        self.app.db = self.db
        self.app.codec = self.codec
        self.app.workspace_dir = self.temp_dir.name
        self.app.current_file_index = -1
        self.app.file_items = [
            {"filename": "intro.dat", "rel_path": "script/intro.dat", "is_virtual": False},
            {"filename": "legend.dat", "rel_path": "event/legend.dat", "is_virtual": False}
        ]

        self.dialog = SuperSearchDialog(self.root, self.app)
        self.dialog.withdraw()

    def tearDown(self):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_search_finds_in_original_and_translation(self):
        """Verify searching finds matches across both original English and translated Indonesian."""
        # 1. Search for English term
        self.dialog.find_var.set("Miraidon")
        self.dialog._search_worker("Miraidon", self.app.file_items, target="both", match_case=False, whole_word=False)
        self.assertEqual(len(self.dialog.results), 1)
        self.assertEqual(self.dialog.results[0]["filename"], "legend.dat")
        self.assertEqual(self.dialog.results[0]["line"], 0)

        # 2. Search for Indonesian term
        self.dialog.results.clear()
        self.dialog.find_var.set("pemulamu")
        self.dialog._search_worker("pemulamu", self.app.file_items, target="both", match_case=False, whole_word=False)
        self.assertEqual(len(self.dialog.results), 1)
        self.assertEqual(self.dialog.results[0]["filename"], "intro.dat")
        self.assertEqual(self.dialog.results[0]["line"], 1)

    def test_search_options_case_and_whole_word(self):
        """Verify case sensitivity and whole word matching."""
        # Case sensitive: lowercase 'miraidon' should not match 'Miraidon'
        self.dialog.results.clear()
        self.dialog._search_worker("miraidon", self.app.file_items, target="both", match_case=True, whole_word=False)
        self.assertEqual(len(self.dialog.results), 0)

        # Whole word: 'start' should not match 'starter'
        self.dialog.results.clear()
        self.dialog._search_worker("start", self.app.file_items, target="both", match_case=False, whole_word=True)
        self.assertEqual(len(self.dialog.results), 0)

        # Whole word exact match
        self.dialog.results.clear()
        self.dialog._search_worker("starter", self.app.file_items, target="both", match_case=False, whole_word=True)
        self.assertEqual(len(self.dialog.results), 1)

    def test_jump_to_dialogue_line(self):
        """Verify jumping from search result to the exact line in editor."""
        self.dialog.find_var.set("Miraidon")
        self.dialog._search_worker("Miraidon", self.app.file_items, target="both", match_case=False, whole_word=False)
        self.dialog.update()
        self.assertEqual(len(self.dialog.results), 1)

        # Mock app table and jump
        self.app.jump_to_dialogue_line.return_value = True

        # Simulate selection and jump
        first_row = self.dialog.tree.get_children()[0]
        self.dialog.tree.selection_set(first_row)
        self.dialog.on_jump_to_result()

        self.app.jump_to_dialogue_line.assert_called_with("legend.dat", 0)

    def test_replace_selected_row(self):
        """Verify replacing a term in the selected row updates translation in SQLite."""
        self.dialog.find_var.set("tidur")
        self.dialog.replace_var.set("terlelap")
        self.dialog._search_worker("tidur", self.app.file_items, target="both", match_case=False, whole_word=False)
        self.dialog.update()
        self.assertEqual(len(self.dialog.results), 1)

        first_row = self.dialog.tree.get_children()[0]
        self.dialog.tree.selection_set(first_row)
        self.dialog.replace_selected()

        # Verify translation in DB updated
        db_lines = self.db.get_file_lines("legend.dat")
        self.assertIn("Koraidon sedang terlelap.", db_lines[1])


if __name__ == "__main__":
    unittest.main()
