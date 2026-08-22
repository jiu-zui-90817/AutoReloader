"""编辑器路径辅助：单文件(Nuitka)下可写数据必须离开临时解压目录。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    """识别 PyInstaller / Nuitka 打包运行（含 onefile 临时目录）。"""
    if getattr(sys, "frozen", False):
        return True
    # Nuitka 编译标记
    try:
        import __main__
        if getattr(__main__, "__compiled__", None) is not None:
            return True
    except Exception:
        pass
    # Nuitka onefile 会把运行目录放到临时路径
    try:
        f = Path(__file__).resolve()
        s = str(f).replace("\\", "/").lower()
        if "onefile_" in s or "/onefile/" in s:
            return True
    except Exception:
        pass
    # 环境变量（Nuitka onefile 父进程）
    if os.environ.get("NUITKA_ONEFILE_PARENT"):
        return True
    return False


def app_dir() -> Path:
    """用户可见的程序目录：打包后为 exe 所在目录，源码为 Frontend/editor。"""
    if is_frozen():
        # sys.executable 在 Nuitka/PyInstaller onefile 下指向真实 exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """只读资源：onefile 解压目录或源码目录。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        # Nuitka onefile：__file__ 常在临时目录，适合读内置资源
        try:
            return Path(__file__).resolve().parent
        except Exception:
            return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _ensure_writable_dir(d: Path) -> bool:
    try:
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".w"
        probe.write_text("1", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def user_data_dir() -> Path:
    """
    可写数据根目录（config / cache）。
    优先 exe 旁；不可写则用 %LocalAppData%\\MO_INI_Editor。
    """
    candidates = [
        app_dir(),
        Path.home() / "AppData" / "Local" / "MO_INI_Editor",
        Path.home() / ".mo_ini_editor",
    ]
    for d in candidates:
        if _ensure_writable_dir(d):
            return d
    return candidates[-1]


def user_config_path() -> Path:
    """
    用户可写 config.json（含 last_project_dir 等）。
    绝不写到 onefile 临时目录。
    """
    data = user_data_dir()
    path = data / "config.json"
    bundled = bundle_dir() / "config.json"
    if not path.is_file() and bundled.is_file():
        try:
            shutil.copy2(bundled, path)
        except Exception:
            pass
    return path


def user_cache_dir() -> Path:
    d = user_data_dir() / "cache"
    _ensure_writable_dir(d)
    return d
