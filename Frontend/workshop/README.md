# 战术工坊 (Workshop) 2.x

经典快调前端：选单位 → 改常用参数 → 部署 `hotfix.ini` → AutoReloader 热重载。

## 升级目标

- [ ] 不再依赖 `Codex_ZH.json` / CodexGenerator
- [ ] 直接读游戏目录（rules + `#include` + CSF）
- [ ] 保留安全模式 / 高级模式、恢复原版、部署与清理
- [ ] 默认常用字段表 + 动态补全 section 中的其它键
- [ ] UI 现代化（后期）

## 入口（待实现）

```bash
# 在仓库根目录
python Frontend/workshop/main.py
```

公共逻辑使用仓库根下的 `shared/`。
