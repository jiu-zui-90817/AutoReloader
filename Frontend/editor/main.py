"""MO / YR INI Editor - 入口（AutoReloader 附带工具）"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.main_window import run_app

if __name__ == "__main__":
    run_app()
