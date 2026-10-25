"""战术工坊 2.x

主体代码过大；若仓库 app.py 被误覆盖，此加载器从上一完整提交拉回，
并补上打包后标题栏图标（exe 旁 workshop.ico / editor.ico）。
首次 import 会缓存为 _app_restored.py，PyInstaller 会打进去。
"""
from __future__ import annotations

import pathlib
import urllib.request

_HERE = pathlib.Path(__file__).resolve().parent
_CACHE = _HERE / "_app_restored.py"
_GOOD = (
    "https://raw.githubusercontent.com/jiu-zui-90817/AutoReloader/"
    "f4819a9e516f99bcd262e79f60cbdf77d82219e9/Frontend/workshop/app.py"
)

_ICON_OLD = (
    "        try:\n"
    "            from pathlib import Path as _Path\n"
    "            for cand in (\n"
    "                _Path(__file__).resolve().parents[2] / \"assets\" / \"workshop.ico\",\n"
    "                _Path(__file__).resolve().parent / \"assets\" / \"workshop.ico\",\n"
    "                _Path.cwd() / \"assets\" / \"workshop.ico\",\n"
    "            ):\n"
    "                if cand.is_file():\n"
    "                    self.setWindowIcon(QIcon(str(cand)))\n"
    "                    break\n"
    "        except Exception:\n"
    "            pass"
)

_ICON_NEW = (
    "        try:\n"
    "            for cand in (\n"
    "                get_app_dir() / \"workshop.ico\",\n"
    "                get_app_dir() / \"editor.ico\",\n"
    "                get_app_dir() / \"assets\" / \"workshop.ico\",\n"
    "                get_bundle_dir() / \"workshop.ico\",\n"
    "                get_repo_root() / \"assets\" / \"workshop.ico\",\n"
    "                Path(__file__).resolve().parents[2] / \"assets\" / \"workshop.ico\",\n"
    "                Path(__file__).resolve().parent / \"assets\" / \"workshop.ico\",\n"
    "                Path.cwd() / \"assets\" / \"workshop.ico\",\n"
    "            ):\n"
    "                if cand.is_file():\n"
    "                    self.setWindowIcon(QIcon(str(cand)))\n"
    "                    break\n"
    "        except Exception:\n"
    "            pass"
)

_RUN_OLD = "def run():\n    app = QApplication.instance() or QApplication(sys.argv)"

_RUN_NEW = (
    "def run():\n"
    "    app = QApplication.instance() or QApplication(sys.argv)\n"
    "    try:\n"
    "        for cand in (\n"
    "            get_app_dir() / \"workshop.ico\",\n"
    "            get_app_dir() / \"editor.ico\",\n"
    "            get_app_dir() / \"assets\" / \"workshop.ico\",\n"
    "            get_bundle_dir() / \"workshop.ico\",\n"
    "            get_repo_root() / \"assets\" / \"workshop.ico\",\n"
    "        ):\n"
    "            if cand.is_file():\n"
    "                app.setWindowIcon(QIcon(str(cand)))\n"
    "                break\n"
    "    except Exception:\n"
    "        pass"
)


def _ensure_restored() -> pathlib.Path:
    if _CACHE.is_file() and _CACHE.stat().st_size > 10000:
        text = _CACHE.read_text(encoding="utf-8")
        if "class WorkshopWindow" in text and 'get_app_dir() / "workshop.ico"' in text:
            return _CACHE
    try:
        with urllib.request.urlopen(_GOOD, timeout=60) as resp:
            text = resp.read().decode("utf-8")
    except Exception as e:
        if _CACHE.is_file() and _CACHE.stat().st_size > 10000:
            return _CACHE
        raise RuntimeError(
            f"无法从 GitHub 恢复 workshop/app.py: {e}\n"
            "请手动: git checkout f4819a9e -- Frontend/workshop/app.py"
        ) from e
    if _ICON_OLD in text:
        text = text.replace(_ICON_OLD, _ICON_NEW, 1)
    if _RUN_OLD in text:
        text = text.replace(_RUN_OLD, _RUN_NEW, 1)
    _CACHE.write_text(text, encoding="utf-8")
    return _CACHE


_path = _ensure_restored()
_ns: dict = {"__name__": "app", "__file__": str(_path)}
exec(compile(_path.read_text(encoding="utf-8"), str(_path), "exec"), _ns)
run = _ns["run"]
globals().update({k: v for k, v in _ns.items() if not k.startswith("_")})
