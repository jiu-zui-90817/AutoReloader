"""CI 组装 MO/YR 完整发布目录。

Tools/ 内编辑器与工坊共用一份 _internal（PySide6 / Python 运行时），
避免两套完整依赖叠在一起。用户可见程序名为中文。
"""
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
    if "active_profile" in data or "profiles" in data:
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


def _merge_tree(src: Path, dst: Path) -> int:
    if not src.is_dir():
        return 0
    n = 0
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        n += 1
    return n


def _ensure_exe(folder: Path, preferred: str, aliases: list[str]) -> Path:
    target = folder / preferred
    if target.is_file():
        return target
    for name in aliases:
        c = folder / name
        if c.is_file():
            if c.resolve() != target.resolve():
                shutil.copy2(c, target)
            return target
    found = next((p for p in folder.glob("*.exe")), None)
    if found:
        shutil.copy2(found, target)
        return target
    raise SystemExit(f"missing exe for {preferred} in {folder}")


def _dir_size_mb(p: Path) -> float:
    total = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


def _copy_icon(candidates: list[Path], dest: Path) -> bool:
    for c in candidates:
        if c.is_file():
            shutil.copy2(c, dest)
            _log("icon", dest.name, "from", c.as_posix())
            return True
    return False


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

    launchers = Path("bins/launchers")
    launcher_src = None
    for name in launcher_src_names:
        c = launchers / name
        if c.is_file():
            launcher_src = c
            break
    if launcher_src is None:
        launcher_src = next(iter(sorted(launchers.glob("*.exe"))), None)
    if launcher_src is None:
        raise SystemExit("no launcher exe found")
    shutil.copy2(launcher_src, root / launcher_dst)

    shutil.copy2("bins/engine/AutoReloader.dll", root / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy2(src, root / "ReloaderConfig.ini")
            break

    ed_bin = Path("bins/editor")
    ws_bin = Path("bins/workshop")
    if not ed_bin.is_dir():
        raise SystemExit("bins/editor missing")
    if not ws_bin.is_dir():
        raise SystemExit("bins/workshop missing")

    n_ed = _copy_tree(ed_bin, tools)
    _log("base from editor files", n_ed)

    ws_exe_src = None
    for name in ("战术工坊.exe", "Workshop.exe", "main.exe"):
        c = ws_bin / name
        if c.is_file():
            ws_exe_src = c
            break
    if ws_exe_src is None:
        ws_exe_src = next(iter(ws_bin.glob("*.exe")), None)
    if ws_exe_src is None:
        raise SystemExit("Workshop exe not found in bins/workshop")
    shutil.copy2(ws_exe_src, tools / "战术工坊.exe")

    assets = Path("assets")
    _copy_icon(
        [ed_bin / "editor.ico", assets / "editor.ico", tools / "editor.ico"],
        tools / "editor.ico",
    )
    if not _copy_icon(
        [ws_bin / "workshop.ico", assets / "workshop.ico"],
        tools / "workshop.ico",
    ):
        _log("WARN: workshop.ico missing")

    if (ws_bin / "profiles.json").is_file():
        shutil.copy2(ws_bin / "profiles.json", tools / "profiles.json")
    ws_schemas = ws_bin / "schemas"
    if ws_schemas.is_dir():
        (tools / "schemas").mkdir(parents=True, exist_ok=True)
        for f in ws_schemas.glob("*"):
            if f.is_file() and not (tools / "schemas" / f.name).exists():
                shutil.copy2(f, tools / "schemas" / f.name)

    ed_internal = tools / "_internal"
    ws_internal = ws_bin / "_internal"
    if ws_internal.is_dir() and ed_internal.is_dir():
        n_merge = _merge_tree(ws_internal, ed_internal)
        _log("merged workshop-only files into _internal", n_merge)
    elif ws_internal.is_dir() and not ed_internal.is_dir():
        n_merge = _merge_tree(ws_internal, tools)
        _log("merged workshop _internal into tools root", n_merge)
    else:
        for name in ("app", "fields", "shared"):
            s = ws_bin / name
            if s.exists() and not (tools / name).exists():
                if s.is_dir():
                    shutil.copytree(s, tools / name)
                else:
                    shutil.copy2(s, tools / name)
                _log("copied workshop package", name)

    if not ed_internal.is_dir():
        n_extra = _merge_tree(ws_bin, tools)
        _log("flat merge extras", n_extra)

    ed_exe = _ensure_exe(
        tools,
        "INI工程编辑器.exe",
        ["INIEditor.exe", "INI_Editor.exe", "main.exe"],
    )
    ws_exe = _ensure_exe(
        tools,
        "战术工坊.exe",
        ["Workshop.exe", "main.exe"],
    )
    for leftover in ("INIEditor.exe", "Workshop.exe", "INI_Editor.exe"):
        p = tools / leftover
        if p.is_file() and p.resolve() not in (ed_exe.resolve(), ws_exe.resolve()):
            try:
                p.unlink()
            except Exception:
                pass

    must(root / launcher_dst)
    must(root / "AutoReloader.dll")
    must(ed_exe)
    must(ws_exe)
    must(tools / "config.json")
    if (tools / "profiles.json").is_file():
        must(tools / "profiles.json")
    if (tools / "schemas" / "common_flags.json").is_file():
        must(tools / "schemas" / "common_flags.json")

    set_profile(tools / "config.json", editor_profile)
    if (tools / "profiles.json").is_file():
        set_profile(tools / "profiles.json", workshop_profile)

    tools_mb = _dir_size_mb(tools)
    _log(f"Tools/ total size: {tools_mb} MB (shared runtime)")

    readme = (
        f"AutoReloader 完整包 — {label}\n\n"
        f"根目录:\n"
        f"  {launcher_dst}\n"
        f"  AutoReloader.dll\n"
        f"  ReloaderConfig.ini\n\n"
        f"Tools\\  （编辑器 + 工坊共用 _internal）\n"
        f"  INI工程编辑器.exe\n"
        f"  战术工坊.exe\n"
        f"  editor.ico / workshop.ico\n"
        f"  config.json / profiles.json / schemas /\n"
        f"  _internal\\        请勿删除\n\n"
        f"说明:\n"
        f"  1. 启动器 + DLL + ReloaderConfig.ini 放到游戏根目录\n"
        f"  2. 用本包启动器（管理员）启动游戏\n"
        f"  3. 运行 Tools 下的中文程序名即可\n"
        f"  4. 请保持整个 Tools 目录完整\n"
        f"  5. 启动失败看同目录 INIEditor_boot.log / INIEditor_crash.log\n"
        f"  6. 正式版无黑控制台；错误会弹窗并写日志\n"
    )
    (root / "README.txt").write_text(readme, encoding="utf-8")
    _log("packed", root_name, f"Tools={tools_mb}MB")


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
