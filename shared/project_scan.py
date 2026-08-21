"""
按 profile 扫描游戏目录：rules（含 #include）+ art + CSF，列出可调试单位与下拉选项。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
                "art_files": ["artmo.ini", "artmd.ini"],
                "csf_files": ["ra2md.csf", "stringtable*.csf"],
                "type_lists": DEFAULT_TYPE_LISTS,
            }
        },
        "hotreload": {"target_ini": "hotfix.ini"},
    }


class GameProject:
    """只读工程扫描：单位列表 + 原文案 + 选项索引，供战术工坊快调。"""

    def __init__(self, game_dir: Path, profile: dict, csf_patterns: Optional[List[str]] = None):
        self.game_dir = Path(game_dir)
        self.profile = profile
        self.rules: Optional[INIFile] = None
        self.rules_path: Optional[Path] = None
        self.art: Optional[INIFile] = None
        self.csf = CSFParser()
        self.section_sources: Dict[str, str] = {}
        self._option_index: Dict[str, List[str]] = {}
        self._load_rules()
        self._load_art()
        patterns = csf_patterns or profile.get("csf_files") or ["ra2md.csf", "stringtable*.csf"]
        try:
            self.csf = load_csf_files(patterns, self.game_dir)
        except Exception:
            pass
        self._build_option_index()

    def _load_first_ini(self, names: List[str]) -> Optional[INIFile]:
        for name in names:
            path = self.game_dir / name
            if not path.is_file():
                continue
            ini = INIFile()
            if ini.load_with_includes(path, self.game_dir):
                for src, sec_names in ini.file_sections.items():
                    for n in sec_names:
                        self.section_sources.setdefault(n.lower(), src)
                return ini
        return None

    def _load_rules(self) -> None:
        ini = self._load_first_ini(self.profile.get("rules_files") or [])
        if ini:
            self.rules = ini
            # best-effort path
            for name in self.profile.get("rules_files") or []:
                p = self.game_dir / name
                if p.is_file():
                    self.rules_path = p
                    break

    def _load_art(self) -> None:
        self.art = self._load_first_ini(self.profile.get("art_files") or [])

    def get_section(self, section_id: str) -> Optional[INISection]:
        if self.rules:
            sec = self.rules.get_section(section_id)
            if sec:
                return sec
        if self.art:
            return self.art.get_section(section_id)
        return None

    def get_section_text(self, section_id: str) -> str:
        sec = None
        if self.rules:
            sec = self.rules.get_section(section_id)
        if not sec and self.art:
            sec = self.art.get_section(section_id)
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
            # 单位类仍以 rules 注册表为准
            if lst in ("Animations", "Particles", "ParticleSystems", "Projectiles"):
                ids = self._registry_ids(lst)
            else:
                ids = list(self.rules.get_list(lst) or [])
            items = [i for i in ids if self.get_section(i)]
            if items:
                groups[lst] = items
        return groups

    def _registry_ids(self, list_name: str) -> List[str]:
        """从 rules 与 art 两边读注册表。"""
        out: List[str] = []
        seen: Set[str] = set()
        for ini in (self.rules, self.art):
            if not ini:
                continue
            for i in ini.get_list(list_name) or []:
                if i and i.lower() not in seen:
                    seen.add(i.lower())
                    out.append(i)
            # 别名
            aliases = {
                "Animations": ["AnimTypes", "Animations"],
                "ProjectileTypes": ["Projectiles", "ProjectileTypes"],
                "Projectiles": ["Projectiles", "ProjectileTypes"],
            }
            for alt in aliases.get(list_name, []):
                if alt == list_name:
                    continue
                for i in ini.get_list(alt) or []:
                    if i and i.lower() not in seen:
                        seen.add(i.lower())
                        out.append(i)
        return out

    def _all_section_names(self) -> List[str]:
        names: List[str] = []
        seen: Set[str] = set()
        for ini in (self.rules, self.art):
            if not ini:
                continue
            for n in ini.sections.keys():
                if n.lower() not in seen:
                    seen.add(n.lower())
                    names.append(n)
        return names

    def _looks_like_weapon(self, sec: INISection) -> bool:
        keys = {k.lower() for k in sec.keys}
        return ("damage" in keys and ("projectile" in keys or "warhead" in keys)) or (
            "rof" in keys and "range" in keys
        )

    def _looks_like_warhead(self, sec: INISection) -> bool:
        keys = {k.lower() for k in sec.keys}
        return "verses" in keys or "cellspread" in keys or "percentatmax" in keys

    def _looks_like_projectile(self, sec: INISection) -> bool:
        keys = {k.lower() for k in sec.keys}
        return ("image" in keys and ("rot" in keys or "arm" in keys or "shadow" in keys)) or (
            "inviso" in keys
        )

    def _build_option_index(self) -> None:
        """合并注册表 + 启发式扫描，供下拉使用。"""
        idx: Dict[str, List[str]] = {}

        def merge(kind: str, ids: List[str]) -> None:
            cur = idx.setdefault(kind, [])
            seen = {x.lower() for x in cur}
            for i in ids:
                if i and i.lower() not in seen:
                    seen.add(i.lower())
                    cur.append(i)

        for kind in (
            "WeaponTypes", "Warheads", "ProjectileTypes", "Projectiles",
            "SuperWeaponTypes", "Animations", "AnimTypes", "Particles",
            "ParticleSystems",
        ):
            merge(kind, self._registry_ids(kind))

        # 单位 ID 可作为 Image 候选项
        unit_ids: List[str] = []
        for g in ("InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes"):
            unit_ids.extend(self._registry_ids(g))
        merge("_images", unit_ids)

        # 启发式补全：扫 rules（武器/弹头等主要在 rules）
        if self.rules:
            for name, sec in self.rules.sections.items():
                if self._looks_like_weapon(sec):
                    merge("WeaponTypes", [name])
                if self._looks_like_warhead(sec):
                    merge("Warheads", [name])
                if self._looks_like_projectile(sec):
                    merge("ProjectileTypes", [name])
                    merge("Projectiles", [name])

        # 动画多在 art
        if self.art:
            merge("Animations", self._registry_ids("Animations"))
            # art 里大量 section 是 shp 名，不宜全塞进 Animations；仅注册表 + 明确列表

        self._option_index = idx

    def list_options(self, list_name: str) -> List[str]:
        if list_name in self._option_index:
            return list(self._option_index[list_name])
        # 回退
        return self._registry_ids(list_name)

    def export_option_index(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self._option_index.items()}

    def import_option_index(self, data: Dict[str, List[str]]) -> None:
        if not isinstance(data, dict):
            return
        for k, v in data.items():
            if isinstance(v, list):
                self._option_index[k] = [str(x) for x in v if x]
