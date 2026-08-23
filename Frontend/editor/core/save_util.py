"""
保存与自动备份 —— 尽量稳健的按 section 写回
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
    """
    规范为单一 section 文本：
      [ID]
      key=value
      ...
    - 去掉工具提示行
    - 多个同名 [ID] 只保留第一段
    - 头前注释不会再触发“缺头就再插一个 [ID]”
    """
    lines_in = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("; 来源:") or s.startswith("; 来源："):
            continue
        lines_in.append(ln.rstrip())
    text = "\n".join(lines_in).strip("\n")
    if not text.strip():
        return f"[{section_id}]\n"

    header_re = re.compile(
        rf"(?im)^\[{re.escape(section_id)}(?:\s*:[^\]]*)?\]\s*$"
    )
    matches = list(header_re.finditer(text))
    if matches:
        start = matches[0].start()
        preamble = text[:start].strip("\n")
        rest = text[matches[0].end() :]
        next_hdr = re.search(r"(?m)^\[", rest)
        chunk = rest[: next_hdr.start()] if next_hdr else rest
        body_lines = [f"[{section_id}]"]
        if preamble:
            for ln in preamble.splitlines():
                st = ln.strip()
                if not st or (st.startswith("[") and st.endswith("]")):
                    continue
                body_lines.append(ln)
        for ln in chunk.splitlines():
            st = ln.strip()
            if st.startswith("[") and st.endswith("]"):
                break
            body_lines.append(ln.rstrip())
        text = "\n".join(body_lines)
    else:
        body_lines = [f"[{section_id}]"]
        for ln in text.splitlines():
            st = ln.strip()
            if st.startswith("[") and st.endswith("]"):
                continue
            body_lines.append(ln.rstrip())
        text = "\n".join(body_lines)

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
