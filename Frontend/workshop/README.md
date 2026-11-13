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
- 「单位转换指令…」：
  - 目标显示中文名，可搜索；只列出同类别、同水域/陆地的类型（海军→海军、陆军→陆军）；
  - 可手动勾选反向转换（默认关闭），让已有单位重新读取配置并保留编组/指令；
  - 自动替换源类型的旧 `Convert` 映射，并对指向源类型的旧映射提示链式转换风险
- 游戏路径/偏好保存在 `%LOCALAPPDATA%\AutoReloader\TacticalWorkshop\console_config.json`，覆盖更新不会丢失

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
