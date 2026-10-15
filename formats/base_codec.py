from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseTextCodec(ABC):
    """
    Abstract Base Class for Game Text Formats.
    Enables SwitchModStudio to support any game format (DAT, MSBT, SARC, JSON, PO, etc.)
    """

    @abstractmethod
    def read_file(self, file_path: str) -> List[str]:
        """Read game file and return a list of text strings."""
        pass

    @abstractmethod
    def write_file(self, file_path: str, lines: List[str]) -> bool:
        """Write list of text strings back into the game file format."""
        pass

    @abstractmethod
    def export_to_txt(self, source_path: str, target_txt_path: str) -> bool:
        """Export game file to editable plain text."""
        pass

    @abstractmethod
    def import_from_txt(self, source_txt_path: str, target_path: str) -> bool:
        """Import plain text back into game binary format."""
        pass
