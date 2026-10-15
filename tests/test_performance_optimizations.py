import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.universal_ai import UniversalAIClient
from gui.app_window import ClassicDATStudioApp
from core.asset_classifier import AssetType


class TestPerformanceOptimizations(unittest.TestCase):
    def setUp(self):
        self.ai = UniversalAIClient(
            provider="openai",
            endpoint="https://api.openai.com/v1",
            api_key="test-key",
            model="gpt-4o-mini"
        )

    def test_parallel_batch_translation_ordering(self):
        """Verify parallel batches preserve exact line order and report progress correctly."""
        lines = [f"Dialog line {i}" for i in range(60)]
        batch_size = 20
        # 3 batches: [0..19], [20..39], [40..59]

        def fake_translate_batch(batch, target_lang, glossary_block=""):
            # Simulate artificial latency per batch
            time.sleep(0.02)
            return [f"ID_{line}" for line in batch], [{"term_en": "Test", "term_id": "Tes"}]

        terms_collected = []
        def on_terms(t):
            terms_collected.extend(t)

        progress_calls = []
        def on_prog(cur, tot):
            progress_calls.append((cur, tot))

        with patch.object(self.ai, "_translate_batch", side_effect=fake_translate_batch):
            res = self.ai.translate_lines(
                lines,
                target_lang="Indonesian",
                batch_size=batch_size,
                progress_callback=on_prog,
                on_new_terms=on_terms,
                max_workers=3
            )

        self.assertEqual(len(res), 60)
        # Check strict ordering
        for i in range(60):
            self.assertEqual(res[i], f"ID_Dialog line {i}")

        # Check progress calls reached 60
        self.assertTrue(any(cur == 60 for cur, tot in progress_calls))
        self.assertEqual(len(terms_collected), 3)

    def test_retry_backoff_on_rate_limit(self):
        """Verify _translate_batch retries with backoff when HTTP 429 occurs."""
        call_count = 0
        def fail_then_succeed(sys_inst, user_content):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("OpenAI Endpoint Error (429): Rate limit exceeded")
            return '{"translations": ["Halo dunia"]}'

        with patch.object(self.ai, "_call_openai", side_effect=fail_then_succeed), \
             patch("time.sleep") as mock_sleep:
            res, terms = self.ai._translate_batch(["Hello world"], "Indonesian", retries=3)
            self.assertEqual(res, ["Halo dunia"])
            self.assertEqual(call_count, 2)
            self.assertTrue(mock_sleep.called)

    def test_virtual_lazy_tree_loading(self):
        """Verify treeview lazy loads non-open folders and populates children on open."""
        with patch("gui.app_window.PokemonDatCodec"), \
             patch("gui.app_window.ProjectDB"), \
             patch("gui.app_window.UniversalAIClient"), \
             patch("gui.app_window.TrpfsClient"):
            app = ClassicDATStudioApp()
            app.withdraw()

        try:
            # Set up mock files across two folders
            app.file_items = [
                {"filename": "common_1.dat", "rel_path": "common/common_1.dat", "status": "untranslated", "diffs": 0, "total": 10},
                {"filename": "common_2.dat", "rel_path": "common/common_2.dat", "status": "untranslated", "diffs": 0, "total": 10},
                {"filename": "script_1.dat", "rel_path": "script/script_1.dat", "status": "untranslated", "diffs": 0, "total": 10},
                {"filename": "script_2.dat", "rel_path": "script/script_2.dat", "status": "untranslated", "diffs": 0, "total": 10},
            ]

            app.populate_file_tree()

            # First folder (common) should be open by default, second (script) should have __dummy__ child
            children = app.file_tree.get_children()
            self.assertEqual(len(children), 2)  # Two folder nodes

            # Find script folder node
            script_node = None
            for c in children:
                if "script" in app.file_tree.item(c, "text"):
                    script_node = c
                    break

            self.assertIsNotNone(script_node)
            script_children = app.file_tree.get_children(script_node)
            self.assertEqual(len(script_children), 1)
            self.assertEqual(app.file_tree.item(script_children[0], "text"), "__dummy__")

            # Simulate expanding script folder
            app.file_tree.item(script_node, open=True)
            app.on_tree_item_open()

            # Now script node should contain the real items
            updated_script_children = app.file_tree.get_children(script_node)
            self.assertEqual(len(updated_script_children), 2)
            item_texts = [app.file_tree.item(ch, "text") for ch in updated_script_children]
            self.assertTrue(any("script_1.dat" in t for t in item_texts))
            self.assertTrue(any("script_2.dat" in t for t in item_texts))
        finally:
            try:
                app.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
