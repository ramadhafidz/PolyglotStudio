# 🤖 AGENTS.md — Polyglot Studio Guide for AI Agents

Welcome, AI Agent! This document provides complete context, architectural guidelines, code conventions, and critical user preferences for **Polyglot Studio** (formerly Switch Mod Studio). Read this before making changes to the codebase.

---

## 🎯 1. Project Overview & Mission

**Polyglot Studio** is a specialized, high-performance desktop application for Nintendo Switch game localization and modding. It is currently configured and actively used for translating **Pokémon Scarlet & Violet** (`Title ID: 0100A3D008C5C000`) into Indonesian (Bahasa Indonesia).

### Primary Capabilities:
1. **Binary DAT Decoding & Encoding**:
   - Decodes and repacks Game Freak's rolling XOR encrypted Flat/Trinity binary text format (`.dat` files) using pure Python ([`formats/pokemon_dat.py`](file:///E:/Modding/SwitchModStudio/formats/pokemon_dat.py)).
2. **Side-by-Side Localization Editor**:
   - Left panel: Treeview file explorer with search, directory hierarchy, and status filtering.
   - Right panel: Side-by-side translation table (`Line | Accept | English Original | Indonesian Translation`).
3. **Universal AI Translation & Tag Preservation**:
   - AI translation via OpenAI, Claude, or Gemini REST APIs ([`core/universal_ai.py`](file:///E:/Modding/SwitchModStudio/core/universal_ai.py)) with automatic batching (20 lines/request) and extended 180s timeout to prevent proxy read timeouts on large dialogue files.
   - **TagGuard** ([`core/tag_guard.py`](file:///E:/Modding/SwitchModStudio/core/tag_guard.py)) validates and protects game engine tokens (`[VAR ...]`, `[WAIT ...]`, `[~ ...]`, `\n`, `\r`, `\c`) against corruption.
4. **Git Diff Review Staging System**:
   - Proposed AI translations are staged with a green Git Diff highlight (`#E6FFEC` / `#D4EDDA`).
   - Translators can accept line-by-line (clicking `Icons.ACCEPT`) or click **Accept All** / **Discard All**.
   - Auto-save runs **only after acceptance**.
5. **Dialogue Syntax Highlighting**:
   - Highlights variables (`[VAR ...]`), wait tags (`[WAIT ...]`), and line escapes (`\n`, `\r`, `\c`) with pill/badge formatting ([`core/syntax_highlighter.py`](file:///E:/Modding/SwitchModStudio/core/syntax_highlighter.py)).
   - Displayed in the **Live Dialogue Inspector** below the table and inside the **Edit Dialog**.
6. **Multi-Asset Localization & Texture Viewer**:
   - Classifies project files into `Text`, `Texture`, `Font`, `Audio`, `Layout`, and `Binary` ([`core/asset_classifier.py`](file:///E:/Modding/SwitchModStudio/core/asset_classifier.py)).
   - Side-by-side texture comparison workspace ([`gui/viewers/texture_viewer.py`](file:///E:/Modding/SwitchModStudio/gui/viewers/texture_viewer.py)) with dual canvas, zoom controls (25% - 400%), alpha checkerboard, external image editor launcher, and direct replacement/reversion.
   - Left panel category filtering (`All Assets`, `Dialogue Text (.dat)`, `Textures / Images`, `Fonts`, `Audio / SFX`, `Layouts / UI`, `Other Binary`).
7. **RomFS Virtual Explorer & On-Demand Extraction (Zero Trinity.exe Dependency)**:
   - Direct parsing of Trinity FlatBuffers descriptor (`arc/data.trpfd`) and archive stream (`arc/data.trpfs`) via dedicated headless worker (`tools/TrpfsWorker`).
   - Integrated Python client ([`core/trpfs_client.py`](file:///E:/Modding/SwitchModStudio/core/trpfs_client.py)) communicating with `TrpfsWorker.exe` over high-speed IPC.
   - On-demand extraction (< 3ms) directly into memory/codec without manual exporting.
   - Completely eliminates dependency on `TrinityFileExplorer.exe` WinForms GUI.
8. **Eden Emulator Mod Manager & Deployment**:
   - One-click compile and deploy directly to Eden emulator mod load paths for both dialogue text and modified assets.
9. **Persistent Glossary & Autonomous Terminology Consistency System**:
   - SQLite-backed terminology memory (`glossary` table in `project.db`).
   - Automatically injected into AI system prompts (`KAMUS ISTILAH WAJIB`) for both full-file batch translations and single-line dialog translations to enforce 100% consistent vocabulary across all files.
   - **Autonomous Term Discovery**: AI autonomously detects important game mechanics/items/locations during translation, extracts them into `new_terms`, and immediately records them to `project.db`. Newly learned terms are dynamically refreshed across subsequent batches in real time.
   - **On-Demand AI Dialogue Scan**: A dedicated "Pindai Dialog AI" tool in the Glossary manager scans the current file's dialogues to extract and pre-populate key terms before or during translation.
   - Pre-seeded with official Pokémon SV terms (`Vending Machine`, `TM Machine`, `Poké Ball`, `Pokémon Center`, `Pokédex`, `Gym Leader`, `Tera Type`, `Terastal`, dll.).
   - Full GUI manager ([`gui/dialogs/glossary_dialog.py`](file:///E:/Modding/SwitchModStudio/gui/dialogs/glossary_dialog.py)) accessible via the toolbar (`Icons.GLOSSARY` "Kamus Istilah") to add, edit, search, and delete custom terms per project.

---

## 🏗️ 2. Architecture & Tech Stack

- **Runtime & OS**: Python 3.10+ on Windows 11 (`win32`).
- **GUI Toolkit**: Tkinter & `ttk` (Native Windows aesthetics, high DPI compatible).
- **Icons**: Centralized vector glyphs from Windows `Segoe Fluent Icons` / `Segoe MDL2 Assets` via [`core/icons.py`](file:///E:/Modding/SwitchModStudio/core/icons.py).
- **Database**: Local SQLite project storage ([`core/db_manager.py`](file:///E:/Modding/SwitchModStudio/core/db_manager.py)) located at `workspace/PokemonScarlet_0100A3D008C5C000/project.db`.
- **Logging**: Rotating file logger ([`core/logger.py`](file:///E:/Modding/SwitchModStudio/core/logger.py)) outputting to `studio.log`.

---

## ⚠️ 3. Strict Rules & User Constraints (CRITICAL)

When maintaining or extending this codebase, **always adhere to the following rules**:

### 🚫 1. No Cartoon Emojis (Vector Segoe Icons Only)
- **NEVER** use cartoon Unicode emojis (e.g. ⚙️, 📁, 🟢, ❌, ✅, 🤖, 🚀, 💾) anywhere in UI labels, buttons, dialogs, or messages.
- **ALWAYS** use the glyph constants defined in [`core/icons.py`](file:///E:/Modding/SwitchModStudio/core/icons.py):
  - `Icons.FOLDER`, `Icons.SAVE`, `Icons.UNDO`, `Icons.REDO`, `Icons.EXPORT`, `Icons.IMPORT`
  - `Icons.AI_SPARKLE`, `Icons.AI_BOT`, `Icons.DEPLOY`, `Icons.PACKAGE`, `Icons.SETTINGS`, `Icons.SYNC`
  - `Icons.ACCEPT` (`\uE73E`), `Icons.DISCARD` (`\uE711`), `Icons.SEARCH` (`\uE721`)
  - `Icons.PREV`, `Icons.NEXT`, `Icons.UP`, `Icons.DOWN`
  - `Icons.STATUS_DONE` (`\uE73E`), `Icons.STATUS_TODO` (`\uEA3A`), `Icons.EDIT` (`\uE70F`)

### 🔘 2. Binary File Status Only ("Sudah" vs "Belum")
- The user explicitly requested **only 2 statuses**:
  - `Sudah` (`completed`)
  - `Belum` (`untranslated`)
- Represented in the UI as a simple **Checkbutton** (`self.status_chk`), NOT a dropdown combobox.
- Do NOT reintroduce "Sedang Dikerjakan", "Otomatis", or "Manual" statuses.

### 📐 3. Table Column Layout
- Column `trans_text` (Bahasa Indonesia) must have `stretch=True` so it anchors cleanly to the right edge and fills available panel width.
- Column `accept` is a narrow action column (width 35px) for clickable per-line review checkmarks.

### 🛡️ 4. AI Staging & Auto-Save
- AI translations must go into `self.pending_ai_diffs` first.
- The table displays pending diffs with green backgrounds (`diff_pending_even`, `diff_pending_odd`).
- Auto-save **must never run automatically on raw AI output**; it only triggers when the user clicks `Icons.ACCEPT`, **Accept All**, or manually saves an edited line.

### 💻 5. Windows Shell Commands & Terminal Encoding
- Always prefix shell commands with `rtk` (e.g. `rtk python -m unittest discover tests`).
- Windows PowerShell stdout uses `cp1252` encoding by default. Printing raw unicode characters outside cp1252 directly to `print()` in scratch scripts will trigger `UnicodeEncodeError`. Always use `.encode('ascii', 'backslashreplace')` or `repr()` when printing unicode in terminal one-liners.

### 🔒 6. Security & Secrets Isolation (.env vs .env.example)
- **NEVER** hardcode or commit API keys, private endpoints, or local computer paths to Git or config JSON files.
- Local secrets and paths MUST be placed in `.env` (ignored by `.gitignore`).
- The repository only tracks `.env.example` as a template with blank placeholder values.
- `EnvManager` (`core/env_manager.py`) automatically injects `.env` variables into `os.environ` and overrides default settings safely.

---

## 📂 4. Project Directory Map

```
SwitchModStudio/
├── AGENTS.md                   # This instruction guide for AI agents
├── README.md                   # Human-readable user manual
├── main.py                     # App entry point (launches ClassicDATStudioApp)
├── run_studio.bat              # Windows batch file shortcut to launch the app
├── studio.log                  # Live diagnostic logging
│
├── config/
│   ├── settings.json           # User configurations (AI keys, endpoints, load paths)
│   └── game_profiles.json      # Supported game Title IDs and paths
│
├── core/
│   ├── icons.py                # Centralized Windows Segoe Fluent Icons pack
│   ├── asset_classifier.py     # Multi-asset detector & category filter
│   ├── trpfs_client.py         # Client for TrpfsWorker daemon (RomFS direct reader)
│   ├── syntax_highlighter.py   # Dialogue Syntax Highlighter for game tokens
│   ├── tag_guard.py            # Token extraction, sanitization, and tag validation
│   ├── db_manager.py           # SQLite project DB manager (project.db)
│   ├── status_tracker.py       # Translation progress calculator (Sudah / Belum)
│   ├── universal_ai.py         # Multi-provider REST AI client (OpenAI, Claude, Gemini)
│   ├── emu_detector.py         # Emulator auto-detection (Eden, Ryujinx, Yuzu)
│   └── logger.py               # Centralized logging subsystem
│
├── formats/
│   ├── base_codec.py           # Abstract base class for text codecs
│   └── pokemon_dat.py          # Flat/Trinity rolling XOR binary .dat codec
│
├── gui/
│   ├── app_window.py           # Main application window (ClassicDATStudioApp)
│   └── viewers/
│       └── texture_viewer.py   # Side-by-side Texture comparison & editing workspace
│
├── tools/
│   └── TrpfsWorker/            # Headless .NET 8 CLI daemon for RomFS parsing & extraction
│
├── tests/
│   ├── test_ai_diff_review.py     # Unit tests for Git Diff staging & auto-save
│   ├── test_syntax_highlighter.py # Unit tests for syntax highlighter & Live Inspector
│   ├── test_asset_classifier.py   # Unit tests for asset extension classification
│   ├── test_texture_viewer.py     # Unit tests for texture comparison & workspace switching
│   ├── test_trpfs_client.py       # Unit tests for TrpfsWorker IPC & RomFS extraction
│   └── test_romfs_integration.py  # Unit tests for GUI RomFS routing & virtual files
│
└── workspace/
    └── PokemonScarlet_.../     # Active project workspace with project.db
```

---

## 🎨 5. Dialogue Syntax Highlighting Reference

Pokémon Scarlet and Trinity engine text files contain specific game tokens:

| Token Type | Example Pattern | Foreground | Background Badge | Meaning |
|---|---|---|---|---|
| **Variables** | `[VAR PKNAME(0000)]`, `[VAR COLOR(0001)]` | `#6A1B9A` (Purple) | `#F3E5F5` (Lavender) | Player names, Pokémon, items, numbers |
| **Escapes** | `\n`, `\r`, `\c`, `\f`, `\t` | `#D84315` (Tangerine) | `#FBE9E7` (Peach) | Literal line breaks, box clears |
| **Timing / Wait** | `[WAIT 30]`, `[~ 1]` | `#00695C` (Teal) | `#E0F2F1` (Mint) | Dialogue pauses, sound triggers |
| **Generic Tags** | `[...]` | `#1565C0` (Blue) | `#E3F2FD` (Sky Blue) | Engine markers |
| **Malformed Tag** | `[VAR PKNAME...` (unclosed) | `#C62828` (Crimson) | `#FFCDD2` (Red) | Syntax error in dialogue |

### Usage:
```python
from core.syntax_highlighter import DialogueSyntaxHighlighter

# Configure text widget
DialogueSyntaxHighlighter.configure_tags(text_widget)

# Set content with syntax highlighting applied
DialogueSyntaxHighlighter.set_text_with_highlight(text_widget, text, editable=False)

# Enable live highlighting during user typing
DialogueSyntaxHighlighter.bind_live_highlighting(trans_box)
```

---

## 🧪 6. Testing & Quality Assurance

Always verify your changes before reporting completion to the user.

### Run All Unit Tests:
```powershell
rtk python -m unittest discover tests
```

### Run Specific Test Suites:
```powershell
rtk python -m unittest tests/test_syntax_highlighter.py
rtk python -m unittest tests/test_ai_diff_review.py
rtk python -m unittest tests/test_asset_classifier.py
rtk python -m unittest tests/test_texture_viewer.py
rtk python -m unittest tests/test_trpfs_client.py
rtk python -m unittest tests/test_romfs_integration.py
```

### Syntax & Compilation Check:
```powershell
rtk python -m py_compile main.py gui/app_window.py core/syntax_highlighter.py core/icons.py
```

### Headless GUI Smoke Test:
```powershell
rtk python -c "from gui.app_window import ClassicDATStudioApp; app = ClassicDATStudioApp(); app.destroy(); print('App initializes cleanly!')"
```

---

## 💡 7. Developer Quick Tips

1. **Table vs. Text Widgets**: `ttk.Treeview` cannot render rich text spans inside individual table cells. This is why the **Live Dialogue Inspector** (`self.inspector_frame`) exists at the bottom pane of the table to provide immediate, rich, syntax-highlighted previews when any row is selected.
2. **Keyboard Productivity**:
   - `Enter` on table row: Opens edit dialog for the selected line.
   - `Ctrl + Enter` in edit dialog: Saves changes and sanitizes tags.
   - `Escape` in edit dialog: Closes dialog without saving.
   - `Ctrl + Z` / `Ctrl + Y` in main window: Undo / Redo line changes.
3. **Database Integrity**: Never manually delete tables in `project.db`. Use [`ProjectDB`](file:///E:/Modding/SwitchModStudio/core/db_manager.py) methods to query and update file records.
