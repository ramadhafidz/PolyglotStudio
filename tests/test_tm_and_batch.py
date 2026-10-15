import unittest
import tempfile
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.db_manager import ProjectDB
from core.tag_guard import TagGuard
from core.icons import Icons


class TestTranslationMemoryAndQA(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_tm.db")
        self.db = ProjectDB(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tm_add_and_exact_match(self):
        """Verify TM stores and matches long sentences while protecting short/ambiguous words."""
        # 1. Add long sentence
        s1 = "Welcome to the Pokémon Center!"
        t1 = "Selamat datang di Pokémon Center!"
        self.assertTrue(self.db.add_tm_entry(s1, t1, context_file="field.dat"))

        # 2. Add short ambiguous words
        self.assertTrue(self.db.add_tm_entry("Run", "Kabur", context_file="battle.dat"))
        self.assertTrue(self.db.add_tm_entry("Fire", "Api", context_file="menu.dat"))

        # 3. Add safe short phrase
        self.assertTrue(self.db.add_tm_entry("Yes\nNo", "Ya\nTidak", context_file="system.dat"))

        # Exact match tests:
        # Long sentence should match 100%
        match_s1 = self.db.get_exact_tm_match("Welcome to the Pokémon Center!", min_words=3)
        self.assertEqual(match_s1, "Selamat datang di Pokémon Center!")

        # Short ambiguous words must be blocked by min_words=3 safety rule
        match_run = self.db.get_exact_tm_match("Run", min_words=3)
        self.assertIsNone(match_run, "Single word 'Run' must not be auto-replaced blindly by TM")

        match_fire = self.db.get_exact_tm_match("Fire", min_words=3)
        self.assertIsNone(match_fire, "Single word 'Fire' must not be auto-replaced blindly by TM")

        # Safe short phrase should be permitted
        match_yes_no = self.db.get_exact_tm_match("Yes\nNo", min_words=3)
        self.assertEqual(match_yes_no, "Ya\nTidak")

    def test_tm_batch_entries_and_stats(self):
        """Verify bulk TM insertion and usage stats counting."""
        pairs = [
            ("Do you want to save your game?", "Apakah kamu ingin menyimpan permainanmu?"),
            ("You received a Poké Ball!", "Kamu mendapatkan sebuah Poké Ball!"),
            ("Please choose a starter Pokémon.", "Silakan pilih Pokémon pemula."),
            ("", ""), # empty should be filtered
            ("[WAIT 10]", "[WAIT 10]"), # tags only should be filtered
        ]
        inserted = self.db.add_batch_tm_entries(pairs, context_file="script.dat")
        self.assertEqual(inserted, 3)

        stats = self.db.get_tm_stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertGreaterEqual(stats["total_uses"], 3)

    def test_tm_prompt_block_generation(self):
        """Verify TM generates context references for AI prompt injection."""
        self.db.add_tm_entry("Are you ready for battle?", "Apakah kamu siap untuk bertarung?")
        lines = ["Are you ready for battle?", "Let's begin!"]

        block = self.db.get_tm_prompt_block(lines)
        self.assertIn("REFERENSI MEMORI TERJEMAHAN", block)
        self.assertIn("Are you ready for battle?", block)
        self.assertIn("Apakah kamu siap untuk bertarung?", block)

    def test_tag_guard_diagnostics_detection_and_autofix(self):
        """Verify QA diagnostics detects tag errors, trailing control mismatches, and can auto-fix."""
        orig = "[VAR TRNAME] waited for [WAIT 30] seconds.\\r"
        
        # Broken translation: dropped tag and trailing \r
        broken = "[VAR TRNAME] menunggu selama beberapa detik."
        diag = TagGuard.validate_line_diagnostics(orig, broken)
        
        self.assertFalse(diag["is_valid"])
        self.assertTrue(any("WAIT" in err for err in diag["errors"]))
        self.assertTrue(any("\\r" in err for err in diag["errors"]))
        self.assertTrue(diag["can_auto_fix"])
        self.assertIn("[WAIT 30]", diag["fixed_text"])
        self.assertTrue(diag["fixed_text"].endswith("\\r"))

    def test_tag_guard_length_warning(self):
        """Verify warning on overly long lines that could overflow the screen."""
        orig = "Short original text."
        very_long = "Ini adalah kalimat terjemahan yang dibuat sangat amat panjang sekali sampai melebihi batas delapan puluh lima karakter di layar Nintendo Switch."
        diag = TagGuard.validate_line_diagnostics(orig, very_long, max_line_len=85)
        self.assertTrue(diag["is_valid"]) # Valid tags, but warning issued
        self.assertTrue(len(diag["warnings"]) > 0)
        self.assertIn("overflow", diag["warnings"][0].lower())


if __name__ == "__main__":
    unittest.main()
