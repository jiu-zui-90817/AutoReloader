"""hotfix / section 写回与备份。
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List


def backup_file(filepath: Path, backup_root: Path) -> Path:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(str(filepath))
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = backup_root / f"{filepath.stem}_{stamp}{filepath.suffix}"
    n = 1
    while dest.exists():
        dest = backup_root / f"{filepath.stem}_{stamp}_{n}{filepath.suffix}"
        n += 1
    shutil.copy2(filepath, dest)
    return dest


def read_text(path: Path) -> Tuple[str, str]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp936", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"


def encode_ini_bytes(text: str, enc: str) -> bytes:
    """
    写回磁盘用的编码。
    读入时可能用 utf-8-sig 去掉 BOM，但写回必须用无 BOM 的 utf-8，
    否则游戏引擎 / AutoReloader 可能无法正确识别。
    GBK 等本地编码保持原样。
    """
    e = (enc or "utf-8").lower().replace("_", "-")
    if e in ("utf-8-sig", "utf8-sig", "utf-8", "utf8"):
        return text.encode("utf-8", errors="replace")  # 无 BOM
    try:
        return text.encode(enc, errors="replace")
    except LookupError:
        return text.encode("utf-8", errors="replace")


def normalize_section_body(section_id: str, body: str) -> str:
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("; 来源:") or s.startswith("; 来源："):
            continue
        lines.append(ln.rstrip())
    text = "\n".join(lines).strip("\n")

    header_re = re.compile(
        rf"(?i)^\[{re.escape(section_id)}(?:\s*:[^\]]*)?\][^\r\n]*$"
    )
    arr = text.splitlines() if text else []
    first_i = 0
    while first_i < len(arr) and not arr[first_i].strip():
        first_i += 1

    out: List[str] = []
    if first_i < len(arr) and header_re.match(arr[first_i].strip()):
        out.append(arr[first_i].rstrip())
        rest = arr[first_i + 1 :]
    else:
        out.append(f"[{section_id}]")
        rest = arr

    started = False
    for ln in rest:
        s = ln.strip()
        if s.startswith("[") and "]" in s:
            break
        if not s and not started:
            # 节头后前导空行不要
            continue
        started = True
        out.append(ln.rstrip())

    while len(out) > 1 and not out[-1].strip():
        out.pop()
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


def find_section_span(text: str, section_name: str) -> Optional[Tuple[int, int]]:
    pattern = re.compile(
        rf"(?im)^\[{re.escape(section_name)}(?:\s*:[^\]]*)?\][^\n]*\r?\n?"
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.start()
    rest = text[m.end():]
    next_sec = re.search(r"(?m)^\[", rest)
    if next_sec:
        end = m.end() + next_sec.start()
    else:
        end = len(text)
    return start, end


def replace_section_in_text(text: str, section_name: str, new_body: str) -> Tuple[str, bool]:
    span = find_section_span(text, section_name)
    body = new_body
    if not body.endswith("\n"):
        body += "\n"
    if span is None:
        return text, False
    start, end = span
    return text[:start] + body + text[end:], True


def append_section_after_peers(text: str, new_body: str, peer_names: List[str]) -> str:
    body = new_body if new_body.endswith("\n") else new_body + "\n"
    last_end = -1
    for name in peer_names:
        span = find_section_span(text, name)
        if span:
            last_end = span[1]
    if last_end >= 0:
        insert = body
        if last_end < len(text) and text[last_end:last_end+1] != "\n":
            insert = "\n" + insert
        return text[:last_end] + insert + text[last_end:]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + "\n" + body


_ART_ONLY_KEYS = {
    "foundation", "height", "buildup", "cameopcx", "remapable", "newtheater",
    "zshapepointmove", "occupyheight", "bibshape", "queueingcell",
    "demandloadbuildup", "freebuildup", "normalized", "canhidethings",
    "canbehidden",
}
_ART_PREFIXES = ("activeanim", "turretanim", "barrelanim", "damagefireoffset")
_RULES_ONLY_KEYS = {
    "strength", "armor", "cost", "techlevel", "owner", "prerequisite",
    "primary", "secondary", "speed", "sight", "power", "factory",
    "constructionyard", "undeploysinto", "capturable", "name", "uiname",
    "crewed", "explosion", "debrisanims", "maxdebris", "threatposed",
    "aibuildthis", "adjacent", "buildcat", "selltime", "builduptime",
    "soylent", "points", "bounty.value", "immune", "spyable",
}


def _section_key_set_from_body(section_id: str, body: str) -> set[str]:
    keys: set[str] = set()
    for line in (body or "").splitlines():
        s = line.strip()
        if not s or s.startswith((";", "#", "[")):
            continue
        if s.startswith("+="):
            keys.add("+")
            continue
        if "=" in s:
            keys.add(s.split("=", 1)[0].strip().lower())
    return keys


def _section_has_meaningful_keys(section_id: str, block: str) -> int:
    keys: set[str] = set()
    for line in (block or "").splitlines():
        s = line.strip()
        if not s or s.startswith((";", "#", "[")):
            continue
        if s.startswith("+="):
            keys.add("+")
            continue
        if "=" in s:
            keys.add(s.split("=", 1)[0].strip().lower())
    return len(keys)


def _section_header_count(text: str, section_id: str) -> int:
    header_re = re.compile(rf"(?im)^\[{re.escape(section_id)}(?:\s*:[^\]]*)?\]")
    return sum(1 for line in (text or "").splitlines() if header_re.match(line))


def _guard_section_write(filepath: Path, section_id: str, new_body: str, text: str) -> str | None:
    """致命保存错误保护：重复节、清空节、rules/art 字段写错文件。"""
    header_re = re.compile(rf"(?im)^\[{re.escape(section_id)}(?:\s*:[^\]]*)?\]")
    header_lines = [i for i, line in enumerate((text or "").splitlines(), 1) if header_re.match(line)]
    if len(header_lines) > 1:
        return (
            f"拒绝写入 [{section_id}]：目标文件存在 {len(header_lines)} 个同名 section"
            f"（行 {', '.join(map(str, header_lines[:6]))}）。\n"
            "请先删除重复节，避免规则/Art 数据被错误覆盖。"
        )

    fname = Path(filepath).name.lower()
    kind = "art" if "art" in fname else ("rules" if "rules" in fname else "")

    span = find_section_span(text or "", section_id)
    old_block = (text or "")[span[0]:span[1]] if span else ""
    old_keys = _section_key_set_from_body(section_id, old_block)
    old_n = len(old_keys)
    new_n = _section_has_meaningful_keys(section_id, new_body)
    old_art = any(
        k in _ART_ONLY_KEYS or k.startswith(_ART_PREFIXES) for k in old_keys
    )
    # 只保护 Art 或包含 Art 字段的节；rules 节清空键是合法操作。
    if old_n > 0 and new_n == 0 and (kind == "art" or old_art):
        return (
            f"拒绝写入 [{section_id}]：新内容没有任何键，而现有 Art 节有 {old_n} 个键。\n"
            "这可能是误删/空保存；请先确认内容，避免清空 Art 数据。"
        )
    if kind:
        new_keys = _section_key_set_from_body(section_id, new_body)
        art_hits = {k for k in new_keys if k in _ART_ONLY_KEYS or k.startswith(_ART_PREFIXES)}
        rules_hits = {k for k in new_keys if k in _RULES_ONLY_KEYS}
        if kind == "art" and rules_hits and not art_hits:
            return (
                f"拒绝写入 [{section_id}]：目标是 Art 文件，但内容只有 rules 字段"
                f"（{', '.join(sorted(rules_hits)[:6])}）。\n"
                "请写入 artmo.ini 的 Image/Foundation/动画字段，或改回 rules 文件。"
            )
        if kind == "rules" and art_hits and not rules_hits:
            return (
                f"拒绝写入 [{section_id}]：目标是 rules 文件，但内容只有 Art 字段"
                f"（{', '.join(sorted(art_hits)[:6])}）。\n"
                "请写入 rulesmo.ini，或改回 Art 文件。"
            )
    return None


def save_section_to_file(
    filepath: Path,
    section_name: str,
    new_section_body: str,
    backup_root: Path,
    is_new: bool = False,
    peer_section_names: Optional[List[str]] = None,
) -> dict:
    filepath = Path(filepath)
    result = {
        "ok": False,
        "backup_path": None,
        "message": "",
        "path": str(filepath),
        "bytes_written": 0,
    }

    body = normalize_section_body(section_name, new_section_body)

    if filepath.exists():
        text, enc = read_text(filepath)
        guard = _guard_section_write(filepath, section_name, body, text)
        if guard:
            result["message"] = guard
            return result
        try:
            bak = backup_file(filepath, backup_root)
            result["backup_path"] = str(bak)
        except Exception as e:
            result["message"] = f"备份失败，已中止保存: {e}"
            return result
    else:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        text, enc = "", "utf-8"
        is_new = True

    if is_new:
        text = append_section_after_peers(text, body, peer_section_names or [])
        action = "新增写入"
    else:
        text2, found = replace_section_in_text(text, section_name, body)
        if found:
            text = text2
            action = "原地替换"
        else:
            text = append_section_after_peers(text, body, peer_section_names or [])
            action = "未找到原块，已按新增插入"

    try:
        data = encode_ini_bytes(text, enc)
        tmp = filepath.with_suffix(filepath.suffix + ".tmp_moeditor")
        tmp.write_bytes(data)
        tmp.replace(filepath)
        # 写入后自检：同名节必须恰好 1 个；有内容时不能变成空节。
        after, _ = read_text(filepath)
        headers = _section_header_count(after, section_name)
        after_block = ""
        span2 = find_section_span(after, section_name)
        if span2:
            after_block = after[span2[0]:span2[1]]
        after_keys = _section_has_meaningful_keys(section_name, after_block)
        body_keys = _section_has_meaningful_keys(section_name, body)
        if headers != 1 or (body_keys > 0 and after_keys == 0):
            if result.get("backup_path") and Path(result["backup_path"]).is_file():
                shutil.copy2(result["backup_path"], filepath)
                result["message"] = (
                    f"写入后校验失败：目标文件出现 {headers} 个 [{section_name}]，"
                    "已自动从备份恢复。"
                )
            else:
                result["message"] = (
                    f"写入后校验失败：目标文件出现 {headers} 个 [{section_name}]。"
                )
            result["ok"] = False
            return result
        result["ok"] = True
        result["bytes_written"] = len(data)
        msg = f"{action}成功 → {filepath}\n写入 {len(data)} 字节"
        if result["backup_path"]:
            msg += f"\n备份: {result['backup_path']}"
        result["message"] = msg
    except Exception as e:
        result["message"] = f"写入失败: {e}"

    return result


def append_autoreloader_commands(
    filepath: Path,
    commands: List[str],
    backup_root: Optional[Path] = None,
) -> dict:
    """Append AutoReloader commands to the [AutoReloader] section.

    Used by the editor and workshop for Convert=... generation. Existing
    commands are preserved; duplicate lines are skipped case-insensitively.
    """
    filepath = Path(filepath)
    backup_root = Path(backup_root) if backup_root else filepath.parent / "backups"
    wanted = [c.strip() for c in commands if c and c.strip()]
    if not wanted:
        return {"ok": False, "message": "没有可写入的指令", "path": str(filepath)}

    text = ""
    if filepath.exists():
        text, _ = read_text(filepath)
    span = find_section_span(text, "AutoReloader")
    body = ""
    if span:
        block = text[span[0]:span[1]]
        lines = block.splitlines()
        body = "\n".join(lines[1:]).strip("\n")

    existing = {line.strip().lower() for line in body.splitlines() if line.strip()}
    added = [c for c in wanted if c.lower() not in existing]
    if not added:
        return {"ok": True, "message": "指令已存在，未重复写入", "path": str(filepath)}

    new_body = body + ("\n" if body else "") + "\n".join(added)
    return save_section_to_file(
        filepath,
        "AutoReloader",
        new_body,
        backup_root=backup_root,
        is_new=span is None,
    )


def read_autoreloader_commands(filepath: Path) -> List[str]:
    """Return non-empty command lines from the [AutoReloader] section."""
    filepath = Path(filepath)
    if not filepath.is_file():
        return []
    text, _ = read_text(filepath)
    span = find_section_span(text, "AutoReloader")
    if not span:
        return []
    block = text[span[0]:span[1]]
    return [
        line.strip() for line in block.splitlines()[1:]
        if line.strip() and not line.strip().startswith((";", "#"))
    ]


def apply_convert_commands(
    filepath: Path,
    source: str,
    target: str,
    round_trip: bool,
    backup_root: Optional[Path] = None,
) -> dict:
    """Write Convert commands, replacing conflicting mappings from source.

    - Existing ``Convert=source>...`` lines are removed and replaced.
    - If ``round_trip``, an existing ``Convert=target>source`` is removed.
    - Other commands are preserved; incoming mappings to source are reported so
      the caller can warn about chained conversions.
    """
    filepath = Path(filepath)
    source = source.strip()
    target = target.strip()
    backup_root = Path(backup_root) if backup_root else filepath.parent / "backups"
    if not source or not target:
        return {"ok": False, "message": "源/目标为空", "path": str(filepath)}

    text = ""
    if filepath.exists():
        text, _ = read_text(filepath)
    span = find_section_span(text, "AutoReloader")
    body = ""
    if span:
        block = text[span[0]:span[1]]
        body = "\n".join(block.splitlines()[1:]).strip("\n")

    kept: List[str] = []
    removed: List[str] = []
    incoming: List[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        m = re.match(r"(?i)^convert\s*=\s*(.+)$", stripped)
        if not m:
            kept.append(line)
            continue
        spec = m.group(1)
        parts = re.split(r"\s*(?:->|>)\s*", spec, maxsplit=1)
        if len(parts) != 2:
            kept.append(line)
            continue
        src, dst = parts[0].strip(), parts[1].strip()
        if src.lower() == source.lower():
            removed.append(stripped)
            continue
        if round_trip and src.lower() == target.lower() and dst.lower() == source.lower():
            removed.append(stripped)
            continue
        if dst.lower() == source.lower():
            incoming.append(stripped)
        kept.append(line)

    added = [f"Convert={source}>{target}"]
    if round_trip:
        added.append(f"Convert={target}>{source}")
    new_body = "\n".join(kept + added).strip("\n")
    result = save_section_to_file(
        filepath,
        "AutoReloader",
        new_body,
        backup_root=backup_root,
        is_new=span is None,
    )
    result["removed"] = removed
    result["incoming"] = incoming
    result["commands"] = added
    return result
