# INI 工程编辑器（AutoReloader 附带工具）

工程级 INI 编辑：对象树、CSF 中文名、Ares `#include`、增删改、保存回源文件（自动备份）、单单位调试与 hotfix 部署。

## 运行

```bash
# 本目录
pip install -r requirements.txt
python main.py

# 或仓库根
pip install -r Frontend/editor/requirements.txt
python Frontend/editor/main.py
```

## 主要能力

- 打开**游戏/工程目录**或**单文件**；记住上次目录（`config.json` → `settings`）
- 合并视图：Rules + Art + **AI**（配置中的 `ai_files`）
- 对象树分类；同名 section 按 Rules/Art/AI 与分组消歧
- 属性说明（`common_flags.json`）；右键可在对象树 / 编辑器中定位
- 代码区自动换行（编辑菜单）；查找替换
- 保存当前 / 保存全部；删除 section（带备份）
- 调试窗口 → 部署 `hotfix.ini` 配合 AutoReloader

## 配置与词典

- `config.json`：profile（Mental Omega / YR）、rules/art/ai/csf 路径
- 属性说明唯一源：`shared/schemas/common_flags.json`（本目录 `schemas/` 为打包副本）
- 显示名缓存：程序目录 `cache/`（带文件指纹，外部改 ini 会失效，勿提交）

## 分工

| 工具 | 职责 |
|------|------|
| 本编辑器 | 改工程结构与全文 |
| 战术工坊 | 快调热重载常用字段 |

热重载由 **AutoReloader.dll** 完成。正式分发以 AutoReloader Release 为准。
