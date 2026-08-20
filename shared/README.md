# shared — 前端公共逻辑

供 **战术工坊** 与 **INI 编辑器** 共用，只放纯逻辑，不放 UI。

| 模块 | 职责 |
|------|------|
| `ini_loader` | rules 读取、Ares `#include` 合并、保留注释与顺序 |
| `csf_loader` | CSF → 中文显示名（UTF-16LE + 按位取反，支持通配符） |
| `hotfix_io` | section 写回、备份、编码探测 |
| `project_scan` | 按 profile 扫描注册表、单位列表 |
| `profiles.json` | Mental Omega / YR 路径约定 |

## 使用

从仓库根运行前端，或入口把仓库根加入 `sys.path`：

```python
from shared.project_scan import GameProject, load_profiles
from shared.hotfix_io import save_section_to_file
```

## 打包

PyInstaller 单文件时用 `--paths .` 与 `--hidden-import shared.*`，并把 `profiles.json` 用 `--add-data` 带上。
