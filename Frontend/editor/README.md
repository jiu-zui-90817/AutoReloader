# INI 工程编辑器（AutoReloader 附带工具）

工程级 INI 编辑：对象树、CSF 中文名、Ares `#include`、增删改、保存回源文件（自动备份）、单单位调试与 hotfix 部署。

## 运行

在本目录下：

```bash
pip install -r requirements.txt
python main.py
```

或在仓库根目录：

```bash
pip install -r Frontend/editor/requirements.txt
python Frontend/editor/main.py
```

## 说明

- 与**战术工坊**分工：工坊负责快调热重载；本工具负责改工程结构与全文。
- 热重载由仓库中的 **AutoReloader.dll** 完成；本工具可把当前单位写入 `hotfix.ini`。
- 配置见 `config.json`（Mental Omega / Yuri's Revenge 等 profile）。
- 源码已从 [mo_ini_editor](https://github.com/jiu-zui-90817/mo_ini_editor) 迁入本目录；正式分发以 **AutoReloader** Release 为准。
