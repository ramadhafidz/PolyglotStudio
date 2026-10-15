import json
import urllib.request
import urllib.error
import re
import time
from typing import List, Dict, Any, Optional, Tuple, Callable
from core.tag_guard import TagGuard

class UniversalAIClient:
    """
    Universal AI Client supporting:
    1. OpenAI Compatible (OpenAI, DeepSeek, Ollama, OpenRouter, LM Studio, vLLM, Groq, etc.)
    2. Anthropic Compatible (Claude 3.5 Sonnet, Haiku, Opus, or Anthropic-compatible proxies)
    3. Google / Gemini (Google AI Studio REST API)
    """

    DEFAULT_PROMPT = (
        "You are an expert video game localizer specializing in Nintendo and Pokémon games.\n"
        "Translate the provided dialogue lines into natural, fluid, conversational Indonesian "
        "(Bahasa Indonesia sehari-hari yang luwes, hidup, dan tidak kaku).\n\n"
        "GAYA BAHASA & KETENTUAN ISTILAH:\n"
        "1. Gaya Bicara: Gunakan bahasa Indonesia percakapan yang alami dan ekspresif layaknya di anime/game Pokémon resmi. "
        "Hindari kalimat kaku atau terlalu baku seperti buku teks formal.\n"
        "2. Aturan Kata Ganti: JANGAN SEKALI-KALI menggunakan kata gaul Jakarta seperti 'Lu', 'Gua', 'Lo', 'Gue'. "
        "Gunakan kata ganti yang luwes dan ramah seperti 'kamu', 'aku', 'kita', atau akhiran '-mu' dan '-ku'.\n"
        "3. Istilah Khas Pokémon (DILARANG DITERJEMAHKAN):\n"
        "   Pertahankan istilah-istilah ikonik Pokémon dalam bentuk aslinya:\n"
        "   - Pokémon, Poké Ball, Poke Ball, Great Ball, Ultra Ball, Master Ball, dll.\n"
        "   - Pokémon Center, Poke Center, Pokédex\n"
        "   - Gym, Gym Leader, Gym Badge\n"
        "   - Partner (partner Pokémon), Pokémon Trainer, Trainer\n"
        "   - Battle, Pokémon Battle, Champion, Elite Four, Team Star\n"
        "   - Nama-nama spesies Pokémon (Pikachu, Koraidon, Miraidon, dll.)\n"
        "   - Nama Item, Ability, dan Jurus penting tetap gunakan istilah resminya.\n"
        "4. Pencatatan Istilah Baru (Auto-Glossary):\n"
        "   Jika menemukan istilah penting khas game/fitur/tempat/item (seperti 'Vending Machine', 'TM Machine', 'Sandwich', 'Tera Raid', dll.) yang BELUM ada di KAMUS ISTILAH WAJIB, "
        "cantumkan di properti 'new_terms' beserta padanan bakunya agar dapat diingat permanen.\n\n"
        "ATURAN ENGINE GAME FREAK (SANGAT KRUSIAL):\n"
        "1. Wajib menjaga seluruh tag kontrol engine dan variabel PERSIS seperti aslinya tanpa diubah sedikit pun: "
        "contoh: [VAR TRNAME], [VAR PKNAME], [VAR 0114(...)], [WAIT 10], [~ 14], \\n, \\r, \\c.\n"
        "2. JANGAN MENGUBAH '\\n' MENJADI ENTER/BARIS BARU. Tetap tuliskan sebagai dua karakter '\\' dan 'n' (literal \\n).\n"
        "3. JANGAN MENGHILANGKAN '\\r' ATAU '\\c' DI AKHIR KALIMAT. Jika kalimat asli berakhiran '\\r' atau '\\c', hasil terjemahan WAJIB diakhiri '\\r' atau '\\c'.\n"
        "4. JANGAN gunakan garis miring depan seperti '/n' atau '/r'. Selalu gunakan backslash '\\n' dan '\\r'.\n"
        "5. Jangan ubah kurung siku, spasi dalam tag, atau kode heksadesimal.\n"
        "6. Jumlah Baris: Kembalikan TEPAT jumlah baris yang sama dengan input ({line_count} baris).\n"
        "7. Format Output: Output berupa JSON valid dengan format:\n"
        '{\n  "translations": ["baris 1", "baris 2", ...],\n  "new_terms": [{"en": "Term", "id": "Terjemahan", "category": "game_term"}]\n}\n'
        'atau JSON array string langsung: ["baris 1", "baris 2", ...]. Dilarang menyertakan komentar tambahan atau markdown code fence.'
    )

    PROVIDERS = {
        "openai": {
            "name": "OpenAI Compatible (OpenAI, DeepSeek, Ollama, OpenRouter, LM Studio)",
            "default_endpoint": "https://api.openai.com/v1",
            "default_model": "gpt-4o-mini"
        },
        "anthropic": {
            "name": "Anthropic (Claude)",
            "default_endpoint": "https://api.anthropic.com/v1",
            "default_model": "claude-3-5-sonnet-20241022"
        },
        "google": {
            "name": "Google (Gemini)",
            "default_endpoint": "https://generativelanguage.googleapis.com/v1beta",
            "default_model": "gemini-2.0-flash"
        }
    }

    def __init__(self, provider: str = "openai", endpoint: str = "", api_key: str = "", model: str = "", custom_prompt: str = ""):
        self.provider = provider.lower() if provider else "openai"
        self.endpoint = endpoint.rstrip("/") if endpoint else self.PROVIDERS.get(self.provider, {}).get("default_endpoint", "https://api.openai.com/v1")
        self.api_key = api_key
        self.model = model if model else self.PROVIDERS.get(self.provider, {}).get("default_model", "gpt-4o-mini")
        self.custom_prompt = custom_prompt

    def update_config(self, provider: str, endpoint: str, api_key: str, model: str, custom_prompt: str = ""):
        self.provider = provider.lower()
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.custom_prompt = custom_prompt.strip()

    def get_system_prompt(self, line_count: int, target_lang: str, glossary_block: str = "") -> str:
        base_prompt = self.custom_prompt if self.custom_prompt else self.DEFAULT_PROMPT
        prompt = base_prompt.replace("{target_lang}", target_lang).replace("{line_count}", str(line_count))
        
        # Inject glossary terminology block if available
        if glossary_block:
            prompt += "\n\n" + glossary_block

        # Enforce JSON rule if missing in custom prompt
        if "JSON array" not in prompt and "translations" not in prompt:
            prompt += f"\n\nCRITICAL: Return output ONLY as valid JSON containing exactly {line_count} elements in 'translations' or direct JSON array."
        return prompt

    def translate_lines(
        self, 
        lines: List[str], 
        target_lang: str = "Indonesian",
        batch_size: int = 20,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        glossary_block: str = "",
        on_new_terms: Optional[Callable[[List[Dict[str, str]]], None]] = None,
        get_fresh_glossary_block: Optional[Callable[[], str]] = None
    ) -> List[str]:
        if not lines:
            return []

        is_local = "localhost" in self.endpoint or "127.0.0.1" in self.endpoint
        if not is_local and not self.api_key:
            raise ValueError(f"API Key untuk provider '{self.provider}' belum diisi! Silakan atur di menu Pengaturan.")

        if batch_size <= 0:
            batch_size = 20

        total = len(lines)
        if total <= batch_size:
            ret = self._translate_batch(lines, target_lang, glossary_block=glossary_block)
            if isinstance(ret, tuple) and len(ret) == 2:
                result, new_terms = ret
            else:
                result, new_terms = ret, []

            if new_terms and on_new_terms:
                on_new_terms(new_terms)

            if progress_callback:
                progress_callback(total, total)
            return result

        all_results: List[str] = []
        cur_glossary_block = glossary_block
        for i in range(0, total, batch_size):
            batch = lines[i:i + batch_size]
            ret = self._translate_batch(batch, target_lang, glossary_block=cur_glossary_block)
            if isinstance(ret, tuple) and len(ret) == 2:
                batch_res, new_terms = ret
            else:
                batch_res, new_terms = ret, []

            if new_terms and on_new_terms:
                on_new_terms(new_terms)
                if get_fresh_glossary_block:
                    try:
                        cur_glossary_block = get_fresh_glossary_block()
                    except Exception:
                        pass

            all_results.extend(batch_res)
            if progress_callback:
                progress_callback(len(all_results), total)
            if i + batch_size < total:
                time.sleep(0.15)  # brief polite pacing between batches

        return all_results

    def _translate_batch(
        self, 
        batch_lines: List[str], 
        target_lang: str, 
        retries: int = 3, 
        glossary_block: str = ""
    ) -> Tuple[List[str], List[Dict[str, str]]]:
        if not batch_lines:
            return [], []

        system_instruction = self.get_system_prompt(len(batch_lines), target_lang, glossary_block=glossary_block)
        user_content = json.dumps(batch_lines, ensure_ascii=False)

        last_err = None
        for attempt in range(1, retries + 1):
            try:
                if self.provider == "anthropic":
                    raw_response = self._call_anthropic(system_instruction, user_content)
                elif self.provider == "google":
                    raw_response = self._call_google(system_instruction, user_content)
                else:
                    raw_response = self._call_openai(system_instruction, user_content)

                return self._parse_json_response(raw_response, batch_lines)
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.5 * attempt)

        raise RuntimeError(f"Gagal menerjemahkan batch dialog setelah {retries}x percobaan ({last_err})")

    def _call_openai(self, system_instruction: str, user_content: str, timeout: int = 180) -> str:
        base = self.endpoint.rstrip("/")
        if base.endswith("/chat/completions"):
            url = base
        else:
            url = f"{base}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Translate these dialogue lines:\n{user_content}"}
            ],
            "temperature": 0.3
        }

        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers, 
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI Endpoint Error ({e.code}): {err}")
        except Exception as e:
            raise RuntimeError(f"OpenAI Request Error: {str(e)}")

    def _call_anthropic(self, system_instruction: str, user_content: str, timeout: int = 180) -> str:
        base = self.endpoint.rstrip("/")
        if base.endswith("/messages"):
            url = base
        else:
            url = f"{base}/messages"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system_instruction,
            "messages": [
                {"role": "user", "content": f"Translate these dialogue lines:\n{user_content}"}
            ],
            "temperature": 0.3
        }

        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers, 
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"]
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Anthropic Endpoint Error ({e.code}): {err}")
        except Exception as e:
            raise RuntimeError(f"Anthropic Request Error: {str(e)}")

    def _call_google(self, system_instruction: str, user_content: str, timeout: int = 180) -> str:
        base = self.endpoint.rstrip("/")
        url = f"{base}/models/{self.model}:generateContent?key={self.api_key}"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {"text": f"Translate these dialogue lines:\n{user_content}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }

        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers, 
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Google Endpoint Error ({e.code}): {err}")
        except Exception as e:
            raise RuntimeError(f"Google Request Error: {str(e)}")

    def _robust_json_loads(self, text: str) -> Any:
        """
        Parses JSON with automatic targeted repair of invalid escape sequences.
        Game Freak control codes like \\c, \\[, \\], \\s, etc. are invalid in JSON.
        If json.loads encounters 'Invalid \\escape', this repairs that specific backslash
        and retries until all invalid escapes are normalized.
        """
        cur = text
        for _ in range(100):
            try:
                return json.loads(cur, strict=False)
            except json.JSONDecodeError as e:
                if "Invalid \\escape" in e.msg:
                    pos = e.pos
                    cur = cur[:pos] + "\\" + cur[pos:]
                else:
                    break
        return json.loads(cur, strict=False)

    def _parse_json_response(self, raw_text: str, original_lines: List[str]) -> Tuple[List[str], List[Dict[str, str]]]:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

        parsed_list = None
        new_terms = []

        try:
            data = self._robust_json_loads(cleaned)
            if isinstance(data, dict):
                # Handle {"translations": [...], "new_terms": [...]}
                if "translations" in data and isinstance(data["translations"], list):
                    parsed_list = [str(x) for x in data["translations"]]
                else:
                    for val in data.values():
                        if isinstance(val, list):
                            parsed_list = [str(x) for x in val]
                            break

                # Extract newly discovered terms if provided
                raw_terms = data.get("new_terms", [])
                if isinstance(raw_terms, list):
                    for item in raw_terms:
                        if isinstance(item, dict):
                            en = item.get("en") or item.get("term_en")
                            id_val = item.get("id") or item.get("term_id")
                            cat = item.get("category", "game_term")
                            notes = item.get("notes", "Otomatis dipelajari AI saat menerjemahkan")
                            if en and id_val and str(en).strip() and str(id_val).strip():
                                new_terms.append({
                                    "term_en": str(en).strip(),
                                    "term_id": str(id_val).strip(),
                                    "category": str(cat).strip(),
                                    "notes": str(notes).strip()
                                })
            elif isinstance(data, list):
                parsed_list = [str(x) for x in data]
        except Exception:
            pass

        if parsed_list is None:
            # Fallback regex search for JSON object or array
            match_dict = re.search(r'\{[\s\S]*\}', cleaned)
            if match_dict:
                try:
                    data = self._robust_json_loads(match_dict.group(0))
                    if isinstance(data, dict):
                        if "translations" in data and isinstance(data["translations"], list):
                            parsed_list = [str(x) for x in data["translations"]]
                        if "new_terms" in data and isinstance(data["new_terms"], list):
                            for item in data["new_terms"]:
                                if isinstance(item, dict):
                                    en = item.get("en") or item.get("term_en")
                                    id_val = item.get("id") or item.get("term_id")
                                    cat = item.get("category", "game_term")
                                    if en and id_val:
                                        new_terms.append({
                                            "term_en": str(en).strip(),
                                            "term_id": str(id_val).strip(),
                                            "category": str(cat).strip(),
                                            "notes": "Otomatis dipelajari AI saat menerjemahkan"
                                        })
                except Exception:
                    pass

        if parsed_list is None:
            match_arr = re.search(r'\[[\s\S]*\]', cleaned)
            if match_arr:
                try:
                    data = self._robust_json_loads(match_arr.group(0))
                    if isinstance(data, list):
                        parsed_list = [str(x) for x in data]
                except Exception:
                    pass

        if parsed_list is None:
            raise ValueError(f"AI tidak mengembalikan format JSON array yang valid:\n{raw_text[:300]}")

        # Ensure correct list length
        fitted = self._fit_length(parsed_list, original_lines)

        # Sanitize and guard tokens for every line against its original line
        sanitized = []
        for orig, trans in zip(original_lines, fitted):
            sanitized.append(TagGuard.sanitize_line(orig, trans))

        return sanitized, new_terms

    def _parse_json_array(self, raw_text: str, original_lines: List[str]) -> List[str]:
        """Backward compatible helper returning only the sanitized lines list."""
        lines, _ = self._parse_json_response(raw_text, original_lines)
        return lines

    def extract_glossary_terms(
        self, 
        lines: List[str], 
        existing_terms: Optional[List[Dict[str, Any]]] = None,
        target_lang: str = "Indonesian"
    ) -> List[Dict[str, str]]:
        """
        Scans dialogue lines with AI to extract key terms, proper nouns, mechanics,
        and items that should be added to the persistent glossary.
        """
        if not lines:
            return []

        # Filter and sample up to 120 lines
        sample = [l for l in lines if l and not l.strip().startswith("[~")][:120]
        if not sample:
            return []

        existing_str = ""
        if existing_terms:
            existing_str = "\nISTILAH YANG SUDAH TERDAFTAR (JANGAN DIMASUKKAN LAGI):\n"
            for t in existing_terms[:60]:
                existing_str += f"- {t.get('term_en', '')}\n"

        prompt = (
            "You are an expert Pokémon video game localization coordinator.\n"
            f"Analyze the provided dialogue lines and extract all important game-specific terminology, proper nouns, "
            f"features, mechanics, locations, or items that should be standardized into the Indonesian ({target_lang}) glossary.\n\n"
            "KETENTUAN:\n"
            "1. HANYA ambil istilah khas game, nama fitur/mesin, item, jurus, tempat unik, organisasi, atau konsep pertarungan "
            "(misal: 'Vending Machine', 'TM Machine', 'Sandwich', 'Tera Raid', 'Herba Mystica', 'Naranja Academy', dll.).\n"
            "2. JANGAN memasukkan kata-kata percakapan umum sehari-hari (seperti kata kerja biasa atau kata benda umum).\n"
            "3. Berikan padanan baku bahasa Indonesia yang tepat dan alami sesuai standar resmi Pokémon.\n"
            f"{existing_str}\n"
            "FORMAT OUTPUT (STRICT JSON ONLY):\n"
            "Kembalikan HANYA array JSON of objects:\n"
            "[\n"
            '  {"term_en": "English Term", "term_id": "Terjemahan Baku", "category": "game_term/item/location/pokemon", "notes": "konteks singkat"}\n'
            "]\n"
            "Jika tidak ada istilah baru yang ditemukan, kembalikan array kosong []."
        )

        user_content = json.dumps(sample, ensure_ascii=False)
        try:
            if self.provider == "anthropic":
                raw = self._call_anthropic(prompt, user_content)
            elif self.provider == "google":
                raw = self._call_google(prompt, user_content)
            else:
                raw = self._call_openai(prompt, user_content)

            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
                cleaned = cleaned.strip()

            data = self._robust_json_loads(cleaned)
            results = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        en = item.get("term_en") or item.get("en")
                        id_val = item.get("term_id") or item.get("id")
                        cat = item.get("category", "game_term")
                        notes = item.get("notes", "Otomatis dipindai AI dari dialog")
                        if en and id_val and str(en).strip() and str(id_val).strip():
                            results.append({
                                "term_en": str(en).strip(),
                                "term_id": str(id_val).strip(),
                                "category": str(cat).strip(),
                                "notes": str(notes).strip()
                            })
            return results
        except Exception as e:
            return []

    def _fit_length(self, result: List[str], original: List[str]) -> List[str]:
        if len(result) == len(original):
            return result
        elif len(result) < len(original):
            result.extend(original[len(result):])
            return result
        else:
            return result[:len(original)]

    def test_connection(self) -> Tuple[bool, str]:
        try:
            res = self.translate_lines(["Hello world!"], target_lang="Indonesian")
            if res and len(res) > 0:
                return True, f"Koneksi Sukses! Respon: '{res[0]}'"
            return False, "Koneksi berhasil tetapi respon kosong."
        except Exception as e:
            return False, str(e)
