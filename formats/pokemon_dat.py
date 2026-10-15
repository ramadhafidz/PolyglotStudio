import struct
import os
from typing import List, Tuple, Any
from .base_codec import BaseTextCodec

class PokemonDatCodec(BaseTextCodec):
    """
    Binary Codec for Pokemon Scarlet & Violet .dat message files.
    Pure Python implementation of Game Freak's rolling encryption and Flat/Trinity text packing.
    """

    VAR_NAMES = {
        0xFF00: "COLOR", 0x0100: "TRNAME", 0x0101: "PKNAME", 0x0102: "PKNICK",
        0x0103: "TYPE", 0x0105: "LOCATION", 0x0106: "ABILITY", 0x0107: "MOVE",
        0x0108: "ITEM1", 0x0109: "ITEM2", 0x010A: "sTRBAG", 0x010B: "BOX",
        0x010D: "EVSTAT", 0x0110: "OPOWER", 0x0127: "RIBBON", 0x0134: "MIINAME",
        0x013E: "WEATHER", 0x0189: "TRNICK", 0x018A: "1stchrTR", 0x018B: "SHOUTOUT",
        0x018E: "BERRY", 0x018F: "REMFEEL", 0x0190: "REMQUAL", 0x0191: "WEBSITE",
        0x019C: "CHOICECOS", 0x01A1: "GSYNCID", 0x0192: "PRVIDSAY", 0x0193: "BTLTEST",
        0x0195: "GENLOC", 0x0199: "CHOICEFOOD", 0x019A: "HOTELITEM", 0x019B: "TAXISTOP",
        0x019F: "MAISTITLE", 0x1000: "ITEMPLUR0", 0x1001: "ITEMPLUR1", 0x1100: "GENDBR",
        0x1101: "NUMBRNCH", 0x1302: "iCOLOR2", 0x1303: "iCOLOR3", 0x0200: "NUM1",
        0x0201: "NUM2", 0x0202: "NUM3", 0x0203: "NUM4", 0x0204: "NUM5", 0x0205: "NUM6",
        0x0206: "NUM7", 0x0207: "NUM8", 0x0208: "NUM9"
    }

    VAR_CODES = {k.lower(): v for k, v in {
        "color": 0xFF00, "trname": 0x0100, "pkname": 0x0101, "pknick": 0x0102,
        "type": 0x0103, "location": 0x0105, "ability": 0x0106, "move": 0x0107,
        "item1": 0x0108, "item2": 0x0109, "strbag": 0x010A, "box": 0x010B,
        "evstat": 0x010D, "opower": 0x0110, "ribbon": 0x0127, "miiname": 0x0134,
        "weather": 0x013E, "trnick": 0x0189, "1stchrtr": 0x018A, "shoutout": 0x018B,
        "berry": 0x018E, "remfeel": 0x018F, "remqual": 0x0190, "website": 0x0191,
        "choicecos": 0x019C, "gsyncid": 0x01A1, "prvidsay": 0x0192, "bltest": 0x0193,
        "genloc": 0x0195, "choicefood": 0x0199, "hotelitem": 0x019A, "taxistop": 0x019B,
        "maistitle": 0x019F, "itemplur0": 0x1000, "itemplur1": 0x1001, "gendbr": 0x1100,
        "numbrnch": 0x1101, "icolor2": 0x1302, "icolor3": 0x1303, "num1": 0x0200,
        "num2": 0x0201, "num3": 0x0202, "num4": 0x0203, "num5": 0x0204, "num6": 0x0205,
        "num7": 0x0206, "num8": 0x0207, "num9": 0x0208
    }.items()}

    def decrypt_u16(self, data: bytes, offset: int, key: int) -> Tuple[int, int, int]:
        val = struct.unpack_from('<H', data, offset)[0] ^ key
        offset += 2
        key = ((key << 3) | (key >> 13)) & 0xFFFF
        return val, offset, key

    def decrypt_variable(self, data: bytes, offset: int, key: int) -> Tuple[str, int, int]:
        length, offset, key = self.decrypt_u16(data, offset, key)
        var_type, offset, key = self.decrypt_u16(data, offset, key)

        if var_type == 0xBE00:
            return "\\r", offset, key
        elif var_type == 0xBE01:
            return "\\c", offset, key
        elif var_type == 0xBE02:
            arg, offset, key = self.decrypt_u16(data, offset, key)
            return f"[WAIT {arg}]", offset, key
        elif var_type == 0xBDFF:
            arg, offset, key = self.decrypt_u16(data, offset, key)
            return f"[~ {arg}]", offset, key
        else:
            var_name = self.VAR_NAMES.get(var_type, f"{var_type:04X}")
            result = f"[VAR {var_name}"
            if length > 1:
                result += "("
                for i in range(length - 1):
                    arg, offset, key = self.decrypt_u16(data, offset, key)
                    result += f"{arg:04X}"
                    if i < length - 2:
                        result += ","
                result += ")"
            result += "]"
            return result, offset, key

    def read_file(self, file_path: str) -> List[str]:
        with open(file_path, 'rb') as f:
            data = f.read()
        return self.decode_bytes(data)

    def decode_bytes(self, data: bytes) -> List[str]:
        if len(data) < 16:
            return []

        text_sections = struct.unpack_from('<H', data, 0)[0]
        line_count = struct.unpack_from('<H', data, 2)[0]
        total_length = struct.unpack_from('<I', data, 4)[0]
        initial_key = struct.unpack_from('<I', data, 8)[0]
        section_data = struct.unpack_from('<i', data, 12)[0]

        if line_count == 0:
            return []
        if initial_key != 0:
            raise ValueError("Invalid initial key in binary dat payload")
        if section_data + total_length != len(data) or text_sections != 1:
            raise ValueError("Invalid text file format in binary dat payload")

        lines = []
        key = 0x7C89

        for i in range(line_count):
            offset = struct.unpack_from('<I', data, section_data + 4 + i * 8)[0] + section_data
            length = struct.unpack_from('<H', data, section_data + 8 + i * 8)[0]

            line_key = key
            result = ''
            chars_decoded = 0

            while chars_decoded < length:
                val, offset, line_key = self.decrypt_u16(data, offset, line_key)
                chars_decoded += 1

                if val == 0:
                    break
                elif val == 0x0A:
                    result += "\\n"
                elif val == 0x10:
                    var_str, offset, line_key = self.decrypt_variable(data, offset, line_key)
                    result += var_str
                    chars_decoded = length
                else:
                    if val == 0xE07F:
                        result += '\u202F'
                    elif val == 0xE08D:
                        result += '…'
                    elif val == 0xE08E:
                        result += '♂'
                    elif val == 0xE08F:
                        result += '♀'
                    else:
                        result += chr(val)

            lines.append(result)
            key = (key + 0x2983) & 0xFFFF

        return lines

    def encrypt_u16(self, val: int, key: int) -> Tuple[bytes, int]:
        encrypted = val ^ key
        key = ((key << 3) | (key >> 13)) & 0xFFFF
        return struct.pack('<H', encrypted), key

    def get_variable_value(self, var_name: str) -> int:
        var_name_lower = var_name.lower()
        if var_name_lower in self.VAR_CODES:
            return self.VAR_CODES[var_name_lower]
        try:
            return int(var_name, 16)
        except ValueError:
            raise ValueError(f"Unknown variable name: {var_name}")

    def parse_variable(self, text: str, index: int) -> Tuple[Any, int]:
        i = index
        if text[i:i+2] == '\\n':
            return '\\n', i+2
        elif text[i:i+2] == '\\r':
            return '\\r', i+2
        elif text[i:i+2] == '\\c':
            return '\\c', i+2

        if text[i] == '[':
            end_bracket = text.find(']', i)
            if end_bracket == -1:
                raise ValueError("Unclosed bracket in variable: " + text[i:])

            content = text[i+1:end_bracket]
            parts = content.split(' ', 1)
            var_type = parts[0]

            if var_type == 'WAIT':
                arg = parts[1] if len(parts) > 1 else "0"
                return ('WAIT', arg), end_bracket+1
            elif var_type == '~':
                arg = parts[1] if len(parts) > 1 else "0"
                return ('~', arg), end_bracket+1
            elif var_type == 'VAR':
                var_content = parts[1] if len(parts) > 1 else ""
                paren_index = var_content.find('(')

                if paren_index == -1:
                    return ('VAR', var_content, []), end_bracket+1
                else:
                    var_name = var_content[:paren_index]
                    args_str = var_content[paren_index+1:-1]
                    args = [int(arg, 16) for arg in args_str.split(',')] if args_str else []
                    return ('VAR', var_name, args), end_bracket+1

        return text[i], i+1

    def write_file(self, file_path: str, lines: List[str]) -> bool:
        text_sections = 1
        line_count = len(lines)
        base_key = 0x7C89

        line_offsets = []
        line_lengths = []
        line_data = []

        for i in range(line_count):
            line_key = base_key
            line_bytes = bytearray()
            j = 0
            while j < len(lines[i]):
                token, j = self.parse_variable(lines[i], j)

                if token == '\\n':
                    enc, line_key = self.encrypt_u16(0x0A, line_key)
                    line_bytes.extend(enc)
                elif token == '\\r':
                    enc, line_key = self.encrypt_u16(0x10, line_key)
                    line_bytes.extend(enc)
                    enc, line_key = self.encrypt_u16(1, line_key)
                    line_bytes.extend(enc)
                    enc, line_key = self.encrypt_u16(0xBE00, line_key)
                    line_bytes.extend(enc)
                elif token == '\\c':
                    enc, line_key = self.encrypt_u16(0x10, line_key)
                    line_bytes.extend(enc)
                    enc, line_key = self.encrypt_u16(1, line_key)
                    line_bytes.extend(enc)
                    enc, line_key = self.encrypt_u16(0xBE01, line_key)
                    line_bytes.extend(enc)
                elif isinstance(token, tuple):
                    if token[0] == 'WAIT':
                        enc, line_key = self.encrypt_u16(0x10, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(1, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(0xBE02, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(int(token[1]), line_key)
                        line_bytes.extend(enc)
                    elif token[0] == '~':
                        enc, line_key = self.encrypt_u16(0x10, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(1, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(0xBDFF, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(int(token[1]), line_key)
                        line_bytes.extend(enc)
                    elif token[0] == 'VAR':
                        var_code = self.get_variable_value(token[1])
                        args = token[2] if len(token) > 2 else []
                        enc, line_key = self.encrypt_u16(0x10, line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(1 + len(args), line_key)
                        line_bytes.extend(enc)
                        enc, line_key = self.encrypt_u16(var_code, line_key)
                        line_bytes.extend(enc)
                        for arg in args:
                            enc, line_key = self.encrypt_u16(arg, line_key)
                            line_bytes.extend(enc)
                else:
                    char_code = ord(token)
                    if token == '\u202F':
                        char_code = 0xE07F
                    elif token == '…':
                        char_code = 0xE08D
                    elif token == '♂':
                        char_code = 0xE08E
                    elif token == '♀':
                        char_code = 0xE08F
                    enc, line_key = self.encrypt_u16(char_code, line_key)
                    line_bytes.extend(enc)

            # Null terminator
            enc, line_key = self.encrypt_u16(0, line_key)
            line_bytes.extend(enc)

            if len(line_bytes) % 4 != 0:
                line_bytes.extend(b'\x00\x00')

            line_data.append(line_bytes)
            line_lengths.append(len(line_bytes) // 2)
            base_key = (base_key + 0x2983) & 0xFFFF

        current_offset = 4 + line_count * 8
        for i in range(line_count):
            line_offsets.append(current_offset)
            current_offset += len(line_data[i])

        total_length = current_offset
        result = bytearray()

        result.extend(struct.pack('<H', text_sections))
        result.extend(struct.pack('<H', line_count))
        result.extend(struct.pack('<I', total_length))
        result.extend(struct.pack('<I', 0))
        result.extend(struct.pack('<I', 0x10))
        result.extend(struct.pack('<I', total_length))

        for i in range(line_count):
            result.extend(struct.pack('<I', line_offsets[i]))
            result.extend(struct.pack('<H', line_lengths[i]))
            result.extend(struct.pack('<H', 0))

        for data in line_data:
            result.extend(data)

        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(result)
        return True

    def export_to_txt(self, source_path: str, target_txt_path: str) -> bool:
        lines = self.read_file(source_path)
        base_name = os.path.basename(source_path)
        os.makedirs(os.path.dirname(os.path.abspath(target_txt_path)), exist_ok=True)
        with open(target_txt_path, 'w', encoding='utf-8') as f:
            f.write("~~~~~~~~~~~~~~~\n")
            f.write(f"Text File: {base_name}\n")
            f.write("~~~~~~~~~~~~~~~\n")
            for line in lines:
                f.write(line + '\n')
        return True

    def import_from_txt(self, source_txt_path: str, target_path: str) -> bool:
        with open(source_txt_path, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()

        content_start = 0
        for i, line in enumerate(raw_lines):
            if "~~~~~~~~~~~~~~~" in line and i > 0:
                content_start = i + 1
                break

        lines = []
        for line in raw_lines[content_start:]:
            stripped = line.rstrip('\r\n')
            if stripped.startswith("~~~~~~~~~~~~~~~"):
                continue
            lines.append(stripped)

        return self.write_file(target_path, lines)
