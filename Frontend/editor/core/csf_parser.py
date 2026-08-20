"""
CSF (Command & Conquer String File) 解析器
正确处理 RA2 / Yuri's Revenge / Mental Omega 的编码：
- 值是 UTF-16LE
- 每个字节需要按位取反 (~) 后才能解码
"""

import struct
from pathlib import Path
from typing import Dict, List


class CSFParser:
    def __init__(self):
        # 同时保存原始大小写和下小写 key，方便查找
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

        # 文件头标识 " FSC"
        magic = data[0:4]
        if magic not in (b" FSC", b"CSF "):
            return False

        try:
            # version, num_labels, num_strings, unused, language
            version, num_labels, num_strings, _unused, language = struct.unpack_from(
                "<IIIII", data, 4
            )
        except struct.error:
            return False

        offset = 24
        labels_parsed = 0

        while offset + 12 <= len(data) and labels_parsed < num_labels:
            # 寻找 " LBL"
            if data[offset:offset + 4] not in (b" LBL", b"LBL "):
                # 容错：向后扫一点
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

            # 读取该 label 下的 value pairs（游戏只用第一个）
            for pair_idx in range(num_pairs):
                if offset + 8 > len(data):
                    break

                value_magic = data[offset:offset + 4]
                # " RTS" = 普通字符串, "WRTS" = 带 extra 的字符串
                is_wide_extra = value_magic in (b"WRTS", b"STRW")

                try:
                    # ValueLength = 字符数（不是字节数）
                    char_count = struct.unpack_from("<I", data, offset + 4)[0]
                except struct.error:
                    break

                offset += 8
                byte_len = char_count * 2  # UTF-16LE

                if byte_len < 0 or offset + byte_len > len(data):
                    break

                raw = bytearray(data[offset:offset + byte_len])
                offset += byte_len

                # 关键：每个字节按位取反
                for i in range(len(raw)):
                    raw[i] = (~raw[i]) & 0xFF

                try:
                    value = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
                except Exception:
                    value = ""

                # WRTS 后面还有 extra 字符串（ASCII），游戏几乎不用，跳过
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
                    # 只保留第一个 value
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
        # 处理 UIName=Name:XXX 形式
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
                # 再试 NAME: 大写
                full2 = f"NAME:{alt}"
                val = self.strings.get(full2) or self.strings.get(full2.lower())
                if val:
                    return val
        return default

    def get_uiname(self, uiname_value: str) -> str:
        """专门处理 UIName=Name:XXX"""
        if not uiname_value:
            return ""
        return self.get(uiname_value, default="")


def load_csf_files(file_list: List[str | Path], base_dir: Path) -> CSFParser:
    """按顺序加载多个 CSF，后面的覆盖前面的。
    支持通配符，例如 stringtable*.csf
    """
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
