import os
import tempfile
import unittest
import tkinter as tk
from unittest.mock import patch

from core.db_manager import ProjectDB
from gui.dialogs.glossary_dialog import GlossaryDialog


class TestGlossaryDialog(unittest.TestCase):
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
        self.db_path = os.path.join(self.temp_dir.name, "test_glossary_gui.db")
        self.db = ProjectDB(self.db_path)
        # Pre-seed some data
        self.db.add_glossary_term("Potion", "Ramuan", "pokemon", "Memulihkan 20 HP")
        self.db.add_glossary_term("Poké Ball", "Poké Ball", "pokemon", "Menangkap Pokémon")
        self.dialog = GlossaryDialog(self.root, self.db)
        self.dialog.withdraw()  # keep off-screen during test

    def tearDown(self):
        try:
            self.dialog.destroy()
        except Exception:
            pass
        self.temp_dir.cleanup()

    def test_init_ui(self):
        self.assertEqual(self.dialog.title(), "Kamus Istilah (Glossary)")
        columns = self.dialog.tree["columns"]
        self.assertEqual(list(columns), ["no", "term_en", "term_id", "category", "notes"])

        # Check treeview rows
        children = self.dialog.tree.get_children()
        self.assertEqual(len(children), 2)
        self.assertIn("Total: 2 istilah terdaftar", self.dialog.status_lbl.cget("text"))

    def test_on_select(self):
        children = self.dialog.tree.get_children()
        # Select first item
        self.dialog.tree.selection_set(children[0])
        self.dialog.on_select()

        self.assertIsNotNone(self.dialog.selected_id)
        # First alphabetical is Poké Ball or Potion
        en_val = self.dialog.en_entry.get()
        self.assertIn(en_val, ["Poké Ball", "Potion"])
        self.assertTrue(len(self.dialog.id_entry.get()) > 0)

    def test_add_term(self):
        self.dialog.en_entry.delete(0, tk.END)
        self.dialog.en_entry.insert(0, "Revive")
        self.dialog.id_entry.delete(0, tk.END)
        self.dialog.id_entry.insert(0, "Pemulih")
        self.dialog.cat_combo.set("pokemon")
        self.dialog.notes_entry.delete(0, tk.END)
        self.dialog.notes_entry.insert(0, "Menghidupkan kembali")

        self.dialog.add_term()

        # Check in DB and tree
        terms = self.db.get_glossary()
        self.assertEqual(len(terms), 3)
        en_terms = [t["term_en"] for t in terms]
        self.assertIn("Revive", en_terms)

        children = self.dialog.tree.get_children()
        self.assertEqual(len(children), 3)

    def test_update_term(self):
        children = self.dialog.tree.get_children()
        self.dialog.tree.selection_set(children[0])
        self.dialog.on_select()

        # Update Indonesian term
        self.dialog.id_entry.delete(0, tk.END)
        self.dialog.id_entry.insert(0, "Terjemahan Baru")
        self.dialog.update_term()

        terms = self.db.get_glossary()
        id_terms = [t["term_id"] for t in terms]
        self.assertIn("Terjemahan Baru", id_terms)

    @patch("tkinter.messagebox.askyesno", return_value=True)
    def test_delete_term(self, mock_ask):
        children = self.dialog.tree.get_children()
        initial_count = len(children)
        self.dialog.tree.selection_set(children[0])
        self.dialog.on_select()

        self.dialog.delete_term()

        terms = self.db.get_glossary()
        self.assertEqual(len(terms), initial_count - 1)
        self.assertEqual(len(self.dialog.tree.get_children()), initial_count - 1)

    def test_filter_and_search(self):
        # Search by keyword
        self.dialog.search_var.set("Potion")
        filtered_children = self.dialog.tree.get_children()
        self.assertEqual(len(filtered_children), 1)

        # Clear search
        self.dialog.search_var.set("")
        self.assertEqual(len(self.dialog.tree.get_children()), 2)


if __name__ == "__main__":
    unittest.main()
