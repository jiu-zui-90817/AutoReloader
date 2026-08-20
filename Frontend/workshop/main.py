"""
战术工坊 2.x 入口。

源码运行（仓库根目录）:
  python Frontend/workshop/main.py

依赖: PySide6
打包单文件见 README「打包」。
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).resolve().parent
    _HERE = _ROOT

for p in (_ROOT, _HERE):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


def main() -> None:
    from app import run
    run()


if __name__ == "__main__":
    main()
