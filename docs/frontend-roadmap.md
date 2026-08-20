# 前端路线图

主产品仍是 **AutoReloader 热重载引擎**；版本号与 Release 以本仓库为准。

## 两个前端

1. **战术工坊**（`Frontend/workshop`）— 经典快调，服务只热重载的用户  
2. **INI 编辑器**（`Frontend/editor`）— 附带工程编辑工具  

## 阶段

| 阶段 | 内容 |
|------|------|
| 当前 | 目录骨架；旧版 TacticalConsole 仍可用 |
| 下一 | 实现 `shared`（ini / csf / hotfix） |
| 然后 | 工坊 2.x：无 Codex 列出单位并部署 |
| 再后 | 常用表单 + 动态字段；UI 现代化 |
| 最后 | mo_ini_editor 迁入 `Frontend/editor` |

## 打包

Release 可同时附带：

- 引擎与启动器
- Workshop 压缩包
- Editor 压缩包（迁入后）
