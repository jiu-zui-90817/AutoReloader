# 属性说明词典（common_flags.json）

`shared/schemas/common_flags.json` 是编辑器属性面板和战术工坊字段标签的唯一说明源。

## 覆盖范围

当前约 **1000+ 个键**，包括：

- 原版单位 / 建筑 / 武器 / 弹头 / 动画 / 抛射体常用键；
- Art 常用键（`Foundation`、`Height`、`NewTheater`、`Normalized`、`ActiveAnim*`、`MuzzleFlash*`、`ZAdjust` 等）；
- Ares 3.0 扩展键（`Prerequisite.*`、`Bounty.*`、`BuildTime.*`、`FactoryOwners.*`、`Spotlight.*`、`Academy.*`、`WaterImage` 等）；
- Phobos 扩展键（Jumpjet、Translucency、HealthBar.Hide、AE 相关等）。

说明来源：

- 本机 Ares 3.0 中文说明书（CHM）；
- [Phobos 官方文档](https://phobos.readthedocs.io/)；
- 公开的 YR/RA2 INI 资料与现有工程配置。

## 索引 / 模式键

某些键会带数字或 `#`，属性面板支持回退匹配：

- `Prerequisite.List1` … `Prerequisite.List10` → `Prerequisite.List#`
- `MuzzleFlash0` … → `MuzzleFlash0`
- `DamageFireOffset0` … → `DamageFireOffset0`
- `Versus.*` / `Verses.*` → `Versus`
- `AddOccupy*` / `RemoveOccupy*` → 对应基础键
- `Animation.DrawOffsetN` / `AttachEffect.DrawOffsetN` → 对应基础键

## 维护约定

- **只改 `shared/schemas/common_flags.json`**；
- 构建前同步到 `Frontend/editor/schemas/` 与 `Frontend/workshop/schemas/`；
- 新增键建议包含：

```json
"KeyName": {
  "type": "bool | int | float | string | list | weapon | warhead | animation",
  "desc_zh": "中文说明",
  "desc_en": "英文说明（可选）"
}
```

- 说明应描述**游戏行为/取值**，不要复制整段手册；
- 同一键在不同 section 语境不同（例如 `Shadow`、`Rate`）时，优先写通用描述，具体差异放在文档或字段注释中。

## 已知限制

- 词典是“常见键”覆盖，不是全量 INI 规范；
- Ares/Phobos 不同版本可能存在键差异；
- 说明用于辅助理解，最终以对应版本引擎/文档为准。
