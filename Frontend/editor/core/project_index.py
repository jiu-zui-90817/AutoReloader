"""
全工程索引：用于搜索 / 引用查找。
基于已加载的 rules / art / ai（及单文件），不重新扫盘。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from .ini_parser import INIFile, INISection


@dataclass
class Hit:
    section_id: str
    key: str
    value: str
    kind: str  # "section" | "key" | "value" | "kv"
    source: str  # "rules" | "art" | "ai" | "single"
    display: str = ""

    def label(self) -> str:
        src = f"[{self.source}]" if self.source else ""
        if self.kind == "section":
            return f"{self.section_id}  {src}  （节名）"
        if self.kind == "key":
            return f"{self.section_id}.{self.key}  {src}"
        if self.kind == "kv":
            return f"{self.section_id}.{self.key}={self.value}  {src}"
        return f"{self.section_id}.{self.key}={self.value}  {src}  （值）"


def _inis(project) -> List[Tuple[str, INIFile]]:
    out: List[Tuple[str, INIFile]] = []
    if getattr(project, "work_mode", "") == "single" and project.single_ini:
        out.append(("single", project.single_ini))
        return out
    if project.rules:
        out.append(("rules", project.rules))
    if project.art:
        out.append(("art", project.art))
    if project.ai:
        out.append(("ai", project.ai))
    return out


def iter_sections(project) -> Iterable[Tuple[str, str, INISection]]:
    """yield (source, section_id, section)"""
    for src, ini in _inis(project):
        for name, sec in ini.sections.items():
            yield src, name, sec


def known_ids(project) -> Dict[str, Set[str]]:
    """小写 id -> 出现过的源集合；用于引用是否存在。"""
    m: Dict[str, Set[str]] = {}
    for src, name, _sec in iter_sections(project):
        m.setdefault(name.lower(), set()).add(src)
    return m


def search_project(
    project,
    query: str,
    *,
    in_section: bool = True,
    in_key: bool = True,
    in_value: bool = True,
    limit: int = 500,
) -> List[Hit]:
    q = (query or "").strip()
    if not q:
        return []
    ql = q.lower()

    # Primary=M60 形式
    kv_key = kv_val = None
    if "=" in q and in_key and in_value:
        left, right = q.split("=", 1)
        if left.strip() and right.strip():
            kv_key, kv_val = left.strip().lower(), right.strip().lower()

    hits: List[Hit] = []
    seen: Set[Tuple[str, str, str, str]] = set()

    def add(h: Hit):
        sig = (h.source, h.section_id.lower(), h.key.lower(), h.kind)
        if sig in seen:
            return
        seen.add(sig)
        hits.append(h)

    for src, name, sec in iter_sections(project):
        if len(hits) >= limit:
            break
        if in_section and ql in name.lower():
            add(Hit(name, "", "", "section", src))

        for key in sec.key_order:
            if len(hits) >= limit:
                break
            val = sec.keys.get(key, "")
            kl, vl = key.lower(), str(val).lower()

            if kv_key is not None:
                if kl == kv_key and kv_val in vl:
                    add(Hit(name, key, val, "kv", src))
                continue

            if in_key and ql in kl:
                add(Hit(name, key, val, "key", src))
            if in_value and ql in vl:
                add(Hit(name, key, val, "value", src))

    return hits


def find_references(project, target_id: str, limit: int = 500) -> List[Hit]:
    """查找值中引用了 target_id 的键（逗号列表也拆开匹配）。"""
    t = (target_id or "").strip()
    if not t:
        return []
    tl = t.lower()
    hits: List[Hit] = []
    for src, name, sec in iter_sections(project):
        if len(hits) >= limit:
            break
        # 自己节名不算「引用自己」时可跳过；仍保留便于看到定义
        for key in sec.key_order:
            val = str(sec.keys.get(key, ""))
            parts = [p.strip().lower() for p in val.replace(";", ",").split(",") if p.strip()]
            if tl in parts or tl == val.strip().lower():
                if name.lower() == tl and key == "":
                    continue
                hits.append(Hit(name, key, val, "value", src))
                if len(hits) >= limit:
                    break
    return hits
