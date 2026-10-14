"""
CSF (Command & Conquer String File) 解析器 / 写回
正确处理 RA2 / Yuri's Revenge / Mental Omega 的编码：
- 值是 UTF-16LE
- 每个字节需要按位取反 (~) 后才能解码/编码
"""

from __future__ import annotations

import struct
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class CSFParser:
    def __init__(self):
        # 查找表：原始大小写 + 小写
        self.strings: Dict[str, str] = {}
        # 写回用：保持首次出现的原始 label 顺序
        self.label_order: List[str] = []
        self.version: int = 3
        self.language: int = 0
        self.source_files: List[str] = []

    def _set_label(self, label: str, value: str) -> None:
        if not label:
            return
        # 更新已有（大小写不敏感）时保留原 key 形态
        existing = None
        for k in self.label_order:
            if k.lower() == label.lower():
                existing = k
                break
        if existing is not None:
            self.strings[existing] = value
            self.strings[existing.lower()] = value
            if existing != label:
                self.strings[label] = value
                self.strings[label.lower()] = value
        else:
            self.label_order.append(label)
            self.strings[label] = value
            self.strings[label.lower()] = value

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

        self.version = int(version)
        self.language = int(language)
        try:
            self.source_files.append(str(path.resolve()))
        except Exception:
            self.source_files.append(str(path))

        offset = 24
        labels_parsed = 0

        while offset + 12 <= len(data) and labels_parsed < num_labels:
            if data[offset : offset + 4] not in (b" LBL", b"LBL "):
                found = False
                for i in range(offset, min(offset + 64, len(data) - 4)):
                    if data[i : i + 4] in (b" LBL", b"LBL "):
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
                label = data[offset : offset + label_len].decode("ascii", errors="ignore").rstrip(
                    "\x00"
                )
            except Exception:
                label = ""
            offset += label_len

            for pair_idx in range(num_pairs):
                if offset + 8 > len(data):
                    break

                value_magic = data[offset : offset + 4]
                is_wide_extra = value_magic in (b"WRTS", b"STRW")

                try:
                    char_count = struct.unpack_from("<I", data, offset + 4)[0]
                except struct.error:
                    break

                offset += 8
                byte_len = char_count * 2

                if byte_len < 0 or offset + byte_len > len(data):
                    break

                raw = bytearray(data[offset : offset + byte_len])
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
                    self._set_label(label, value)

            labels_parsed += 1

        return len(self.label_order) > 0 or len(self.strings) > 0

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

    def set(self, label: str, value: str) -> None:
        """内存中新增/覆盖一条（写盘请用 save / upsert_label_to_file）。"""
        self._set_label(label, value)


def _encode_value_bytes(text: str) -> bytes:
    raw = (text or "").encode("utf-16-le")
    return bytes((~b) & 0xFF for b in raw)


def write_csf_file(
    filepath: Path,
    labels: OrderedDict[str, str] | Dict[str, str],
    *,
    version: int = 3,
    language: int = 0,
) -> None:
    """整文件写回。labels 的 key 使用原始大小写，勿混入纯小写重复项。"""
    filepath = Path(filepath)
    # 去重：同 label 小写只留第一次
    ordered: OrderedDict[str, str] = OrderedDict()
    seen_l: set[str] = set()
    items = labels.items() if hasattr(labels, "items") else []
    for k, v in items:
        if not k:
            continue
        lk = k.lower()
        if lk in seen_l:
            # 更新已有 key 的值
            for ok in list(ordered.keys()):
                if ok.lower() == lk:
                    ordered[ok] = v
                    break
            continue
        seen_l.add(lk)
        ordered[k] = v

    num_labels = len(ordered)
    num_strings = num_labels  # 每 label 一个 value
    out = bytearray()
    out += b" FSC"
    out += struct.pack("<IIIII", int(version), num_labels, num_strings, 0, int(language))

    for label, value in ordered.items():
        label_bytes = label.encode("ascii", errors="ignore")
        out += b" LBL"
        out += struct.pack("<II", 1, len(label_bytes))  # 1 pair
        out += label_bytes
        val_bytes = _encode_value_bytes(value)
        char_count = len(val_bytes) // 2
        out += b" RTS"
        out += struct.pack("<I", char_count)
        out += val_bytes

    filepath.write_bytes(bytes(out))


def load_csf_single(filepath: Path) -> Tuple[Optional[CSFParser], str]:
    """加载单个 CSF 文件（含 label_order）。返回 (parser, error)。"""
    p = CSFParser()
    if not p.load(filepath):
        return None, f"无法读取 CSF: {filepath}"
    return p, ""


def upsert_label_to_file(
    filepath: Path,
    label: str,
    value: str,
    *,
    backup_root: Optional[Path] = None,
    section_id: str = "",
) -> dict:
    """
    在指定 CSF 中新增或覆盖一条 label。
    读入 → 按文件风格规范标签 → 备份 → 整文件写回（保留 version/language）。
    若传入 section_id，会优先用 make_uiname_csf_label 对齐已有大小写。
    返回 {ok, message, path, label}
    """
    from core.save_util import backup_file

    filepath = Path(filepath)
    if not filepath.is_file():
        return {"ok": False, "message": f"CSF 文件不存在: {filepath}"}

    parser, err = load_csf_single(filepath)
    if not parser:
        return {"ok": False, "message": err}

    if section_id:
        label = make_uiname_csf_label(section_id, parser)
    elif not label:
        return {"ok": False, "message": "CSF label 为空"}
    else:
        # 覆盖时尽量跟已有键大小写一致
        for lab in parser.label_order or []:
            if lab.lower() == label.lower():
                label = lab
                break

    parser.set(label, value)
    ordered: OrderedDict[str, str] = OrderedDict()
    for k in parser.label_order:
        ordered[k] = parser.strings.get(k, "")

    if backup_root is None:
        backup_root = filepath.parent / "backups"
    try:
        backup_file(filepath, Path(backup_root))
    except Exception as e:
        return {"ok": False, "message": f"CSF 备份失败，已中止: {e}"}

    try:
        write_csf_file(
            filepath,
            ordered,
            version=parser.version or 3,
            language=parser.language or 0,
        )
    except Exception as e:
        return {"ok": False, "message": f"写入 CSF 失败: {e}"}

    return {
        "ok": True,
        "message": f"已写入 {label}={value!r} → {filepath.name}",
        "path": str(filepath),
        "label": label,
        "value": value,
    }



def resolve_csf_write_target(project_dir: Path, patterns: List[str]) -> Optional[Path]:
    """
    选写入目标 CSF（与游戏加载一致：同名 label 以后加载的为准）。

    规则：
    1. 按 profile.csf_files 顺序展开（通配按文件名排序）
    2. 优先 stringtable*.csf（模组表），取**最后一个**（覆盖优先级最高）
    3. 尽量不改原版 ra2.csf / ra2md.csf
    """
    if not project_dir:
        return None
    base = Path(project_dir)
    matched: List[Path] = []
    for pattern in patterns or []:
        pattern_str = str(pattern)
        if "*" in pattern_str or "?" in pattern_str:
            matched.extend(sorted(p for p in base.glob(pattern_str) if p.is_file()))
        else:
            p = base / pattern_str
            if p.is_file():
                matched.append(p)
    if not matched:
        return None
    seen = set()
    uniq: List[Path] = []
    for p in matched:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(Path(p))

    def is_vanilla(p: Path) -> bool:
        return p.name.lower() in ("ra2.csf", "ra2md.csf")

    stringtables = [p for p in uniq if "stringtable" in p.name.lower()]
    if stringtables:
        return stringtables[-1]
    modish = [
        p
        for p in uniq
        if not is_vanilla(p)
        and (
            "string" in p.name.lower()
            or "mod" in p.name.lower()
            or "mo" in p.name.lower()
            or "cn" in p.name.lower()
        )
    ]
    if modish:
        return modish[-1]
    non_van = [p for p in uniq if not is_vanilla(p)]
    if non_van:
        return non_van[-1]
    return uniq[-1]


def detect_name_prefix_style(parser: "CSFParser") -> str:
    """从已有标签推断前缀：NAME: / Name: / name:；默认 NAME:。"""
    counts = {"NAME:": 0, "Name:": 0, "name:": 0}
    for lab in parser.label_order or []:
        if ":" not in lab:
            continue
        pre, _, _rest = lab.partition(":")
        if pre.upper() != "NAME":
            continue
        if pre == "NAME":
            counts["NAME:"] += 1
        elif pre == "Name":
            counts["Name:"] += 1
        elif pre == "name":
            counts["name:"] += 1
        else:
            if pre.isupper():
                counts["NAME:"] += 1
            elif pre[0].isupper():
                counts["Name:"] += 1
            else:
                counts["name:"] += 1
    if not any(counts.values()):
        return "NAME:"
    return max(counts.items(), key=lambda kv: kv[1])[0]


def make_uiname_csf_label(section_id: str, parser: Optional["CSFParser"] = None) -> str:
    """已有同 ID 则保留原标签大小写；否则按文件主流前缀 + 注册名。"""
    sid = (section_id or "").strip()
    if not sid:
        return "NAME:"
    if parser is not None:
        for lab in parser.label_order or []:
            if ":" not in lab:
                continue
            pre, _, rest = lab.partition(":")
            if pre.upper() == "NAME" and rest.lower() == sid.lower():
                return lab
        prefix = detect_name_prefix_style(parser)
    else:
        prefix = "NAME:"
    return f"{prefix}{sid}"



def load_csf_files(file_list: List[str | Path], base_dir: Path) -> CSFParser:
    """按顺序加载多个 CSF，后面的覆盖前面的。支持通配符。"""
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
