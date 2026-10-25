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
    """多路径写日志：exe 旁 / cwd / TEMP / Desktop，保证总能找到痕迹。"""
    line = msg.rstrip()
    candidates: list[Path] = []
    try:
        candidates.append(Path(sys.executable).resolve().parent / "INIEditor_boot.log")
    except Exception:
        pass
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent / "INIEditor_boot.log")
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
    """用户双击的目录。Nuitka standalone 下 sys.executable 有时是同目录 python.exe，优先 argv[0]。"""
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
    """Nuitka 不设 sys.frozen；业务代码大量依赖它，启动时补上。"""
    if getattr(sys, "frozen", False):
        return
    try:
        import __main__

        if getattr(__main__, "__compiled__", None) is not None:
            sys.frozen = True  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    try:
        root = _exe_dir()
        if (root / "PySide6").is_dir() or (root / "_internal" / "PySide6").is_dir():
            sys.frozen = True  # type: ignore[attr-defined]
    except Exception:
        pass


def _write_crash(msg: str) -> Path:
    path = _exe_dir() / "INIEditor_crash.log"
    try:
        path.write_text(msg, encoding="utf-8")
        return path
    except Exception:
        pass
    try:
        path = Path.cwd() / "INIEditor_crash.log"
        path.write_text(msg, encoding="utf-8")
        return path
    except Exception:
        pass
    temp = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    path = Path(temp) / "INIEditor_crash.log"
    try:
        path.write_text(msg, encoding="utf-8")
    except Exception:
        pass
    return path


def _show_error(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text[:1500], title, 0x10)
        return
    except Exception:
        pass
    try:
        print(title, text, file=sys.stderr)
    except Exception:
        pass


def _setup_qt_plugins(root: Path) -> None:
    """为 PyInstaller onedir / Nuitka standalone 设置 Qt 插件路径。"""
    candidates = [
        root / "_internal" / "PySide6" / "plugins",
        root / "_internal" / "PySide6" / "qt-plugins",
        root / "PySide6" / "plugins",
        root / "PySide6" / "qt-plugins",
        root / "qt-plugins",
        root / "plugins",
        root / "_internal" / "plugins",
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
        from paths import user_config_path
    except Exception:
        def user_config_path():  # type: ignore
            return root / "config.json"

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
        _show_error("INI 工程编辑器崩溃", f"{e}\n\n详情:\n{log}")
        raise SystemExit(1) from e


if __name__ == "__main__":
    try:
        _boot_log("__main__ enter")
        main()
    except SystemExit as e:
        _boot_log(f"SystemExit {getattr(e, 'code', e)}")
        raise
    except Exception:
        tb = traceback.format_exc()
        log = _write_crash(tb)
        _boot_log("uncaught\n" + tb)
        _show_error("INI 工程编辑器无法启动", f"未捕获异常。\n详情:\n{log}")
        raise
