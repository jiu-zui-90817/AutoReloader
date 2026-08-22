# YR/MO Hot Reloader Toolchain（红警2 / 心灵终结 热重载工具链）

一套面向 **红警2：尤里的复仇 (YR)** 与 **心灵终结 (Mental Omega)** 的前后端分离式动态热重载工具链。

## 组成

1. **后端注入引擎 (`AutoReloader.dll`)**：基于 YRpp，游戏运行中监测并写入 INI 属性。  
2. **前端工具（`Frontend/`）**
   - **战术工坊 2.x**（`Frontend/workshop/`）：快调常用参数 → 部署 `hotfix.ini`；**不再依赖** Codex 词典。  
   - **经典战术工坊**（`Frontend/TacticalConsole.py`，若仓库中仍保留）：旧版入口，需 `Codex_ZH.json`。  
   - **INI 工程编辑器**（`Frontend/editor/`）：工程级浏览/编辑/保存，附带单单位调试与 hotfix 部署。  
3. **公共逻辑（`shared/`）**：INI / Ares `#include`、CSF、hotfix 写回、词典构建、profile 与属性说明。

**版本号与 GitHub Release 以本仓库（AutoReloader）为准。**

---

## 仓库目录

```text
Backend/                  # 注入 DLL 源码
Launcher/                 # MOInjector / YRInjector
shared/                   # 工坊与编辑器共用逻辑与 schemas
Frontend/
  workshop/               # 战术工坊 2.x（推荐）
  editor/                 # INI 工程编辑器
docs/frontend-roadmap.md
.github/workflows/        # Windows 双打包（若启用 CI）
```

---

## 快速上手

### 1. 后端

1. 从 [Releases](../../releases) 下载整合包。  
2. 将 `AutoReloader.dll`、`ReloaderConfig.ini`、`MOInjector.exe` 放入游戏根目录。  
3. **必须用 `MOInjector.exe` 启动游戏**。

### 2. 战术工坊 2.x（推荐）

```bash
pip install -r Frontend/workshop/requirements.txt
python Frontend/workshop/main.py
```

打开游戏/Mod 根目录即可；显示名与列表由 rules + CSF 生成，可「重建词典」。

### 3. INI 工程编辑器

```bash
pip install -r Frontend/editor/requirements.txt
python Frontend/editor/main.py
```

对象树 + CSF 中文名、Ares `#include`、按源文件保存与备份、属性说明、单单位调试部署 hotfix。详见 `Frontend/editor/README.md`。

---

## 标准调试流程

1. 在工坊或编辑器中改参数。  
2. 部署到 `hotfix.ini`（安全模式）或写回工程源文件。  
3. 游戏内热键（默认 F5）或 AutoMonitor 触发重载。  
4. 需要时用前端瘦身/恢复逻辑清理脏数据。

---

## 打包与词典说明

- GitHub Actions（若已配置）：编辑器 / 工坊可出 PyInstaller、Nuitka 单文件包。  
- 属性说明唯一源：`shared/schemas/common_flags.json`（构建时同步到各工具 `schemas/`）。  
- 本地日常只改这一份即可。

---

## 许可证

见 `LICENSE`。
