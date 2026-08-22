# shared — 前端公共逻辑

供 **战术工坊** 与 **INI 编辑器** 共用：纯逻辑，不放 UI。

| 模块 | 职责 |
|------|------|
| `ini_loader` | rules 读取、Ares `#include` 合并 |
| `csf_loader` | CSF 中文显示名（通配符路径） |
| `hotfix_io` | section 写回、备份、编码 |
| `project_scan` | 按 profile 扫描注册表/单位 |
| `codex_builder` | 工坊用显示名/武器列表/阵营分类词典 |
| `profiles.json` | Mental Omega / YR 路径约定 |
| `schemas/common_flags.json` | **属性说明唯一源**（构建时复制到各前端） |

## 使用

仓库根加入 `sys.path` 后：

```python
from shared.project_scan import GameProject, load_profiles
from shared.codex_builder import build_codex
from shared.hotfix_io import save_section_to_file
```

## 打包注意

- 只改 **`shared/schemas/common_flags.json`**
- CI / 本地打包前同步到 `Frontend/*/schemas/` 再打进包
- 运行时查找顺序：exe 旁 `schemas/` → 包内 → 源码 `shared/schemas/`
