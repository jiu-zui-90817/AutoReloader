"""
战术工坊 2.x 入口（占位）。

下一步：接入 shared，实现「选择游戏目录 → 列出单位 → 部署 hotfix」。
当前请继续使用 Frontend/TacticalConsole.py（旧版）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 仓库根目录加入 path，便于 import shared
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> None:
    print("战术工坊 2.x 尚未实现。")
    print("请暂时使用: Frontend/TacticalConsole.py")
    print(f"仓库根目录: {_ROOT}")
    try:
        import shared  # noqa: F401
        print("shared 包: 可导入")
    except ImportError as e:
        print(f"shared 包: 导入失败 ({e})")
    sys.exit(0)


if __name__ == "__main__":
    main()
