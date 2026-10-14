"""当前节 Diff：编辑内容 vs 磁盘 / vs 会话基线。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class KeyChange:
    key: str
    kind: str  # "added" | "removed" | "changed"
    old: str = ""
    new: str = ""

    def label(self) -> str:
        if self.kind == "added":
            return f"+ {self.key}={self.new}"
        if self.kind == "removed":
            return f"- {self.key}={self.old}"
        return f"~ {self.key}: {self.old} → {self.new}"


def parse_kv_map(section_text: str) -> Dict[str, str]:
    """解析 section 正文为 key→value（小写键索引，保留首次出现的原始键名于 _orig）。"""
    out: Dict[str, str] = {}
    orig: Dict[str, str] = {}
    for raw in (section_text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or (line.startswith("[") and "]" in line):
            continue
        if ";" in line:
            line = line.split(";", 1)[0].strip()
        if "=" not in line:
            # Ares +=ID
            if line.startswith("+="):
                val = line[2:].strip()
                k = f"+=@{len([x for x in out if x.startswith('+=@')])}"
                out[k] = val
                orig[k] = "+="
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if not k:
            continue
        if k in ("+", "+=", "++"):
            uniq = f"+=@{len([x for x in out if x.startswith('+=@')])}"
            out[uniq] = v
            orig[uniq] = "+="
            continue
        kl = k.lower()
        out[kl] = v
        orig[kl] = k
    out["__orig_keys__"] = orig  # type: ignore
    return out


def diff_kv(old_text: str, new_text: str) -> List[KeyChange]:
    old_m = parse_kv_map(old_text)
    new_m = parse_kv_map(new_text)
    old_orig = old_m.pop("__orig_keys__", {}) or {}
    new_orig = new_m.pop("__orig_keys__", {}) or {}
    changes: List[KeyChange] = []
    all_keys = sorted(set(old_m) | set(new_m), key=lambda x: (not x.startswith("+=@"), x))
    for kl in all_keys:
        o = old_m.get(kl)
        n = new_m.get(kl)
        display = new_orig.get(kl) or old_orig.get(kl) or kl
        if o is None and n is not None:
            changes.append(KeyChange(display, "added", new=n))
        elif o is not None and n is None:
            changes.append(KeyChange(display, "removed", old=o))
        elif o != n:
            changes.append(KeyChange(display, "changed", old=o or "", new=n or ""))
    return changes


def summarize_changes(changes: List[KeyChange]) -> str:
    if not changes:
        return "无差异"
    a = sum(1 for c in changes if c.kind == "added")
    r = sum(1 for c in changes if c.kind == "removed")
    ch = sum(1 for c in changes if c.kind == "changed")
    parts = []
    if ch:
        parts.append(f"改 {ch}")
    if a:
        parts.append(f"增 {a}")
    if r:
        parts.append(f"删 {r}")
    return "，".join(parts)
