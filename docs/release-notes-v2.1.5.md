# 更新日志：

### 新增

- **实时类型转换与已有单位刷新**：通过 Phobos `ConvertToType_Phobos` 把地图上已放置单位转换为新类型，例如 `Convert=M60>MTNK`；用两条 `Convert` 往返可让已有单位重新读取配置，同时保留编组和移动/攻击指令。
- **运行时 AttachEffect**：支持 `AttachAE` / `DetachAE` / `DetachAEGroup` / `ReplaceAE` / `ReplaceAEGroup`，对指定类型的所有单位附加、移除或替换 AE。
- **场景变量**：`SetLocalVar=5=1` / `SetGlobalVar=10=1` 运行时修改地图局部变量或战役全局变量。
- **Ares / Phobos 集成**：Ares 基础类型扩展字段随 `LoadFromINI` hook 刷新；Phobos 通过 Interop 提供转换、AE 和变量能力；日志记录 Phobos Interop 版本与可用能力。
- **类型配置热重载**：已存在的单位/武器/建筑/动画等类型对象可直接重读 INI；类型索引按 `ID -> 类型` 哈希查找，不再逐节扫描全类型数组。
- **单位转换向导（编辑器 / 战术工坊）**：当前单位作为源类型，目标显示中文名并支持搜索；只列出同类别、同水域/陆地的目标（海军→海军、陆军→陆军）；可手动勾选反向转换，默认关闭。
- **转换冲突处理**：自动替换源类型的旧 `Convert` 映射；存在指向源类型的旧映射时提示可能的链式转换。
- **属性说明词典扩充**：`common_flags.json` 扩充到 1000+ 键，补齐原版 Art、Ares 3.0 与 Phobos 常用属性；支持 `Prerequisite.List*`、`Versus.*` 等索引键回退匹配。
- **Syringe 版本自适应**：启动前检测 Syringe 是新版 SyringeEx 还是旧版，分别使用 `--args="..."` 或旧参数；不替换/改名任何文件。
- **MO 客户端临时兼容包装器**：新增 `AutoReloader.SyringeLauncher.exe`，供旧 MO 客户端正确调用 SyringeEx。发布包提供可选的 `Tools\Enable-SyringeExCompat.cmd` / `Disable-SyringeExCompat.cmd`，自动备份/恢复 `ClientDefinitions.ini` 的一行启动器配置。**这是临时补丁，不是长期方案。**
- **配置热更新与日志**：`ReloaderConfig.ini` 修改后自动重读；日志写入 `Reloader_Log.txt` 并自动轮转；热键支持边沿触发。
- **导出接口**：`AutoReloader_TriggerReload`（外部触发一次全量重载）与 `AutoReloader_GetVersion`。

### 修复

- **Art / rules 致命保存错误保护**：写入前拒绝同名 section 重复、拒绝空内容覆盖 Art 节、拒绝把 rules 字段写进 Art（或反向）；写入后再次校验，失败自动从备份恢复。可避免 `GACNST` 这类 Art 节被清空或写错文件后变成 1x1 / 错误图像。
- **覆盖更新不再丢路径配置**：发行包只带 `Tools/config.default.json`，首次运行才复制成 `Tools/config.json`；编辑器另将路径/偏好备份到 `%LOCALAPPDATA%\AutoReloader\INIEditor\config.user.json` 并在启动时合并。工坊设置迁移到 `%LOCALAPPDATA%\AutoReloader\TacticalWorkshop\console_config.json`，覆盖安装不再清空游戏目录选择。
- **默认配置适配**：MO 包默认 `MentalOmega`（rulesmo / artmo / aimo），YR 包默认 `YuriRevenge_Vanilla`（rulesmd / artmd / aimd）；清理旧测试留下的 `X` profile。
- **转换水域校验**：引擎拒绝海军↔陆军等跨水域/陆地转换并写日志，避免目标落点非法导致异常。
- **转换反向默认关闭**：避免未测试就自动生成反向 `Convert` 指令。
- **转换弹窗体验**：目标中文名、搜索、居中显示、限制下拉高度；旧映射和链式冲突在窗口内提示。
- 带 BOM、行尾注释（如 `[E1] ; comment`）或节名内外空格的 section 头被静默跳过。
- `EnsureTrailingNewline` 直接改写目标文件，导致 AutoMonitor 自我触发、重复重载。
- 手动热键按住时每 500ms 重复重载，且 AutoMonitor 模式下热键完全无效。
- 文件 mtime 变化后固定等待 100ms 就解析，慢写入时可能读到空/半截文件；读失败无重试。
- 配置读取重复、`TargetINI` 缓冲过小；非 ASCII 路径下可能永远不触发重载。
- `ReadCCFile` 失败、类型未匹配时只有控制台输出（默认控制台关闭），用户无反馈。
- 同一 ID 跨类型时只重载第一个命中的类型；类型查找为 O(节数 × 全类型数)。
- 配置变更后旧的文件时间状态未清理，新目标可能不触发重载。
- 编辑器写入 CSF 中文名时清空语音（wave）数据；写回显示名会保留 `WRTS / STRW` 值块与 wave 文件名。
- 编辑器「保存全部」无法保存新增/克隆单位、失败后仍清脏标记、逐节弹确认框；克隆 Art 可能重复写节。
- 拆分工程全量保存会删掉被后加载文件覆盖的旧键；删除某个键只清理生效来源，旧副本可能“复活”。
- 「另存为」到已存在但缺少当前节的文件失败；「部署到 hotfix」在 hotfix 已有其它节但缺少当前节时失败。
- 删除节 / 从注册表移除条目会写回 UTF-8 BOM；备份失败时仍继续删除。
- 节头带行尾注释时保存会出现两个同名节头；`[Section]` 与第一个键之间插入多余空行。
- 显示名缓存指纹未包含 `#include` 文件；`+=ID` 注册查重区分大小写。
- 启动器未检查 `CreateToolhelp32Snapshot` 失败，可能继续操作无效句柄。

### 优化

- 文件与配置读取改用宽字符 Win32 API，兼容中文/Unicode 路径；文件变化采用 `mtime + size` 双采样，稳定后才解析。
- 按 section 记录命中类型、未命中、加载失败、耗时与转换数量；类型数组变化时自动重建索引。
- 「保存全部」只处理有未保存修改的标签，不再重写所有已打开节，也不再逐节确认。
- 高级模式部署不再自动瘦身；hotfix 瘦身仅限安全模式的 `hotfix.ini`，以数据安全优先。
- 发布包不再附带用户 `Tools/config.json`；只带默认配置，避免覆盖更新丢路径。
- 编辑器/工坊属性说明统一使用 `shared/schemas/common_flags.json`，构建时同步到各前端。
- 移除实验性“全地图重建/RefreshExisting”代码，避免未完成功能造成闪退；已有单位刷新改用可验证的 `Convert` 往返。

---

> **说明**：Ares 没有导出刷新 API（全部为 Syringe hook），因此 Ares 扩展字段通过基础类型的 `LoadFromINI` hook 刷新；Ares 独有类型数组与全局规则节仍无法从外部 DLL 刷新。Phobos 集成要求 Interop API ≥ 1.1（Phobos v0.5-alpha1+），转换仅支持 Unit / Infantry / Aircraft 且源目标类别、水域/陆地属性一致。
>
> **SyringeEx / MO 兼容（临时补丁）**：`AutoReloader.SyringeLauncher.exe` 只解决旧 MO 客户端按旧参数调用 SyringeEx 的问题。需要用户显式运行 `Tools\Enable-SyringeExCompat.cmd`，会备份并修改 `Resources\ClientDefinitions.ini` 的一行启动器配置；不注入、不替换/改名 MO 文件。默认关闭，可一键回滚。MO 客户端原生支持 `--args` 后应停用；联机/社区规则风险自负。详见 `docs/syringe-ex-mo-config.md`。
>
> **版本**：v2.1.5
