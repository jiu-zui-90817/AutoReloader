"""编辑器路径：Nuitka onefile 下禁止把配置写到临时解压目录。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _path_str(p: Path | str) -> str:
    return str(p).replace("\\", "/")


def _is_ephemeral(path: Path) -> bool:
    s = _path_str(path).lower()
    needles = (
        "/temp/",
        "/tmp/",
        "\\temp\\",
        "appdata/local/temp",
        "appdata\\local\\temp",
        "onefile_",
        "/onefile/",
        "nuitka_temp",
        "_mei",
    )
    return any(n in s for n in needles)


def is_frozen() -> bool:
    if getattr(sys, "frozen", False):
        return True
    try:
        if getattr(sys, "_MEIPASS", None):
            return True
    except Exception:
        pass
    try:
        for _name, mod in list(sys.modules.items()):
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
    """真正的 %LocalAppData%，不要用 home/AppData 猜。"""
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
            return app_dir()
    return Path(__file__).resolve().parent


def _ensure_writable_dir(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def user_data_dir() -> Path:
    """可写用户数据目录。"""
    base = local_appdata() / "AutoReloader" / "INIEditor"
    if _ensure_writable_dir(base):
        return base
    fallback = Path.home() / ".autoreloader" / "inieditor"
    _ensure_writable_dir(fallback)
    return fallback


def user_config_path() -> Path:
    """用户级 config 备份路径（主 config 仍在 app_dir）。"""
    return user_data_dir() / "config.user.json"


def user_cache_dir() -> Path:
    d = user_data_dir() / "cache"
    _ensure_writable_dir(d)
    return d


def describe_paths() -> str:
    lines = [
        f"frozen={is_frozen()}",
        f"app_dir={app_dir()}",
        f"bundle_dir={bundle_dir()}",
        f"user_data={user_data_dir()}",
    ]
    return "\n".join(lines)
