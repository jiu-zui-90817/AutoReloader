# 前端路线图

主产品仍是 **AutoReloader 热重载引擎**；版本号与 Release 以本仓库为准。

## 两个前端

1. **战术工坊**（`Frontend/workshop`）— 快调热重载；2.x 已可用，不依赖 Codex  
2. **INI 编辑器**（`Frontend/editor`）— 工程级编辑；已可用  
3. **经典工坊**（`TacticalConsole.py`，目前保留）— 给习惯旧流程的用户  

## 阶段（现状）

| 阶段 | 状态 |
|------|------|
| `shared`（ini / csf / hotfix / codex / schemas） | 已具备 |
| 工坊 2.x 无 Codex 列出单位并部署 | 已具备 |
| 编辑器对象树 / 保存 / AI / 调试 | 已具备 |
| 持续 | UI 打磨、同名 section 体验、词典与说明扩充、CI 打包 |

## 打包

Release 可同时附带：引擎与启动器、Workshop 压缩包、Editor 压缩包。  
`common_flags.json` 以 `shared/schemas` 为唯一源，构建时注入各前端。
