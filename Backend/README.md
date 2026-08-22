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

当前仓库的 GitHub Actions **尚未**自动编译 DLL（前端打包工作流另计）。本地用上述 VS 或 CMake 即可产出 32 位 DLL。若后续要加 `build-dll` job，需在 runner 上准备 YRpp 与 x86 MSVC 环境。

## 源码现状备注

`dllmain.cpp` 已实现：配置读取、TargetINI 监控、按 section 名对已加载类型调用 `LoadFromINI`。

**限制**：只能重载**已在内存中存在**的 ID；新增/删除单位类型仍无法靠热重载完成（引擎未注册新类型）。
