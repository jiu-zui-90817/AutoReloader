# 自动同步已有单位的 AttachEffect（Ares / Phobos 源码补丁）

## 目标

保持原来的 INI 写法：只改单位节里的 AE 字段，重载后**地图上已经存在的该类型单位**也同步 AE，而不只是新生产的单位。

AutoReloader 本身做不到这一点：

- 它调用 `LoadFromINI` 只能更新“类型模板”；
- Ares / Phobos 没有导出“刷新该类型所有已有单位 AE”的接口；
- AutoReloader 的重载在监控线程执行，直接遍历/修改场上单位会与游戏线程冲突。

所以正确做法是在 Ares / Phobos 源码里加一个**延迟到游戏线程执行**的刷新标记：

1. 类型 INI 重载时，只给该类型的版本号 +1（线程安全、无对象操作）；
2. 每个单位的常规 AI 更新（游戏线程）发现版本变化后，重新应用该类型的 AE。

## 补丁

| 文件 | 对应 |
|------|------|
| `ares-auto-refresh-ae.patch` | Ares 的 `AttachEffect.*`（单位/武器节内联 AE） |
| `phobos-auto-refresh-ae.patch` | Phobos 的 `AttachEffect.AttachTypes`（具名 AE） |

### 应用

```bash
git -C /path/to/Ares apply /path/to/ares-auto-refresh-ae.patch
git -C /path/to/Phobos apply /path/to/phobos-auto-refresh-ae.patch
```

然后按各自项目的方式重新编译 Ares.dll / Phobos.dll。

两个补丁都是针对当前 `Ares master` / `Phobos develop` 生成的；如果你用的是 MO 自带的旧版分支，可能需要按上下文手动调整（补丁很小，核心就是版本号 + 游戏线程刷新）。

### Ares 补丁做了什么

- `TechnoTypeExt::ExtData` 增加 `AE_RefreshVersion`；
- `TechnoTypeExt::LoadFromINIFile` 读完 `AttachedTechnoEffect` 后版本 +1；
- `AttachEffectClass::Update`（游戏线程）发现版本变化时：
  - 移除旧的 type-owned AE（并 `KillAnim()`）；
  - 重置 `AttachedTechnoEffect_isset / Delay`；
  - `RecalculateStats()`，随后按新配置重新附加。

### Phobos 补丁做了什么

- `TechnoTypeExt` 增加 `AE_RefreshVersion`；
- `TechnoTypeExt::LoadFromINIFile` 读完 `AttachEffects` 后版本 +1；
- 每个 `TechnoExt` 增加 `AE_SeenVersion`；
- `TechnoExt::OnEarlyUpdate`（游戏线程）发现版本变化时调用
  `UpdateSelfOwnedAttachEffects()`：移除不再存在的 self-owned AE、按新 `AttachEffect.AttachTypes` 重新附加。

## 使用效果

打了补丁后，**不需要** `[AutoReloader]` 的 `AttachAE/DetachAE/...` 命令：

```ini
[E1]
; Ares 写法
AttachEffect.Animation=...
AttachEffect.Duration=...
AttachEffect.SpeedMultiplier=...
```

或 Phobos 写法：

```ini
[E1]
AttachEffect.AttachTypes=AE_ONE,AE_TWO

[AttachEffectTypes]
; 具名 AE 定义...
```

改完保存 hotfix → AutoReloader 重载 → 现有 E1 与新生产的 E1 使用同一套 AE。

## 注意

- Ares 与 Phobos 的 AE 是两套系统：你的 mod 用哪套就补哪套；两套都用就都补。
- 补丁只处理“单位类型拥有的 AE（self-owned）”；武器/弹头附加的临时 AE、其他来源的 AE 不会被误删。
- Phobos 的 `[AttachEffectTypes]` **具名 AE 定义本身**仍不会随 hotfix 重载（它不在原版类型遍历里）；补丁只保证单位类型引用的 AE 列表/参数在已有单位上刷新。
- 无法重新编译 Ares/Phobos 时，仍可使用 AutoReloader 的 `[AutoReloader] AttachAE/DetachAE/ReplaceAE` 命令做实例级操作。
- 补丁未经实际游戏内回归（本仓库没有 Ares/Phobos 构建环境）；建议先在测试地图验证：
  1. 放置若干 E1；
  2. 改 hotfix 中 E1 的 AE 参数并重载；
  3. 确认已有 E1 的 AE 动画/属性变化；
  4. 再生产一个新 E1，确认两者一致；
  5. 检查没有属性叠加或旧动画残留。
