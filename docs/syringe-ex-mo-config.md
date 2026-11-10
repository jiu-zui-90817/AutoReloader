# SyringeEx × MO 客户端兼容包装器（临时补丁）

> **状态：临时兼容补丁，不是 MO/CnCNet 官方支持，也不会永久保留在默认流程里。**
>
> 它只解决一个具体问题：旧版 MO 客户端按旧参数调用新版 `Syringe.exe`（SyringeEx），导致 `-SPAWN` 等参数被丢弃。
> 当 MO 客户端自己适配 SyringeEx，或官方给出启动参数接口后，这个方案应被移除。

## 适用场景

| 环境 | 是否需要包装器 |
|------|----------------|
| 旧版 Syringe + 旧版 MO 客户端 | 不需要，保持原配置 |
| 新版 SyringeEx + 旧版 MO 客户端 | **需要**，否则 `-SPAWN` 会被 SyringeEx 丢弃 |
| 新版 SyringeEx + 已支持 `--args` 的新客户端 | 不需要，应把配置改回 `Syringe.exe` |
| 旧版 Syringe + 已支持 `--args` 的新客户端 | 不需要，客户端会自己处理 |

判断依据：`Syringe.exe` 是否包含 `SyringeEx` 标识、是否支持 `--args`。包装器每次启动都会重新检测。

## 它做了什么

MO 客户端原来通过配置调用：

```ini
Resources\ClientDefinitions.ini
GameLauncherExecutableName=Syringe.exe
```

启用后改为：

```ini
GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe
```

客户端会调用：

```text
AutoReloader.SyringeLauncher.exe gamemd.exe -SPAWN -CD ...
```

包装器按 Syringe 版本生成：

```text
新版 SyringeEx:
Syringe.exe gamemd.exe --args="-SPAWN -CD ..."

旧版 Syringe:
Syringe.exe gamemd.exe -SPAWN -CD ...
```

然后等待 Syringe/游戏退出，并原样返回退出码。

## 它不做什么

- 不修改、不替换、不改名 `Syringe.exe` / `gamemd.exe` / `MOLauncher.exe`；
- 不注入 `MentalOmegaClient.exe` / `clientdx.exe`；
- 不修改 MO 的代码或二进制文件；
- 不自动修复客户端内部其它启动逻辑；
- 不保证在联机/反作弊环境下被允许。

它只改 **一行客户端启动器配置**，仅此而已。

## 启用

发布包应包含：

```text
AutoReloader.SyringeLauncher.exe
Tools\Enable-SyringeExCompat.cmd
Tools\Disable-SyringeExCompat.cmd
```

步骤：

1. 把 `AutoReloader.SyringeLauncher.exe` 放在游戏根目录（和 `Syringe.exe` 同目录）；
2. 运行：

```text
Tools\Enable-SyringeExCompat.cmd
```

脚本会：

- 备份 `Resources\ClientDefinitions.ini` 到 `ClientDefinitions.ini.autoreloader.bak`；
- 只把 `GameLauncherExecutableName` 改成 `AutoReloader.SyringeLauncher.exe`；
- 重复运行时不会重复改。

3. **完全退出并重启 MO 客户端**，配置只在客户端启动时读取。

## 手动启用

不想运行脚本时，手动改：

```ini
; Resources\ClientDefinitions.ini
GameLauncherExecutableName=AutoReloader.SyringeLauncher.exe
```

改回：

```ini
GameLauncherExecutableName=Syringe.exe
```

## 验证

包装器日志：

```text
SyringeLauncher_Log.txt
```

正常应看到：

```text
syringeEx=1
cmd="...\Syringe.exe" gamemd.exe --args="-SPAWN -CD ..."
```

Syringe 日志 `syringe.log` 应看到：

```text
WinMain: arguments = "gamemd.exe --args=\"-SPAWN -CD ...\""
```

而不是：

```text
arguments = "gamemd.exe -SPAWN -CD ..."
Unknown flag "-SPAWN", skipping.
```

如果 `syringeEx=0`，说明检测到旧 Syringe，包装器会走旧参数；这通常说明你不需要这个补丁。

## 关闭 / 回滚

运行：

```text
Tools\Disable-SyringeExCompat.cmd
```

它优先从 `.autoreloader.bak` 恢复；没有备份时把这一行改回 `Syringe.exe`。

也可以手动改回 `GameLauncherExecutableName=Syringe.exe`。

## MO 更新后

MO 客户端更新、修复安装、重新解压整合包时，可能覆盖 `Resources\ClientDefinitions.ini`。

如果更新后配置又变回：

```ini
GameLauncherExecutableName=Syringe.exe
```

重新运行一次 `Enable-SyringeExCompat.cmd` 即可。  
如果客户端更新后已经原生支持 SyringeEx，则**不要**再启用。

## 风险与发布约定

- 这是**临时兼容补丁**，不是长期功能；
- 修改的是 MO 客户端的一行配置，是否允许由 MO/CnCNet 社区规则决定；
- **联机前必须确认服务器/客户端规则**；不确定就不要启用；
- 发布包**不附带修改过的 `ClientDefinitions.ini`**，只提供可选脚本；
- 默认不启用，用户显式运行脚本才生效；
- 不修改 MO 二进制，不注入进程；
- 出现客户端更新/反作弊/启动异常时，第一件事是运行 `Disable-SyringeExCompat.cmd` 回滚。

## 何时移除

满足任一条件后，应删除包装器方案并恢复原配置：

- MO 3.3.7 或更新客户端原生支持 SyringeEx 的 `--args`；
- CnCNet/MO 客户端作者提供正式的“启动器参数”配置项；
- 官方明确禁止修改 `ClientDefinitions.ini` 的启动器字段。

## 文件清单

```text
AutoReloader.SyringeLauncher.exe     包装器本体
Tools\Enable-SyringeExCompat.cmd     可选启用（自动备份）
Tools\Disable-SyringeExCompat.cmd    回滚
SyringeLauncher_Log.txt              运行日志（生成）
```

`AutoReloader.SyringeLauncher.exe` 与两个脚本由 release 构建自动打进包；单独下载 `AutoReloader-dll` CI 产物不会包含它们。
