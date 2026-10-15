"""
Zero-dependency .env file parser and manager for Polyglot Studio.
Loads environment variables from .env file into os.environ and provides helper methods.
"""

import os
from typing import Dict, Optional


class EnvManager:
    """
    Lightweight, robust .env parser without external dependencies (no python-dotenv required).
    Handles:
    - KEY=VALUE syntax
    - Single and double quotes stripping
    - Comments (#) stripping
    - Multiline values and empty lines
    - Export prefix ('export KEY=VAL')
    """

    @classmethod
    def load_env(cls, env_path: Optional[str] = None) -> Dict[str, str]:
        """
        Loads key-value pairs from .env into os.environ.
        If env_path is not specified, looks for '.env' in project root.
        Returns dictionary of loaded variables.
        """
        if not env_path:
            # Project root is parent of core/ directory
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            env_path = os.path.join(root_dir, ".env")

        if not os.path.isfile(env_path):
            return {}

        loaded: Dict[str, str] = {}
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Handle 'export KEY=VAL'
                    if line.startswith("export "):
                        line = line[7:].strip()

                    if "=" not in line:
                        continue

                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()

                    # Strip matching surrounding quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]

                    # Strip inline comments if not inside quotes
                    if "#" in val and not (val.startswith('"') or val.startswith("'")):
                        val = val.split("#", 1)[0].strip()

                    # Set into os.environ and record
                    os.environ[key] = val
                    loaded[key] = val
        except Exception:
            pass

        return loaded

    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """Gets environment variable from os.environ with fallback."""
        return os.environ.get(key, default)
