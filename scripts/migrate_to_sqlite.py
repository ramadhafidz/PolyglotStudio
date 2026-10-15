import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import log
from core.db_manager import ProjectDB
from core.status_tracker import StatusTracker
from formats.pokemon_dat import PokemonDatCodec

def migrate_existing_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    workspace_dir = os.path.join(base_dir, "workspace", "PokemonScarlet_0100A3D008C5C000")
    db_path = os.path.join(workspace_dir, "project.db")
    trans_dir = os.path.join(workspace_dir, "translations")
    english_dir = r"D:\Environtment\utilities\trinity\output\message\dat\English"

    db = ProjectDB(db_path)
    codec = PokemonDatCodec()

    print(f"Starting migration to SQLite: {db_path}...")
    
    txt_files = {}
    if os.path.exists(trans_dir):
        for f in os.listdir(trans_dir):
            if f.endswith(".txt"):
                txt_files[f[:-4]] = os.path.join(trans_dir, f)

    print(f"Found {len(txt_files)} translated .txt files to migrate.")

    migrated_count = 0
    total_files = 0

    for root, _, files in os.walk(english_dir):
        for f in sorted(files):
            if f.endswith(".dat"):
                total_files += 1
                base = f[:-4]
                full_p = os.path.join(root, f)
                rel = os.path.relpath(full_p, english_dir)

                if base in txt_files:
                    txt_p = txt_files[base]
                    try:
                        orig_lines = codec.read_file(full_p)
                        trans_lines = StatusTracker.parse_txt_lines(txt_p)
                        status, diffs, total = db.save_file_translation(f, rel, orig_lines, trans_lines)
                        migrated_count += 1
                        print(f"Migrated {f}: {status} ({diffs}/{total})")
                    except Exception as e:
                        print(f"Failed to migrate {f}: {e}")

    summary = db.get_progress_summary()
    print(f"Migration complete! Total files scanned: {total_files}")
    print(f"Database progress summary: {summary}")

if __name__ == "__main__":
    migrate_existing_data()
