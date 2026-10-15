import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.asset_classifier import AssetClassifier, AssetType
from core.icons import Icons


class TestAssetClassifier(unittest.TestCase):
    def test_text_classification(self):
        self.assertEqual(AssetClassifier.get_asset_type("ajito_aku_010.dat"), AssetType.TEXT)
        self.assertEqual(AssetClassifier.get_asset_type("dialogue.txt"), AssetType.TEXT)
        self.assertEqual(AssetClassifier.get_asset_type("strings.json"), AssetType.TEXT)
        self.assertTrue(AssetClassifier.is_text("ajito_aku_010.dat"))
        self.assertFalse(AssetClassifier.is_texture("ajito_aku_010.dat"))

    def test_texture_classification(self):
        self.assertEqual(AssetClassifier.get_asset_type("title_logo.png"), AssetType.TEXTURE)
        self.assertEqual(AssetClassifier.get_asset_type("map_banner.dds"), AssetType.TEXTURE)
        self.assertEqual(AssetClassifier.get_asset_type("ui_button.bntx"), AssetType.TEXTURE)
        self.assertEqual(AssetClassifier.get_asset_type("sprite.tga"), AssetType.TEXTURE)
        self.assertTrue(AssetClassifier.is_texture("title_logo.png"))
        self.assertFalse(AssetClassifier.is_text("title_logo.png"))

    def test_font_and_audio_classification(self):
        self.assertEqual(AssetClassifier.get_asset_type("PokemonFont.ttf"), AssetType.FONT)
        self.assertEqual(AssetClassifier.get_asset_type("system.bffnt"), AssetType.FONT)
        self.assertEqual(AssetClassifier.get_asset_type("voice_pikachu.wav"), AssetType.AUDIO)
        self.assertEqual(AssetClassifier.get_asset_type("bgm_battle.bwav"), AssetType.AUDIO)
        self.assertEqual(AssetClassifier.get_asset_type("wwise.pck"), AssetType.AUDIO)

    def test_icon_mapping(self):
        self.assertEqual(AssetClassifier.get_icon("test.dat"), Icons.EDIT)
        self.assertEqual(AssetClassifier.get_icon("logo.png"), Icons.IMAGE)
        self.assertEqual(AssetClassifier.get_icon("font.ttf"), Icons.FONT)
        self.assertEqual(AssetClassifier.get_icon("voice.wav"), Icons.AUDIO)
        self.assertEqual(AssetClassifier.get_icon("model.bin"), Icons.EXPORT)

    def test_category_filtering(self):
        # All files filter
        self.assertTrue(AssetClassifier.matches_category_filter("test.dat", "Semua File"))
        self.assertTrue(AssetClassifier.matches_category_filter("logo.png", "Semua File"))

        # Text filter
        self.assertTrue(AssetClassifier.matches_category_filter("test.dat", "Teks Dialog (.dat, .txt)"))
        self.assertFalse(AssetClassifier.matches_category_filter("logo.png", "Teks Dialog (.dat, .txt)"))

        # Texture filter
        self.assertTrue(AssetClassifier.matches_category_filter("logo.png", "Gambar & Textures (.png, .dds, .bntx)"))
        self.assertFalse(AssetClassifier.matches_category_filter("test.dat", "Gambar & Textures (.png, .dds, .bntx)"))

        # Audio filter
        self.assertTrue(AssetClassifier.matches_category_filter("voice.wav", "Audio / Voice (.wav, .bwav)"))
        self.assertFalse(AssetClassifier.matches_category_filter("logo.png", "Audio / Voice (.wav, .bwav)"))


if __name__ == "__main__":
    unittest.main()
