# shared — 前端公共逻辑

供 **战术工坊** 与 **INI 编辑器** 共用，只放纯逻辑，不放 UI。

| 模块（规划） | 职责 |
|--------------|------|
| `ini_loader` | rules / art 读取、Ares `#include` 合并 |
| `csf_loader` | CSF → 中文显示名 |
| `project_scan` | 按 profile 扫描注册表、单位分类 |
| `hotfix_io` | 写入/替换 hotfix section、备份 |
| `profiles.json` | Mental Omega / YR 等路径约定 |

## 使用方式

从仓库根目录运行前端，或在入口里把仓库根加入 `sys.path`：

```python
from shared.csf_loader import ...  # 实现后
```

打包时由各前端入口自动带上本目录，无需单独编译。
