# SyringeEx 与 MO 客户端：配置适配说明

## 结论

在**不修改 MO 原版文件、不替换 Syringe、不注入客户端**的前提下，唯一可用的入口是 MO 客户端自己的配置：

```ini
Resources\ClientDefinitions.ini
GameLauncherExecutableName=Syringe.exe
```

把它指向我们提供的包装器：

```ini
GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe
```

客户端会调用：

```text
AutoReloader.SyringeLauncher.exe gamemd.exe -SPAWN -CD ...
```

包装器再按 Syringe 版本生成正确参数：

```text
新版 SyringeEx:
Syringe.exe gamemd.exe --args="-SPAWN -CD ..."

旧版 Syringe:
Syringe.exe gamemd.exe -SPAWN -CD ...
```

## 为什么必须改这一行

MO 客户端内部启动游戏的链路是：

```text
MentalOmegaClient.exe
  -> Resources\clientdx.exe
  -> Syringe.exe
```

`clientdx.exe` 直接按旧格式调用 Syringe。我们试过：

- Hook `CreateProcess` / `ShellExecute`：客户端进程有保护，`CreateRemoteThread` 被拒绝；
- `SetWindowsHookEx` 注入：同样受保护；
- 替换/改名 `Syringe.exe`：违反 MO 社区规定。

在没有官方支持的情况下，`GameLauncherExecutableName` 是唯一**不注入、不替换**的合法接入点。

## 发布方式（推荐）

发布包**不包含修改过的 MO 文件**，只包含：

```text
AutoReloader.SyringeLauncher.exe
Tools\Enable-SyringeExCompat.cmd
Tools\Disable-SyringeExCompat.cmd
```

用户自行选择是否启用：

1. 把 `AutoReloader.SyringeLauncher.exe` 放到游戏根目录；
2. 运行 `Tools\Enable-SyringeExCompat.cmd`；
3. 脚本会：
   - 备份 `Resources\ClientDefinitions.ini` 到 `.autoreloader.bak`；
   - 只改 `GameLauncherExecutableName` 一行；
4. 重启 MO 客户端。

恢复：

```text
Tools\Disable-SyringeExCompat.cmd
```

它会优先从备份恢复；没有备份时把这一行改回 `Syringe.exe`。

## 手动方式

不想运行脚本，就手动改：

```ini
; Resources\ClientDefinitions.ini
GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe
```

改回：

```ini
GameLauncherExecutableName=Syringe.exe
```

## 风险说明

- 这不是 MO 代码修改，也不是注入，但**确实修改了 MO 客户端的一行配置**；
- 是否允许由 MO/CnCNet 社区规则决定，发布时应明确标注为“可选兼容步骤”，默认不启用；
- 联机前请确认服务器/客户端规则允许该配置；
- 只对 **旧 MO 客户端 + 新版 SyringeEx** 需要；旧 Syringe 保持原配置即可。

## 更长期的方案

- MO 3.3.7 / 新版客户端原生支持 SyringeEx 的 `--args`；
- 或由 CnCNet/MO 客户端作者增加“启动器参数”配置项。

在那之前，包装器 + 可选配置脚本是唯一可发布、可回滚、无注入的方案。
