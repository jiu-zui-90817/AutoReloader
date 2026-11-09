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
- **实验性：重载后重建已有单位**：`[Experimental] RefreshExistingUnits=true` 时，重载单位类型会重建场上已有的 Infantry/Unit，让**所有类型参数**（不只 AE）重新初始化；默认关闭，会跳过运输/小队/部署等复杂状态，并转移 Tag/UniqueID 等尽量保留触发器关联。不要用于联机。
- **已有单位 AE 自动同步**：Phobos **v0.5-alpha1+（Interop 1.1+）** 可用时，只改单位节里的 `AttachEffect.AttachTypes` / `RemoveTypes` / `RemoveGroups` / `DurationOverrides` 等原有写法，重载时自动刷新场上已有单位；MO 3.3.6 默认无 Phobos，因此默认环境不生效。
- **Ares / Phobos 探测**：日志记录 Phobos Interop 版本与转换能力；Ares 基础类型扩展字段随 `LoadFromINI` hook 自动刷新。
- **DLL CI**：新增 `.github/workflows/build-dll.yml`，push/PR 修改 `Backend/**` 时自动编译 x86 DLL。
- **导出接口**：`AutoReloader_TriggerReload`（外部触发一次全量重载）与 `AutoReloader_GetVersion`。

### 修复

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
> **版本**：v2.1.5（源码提交 `4c90ee9` 之后的实验性重建提交）
