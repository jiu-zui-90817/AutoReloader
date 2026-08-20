"""CSF 加载：UTF-16LE + 按位取反，支持通配符。
"""

import struct
from pathlib import Path
from typing import Dict, List


class CSFParser:
    def __init__(self):
        self.strings: Dict[str, str] = {}

    def load(self, filepath: str | Path) -> bool:
        path = Path(filepath)
        if not path.exists() or not path.is_file():
            return False

        try:
            data = path.read_bytes()
        except Exception:
            return False

        if len(data) < 24:
            return False

        magic = data[0:4]
        if magic not in (b" FSC", b"CSF "):
            return False

        try:
            version, num_labels, num_strings, _unused, language = struct.unpack_from(
                "<IIIII", data, 4
            )
        except struct.error:
            return False

        offset = 24
        labels_parsed = 0

        while offset + 12 <= len(data) and labels_parsed < num_labels:
            if data[offset:offset + 4] not in (b" LBL", b"LBL "):
                found = False
                for i in range(offset, min(offset + 64, len(data) - 4)):
                    if data[i:i + 4] in (b" LBL", b"LBL "):
                        offset = i
                        found = True
                        break
                if not found:
                    break

            try:
                num_pairs, label_len = struct.unpack_from("<II", data, offset + 4)
            except struct.error:
                break

            offset += 12
            if label_len < 0 or offset + label_len > len(data):
                break

            try:
                label = data[offset:offset + label_len].decode("ascii", errors="ignore").rstrip("\x00")
            except Exception:
                label = ""
            offset += label_len

            for pair_idx in range(num_pairs):
                if offset + 8 > len(data):
                    break

                value_magic = data[offset:offset + 4]
                is_wide_extra = value_magic in (b"WRTS", b"STRW")

                try:
                    char_count = struct.unpack_from("<I", data, offset + 4)[0]
                except struct.error:
                    break

                offset += 8
                byte_len = char_count * 2

                if byte_len < 0 or offset + byte_len > len(data):
                    break

                raw = bytearray(data[offset:offset + byte_len])
                offset += byte_len

                for i in range(len(raw)):
                    raw[i] = (~raw[i]) & 0xFF

                try:
                    value = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
                except Exception:
                    value = ""

                if is_wide_extra:
                    if offset + 4 <= len(data):
                        try:
                            extra_len = struct.unpack_from("<I", data, offset)[0]
                            offset += 4
                            if extra_len > 0 and offset + extra_len <= len(data):
                                offset += extra_len
                        except struct.error:
                            pass

                if label and pair_idx == 0:
                    self.strings[label] = value
                    self.strings[label.lower()] = value

            labels_parsed += 1

        return len(self.strings) > 0

    def get(self, label: str, default: str = "") -> str:
        if not label:
            return default
        key = label.strip()
        val = self.strings.get(key) or self.strings.get(key.lower())
        if val:
            return val
        if ":" in key:
            parts = key.split(":", 1)
            if len(parts) == 2:
                alt = parts[1].strip()
                val = self.strings.get(alt) or self.strings.get(alt.lower())
                if val:
                    return val
                full = f"Name:{alt}"
                val = self.strings.get(full) or self.strings.get(full.lower())
                if val:
                    return val
                full2 = f"NAME:{alt}"
                val = self.strings.get(full2) or self.strings.get(full2.lower())
                if val:
                    return val
        return default

    def get_uiname(self, uiname_value: str) -> str:
        if not uiname_value:
            return ""
        return self.get(uiname_value, default="")


def load_csf_files(file_list: List[str | Path], base_dir: Path) -> CSFParser:
    parser = CSFParser()
    for pattern in file_list:
        pattern_str = str(pattern)
        if "*" in pattern_str or "?" in pattern_str:
            matched = sorted(base_dir.glob(pattern_str))
            for path in matched:
                if path.is_file():
                    parser.load(path)
        else:
            path = base_dir / pattern_str
            if path.exists() and path.is_file():
                parser.load(path)
    return parser
