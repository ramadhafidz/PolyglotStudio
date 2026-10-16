import os
import sys
import subprocess
import base64
import time
from typing import Optional, List, Dict, Tuple
from core.logger import log

class TrpfsClient:
    """
    High-performance client for TrpfsWorker.exe.
    Enables reading and on-demand file extraction directly from Nintendo Switch
    Trinity/Flat RomFS (data.trpfd / data.trpfs) with zero Trinity GUI dependency.
    """

    def __init__(self, worker_exe_path: Optional[str] = None):
        if worker_exe_path is None:
            # Look in tools/TrpfsWorker/bin/Release/net8.0-windows/TrpfsWorker.exe
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            worker_exe_path = os.path.join(
                base_dir, "tools", "TrpfsWorker", "bin", "Release", "net8.0-windows", "TrpfsWorker.exe"
            )
        self.worker_exe_path = worker_exe_path
        self.process: Optional[subprocess.Popen] = None
        self.is_loaded = False
        self.romfs_path: Optional[str] = None
        self.total_hashes = 0
        self.named_count = 0

    def _ensure_process(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True

        if not os.path.isfile(self.worker_exe_path):
            log.error(f"TrpfsWorker executable not found at: {self.worker_exe_path}")
            return False

        try:
            cwd = os.path.dirname(self.worker_exe_path)
            self.process = subprocess.Popen(
                [self.worker_exe_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=cwd,
                bufsize=1
            )
            init_line = self.process.stdout.readline().strip()
            log.info(f"TrpfsWorker daemon started: {init_line}")
            return True
        except Exception as e:
            log.error(f"Failed to start TrpfsWorker process: {e}", exc_info=True)
            self.process = None
            return False

    def load_romfs(self, romfs_path: str) -> Tuple[bool, str]:
        """
        Loads the RomFS directory (arc/data.trpfd and arc/data.trpfs).
        """
        if not self._ensure_process():
            return False, "Failed to start TrpfsWorker background process."

        romfs_path = os.path.abspath(romfs_path)
        log.info(f"Loading RomFS from {romfs_path} via TrpfsWorker...")
        t0 = time.time()

        try:
            self.process.stdin.write(f"LOAD {romfs_path}\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline().strip()

            if response.startswith("READY"):
                parts = response.split()
                self.total_hashes = int(parts[1]) if len(parts) > 1 else 0
                self.named_count = int(parts[2]) if len(parts) > 2 else 0
                self.is_loaded = True
                self.romfs_path = romfs_path
                dt = (time.time() - t0) * 1000
                msg = f"RomFS loaded in {dt:.0f}ms ({self.total_hashes} hashes, {self.named_count} named files)."
                log.info(msg)
                return True, msg
            else:
                err_msg = response.replace("ERR ", "")
                log.error(f"TrpfsWorker load error: {err_msg}")
                return False, err_msg
        except Exception as e:
            log.error(f"Exception communicating with TrpfsWorker: {e}", exc_info=True)
            return False, str(e)

    def list_files(self, filter_keyword: str = "") -> List[Dict[str, str]]:
        """
        Lists files matching filter_keyword.
        Returns list of dicts: {"hash": "...", "rel_path": "...", "filename": "..."}
        """
        if not self.is_loaded or not self._ensure_process():
            return []

        try:
            self.process.stdin.write(f"LIST {filter_keyword}\n")
            self.process.stdin.flush()

            files = []
            while True:
                line = self.process.stdout.readline().strip()
                if not line or line == "END_LIST":
                    break
                if line.startswith("ERR"):
                    log.error(f"TrpfsWorker LIST error: {line}")
                    break
                if "|" in line:
                    h, path = line.split("|", 1)
                    files.append({
                        "hash": h,
                        "rel_path": path,
                        "filename": os.path.basename(path)
                    })
            return files
        except Exception as e:
            log.error(f"Error querying file list from TrpfsWorker: {e}", exc_info=True)
            return []

    def extract_file_bytes(self, target: str) -> Optional[bytes]:
        """
        Extracts a single file's raw bytes on-demand using its virtual path or 64-bit hash.
        """
        if not self.is_loaded or not self._ensure_process():
            return None

        try:
            self.process.stdin.write(f"EXTRACT {target}\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline().strip()

            if response.startswith("BASE64"):
                parts = response.split(" ", 2)
                if len(parts) >= 3:
                    b64_data = parts[2]
                    return base64.b64decode(b64_data)
                elif len(parts) == 2:
                    return b""
            log.error(f"Failed to extract {target}: {response}")
            return None
        except Exception as e:
            log.error(f"Exception extracting file bytes for {target}: {e}", exc_info=True)
            return None

    def get_file(self, target: str) -> Optional[bytes]:
        """
        Alias for extract_file_bytes for convenience and backward compatibility.
        """
        return self.extract_file_bytes(target)

    def extract_file_to_disk(self, target: str, out_path: str) -> bool:
        """
        Extracts a file directly to disk on-demand.
        """
        if not self.is_loaded or not self._ensure_process():
            return False

        out_path = os.path.abspath(out_path)
        try:
            self.process.stdin.write(f"EXTRACT {target} {out_path}\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline().strip()

            if response.startswith("EXTRACTED"):
                return True
            log.error(f"Failed to extract to disk {target} -> {out_path}: {response}")
            return False
        except Exception as e:
            log.error(f"Exception extracting {target} to {out_path}: {e}", exc_info=True)
            return False

    def extract_texture_png(self, target: str, out_png_path: str) -> bool:
        """
        Extracts a texture file and converts it to a standard PNG on-demand.
        If the file is a Nintendo Switch BNTX archive, it is decoded via BnTxx into PNG.
        """
        if not self.is_loaded or not self._ensure_process():
            return False

        out_png_path = os.path.abspath(out_png_path)
        try:
            self.process.stdin.write(f"EXTRACT_PNG {target} {out_png_path}\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline().strip()

            if response.startswith("EXTRACTED_PNG"):
                return True
            log.error(f"Failed to extract PNG {target} -> {out_png_path}: {response}")
            return False
        except Exception as e:
            log.error(f"Exception extracting PNG {target} to {out_png_path}: {e}", exc_info=True)
            return False

    def close(self):
        """
        Shuts down the TrpfsWorker background process.
        """
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.stdin.write("QUIT\n")
                self.process.stdin.flush()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            finally:
                try:
                    if self.process.stdin:
                        self.process.stdin.close()
                    if self.process.stdout:
                        self.process.stdout.close()
                    if self.process.stderr:
                        self.process.stderr.close()
                except Exception:
                    pass
            self.process = None
            self.is_loaded = False
            log.info("TrpfsWorker background process terminated.")
