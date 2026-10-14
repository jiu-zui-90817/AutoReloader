# P0 — 大工程加载性能（当前主推）

> 目标：MO 量级工程打开不再假死；对象树可交互；进度可见。  
> 状态：**P0-1～P0-4 已落地** · 启动日期 2026-10-09 · 完成 2026-10-09  
> 关联：`docs/editor-roadmap.md`；《开发方向、建议.txt》

---

## 成功标准（验收）

| 项 | 标准 | 状态 |
|----|------|------|
| 打开反馈 | 打开后状态栏分步进度（非一直「正在加载…」） | ☑ |
| 可交互 | 树骨架先出；大类展开再填子项 | ☑ |
| 树不卡 | 无过滤时 count>40 只放占位 | ☑ |
| 过滤 | 防抖；匹配不强制查 CSF；匹配数>120 仍 lazy | ☑ |
| 显示名 | 默认打开不全量 warm；磁盘缓存仍加载 | ☑ |
| 回归 | 搜索 / 校验 / 保存 / hotfix 主路径应仍可用（请本地点一次） | 待你验 |

---

## 任务拆分与进度

### P0-1 打开工程分阶段 + 进度反馈 — **已完成**

| 子项 | 状态 |
|------|------|
| 1.1 `open_directory(..., progress=)` | ☑ |
| 1.2 分步：rules → art → ai → 登记 → CSF → 索引 | ☑ |
| 1.3 UI 状态栏 + processEvents（打开工程 / 切换 profile） | ☑ |
| 1.4 art/ai/CSF 失败不阻断 | ☑ |

说明：仍在同一次调用内串行；单步巨大 include 仍可能较久。若不够再做「rules 后先建树」。

---

### P0-2 对象树严格懒加载 — **已完成**

| 子项 | 说明 | 状态 |
|------|------|------|
| 2.1 无全量建项 | 无过滤且 count>`_tree_lazy_threshold`(40) 只占位 | ☑ |
| 2.2 classify 缓存 | `Project._classify_cache`；`invalidate_classify_cache` 在打开/注入/单文件/删除时清空 | ☑ |
| 2.3 过滤路径 | 匹配只用 ID + **已有** display 缓存，不调用 `_disp`；匹配数>`_tree_filter_fill_cap`(120) 仍占位展开加载 | ☑ |
| 2.4 Art/AI | 与 rules 相同 lazy / 过滤策略 | ☑ |

---

### P0-3 显示名缓存策略 — **已完成**

| 子项 | 说明 | 状态 |
|------|------|------|
| 3.1 默认不全量 warm | `open_project` 末尾仅当 `settings.warm_display_names_on_open == true` 才 `_warm_display_cache` | ☑ |
| 3.2 设置项 | 写入 `config.json` → `settings.warm_display_names_on_open`（默认缺省=false） | ☑（约定，无单独 UI 开关） |
| 3.3 磁盘缓存 | `_load_display_cache_file` 仍在打开时加载 | ☑ 原有 |
| 3.4 CSF O(1) | `csf_parser` 已用 dict + lower key | ☑ 原有 |

需要全量预热时，在 config 的 settings 中设：

```json
"warm_display_names_on_open": true
```

或调用 `schedule_display_cache_rebuild`（仍会全量 warm）。

---

### P0-4 索引与刷新 — **已完成（4.2 后置）**

| 子项 | 状态 |
|------|------|
| 4.1 搜索基于已加载 ini，不另扫盘 | ☑ 原有 |
| 4.2 保存后增量更新索引 | ☐ 后置（P1 可做） |

---

## 改动文件一览

- `Frontend/editor/core/project.py` — progress、classify 缓存、invalidate
- `Frontend/editor/ui/main_window.py` — 打开进度、树匹配/lazy、warm 开关、删除时 invalidate

---

## 进度日志

| 日期 | 记录 |
|------|------|
| 2026-10-09 | 立项；P0-1 完成 |
| 2026-10-09 | **P0-2 / P0-3 / P0-4(基线) 完成** |

---

## 完成后下一优先

1. 本地用 MO 根目录验收打开 + 过滤 + 展开大类  
2. 路线图 P1：**当前节 Diff（A3）** 或 **语法高亮+节折叠（A4）**
