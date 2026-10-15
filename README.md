# 🌐 Polyglot Studio

**Polyglot Studio** adalah Integrated Development Environment (IDE) modern berkinerja tinggi yang dirancang khusus untuk membedah, melokalisasi (menerjemahkan), dan memodifikasi game Nintendo Switch. 

Saat ini Polyglot Studio dikonfigurasi dan aktif digunakan untuk proyek lokalisasi **Pokémon Scarlet & Violet** (`Title ID: 0100A3D008C5C000`) ke Bahasa Indonesia.

---

## ✨ Fitur Utama

### 1. 🔍 Zero-Dependency RomFS Virtual Explorer
* **Eksplorasi Virtual On-Demand**: Membaca arsip RomFS langsung dari dump game tanpa perlu mengekstrak ratusan ribu file ke harddisk terlebih dahulu.
* **Backend TrpfsWorker Berkecepatan Tinggi**: Menggunakan worker headless .NET 8 dengan dekompresi Oodle Kraken (`oo2core_8_win64.dll`) yang mengurai deskriptor FlatBuffers Trinity (`arc/data.trpfd` & `arc/data.trpfs`) dalam hitungan milidetik.
* **Ekstraksi In-Memory (< 3ms)**: File biner `.dat` diekstrak langsung ke memori codec Python tanpa meninggalkan sampah file sementara. Tidak lagi bergantung pada antarmuka WinForms `TrinityFileExplorer.exe`.

### 2. 🤖 Universal AI Localization Engine
* **Multi-Provider REST Support**: Terintegrasi langsung dengan penyedia AI terkemuka:
  * **OpenAI Compatible**: OpenAI, DeepSeek, Ollama, OpenRouter, LM Studio, vLLM, Groq.
  * **Anthropic**: Claude 3.5 Sonnet, Claude 3 Opus/Haiku.
  * **Google**: Gemini 2.0 Flash / Gemini Pro.
* **Automatic Chunking & Batching (20 Baris/Request)**: File dialog berukuran ratusan baris (seperti 458 baris) otomatis dipecah bertahap agar tidak mengalami *read timeout* dan mencegah halusinasi model.
* **Auto-Retry & Anti Rate-Limit**: Otomatis mencoba ulang hingga 3x dengan backoff delay jika terjadi fluktuasi koneksi atau rate limit proxy.
* **Live Progress Counter**: Pemantauan progres penerjemahan secara visual dan real-time di antarmuka.

### 3. 🧠 Autonomous Glossary & Consistency Memory
* **Database Glosarium Persisten**: Menyimpan kamus istilah baku per proyek dalam SQLite (`project.db`).
* **Pre-Seeded Pokémon SV Terminology**: Sudah dilengkapi istilah baku resmi Pokémon:
  * `Vending Machine` → **`Vending Machine`**
  * `TM Machine` → **`TM Machine`**
  * `Poké Ball`, `Pokémon Center`, `Pokédex`, `Gym Leader`, `Tera Type`, `Terastal`, dll.
* **Autonomous Term Learning**: AI secara otomatis mengenali istilah khas baru saat menerjemahkan dialog dan langsung mencatatnya ke kamus permanen.
* **Dynamic Memory Refresh**: Setiap istilah baru yang dipelajari di Batch 1 langsung diinjeksikan sebagai aturan wajib untuk Batch 2 dan file-file berikutnya.
* **On-Demand AI Dialogue Scan**: Tersedia tombol pemindai AI di menu Kamus Istilah untuk menganalisis dan mengekstrak seluruh kosakata kunci dari file yang sedang terbuka.

### 4. 🌿 Git Diff Review Staging System
* **Pratinjau Diff Berwarna Hijau**: Terjemahan AI tidak langsung menimpa data asli, melainkan masuk ke mode *staging* dengan penanda hijau layaknya Git Diff (`#E6FFEC`).
* **Kontrol Translator Penuh**: Setujui hasil per baris dengan tombol centang (`✓`), atau gunakan tombol **Accept All** / **Discard All**.
* **Proteksi Auto-Save**: Fitur simpan otomatis hanya berjalan setelah Anda menyetujui terjemahan, menjaga integritas naskah game.

### 5. 🛡️ Token Guardian (TagGuard) & Syntax Highlighting
* **Proteksi Mutlak Kode Game Freak**: Modul `TagGuard` mengawal seluruh variabel engine (`[VAR TRNAME]`, `[VAR PKNAME]`, `[WAIT 10]`, `\n`, `\r`, `\c`). Jika AI keliru mengubah tag, sistem otomatis memulihkan tag asli sebelum disimpan.
* **Pill-Style Syntax Highlighter**: Pewarnaan kode interaktif di Live Dialogue Inspector dan Edit Dialog untuk membedakan teks dialog biasa dengan variabel kontrol engine.

### 6. 🎨 Multi-Asset Localization Workspace
* **Kategorisasi Aset Otomatis**: Memfilter berkas proyek berdasarkan tipe aset:
  * Teks Dialog (`.dat`, `.txt`, `.json`)
  * Tekstur & Gambar (`.png`, `.dds`, `.bntx`, `.tga`)
  * Font & Tipografi (`.ttf`, `.otf`, `.bffnt`)
  * Audio & Suara (`.wav`, `.bwav`, `.bfwav`, `.mp3`)
* **Texture Comparison Viewer**: Penampil tekstur berdampingan (Original vs Translated) dengan kontrol zoom (25% - 400%), alpha checkerboard transparan, dan tombol peluncur editor gambar eksternal (Photoshop/GIMP/Aseprite).

### 7. 🚀 One-Click Eden Mod Deployment & Manager
* **Direct Compilation & Hot Deploy**: Mengompilasi format binary rolling XOR Flat/Trinity `.dat` dan langsung menaruhnya ke direktori load mod emulator **Eden** (`0100A3D008C5C000`).
* **Mod Manager Terpadu**: Mengaktifkan dan menonaktifkan mod (*Toggle On/Off*) yang terpasang dengan satu klik tanpa perlu menghapus berkas.

---

## 💻 Cara Menjalankan

### Cara 1: Shortcut Windows (Paling Mudah)
Cukup klik ganda berkas batch shortcut:
```text
run_studio.bat
```

### Cara 2: Terminal / PowerShell
```powershell
cd E:\Modding\SwitchModStudio
python main.py
```

---

## ⌨️ Pintasan Keyboard (Shortcuts)

| Shortcut | Aksi |
|---|---|
| `Ctrl + S` | Simpan file dialog `.dat` saat ini |
| `Ctrl + Z` | Undo perubahan terjemahan |
| `Ctrl + Y` / `Ctrl + Shift + Z` | Redo perubahan terjemahan |
| `Enter` (pada tabel) | Buka dialog edit baris dialog |

---

## 📂 Struktur Direktori Proyek

```text
SwitchModStudio/
├── run_studio.bat              # Shortcut peluncur aplikasi
├── main.py                     # Entry point Polyglot Studio
├── AGENTS.md                   # Panduan arsitektur untuk AI Agent
├── README.md                   # Dokumentasi resmi aplikasi
├── studio.log                  # Log diagnostik runtime aplikasi
│
├── config/
│   ├── settings.json           # Konfigurasi AI endpoint, key, model, dan path
│   └── game_profiles.json      # Profil game Title ID dan path emulator
│
├── core/
│   ├── asset_classifier.py     # Klasifikasi tipe aset game (Text, Texture, Audio, dll.)
│   ├── db_manager.py           # Database SQLite (project.db, status berkas, glosarium)
│   ├── emu_detector.py         # Detektor otomatis emulator Eden, Ryujinx, Yuzu
│   ├── icons.py                # Ikon vektor Segoe Fluent Icons (bebas emoji)
│   ├── logger.py               # Rotating file logging
│   ├── status_tracker.py       # Pelacak status berkas (Sudah / Belum)
│   ├── syntax_highlighter.py   # Syntax highlighter kontrol tag dialog
│   ├── tag_guard.py            # Validator & pelindung tag variabel Game Freak
│   ├── trpfs_client.py         # Klien IPC penghubung ke worker RomFS
│   └── universal_ai.py         # AI localization engine (OpenAI, Claude, Gemini, Glossary)
│
├── formats/
│   └── pokemon_dat.py          # Enkoder & dekoder rolling XOR Flat/Trinity .dat
│
├── gui/
│   ├── app_window.py           # Jendela utama Polyglot Studio
│   ├── dialogs/
│   │   └── glossary_dialog.py  # Dialog manajemen Kamus Istilah (Glossary)
│   └── viewers/
│       └── texture_viewer.py   # Viewer tekstur grafis berdampingan
│
├── tools/
│   └── TrpfsWorker/            # Backend .NET 8 headless parser RomFS Trinity
│
└── workspace/
    └── PokemonScarlet_0100A3D008C5C000/
        ├── project.db          # Database SQLite proyek & memori glosarium
        └── assets/             # Direktori modifikasi aset grafis/tekstur
```

---

## 📜 Lisensi & Etika
Aplikasi ini dikembangkan untuk tujuan pelestarian karya dan lokalisasi komunitas (fan translation). Seluruh aset asli permainan tetap merupakan hak cipta dari Nintendo, Game Freak, dan The Pokémon Company.
