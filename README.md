# AutoReloader — 红警2 / 尤里的复仇 · 心灵终结 热重载工具链

在游戏运行中修改 INI 参数并即时生效，配套 **INI 工程编辑器** 与 **战术工坊**，面向 MOD 作者与调试向玩家。

| 组件 | 作用 |
|------|------|
| **AutoReloader.dll** | 注入游戏进程，监控目标 INI 并热写属性 |
| **MO / YR 启动器** | 以管理员权限启动游戏并注入 DLL（需 UAC） |
| **INI 工程编辑器** | 工程级浏览 / 编辑 / 保存 / 备份，单单位调试部署 |
| **战术工坊 2.x** | 快调常用字段 → 安全写入 `hotfix.ini` |

**版本与 Release 以本仓库为准。**

---

## 构建与发布说明

本项目**源代码公开**于本仓库，欢迎查阅与自行构建。

**正式发布包**通过本仓库的 **GitHub Actions** 自动构建（工作流：`.github/workflows/build-release.yml`）：

- 在 GitHub 托管的 runner 上完成编译与打包，步骤与日志可在 [Actions](../../actions) 中查看；
- 发布文件见 [Releases](../../releases)，与对应 tag / commit 关联，便于对照源码版本；
- 内容一般包括注入 DLL、启动器、INI 工程编辑器、战术工坊等（以当次工作流为准）。

推荐从本仓库的 **Releases** 或 **Actions** 获取与当前源码一致的构建产物。若你希望完全自主可控，也可按下文「开发者」说明从源码本地编译。


---



## 下载与安装（正式包）

1. 从 [Releases](../../releases) 下载对应版本：
   - **心灵终结 (MO)** 整合包  
   - **尤里的复仇 (YR)** 整合包  
2. 解压到游戏根目录（或按包内说明放置）。  
3. 典型内容包括：
   - 启动器（`MO启动器.exe` / `YR启动器.exe`）与 `AutoReloader.dll`、`ReloaderConfig.ini`
   - `INI工程编辑器/`、`战术工坊/`（或合并目录，以实际包为准）
4. **必须用配套启动器启动游戏**（会请求管理员权限），不要直接双击原客户端后指望注入成功。

源码运行见下文「开发者」。

---

## 快速使用

### 热重载（游戏内）

1. 用启动器启动游戏并进入可调试场景。  
2. 在工坊或编辑器中修改参数，部署到 **`hotfix.ini`**（或你在 `ReloaderConfig.ini` 里配置的 TargetINI）。  
3. 按热键（默认常见为 **F5**，以配置为准）或开启 AutoMonitor。  
4. 确认改动生效；需要时用工坊「恢复」清理安全模式下的覆盖。

### 战术工坊

- 打开游戏 / MOD 根目录 → 在对象树选单位 → 改常用字段 → **部署**。  
- **安全模式**（推荐）：只写 `hotfix.ini`，不改原版 rules。  
- 显示名来自 CSF；可重建词典以刷新列表。

### INI 工程编辑器

- 打开工程目录（或单文件）→ 对象树浏览 → 中间改代码 → **保存当前 / 保存全部**（自动备份）。  
- 右侧为属性说明（只读释义）；调试可把当前单位部署到 hotfix。  
- 支持 Ares `#include`、profile（Mental Omega / YR）、CSF 中文对照。  

更细的说明见：

- `Frontend/editor/使用说明.txt`
- `Frontend/editor/README.md`
- `Frontend/workshop/README.md`

---

## 仓库结构

```text
Backend/           注入 DLL（YRpp）
Launcher/          MO / YR 启动器（需管理员清单）
shared/            公共 INI / CSF / hotfix / schema
Frontend/
  editor/          INI 工程编辑器
  workshop/        战术工坊 2.x
assets/
  *.ico            程序图标
  screenshots/     README 用截图（可替换）
docs/              设计与路线说明
scripts/           发布打包脚本
```

---


## 开发者

```bash
# 编辑器
pip install -r Frontend/editor/requirements.txt
python Frontend/editor/main.py

# 工坊
pip install -r Frontend/workshop/requirements.txt
python Frontend/workshop/main.py
```

属性说明唯一源：`shared/schemas/common_flags.json`。  
CI：`.github/workflows/build-release.yml`（DLL + 启动器 + 前端打包）。

---

## 许可

见 `LICENSE`。请遵守游戏与 MOD 相关使用约定；勿将本工具用于破坏他人受保护资源的宣传用途。
