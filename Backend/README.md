# Backend — AutoReloader.dll

热重载注入引擎源码。当前仓库里**只有** `src/dllmain.cpp`，尚不能直接编译出 DLL。

## 编译还缺什么

| 缺失项 | 说明 |
|--------|------|
| **YRpp** | `dllmain.cpp` 依赖 `#include <YRpp.h>`、`CCINIClass`、`UnitTypeClass` 等。需克隆 [Phobos-developers/YRpp](https://github.com/Phobos-developers/YRpp)（或 Ares 系 YRpp）到 `Backend/YRpp/`，并加入头文件搜索路径。 |
| **预编译头 `pch.h`** | 源码第一行 `#include "pch.h"`，仓库中原本不存在。已补一份最小 `src/pch.h`，也可在工程中关闭预编译头。 |
| **VS 工程 / 构建脚本** | 无 `.sln` / `.vcxproj` / CMake。需新建 **Win32 (x86)** DLL 工程（游戏为 32 位）。 |
| **工具链** | Visual Studio 2019/2022，工作负载「使用 C++ 的桌面开发」；目标平台 **x86**，C++17。 |
| **运行时注入方式** | 本 DLL 在 `DllMain` 里 `CreateThread` 启动监控，通常由 `Launcher/MOInjector.exe` 注入进程，**不是** Syringe 的 hook 列表 DLL（与 Phobos 构建方式不同）。Injector 本身也需能编译/已有预编译包。 |

## 建议本地搭建步骤

1. 安装 VS 2022 + C++ 桌面开发（含 Windows SDK）。
2. 克隆 YRpp 到 `Backend/YRpp`：
   ```bash
   git clone --depth 1 https://github.com/Phobos-developers/YRpp.git Backend/YRpp
   ```
3. 新建 `Backend/AutoReloader.vcxproj`（Configuration Type = Dynamic Library，Platform = Win32）：
   - 附加包含目录：`$(ProjectDir)YRpp`（及 YRpp 内需要的子路径）
   - 源文件：`src/dllmain.cpp`
   - 预编译头：`src/pch.h`（或关闭 PCH）
4. 关闭「强制符合模式」若 YRpp 报扩展语法错误。
5. 生成 `AutoReloader.dll`，与 `Config/ReloaderConfig.ini`、`MOInjector.exe` 一并放入游戏根目录。

## CI 说明

GitHub Actions **暂不自动编 DLL**：依赖 YRpp 与 32 位 MSVC 工程文件，需先把工程与 submodule 补全后再加 `build-dll` job。

当前工作流只打包两个前端：

- `MO_INI_Editor-windows.zip`（单文件）
- `TacticalWorkshop-windows.zip`（单文件）

## 源码现状备注

`dllmain.cpp` 已实现：配置读取、TargetINI 监控、按 section 名对已加载类型调用 `LoadFromINI`。  
**限制**：只能重载**已在内存中存在**的 ID；新增/删除单位类型仍无法靠热重载完成（引擎未注册新类型）。
