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
      Tools/
        INIEditor.exe
        Workshop.exe
        config.json
        profiles.json
        schemas/common_flags.json
        README.txt   (optional)
    """
    root = Path(root_name)
    if root.exists():
        shutil.rmtree(root)
    tools = root / "Tools"
    tools.mkdir(parents=True)
    (tools / "schemas").mkdir(parents=True)

    # 启动器
    launcher_src = _first_exe(Path("bins/launchers"), launcher_src_names)
    shutil.copy2(launcher_src, root / launcher_dst)

    # 引擎
    shutil.copy2("bins/engine/AutoReloader.dll", root / "AutoReloader.dll")
    for src in (Path("bins/engine/ReloaderConfig.ini"), Path("Config/ReloaderConfig.ini")):
        if src.is_file():
            shutil.copy2(src, root / "ReloaderConfig.ini")
            break

    # 编辑器
    ed_exe = _first_exe(
        Path("bins/editor"),
        ["INIEditor.exe", "INI工程编辑器.exe", "editor.exe"],
    )
    shutil.copy2(ed_exe, tools / "INIEditor.exe")
    shutil.copy2("bins/editor/config.json", tools / "config.json")
    schema_src = Path("bins/editor/schemas/common_flags.json")
    if not schema_src.is_file():
        schema_src = Path("shared/schemas/common_flags.json")
    shutil.copy2(schema_src, tools / "schemas" / "common_flags.json")
    for readme_src in (
        Path("bins/editor/使用说明.txt"),
        Path("Frontend/editor/使用说明.txt"),
        Path("bins/editor/README.txt"),
    ):
        if readme_src.is_file():
            shutil.copy2(readme_src, tools / "README.txt")
            break

    # 工坊
    ws_exe = _first_exe(
        Path("bins/workshop"),
        ["Workshop.exe", "战术工坊.exe", "workshop.exe"],
    )
    shutil.copy2(ws_exe, tools / "Workshop.exe")
    shutil.copy2("bins/workshop/profiles.json", tools / "profiles.json")

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
        f"Tools\\  frontend (shared schemas/config)\n"
        f"  INIEditor.exe   (editor profile: {editor_profile})\n"
        f"  Workshop.exe    (workshop profile: {workshop_profile})\n\n"
        f"Usage:\n"
        f"  1. Copy DLL / ReloaderConfig.ini / launcher into the game folder\n"
        f"  2. Start the game with this package's launcher (admin UAC)\n"
        f"  3. Run Tools\\INIEditor.exe or Tools\\Workshop.exe from any writable path\n"
        f"  4. cache / local config files are created at runtime; no need to ship them\n"
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
