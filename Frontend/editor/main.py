"""MO / YR INI Editor - 入口（AutoReloader 附带工具）"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _exe_dir() -> Path:
    """用户双击的 exe 所在目录（不是临时目录）。"""
    try:
        p = Path(sys.executable).resolve().parent
        s = str(p).replace("\\", "/").lower()
        if any(x in s for x in ("/temp/", "/tmp/", "onefile_", "nuitka_temp")):
            try:
                return Path(sys.argv[0]).resolve().parent
            except Exception:
                pass
        return p
    except Exception:
        return Path.cwd()


def _boot_log(msg: str) -> None:
    """最早日志：即使 Qt 起不来也能看见进程有没有进来。"""
    try:
        p = _exe_dir() / "INIEditor_boot.log"
        with p.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        try:
            with open("INIEditor_boot.log", "a", encoding="utf-8") as f:
                f.write(msg.rstrip() + "\n")
        except Exception:
            pass


def _crash_log_path() -> Path:
    return _exe_dir() / "INIEditor_crash.log"


def _write_crash(msg: str) -> Path:
    path = _crash_log_path()
    try:
        path.write_text(msg, encoding="utf-8")
    except Exception:
        try:
            path = Path.cwd() / "INIEditor_crash.log"
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


def main() -> None:
    print("INIEditor starting...", flush=True)
    _boot_log(f"boot start executable={sys.executable!r} argv0={sys.argv[0]!r}")
    _boot_log(f"exe_dir={_exe_dir()}")
    _boot_log(f"cwd={Path.cwd()}")

    root = _exe_dir()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    plugin_candidates = [
        root / "PySide6" / "qt-plugins",
        root / "PySide6" / "plugins",
        root / "qt-plugins",
        root / "plugins",
    ]
    for pc in plugin_candidates:
        if pc.is_dir():
            os.environ.setdefault("QT_PLUGIN_PATH", str(pc))
            _boot_log(f"QT_PLUGIN_PATH={pc}")
            break

    try:
        from paths import user_config_path
    except Exception:
        def user_config_path():
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
        log = _write_crash(f"业务模块导入失败\nexe_dir={root}\nsys.path={sys.path[:8]}\n{tb}")
        _boot_log(f"app import FAIL {e}")
        _show_error("INI 工程编辑器无法启动", f"模块导入失败。\n\n{e}\n\n详情:\n{log}")
        raise SystemExit(1) from e

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("INI 工程编辑器")
        app.setStyle("Fusion")
        config_path = user_config_path()
        _boot_log(f"config={config_path}")
        win = MainWindow(Project(config_path))
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
