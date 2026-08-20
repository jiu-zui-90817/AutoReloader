# 战术工坊 (Workshop) 2.x

经典快调前端：选单位 → 改常用参数 → 部署 `hotfix.ini` → AutoReloader 热重载。

**不再依赖** `Codex_ZH.json` / CodexGenerator，直接读游戏目录（rules + `#include` + CSF）。

## 功能

- 打开游戏 / Mod 根目录，按 profile 加载 rules（含 Ares `#include`）与 CSF 中文名
- 对象树：步兵 / 载具 / 飞行器 / 建筑 / 武器 / 弹头…
- 表单：常用字段优先 + section 内其余键动态补全
- 辅助下拉：武器 / 弹头 / 装甲 / 布尔等（可关）
- **安全模式**：仅 `hotfix.ini`；**高级模式**：任意 ini
- 部署、恢复原版（安全模式）、复制完整代码（原版底包 + 修改）
- 部署后自动瘦身（去掉与 rules 完全相同的键）

## 运行

```bash
# 仓库根目录
pip install -r Frontend/workshop/requirements.txt
python Frontend/workshop/main.py
```

旧版仍可用：`Frontend/TacticalConsole.py`（需 Codex_ZH.json）。

## 打包（单文件）

在仓库根目录、Windows 上：

```bash
pip install pyinstaller PySide6
pyinstaller --noconfirm --clean --onefile --windowed ^
  --name TacticalWorkshop ^
  --paths . ^
  --hidden-import shared.ini_loader ^
  --hidden-import shared.csf_loader ^
  --hidden-import shared.hotfix_io ^
  --hidden-import shared.project_scan ^
  --add-data "shared/profiles.json;shared" ^
  Frontend/workshop/main.py
```

生成 `dist/TacticalWorkshop.exe`。配置写在 exe 旁 `workshop_config.json`。

## 与编辑器的关系

| | 战术工坊 | INI 编辑器 |
|--|----------|------------|
| 定位 | 快调 + 热重载 | 工程编辑 |
| 依赖 | `shared/` | `Frontend/editor/core` |
| 打包 | **单文件** | 单文件或目录 |
