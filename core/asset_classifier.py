"""
Asset Classifier for Nintendo Switch Game Modding.
Categorizes game files into specialized asset groups:
- Text: Dialogue & localization files (.dat, .txt, .json)
- Texture: Visual graphics with baked text (.png, .dds, .tga, .bntx)
- Font: UI fonts & glyph sets (.ttf, .otf, .bffnt, .bfttf)
- Audio: Voice acting & sound cues (.wav, .bwav, .bfwav, .mp3, .pck)
- Layout: UI layout & binary archives (.bflyt, .bflim, .arc)
- Binary: Other game assets
"""

import os
from enum import Enum
from typing import Dict, List, Optional, Set
from core.icons import Icons


class AssetType(str, Enum):
    TEXT = "text"
    TEXTURE = "texture"
    FONT = "font"
    AUDIO = "audio"
    LAYOUT = "layout"
    BINARY = "binary"


class AssetClassifier:
    """
    Classifies file paths into game asset types and provides metadata icons & category filters.
    """

    EXT_MAP: Dict[str, AssetType] = {
        # Dialogue & Text
        ".dat": AssetType.TEXT,
        ".txt": AssetType.TEXT,
        ".json": AssetType.TEXT,
        ".csv": AssetType.TEXT,
        ".xml": AssetType.TEXT,
        
        # Textures & Graphics
        ".png": AssetType.TEXTURE,
        ".dds": AssetType.TEXTURE,
        ".tga": AssetType.TEXTURE,
        ".jpg": AssetType.TEXTURE,
        ".jpeg": AssetType.TEXTURE,
        ".bmp": AssetType.TEXTURE,
        ".webp": AssetType.TEXTURE,
        ".bntx": AssetType.TEXTURE,
        
        # Fonts
        ".ttf": AssetType.FONT,
        ".otf": AssetType.FONT,
        ".bffnt": AssetType.FONT,
        ".bfttf": AssetType.FONT,
        
        # Audio & Voice
        ".wav": AssetType.AUDIO,
        ".bwav": AssetType.AUDIO,
        ".bfwav": AssetType.AUDIO,
        ".mp3": AssetType.AUDIO,
        ".ogg": AssetType.AUDIO,
        ".pck": AssetType.AUDIO,
        ".bnk": AssetType.AUDIO,
        
        # Layouts
        ".bflyt": AssetType.LAYOUT,
        ".bflim": AssetType.LAYOUT,
        ".arc": AssetType.LAYOUT,
    }

    ICON_MAP: Dict[AssetType, str] = {
        AssetType.TEXT: Icons.EDIT,
        AssetType.TEXTURE: Icons.IMAGE,
        AssetType.FONT: Icons.FONT,
        AssetType.AUDIO: Icons.AUDIO,
        AssetType.LAYOUT: Icons.PACKAGE,
        AssetType.BINARY: Icons.EXPORT,
    }

    CATEGORY_LABELS: List[str] = [
        "All Files",
        "Dialogue Text (.dat, .txt)",
        "Images & Textures (.png, .dds, .bntx)",
        "Fonts & Typography (.ttf, .bffnt)",
        "Audio / Voice (.wav, .bwav)",
    ]

    @classmethod
    def get_asset_type(cls, file_path: str) -> AssetType:
        ext = os.path.splitext(file_path)[1].lower()
        return cls.EXT_MAP.get(ext, AssetType.BINARY)

    @classmethod
    def get_icon(cls, file_path_or_type: str) -> str:
        if isinstance(file_path_or_type, AssetType):
            atype = file_path_or_type
        elif file_path_or_type in AssetType._value2member_map_:
            atype = AssetType(file_path_or_type)
        else:
            atype = cls.get_asset_type(file_path_or_type)
        return cls.ICON_MAP.get(atype, Icons.EXPORT)

    @classmethod
    def matches_category_filter(cls, file_path: str, filter_name: str) -> bool:
        if not filter_name or filter_name in ("All Files", "Semua File"):
            return True
        atype = cls.get_asset_type(file_path)
        fn_lower = filter_name.lower()
        if "texture" in fn_lower or "gambar" in fn_lower or "image" in fn_lower:
            return atype == AssetType.TEXTURE
        elif "dialogue" in fn_lower or "dialog" in fn_lower or "teks" in fn_lower or ("text" in fn_lower and "texture" not in fn_lower):
            return atype == AssetType.TEXT
        elif "font" in fn_lower or "tipografi" in fn_lower:
            return atype == AssetType.FONT
        elif "audio" in fn_lower or "voice" in fn_lower or "suara" in fn_lower:
            return atype == AssetType.AUDIO
        return True

    @classmethod
    def is_text(cls, file_path: str) -> bool:
        return cls.get_asset_type(file_path) == AssetType.TEXT

    @classmethod
    def is_texture(cls, file_path: str) -> bool:
        return cls.get_asset_type(file_path) == AssetType.TEXTURE
