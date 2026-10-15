import unittest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.trpfs_client import TrpfsClient
from formats.pokemon_dat import PokemonDatCodec

class TestTrpfsClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.romfs_path = r"E:\Modding\eden\dump\0100A3D008C5C000\romfs"
        cls.has_romfs = os.path.isdir(os.path.join(cls.romfs_path, "arc"))
        cls.client = TrpfsClient()

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_worker_executable_exists(self):
        self.assertTrue(os.path.isfile(self.client.worker_exe_path))

    def test_load_romfs_and_extract(self):
        if not self.has_romfs:
            self.skipTest(f"RomFS not found at {self.romfs_path}")

        # 1. Load RomFS
        ok, msg = self.client.load_romfs(self.romfs_path)
        self.assertTrue(ok, f"Failed to load RomFS: {msg}")
        self.assertGreater(self.client.total_hashes, 10000)
        self.assertGreater(self.client.named_count, 10000)

        # 2. List English dat files
        files = self.client.list_files("message/dat/English")
        self.assertGreater(len(files), 500)
        
        target = next((f for f in files if "field_event.dat" in f["rel_path"]), None)
        self.assertIsNotNone(target)

        # 3. Extract bytes directly
        data = self.client.extract_file_bytes(target["rel_path"])
        self.assertIsNotNone(data)
        self.assertGreater(len(data), 100)

        # 4. Verify decoded with PokemonDatCodec
        codec = PokemonDatCodec()
        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        try:
            lines = codec.read_file(tmp_path)
            self.assertIsInstance(lines, list)
            self.assertGreater(len(lines), 0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        # 5. Test extract directly to disk
        with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as tmp_out:
            out_path = tmp_out.name

        try:
            disk_ok = self.client.extract_file_to_disk(target["rel_path"], out_path)
            self.assertTrue(disk_ok)
            self.assertEqual(os.path.getsize(out_path), len(data))
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

if __name__ == "__main__":
    unittest.main()
