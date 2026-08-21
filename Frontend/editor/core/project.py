"""
工程管理
- 合并 / 单文件双模式
- 可编辑文件列表 = 配置主文件 + #include 拆分文件（不扫地图等无关 ini）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .ini_parser import INIFile, INISection
from .csf_parser import CSFParser, load_csf_files
from .save_util import save_section_to_file, normalize_section_body


# 根据 section 内字段猜测类型（无注册表时的临时分类）
# 已知全局/系统节名（不区分大小写）
KNOWN_GLOBAL = {
    "general": "全局 General",
    "combattamage": "全局 CombatDamage",
    "combatdamage": "全局 CombatDamage",
    "audiovisual": "全局 AudioVisual",
    "specialweapons": "全局 SpecialWeapons",
    "jumpjetcontrols": "全局 JumpjetControls",
    "multiplayerdialogsettings": "全局 多人",
    "ai": "全局 AI",
    "iq": "全局 IQ",
    "rocketdata": "全局 RocketData",
    "crate": "全局 Crate",
    "powersups": "全局 Powerups",
    "powerups": "全局 Powerups",
    "radiation": "全局 Radiation",
    "easy": "难度 Easy",
    "normal": "难度 Normal",
    "difficult": "难度 Difficult",
    "countries": "国家 Countries",
    "sides": "阵营 Sides",
    "colors": "颜色 Colors",
    "tiberiums": "矿石 Tiberiums",
    "overlaytypes": "覆盖物 OverlayTypes",
    "smudgetypes": "污迹 SmudgeTypes",
    "terraintypes": "地形 TerrainTypes",
    "animation": "动画列表",
    "animations": "动画列表",
    "movie": "影片",
    "movies": "影片",
    "sound": "音效列表",
    "sounds": "音效列表",
    "themes": "音乐 Themes",
    "variable": "变量",
    "variables": "变量",
    "basic": "地图 Basic",
    "map": "地图 Map",
    "waypoints": "地图 Waypoints",
    "house": "地图 House",
    "houses": "地图 Houses",
    "team": "地图 Team",
    "teams": "地图 Teams",
    "triggers": "地图 Triggers",
    "events": "地图 Events",
    "actions": "地图 Actions",
    "tags": "地图 Tags",
    "celltags": "地图 CellTags",
    "digest": "地图 Digest",
}


def guess_section_kind(sec: INISection) -> str:
    name_l = sec.name.lower().strip()
    if name_l in KNOWN_GLOBAL:
        return KNOWN_GLOBAL[name_l]
    if name_l.startswith("sound") or name_l.startswith("vox"):
        return "音效相关"
    if name_l.startswith("anim") or name_l.endswith("anim"):
        return "动画相关"

    keys = {k.lower() for k in sec.keys}
    if "verses" in keys or "cellspread" in keys or "percentatmax" in keys:
        return "疑似弹头(未注册)"
    if "rof" in keys and ("damage" in keys or "warhead" in keys):
        return "疑似武器(未注册)"
    if "trajectory" in keys or "subjecttocliffs" in keys or "proximity" in keys:
        return "疑似抛射体(未注册)"
    if "type" in keys and ("action" in keys or "sidebarimage" in keys):
        return "疑似超武(未注册)"
    if "foundation" in keys or "buildup" in keys:
        return "疑似建筑(未注册)"
    if "locomotor" in keys or "movementzone" in keys:
        if "landable" in keys or "airportbound" in keys:
            return "疑似飞行器(未注册)"
        return "疑似载具/步兵(未注册)"
    if "strength" in keys and ("primary" in keys or "owner" in keys or "category" in keys):
        return "疑似单位(未注册)"
    if "script" in keys or "taskforce" in keys or "group" in keys:
        return "AI 相关"
    country_hits = sum(1 for k in (
        "multiplay", "side", "prefix", "suffix", "listindex",
        "color", "smartai", "parentcountry", "spawnranking",
        "buildtimeinfantrymult", "armorinfantrymult",
    ) if k in keys)
    if country_hits >= 2 or ("side" in keys and "multiplay" in keys):
        return "国家 Country"
    if "particlesystem" in name_l or name_l.endswith("sys"):
        if "behaveslike" in keys or "holdswhat" in keys:
            return "疑似粒子系统(未注册)"
    if "behaveslike" in keys and ("maxdc" in keys or "maxec" in keys):
        return "疑似粒子(未注册)"
    if "loopcount" in keys and ("report" in keys or "anim" in keys or "rate" in keys):
        return "疑似动画(未注册)"
    digit_keys = sum(1 for k in list(sec.keys)[:8] if k.strip().isdigit())
    if digit_keys >= 2:
        return "列表/其它注册表"
    if not keys:
        return "空节"
    return "杂项"


class Project:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.project_dir: Optional[Path] = None
        self.profile_name: str = ""
        self.profile: Dict[str, Any] = {}

        self.rules: Optional[INIFile] = None
        self.art: Optional[INIFile] = None
        self.ai: Optional[INIFile] = None

        self.single_ini: Optional[INIFile] = None
        self.single_path: Optional[Path] = None
        self.work_mode: str = "merged"

        self.csf: CSFParser = CSFParser()
        self.section_sources: Dict[str, str] = {}
        self.allowed_files: List[Path] = []
        self.type_list_index: Dict[str, List[Path]] = {}

        self.load_config()

    def load_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {"active_profile": "MentalOmega", "profiles": {}}
        self.profile_name = self.config.get("active_profile", "")
        self.profile = self.config.get("profiles", {}).get(self.profile_name, {})

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def set_active_profile(self, name: str):
        if name in self.config.get("profiles", {}):
            self.profile_name = name
            self.profile = self.config["profiles"][name]
            self.config["active_profile"] = name
            self.save_config()

    def _load_merged(self, filename: str) -> Optional[INIFile]:
        if not self.project_dir:
            return None
        path = self.project_dir / filename
        if not path.exists():
            return None
        ini = INIFile()
        if not ini.load_with_includes(path, self.project_dir):
            return None
        for src_path, names in ini.file_sections.items():
            p = Path(src_path)
            if p.is_file():
                self._add_allowed(p)
            for n in names:
                k = n.lower()
                if k not in self.section_sources:
                    self.section_sources[k] = str(p.resolve()) if p.is_file() else src_path
        for name, sec in ini.sections.items():
            if name.lower() in self.section_sources:
                continue
            if sec.source_file:
                resolved = self._resolve_name(sec.source_file)
                if resolved:
                    self.section_sources[name.lower()] = str(resolved)
                    self._add_allowed(resolved)
        for f in ini.loaded_files:
            self._add_allowed(Path(f))
        return ini

    def _add_allowed(self, p: Path):
        if not p or not p.exists():
            return
        rp = p.resolve()
        for existing in self.allowed_files:
            if existing.resolve() == rp:
                return
        self.allowed_files.append(rp)

    def _resolve_name(self, name: str) -> Optional[Path]:
        p = Path(name)
        if p.is_file():
            return p.resolve()
        if not self.project_dir:
            return None
        for f in self.allowed_files:
            if f.name.lower() == p.name.lower():
                return f
        cand = self.project_dir / p.name
        if cand.is_file():
            return cand.resolve()
        for f in self.allowed_files:
            sibling = f.parent / p.name
            if sibling.is_file():
                return sibling.resolve()
        return None

    def open_directory(self, dir_path: str | Path) -> bool:
        path = Path(dir_path)
        if not path.is_dir():
            return False
        self.project_dir = path
        self.rules = self.art = self.ai = None
        self.single_ini = None
        self.single_path = None
        self.section_sources = {}
        self.allowed_files = []
        self.type_list_index = {}
        self.csf = CSFParser()

        for name in self.profile.get("rules_files", []):
            ini = self._load_merged(name)
            if ini:
                self.rules = ini
                break
        for name in self.profile.get("art_files", []):
            ini = self._load_merged(name)
            if ini:
                self.art = ini
                break
        for name in self.profile.get("ai_files", []):
            ini = self._load_merged(name)
            if ini:
                self.ai = ini
                break

        for key in ("rules_files", "art_files", "ai_files"):
            for name in self.profile.get(key, []):
                p = path / name
                if p.is_file():
                    self._add_allowed(p)

        self.csf = load_csf_files(self.profile.get("csf_files", []), path)
        self._rebuild_type_list_index()
        self.work_mode = "merged"
        return self.rules is not None or bool(self.allowed_files)

    def _rebuild_type_list_index(self):
        self.type_list_index = {}
        type_names = set(self.profile.get("type_lists", []))
        type_names.update([
            "InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes",
            "WeaponTypes", "Warheads", "ProjectileTypes", "SuperWeaponTypes",
            "TaskForces", "ScriptTypes", "TeamTypes", "AITriggerTypes",
        ])
        for ini in (self.rules, self.art, self.ai):
            if not ini:
                continue
            for src, names in ini.file_sections.items():
                p = Path(src)
                if not p.is_file():
                    continue
                for n in names:
                    if n in type_names or n.lower() in {x.lower() for x in type_names}:
                        canon = n
                        for t in type_names:
                            if t.lower() == n.lower():
                                canon = t
                                break
                        self.type_list_index.setdefault(canon, [])
                        rp = p.resolve()
                        if rp not in self.type_list_index[canon]:
                            self.type_list_index[canon].append(rp)
            for tname in type_names:
                sec = ini.get_section(tname)
                if not sec:
                    continue
                src = self.section_sources.get(tname.lower())
                if src:
                    p = Path(src)
                    if p.is_file():
                        self.type_list_index.setdefault(tname, [])
                        rp = p.resolve()
                        if rp not in self.type_list_index[tname]:
                            self.type_list_index[tname].append(rp)

    def files_with_type_list(self, type_list: str) -> List[Path]:
        for k, v in self.type_list_index.items():
            if k.lower() == type_list.lower():
                return list(v)
        return []

    def list_ini_files(self) -> List[Path]:
        return sorted(self.allowed_files, key=lambda x: x.name.lower())

    def open_single_file(self, filepath: Path) -> bool:
        filepath = Path(filepath)
        if not filepath.is_file():
            return False
        ini = INIFile()
        if not ini.load_file_only(filepath):
            return False
        self.single_ini = ini
        self.single_path = filepath.resolve()
        self.work_mode = "single"
        csf_dir = self.project_dir or filepath.parent
        patterns = self.profile.get("csf_files") or ["ra2md.csf", "stringtable*.csf", "ra2.csf"]
        try:
            self.csf = load_csf_files(patterns, csf_dir)
        except Exception:
            pass
        return True

    def set_merged_mode(self):
        self.work_mode = "merged"
        self.single_ini = None
        self.single_path = None

    def active_ini(self) -> Optional[INIFile]:
        if self.work_mode == "single":
            return self.single_ini
        return self.rules

    def get_type_lists(self, ini: Optional[INIFile] = None) -> Dict[str, List[str]]:
        target = ini or self.active_ini()
        if not target:
            return {}
        names = self.profile.get("type_lists", [
            "InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes",
            "WeaponTypes", "Warheads", "ProjectileTypes", "SuperWeaponTypes",
            "Animations", "Particles", "ParticleSystems", "Projectiles",
            "TaskForces", "ScriptTypes", "TeamTypes", "AITriggerTypes",
        ])
        return target.get_all_type_ids(names)

    def classify_sections(self, ini: INIFile) -> Dict[str, List[str]]:
        lists = self.get_type_lists(ini)
        used = set()
        groups: Dict[str, List[str]] = {}
        reg_list: List[str] = []
        extra_lists = [
            "Countries", "Sides", "Colors", "Animations", "Particles", "ParticleSystems", "Projectiles",
            "TaskForces", "ScriptTypes", "TeamTypes", "AITriggerTypes",
        ]
        all_lists = dict(lists)
        for en in extra_lists:
            if en not in all_lists:
                ids = ini.get_list(en) if hasattr(ini, "get_list") else []
                if ids:
                    all_lists[en] = ids

        for list_name, ids in all_lists.items():
            items = []
            for uid in ids:
                if ini.get_section(uid):
                    items.append(uid)
                    used.add(uid.lower())
            if items:
                groups[list_name] = items
            if ini.get_section(list_name):
                if list_name not in reg_list:
                    reg_list.append(list_name)
                used.add(list_name.lower())

        for name in ini.section_order:
            if name.startswith("#") or name.lower() in used:
                continue
            sec = ini.get_section(name)
            if not sec:
                continue
            kind = guess_section_kind(sec)
            groups.setdefault(kind, []).append(name)

        ordered: Dict[str, List[str]] = {}
        if reg_list:
            ordered["注册表"] = reg_list
        for k, v in groups.items():
            if k == "注册表":
                continue
            ordered[k] = v
        return ordered

    def get_section(self, name: str, prefer: Optional[INIFile] = None) -> Optional[INISection]:
        if prefer:
            sec = prefer.get_section(name)
            if sec:
                return sec
        if self.work_mode == "single" and self.single_ini:
            return self.single_ini.get_section(name)
        for ini in (self.rules, self.art, self.ai):
            if not ini:
                continue
            sec = ini.get_section(name)
            if sec:
                return sec
        return None

    def get_source_path_for_section(self, section_id: str) -> Optional[Path]:
        if self.work_mode == "single" and self.single_path:
            return self.single_path

        def from_ini(ini: Optional[INIFile]) -> Optional[Path]:
            if not ini:
                return None
            sec = ini.get_section(section_id)
            if not sec:
                return None
            if sec.source_file:
                resolved = self._resolve_name(sec.source_file)
                if resolved and resolved.is_file():
                    return resolved
            sid = section_id.lower()
            for src, names in ini.file_sections.items():
                if any(n.lower() == sid for n in names):
                    p = Path(src)
                    if p.is_file():
                        return p.resolve()
            return None

        path = from_ini(self.rules)
        if path:
            return path
        key = section_id.lower()
        if key in self.section_sources:
            p = Path(self.section_sources[key])
            if p.is_file():
                return p
        if not (self.rules and self.rules.get_section(section_id)):
            path = from_ini(self.art) or from_ini(self.ai)
            if path:
                return path
        return None

    def get_display_name(self, section_id: str, prefer: Optional[INIFile] = None) -> str:
        sec = self.get_section(section_id, prefer=prefer)
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

    def inject_section_memory(
        self,
        section_id: str,
        section_text: str,
        source_path: Optional[Path] = None,
        type_list: Optional[str] = None,
    ) -> None:
        body = normalize_section_body(section_id, section_text)
        sec = INISection(section_id)
        for line in body.splitlines():
            s = line.strip()
            if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                continue
            if "=" in s:
                if ";" in s:
                    s = s.split(";", 1)[0].strip()
                k, _, v = s.partition("=")
                k, v = k.strip(), v.strip()
                if k:
                    sec.set(k, v)
        if source_path:
            sec.source_file = Path(source_path).name
            self.section_sources[section_id.lower()] = str(Path(source_path).resolve())
            self._add_allowed(Path(source_path))

        target = self.active_ini()
        if target is None and self.rules:
            target = self.rules
        if target is None:
            return
        if section_id not in target.sections and section_id.lower() not in {x.lower() for x in target.sections}:
            target.section_order.append(section_id)
        old_key = None
        for k in list(target.sections.keys()):
            if k.lower() == section_id.lower():
                old_key = k
                break
        if old_key and old_key != section_id:
            del target.sections[old_key]
            target.section_order = [section_id if x == old_key else x for x in target.section_order]
        target.sections[section_id] = sec

        if type_list and target.get_section(type_list):
            lst = target.get_section(type_list)
            vals = {v.strip().lower() for v in lst.keys.values()}
            if section_id.lower() not in vals:
                n = 0
                while str(n) in lst.keys:
                    n += 1
                lst.set(str(n), section_id)

    def get_section_text(self, section_id: str, prefer: Optional[INIFile] = None) -> str:
        sec = self.get_section(section_id, prefer=prefer or self.active_ini())
        if not sec:
            return f"; Section [{section_id}] not found"
        return sec.to_text()

    def get_loaded_files_summary(self) -> str:
        if self.work_mode == "single" and self.single_path:
            return f"单文件: {self.single_path.name}"
        parts, total = [], 0
        for label, ini in (("Rules", self.rules), ("Art", self.art), ("AI", self.ai)):
            if ini:
                n = len(ini.loaded_files)
                parts.append(f"{label}:{n}")
                total += n
        return f"合并 {total}个INI(" + ",".join(parts) + ") 允许文件:{len(self.allowed_files)}"

    def save_section_text(
        self,
        section_id: str,
        section_text: str,
        target_path: Optional[Path] = None,
        is_new: bool = False,
        peer_ids: Optional[List[str]] = None,
    ) -> dict:
        if self.work_mode == "single" and self.single_path:
            path = self.single_path
        else:
            path = Path(target_path) if target_path else self.get_source_path_for_section(section_id)

        if path is None:
            return {"ok": False, "need_path": True, "message": "无法确定写入文件"}

        if not self.project_dir:
            return {"ok": False, "message": "未打开工程"}

        result = save_section_to_file(
            path,
            section_id,
            section_text,
            backup_root=self.project_dir / "backups",
            is_new=is_new,
            peer_section_names=peer_ids or [],
        )
        if not result.get("ok"):
            return result

        body = normalize_section_body(section_id, section_text)
        new_sec = INISection(section_id)
        new_sec.source_file = Path(path).name
        for line in body.splitlines():
            s = line.strip()
            if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                continue
            if "=" in s:
                if ";" in s:
                    main, _, cmt = s.partition(";")
                    cmt = cmt.strip()
                else:
                    main, cmt = s, ""
                k, _, v = main.partition("=")
                k, v = k.strip(), v.strip()
                if k:
                    new_sec.set(k, v, cmt)

        targets = []
        if self.work_mode == "single" and self.single_ini:
            targets = [self.single_ini]
        else:
            targets = [i for i in (self.rules, self.art, self.ai) if i]

        for ini in targets:
            existing = ini.get_section(section_id)
            if existing:
                existing.keys = new_sec.keys
                existing.key_order = list(new_sec.key_order)
                existing.inline_comments = dict(new_sec.inline_comments)
                existing.source_file = Path(path).name
            elif self.work_mode == "single":
                ini.sections[section_id] = new_sec
                if section_id not in ini.section_order:
                    ini.section_order.append(section_id)

        self.section_sources[section_id.lower()] = str(Path(path).resolve())
        result["path"] = str(path)

        if self.work_mode == "single" and self.single_path:
            self.open_single_file(self.single_path)

        return result
