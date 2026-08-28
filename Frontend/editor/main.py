"""MO / YR INI Editor - 入口（AutoReloader 附带工具）"""
from __future__ import annotations

import sys
from pathlib import Path

from paths import app_dir, user_config_path, describe_paths, user_data_dir

ROOT = app_dir()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from core.project import Project
from ui.main_window import MainWindow


def main() -> None:
    """
    入口独立实现，避免 run_app() 在 frozen 时用 __file__ 指向临时目录写 config。
    用户配置固定落到 exe 旁或 AppData，单文件 Nuitka 下上次工程路径可持久。
    """
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


if __name__ == "__main__":
    main()
