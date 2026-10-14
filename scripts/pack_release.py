"""CI 组装 MO/YR 完整发布目录。editor / workshop 各自独立 standalone，互不覆盖。"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _log(*args) -> None:
    try:
        print(*args)
    except Exception:
        print(*(repr(a) for a in args))


def set_profile(path: Path, profile: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if "active_profile" in data:
        data["active_profile"] = profile
    elif "profiles" in data and profile in data.get("profiles", {}):
        # workshop profiles.json 可能结构不同，尽量兼容
        data["active_profile"] = profile
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def must(p: Path) -> None:
    if not p.exists():
        names = [x.name for x in p.parent.iterdir()] if p.parent.is_dir() else []
        raise SystemExit(f"missing {p.as_posix()} parent={names!r}")
    _log("OK", p.as_posix(), p.stat().st_size)


def _copy_tree(src: Path, dst: Path) -> int:
    if not src.is_dir():
        raise SystemExit(f"source missing: {src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return sum(1 for _ in dst.rglob("*") if _.is_file())


def pack(
    root_name: str,
    editor_profile: str,
    workshop_profile: str,
    launcher_src_names: list[str],
    launcher_dst: str,
    label: str,
) -> None:
    root = Path(root_name)
    if root.exists():
        shutil.rmtree(root)
    tools = root / "Tools"
    tools.mkdir(parents=True)

    # 启动器
    launchers = Path("bins/launchers")
    launcher_src = None
    for name in launcher_src_names:
        c = launchers / name
        if c.is_file():
            launcher_src = c
            break
    if launcher_src is None:
        for c in sorted(launchers.glob("*.exe")):
            launcher_src = c
            break
    if launcher_src is None:
        raise SystemExit("no launcher exe found")
    shutil.copy2(launcher_src, root / launcher_dst)

    # 引擎
    shutil.copy2("bins/engine/AutoReloader.dll", root / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy2(src, root / "ReloaderConfig.ini")
            break

    ed_bin = Path("bins/editor")
    ws_bin = Path("bins/workshop")

    # 各自独立复制，绝不互相覆盖
    n_ed = _copy_tree(ed_bin, tools / "editor")
    n_ws = _copy_tree(ws_bin, tools / "workshop")
    _log("copied editor files", n_ed, "workshop files", n_ws)

    # 强制主程序名
    ed_exe = tools / "editor" / "INIEditor.exe"
    ws_exe = tools / "workshop" / "Workshop.exe"
    if not ed_exe.is_file():
        # 兜底找任意 exe 改名
        found = next((p for p in (tools / "editor").glob("*.exe")), None)
        if found:
            found.rename(ed_exe)
    if not ws_exe.is_file():
        found = next((p for p in (tools / "workshop").glob("*.exe")), None)
        if found:
            found.rename(ws_exe)

    must(root / launcher_dst)
    must(root / "AutoReloader.dll")
    must(ed_exe)
    must(ws_exe)
    must(tools / "editor" / "config.json")
    must(tools / "workshop" / "profiles.json")
    must(tools / "editor" / "schemas" / "common_flags.json")

    # 设置 profile
    set_profile(tools / "editor" / "config.json", editor_profile)
    if (tools / "workshop" / "profiles.json").is_file():
        set_profile(tools / "workshop" / "profiles.json", workshop_profile)

    readme = (
        f"AutoReloader full package — {label}\n\n"
        f"Root:\n"
        f"  {launcher_dst}\n"
        f"  AutoReloader.dll\n"
        f"  ReloaderConfig.ini\n\n"
        f"Tools\\editor\\     INI 工程编辑器（完整独立运行时）\n"
        f"  INIEditor.exe\n"
        f"Tools\\workshop\\   战术工坊（完整独立运行时）\n"
        f"  Workshop.exe\n\n"
        f"Usage:\n"
        f"  1. 把启动器 + DLL + ReloaderConfig.ini 放到游戏根目录\n"
        f"  2. 用本包启动器（管理员）启动游戏\n"
        f"  3. 运行 Tools\\editor\\INIEditor.exe 或 Tools\\workshop\\Workshop.exe\n"
        f"  4. 不要只移动单个 exe，整个子目录必须保持完整\n"
        f"  5. 如启动失败，查看同目录下的 INIEditor.err.txt / Workshop.err.txt\n"
    )
    (root / "README.txt").write_text(readme, encoding="utf-8")
    _log("packed", root_name)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
        "AutoReloader-MO",
        "MentalOmega",
        "MentalOmega",
        ["MOLauncher.exe", "MO启动器.exe"],
        "MOLauncher.exe",
        "Mental Omega",
    )
    pack(
        "AutoReloader-YR",
        yr_ed,
        "YurisRevenge",
        ["YRLauncher.exe", "YR启动器.exe"],
        "YRLauncher.exe",
        "Yuri's Revenge",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
