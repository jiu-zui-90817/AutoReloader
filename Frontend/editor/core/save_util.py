"""
保存与自动备份 —— 尽量稳健的按 section 写回
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List


def backup_file(filepath: Path, backup_root: Path, keep: int = 100) -> Path:
    """备份到 backup_root/<原文件名>/ ，并只保留最近 keep 份（0=不限制）。"""
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(str(filepath))
    backup_root = Path(backup_root)
    sub = backup_root / filepath.name
    sub.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = sub / f"{filepath.stem}_{stamp}{filepath.suffix}"
    n = 1
    while dest.exists():
        dest = sub / f"{filepath.stem}_{stamp}_{n}{filepath.suffix}"
        n += 1
    shutil.copy2(filepath, dest)
    if keep and keep > 0:
        try:
            files = sorted(
                [p for p in sub.iterdir() if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in files[int(keep):]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except OSError:
            pass
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
    backup_keep: int = 100,
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
            bak = backup_file(filepath, backup_root, keep=backup_keep)
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


def save_type_list_distributed(
    section_id: str,
    section,
    backup_root: Path,
) -> dict:
    """
    将合并后的类型注册表按 key_sources 拆回各来源文件。
    每个文件只写回「属于该文件」的键，避免把其它拆分文件的条目写进一个文件。
    """
    from collections import OrderedDict

    result = {"ok": False, "message": "", "files": []}
    if not section or not getattr(section, "key_order", None):
        result["message"] = "空注册表"
        return result

    by_file: dict = {}
    unknown = []
    for k in section.key_order:
        src = (section.key_sources or {}).get(k) or section.source_file or ""
        if not src:
            unknown.append(k)
            continue
        by_file.setdefault(str(src), []).append(k)

    if unknown and by_file:
        # 无来源的键：并入「出现次数最多的文件」或第一个
        primary = max(by_file.keys(), key=lambda p: len(by_file[p]))
        by_file[primary].extend(unknown)
        unknown = []
    elif unknown and not by_file:
        result["message"] = "注册表条目缺少来源文件信息，拒绝整表写回以防串文件"
        return result

    messages = []
    for fpath, keys in by_file.items():
        path = Path(fpath)
        if not path.is_file():
            # 尝试仅文件名：由调用方应传入绝对路径
            messages.append(f"跳过不存在的文件: {fpath}")
            continue
        # 构造仅含本文件键的节文本
        lines = [f"[{section_id}]"]
        for k in keys:
            val = section.keys.get(k, "")
            cmt = (section.inline_comments or {}).get(k, "")
            out_key = "+=" if str(k).startswith("+@") else k
            if out_key == "+=":
                line = f"+={val}"
            else:
                line = f"{out_key}={val}"
            if cmt:
                line += f" ;{cmt}"
            lines.append(line)
        body = "\n".join(lines)
        r = save_section_to_file(
            path,
            section_id,
            body,
            backup_root=backup_root,
            is_new=False,
            peer_section_names=[],
        )
        result["files"].append({"path": str(path), "ok": r.get("ok"), "msg": r.get("message")})
        messages.append(r.get("message") or str(path))
        if not r.get("ok"):
            result["message"] = "；".join(messages)
            return result

    result["ok"] = True
    result["message"] = "；".join(messages) if messages else "OK"
    return result
