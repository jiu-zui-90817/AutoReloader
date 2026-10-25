"""编辑器路径：Nuitka onefile 下禁止把配置写到临时解压目录。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _path_str(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _is_ephemeral(p: Path) -> bool:
    s = _path_str(p).lower()
    return any(
        x in s
        for x in (
            "/temp/",
            "/tmp/",
            "appdata/local/temp",
            "onefile_",
            "/onefile/",
            "nuitka_temp",
            "_mei",
        )
    )


def is_frozen() -> bool:
    if getattr(sys, "frozen", False):
        return True
    try:
        if getattr(sys, "_MEIPASS", None):
            return True
    except Exception:
        pass
    try:
        for name, mod in list(sys.modules.items()):
            if mod is not None and getattr(mod, "__compiled__", None) is not None:
                return True
    except Exception:
        pass
    try:
        a0 = Path(sys.argv[0]).resolve()
        if a0.suffix.lower() == ".exe":
            parent = a0.parent
            if (parent / "PySide6").is_dir() or (parent / "_internal" / "PySide6").is_dir():
                return True
    except Exception:
        pass
    try:
        if _is_ephemeral(Path(__file__).resolve().parent):
            return True
    except Exception:
        pass
    try:
        main = getattr(sys.modules.get("__main__"), "__file__", None)
        if main and _is_ephemeral(Path(main).resolve().parent):
            return True
    except Exception:
        pass
    return False


def local_appdata() -> Path:
    env = os.environ.get("LOCALAPPDATA") or os.environ.get("LocalAppData")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Local"


def _prefer_tools_dir(folder: Path) -> Path:
    """Nuitka 真身在 Tools/_internal 时，配置/图标目录用 Tools。"""
    try:
        if folder.name.lower() == "_internal" and folder.parent.is_dir():
            return folder.parent
    except Exception:
        pass
    return folder


def app_dir() -> Path:
    """
    程序目录（用户放置启动器的地方）。
    打包：优先 argv[0]；若在 _internal 内则上提到 Tools。
    """
    if is_frozen():
        try:
            a0 = Path(sys.argv[0]).resolve()
            if a0.suffix.lower() == ".exe" and not _is_ephemeral(a0.parent):
                return _prefer_tools_dir(a0.parent)
        except Exception:
            pass
        exe = Path(sys.executable).resolve()
        parent = exe.parent
        if exe.name.lower() in ("python.exe", "pythonw.exe", "python", "python3"):
            try:
                a0 = Path(sys.argv[0]).resolve()
                if not _is_ephemeral(a0.parent):
                    return _prefer_tools_dir(a0.parent)
            except Exception:
                pass
        if not _is_ephemeral(parent):
            return _prefer_tools_dir(parent)
        return _prefer_tools_dir(parent)
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """只读内置资源目录。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        try:
            return Path(__file__).resolve().parent
        except Exception:
            return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return app_dir() / "config.json"


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
