"""
High-Performance LayeredFS Mod Deployer & Packager for Polyglot Studio.
Compiles modified game assets into valid Nintendo Switch LayeredFS folder structure,
ready for Eden, Ryujinx, Yuzu, and real Nintendo Switch Atmosphere CFW.
"""

import os
import time
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Tuple

from core.logger import log
from core.db_manager import ProjectDB
from core.asset_classifier import AssetClassifier, AssetType
from formats.pokemon_dat import PokemonDatCodec


@dataclass
class DeployResult:
    """Stores execution metrics and outcomes for a mod deployment."""
    success: bool
    mod_root: str
    text_count: int = 0
    asset_count: int = 0
    total_files: int = 0
    total_bytes: int = 0
    elapsed_ms: float = 0.0
    deployed_files: List[str] = field(default_factory=list)
    error: Optional[str] = None


class LayeredFSDeployer:
    """
    Manages compiling, staging, deploying, and packaging LayeredFS mods.
    Strict Rule: Only compiles and deploys files that have user modifications.
    Untouched / untranslated files are never copied to keep mods clean, fast, and lightweight.
    """

    def __init__(
        self,
        db: ProjectDB,
        codec=None,
        title_id: str = "0100A3D008C5C000",
        mod_name: str = "[ID] Pokemon Scarlet Bahasa Indonesia",
        mod_assets_dir: str = "",
        romfs_message_prefix: str = "message/dat/English"
    ):
        self.db = db
        self.codec = codec or PokemonDatCodec()
        self.title_id = title_id.upper()
        self.mod_name = mod_name
        self.mod_assets_dir = mod_assets_dir
        self.romfs_message_prefix = romfs_message_prefix.replace("\\", "/").strip("/")

    def get_modified_items(self) -> List[Dict[str, Any]]:
        """
        Retrieves all modified files ready for deployment:
        1. Text dialogue files with user edits or marked completed in SQLite.
        2. Visual / audio asset files in workspace/assets.
        """
        modified_items = []
        seen_filenames = set()

        # 1. Query modified files from SQLite database
        db_files = self.db.get_modified_files()
        for f in db_files:
            fname = f["filename"]
            rel_p = f["rel_path"].replace("\\", "/")
            atype = f.get("asset_type") or AssetClassifier.get_asset_type(fname)
            diffs = f.get("diffs", 0)

            # Strict Rule: Text dialogue files (.dat, etc.) must have diffs > 0.
            # Untouched files or syntax-only files marked completed must never be deployed.
            if atype == AssetType.TEXT or str(atype).lower() == "text" or fname.lower().endswith(".dat"):
                if diffs <= 0:
                    continue

            # Build exact destination path relative to RomFS root
            if atype == AssetType.TEXT or fname.lower().endswith(".dat"):
                if rel_p.startswith(self.romfs_message_prefix):
                    romfs_rel = rel_p
                else:
                    romfs_rel = f"{self.romfs_message_prefix}/{rel_p}".replace("//", "/")
            else:
                romfs_rel = rel_p

            modified_items.append({
                "filename": fname,
                "rel_path": rel_p,
                "romfs_rel_path": romfs_rel,
                "asset_type": atype,
                "diffs": diffs,
                "total_lines": f.get("total_lines", 0),
                "source": "db"
            })
            seen_filenames.add(fname)

        # 2. Check mod_assets_dir for any modified non-text assets not yet in seen_filenames
        if self.mod_assets_dir and os.path.exists(self.mod_assets_dir):
            for root, _, files in os.walk(self.mod_assets_dir):
                for f in files:
                    if f in seen_filenames:
                        continue
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, self.mod_assets_dir).replace("\\", "/")
                    atype = AssetClassifier.get_asset_type(f)

                    modified_items.append({
                        "filename": f,
                        "rel_path": rel_p,
                        "romfs_rel_path": rel_p,
                        "asset_type": atype,
                        "diffs": 1,
                        "total_lines": 0,
                        "source": "assets_dir",
                        "full_path": full_p
                    })
                    seen_filenames.add(f)

        return modified_items

    def deploy_to_directory(
        self,
        target_mod_root: str,
        clean_old: bool = True,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> DeployResult:
        """
        Compiles and deploys all modified files into target LayeredFS folder:
        <target_mod_root>/romfs/...
        """
        t0 = time.time()
        mod_root = os.path.abspath(target_mod_root)
        target_romfs = os.path.join(mod_root, "romfs")

        items = self.get_modified_items()
        if not items:
            return DeployResult(
                success=True,
                mod_root=mod_root,
                text_count=0,
                asset_count=0,
                total_files=0,
                total_bytes=0,
                elapsed_ms=(time.time() - t0) * 1000,
                deployed_files=[],
                error=None
            )

        # 1. Clean existing romfs in destination if requested
        if clean_old and os.path.exists(target_romfs):
            try:
                shutil.rmtree(target_romfs)
                log.info(f"LayeredFS: Cleaned previous romfs at {target_romfs}")
            except Exception as e:
                log.warning(f"LayeredFS: Could not clean old romfs folder: {e}")

        os.makedirs(target_romfs, exist_ok=True)

        text_count = 0
        asset_count = 0
        total_bytes = 0
        deployed_files = []
        tot = len(items)

        try:
            for i, item in enumerate(items, 1):
                fname = item["filename"]
                romfs_rel = item["romfs_rel_path"]
                atype = item["asset_type"]
                dest_file = os.path.join(target_romfs, os.path.normpath(romfs_rel))
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)

                if progress_cb:
                    progress_cb(i, tot, fname)

                # A. Text File (compile from DB lines)
                if atype == AssetType.TEXT or str(atype).lower() == "text" or fname.lower().endswith(".dat"):
                    if item.get("diffs", 0) <= 0:
                        continue
                    lines = self.db.get_file_lines(fname)
                    if lines is not None:
                        compiled_bytes = self.codec.encode_lines(lines)
                        with open(dest_file, "wb") as f_out:
                            f_out.write(compiled_bytes)
                        total_bytes += len(compiled_bytes)
                        text_count += 1
                        deployed_files.append(romfs_rel)

                # B. Non-text Asset File (copy from mod_assets_dir)
                else:
                    src_asset = item.get("full_path")
                    if not src_asset and self.mod_assets_dir:
                        src_asset = os.path.join(self.mod_assets_dir, os.path.normpath(item["rel_path"]))

                    if src_asset and os.path.exists(src_asset):
                        shutil.copy2(src_asset, dest_file)
                        total_bytes += os.path.getsize(dest_file)
                        asset_count += 1
                        deployed_files.append(romfs_rel)

            # 2. Write metadata files for Atmosphere / SimpleModDownloader
            self._write_metadata_files(mod_root, len(deployed_files))

            elapsed = (time.time() - t0) * 1000
            log.info(
                f"LayeredFS Deploy finished in {elapsed:.1f}ms: "
                f"{text_count} text files, {asset_count} assets ({total_bytes / 1024:.1f} KB) deployed to {mod_root}"
            )

            return DeployResult(
                success=True,
                mod_root=mod_root,
                text_count=text_count,
                asset_count=asset_count,
                total_files=len(deployed_files),
                total_bytes=total_bytes,
                elapsed_ms=elapsed,
                deployed_files=deployed_files,
                error=None
            )

        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            log.error(f"LayeredFS Deploy failed: {e}", exc_info=True)
            return DeployResult(
                success=False,
                mod_root=mod_root,
                text_count=text_count,
                asset_count=asset_count,
                total_files=len(deployed_files),
                total_bytes=total_bytes,
                elapsed_ms=elapsed,
                deployed_files=deployed_files,
                error=str(e)
            )

    def deploy_to_emulator(
        self,
        load_path: str,
        clean_old: bool = True,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> DeployResult:
        """
        Deploys directly into emulator load folder:
        <load_path>/<title_id>/<mod_name>/romfs/...
        """
        if not load_path:
            return DeployResult(
                success=False,
                mod_root="",
                error="Path emulator load_path belum diatur. Silakan atur di menu Pengaturan atau file .env."
            )

        target_mod_root = os.path.join(load_path, self.title_id, self.mod_name)
        return self.deploy_to_directory(target_mod_root, clean_old=clean_old, progress_cb=progress_cb)

    def export_to_zip(
        self,
        zip_path: str,
        atmosphere_layout: bool = True,
        clean_old: bool = True,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> DeployResult:
        """
        Compiles and packages modified files directly into a distributable .zip package.
        If atmosphere_layout is True, packages into:
        atmosphere/contents/<title_id>/romfs/...
        """
        t0 = time.time()
        import tempfile
        zip_path = os.path.abspath(zip_path)
        os.makedirs(os.path.dirname(zip_path), exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            if atmosphere_layout:
                target_stage = os.path.join(tmp_dir, "atmosphere", "contents", self.title_id)
            else:
                target_stage = os.path.join(tmp_dir, self.mod_name)

            deploy_res = self.deploy_to_directory(target_stage, clean_old=clean_old, progress_cb=progress_cb)
            if not deploy_res.success:
                return deploy_res

            # Create ZIP archive
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(tmp_dir):
                    for f in files:
                        full_f = os.path.join(root, f)
                        rel_in_zip = os.path.relpath(full_f, tmp_dir)
                        zf.write(full_f, rel_in_zip)

        elapsed = (time.time() - t0) * 1000
        zip_bytes = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
        log.info(f"LayeredFS ZIP Export finished in {elapsed:.1f}ms ({zip_bytes / 1024:.1f} KB): {zip_path}")

        return DeployResult(
            success=True,
            mod_root=zip_path,
            text_count=deploy_res.text_count,
            asset_count=deploy_res.asset_count,
            total_files=deploy_res.total_files,
            total_bytes=zip_bytes,
            elapsed_ms=elapsed,
            deployed_files=deploy_res.deployed_files,
            error=None
        )

    def _write_metadata_files(self, mod_root: str, file_count: int):
        """Generates standard metadata files for Atmosphere / Switch mod managers."""
        # 1. toolbox.json (SimpleModDownloader standard)
        toolbox_path = os.path.join(mod_root, "toolbox.json")
        toolbox_data = {
            "name": self.mod_name,
            "author": "Polyglot Studio",
            "version": "1.0.0",
            "description": f"Localization mod containing {file_count} translated assets.",
            "tid": self.title_id
        }
        try:
            with open(toolbox_path, "w", encoding="utf-8") as f:
                json.dump(toolbox_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Could not write toolbox.json: {e}")

        # 2. mod_info.json (Polyglot Studio build manifest)
        manifest_path = os.path.join(mod_root, "mod_info.json")
        manifest_data = {
            "tool": "Polyglot Studio",
            "title_id": self.title_id,
            "mod_name": self.mod_name,
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "modified_files_count": file_count
        }
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning(f"Could not write mod_info.json: {e}")
