"""CI 组装 MO/YR 完整发布目录。包名与目录均为英文：AutoReloader-MO / AutoReloader-YR。"""
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


def _first_exe(folder: Path, preferred: list[str]) -> Path:
    for name in preferred:
        c = folder / name
        if c.is_file():
            return c
    for c in sorted(folder.glob("*.exe")):
        return c
    raise SystemExit(f"no exe in {folder}")


def _merge_tree(src: Path, dst: Path, *, overwrite_exe: bool = False) -> int:
    """把 src 整树合并进 dst。同名文件：exe 默认不覆盖已有；其它文件后写覆盖（便于共用 Qt DLL）。"""
    n = 0
    if not src.is_dir():
        raise SystemExit(f"merge source missing: {src}")
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if path.suffix.lower() == ".exe" and target.exists() and not overwrite_exe:
            _log("skip exe exists", target.as_posix())
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        n += 1
    return n


def pack(
    root_name: str,
    editor_profile: str,
    workshop_profile: str,
    launcher_src_names: list[str],
    launcher_dst: str,
    label: str,
) -> None:
    """
    AutoReloader-MO/  or AutoReloader-YR/
      MOLauncher.exe | YRLauncher.exe
      AutoReloader.dll
      ReloaderConfig.ini
      README.txt
      Tools/                    # 编辑器 + 工坊共用运行库（standalone 合并）
        INIEditor.exe
        Workshop.exe
        config.json
        profiles.json
        schemas/common_flags.json
        *.dll / PySide6 / ...   # Nuitka standalone 依赖，两工具共享
    """
    root = Path(root_name)
    if root.exists():
        shutil.rmtree(root)
    tools = root / "Tools"
    tools.mkdir(parents=True)

    # 启动器
    launcher_src = _first_exe(Path("bins/launchers"), launcher_src_names)
    shutil.copy2(launcher_src, root / launcher_dst)

    # 引擎
    shutil.copy2("bins/engine/AutoReloader.dll", root / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy2(src, root / "ReloaderConfig.ini")
            break

    ed_bin = Path("bins/editor")
    ws_bin = Path("bins/workshop")

    # 先合并编辑器整包，再合并工坊（DLL 同名覆盖 = 共用一份 Qt/PySide）
    n_ed = _merge_tree(ed_bin, tools, overwrite_exe=True)
    n_ws = _merge_tree(ws_bin, tools, overwrite_exe=True)
    _log("merged editor files", n_ed, "workshop files", n_ws)

    # 确保主程序文件名固定
    for preferred, names in (
        ("INIEditor.exe", ["INIEditor.exe", "INI_Editor.exe", "INI工程编辑器.exe", "editor.exe", "main.exe"]),
        ("Workshop.exe", ["Workshop.exe", "战术工坊.exe", "workshop.exe", "main.exe"]),
    ):
        target = tools / preferred
        if target.is_file():
            continue
        found = None
        for name in names:
            c = tools / name
            if c.is_file():
                found = c
                break
        if not found:
            # bins 里可能只有一层
            try:
                found = _first_exe(ed_bin if preferred.startswith("INI") else ws_bin, names)
            except SystemExit:
                found = None
        if found and found.resolve() != target.resolve():
            shutil.copy2(found, target)
        if not target.is_file():
            raise SystemExit(f"missing {target} after merge")

    # 旁路配置（可写目录 = Tools）
    cfg = ed_bin / "config.json"
    if cfg.is_file():
        shutil.copy2(cfg, tools / "config.json")
    prof = ws_bin / "profiles.json"
    if prof.is_file():
        shutil.copy2(prof, tools / "profiles.json")
    schema_src = ed_bin / "schemas" / "common_flags.json"
    if not schema_src.is_file():
        schema_src = Path("shared/schemas/common_flags.json")
    (tools / "schemas").mkdir(parents=True, exist_ok=True)
    if schema_src.is_file():
        shutil.copy2(schema_src, tools / "schemas" / "common_flags.json")
    for readme_src in (
        ed_bin / "使用说明.txt",
        Path("Frontend/editor/使用说明.txt"),
        ed_bin / "README.txt",
    ):
        if readme_src.is_file():
            shutil.copy2(readme_src, tools / "README.txt")
            break

    must(root / launcher_dst)
    must(root / "AutoReloader.dll")
    must(tools / "INIEditor.exe")
    must(tools / "Workshop.exe")
    must(tools / "config.json")
    must(tools / "profiles.json")
    must(tools / "schemas" / "common_flags.json")

    set_profile(tools / "config.json", editor_profile)
    set_profile(tools / "profiles.json", workshop_profile)

    readme = (
        f"AutoReloader full package — {label}\n\n"
        f"Root:\n"
        f"  {launcher_dst}\n"
        f"  AutoReloader.dll\n"
        f"  ReloaderConfig.ini\n\n"
        f"Tools\\  editor + workshop share one runtime folder (no onefile temp extract)\n"
        f"  INIEditor.exe   (profile: {editor_profile})\n"
        f"  Workshop.exe    (profile: {workshop_profile})\n"
        f"  config.json / profiles.json / schemas / Qt-PySide DLLs\n\n"
        f"Usage:\n"
        f"  1. Place launcher + DLL + ReloaderConfig.ini in the game folder\n"
        f"  2. Start the game with this package's launcher (admin UAC)\n"
        f"  3. Run Tools\\INIEditor.exe or Tools\\Workshop.exe (keep Tools folder intact)\n"
        f"  4. Do not move only the .exe out of Tools — DLLs must stay beside them\n"
        f"  5. INI saves use UTF-8 without BOM\n"
    )
    (root / "README.txt").write_text(readme, encoding="utf-8")
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
