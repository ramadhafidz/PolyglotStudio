import json
import urllib.request
import urllib.error
import time
from typing import List, Dict, Any, Optional

class GeminiTranslator:
    """
    Direct connector to Google Gemini REST API using native urllib.
    No heavy pip packages needed.
    """

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def set_model(self, model: str):
        self.model = model

    def translate_lines(self, lines: List[str], target_lang: str = "Indonesian") -> List[str]:
        if not self.api_key:
            raise ValueError("Gemini API Key belum diatur! Masukkan API Key di pengaturan.")

        if not lines:
            return []

        # Prepare payload
        system_instruction = (
            f"You are a professional video game localizer specializing in Nintendo games. "
            f"Translate the following game dialogue lines from English into natural, engaging {target_lang}. "
            f"CRITICAL RULES:\n"
            f"1. You MUST preserve all engine control tags and variables EXACTLY as they appear: "
            f"e.g. [VAR TRNAME], [VAR PKNAME], [VAR 0114(0009)], [WAIT 10], [~ 14], \\n, \\r, \\c.\n"
            f"2. Do NOT translate or modify tag names or hexadecimal codes inside brackets.\n"
            f"3. Return EXACTLY the same number of lines as provided ({len(lines)} lines).\n"
            f"4. Output format MUST be a valid JSON array of strings containing the translated lines, with no markdown codeblocks or extra commentary."
        )

        user_content = json.dumps(lines, ensure_ascii=False)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        request_body = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instruction},
                        {"text": f"Translate these lines into {target_lang}:\n{user_content}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json"
            }
        }

        req_data = json.dumps(request_body).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                res_bytes = response.read()
                res_json = json.loads(res_bytes.decode('utf-8'))

                candidate_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                translated_array = json.loads(candidate_text)

                if isinstance(translated_array, list) and len(translated_array) == len(lines):
                    return [str(x) for x in translated_array]
                elif isinstance(translated_array, list):
                    # Pad or trim if slight mismatch
                    if len(translated_array) < len(lines):
                        translated_array.extend(lines[len(translated_array):])
                    return [str(x) for x in translated_array[:len(lines)]]
                else:
                    raise ValueError("Format respon AI bukan berupa array teks JSON.")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode('utf-8')
            raise RuntimeError(f"Gemini API Error ({e.code}): {err_msg}")
        except Exception as e:
            raise RuntimeError(f"Gagal menerjemahkan dengan AI: {str(e)}")
