# Frontend — 热重载前端工具

| 路径 | 说明 | 状态 |
|------|------|------|
| `workshop/` | **战术工坊 2.x**：快调 + hotfix，读工程/CSF，不依赖 Codex | 可用 |
| `editor/` | **INI 工程编辑器**：对象树、全文编辑、保存回源、调试 | 可用 |
| `TacticalConsole.py` | 经典战术工坊（当前保留） | 需 Codex |
| `CodexGenerator.py` | 经典工坊词典生成（当前保留） | 仅旧流程 |

公共逻辑在仓库根目录 **`shared/`**。

## 运行

```bash
# 工坊 2.x（在仓库根）
pip install -r Frontend/workshop/requirements.txt
python Frontend/workshop/main.py

# 编辑器
pip install -r Frontend/editor/requirements.txt
python Frontend/editor/main.py
```

打包见仓库根 README 与 `.github/workflows/`。
