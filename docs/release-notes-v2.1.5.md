# 更新日志：

### 新增

- **类型索引**：引擎就绪后建立 `ID -> 类型` 哈希表，热重载时按 section 直接查表，不再逐节扫描全部类型数组。
- **配置热更新**：`ReloaderConfig.ini` 修改后自动重读（目标文件、热键、轮询间隔、日志、扩展开关），无需重启游戏。
- **日志文件**：游戏目录写入 `Reloader_Log.txt`，超过 `LogMaxKB` 自动轮转为 `.1`；即使关闭控制台也能排查重载结果。
- **热键增强**：边沿触发（按住不重复重载）；AutoMonitor 开启时也可强制重载；默认仅在游戏窗口前台响应。
- **`[AutoReloader]` 实时类型转换**：通过 Phobos `ConvertToType_Phobos` 把地图上已放置的旧单位转换为新类型，例如 `Convert=M60>MTNK`；若装有 Ares 3.0，Phobos 会转调 Ares 的转换实现。
- **运行时 AttachEffect**：通过 Phobos `AE_Attach` / `AE_Detach` / `AE_DetachByGroups` 对指定类型的所有单位执行附加、移除、按组移除与替换：
  - `AttachAE=M60:AE_NAME`
  - `DetachAE=M60:AE_NAME`
  - `DetachAEGroup=M60:GROUP_NAME`
  - `ReplaceAE=M60:OLD_AE>NEW_AE`
  - `ReplaceAEGroup=M60:GROUP>NEW_AE`
- **场景变量**：`SetLocalVar=5=1` / `SetGlobalVar=10=1` 运行时修改地图局部变量或战役全局变量，方便调试触发器/事件。
- **已有单位 AE 自动同步**：Phobos **v0.5-alpha1+（Interop 1.1+）** 可用时，只改单位节里的 `AttachEffect.AttachTypes` / `RemoveTypes` / `RemoveGroups` / `DurationOverrides` 等原有写法，重载时自动刷新场上已有单位；MO 3.3.6 默认无 Phobos，因此默认环境不生效。
- **Ares / Phobos 探测**：日志记录 Phobos Interop 版本与转换能力；Ares 基础类型扩展字段随 `LoadFromINI` hook 自动刷新。
- **DLL CI**：新增 `.github/workflows/build-dll.yml`，push/PR 修改 `Backend/**` 时自动编译 x86 DLL。
- **Syringe 版本自适应**：启动前检测 `Syringe.exe` 是新版 SyringeEx 还是旧版 Syringe，分别使用 `--args="..."` 或旧参数形式；不替换/改名任何文件，也不修改 `MOLauncher.exe` / `gamemd.exe`。`MOLauncher` 日志会记录检测结果。
- **MO 客户端配置适配（临时补丁）**：新增 `AutoReloader.SyringeLauncher.exe`。把 `Resources\ClientDefinitions.ini` 的 `GameLauncherExecutableName` 指向它，客户端就会经包装器按 Syringe 版本生成正确参数。只改一行配置，不注入、不替换 MO 文件。发布包同时提供可选的 `Tools\Enable-SyringeExCompat.cmd` / `Disable-SyringeExCompat.cmd`，自动备份/恢复该行，默认不启用。**它不是长期方案**，MO 客户端原生支持 `--args` 后应回滚；联机规则风险自负。
- **单位转换指令生成**：编辑器和战术工坊都可以把当前单位作为源类型，生成 `Convert=源>目标`；目标下拉按同类别、同水域/陆地过滤（海军→海军、陆军→陆军），可选反向转换，并自动替换源类型旧映射、提示链式转换风险。
- **转换水域校验**：引擎拒绝海军↔陆军等跨水域/陆地转换并写日志，避免目标落点非法导致异常。
- **属性说明词典扩充**：`common_flags.json` 扩充到 1000+ 键，补齐原版 Art（Foundation/Height/NewTheater/ActiveAnim/MuzzleFlash/ZAdjust 等）、Ares 3.0 与 Phobos 常用属性；支持 `Prerequisite.List*`、`Versus.*` 等索引键回退匹配。
- **导出接口**：`AutoReloader_TriggerReload`（外部触发一次全量重载）与 `AutoReloader_GetVersion`。

### 修复

- **更新不丢路径配置**：编辑器的路径/偏好保存到 `%LOCALAPPDATA%\AutoReloader\INIEditor\config.user.json` 并在启动时合并；工坊设置迁移到 `%LOCALAPPDATA%\AutoReloader\TacticalWorkshop\console_config.json`。覆盖安装 `Tools/config.json` 不再清空游戏目录选择。
- **单位转换向导**：目标显示中文名、支持搜索、往返转换和冲突提示，减少多步弹窗。
- **编辑器保存保护**：写入前拒绝同名 section 重复、拒绝空内容覆盖 Art 节、拒绝把 rules 字段写进 Art（或反向），避免 Art/规则数据被误清空或错写文件。
- 带 BOM、行尾注释（`[E1] ; comment`）或节名内外空格的 section 头被静默跳过。
- `EnsureTrailingNewline` 直接改写目标文件，导致 AutoMonitor 自我触发、重复重载。
- 手动热键按住时每 500ms 重复重载，且 AutoMonitor 模式下热键完全无效。
- 文件 mtime 变化后固定等待 100ms 就解析，慢写入时可能读到空/半截文件；读失败无重试。
- 每 50/500ms 重复读取配置；`TargetINI` 只有 1024 字节缓冲。
- 非 ASCII 游戏路径下 `GetFileAttributesExA` / `std::ifstream` 可能取不到文件，导致永不重载。
- `ReadCCFile` 失败、ID 未匹配时只有控制台输出（默认控制台关闭），用户无反馈。
- 同一 ID 跨类型时只重载第一个命中的类型；类型查找为 O(节数 × 全类型数)。
- 配置变更后旧的 `fileTimes` 状态未清理，新目标可能不触发重载。

### 优化

- 文件与配置读取改用宽字符 Win32 API，兼容中文/Unicode 路径。
- 文件变化采用 `mtime + size` 双采样，稳定后才解析；不再修改目标文件（缺换行时用临时副本）。
- 按 section 记录命中类型、未命中、加载失败、耗时与转换数量。
- 类型数组数量变化时自动重建索引。
- 移除每次轮询的全量配置解析与重复控制台输出。

---

> **说明**：Ares 没有导出刷新 API（全部为 Syringe hook），因此 Ares 扩展字段通过基础类型的 `LoadFromINI` hook 刷新；Ares 独有类型数组（如 AttachEffect 类型）与全局规则节（`[General]` 等）仍无法从外部 DLL 刷新。Phobos 集成要求 Interop API ≥ 1.1（Phobos v0.5-alpha1+），转换仅支持 Unit / Infantry / Aircraft 且源目标类别一致。
>
> **SyringeEx / MO 兼容（临时补丁）**：`AutoReloader.SyringeLauncher.exe` 只解决旧 MO 客户端按旧参数调用 SyringeEx 的问题。它需要用户显式运行 `Tools\Enable-SyringeExCompat.cmd`，会备份并修改 `Resources\ClientDefinitions.ini` 的一行启动器配置；不注入、不替换/改名 MO 文件。默认关闭，可一键回滚。MO 客户端更新可能覆盖配置，原生支持 `--args` 后应停用；联机/社区规则风险自负。详见 `docs/syringe-ex-mo-config.md`。
>
> **版本**：v2.1.5（含 Syringe 版本自适应）
