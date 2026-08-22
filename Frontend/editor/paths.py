"""编辑器路径辅助：单文件(Nuitka/PyInstaller)下可写数据必须离开临时目录。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """真程序目录：打包后为 exe 所在目录，源码为 Frontend/editor。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """只读资源目录：onefile 时为 _MEIPASS（或等价临时目录）。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def user_config_path() -> Path:
    """
    用户可写 config.json。
    单文件模式下绝不能写到 bundle/临时目录，否则上次路径、首选项会丢失。
    优先：exe 旁 → %LocalAppData%\\MO_INI_Editor → ~/.mo_ini_editor
    若目标尚无文件且 bundle 内有默认 config，则复制一份再返回。
    """
    candidates = [
        app_dir() / "config.json",
        Path.home() / "AppData" / "Local" / "MO_INI_Editor" / "config.json",
        Path.home() / ".mo_ini_editor" / "config.json",
    ]
    bundled = bundle_dir() / "config.json"
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                return path
            if bundled.is_file():
                shutil.copy2(bundled, path)
                return path
            probe = path.parent / ".w"
            probe.write_text("1", encoding="utf-8")
            probe.unlink(missing_ok=True)
            if bundled.is_file() and not path.is_file():
                shutil.copy2(bundled, path)
            return path
        except Exception:
            continue
    return candidates[0]
