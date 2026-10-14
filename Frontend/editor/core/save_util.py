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


def detect_newline(text: str) -> str:
    """沿用原文件换行风格，避免整文件被改成 \\n 后出现‘空行错乱’观感。"""
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text and "\n" not in text:
        return "\r"
    return "\n"


def to_newlines(text: str, nl: str) -> str:
    """把任意换行统一成目标 nl（先摊成 \\n 再替换）。"""
    if not text:
        return text
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    if nl == "\n":
        return unified
    return unified.replace("\n", nl)


def find_section_span(text: str, section_name: str) -> Optional[Tuple[int, int]]:
    """
    定位第一个 [section_name] … 下一节之前。
    节头允许行尾注释；兼容 CRLF。
    """
    # [Name] 或 [Name:xxx] ，同一行其余内容（注释）忽略
    pattern = re.compile(
        rf"(?im)^\[{re.escape(section_name)}(?:\s*:[^\]]*)?\][^\r\n]*(?:\r\n|\n|\r)?"
    )
    m = pattern.search(text)
    if not m:
        return None
    start = m.start()
    rest = text[m.end() :]
    # 下一节：行首 [
    next_sec = re.search(r"(?m)^\[", rest)
    if next_sec:
        end = m.end() + next_sec.start()
    else:
        end = len(text)
    return start, end


def _ensure_section_body(body: str, nl: str = "\n") -> str:
    """节正文：统一换行 + 末尾恰好一个 nl（不含节后空行）。"""
    unified = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    # 去掉末尾多余空行，保留内容
    unified = unified.rstrip("\n") + "\n"
    return to_newlines(unified, nl)


def _join_section_and_rest(body: str, rest: str, nl: str = "\n") -> str:
    """
    节正文 + 后文。
    若后文下一有效内容是 [Section]，中间恰好一个空行（即两个 nl）。
    """
    body = _ensure_section_body(body, nl=nl)
    if not rest:
        return body
    i = 0
    n = len(rest)
    while i < n and rest[i] in "\r\n":
        i += 1
    rest_core = rest[i:]
    if not rest_core:
        return body
    if rest_core.lstrip(" \t").startswith("["):
        # body 已以 nl 结尾，再补一个 nl → 一个空行
        return body + nl + rest_core
    return body + rest_core


def replace_section_in_text(text: str, section_name: str, new_body: str) -> Tuple[str, bool]:
    span = find_section_span(text, section_name)
    if span is None:
        return text, False
    start, end = span
    nl = detect_newline(text)
    body = _ensure_section_body(new_body, nl=nl)
    return text[:start] + _join_section_and_rest(body, text[end:], nl=nl), True


def append_section_after_peers(text: str, new_body: str, peer_names: List[str]) -> str:
    nl = detect_newline(text) if text else "\n"
    body = _ensure_section_body(new_body, nl=nl)
    last_end = -1
    for name in peer_names:
        span = find_section_span(text, name)
        if span:
            last_end = span[1]
    if last_end >= 0:
        return text[:last_end] + _join_section_and_rest(body, text[last_end:], nl=nl)
    base = text or ""
    if base and not base.endswith(("\n", "\r")):
        base += nl
    if base.strip():
        # 文件末尾追加：与最后内容之间一个空行
        core = base.rstrip("\r\n")
        return core + nl + nl + body
    return body


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
        # 新增前再确认文件中确实没有该节，避免拆分工程里重复 [Section]
        if filepath.exists() and text:
            if find_section_span(text, section_name) is not None:
                result["message"] = (
                    f"拒绝新增：{filepath.name} 中已存在 [{section_name}]，"
                    f"请改为原地保存，避免重复节块"
                )
                return result
        text = append_section_after_peers(text, body, peer_section_names or [])
        action = "新增写入"
    else:
        text2, found = replace_section_in_text(text, section_name, body)
        if found:
            text = text2
            action = "原地替换"
        else:
            # 拆分工程中「未找到」时绝不能默默追加，否则易出现双份 [E1]
            result["message"] = (
                f"拒绝写入：在 {filepath.name} 中未找到 [{section_name}] 原块。"
                f"未执行追加，以免产生重复节或写错文件。"
            )
            return result

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
