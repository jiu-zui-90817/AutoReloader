# Syringe / SyringeEx 启动兼容层

## 问题

MO 的 `MOLauncher.exe` 还是按**老 Syringe** 的方式启动：

```text
Syringe.exe gamemd.exe -SPAWN -CD -SPEEDCONTROL -LOG -AFFINITY:255 -b=44
```

老 Syringe 会把 `gamemd.exe` 后面的参数原样交给游戏。

但 Phobos 0.5+ 自带的 **SyringeEx** 改成了：

```text
Syringe.exe gamemd.exe --args="-SPAWN -CD -SPEEDCONTROL -LOG -AFFINITY:255 -b=44"
```

如果直接把 SyringeEx 当成 `Syringe.exe` 用，`-SPAWN` 等会被 SyringeEx 当成自己的未知参数丢掉，游戏实际以空命令行启动，于是出现：

> This version of Yuri's Revenge only supports online play using CnCNet 5

并且 `syringe.log` 里能看到：

```text
Unknown flag "-SPAWN", skipping.
...
cmd = "gamemd.exe "
```

## 方案

用一个**启动兼容层**顶替 `Syringe.exe`：

- `MOLauncher.exe` 仍然调用 `Syringe.exe`（不改 MO 原版代码）；
- 兼容层判断目录里是 `SyringeEx.exe` 还是 `SyringeLegacy.exe`；
- 新 SyringeEx：把老写法翻译成 `--args="..."`；
- 老 Syringe：原样转发，行为不变。

**不会修改** `MOLauncher.exe`、`gamemd.exe`、Ares/Phobos 的代码或配置。

## 文件布局

### 新 Phobos（SyringeEx）

```text
Syringe.exe                      <- AutoReloader.SyringeShim.exe 改名为 Syringe.exe
SyringeEx.exe                    <- Phobos 0.5 包里的 SyringeEx，改名为 SyringeEx.exe
MOLauncher.exe / gamemd.exe ...  <- 不动
```

### 老 Phobos / 只有老 Syringe

```text
Syringe.exe                      <- AutoReloader.SyringeShim.exe 改名为 Syringe.exe
SyringeLegacy.exe                <- 原来的老 Syringe.exe，改名为 SyringeLegacy.exe
MOLauncher.exe / gamemd.exe ...  <- 不动
```

### 两个都想保留

```text
Syringe.exe          <- 兼容层
SyringeEx.exe        <- 新
SyringeLegacy.exe     <- 老
```

默认优先 `SyringeEx.exe`。要强制用老版，写 `SyringeShim.ini`：

```ini
[Loader]
; auto / ex / legacy
Use=legacy
```

## 安装步骤

1. 关闭游戏和启动器；
2. 把原来的 `Syringe.exe` 改名：
   - 新 Phobos → `SyringeEx.exe`
   - 老 Phobos/Ares → `SyringeLegacy.exe`
3. 把 `AutoReloader.SyringeShim.exe` 复制到游戏目录，改名为 `Syringe.exe`；
4. 照常用 `MOLauncher.exe` 启动。

不需要改快捷方式、注册表或启动器参数。

## 验证

看游戏目录的 `SyringeShim.log`：

```text
[2026-11-10 ...] loader: D:\MO\Mental Omega\SyringeEx.exe
[2026-11-10 ...] launch: "D:\MO\Mental Omega\SyringeEx.exe" gamemd.exe --args="-SPAWN -CD ..."
[2026-11-10 ...] exit code: 0
```

- 有 `launch:` 行说明转发成功；
- `SyringeEx.exe` 时命令行应包含 `--args="..."`；
- `SyringeLegacy.exe` 时命令行应保持老写法；
- 游戏正常进入、CnCNet 提示消失，说明参数已传下去。

## 回滚

1. 删除 `Syringe.exe`（兼容层）；
2. 把 `SyringeEx.exe` 或 `SyringeLegacy.exe` 改回 `Syringe.exe`；
3. 可选：删除 `SyringeShim.log` / `SyringeShim.ini`。

## 注意

- 兼容层只解决**启动参数**问题，不改变 Ares/Phobos 版本兼容性；Phobos 0.5 仍然需要 SyringeEx 0.1.0.2+。
- 它不修改 MO 原版文件，也不会绕过任何在线/版本校验；只是把同一组参数按对应 loader 的语法传下去。
- 如果以后 MO/启动器自己适配了 SyringeEx，可以撤掉兼容层。
- 源码：[`Backend/tools/SyringeShim.cpp`](../Backend/tools/SyringeShim.cpp)
