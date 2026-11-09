# Backend — AutoReloader.dll

热重载注入引擎源码。提供 **CMake** 与 **Visual Studio（Win32）** 两种本地编译方式。

## 编译前准备

| 依赖 | 说明 |
|------|------|
| **YRpp** | `dllmain.cpp` 依赖 `#include <YRpp.h>`、`CCINIClass`、`UnitTypeClass` 等。需克隆到 `Backend/YRpp/`。 |
| **工具链** | Visual Studio 2019/2022，工作负载「使用 C++ 的桌面开发」（含 Windows SDK）。目标平台必须为 **x86 / Win32**，C++17。 |
| **预编译头** | 已提供 `src/pch.h`、`src/pch.cpp`、`src/framework.h`。也可在工程中关闭预编译头。 |

克隆 YRpp（在仓库根目录或 `Backend/` 下执行均可，路径需对应工程设置）：

```bash
git clone --depth 1 https://github.com/Phobos-developers/YRpp.git Backend/YRpp
```

## 方式一：Visual Studio 工程（推荐图形界面）

1. 用 VS 2022 打开 `Backend/AutoReloader.sln`。
2. 顶部平台选择 **x86**（不要选 x64）。
3. 配置选 Debug 或 Release，生成解决方案。
4. 输出目录：`Backend/bin/Debug/` 或 `Backend/bin/Release/`，产物为 `AutoReloader.dll`。

工程已配置：

- Configuration Type = Dynamic Library
- 附加包含目录：`YRpp`、`src`
- 语言标准 C++17，关闭强制符合模式（`/permissive`），便于兼容 YRpp

若本机工具集不是 v143，可在项目属性 → 常规 → 平台工具集中改为已安装版本（如 v142）。

## 方式二：CMake

```bash
cd Backend
# 若尚未克隆 YRpp：
# git clone --depth 1 https://github.com/Phobos-developers/YRpp.git YRpp

cmake -B build -A Win32 -G "Visual Studio 17 2022"
cmake --build build --config Release
```

产物默认在 `Backend/build/bin/Release/AutoReloader.dll`（以 `CMakeLists.txt` 中 `RUNTIME_OUTPUT_DIRECTORY` 为准）。

也可用 Ninja 等生成器，但须保证工具链为 32 位。

## 部署与运行

将生成的 `AutoReloader.dll` 与 `Config/ReloaderConfig.ini`、`MOInjector.exe`（或 YRInjector）一并放入游戏根目录。

**必须用 Injector 启动游戏。** 本 DLL 在 `DllMain` 里 `CreateThread` 启动监控线程，不是 Syringe 的 hook 列表 DLL（与 Phobos 构建/加载方式不同）。

## CI 说明

- `.github/workflows/build-dll.yml`：在 push / PR 修改 `Backend/**` 时自动编译 x86 DLL，并上传 `AutoReloader-dll` 产物。
- `.github/workflows/build-nuitka-release.yml` / `build-release.yml` 仍会在完整发布构建时编译 DLL。

## 发布与集成能力

### 运行机制

- 启动后等待引擎就绪，建立 `ID -> 类型` 哈希索引，热重载时按 section 名直接查表，不再遍历全部类型数组。
- 目标文件采用 `mtime + size` 双采样，确认写入稳定后再解析；读失败自动重试。
- 日志写入游戏目录 `Reloader_Log.txt`（默认超过 1 MB 轮转为 `.1`），即使 `ShowConsole=false` 也能排查。
- 热键为边沿触发，AutoMonitor 开启时也可强制重载；默认只在游戏窗口前台时响应。
- 配置 `ReloaderConfig.ini` 修改后无需重启，监控线程会自动重读。

### Ares / Phobos 集成

- **Ares**：Ares 没有导出 API（全部是 Syringe hook）。基础类型调用 `LoadFromINI` 时会经过 Ares 的 hook，因此 Ares 扩展字段会随普通重载刷新；Ares 独有的类型数组（如 AttachEffect 类型）无法从外部 DLL 访问。
- **Phobos**：使用其官方 Interop 导出：
  - `GetInteropAPIVersion`：校验接口版本（要求 1.x）。
  - `ConvertToType_Phobos`：实时把已放置单位转换为另一种类型。
  - 若同时安装了 Ares 3.0，Phobos 的转换实现会转调 Ares 的转换逻辑。
- 未安装 Ares/Phobos 时保持原版行为。

### 实时类型转换（`[AutoReloader]`）

在任意 `TargetINI` 末尾追加：

```ini
[AutoReloader]
; 把地图上所有 M60 转换为 MTNK（ID 必须已存在）
Convert=M60>MTNK

; 可写多条；也支持 ->
Convert=OLD_TYPE->NEW_TYPE
```

执行条件：

- `[Extensions] LiveConvert=true`；
- 进程内已加载 Phobos 且 Interop 版本 ≥ 1.0；
- 源/目标类型都在内存中，且类型类别一致（Unit/Infantry/Aircraft）。

转换在本次 section 重载完成后执行，日志会记录 `converted / failed` 数量。

### 自动同步已有单位 AE（Ares / Phobos 源码补丁）

只改单位节里的 `AttachEffect.*`，希望**场上已有的该类型单位**也同步，需要在 Ares / Phobos 源码里加一个“版本号 + 游戏线程延迟刷新”补丁：

- Ares：`docs/patches/ares-auto-refresh-ae.patch`
- Phobos：`docs/patches/phobos-auto-refresh-ae.patch`

说明与用法见 [`docs/patches/README.md`](../docs/patches/README.md)。

原因：AutoReloader 的 `LoadFromINI` 在监控线程执行，直接遍历/修改场上单位会与游戏线程竞争；Ares/Phobos 也没有导出刷新接口。补丁只在线程安全的位置给类型版本号 +1，实际 AE 重建由游戏线程的常规单位更新完成。

打了补丁后，用户只需要原来的 INI 写法，不再需要 `[AutoReloader]` 命令。

### 运行时 AttachEffect（需要 Phobos）

Phobos Interop 提供 `AE_Attach` / `AE_Detach` / `AE_DetachByGroups`。可用 hotfix 指令：

```ini
[AutoReloader]
; 给所有 M60 附加一个或多个 AttachEffect
AttachAE=M60:EFFECT_NAME
AttachAE=M60:AE_ONE,AE_TWO

; 按效果名移除
DetachAE=M60:EFFECT_NAME

; 按组移除（AttachEffect 类型可定义 Group）
DetachAEGroup=M60:GROUP_NAME

; 替换：先移除旧效果（或旧组），再附加新效果
ReplaceAE=M60:OLD_EFFECT>NEW_EFFECT
ReplaceAEGroup=M60:GROUP_NAME>NEW_EFFECT
```

行为说明：

- 对**所有该类型且存活**的单位执行；建筑等 TechnoClass 也可作为目标（取决于 AE 是否支持）。
- 每次热重载都会执行一次；重复 `AttachAE` 是否叠加取决于该 AE 类型的 `Cumulative` 设置。
- `ReplaceAE` / `ReplaceAEGroup` 内部就是“先 detach，再 attach”。
- 效果名 / 组名来自 Ares/Phobos 的 AttachEffect 定义；名称不存在时 Phobos 返回 `S_FALSE`，日志显示 attached/removed 为 0。

### 场景变量（需要 Phobos）

```ini
[AutoReloader]
SetLocalVar=5=1
SetGlobalVar=10=1
```

- **局部变量（Local）**：当前地图 / 场景的触发器变量，地图触发器读取它；重开地图会重置。
- **全局变量（Global）**：战役 / 跨地图保存的变量，常用于战役进度、跨任务标志。
- 用途：调试地图触发器 / 事件时，直接改条件变量，不必回到地图编辑器加触发器动作。
- 索引与取值范围由 Phobos/游戏侧决定；写入失败会记录 HRESULT。

### 配置项

| 项 | 默认 | 说明 |
|----|------|------|
| `[Settings] AutoMonitor` | true | 文件变化自动重载 |
| `[Settings] HotKey` | 116 (F5) | 手动重载热键 |
| `[Settings] ShowConsole` | false | 调试控制台 |
| `[Settings] Beep` | true | 重载成功提示音 |
| `[Settings] HotkeyOnlyInGame` | true | 仅游戏前台响应热键 |
| `[Settings] PollIntervalMs` | 500 | 轮询间隔（100–5000） |
| `[Settings] TargetINI` | hotfix.ini | 逗号分隔，可多个 |
| `[Logging] LogFile` | true | 写 `Reloader_Log.txt` |
| `[Logging] LogMaxKB` | 1024 | 日志轮转大小 |
| `[Extensions] LiveConvert` | true | 允许 `[AutoReloader]` 转换 |

## 源码现状 / 限制

`dllmain.cpp` 实现：配置热更新、文件监控、稳定读取、类型索引、日志、热键边沿触发、`[AutoReloader]` 转换，以及 Ares/Phobos 探测与 Phobos Interop 调用。

**限制**：

- 只能重载**已在内存中存在**的类型；新增/删除类型仍无法靠热重载完成（引擎未注册新类型）。
- `[General]`、`[CombatDamage]` 等全局规则节不会重载（当前只对类型对象调用 `LoadFromINI`）。
- 已放置单位的实例数据（当前生命、经验、弹药等）不会因类型重载而自动改变；可用 `[AutoReloader]` 的 `Convert` 通过 Phobos 转换单位为同类新类型（会按百分比换算生命）。
- Ares/Phobos 独有的新类型数组（AttachEffect、LaserTrail 等）没有公开 API，无法从外部 DLL 直接刷新。
- 路径过长（> MAX_PATH）时 `CCFileClass` 可能无法读取。

