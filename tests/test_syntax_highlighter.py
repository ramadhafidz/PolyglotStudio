import unittest
from unittest.mock import patch
import os
import sys
import tkinter as tk

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.syntax_highlighter import DialogueSyntaxHighlighter
from gui.app_window import ClassicDATStudioApp


class TestDialogueSyntaxHighlighter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.text = tk.Text(cls.root)
        DialogueSyntaxHighlighter.configure_tags(cls.text)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_variable_highlighting(self):
        sample = "Halo, [VAR PKNAME(0000)] dan [VAR 0101(0000)]!"
        DialogueSyntaxHighlighter.set_text_with_highlight(self.text, sample, editable=True)

        ranges = self.text.tag_ranges("token_var")
        self.assertEqual(len(ranges), 4)  # 2 matched tokens -> 2 * (start, end)
        self.assertEqual(self.text.get(ranges[0], ranges[1]), "[VAR PKNAME(0000)]")
        self.assertEqual(self.text.get(ranges[2], ranges[3]), "[VAR 0101(0000)]")

    def test_escape_highlighting(self):
        sample = "Baris 1\\nBaris 2\\rBaris 3\\c"
        DialogueSyntaxHighlighter.set_text_with_highlight(self.text, sample, editable=True)

        ranges = self.text.tag_ranges("token_escape")
        self.assertEqual(len(ranges), 6)  # 3 tokens -> 3 * (start, end)
        self.assertEqual(self.text.get(ranges[0], ranges[1]), "\\n")
        self.assertEqual(self.text.get(ranges[2], ranges[3]), "\\r")
        self.assertEqual(self.text.get(ranges[4], ranges[5]), "\\c")

    def test_wait_highlighting(self):
        sample = "Tunggu [WAIT 30] lalu [~ 1] lanjut."
        DialogueSyntaxHighlighter.set_text_with_highlight(self.text, sample, editable=True)

        ranges = self.text.tag_ranges("token_wait")
        self.assertEqual(len(ranges), 4)
        self.assertEqual(self.text.get(ranges[0], ranges[1]), "[WAIT 30]")
        self.assertEqual(self.text.get(ranges[2], ranges[3]), "[~ 1]")

    def test_normal_text_not_highlighted(self):
        sample = "Ini teks biasa tanpa simbol apapun."
        DialogueSyntaxHighlighter.set_text_with_highlight(self.text, sample, editable=True)

        for tag in ["token_var", "token_escape", "token_wait", "token_generic", "token_error"]:
            ranges = self.text.tag_ranges(tag)
            self.assertEqual(len(ranges), 0, f"Tag {tag} should not be present on plain text")

    def test_unclosed_tag_error(self):
        sample = "Error tag [VAR PKNAME"
        DialogueSyntaxHighlighter.set_text_with_highlight(self.text, sample, editable=True)

        ranges = self.text.tag_ranges("token_error")
        self.assertTrue(len(ranges) >= 2)
        self.assertEqual(self.text.get(ranges[0], ranges[1]), "[VAR PKNAME")


class TestLiveInspectorIntegration(unittest.TestCase):
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

    def test_inspector_widgets_exist(self):
        self.assertTrue(hasattr(self.app, "inspector_frame"))
        self.assertTrue(hasattr(self.app, "inspector_orig_box"))
        self.assertTrue(hasattr(self.app, "inspector_trans_box"))
        self.assertTrue(hasattr(self.app, "toggle_inspector_btn"))

    def test_update_inspector_content_and_tags(self):
        orig = "Hello, [VAR PKNAME(0000)]!\\nWelcome to Paldea.\\c"
        trans = "Halo, [VAR PKNAME(0000)]!\\nSelamat datang di Paldea.\\c"

        self.app.update_inspector(0, orig, trans)

        # Verify orig text
        orig_content = self.app.inspector_orig_box.get("1.0", "end-1c")
        self.assertEqual(orig_content, orig)

        # Verify trans text
        trans_content = self.app.inspector_trans_box.get("1.0", "end-1c")
        self.assertEqual(trans_content, trans)

        # Verify syntax tags on inspector trans box
        var_ranges = self.app.inspector_trans_box.tag_ranges("token_var")
        self.assertTrue(len(var_ranges) >= 2)
        self.assertEqual(self.app.inspector_trans_box.get(var_ranges[0], var_ranges[1]), "[VAR PKNAME(0000)]")

        esc_ranges = self.app.inspector_trans_box.tag_ranges("token_escape")
        self.assertTrue(len(esc_ranges) >= 4)  # \n and \c

        # Verify tag validation badge
        self.assertIn("Tags Match", self.app.inspector_tag_lbl.cget("text"))

    def test_toggle_inspector(self):
        initial_state = self.app.inspector_visible
        self.assertTrue(initial_state)

        # Toggle off
        self.app.toggle_inspector()
        self.assertFalse(self.app.inspector_visible)
        self.assertEqual(self.app.toggle_inspector_btn.cget("text"), "Show Inspector")

        # Toggle back on
        self.app.toggle_inspector()
        self.assertTrue(self.app.inspector_visible)
        self.assertEqual(self.app.toggle_inspector_btn.cget("text"), "Hide Inspector")


if __name__ == "__main__":
    unittest.main()
