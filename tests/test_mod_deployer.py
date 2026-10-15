import unittest
import tempfile
import os
import sys
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.db_manager import ProjectDB
from core.mod_deployer import LayeredFSDeployer
from formats.pokemon_dat import PokemonDatCodec


class TestLayeredFSDeployer(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_deploy.db")
        self.db = ProjectDB(self.db_path)
        self.codec = PokemonDatCodec()
        self.assets_dir = os.path.join(self.temp_dir.name, "workspace_assets")
        os.makedirs(self.assets_dir, exist_ok=True)

        self.title_id = "0100A3D008C5C000"
        self.mod_name = "[ID] Pokemon Scarlet Bahasa Indonesia"

        self.deployer = LayeredFSDeployer(
            db=self.db,
            codec=self.codec,
            title_id=self.title_id,
            mod_name=self.mod_name,
            mod_assets_dir=self.assets_dir
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_only_modified_files_are_selected(self):
        """Verify deployer strictly selects only files that were modified."""
        # 1. Unmodified file (diffs = 0, status = untranslated)
        self.db.save_file_translation(
            filename="untouched.dat",
            rel_path="common/untouched.dat",
            orig_lines=["Hello", "World"],
            trans_lines=["Hello", "World"]
        )

        # 2. Modified file (diffs > 0, status = partial / completed)
        self.db.save_file_translation(
            filename="bbschool.dat",
            rel_path="script/bbschool.dat",
            orig_lines=["Welcome to school!", "Study hard!"],
            trans_lines=["Selamat datang di sekolah!", "Belajarlah yang rajin!"]
        )

        items = self.deployer.get_modified_items()
        filenames = [it["filename"] for it in items]

        self.assertIn("bbschool.dat", filenames)
        self.assertNotIn("untouched.dat", filenames, "Untouched files must never be deployed")
        self.assertEqual(len(items), 1)

        # Check romfs target path
        self.assertEqual(
            items[0]["romfs_rel_path"],
            "message/dat/English/script/bbschool.dat"
        )

    def test_deploy_to_directory_creates_valid_layeredfs(self):
        """Verify deploy compiles .dat binary and creates proper LayeredFS structure."""
        self.db.save_file_translation(
            filename="field_event.dat",
            rel_path="script/field_event.dat",
            orig_lines=["Look out!", "A wild Pokémon appeared!"],
            trans_lines=["Awas!", "Seekor Pokémon liar muncul!"]
        )

        # Add a mock texture asset
        texture_path = os.path.join(self.assets_dir, "ui", "title_logo.png")
        os.makedirs(os.path.dirname(texture_path), exist_ok=True)
        with open(texture_path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nFakePngData")

        target_stage = os.path.join(self.temp_dir.name, "deployed_mod")
        result = self.deployer.deploy_to_directory(target_stage, clean_old=True)

        self.assertTrue(result.success)
        self.assertEqual(result.text_count, 1)
        self.assertEqual(result.asset_count, 1)
        self.assertEqual(result.total_files, 2)

        # Verify compiled .dat file exists in correct LayeredFS path
        dat_dest = os.path.join(target_stage, "romfs", "message", "dat", "English", "script", "field_event.dat")
        self.assertTrue(os.path.exists(dat_dest))

        # Verify binary decode can read it back
        with open(dat_dest, "rb") as f_in:
            decoded_lines = self.codec.decode_bytes(f_in.read())
        self.assertEqual(decoded_lines[0], "Awas!")
        self.assertEqual(decoded_lines[1], "Seekor Pokémon liar muncul!")

        # Verify texture asset exists in romfs/ui/title_logo.png
        tex_dest = os.path.join(target_stage, "romfs", "ui", "title_logo.png")
        self.assertTrue(os.path.exists(tex_dest))

        # Verify metadata files exist
        toolbox_json = os.path.join(target_stage, "toolbox.json")
        self.assertTrue(os.path.exists(toolbox_json))
        mod_info_json = os.path.join(target_stage, "mod_info.json")
        self.assertTrue(os.path.exists(mod_info_json))

    def test_export_to_zip_atmosphere_layout(self):
        """Verify export to flashable Atmosphere zip package."""
        self.db.save_file_translation(
            filename="msg.dat",
            rel_path="common/msg.dat",
            orig_lines=["Yes", "No"],
            trans_lines=["Ya", "Tidak"]
        )

        zip_out = os.path.join(self.temp_dir.name, "PokemonScarlet_Mod.zip")
        res = self.deployer.export_to_zip(zip_out, atmosphere_layout=True)

        self.assertTrue(res.success)
        self.assertTrue(os.path.exists(zip_out))
        self.assertGreater(os.path.getsize(zip_out), 0)

        # Inspect zip contents
        with zipfile.ZipFile(zip_out, "r") as zf:
            namelist = zf.namelist()
            expected_dat = f"atmosphere/contents/{self.title_id}/romfs/message/dat/English/common/msg.dat"
            self.assertIn(expected_dat, [n.replace("\\", "/") for n in namelist])

    def test_completed_file_with_zero_diffs_is_not_deployed(self):
        """
        Verify that a text file marked 'completed' for checklist/organization purposes,
        but having 0 diffs (e.g. pure engine syntax or untouched lines), is NOT deployed.
        Only files with real modifications (diffs > 0) or non-text assets are deployed.
        """
        # 1. Text file with 0 diffs marked completed (e.g. pure syntax checked by user)
        self.db.save_file_translation(
            filename="syntax_script.dat",
            rel_path="script/syntax_script.dat",
            orig_lines=["[~ 14] 00 00", "[~ 15] 01 02"],
            trans_lines=["[~ 14] 00 00", "[~ 15] 01 02"]
        )
        self.db.set_file_status_override("syntax_script.dat", "script/syntax_script.dat", "completed")

        # 2. Text file with genuine diffs (diffs = 1)
        self.db.save_file_translation(
            filename="dialogue.dat",
            rel_path="script/dialogue.dat",
            orig_lines=["Hello!", "Thank you!"],
            trans_lines=["Halo!", "Thank you!"]
        )

        # 3. Non-text texture asset marked completed
        self.db.upsert_asset_file(
            filename="custom_logo.png",
            rel_path="ui/custom_logo.png",
            status="completed",
            asset_type="texture"
        )
        # Create physical asset file
        full_png = os.path.join(self.assets_dir, "ui", "custom_logo.png")
        os.makedirs(os.path.dirname(full_png), exist_ok=True)
        with open(full_png, "wb") as f:
            f.write(b"PNG_DATA")

        # Query items
        items = self.deployer.get_modified_items()
        item_filenames = [it["filename"] for it in items]

        # syntax_script.dat MUST NOT be in items (diffs == 0)
        self.assertNotIn("syntax_script.dat", item_filenames, "Syntax-only file with 0 diffs must be excluded")
        # dialogue.dat MUST be in items (diffs == 1)
        self.assertIn("dialogue.dat", item_filenames)
        # custom_logo.png MUST be in items (texture marked completed)
        self.assertIn("custom_logo.png", item_filenames)

        # Execute deployment and confirm file system output
        target_stage = os.path.join(self.temp_dir.name, "deployed_test_zero_diff")
        result = self.deployer.deploy_to_directory(target_stage, clean_old=True)

        self.assertTrue(result.success)
        syntax_dest = os.path.join(target_stage, "romfs", "message", "dat", "English", "script", "syntax_script.dat")
        dialogue_dest = os.path.join(target_stage, "romfs", "message", "dat", "English", "script", "dialogue.dat")
        logo_dest = os.path.join(target_stage, "romfs", "ui", "custom_logo.png")

        self.assertFalse(os.path.exists(syntax_dest), "syntax_script.dat must NOT be written to LayeredFS romfs")
        self.assertTrue(os.path.exists(dialogue_dest), "dialogue.dat MUST be written to LayeredFS romfs")
        self.assertTrue(os.path.exists(logo_dest), "custom_logo.png MUST be written to LayeredFS romfs")


if __name__ == "__main__":
    unittest.main()

