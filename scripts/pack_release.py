"""CI 组装 MO/YR 完整发布目录（UTF-8 无 BOM）。在仓库根运行。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def set_profile(path: Path, profile: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    data["active_profile"] = profile
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def must(p: Path) -> None:
    if not p.exists():
        raise SystemExit(f"missing {p}")
    print("OK", p, p.stat().st_size)


def pack(
    root_name: str,
    editor_profile: str,
    workshop_profile: str,
    launcher: str,
    label: str,
) -> None:
    root = Path(root_name)
    if root.exists():
        shutil.rmtree(root)
    (root / "引擎").mkdir(parents=True)
    (root / "INI工程编辑器").mkdir(parents=True)
    (root / "战术工坊").mkdir(parents=True)

    shutil.copy("bins/engine/AutoReloader.dll", root / "引擎" / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy(src, root / "引擎" / "ReloaderConfig.ini")
            break
    shutil.copy(Path("bins/launchers") / launcher, root / "引擎" / launcher)

    for item in Path("bins/editor").iterdir():
        dest = root / "INI工程编辑器" / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    must(root / "INI工程编辑器" / "INI工程编辑器.exe")
    must(root / "INI工程编辑器" / "config.json")
    must(root / "INI工程编辑器" / "schemas" / "common_flags.json")
    set_profile(root / "INI工程编辑器" / "config.json", editor_profile)

    for item in Path("bins/workshop").iterdir():
        dest = root / "战术工坊" / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    must(root / "战术工坊" / "战术工坊.exe")
    must(root / "战术工坊" / "profiles.json")
    must(root / "战术工坊" / "schemas" / "common_flags.json")
    set_profile(root / "战术工坊" / "profiles.json", workshop_profile)

    text = (
        f"AutoReloader 完整包 — {label}\n"
        f"引擎 / INI工程编辑器 / 战术工坊\n"
        f"编辑器 profile: {editor_profile}\n"
        f"工坊 profile: {workshop_profile}\n"
        "将「引擎」目录文件放入游戏根目录，用本包启动器启动游戏。\n"
        "GitHub Actions 下载的 zip 解压一次即可。\n"
        "INI 保存编码：UTF-8 无 BOM。\n"
    )
    (root / "使用说明.txt").write_text(text, encoding="utf-8")
    print("packed", root_name)


def main() -> int:
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
