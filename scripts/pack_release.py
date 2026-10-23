"""CI 组装 MO/YR 完整发布目录。

Tools/ 内编辑器与工坊共用一份 _internal（PySide6 / Python 运行时），
避免两套完整依赖叠在一起。
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
    """把 src 中 dst 尚不存在的文件补进去（不覆盖已有 DLL / 公共库）。"""
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


def pack(
    root_name: str,
    editor_profile: str,
    workshop_profile: str,
    launcher_src_names: list[str],
    launcher_dst: str,
    label: str,
) -> None:
    """
    Tools/ 布局（共用运行时）::

        Tools/
          INIEditor.exe
          Workshop.exe
          config.json
          profiles.json
          schemas/
          qt.conf
          _internal/     # 编辑器为底，工坊独有模块补入
    """
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
        launcher_src = next(iter(sorted(launchers.glob("*.exe"))), None)
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
    if not ed_bin.is_dir():
        raise SystemExit("bins/editor missing")
    if not ws_bin.is_dir():
        raise SystemExit("bins/workshop missing")

    # 1) 以编辑器整包为底（含 _internal）
    n_ed = _copy_tree(ed_bin, tools)
    _log("base from editor files", n_ed)

    # 2) 工坊 exe + 配置落到同一目录
    ws_exe_src = None
    for name in ("Workshop.exe", "main.exe"):
        c = ws_bin / name
        if c.is_file():
            ws_exe_src = c
            break
    if ws_exe_src is None:
        ws_exe_src = next(iter(ws_bin.glob("*.exe")), None)
    if ws_exe_src is None:
        raise SystemExit("Workshop.exe not found in bins/workshop")
    shutil.copy2(ws_exe_src, tools / "Workshop.exe")

    if (ws_bin / "profiles.json").is_file():
        shutil.copy2(ws_bin / "profiles.json", tools / "profiles.json")
    ws_schemas = ws_bin / "schemas"
    if ws_schemas.is_dir():
        (tools / "schemas").mkdir(parents=True, exist_ok=True)
        for f in ws_schemas.glob("*"):
            if f.is_file() and not (tools / "schemas" / f.name).exists():
                shutil.copy2(f, tools / "schemas" / f.name)

    # 3) 合并工坊 _internal 中编辑器没有的部分（app/fields/shared 等）
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

    ed_exe = _ensure_exe(tools, "INIEditor.exe", ["INI_Editor.exe", "main.exe"])
    ws_exe = tools / "Workshop.exe"
    if not ws_exe.is_file():
        raise SystemExit("Workshop.exe missing after merge")

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
        f"AutoReloader full package — {label}\n\n"
        f"Root:\n"
        f"  {launcher_dst}\n"
        f"  AutoReloader.dll\n"
        f"  ReloaderConfig.ini\n\n"
        f"Tools\\  （编辑器 + 工坊共用 _internal 运行时）\n"
        f"  INIEditor.exe     INI 工程编辑器\n"
        f"  Workshop.exe      战术工坊\n"
        f"  config.json / profiles.json / schemas /\n"
        f"  _internal\\        请勿删除或挪走\n\n"
        f"Usage:\n"
        f"  1. 启动器 + DLL + ReloaderConfig.ini 放到游戏根目录\n"
        f"  2. 用本包启动器（管理员）启动游戏\n"
        f"  3. 运行 Tools\\INIEditor.exe 或 Tools\\Workshop.exe\n"
        f"  4. 整个 Tools 目录必须保持完整，不要只拷某一个 exe\n"
        f"  5. 启动失败可看 Tools\\INIEditor_boot.log\n"
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
