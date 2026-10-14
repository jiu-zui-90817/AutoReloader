"""MO / YR INI Editor - 入口（AutoReloader 附带工具）"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _exe_dir() -> Path:
    """用户双击的 exe 所在目录（不是 onefile 临时解压目录）。"""
    try:
        p = Path(sys.executable).resolve().parent
        s = str(p).replace("\\", "/").lower()
        if any(x in s for x in ("/temp/", "/tmp/", "onefile_", "nuitka_temp")):
            # 回退：从 argv[0] 猜真实路径
            try:
                return Path(sys.argv[0]).resolve().parent
            except Exception:
                pass
        return p
    except Exception:
        return Path.cwd()


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
    """无控制台时也能看见错误。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text[:1500], title, 0x10)
        return
    except Exception:
        pass
    try:
        sys.stderr.write(text + "\n")
    except Exception:
        pass


def main() -> None:
    """
    入口独立实现，避免 frozen 时把配置写到临时目录。
    任何启动失败写入 INIEditor_crash.log，并弹窗提示。
    """
    # 保证能 import core / ui（standalone 下与 exe 同目录）
    root = _exe_dir()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        from paths import app_dir, user_config_path
    except Exception:
        # paths 也失败时仍尽量继续
        app_dir = lambda: root  # type: ignore
        user_config_path = lambda: root / "config.json"  # type: ignore

    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(f"PySide6 导入失败\nexe_dir={root}\n{tb}")
        _show_error(
            "INI 工程编辑器无法启动",
            f"PySide6/Qt 加载失败。\n\n{e}\n\n详情已写入:\n{log}\n\n"
            "请确认未单独挪走 exe，整个 Tools 目录需完整。",
        )
        raise SystemExit(1) from e

    try:
        from core.project import Project
        from ui.main_window import MainWindow
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(f"业务模块导入失败\nexe_dir={root}\nsys.path={sys.path[:8]}\n{tb}")
        _show_error(
            "INI 工程编辑器无法启动",
            f"模块导入失败。\n\n{e}\n\n详情已写入:\n{log}",
        )
        raise SystemExit(1) from e

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("INI 工程编辑器")
        app.setStyle("Fusion")
        config_path = user_config_path()
        win = MainWindow(Project(config_path))
        win.show()
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
        sys.exit(app.exec())
    except SystemExit:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        log = _write_crash(f"启动后异常\n{tb}")
        _show_error(
            "INI 工程编辑器崩溃",
            f"{e}\n\n详情已写入:\n{log}",
        )
        raise SystemExit(1) from e


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        log = _write_crash(tb)
        _show_error("INI 工程编辑器无法启动", f"未捕获异常。\n详情:\n{log}")
        raise
