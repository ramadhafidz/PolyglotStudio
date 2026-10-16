import os
import sqlite3
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from core.logger import log
from core.status_tracker import StatusTracker

class ProjectDB:
    """
    SQLite Database Manager for Switch Mod Studio localization projects.
    Stores files metadata, per-line translations, and translation memory.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.project_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(self.project_dir, exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for high concurrency & speed
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self):
        """Creates tables and indexes if they don't already exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Metadata Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """)

            # Files Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                rel_path TEXT NOT NULL,
                total_lines INTEGER DEFAULT 0,
                diffs INTEGER DEFAULT 0,
                status TEXT DEFAULT 'untranslated', -- 'untranslated', 'partial', 'completed'
                status_override TEXT DEFAULT NULL,   -- manual user override
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename)")

            # Check if status_override column exists (migration for existing DB)
            cursor.execute("PRAGMA table_info(files)")
            cols = [row["name"] for row in cursor.fetchall()]
            if "status_override" not in cols:
                cursor.execute("ALTER TABLE files ADD COLUMN status_override TEXT DEFAULT NULL")
            if "asset_type" not in cols:
                cursor.execute("ALTER TABLE files ADD COLUMN asset_type TEXT DEFAULT 'text'")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_override ON files(status_override)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_asset_type ON files(asset_type)")

            # Migration: convert legacy 'partial' status to 'untranslated'
            cursor.execute("UPDATE files SET status = 'untranslated' WHERE status = 'partial'")
            cursor.execute("UPDATE files SET status_override = 'untranslated' WHERE status_override = 'partial'")

            # Lines Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS lines (
                file_id INTEGER NOT NULL,
                line_index INTEGER NOT NULL,
                orig_text TEXT NOT NULL,
                trans_text TEXT NOT NULL,
                is_translated INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (file_id, line_index),
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_lines_file ON lines(file_id)")

            # Glossary Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term_en TEXT UNIQUE NOT NULL,
                term_id TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                notes TEXT DEFAULT ''
            )
            """)

            # Translation Memory (TM) Table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text TEXT NOT NULL,
                target_text TEXT NOT NULL,
                source_hash TEXT UNIQUE NOT NULL,
                context_file TEXT DEFAULT '',
                word_count INTEGER DEFAULT 0,
                usage_count INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tm_source_hash ON translation_memory(source_hash)")

            # Set version
            cursor.execute("INSERT OR IGNORE INTO project_meta (key, value) VALUES ('schema_version', '1.2')")
            conn.commit()
            log.info(f"Project SQLite database initialized at {self.db_path}")

    def get_all_file_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves status of all registered files in <1ms.
        Returns { filename: { 'status': ..., 'diffs': ..., 'total_lines': ..., 'is_manual': ..., 'updated_at': ... } }
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename, rel_path, total_lines, diffs, status, status_override, asset_type, updated_at FROM files")
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                override = row["status_override"]
                effective_status = override if override else row["status"]
                asset_type = row["asset_type"] if ("asset_type" in row.keys() and row["asset_type"]) else "text"
                result[row["filename"]] = {
                    "rel_path": row["rel_path"],
                    "total_lines": row["total_lines"],
                    "diffs": row["diffs"],
                    "status": effective_status,
                    "raw_status": row["status"],
                    "status_override": override,
                    "is_manual": bool(override),
                    "asset_type": asset_type,
                    "updated_at": row["updated_at"]
                }
            return result

    def get_modified_files(self) -> List[Dict[str, Any]]:
        """
        Retrieves all files that have genuine user modifications ready for deployment.
        Strict Rule:
        - For text dialogue files (asset_type == 'text' or NULL): diffs MUST be > 0.
          Files with diffs == 0 are untouched/syntax-only and excluded, even if marked 'completed'
          (users often mark syntax-only files 'completed' as a checklist to avoid clutter).
        - For non-text assets (textures, audio, etc.):
          status == 'completed' or status_override == 'completed' or diffs > 0.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, filename, rel_path, status, status_override, diffs, total_lines, asset_type, updated_at
            FROM files
            WHERE diffs > 0 OR (
                COALESCE(asset_type, 'text') != 'text' 
                AND (status = 'completed' OR status_override = 'completed')
            )
            ORDER BY filename ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def upsert_asset_file(self, filename: str, rel_path: str, status: str = "untranslated", asset_type: str = "texture"):
        """
        Registers or updates a non-text asset file (e.g. texture, font, audio).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO files (filename, rel_path, total_lines, diffs, status, asset_type, updated_at)
            VALUES (?, ?, 0, 0, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(filename) DO UPDATE SET
                rel_path = excluded.rel_path,
                status = excluded.status,
                asset_type = excluded.asset_type,
                updated_at = CURRENT_TIMESTAMP
            """, (filename, rel_path, status, asset_type))
            conn.commit()

    def get_file_lines(self, filename: str) -> Optional[List[str]]:
        """
        Retrieves translated lines for a file if saved in database.
        Returns list of trans_text ordered by line_index, or None if not yet saved in DB.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT l.line_index, l.trans_text 
            FROM lines l
            JOIN files f ON f.id = l.file_id
            WHERE f.filename = ?
            ORDER BY l.line_index ASC
            """, (filename,))
            rows = cursor.fetchall()
            if not rows:
                return None
            return [row["trans_text"] for row in rows]

    def get_file_full_data(self, filename: str) -> Optional[Tuple[List[str], List[str]]]:
        """
        Retrieves both (orig_lines, trans_lines) for a file if saved in database.
        Returns (list_orig, list_trans) ordered by line_index, or None if not yet saved in DB.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT l.line_index, l.orig_text, l.trans_text 
            FROM lines l
            JOIN files f ON f.id = l.file_id
            WHERE f.filename = ?
            ORDER BY l.line_index ASC
            """, (filename,))
            rows = cursor.fetchall()
            if not rows:
                return None
            origs = [row["orig_text"] for row in rows]
            trans = [row["trans_text"] for row in rows]
            return origs, trans

    def set_file_status_override(self, filename: str, rel_path: str, override: Optional[str]) -> Tuple[str, bool]:
        """
        Manually override status for a file ('completed', 'partial', 'untranslated', or None for auto).
        Returns (effective_status, is_manual).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM files WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                UPDATE files 
                SET status_override = ?, updated_at = CURRENT_TIMESTAMP
                WHERE filename = ?
                """, (override, filename))
                raw_status = row["status"]
            else:
                raw_status = "untranslated"
                cursor.execute("""
                INSERT INTO files (filename, rel_path, status, status_override, updated_at)
                VALUES (?, ?, 'untranslated', ?, CURRENT_TIMESTAMP)
                """, (filename, rel_path, override))
            conn.commit()

        effective = override if override else raw_status
        is_manual = bool(override)
        log.info(f"Database: File {filename} status override set to '{override}' (effective: {effective}, manual: {is_manual})")
        return effective, is_manual

    def save_file_translation(
        self, 
        filename: str, 
        rel_path: str, 
        orig_lines: List[str], 
        trans_lines: List[str]
    ) -> Tuple[str, int, int, bool]:
        """
        Saves translations for a file atomically in SQLite.
        Preserves true original English text so it is never overwritten by translations.
        Recalculates status, diffs, and total lines.
        Returns (effective_status, diffs, total_lines, is_manual).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch file_id and any existing true original lines to preserve English text
            row = cursor.execute("SELECT id, status_override FROM files WHERE filename = ?", (filename,)).fetchone()
            file_id = row["id"] if row else None
            override = row["status_override"] if row else None

            existing_orig = {}
            if file_id:
                cursor.execute("SELECT line_index, orig_text FROM lines WHERE file_id = ? ORDER BY line_index ASC", (file_id,))
                existing_orig = {r["line_index"]: r["orig_text"] for r in cursor.fetchall() if r["orig_text"]}

            # 2. Build line data preserving true orig_text
            max_len = max(len(orig_lines), len(trans_lines))
            line_data = []
            for i in range(max_len):
                if i in existing_orig and existing_orig[i]:
                    orig = existing_orig[i]
                else:
                    orig = orig_lines[i] if i < len(orig_lines) else ""
                trans = trans_lines[i] if i < len(trans_lines) else orig
                is_trans = 1 if (orig.strip() and orig != trans and not orig.strip().startswith("[~")) else 0
                line_data.append((file_id, i, orig, trans, is_trans))

            # Recalculate status with the true original lines
            orig_check = [d[2] for d in line_data]
            trans_check = [d[3] for d in line_data]
            status, diffs, total = StatusTracker.calculate_status(orig_check, trans_check)
            effective_status = override if override else status
            is_manual = bool(override)

            # 3. Upsert files record
            cursor.execute("""
            INSERT INTO files (filename, rel_path, total_lines, diffs, status, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(filename) DO UPDATE SET
                rel_path = excluded.rel_path,
                total_lines = excluded.total_lines,
                diffs = excluded.diffs,
                status = excluded.status,
                updated_at = CURRENT_TIMESTAMP
            """, (filename, rel_path, total, diffs, status))

            if not file_id:
                row = cursor.execute("SELECT id FROM files WHERE filename = ?", (filename,)).fetchone()
                file_id = row["id"]

            # 4. Replace lines
            cursor.execute("DELETE FROM lines WHERE file_id = ?", (file_id,))
            final_lines = [(file_id, d[1], d[2], d[3], d[4]) for d in line_data]
            cursor.executemany("""
            INSERT INTO lines (file_id, line_index, orig_text, trans_text, is_translated, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, final_lines)

            conn.commit()

        log.info(f"Database: Saved {filename} ({diffs}/{total} diffs, effective status: {effective_status}, manual: {is_manual})")
        return effective_status, diffs, total, is_manual

    def upsert_file_status(
        self, 
        filename: str, 
        rel_path: str, 
        orig_lines: List[str], 
        trans_lines: List[str],
        **kwargs
    ) -> Tuple[str, int, int, bool]:
        """Backward-compatible alias for save_file_translation."""
        return self.save_file_translation(filename, rel_path, orig_lines, trans_lines)

    def search_all_dialogues(self, query: str) -> List[Dict[str, Any]]:
        """
        Global Search across all game dialogue lines in the database.
        Returns matching lines with filename and line_index.
        """
        query_pattern = f"%{query}%"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT f.filename, f.rel_path, l.line_index, l.orig_text, l.trans_text
            FROM lines l
            JOIN files f ON f.id = l.file_id
            WHERE l.orig_text LIKE ? OR l.trans_text LIKE ?
            ORDER BY f.filename ASC, l.line_index ASC
            LIMIT 200
            """, (query_pattern, query_pattern))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_progress_summary(self) -> Dict[str, int]:
        """
        Returns counts considering overrides: {'completed': X, 'untranslated': Y}
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(status_override, status) as eff_status, COUNT(*) as cnt FROM files GROUP BY eff_status")
            rows = cursor.fetchall()
            res = {"completed": 0, "untranslated": 0}
            for r in rows:
                st = r["eff_status"]
                if st == "completed":
                    res["completed"] += r["cnt"]
                else:
                    res["untranslated"] += r["cnt"]
            return res

    # -------------------------------------------------------------
    # Glossary (Kamus Istilah) Management
    # -------------------------------------------------------------

    def get_glossary(self) -> List[Dict[str, str]]:
        """
        Mengambil semua entri glosarium terurut berdasarkan term_en (A-Z).
        Returns:
            List[Dict[str, str]]: Daftar entri glosarium dengan kunci id, term_en, term_id, category, notes.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, term_en, term_id, category, notes FROM glossary ORDER BY term_en ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def add_glossary_term(self, term_en: str, term_id: str, category: str = 'general', notes: str = '') -> int:
        """
        Menambahkan entri baru ke dalam glosarium atau memperbarui jika term_en sudah ada.
        Menggunakan INSERT OR REPLACE sehingga duplikat term_en akan memperbarui data.
        Returns:
            int: ID baris glosarium yang baru dibuat/diperbarui.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO glossary (term_en, term_id, category, notes)
            VALUES (?, ?, ?, ?)
            """, (term_en, term_id, category, notes))
            conn.commit()
            row_id = cursor.lastrowid
            log.info(f"Glosarium term '{term_en}' berhasil disimpan dengan ID {row_id}")
            return row_id

    def update_glossary_term(self, term_id_row: int, term_en: str, term_id: str, category: str = 'general', notes: str = '') -> None:
        """
        Memperbarui entri glosarium yang sudah ada berdasarkan ID baris.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE glossary
            SET term_en = ?, term_id = ?, category = ?, notes = ?
            WHERE id = ?
            """, (term_en, term_id, category, notes, term_id_row))
            conn.commit()
            log.info(f"Glosarium ID {term_id_row} berhasil diperbarui: '{term_en}' -> '{term_id}'")

    def delete_glossary_term(self, term_id_row: int) -> None:
        """
        Menghapus entri glosarium berdasarkan ID baris.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM glossary WHERE id = ?", (term_id_row,))
            conn.commit()
            log.info(f"Glosarium ID {term_id_row} berhasil dihapus")

    def get_glossary_prompt_block(self) -> str:
        """
        Mengembalikan blok teks glosarium terformat untuk disisipkan ke dalam system prompt AI.
        Mengembalikan string kosong jika glosarium kosong.
        """
        terms = self.get_glossary()
        if not terms:
            return ""

        lines = [
            "KAMUS ISTILAH WAJIB (Glossary):",
            "Gunakan terjemahan berikut secara KONSISTEN di seluruh file. JANGAN gunakan alternatif lain."
        ]
        for term in terms:
            lines.append(f'- "{term["term_en"]}" → "{term["term_id"]}"')
        return "\n".join(lines)

    def seed_default_glossary(self) -> None:
        """
        Mengisi default istilah Pokémon SV jika tabel glosarium masih kosong atau menambahkan istilah baru yang belum terdaftar.
        Menggunakan INSERT OR IGNORE agar tidak menimpa kustomisasi pengguna yang sudah ada.
        """
        defaults = [
            # 1. Core Pokémon Terms
            ("Vending Machine", "Vending Machine", "game_term", ""),
            ("TM Machine", "TM Machine", "game_term", ""),
            ("Poké Ball", "Poké Ball", "pokemon", ""),
            ("Pokémon Center", "Pokémon Center", "pokemon", ""),
            ("Pokédex", "Pokédex", "pokemon", ""),
            ("Gym", "Gym", "pokemon", ""),
            ("Gym Leader", "Gym Leader", "pokemon", ""),
            ("Elite Four", "Elite Four", "pokemon", ""),
            ("Champion", "Champion", "pokemon", ""),
            ("Trainer", "Trainer", "pokemon", ""),
            ("Team Star", "Team Star", "pokemon", ""),
            ("Area Zero", "Area Zero", "location", ""),
            ("Tera Type", "Tera Type", "game_term", ""),
            ("Terastal", "Terastal", "game_term", ""),
            ("Tera Orb", "Tera Orb", "game_term", ""),

            # 2. Weathers (Diterjemahkan ke Bahasa Indonesia)
            ("Rain", "Hujan", "game_term", "Kondisi cuaca hujan"),
            ("Heavy Rain", "Hujan Lebat", "game_term", "Kondisi cuaca hujan lebat (Kyogre / Primordial Sea)"),
            ("Harsh Sunlight", "Sinar Matahari Terik", "game_term", "Kondisi cuaca sinar matahari terik"),
            ("Extremely Harsh Sunlight", "Sinar Matahari Terik Ekstrem", "game_term", "Kondisi cuaca sinar matahari terik ekstrem (Groudon / Desolate Land)"),
            ("Strong Sunlight", "Sinar Matahari Terik", "game_term", "Kondisi cuaca sinar matahari terik"),
            ("Sandstorm", "Badai Pasir", "game_term", "Kondisi cuaca badai pasir"),
            ("Snow", "Salju", "game_term", "Kondisi cuaca salju"),
            ("Fog", "Kabut", "game_term", "Kondisi cuaca kabut"),
            ("Strong Winds", "Angin Kencang", "game_term", "Kondisi cuaca angin kencang (Rayquaza / Delta Stream)"),

            # 3. Terrains (Tetap Bahasa Inggris)
            ("Electric Terrain", "Electric Terrain", "game_term", "Kondisi medan Electric Terrain / nama jurus"),
            ("Grassy Terrain", "Grassy Terrain", "game_term", "Kondisi medan Grassy Terrain / nama jurus"),
            ("Misty Terrain", "Misty Terrain", "game_term", "Kondisi medan Misty Terrain / nama jurus"),
            ("Psychic Terrain", "Psychic Terrain", "game_term", "Kondisi medan Psychic Terrain / nama jurus"),

            # 4. Rooms & Field Effects (Tetap Bahasa Inggris)
            ("Trick Room", "Trick Room", "game_term", "Efek ruangan jurus Trick Room"),
            ("Magic Room", "Magic Room", "game_term", "Efek ruangan jurus Magic Room"),
            ("Wonder Room", "Wonder Room", "game_term", "Efek ruangan jurus Wonder Room"),
            ("Tailwind", "Tailwind", "game_term", "Efek angin buritan jurus Tailwind"),
            ("Gravity", "Gravity", "game_term", "Efek gravitasi jurus Gravity"),
            ("Stealth Rock", "Stealth Rock", "game_term", "Entry hazard Stealth Rock"),
            ("Sticky Web", "Sticky Web", "game_term", "Entry hazard Sticky Web"),
            ("Spikes", "Spikes", "game_term", "Entry hazard Spikes"),
            ("Toxic Spikes", "Toxic Spikes", "game_term", "Entry hazard Toxic Spikes"),
            ("Aurora Veil", "Aurora Veil", "game_term", "Efek tirai perlindungan Aurora Veil"),
            ("Light Screen", "Light Screen", "game_term", "Efek tirai perlindungan Light Screen"),
            ("Reflect", "Reflect", "game_term", "Efek tirai perlindungan Reflect"),
            ("Safeguard", "Safeguard", "game_term", "Efek perlindungan status Safeguard"),
            ("Mist", "Mist", "game_term", "Efek perlindungan penurunan stat Mist"),
            ("Mud Sport", "Mud Sport", "game_term", "Efek medan Mud Sport"),
            ("Water Sport", "Water Sport", "game_term", "Efek medan Water Sport"),
            ("Rainbow", "Pelangi", "game_term", "Efek kombinasi Fire + Water Pledge"),
            ("Swamp", "Rawa", "game_term", "Efek kombinasi Water + Grass Pledge"),
            ("Sea of Fire", "Lautan Api", "game_term", "Efek kombinasi Fire + Grass Pledge"),

            # 5. Move Names as Battle States (Tetap Bahasa Inggris)
            ("Encore", "Encore", "game_term", "Kondisi terkena jurus Encore"),
            ("Torment", "Torment", "game_term", "Kondisi terkena jurus Torment"),
            ("Taunt", "Taunt", "game_term", "Kondisi terkena jurus Taunt"),
            ("Leech Seed", "Leech Seed", "game_term", "Efek jurus Leech Seed"),
            ("Destiny Bond", "Destiny Bond", "game_term", "Efek ikatan jurus Destiny Bond"),
            ("Ingrain", "Ingrain", "game_term", "Efek berakar jurus Ingrain"),
            ("Aqua Ring", "Aqua Ring", "game_term", "Efek lingkaran air jurus Aqua Ring"),
            ("Curse", "Curse", "game_term", "Kondisi kutukan jurus Curse"),
            ("Salt Cure", "Salt Cure", "game_term", "Efek pembaluran garam jurus Salt Cure"),
            ("Octolock", "Octolock", "game_term", "Kondisi kuncian jurus Octolock"),
            ("Stockpile", "Stockpile", "game_term", "Kondisi penimbunan jurus Stockpile"),
            ("Imprison", "Imprison", "game_term", "Kondisi kurungan jurus Imprison"),
            ("Embargo", "Embargo", "game_term", "Kondisi jurus Embargo"),
            ("Telekinesis", "Telekinesis", "game_term", "Efek jurus Telekinesis"),
            ("Magnet Rise", "Magnet Rise", "game_term", "Efek mengapung jurus Magnet Rise"),
            ("Wish", "Wish", "game_term", "Efek harapan jurus Wish"),
            ("Charge", "Charge", "game_term", "Efek pengisian daya jurus Charge"),
            ("Bide", "Bide", "game_term", "Kondisi menahan serangan jurus Bide"),
            ("Outrage", "Outrage", "game_term", "Kondisi mengamuk jurus Outrage"),
            ("Petal Dance", "Petal Dance", "game_term", "Kondisi tarian kelopak jurus Petal Dance"),
            ("Uproar", "Uproar", "game_term", "Kondisi keributan jurus Uproar"),
            ("Autotomize", "Autotomize", "game_term", "Efek jurus Autotomize"),
            ("Smack Down", "Smack Down", "game_term", "Efek jatuhan jurus Smack Down"),
            ("Fairy Lock", "Fairy Lock", "game_term", "Kondisi kuncian jurus Fairy Lock"),
            ("Throat Chop", "Throat Chop", "game_term", "Efek pembungkaman jurus Throat Chop"),
            ("Laser Focus", "Laser Focus", "game_term", "Efek fokus jurus Laser Focus"),
            ("Tar Shot", "Tar Shot", "game_term", "Efek lumuran aspal jurus Tar Shot"),
            ("Raging Fury", "Raging Fury", "game_term", "Kondisi kemarahan jurus Raging Fury"),
            ("Lock-On", "Lock-On", "game_term", "Efek penguncian sasaran jurus Lock-On"),
            ("Slow Start", "Slow Start", "game_term", "Ability Slow Start (Regigigas)"),
            ("G-Max Wildfire", "G-Max Wildfire", "game_term", "Efek jurus G-Max Wildfire"),
            ("G-Max Volcalith", "G-Max Volcalith", "game_term", "Efek jurus G-Max Volcalith"),
            ("G-Max Steelsurge", "G-Max Steelsurge", "game_term", "Efek jurus G-Max Steelsurge"),
            ("G-Max Vine Lash", "G-Max Vine Lash", "game_term", "Efek jurus G-Max Vine Lash"),
            ("G-Max Cannonade", "G-Max Cannonade", "game_term", "Efek jurus G-Max Cannonade"),

            # 6. Status Conditions (Standar Resmi Pokémon TCG Indonesia)
            ("Poisoned", "Terkena Racun", "game_term", "Kondisi status racun"),
            ("Badly Poisoned", "Racun Parah", "game_term", "Kondisi status racun mematikan / parah"),
            ("Paralyzed", "Lumpuh", "game_term", "Kondisi status kelumpuhan"),
            ("Burned", "Terbakar", "game_term", "Kondisi status luka bakar"),
            ("Frostbite", "Radang Dingin", "game_term", "Kondisi status radang dingin"),
            ("Asleep", "Tidur", "game_term", "Kondisi status tertidur"),
            ("Drowsy", "Mengantuk", "game_term", "Kondisi status mengantuk"),
            ("Confusion", "Pusing", "game_term", "Kondisi status kebingungan / pusing"),
            ("Infatuation", "Terpikat", "game_term", "Kondisi status terpikat lawan"),
            ("Nightmare", "Mimpi Buruk", "game_term", "Kondisi terkena mimpi buruk"),
            ("Bound", "Terikat", "game_term", "Kondisi terikat tidak bisa bertukar"),

            # 7. Combat States & Modifiers
            ("Critical Hit", "Serangan Kritis", "game_term", "Serangan kritikal dengan damage berlipat"),
            ("Critical Hit Boost", "Peningkatan Serangan Kritis", "game_term", "Peluang serangan kritis meningkat"),
            ("No Ability", "Tanpa Ability", "game_term", "Efek hilangnya fungsi Ability"),
            ("Healing Prevented", "Pemulihan Dicegah", "game_term", "Tidak dapat memulihkan HP"),
            ("Identified", "Teridentifikasi", "game_term", "Dapat diserang jurus yang biasanya tidak mempan"),
            ("Move Disabled", "Jurus Dinonaktifkan", "game_term", "Jurus tidak dapat digunakan"),
            ("Can't Escape", "Tidak Bisa Kabur", "game_term", "Tidak dapat melarikan diri atau bertukar"),
            ("Can’t Escape", "Tidak Bisa Kabur", "game_term", "Tidak dapat melarikan diri atau bertukar"),
            ("Counting Down", "Hitungan Mundur", "game_term", "Hitungan mundur sebelum pingsan (Perish Song)"),
            ("Future Attack", "Serangan Masa Depan", "game_term", "Serangan tertunda masa depan (Future Sight/Doom Desire)"),
            ("Fixated", "Terpaku", "game_term", "Terpaku pada jurus terakhir"),
            ("Splinters", "Serpihan Runcing", "game_term", "Tertusuk serpihan runcing setiap giliran"),
            ("Obscured", "Terselubung", "game_term", "Terselubung lumpur atau kabut pelindung"),
            ("Primed", "Siap Menyerang", "game_term", "Kuda-kuda siap memberikan serangan kuat"),
            ("Stance Swap", "Tukar Kuda-Kuda", "game_term", "Tukar stat ofensif dan defensif"),
            ("Frenzied Might", "Kekuatan Mengamuk", "game_term", "Kekuatan Pokémon Raja yang mengamuk"),
            ("Wild Might", "Kekuatan Liar", "game_term", "Kekuatan Pokémon Alpha liar"),
            ("Terrific Might", "Kekuatan Hebat", "game_term", "Kekuatan luar biasa Pokémon Alpha"),
            ("Terrible Might", "Kekuatan Mengerikan", "game_term", "Kekuatan mengerikan Pokémon"),
            ("Power Boost", "Peningkatan Serangan", "game_term", "Stat Attack dan Sp. Atk meningkat"),
            ("Power Drop", "Penurunan Serangan", "game_term", "Stat Attack dan Sp. Atk menurun"),
            ("Guard Boost", "Peningkatan Pertahanan", "game_term", "Stat Defense dan Sp. Def meningkat"),
            ("Guard Drop", "Penurunan Pertahanan", "game_term", "Stat Defense dan Sp. Def menurun"),
            ("Syrupy", "Lengket Berlendir", "game_term", "Kecepatan turun akibat sirup lengket"),
            ("Going All Out", "Mengerahkan Segalanya", "game_term", "Peningkatan serangan dari sorakan Trainer"),
            ("Hanging Tough", "Bertahan Kuat", "game_term", "Peningkatan pertahanan dari sorakan Trainer"),
        ]
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO glossary (term_en, term_id, category, notes) VALUES (?, ?, ?, ?)",
                defaults
            )
            conn.commit()
            log.info(f"Berhasil mensinkronkan {len(defaults)} entri glosarium default Pokémon SV ke database.")

    # ----------------- Translation Memory (TM) Methods -----------------
    @staticmethod
    def _compute_text_hash(text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _count_words(text: str) -> int:
        clean = re.sub(r'\[.*?\]|\\n|\\r|\\c', ' ', text)
        return len(clean.strip().split())

    def add_tm_entry(self, source_text: str, target_text: str, context_file: str = "") -> bool:
        """
        Records a translated sentence pair into Translation Memory.
        Filters out empty lines, identical lines, or pure control-token strings.
        """
        s_clean = source_text.strip()
        t_clean = target_text.strip()
        if not s_clean or not t_clean or s_clean == t_clean:
            return False

        words = self._count_words(s_clean)
        if words == 0:
            return False

        s_hash = self._compute_text_hash(s_clean)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO translation_memory (source_text, target_text, source_hash, context_file, word_count, usage_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(source_hash) DO UPDATE SET
                target_text = excluded.target_text,
                context_file = CASE WHEN excluded.context_file != '' THEN excluded.context_file ELSE translation_memory.context_file END,
                usage_count = translation_memory.usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
            """, (s_clean, t_clean, s_hash, context_file, words))
            conn.commit()
            return True

    def add_batch_tm_entries(self, pairs: List[Tuple[str, str]], context_file: str = "") -> int:
        """
        Records multiple translation pairs into TM in a single fast transaction.
        """
        if not pairs:
            return 0

        valid_entries = []
        for s, t in pairs:
            s_clean = s.strip()
            t_clean = t.strip()
            if not s_clean or not t_clean or s_clean == t_clean:
                continue
            words = self._count_words(s_clean)
            if words == 0:
                continue
            s_hash = self._compute_text_hash(s_clean)
            valid_entries.append((s_clean, t_clean, s_hash, context_file, words))

        if not valid_entries:
            return 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
            INSERT INTO translation_memory (source_text, target_text, source_hash, context_file, word_count, usage_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(source_hash) DO UPDATE SET
                target_text = excluded.target_text,
                usage_count = translation_memory.usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
            """, valid_entries)
            conn.commit()
            return len(valid_entries)

    def get_exact_tm_match(self, source_text: str, min_words: int = 3) -> Optional[str]:
        """
        Checks for a 100% exact match in Translation Memory.
        Safety Rule: Only returns match if word count >= min_words OR it is an exact safe UI token (e.g. 'Yes\nNo').
        Protects ambiguous single words like 'Run', 'Fire', 'Right' from being wrongly replaced.
        """
        s_clean = source_text.strip()
        if not s_clean:
            return None

        words = self._count_words(s_clean)
        is_safe_short = s_clean.lower() in ("yes\nno", "yes", "no", "ok", "cancel")
        if words < min_words and not is_safe_short:
            return None

        s_hash = self._compute_text_hash(s_clean)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT target_text FROM translation_memory WHERE source_hash = ?", (s_hash,))
            row = cursor.fetchone()
            if row:
                return row["target_text"]
            return None

    def get_tm_prompt_block(self, source_lines: List[str], max_suggestions: int = 15) -> str:
        """
        Finds matching TM entries for the given source lines and formats them as contextual references for AI.
        """
        if not source_lines:
            return ""

        hashes = [self._compute_text_hash(l) for l in source_lines if l.strip()]
        if not hashes:
            return ""

        unique_hashes = list(set(hashes))[:max_suggestions * 2]
        placeholders = ",".join(["?"] * len(unique_hashes))

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
            SELECT source_text, target_text FROM translation_memory 
            WHERE source_hash IN ({placeholders})
            LIMIT ?
            """, (*unique_hashes, max_suggestions))
            rows = cursor.fetchall()

        if not rows:
            return ""

        prompt_lines = [
            "REFERENSI MEMORI TERJEMAHAN (Translation Memory):",
            "Gunakan padanan berikut HANYA JIKA konteks dialognya sesuai (jangan paksakan jika konteks berbeda):"
        ]
        for row in rows:
            s_short = row["source_text"].replace("\n", " ").strip()
            t_short = row["target_text"].replace("\n", " ").strip()
            prompt_lines.append(f'- "{s_short}" → "{t_short}"')
        return "\n".join(prompt_lines)

    def get_tm_stats(self) -> Dict[str, int]:
        """Returns total entries and usage statistics in Translation Memory."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total_entries, COALESCE(SUM(usage_count), 0) as total_uses FROM translation_memory")
            row = cursor.fetchone()
            return {
                "total_entries": row["total_entries"] if row else 0,
                "total_uses": row["total_uses"] if row else 0
            }

