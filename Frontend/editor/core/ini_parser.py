"""
保留顺序和注释的简易 INI 解析器
专为 Red Alert 2 / Mental Omega / Ares 规则文件设计
支持 Ares [#include] 深度优先递归加载与合并
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import OrderedDict
import re


class INISection:
    def __init__(self, name: str):
        self.name = name
        self.keys: OrderedDict[str, str] = OrderedDict()
        self.key_order: List[str] = []
        self.comments_before: List[str] = []
        self.inline_comments: Dict[str, str] = {}
        self.source_file: str = ""
        self.key_sources: Dict[str, str] = {}  # 键 -> 来源文件（拆分注册表用）

    def get(self, key: str, default: str = "") -> str:
        for k, v in self.keys.items():
            if k.lower() == key.lower():
                return v
        return default

    def set(self, key: str, value: str, inline_comment: str = "", source_file: str = ""):
        # Ares 列表追加：+=ID 或 + = ID → 每次新行，不能覆盖同一个 "+"
        ks = key.strip()
        if ks in ("+", "+=", "++"):
            n = sum(1 for x in self.key_order if x.startswith("+@"))
            uniq = f"+@{n}"
            self.keys[uniq] = value
            self.key_order.append(uniq)
            if inline_comment:
                self.inline_comments[uniq] = inline_comment
            if source_file:
                self.key_sources[uniq] = source_file
            return
        found = None
        for k in self.keys:
            if k.lower() == key.lower():
                found = k
                break
        if found:
            self.keys[found] = value
            if inline_comment:
                self.inline_comments[found] = inline_comment
            if source_file:
                self.key_sources[found] = source_file
        else:
            self.keys[key] = value
            self.key_order.append(key)
            if inline_comment:
                self.inline_comments[key] = inline_comment
            if source_file:
                self.key_sources[key] = source_file

    def merge_from(self, other: "INISection"):
        for key in other.key_order:
            src = other.key_sources.get(key) or other.source_file or ""
            self.set(
                key,
                other.keys[key],
                other.inline_comments.get(key, ""),
                source_file=src,
            )
        if other.source_file:
            self.source_file = other.source_file

    def to_text(self) -> str:
        # [ID] 必须在第一行，避免保存时再被 normalize 插一个头
        lines = [f"[{self.name}]"]
        for c in self.comments_before:
            if c is None:
                continue
            s = str(c).rstrip()
            if not s:
                continue
            # 分类注释保留在 section 内
            lines.append(s if s.lstrip().startswith(";") else f"; {s}")
        for key in self.key_order:
            val = self.keys.get(key, "")
            comment = self.inline_comments.get(key, "")
            out_key = "+=" if key.startswith("+@") else key
            if comment:
                lines.append(f"{out_key}{val} ;{comment}" if out_key == "+=" else f"{out_key}={val} ;{comment}")
            else:
                # Ares 常见写法 +=ID 或 += ID
                if out_key == "+=":
                    lines.append(f"+={val}")
                else:
                    lines.append(f"{out_key}={val}")
        return "\n".join(lines)


class INIFile:
    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath
        self.sections: OrderedDict[str, INISection] = OrderedDict()
        self.header_comments: List[str] = []
        self.section_order: List[str] = []
        self.loaded_files: List[str] = []
        self.file_sections: Dict[str, List[str]] = {}

    def _parse_text(self, text: str, source_name: str = "") -> None:
        current_section: Optional[INISection] = None
        pending_comments: List[str] = []

        for line in text.splitlines():
            stripped = line.strip()

            if not stripped:
                if current_section is None:
                    self.header_comments.append(line)
                else:
                    pending_comments.append(line)
                continue

            if stripped.startswith(";") or (
                stripped.startswith("#") and not stripped.lower().startswith("#include")
                and not re.match(r"^#\s*$", stripped)
            ):
                if current_section is None:
                    self.header_comments.append(line)
                else:
                    pending_comments.append(line)
                continue

            m = re.match(r"^\[([^\]]+)\](.*)$", stripped)
            if m:
                raw_name = m.group(1).strip()
                if "]:" in stripped or "]:[" in stripped:
                    sec_name = raw_name.split(":")[0].strip()
                else:
                    sec_name = raw_name

                if current_section is not None:
                    self._add_or_merge_section(current_section)

                current_section = INISection(sec_name)
                current_section.comments_before = pending_comments
                current_section.source_file = source_name
                pending_comments = []
                continue

            if current_section is not None and "=" in stripped:
                if ";" in stripped:
                    main, _, comment = stripped.partition(";")
                    comment = comment.strip()
                else:
                    main = stripped
                    comment = ""

                # Ares: +=ID / + = ID / += ID
                main_s = main.strip()
                if main_s.startswith("+=") or main_s.startswith("++="):
                    value = main_s.split("=", 1)[1].strip()
                    current_section.set("+", value, comment, source_file=source_name)
                    continue

                key, _, value = main.partition("=")
                key = key.strip()
                value = value.strip()

                if key:
                    current_section.set(key, value, comment, source_file=source_name)
                continue

            if current_section is None:
                self.header_comments.append(line)
            else:
                pending_comments.append(line)

        if current_section is not None:
            self._add_or_merge_section(current_section)

    def _add_or_merge_section(self, section: INISection):
        existing = self.get_section(section.name)
        if existing:
            existing.merge_from(section)
        else:
            self.sections[section.name] = section
            self.section_order.append(section.name)

    def load_file_only(self, filepath: Path) -> bool:
        if not filepath.exists():
            return False
        try:
            raw = filepath.read_bytes()
            text = None
            for enc in ("utf-8", "gbk", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                text = raw.decode("latin-1", errors="replace")
        except Exception:
            return False

        src_key = str(filepath.resolve()) if filepath.exists() else str(filepath)
        # 用绝对路径作来源，拆分注册表写回时才能落到正确文件（不能只用文件名）
        src_name = src_key
        self._parse_text(text, source_name=src_name)

        after_names = [n for n, s in self.sections.items() if s.source_file == src_name]
        if not after_names:
            for m in re.finditer(r"^\[([^\]]+)\]", text, re.M):
                n = m.group(1).strip().split(":")[0].strip()
                if n and n not in after_names:
                    after_names.append(n)

        self.file_sections[src_key] = after_names
        self.loaded_files.append(src_key)
        return True

    def load_with_includes(self, filepath: Path, base_dir: Path, visited: Optional[Set[str]] = None) -> bool:
        if visited is None:
            visited = set()

        abs_path = str(filepath.resolve())
        if abs_path in visited:
            return True
        visited.add(abs_path)

        ok = self.load_file_only(filepath)
        if not ok:
            return False

        include_sec = self.get_section("#include")
        if not include_sec:
            return True

        for key in include_sec.key_order:
            inc_name = include_sec.keys[key].strip()
            if not inc_name or inc_name.startswith(";"):
                continue

            inc_path = base_dir / inc_name
            if not inc_path.exists():
                inc_path = base_dir / Path(inc_name).name
            if not inc_path.exists():
                continue

            self.load_with_includes(inc_path, base_dir, visited)

        return True

    def get_section(self, name: str) -> Optional[INISection]:
        for k, v in self.sections.items():
            if k.lower() == name.lower():
                return v
        return None

    def get_list(self, list_name: str) -> List[str]:
        sec = self.get_section(list_name)
        if not sec:
            return []
        result = []
        for key in sec.key_order:
            val = sec.keys[key].strip()
            if val and not val.startswith(";"):
                result.append(val)
        return result

    def get_all_type_ids(self, type_lists: List[str]) -> Dict[str, List[str]]:
        result = {}
        for lst in type_lists:
            result[lst] = self.get_list(lst)
        return result
