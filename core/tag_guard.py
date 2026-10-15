import re
from typing import List, Tuple, Dict, Any

class TagGuard:
    """
    Validates and preserves Game Freak engine control tokens and variables.
    Tags: [VAR ...], [WAIT ...], [~ ...], \\n, \\r, \\c
    """

    TAG_PATTERN = re.compile(r'(\[VAR [^\]]+\]|\[WAIT \d+\]|\[~ \d+\]|\\n|\\r|\\c)')

    @classmethod
    def extract_tags(cls, text: str) -> List[str]:
        return cls.TAG_PATTERN.findall(text)

    @classmethod
    def sanitize_line(cls, original: str, translated: str) -> str:
        r"""
        Sanitizes and repairs game engine control tokens in a translated line:
        1. Normalizes raw unescaped newlines (\r\n, \n) into literal '\n'
        2. Normalizes raw unescaped carriage returns (\r) into literal '\r'
        3. Fixes forward slash typos (/n, /r, /c) to backslash tokens
        4. Restores trailing control tokens (\r or \c) from original if dropped
        5. Preserves [WAIT ...] and [~ ...] engine tokens
        """
        if not translated:
            return translated

        # 1. Convert raw newline and carriage return characters to literal tokens
        # In JSON/LLM responses, \n often gets decoded into ASCII 10 (newline) and \r into ASCII 13
        trans = translated.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\r')

        # 2. Fix forward slash typos if original had backslash tokens
        if '\\n' in original and '/n' in trans:
            trans = trans.replace('/n', '\\n')
        if '\\r' in original and '/r' in trans:
            trans = trans.replace('/r', '\\r')
        if '\\c' in original and '/c' in trans:
            trans = trans.replace('/c', '\\c')

        # 3. Ensure trailing control tokens (\r or \c) are preserved from original
        orig_clean = original.rstrip()
        trans_clean = trans.rstrip()
        if orig_clean.endswith('\\r') and not trans_clean.endswith('\\r'):
            trans = trans_clean + '\\r'
        elif orig_clean.endswith('\\c') and not trans_clean.endswith('\\c'):
            trans = trans_clean + '\\c'

        # 4. Check for dropped [WAIT ...] or [~ ...] tokens
        orig_tags = cls.extract_tags(original)
        trans_tags = cls.extract_tags(trans)
        for tag in orig_tags:
            if tag.startswith("[WAIT") or tag.startswith("[~"):
                if tag not in trans_tags:
                    if original.startswith(tag) and not trans.startswith(tag):
                        trans = tag + trans
                    elif original.endswith(tag) and not trans.endswith(tag):
                        trans = trans + tag

        return trans

    @classmethod
    def validate_line(cls, original: str, translated: str) -> Tuple[bool, str]:
        orig_tags = cls.extract_tags(original)
        trans_tags = cls.extract_tags(translated)

        if orig_tags != trans_tags:
            return False, f"Tag mismatch! Expected {orig_tags}, found {trans_tags}"
        return True, ""

    @classmethod
    def validate_file(cls, orig_lines: List[str], trans_lines: List[str]) -> Tuple[bool, List[str]]:
        errors = []
        if len(orig_lines) != len(trans_lines):
            errors.append(f"Line count mismatch: Original has {len(orig_lines)} lines, translated has {len(trans_lines)} lines.")
            return False, errors

        for idx, (orig, trans) in enumerate(zip(orig_lines, trans_lines)):
            valid, err = cls.validate_line(orig, trans)
            if not valid:
                errors.append(f"Line {idx}: {err}")

        return len(errors) == 0, errors
