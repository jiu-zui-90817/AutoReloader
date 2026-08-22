"""CI 组装 MO/YR 完整发布目录。布局对齐用户约定（前端合并目录）。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _log(*args) -> None:
    parts = []
    for a in args:
        s = str(a)
        try:
            s.encode(sys.stdout.encoding or "utf-8")
            parts.append(s)
        except Exception:
            parts.append(s.encode("unicode_escape", errors="replace").decode("ascii"))
    try:
        print(*parts)
    except Exception:
        print(*(repr(a) for a in args))


def set_profile(path: Path, profile: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data["active_profile"] = profile
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def must(p: Path) -> None:
    if not p.exists():
        names = [x.name for x in p.parent.iterdir()] if p.parent.is_dir() else []
        raise SystemExit(f"missing {p.as_posix()} parent={names!r}")
    _log("OK", p.as_posix(), p.stat().st_size)


def pack(
    root_name: str,
    editor_profile: str,
    workshop_profile: str,
    launcher: str,
    label: str,
) -> None:
    """
    热重载工具-xxx/
      MO启动器.exe | YR启动器.exe
      AutoReloader.dll
      ReloaderConfig.ini
      使用说明.txt
      INI工程编辑器&战术工坊/
        INI工程编辑器.exe
        战术工坊.exe
        config.json
        profiles.json
        schemas/common_flags.json
        使用说明.txt
    """
    root = Path(root_name)
    if root.exists():
        shutil.rmtree(root)
    tools = root / "INI工程编辑器&战术工坊"
    tools.mkdir(parents=True)
    (tools / "schemas").mkdir(parents=True)

    # 根目录：启动器 + 引擎
    shutil.copy(Path("bins/launchers") / launcher, root / launcher)
    shutil.copy("bins/engine/AutoReloader.dll", root / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy(src, root / "ReloaderConfig.ini")
            break

    # 前端：同一目录，共享 schemas / 配置
    # 编辑器产物
    ed_exe = Path("bins/editor/INI工程编辑器.exe")
    if not ed_exe.is_file():
        # 兼容英文中间名
        for c in Path("bins/editor").glob("*.exe"):
            ed_exe = c
            break
    shutil.copy2(ed_exe, tools / "INI工程编辑器.exe")
    shutil.copy2("bins/editor/config.json", tools / "config.json")
    schema_src = Path("bins/editor/schemas/common_flags.json")
    if not schema_src.is_file():
        schema_src = Path("shared/schemas/common_flags.json")
    shutil.copy2(schema_src, tools / "schemas" / "common_flags.json")
    if Path("bins/editor/使用说明.txt").is_file():
        shutil.copy2("bins/editor/使用说明.txt", tools / "使用说明.txt")
    elif Path("Frontend/editor/使用说明.txt").is_file():
        shutil.copy2("Frontend/editor/使用说明.txt", tools / "使用说明.txt")

    # 工坊产物
    ws_exe = Path("bins/workshop/战术工坊.exe")
    if not ws_exe.is_file():
        for c in Path("bins/workshop").glob("*.exe"):
            ws_exe = c
            break
    shutil.copy2(ws_exe, tools / "战术工坊.exe")
    shutil.copy2("bins/workshop/profiles.json", tools / "profiles.json")
    # schemas 已复制一份即可

    must(root / launcher)
    must(root / "AutoReloader.dll")
    must(tools / "INI工程编辑器.exe")
    must(tools / "战术工坊.exe")
    must(tools / "config.json")
    must(tools / "profiles.json")
    must(tools / "schemas" / "common_flags.json")

    set_profile(tools / "config.json", editor_profile)
    set_profile(tools / "profiles.json", workshop_profile)

    readme = (
        f"AutoReloader 完整包 — {label}\n\n"
        f"根目录：\n"
        f"  {launcher}\n"
        f"  AutoReloader.dll\n"
        f"  ReloaderConfig.ini\n\n"
        f"INI工程编辑器&战术工坊\\  前端工具（共享 schemas/配置）\n"
        f"  编辑器 profile: {editor_profile}\n"
        f"  工坊 profile: {workshop_profile}\n\n"
        f"使用：\n"
        f"  1. 将根目录 DLL / 配置 / 启动器 放入游戏根目录\n"
        f"  2. 用本包启动器启动游戏\n"
        f"  3. 前端目录可放任意可写位置运行两个 exe\n"
        f"  4. cache、console_config 为运行后生成，不必随包分发\n"
        f"  5. INI 保存为 UTF-8 无 BOM\n"
    )
    (root / "使用说明.txt").write_text(readme, encoding="utf-8")
    _log("packed", root_name)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass

    ed = json.loads(Path("bins/editor/config.json").read_text(encoding="utf-8-sig"))
    keys = list((ed.get("profiles") or {}).keys())
    yr_ed = (
        "YurisRevenge"
        if "YurisRevenge" in keys
        else ("YuriRevenge_Vanilla" if "YuriRevenge_Vanilla" in keys else "MentalOmega")
    )
    pack(
        "热重载工具-心灵终结",
        "MentalOmega",
        "MentalOmega",
        "MO启动器.exe",
        "心灵终结 (Mental Omega)",
    )
    pack(
        "热重载工具-尤里的复仇",
        yr_ed,
        "YurisRevenge",
        "YR启动器.exe",
        "尤里的复仇 (Yuri's Revenge)",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
