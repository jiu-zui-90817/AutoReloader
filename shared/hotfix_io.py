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
        try:
            bak = backup_file(filepath, backup_root)
            result["backup_path"] = str(bak)
        except Exception as e:
            result["message"] = f"备份失败，已中止保存: {e}"
            return result
        text, enc = read_text(filepath)
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
