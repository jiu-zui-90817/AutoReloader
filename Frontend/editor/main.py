"""MO / YR INI Editor - 入口（AutoReloader 附带工具）

打包失败时最关键：进程是否进入 Python。
本文件在任何 import 之前就把日志写到多个位置，避免「EXIT:0 无痕迹」。
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _safe_write(path: Path, msg: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
        return True
    except Exception:
        return False


def _boot_log(msg: str) -> None:
    line = msg.rstrip()
    candidates: list[Path] = []
    try:
        candidates.append(Path(sys.executable).resolve().parent / "INIEditor_boot.log")
    except Exception:
        pass
    try:
        a0p = Path(sys.argv[0]).resolve().parent
        candidates.append(a0p / "INIEditor_boot.log")
        if a0p.name.lower() == "_internal":
            candidates.append(a0p.parent / "INIEditor_boot.log")
    except Exception:
        pass
    try:
        candidates.append(Path.cwd() / "INIEditor_boot.log")
    except Exception:
        pass
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        candidates.append(Path(temp) / "INIEditor_boot.log")
    desk = os.environ.get("USERPROFILE")
    if desk:
        candidates.append(Path(desk) / "Desktop" / "INIEditor_boot.log")
    seen: set[str] = set()
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if _safe_write(p, line):
            break


def _exe_dir() -> Path:
    """真 exe 所在目录（_internal），用于 Qt 插件路径。"""
    try:
        a0 = Path(sys.argv[0]).resolve()
        if a0.suffix.lower() == ".exe" and a0.is_file():
            return a0.parent
    except Exception:
        pass
    try:
        p = Path(sys.executable).resolve()
        if p.name.lower() in ("python.exe", "pythonw.exe", "python", "python3"):
            try:
                a0 = Path(sys.argv[0]).resolve()
                if a0.parent.is_dir():
                    return a0.parent
            except Exception:
                pass
        parent = p.parent
        s = str(parent).replace("\\", "/").lower()
        if any(x in s for x in ("/temp/", "/tmp/", "onefile_", "_mei", "nuitka_temp")):
            try:
                return Path(sys.argv[0]).resolve().parent
            except Exception:
                pass
        return parent
    except Exception:
        return Path.cwd()


def _mark_frozen_if_nuitka() -> None:
    try:
        if getattr(sys, "frozen", False):
            return
        for _name, mod in list(sys.modules.items()):
            if mod is not None and getattr(mod, "__compiled__", None) is not None:
                sys.frozen = True  # type: ignore[attr-defined]
                return
        a0 = Path(sys.argv[0]).resolve()
        if a0.suffix.lower() == ".exe":
            parent = a0.parent
            if (parent / "PySide6").is_dir() or (parent / "python312.dll").is_file():
                sys.frozen = True  # type: ignore[attr-defined]
    except Exception:
        pass


def _show_error(title: str, text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text[:2000], title, 0x10)
    except Exception:
        print(title, text, file=sys.stderr)


def _write_crash(msg: str) -> Path:
    try:
        a0p = Path(sys.argv[0]).resolve().parent
        path = a0p / "INIEditor_crash.log"
        if a0p.name.lower() == "_internal":
            path = a0p.parent / "INIEditor_crash.log"
        _safe_write(path, msg)
        return path
    except Exception:
        pass
    try:
        path = Path.cwd() / "INIEditor_crash.log"
        _safe_write(path, msg)
        return path
    except Exception:
        pass
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    path = Path(temp) / "INIEditor_crash.log"
    _safe_write(path, msg)
    return path


def _setup_qt_plugins(root: Path) -> None:
    candidates = [
        root / "PySide6" / "qt-plugins",
        root / "PySide6" / "plugins",
        root / "_internal" / "PySide6" / "qt-plugins",
        root / "_internal" / "PySide6" / "plugins",
        root / "plugins",
        root / "qt-plugins",
    ]
    for pc in candidates:
        if not pc.is_dir():
            continue
        platforms = pc / "platforms"
        if platforms.is_dir() or any(pc.rglob("qwindows.dll")):
            os.environ["QT_PLUGIN_PATH"] = str(pc)
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(
                platforms if platforms.is_dir() else pc
            )
            _boot_log(f"QT_PLUGIN_PATH={pc}")
            return
    _boot_log("WARNING: no Qt plugins dir found under " + str(root))


def main() -> None:
    print("INIEditor starting...", flush=True)
    _mark_frozen_if_nuitka()
    _boot_log("===== boot =====")
    _boot_log(f"executable={sys.executable!r}")
    _boot_log(f"argv0={sys.argv[0]!r}")
    _boot_log(f"cwd={Path.cwd()}")
    _boot_log(
        f"frozen={getattr(sys, 'frozen', False)} "
        f"meipass={getattr(sys, '_MEIPASS', None)!r}"
    )

    root = _exe_dir()
    _boot_log(f"exe_dir={root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and meipass not in sys.path:
        sys.path.insert(0, meipass)

    _setup_qt_plugins(root)
    if meipass:
        _setup_qt_plugins(Path(meipass))
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    try:
        from paths import app_dir, config_path as _config_path

        def user_config_path():  # type: ignore
            # 主配置在 Tools（壳旁），禁止落到 AppData/TEMP
            return _config_path()
    except Exception:

        def user_config_path():  # type: ignore
            p = root
            if p.name.lower() == "_internal":
                p = p.parent
            return p / "config.json"

    try:
        _boot_log("importing PySide6...")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        _boot_log("PySide6 OK")
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(f"PySide6 导入失败\nexe_dir={root}\n{tb}")
        _boot_log(f"PySide6 FAIL {e}")
        _show_error("INI 工程编辑器无法启动", f"PySide6/Qt 加载失败。\n\n{e}\n\n详情:\n{log}")
        raise SystemExit(1) from e

    try:
        _boot_log("importing Project/MainWindow...")
        from core.project import Project
        from ui.main_window import MainWindow

        _boot_log("Project/MainWindow OK")
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(
            f"业务模块导入失败\nexe_dir={root}\nsys.path={sys.path[:12]}\n{tb}"
        )
        _boot_log(f"app import FAIL {e}")
        _show_error("INI 工程编辑器无法启动", f"模块导入失败。\n\n{e}\n\n详情:\n{log}")
        raise SystemExit(1) from e

    try:
        _boot_log("creating QApplication...")
        app = QApplication.instance() or QApplication(sys.argv)
        try:
            from PySide6.QtGui import QIcon
            from paths import app_dir, bundle_dir

            for cand in (
                app_dir() / "editor.ico",
                app_dir() / "assets" / "editor.ico",
                bundle_dir() / "editor.ico",
                root / "editor.ico",
                Path(__file__).resolve().parents[2] / "assets" / "editor.ico",
            ):
                if cand.is_file():
                    app.setWindowIcon(QIcon(str(cand)))
                    _boot_log(f"window icon={cand}")
                    break
        except Exception as e:
            _boot_log(f"setWindowIcon skip {e}")
        app.setApplicationName("INI 工程编辑器")
        try:
            app.setStyle("Fusion")
        except Exception as e:
            _boot_log(f"setStyle Fusion FAIL {e}")
        _boot_log("QApplication OK")
        config_path = user_config_path()
        _boot_log(f"config={config_path}")
        _boot_log(f"app_dir try: config exists={config_path.is_file()}")
        if not config_path.is_file():
            for seed in (root / "config.json", root.parent / "config.json"):
                try:
                    if seed.is_file() and seed.resolve() != config_path.resolve():
                        config_path.parent.mkdir(parents=True, exist_ok=True)
                        import shutil

                        shutil.copy2(seed, config_path)
                        _boot_log(f"seeded config from {seed}")
                        break
                except Exception as e:
                    _boot_log(f"seed skip {e}")
        _boot_log("creating Project...")
        project = Project(config_path)
        _boot_log("Project OK")
        _boot_log("creating MainWindow...")
        win = MainWindow(project)
        _boot_log("MainWindow OK")
        win.show()
        _boot_log("window shown")
        try:
            win.statusBar().showMessage(f"配置: {config_path}", 8000)
        except Exception:
            pass
        try:
            st = win.project.config.get("settings") or {}
            last = st.get("last_project_dir") or ""
            if last and Path(last).is_dir():
                QTimer.singleShot(200, lambda: win.open_project(last))
        except Exception:
            pass
        code = app.exec()
        _boot_log(f"app.exec exit={code}")
        sys.exit(code)
    except SystemExit:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(f"启动后异常\n{tb}")
        _boot_log(f"runtime FAIL {e}")
        _show_error("INI 工程编辑器崩溃", f"{e}\n\n{log}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    try:
        print("__main__ enter", flush=True)
        main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        _boot_log(f"SystemExit code={code}")
        raise
    except Exception:
        tb = traceback.format_exc()
        log = _write_crash(tb)
        _boot_log("fatal\n" + tb)
        _show_error("INI 工程编辑器崩溃", f"未捕获异常\n{log}")
        raise SystemExit(1)
