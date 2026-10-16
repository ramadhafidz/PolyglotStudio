import os
import tempfile
import unittest
from core.db_manager import ProjectDB

class TestGlossaryDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_project.db")
        self.db = ProjectDB(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_glossary(self):
        self.assertEqual(self.db.get_glossary(), [])
        self.assertEqual(self.db.get_glossary_prompt_block(), "")

    def test_add_and_get_glossary(self):
        row_id1 = self.db.add_glossary_term("Potion", "Ramuan", "item", "Restores HP")
        self.assertIsInstance(row_id1, int)

        row_id2 = self.db.add_glossary_term("Antidote", "Penawar Racun", "item")
        self.assertIsInstance(row_id2, int)

        terms = self.db.get_glossary()
        self.assertEqual(len(terms), 2)
        # Check ordering term_en ASC (Antidote before Potion)
        self.assertEqual(terms[0]["term_en"], "Antidote")
        self.assertEqual(terms[0]["term_id"], "Penawar Racun")
        self.assertEqual(terms[0]["category"], "item")
        self.assertEqual(terms[0]["notes"], "")
        self.assertEqual(terms[1]["term_en"], "Potion")
        self.assertEqual(terms[1]["term_id"], "Ramuan")
        self.assertEqual(terms[1]["category"], "item")
        self.assertEqual(terms[1]["notes"], "Restores HP")

    def test_add_duplicate_replaces(self):
        self.db.add_glossary_term("Potion", "Obat", "item")
        self.db.add_glossary_term("Potion", "Ramuan", "item", "Restores 20 HP")
        terms = self.db.get_glossary()
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0]["term_en"], "Potion")
        self.assertEqual(terms[0]["term_id"], "Ramuan")
        self.assertEqual(terms[0]["notes"], "Restores 20 HP")

    def test_update_glossary_term(self):
        row_id = self.db.add_glossary_term("Revive", "Hidupkan", "item")
        self.db.update_glossary_term(row_id, "Revive", "Pemulih", "item", "Revives fainted Pokemon")
        terms = self.db.get_glossary()
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0]["term_id"], "Pemulih")
        self.assertEqual(terms[0]["notes"], "Revives fainted Pokemon")

    def test_delete_glossary_term(self):
        row_id = self.db.add_glossary_term("Rare Candy", "Permen Langka", "item")
        self.assertEqual(len(self.db.get_glossary()), 1)
        self.db.delete_glossary_term(row_id)
        self.assertEqual(len(self.db.get_glossary()), 0)

    def test_glossary_prompt_block(self):
        self.db.add_glossary_term("Vending Machine", "Vending Machine", "game_term")
        self.db.add_glossary_term("TM Machine", "TM Machine", "game_term")

        block = self.db.get_glossary_prompt_block()
        expected = (
            "KAMUS ISTILAH WAJIB (Glossary):\n"
            "Gunakan terjemahan berikut secara KONSISTEN di seluruh file. JANGAN gunakan alternatif lain.\n"
            '- "TM Machine" → "TM Machine"\n'
            '- "Vending Machine" → "Vending Machine"'
        )
        self.assertEqual(block, expected)

    def test_seed_default_glossary(self):
        self.db.seed_default_glossary()
        terms = self.db.get_glossary()
        self.assertGreaterEqual(len(terms), 115)

        term_map = {t["term_en"]: (t["term_id"], t["category"]) for t in terms}
        self.assertIn("Poké Ball", term_map)
        self.assertEqual(term_map["Poké Ball"], ("Poké Ball", "pokemon"))
        self.assertIn("Area Zero", term_map)
        self.assertEqual(term_map["Area Zero"], ("Area Zero", "location"))
        self.assertIn("Terastal", term_map)
        self.assertEqual(term_map["Terastal"], ("Terastal", "game_term"))
        # Verify battle states and weathers
        self.assertIn("Rain", term_map)
        self.assertEqual(term_map["Rain"][0], "Hujan")
        self.assertIn("Trick Room", term_map)
        self.assertEqual(term_map["Trick Room"][0], "Trick Room")
        self.assertIn("Poisoned", term_map)
        self.assertEqual(term_map["Poisoned"][0], "Terkena Racun")

        # Calling again should not duplicate
        self.db.seed_default_glossary()
        terms_after = self.db.get_glossary()
        self.assertEqual(len(terms_after), len(terms))

    def test_ai_parse_json_response_with_new_terms(self):
        from core.universal_ai import UniversalAIClient
        ai = UniversalAIClient()

        json_payload = """
        {
          "translations": ["Halo dunia!", "Gunakan Vending Machine."],
          "new_terms": [
            {"en": "Vending Machine", "id": "Vending Machine", "category": "game_term"},
            {"en": "Sandwich", "id": "Sandwich", "category": "item"}
          ]
        }
        """
        orig_lines = ["Hello world!", "Use the Vending Machine."]
        lines, terms = ai._parse_json_response(json_payload, orig_lines)

        self.assertEqual(lines, ["Halo dunia!", "Gunakan Vending Machine."])
        self.assertEqual(len(terms), 2)
        self.assertEqual(terms[0]["term_en"], "Vending Machine")
        self.assertEqual(terms[0]["term_id"], "Vending Machine")
        self.assertEqual(terms[1]["term_en"], "Sandwich")

    def test_ai_translate_lines_learning_new_terms(self):
        from core.universal_ai import UniversalAIClient
        ai = UniversalAIClient(api_key="test-key")

        discovered = []
        def on_terms(terms):
            discovered.extend(terms)

        mock_return = (
            ["Gunakan TM Machine di sini."],
            [{"term_en": "TM Machine", "term_id": "TM Machine", "category": "game_term"}]
        )
        from unittest.mock import patch
        with patch.object(ai, "_translate_batch", return_value=mock_return):
            res = ai.translate_lines(["Use TM Machine here."], on_new_terms=on_terms)
            self.assertEqual(res, ["Gunakan TM Machine di sini."])
            self.assertEqual(len(discovered), 1)
            self.assertEqual(discovered[0]["term_en"], "TM Machine")

if __name__ == "__main__":
    unittest.main()
