"""编辑器路径：Nuitka onefile 下禁止把配置写到临时解压目录。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _path_str(p: Path | str) -> str:
    return str(p).replace("\\", "/").lower()


def _is_ephemeral(path: Path) -> bool:
    """临时目录 / onefile 解压目录不可用于持久配置。"""
    s = _path_str(path)
    needles = (
        "/temp/",
        "/tmp/",
        "/temps/",
        "appdata/local/temp",
        "onefile_",
        "/onefile/",
        "nuitka_temp",
        "\\temp\\",
    )
    return any(n in s for n in needles)


def is_frozen() -> bool:
    if getattr(sys, "frozen", False):
        return True
    if os.environ.get("NUITKA_ONEFILE_PARENT"):
        return True
    # Nuitka 在模块上挂 __compiled__
    try:
        import __main__
        if getattr(__main__, "__compiled__", None) is not None:
            return True
    except Exception:
        pass
    try:
        if globals().get("__compiled__") is not None:
            return True
    except Exception:
        pass
    # 运行中的 __file__ 落在临时目录 → 视为打包
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
    # 极端回退
    return Path.home() / "AppData" / "Local"


def app_dir() -> Path:
    """
    程序目录（用户放置 exe 的地方）。
    打包：sys.executable 所在目录；源码：Frontend/editor。
    """
    if is_frozen():
        # Nuitka/PyInstaller：executable 指向真实 exe
        exe = Path(sys.executable).resolve()
        parent = exe.parent
        if not _is_ephemeral(parent):
            return parent
        # 万一 executable 也在临时目录，试 argv[0]
        try:
            a0 = Path(sys.argv[0]).resolve()
            if a0.suffix.lower() == ".exe" and not _is_ephemeral(a0.parent):
                return a0.parent
        except Exception:
            pass
        return parent
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
    """
    可写数据根：config / cache。
    1) exe 旁（非临时且可写）
    2) %LOCALAPPDATA%\\MO_INI_Editor  （强制创建）
    3) ~/.mo_ini_editor
    """
    candidates: list[Path] = []
    ad = app_dir()
    if not _is_ephemeral(ad):
        candidates.append(ad)
    candidates.append(local_appdata() / "MO_INI_Editor")
    candidates.append(Path.home() / ".mo_ini_editor")

    for d in candidates:
        if _is_ephemeral(d):
            continue
        if _ensure_writable_dir(d):
            return d
    # 最后一搏：仍返回 LocalAppData 路径（即使探测失败，调用方再试写）
    fallback = local_appdata() / "MO_INI_Editor"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return fallback


def user_config_path() -> Path:
    """用户 config.json（含 last_project_dir）。永不落在临时目录。"""
    data = user_data_dir()
    path = data / "config.json"
    bundled = bundle_dir() / "config.json"
    if not path.is_file():
        # 再试 exe 旁的默认 config（发布包里常有）
        side = app_dir() / "config.json"
        src = None
        if bundled.is_file():
            src = bundled
        elif side.is_file() and not _is_ephemeral(side):
            src = side
        if src is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, path)
            except Exception:
                pass
    return path


def user_cache_dir() -> Path:
    d = user_data_dir() / "cache"
    _ensure_writable_dir(d)
    return d


def describe_paths() -> str:
    """调试用：当前解析到的路径。"""
    return (
        f"frozen={is_frozen()}\n"
        f"executable={sys.executable}\n"
        f"app_dir={app_dir()}\n"
        f"bundle_dir={bundle_dir()}\n"
        f"user_data={user_data_dir()}\n"
        f"config={user_config_path()}\n"
        f"LOCALAPPDATA={os.environ.get('LOCALAPPDATA', '')}\n"
    )
