"""
按 profile 扫描游戏目录：rules（含 #include）+ CSF，列出可调试单位。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .ini_loader import INIFile, INISection
from .csf_loader import CSFParser, load_csf_files


DEFAULT_TYPE_LISTS = [
    "InfantryTypes",
    "VehicleTypes",
    "AircraftTypes",
    "BuildingTypes",
    "WeaponTypes",
    "Warheads",
    "ProjectileTypes",
    "SuperWeaponTypes",
]


def load_profiles(profiles_path: Path) -> dict:
    if profiles_path.exists():
        return json.loads(profiles_path.read_text(encoding="utf-8"))
    return {
        "active_profile": "MentalOmega",
        "profiles": {
            "MentalOmega": {
                "display_name": "Mental Omega",
                "rules_files": ["rulesmo.ini", "rulesmd.ini"],
                "csf_files": ["ra2md.csf", "stringtable*.csf"],
                "type_lists": DEFAULT_TYPE_LISTS,
            }
        },
        "hotreload": {"target_ini": "hotfix.ini"},
    }


class GameProject:
    """只读工程扫描：单位列表 + 原文案，供战术工坊快调。"""

    def __init__(self, game_dir: Path, profile: dict, csf_patterns: Optional[List[str]] = None):
        self.game_dir = Path(game_dir)
        self.profile = profile
        self.rules: Optional[INIFile] = None
        self.rules_path: Optional[Path] = None
        self.csf = CSFParser()
        self.section_sources: Dict[str, str] = {}
        self._load_rules()
        patterns = csf_patterns or profile.get("csf_files") or ["ra2md.csf", "stringtable*.csf"]
        try:
            self.csf = load_csf_files(patterns, self.game_dir)
        except Exception:
            pass

    def _load_rules(self) -> None:
        for name in self.profile.get("rules_files", []):
            path = self.game_dir / name
            if not path.is_file():
                continue
            ini = INIFile()
            if ini.load_with_includes(path, self.game_dir):
                self.rules = ini
                self.rules_path = path
                for src, names in ini.file_sections.items():
                    for n in names:
                        self.section_sources.setdefault(n.lower(), src)
                break

    def get_section(self, section_id: str) -> Optional[INISection]:
        if not self.rules:
            return None
        return self.rules.get_section(section_id)

    def get_section_text(self, section_id: str) -> str:
        sec = self.get_section(section_id)
        if not sec:
            return f"[{section_id}]\n"
        return sec.to_text()

    def display_name(self, section_id: str) -> str:
        sec = self.get_section(section_id)
        if not sec:
            return section_id
        uiname = sec.get("UIName", "")
        name = sec.get("Name", "")
        csf_name = self.csf.get_uiname(uiname) if uiname else ""
        if not csf_name and name:
            csf_name = name
        if not csf_name:
            csf_name = self.csf.get(f"Name:{section_id}") or self.csf.get(section_id) or ""
        if csf_name and csf_name != section_id:
            return f"{section_id}  -  {csf_name}"
        return section_id

    def list_groups(self) -> Dict[str, List[str]]:
        """注册表 → ID 列表（只保留 rules 里确有 section 的）。"""
        if not self.rules:
            return {}
        names = self.profile.get("type_lists") or DEFAULT_TYPE_LISTS
        groups: Dict[str, List[str]] = {}
        for lst in names:
            ids = self.rules.get_list(lst)
            items = [i for i in ids if self.rules.get_section(i)]
            if items:
                groups[lst] = items
        return groups

    def list_options(self, list_name: str) -> List[str]:
        if not self.rules:
            return []
        return list(self.rules.get_list(list_name) or [])
