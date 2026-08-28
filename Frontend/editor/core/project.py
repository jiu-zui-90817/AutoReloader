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
from .save_util import save_section_to_file, normalize_section_body, save_type_list_distributed


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
    "countries": "注册表 Countries",
    "sides": "注册表 Sides",
    "colors": "注册表 Colors",
    "tiberiums": "矿石 Tiberiums",
    "overlaytypes": "注册表 OverlayTypes",
    "smudgetypes": "注册表 SmudgeTypes",
    "terraintypes": "注册表 TerrainTypes",
    "animation": "注册表 Animations",
    "animations": "注册表 Animations",
    "movie": "影片",
    "movies": "影片",
    "sound": "音效列表",
    "sounds": "音效列表",
    "themes": "音乐 Themes",
    "variable": "变量",
    "variables": "变量",
    "genericprerequisites": "Ares GenericPrerequisites",
    "attacheffecttypes": "Ares AttachEffectTypes",
    "voxelanims": "VoxelAnims",
    "particlesystems": "注册表 ParticleSystems",
    "particles": "注册表 Particles",
    "projectiles": "注册表 Projectiles",
    "projectiletypes": "注册表 ProjectileTypes",
    "weapontypes": "注册表 WeaponTypes",
    "warheads": "注册表 Warheads",
    "superweapontypes": "注册表 SuperWeaponTypes",
    "infantrytypes": "注册表 InfantryTypes",
    "vehicletypes": "注册表 VehicleTypes",
    "aircrafttypes": "注册表 AircraftTypes",
    "buildingtypes": "注册表 BuildingTypes",
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

# 对象树主分类顺序（注册表名 → 显示）
TYPE_LIST_ORDER = [
    "InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes",
    "WeaponTypes", "Warheads", "ProjectileTypes", "Projectiles",
    "SuperWeaponTypes",
    "Animations", "VoxelAnims", "Particles", "ParticleSystems",
    "OverlayTypes", "SmudgeTypes", "TerrainTypes", "Tiberiums",
    "Countries", "Sides", "Colors",
    "AttachEffectTypes",
    "TaskForces", "ScriptTypes", "TeamTypes", "AITriggerTypes", "AITriggerTypesEnable",
]

# 这些注册表的「条目 ID」是键名，不是 0=XXX 的值
REGISTRY_USE_KEYS = {
    "sides", "colors", "genericprerequisites",
}

DEFAULT_TYPE_LISTS = [
    "InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes",
    "WeaponTypes", "Warheads", "ProjectileTypes", "Projectiles",
    "SuperWeaponTypes",
    "Animations", "VoxelAnims", "Particles", "ParticleSystems",
    "OverlayTypes", "SmudgeTypes", "TerrainTypes", "Tiberiums",
    "Countries", "Sides", "Colors",
    "AttachEffectTypes",
    "TaskForces", "ScriptTypes", "TeamTypes", "AITriggerTypes", "AITriggerTypesEnable",
]


def registry_ids(ini: INIFile, list_name: str) -> List[str]:
    """
    从注册表节取出 ID 列表。
    - 常规 TypeList：0=E1, 1=MTNK → 取「值」
    - Ares 追加：+=SiegfriedWH_MG / + = Huge-slaveHE → 取「值」（可多行）
    - Sides/Colors 等：GDI=... → 取「键」
    - 可与数字序号混写
    """
    sec = ini.get_section(list_name)
    if not sec:
        return []
    keys = list(sec.key_order)
    if not keys:
        return []

    ln = list_name.lower()
    if ln in REGISTRY_USE_KEYS:
        return [
            k.strip()
            for k in keys
            if k.strip() and not k.strip().startswith(";") and not k.startswith("+@")
        ]

    out: List[str] = []
    seen = set()

    def add(uid: str):
        u = uid.strip()
        if not u or u.startswith(";"):
            return
        ul = u.lower()
        if ul not in seen:
            seen.add(ul)
            out.append(u)

    for k in keys:
        val = (sec.keys.get(k) or "").strip()
        # Ares += 追加项（内部键 +@n）
        if k.startswith("+@") or k.strip() in ("+", "+=", "++"):
            add(val)
            continue
        if k.strip().isdigit():
            add(val)
            continue

    if out:
        # 已有数字序或 +=，再扫一遍非 + 的命名键作补充（少见）
        return out

    # 键即 ID（部分 MOD 写法）
    return [
        k.strip()
        for k in keys
        if k.strip() and not k.strip().startswith(";") and not k.startswith("+@")
    ]


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
    if "type" in keys and ("action" in keys or "sidebarimage" in keys or "rechargetime" in keys):
        return "疑似超武(未注册)"
    if "duration" in keys and ("animation" in keys or "penetratesironcurtain" in keys or "armormultiplier" in keys):
        return "疑似AttachEffect(未注册)"
    if "foundation" in keys or "buildup" in keys:
        return "疑似建筑(未注册)"
    if "locomotor" in keys or "movementzone" in keys:
        if "landable" in keys or "airportbound" in keys:
            return "疑似飞行器(未注册)"
        return "疑似载具/步兵(未注册)"
    if "strength" in keys and ("primary" in keys or "owner" in keys or "category" in keys):
        return "疑似单位(未注册)"
    if "script" in keys or "taskforce" in keys:
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
    if "loopcount" in keys and ("report" in keys or "rate" in keys):
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
        """写入 config；失败则尝试 %LocalAppData%\\MO_INI_Editor\\config.json。"""
        import os
        payload = json.dumps(self.config, ensure_ascii=False, indent=2)
        targets = [Path(self.config_path)]
        la = os.environ.get("LOCALAPPDATA") or os.environ.get("LocalAppData")
        if la:
            targets.append(Path(la) / "MO_INI_Editor" / "config.json")
        targets.append(Path.home() / ".mo_ini_editor" / "config.json")
        last_err = None
        for path in targets:
            try:
                path = Path(path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload, encoding="utf-8")
                self.config_path = path
                return
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise last_err

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
        type_names.update(DEFAULT_TYPE_LISTS)
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
        """读取各注册表 ID。合并 profile 与 DEFAULT_TYPE_LISTS。"""
        target = ini or self.active_ini()
        if not target:
            return {}
        names = list(self.profile.get("type_lists") or [])
        for n in DEFAULT_TYPE_LISTS:
            if n not in names and n.lower() not in {x.lower() for x in names}:
                names.append(n)
        result: Dict[str, List[str]] = {}
        for lst in names:
            ids = registry_ids(target, lst)
            if ids:
                result[lst] = ids
        return result

    def classify_sections(self, ini: INIFile) -> Dict[str, List[str]]:
        """
        对象树分组：
        1) 各 TypeList 注册表中的 ID（即使本节体暂缺也列出，避免遗漏）
        2) 注册表节本身
        3) 其余节用字段启发式归类
        """
        lists = self.get_type_lists(ini)
        used: set = set()
        groups: Dict[str, List[str]] = {}
        reg_list: List[str] = []

        # 固定顺序 + 其余
        ordered_names = list(TYPE_LIST_ORDER)
        for ln in lists:
            if ln not in ordered_names:
                ordered_names.append(ln)

        for list_name in ordered_names:
            ids = lists.get(list_name) or []
            if not ids:
                # 仍可能有空注册表节
                if ini.get_section(list_name):
                    if list_name not in reg_list:
                        reg_list.append(list_name)
                    used.add(list_name.lower())
                continue
            items: List[str] = []
            for uid in ids:
                items.append(uid)
                used.add(uid.lower())
            groups[list_name] = items
            if ini.get_section(list_name):
                if list_name not in reg_list:
                    reg_list.append(list_name)
                used.add(list_name.lower())

        # GenericPrerequisites 节本身
        if ini.get_section("GenericPrerequisites"):
            if "GenericPrerequisites" not in reg_list:
                reg_list.append("GenericPrerequisites")
            used.add("genericprerequisites")

        for name in ini.section_order:
            if name.startswith("#") or name.lower() in used:
                continue
            sec = ini.get_section(name)
            if not sec:
                continue
            kind = guess_section_kind(sec)
            groups.setdefault(kind, []).append(name)
            used.add(name.lower())

        ordered: Dict[str, List[str]] = {}
        if reg_list:
            ordered["注册表"] = reg_list
        for k in ordered_names:
            if k in groups and groups[k]:
                ordered[k] = groups[k]
        for k, v in groups.items():
            if k not in ordered and k != "注册表":
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

    def _parse_section_kv_lines(self, section_id: str, section_text: str) -> list:
        """[(key, value, inline_comment), ...]；+= 记为 ('+', value, comment)。"""
        body = normalize_section_body(section_id, section_text)
        out = []
        for line in body.splitlines():
            s = line.strip()
            if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                continue
            if s.startswith("+="):
                rest = s[2:]
                if ";" in rest:
                    main, _, cmt = rest.partition(";")
                    out.append(("+", main.strip(), cmt.strip()))
                else:
                    out.append(("+", rest.strip(), ""))
                continue
            if "=" not in s:
                continue
            if ";" in s:
                main, _, cmt = s.partition(";")
                cmt = cmt.strip()
            else:
                main, cmt = s, ""
            k, _, v = main.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                out.append((k, v, cmt))
        return out

    def _resolve_key_origin(self, path_str: str) -> str:
        if not path_str:
            return ""
        try:
            return str(Path(path_str).resolve())
        except Exception:
            return str(path_str)

    def _extract_section_raw_from_file(self, filepath: Path, section_id: str) -> str:
        """读取磁盘上该文件中 [section] 原始文本（含注释）。"""
        from core.save_util import read_text, find_section_span
        path = Path(filepath)
        if not path.is_file():
            return ""
        try:
            text, _enc = read_text(path)
        except Exception:
            return ""
        span = find_section_span(text, section_id)
        if not span:
            return ""
        return text[span[0]:span[1]]

    def _build_body_preserving_comments(
        self,
        section_id: str,
        filepath: str,
        kvs: list,
    ) -> str:
        """
        在该文件原有节块上更新键值，保留纯注释行与行内注释。
        kvs: [(out_key, value, comment), ...]，out_key 为 '+=' 或键名
        """
        raw = self._extract_section_raw_from_file(Path(filepath), section_id)
        normal = {}
        plus_list = []
        for ok, val, cmt in kvs:
            if ok == "+=":
                plus_list.append(((val or "").strip(), cmt or ""))
            else:
                normal[str(ok).lower()] = (ok, val or "", cmt or "")

        def fmt_plus(val, cmt):
            line = "+=" + (val or "")
            if cmt:
                line += " ; " + str(cmt).lstrip(" ;")
            return line

        def fmt_kv(ok, val, cmt):
            line = str(ok) + "=" + (val or "")
            if cmt:
                line += " ; " + str(cmt).lstrip(" ;")
            return line

        if not raw.strip():
            lines_out = ["[" + section_id + "]"]
            for ok, val, cmt in kvs:
                if ok == "+=":
                    lines_out.append(fmt_plus(val, cmt))
                else:
                    lines_out.append(fmt_kv(ok, val, cmt))
            return chr(10).join(lines_out)

        out_lines = []
        seen_normal = set()
        plus_i = 0
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                out_lines.append(line.rstrip())
                continue
            if s.startswith("[") and "]" in s:
                out_lines.append("[" + section_id + "]")
                continue
            if s.startswith(";"):
                out_lines.append(line.rstrip())
                continue
            if s.startswith("+="):
                rest = s[2:]
                if ";" in rest:
                    main, _, old_cmt = rest.partition(";")
                    old_cmt = old_cmt.strip()
                else:
                    main, old_cmt = rest.strip(), ""
                if plus_i < len(plus_list):
                    val, cmt = plus_list[plus_i]
                    plus_i += 1
                    out_lines.append(fmt_plus(val, cmt or old_cmt))
                continue
            if "=" in s:
                if ";" in s:
                    main, _, old_cmt = s.partition(";")
                    old_cmt = old_cmt.strip()
                else:
                    main, old_cmt = s, ""
                k, _, _v = main.partition("=")
                k = k.strip()
                kl = k.lower()
                if kl in normal:
                    ok, val, cmt = normal[kl]
                    seen_normal.add(kl)
                    out_lines.append(fmt_kv(ok, val, cmt or old_cmt))
                continue
            out_lines.append(line.rstrip())

        for kl, (ok, val, cmt) in normal.items():
            if kl not in seen_normal:
                out_lines.append(fmt_kv(ok, val, cmt))
        while plus_i < len(plus_list):
            val, cmt = plus_list[plus_i]
            plus_i += 1
            out_lines.append(fmt_plus(val, cmt))
        return chr(10).join(out_lines)

    def plan_section_write(
        self,
        section_id: str,
        section_text: str,
        target_path: Optional[Path] = None,
        is_new: bool = False,
    ) -> dict:
        """按键来源生成多文件写入计划（不落盘）；正文尽量保留原文件注释。"""
        if self.work_mode == "single" and self.single_path:
            path = self.single_path
        else:
            path = Path(target_path) if target_path else self.get_source_path_for_section(section_id)
        if path is None:
            return {"ok": False, "need_path": True, "message": "无法确定默认写入文件", "files": []}

        default = self._resolve_key_origin(str(path))
        mem = self.get_section(section_id)
        parsed = self._parse_section_kv_lines(section_id, section_text)

        origin_by_key = {}
        origin_by_plus_val = {}
        if mem:
            for k in mem.key_order:
                src = self._resolve_key_origin(
                    (mem.key_sources or {}).get(k) or mem.source_file or default
                )
                if str(k).startswith("+@"):
                    val = (mem.keys.get(k) or "").strip().lower()
                    if val:
                        origin_by_plus_val[val] = src
                else:
                    origin_by_key[str(k).lower()] = src

        groups = {}
        for item in parsed:
            k, v, cmt = item[0], item[1], item[2] if len(item) > 2 else ""
            if k in ("+", "+=", "++"):
                src = origin_by_plus_val.get((v or "").strip().lower()) or default
                out_k = "+="
            else:
                src = origin_by_key.get(str(k).lower()) or default
                out_k = k
            groups.setdefault(src or default, []).append((out_k, v, cmt))

        if mem and not is_new:
            prev_files = set()
            for k in mem.key_order:
                prev_files.add(
                    self._resolve_key_origin(
                        (mem.key_sources or {}).get(k) or mem.source_file or default
                    )
                )
            for pf in prev_files:
                if pf and pf not in groups:
                    groups[pf] = []

        files = []
        for fpath, kvs in groups.items():
            if not fpath:
                continue
            body = self._build_body_preserving_comments(section_id, fpath, kvs)
            files.append({
                "path": fpath,
                "body": body,
                "count": len(kvs),
                "keys": [a for a, _, _ in kvs],
            })
        files.sort(key=lambda x: x["path"].lower())
        return {
            "ok": True,
            "files": files,
            "default_path": default,
            "section_id": section_id,
            "message": "计划写入 %d 个文件" % len(files),
        }

    def execute_section_write_plan(
        self,
        plan: dict,
        peer_ids: Optional[List[str]] = None,
        is_new: bool = False,
    ) -> dict:
        files = plan.get("files") or []
        if not files:
            return {"ok": False, "message": "没有可写入的内容"}
        try:
            _bk = int((self.config.get("settings") or {}).get("backup_keep", 100))
        except (TypeError, ValueError):
            _bk = 100
        if self.project_dir:
            backup_root = self.project_dir / "backups"
        else:
            backup_root = Path(files[0]["path"]).parent / "backups"

        messages = []
        written = []
        section_id = plan.get("section_id") or ""
        for item in files:
            path = Path(item["path"])
            body = item["body"]
            count = int(item.get("count") or 0)
            if count == 0 and not path.is_file():
                continue
            r = save_section_to_file(
                path,
                section_id,
                body,
                backup_root=backup_root,
                is_new=is_new and count > 0 and not path.is_file(),
                peer_section_names=peer_ids or [],
                backup_keep=_bk,
            )
            written.append({"path": str(path), "ok": r.get("ok"), "msg": r.get("message")})
            messages.append(r.get("message") or str(path))
            if not r.get("ok"):
                return {
                    "ok": False,
                    "message": "；".join(messages),
                    "written": written,
                    "path": str(path),
                }

        new_sec = INISection(section_id)
        for item in files:
            fpath = item["path"]
            for line in (item.get("body") or "").splitlines():
                s = line.strip()
                if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                    continue
                if s.startswith("+="):
                    new_sec.set("+", s[2:].strip(), source_file=fpath)
                elif "=" in s:
                    main, _, cmt = s.partition(";")
                    k, _, v = main.partition("=")
                    if k.strip():
                        new_sec.set(k.strip(), v.strip(), cmt.strip(), source_file=fpath)

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
                existing.key_sources = dict(new_sec.key_sources)
                existing.source_file = new_sec.source_file or existing.source_file
            elif self.work_mode == "single":
                ini.sections[section_id] = new_sec
                if section_id not in ini.section_order:
                    ini.section_order.append(section_id)

        if section_id and files:
            try:
                self.section_sources[section_id.lower()] = str(Path(files[0]["path"]).resolve())
            except Exception:
                pass

        return {
            "ok": True,
            "message": "；".join(messages),
            "written": written,
            "path": files[0]["path"] if files else "",
            "files": files,
        }

    def save_section_text(
        self,
        section_id: str,
        section_text: str,
        target_path: Optional[Path] = None,
        is_new: bool = False,
        peer_ids: Optional[List[str]] = None,
        confirmed: bool = False,
    ) -> dict:
        """
        按键来源拆分写回。
        confirmed=False：只返回 need_confirm + plan，不落盘。
        confirmed=True：执行写入。
        """
        plan = self.plan_section_write(
            section_id, section_text, target_path=target_path, is_new=is_new
        )
        if not plan.get("ok"):
            return plan
        if not (plan.get("files") or []):
            return {"ok": False, "message": "无内容可写"}
        if not confirmed:
            return {
                "ok": False,
                "need_confirm": True,
                "plan": plan,
                "message": plan.get("message") or "需要确认后写入",
            }
        return self.execute_section_write_plan(plan, peer_ids=peer_ids, is_new=is_new)
