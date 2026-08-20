# YR/MO Hot Reloader Toolchain (红警2/心灵终结 热重载工具链)

一套专为 **红警2：尤里的复仇 (YR)** 及 **心灵终结 (Mental Omega)** 开发的**前后端分离式动态热重载工具链**。

本工具链由以下部分组成：

1. **后端注入引擎 (AutoReloader.dll)**：基于 `YRpp` 开发的独立注入组件，可在游戏运行中监测并写入 INI 属性。
2. **前端工具（本仓库 Frontend）**
   - **战术工坊**：经典快调（部署 hotfix）；2.x 升级中，目标为不再依赖 Codex 词典。
   - **INI 工程编辑器**：附带工具（工程级编辑），源码将迁入 `Frontend/editor/`。

版本号与 **GitHub Release 以本仓库（AutoReloader）为准**。

本项目针对心灵终结 (MO) 的调试需求做了适配，支持复杂视觉与特效（AE）相关参数的热重载预览。

---

## 仓库目录（前端相关）

```text
shared/                 # 工坊与编辑器共用逻辑（建设中）
Frontend/
  TacticalConsole.py    # 当前可用的经典工坊（需 Codex_ZH.json）
  CodexGenerator.py     # 词典生成器（将逐步废弃）
  workshop/             # 战术工坊 2.x（新入口，建设中）
  editor/               # INI 编辑器迁入位置（占位）
  legacy/               # 旧版说明
docs/frontend-roadmap.md
```

---

## 🚀 核心特性

- **开箱即用**：预编译组件与前端工具，配合专用启动器部署热重载环境。
- **全要素图纸覆盖**：作战单位、武器/弹头/抛射体、MO 特效（动画/粒子等）等类型的动态覆写。
- **状态同步与数据回滚**：前端支持基准重置与补丁清理，降低脏数据风险。
- **与 TargetINI 配合**：默认监控 `hotfix.ini` 等，见下方配置说明。

---

## 📥 快速上手指引

### 1. 部署后端注入引擎

1. 前往 [Releases](../../releases) 下载整合包。
2. 将 `AutoReloader.dll`、`ReloaderConfig.ini`、`MOInjector.exe` 放入游戏根目录。
3. **必须使用 `MOInjector.exe` 启动游戏**。

### 2. 启动前端（当前）

**经典战术工坊（现可用）：**

1. 使用 `CodexGenerator.py` 生成 `Codex_ZH.json`，或使用已有词典。
2. 运行 `Frontend/TacticalConsole.py`。
3. 建议与 `rulesmo.ini` 同目录，以便回滚与清理。

**战术工坊 2.x / 现代编辑器：** 开发中，见 `Frontend/workshop/`、`docs/frontend-roadmap.md`。编辑器源码暂在 [mo_ini_editor](https://github.com/jiu-zui-90817/mo_ini_editor)。

---

## 💻 标准调试工作流

1. **修改参数**：在工坊表单或代码预览中调整。
2. **保存部署**：写入 `hotfix.ini`（安全模式下的工程文件）。
3. **触发重载**：游戏内热键（默认 F5）或 AutoMonitor。
4. **自动清理**：前端可按底包对比去掉冗余键。
5. **恢复默认**：安全模式下可恢复原版属性后再部署。

---

## ⚙️ 配置文件说明 (`ReloaderConfig.ini`)

```ini
[Settings]
AutoMonitor=true
HotKey=116
ShowConsole=true
TargetINI=hotfix.ini, ae_effects.ini
```

---

## 🛠️ 编译指引 (C++ / 后端)

- **环境**: Visual Studio 2019 / 2022
- **YRpp**: 放入 `Backend/YRpp/`（仓库不直接包含）
- **标准**: C++17；建议关闭强制符合模式

---

## 📄 开源协议 & 鸣谢

**[GPL-3.0](LICENSE)**

感谢 [YRpp](https://github.com/Phobos-developers/YRpp)、Ares/Syringe、Mental Omega 制作组。
