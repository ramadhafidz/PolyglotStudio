import os
import tempfile
import unittest
from core.env_manager import EnvManager

class TestEnvManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_file = os.path.join(self.temp_dir.name, ".env")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_env_basic(self):
        content = """
        # Comment line
        AI_PROVIDER=openai
        AI_ENDPOINT="https://custom.router.com/v1"
        AI_KEY='sk-test-secret-123'
        EMPTY_LINE=
        SPACED_KEY = value_with_space # inline comment
        export EXPORTED_VAR=true
        """
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write(content)

        loaded = EnvManager.load_env(self.env_file)
        self.assertEqual(loaded.get("AI_PROVIDER"), "openai")
        self.assertEqual(loaded.get("AI_ENDPOINT"), "https://custom.router.com/v1")
        self.assertEqual(loaded.get("AI_KEY"), "sk-test-secret-123")
        self.assertEqual(loaded.get("SPACED_KEY"), "value_with_space")
        self.assertEqual(loaded.get("EXPORTED_VAR"), "true")

        # Verify os.environ lookup
        self.assertEqual(EnvManager.get("AI_PROVIDER"), "openai")
        self.assertEqual(EnvManager.get("NON_EXISTENT", "default_val"), "default_val")

    def test_load_non_existent_env_returns_empty(self):
        res = EnvManager.load_env(os.path.join(self.temp_dir.name, "does_not_exist.env"))
        self.assertEqual(res, {})

if __name__ == "__main__":
    unittest.main()
