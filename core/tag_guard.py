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
                    else:
                        if trans.endswith('\\r'):
                            trans = trans[:-2] + " " + tag + "\\r"
                        elif trans.endswith('\\c'):
                            trans = trans[:-2] + " " + tag + "\\c"
                        else:
                            trans = trans + " " + tag

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

    @classmethod
    def validate_line_diagnostics(cls, original: str, translated: str, max_line_len: int = 85) -> Dict[str, Any]:
        """
        Detailed QA / Linter diagnostics for a translated dialogue line.
        Checks:
        1. Tag mismatches (missing or corrupted [VAR ...], [WAIT ...], [~ ...])
        2. Control token mismatches (\\n, \\r, \\c)
        3. Raw unescaped enter/newlines (Game Freak expects literal \\n)
        4. Line length warnings (potential UI text overflow on Switch screen)
        5. Auto-repair ability via sanitize_line
        """
        errors: List[str] = []
        warnings: List[str] = []

        orig_tags = cls.extract_tags(original)
        trans_tags = cls.extract_tags(translated)

        # 1. Tag count & identity mismatch
        missing_tags = [t for t in orig_tags if t not in trans_tags]
        extra_tags = [t for t in trans_tags if t not in orig_tags]
        if missing_tags:
            errors.append(f"Tag hilang: {', '.join(missing_tags)}")
        if extra_tags:
            errors.append(f"Tag tidak dikenal: {', '.join(extra_tags)}")

        # 2. Control character endings
        orig_clean = original.rstrip()
        trans_clean = translated.rstrip()
        if orig_clean.endswith('\\r') and not trans_clean.endswith('\\r'):
            errors.append("Hilang kontrol '\\r' di akhir kalimat")
        if orig_clean.endswith('\\c') and not trans_clean.endswith('\\c'):
            errors.append("Hilang kontrol '\\c' di akhir kalimat")

        # 3. Raw newlines check
        if '\n' in translated or '\r' in translated:
            errors.append("Terdapat karakter enter asli (wajib gunakan literal '\\n')")

        # 4. Length warning (stripping control tags for visible text estimation)
        clean_visible = re.sub(r'\[.*?\]|\\n|\\r|\\c', '', translated).strip()
        if len(clean_visible) > max_line_len:
            warnings.append(f"Teks panjang ({len(clean_visible)} karakter) — potensi overflow di layar Switch")

        # 5. Check auto-fix potential
        sanitized = cls.sanitize_line(original, translated)
        can_auto_fix = (sanitized != translated and len(errors) > 0)

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "can_auto_fix": can_auto_fix,
            "fixed_text": sanitized
        }

    @classmethod
    def validate_file_diagnostics(cls, orig_lines: List[str], trans_lines: List[str]) -> Dict[str, Any]:
        """Runs QA diagnostics over all lines in a file, returning per-line errors and summary counts."""
        line_reports: Dict[int, Dict[str, Any]] = {}
        total_errors = 0
        total_warnings = 0

        for idx, (orig, trans) in enumerate(zip(orig_lines, trans_lines)):
            diag = cls.validate_line_diagnostics(orig, trans)
            if not diag["is_valid"] or diag["warnings"]:
                line_reports[idx] = diag
                total_errors += len(diag["errors"])
                total_warnings += len(diag["warnings"])

        return {
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "failed_line_count": len([d for d in line_reports.values() if not d["is_valid"]]),
            "warning_line_count": len([d for d in line_reports.values() if d["warnings"]]),
            "line_reports": line_reports
        }

