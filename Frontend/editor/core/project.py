"""
工程管理
- 合并 / 单文件双模式
- 可编辑文件列表 = 配置主文件 + #include 拆分文件（不扫地图等无关 ini）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Tuple

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
        # classify_sections 结果缓存：key=id(ini)，工程重载或结构变更时清空
        self._classify_cache: Dict[int, Dict[str, List[str]]] = {}

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

    def open_directory(
        self,
        dir_path: str | Path,
        progress: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        打开工程目录。可选 progress(msg) 回调，便于 UI 分步刷新状态栏。
        顺序：rules → art → ai → 登记主文件 → CSF → 注册表索引。
        art/ai/CSF 失败不导致整体失败（仅 rules 或 allowed 为空才返回 False）。
        """
        def report(msg: str) -> None:
            if progress:
                try:
                    progress(msg)
                except Exception:
                    pass

        path = Path(dir_path)
        if not path.is_dir():
            return False

        report("准备工程目录…")
        self.project_dir = path
        self.rules = self.art = self.ai = None
        self.single_ini = None
        self.single_path = None
        self.section_sources = {}
        self.allowed_files = []
        self.type_list_index = {}
        self._classify_cache.clear()
        self.csf = CSFParser()

        # 1) rules（含 #include）— 主路径，必须尽量成功
        rules_names = list(self.profile.get("rules_files", []) or [])
        if rules_names:
            report(f"解析 rules（{rules_names[0]}）…")
        else:
            report("解析 rules…")
        for name in rules_names:
            report(f"解析 rules（{name}）…")
            ini = self._load_merged(name)
            if ini:
                self.rules = ini
                break
        if self.rules is None and rules_names:
            report("未找到可用 rules 文件，继续尝试 art/ai…")

        # 2) art
        art_names = list(self.profile.get("art_files", []) or [])
        if art_names:
            report(f"解析 art（{art_names[0]}）…")
        for name in art_names:
            report(f"解析 art（{name}）…")
            try:
                ini = self._load_merged(name)
                if ini:
                    self.art = ini
                    break
            except Exception:
                continue

        # 3) ai
        ai_names = list(self.profile.get("ai_files", []) or [])
        if ai_names:
            report(f"解析 ai（{ai_names[0]}）…")
        for name in ai_names:
            report(f"解析 ai（{name}）…")
            try:
                ini = self._load_merged(name)
                if ini:
                    self.ai = ini
                    break
            except Exception:
                continue

        # 4) 确保 profile 中的主文件在允许列表
        report("登记工程 ini 列表…")
        for key in ("rules_files", "art_files", "ai_files"):
            for name in self.profile.get(key, []):
                p = path / name
                if p.is_file():
                    self._add_allowed(p)

        # 5) CSF（失败不阻断）
        csf_patterns = self.profile.get("csf_files", []) or []
        report("加载 CSF 字符串表…")
        try:
            self.csf = load_csf_files(csf_patterns, path)
        except Exception:
            self.csf = CSFParser()

        # 6) 注册表 / type list 索引
        report("建立注册表索引…")
        self._rebuild_type_list_index()
        self.work_mode = "merged"

        ok = self.rules is not None or bool(self.allowed_files)
        if ok:
            n_csf = len(getattr(self.csf, "strings", {}) or {})
            report(f"加载完成（CSF {n_csf} 条）")
        else:
            report("加载失败：未找到 rules 或可编辑 ini")
        return ok

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
        self.invalidate_classify_cache()
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

    def invalidate_classify_cache(self) -> None:
        """增删节、改注册表或重载后调用。"""
        self._classify_cache.clear()

    def classify_sections(self, ini: INIFile) -> Dict[str, List[str]]:
        """
        对象树分组：
        1) 各 TypeList 注册表中的 ID（即使本节体暂缺也列出，避免遗漏）
        2) 注册表节本身
        3) 其余节用字段启发式归类
        结果按 id(ini) 缓存；结构变更请 invalidate_classify_cache。
        """
        cache_key = id(ini)
        hit = self._classify_cache.get(cache_key)
        if hit is not None:
            return hit

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
        self._classify_cache[cache_key] = ordered
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

    def get_source_path_for_section(
        self, section_id: str, prefer: str | None = None
    ) -> Optional[Path]:
        """
        解析 section 应写入的磁盘文件。
        prefer: ""/"rules" | "art" | "ai" —— 编辑 Art/AI 标签时必须传入，
        否则同名节会优先命中 rules，把 art 正文误写进 rules（致命）。
        """
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

        pref = (prefer or "").strip().lower()
        if pref == "art":
            path = from_ini(self.art)
            if path:
                return path
            return None
        if pref == "ai":
            path = from_ini(self.ai)
            if path:
                return path
            return None

        # 默认：rules 优先，再 section_sources，最后 art/ai
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
        self.invalidate_classify_cache()

    def get_section_text(self, section_id: str, prefer: Optional[INIFile] = None) -> str:
        sec = self.get_section(section_id, prefer=prefer or self.active_ini())
        if not sec:
            return f"; Section [{section_id}] not found"
        return sec.to_text()

    def analyze_section_origins(
        self, section_id: str, prefer: Optional[INIFile] = None
    ) -> dict:
        """
        B3：同节多文件来源分析。
        返回 {
          section_id, files: [{path, name, order, raw, key_count}],
          keys: [{key, value, source, source_name}],
          multi: bool
        }
        files 按加载顺序（先底后覆盖）；keys 为合并后的键及生效来源。
        """
        from collections import OrderedDict
        from core.save_util import find_section_span, read_text

        ini = prefer or self.active_ini()
        result = {
            "section_id": section_id,
            "files": [],
            "keys": [],
            "multi": False,
        }
        if not ini or not section_id:
            return result

        sid_l = section_id.lower()
        # 候选路径：file_sections + loaded_files + key_sources
        candidates: OrderedDict[str, None] = OrderedDict()
        for src, names in (ini.file_sections or {}).items():
            if any(str(n).lower() == sid_l for n in names):
                candidates[str(src)] = None
        for f in ini.loaded_files or []:
            candidates.setdefault(str(f), None)
        sec = self.get_section(section_id, prefer=ini)
        if sec:
            for k in sec.key_order:
                src = (sec.key_sources or {}).get(k) or sec.source_file or ""
                if src:
                    candidates.setdefault(str(src), None)

        order = 0
        file_rows = []
        for src in candidates:
            path = Path(src)
            if not path.is_file():
                resolved = self._resolve_name(src)
                path = resolved if resolved else path
            if not path or not Path(path).is_file():
                continue
            path = Path(path)
            try:
                text, _enc = read_text(path)
            except Exception:
                continue
            span = find_section_span(text, section_id)
            if not span:
                continue
            raw = text[span[0] : span[1]]
            # 粗算键数
            kc = 0
            for line in raw.splitlines():
                s = line.strip()
                if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                    continue
                if s.startswith("+=") or "=" in s:
                    kc += 1
            try:
                name = (
                    str(path.relative_to(self.project_dir))
                    if self.project_dir
                    else path.name
                )
            except Exception:
                name = path.name
            file_rows.append(
                {
                    "path": str(path.resolve()),
                    "name": name,
                    "order": order,
                    "raw": raw if raw.endswith("\n") else raw + "\n",
                    "key_count": kc,
                }
            )
            order += 1

        # 按 loaded_files 顺序重排（更贴近 Ares 加载）
        load_index = {}
        for i, f in enumerate(ini.loaded_files or []):
            try:
                load_index[str(Path(f).resolve())] = i
            except Exception:
                load_index[str(f)] = i
        file_rows.sort(
            key=lambda r: (load_index.get(r["path"], 10_000 + r["order"]), r["order"])
        )
        for i, r in enumerate(file_rows):
            r["order"] = i

        result["files"] = file_rows
        result["multi"] = len(file_rows) > 1

        if sec:
            for k in sec.key_order:
                val = sec.keys.get(k, "")
                src = (sec.key_sources or {}).get(k) or sec.source_file or ""
                src_path = ""
                src_name = ""
                if src:
                    try:
                        p = Path(src)
                        if not p.is_file():
                            rp = self._resolve_name(src)
                            p = rp if rp else p
                        if p and Path(p).is_file():
                            src_path = str(Path(p).resolve())
                            try:
                                src_name = (
                                    str(Path(p).relative_to(self.project_dir))
                                    if self.project_dir
                                    else Path(p).name
                                )
                            except Exception:
                                src_name = Path(p).name
                        else:
                            src_name = Path(str(src)).name
                    except Exception:
                        src_name = str(src)
                disp_key = "+=" if str(k).startswith("+@") else k
                result["keys"].append(
                    {
                        "key": disp_key,
                        "value": val,
                        "source": src_path,
                        "source_name": src_name,
                    }
                )
        return result

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

    def _build_body_with_patches(
        self,
        section_id: str,
        filepath: str,
        set_map: dict,
        delete_set: set,
        plus_list=None,
        replace_plus: bool = False,
    ) -> str:
        """
        增量写：在磁盘原节上只改 set_map / delete_set；未提及的键保持原样。
        plus_list + replace_plus=True 时替换该文件全部 += 行，否则保留原 +=。
        set_map: lower_key -> (out_key, value, comment)
        """
        raw = self._extract_section_raw_from_file(Path(filepath), section_id)

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
            for ok, val, cmt in set_map.values():
                lines_out.append(fmt_kv(ok, val, cmt))
            if replace_plus and plus_list:
                for val, cmt in plus_list:
                    lines_out.append(fmt_plus(val, cmt))
            return chr(10).join(lines_out)

        out_lines = []
        seen = set()
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
                if replace_plus:
                    continue  # 稍后统一追加
                out_lines.append(line.rstrip())
                continue
            if "=" in s:
                main = s.split(";", 1)[0]
                k = main.partition("=")[0].strip()
                kl = k.lower()
                if kl in delete_set:
                    continue
                if kl in set_map:
                    ok, val, cmt = set_map[kl]
                    seen.add(kl)
                    out_lines.append(fmt_kv(ok, val, cmt))
                    continue
                out_lines.append(line.rstrip())
                continue
            out_lines.append(line.rstrip())

        for kl, (ok, val, cmt) in set_map.items():
            if kl not in seen and kl not in delete_set:
                out_lines.append(fmt_kv(ok, val, cmt))
        if replace_plus and plus_list is not None:
            for val, cmt in plus_list:
                out_lines.append(fmt_plus(val, cmt))
        return chr(10).join(out_lines)

    def _collect_key_origins(
        self,
        section_id: str,
        mem,
        prefer_ini=None,
        orphan_default: str = "",
    ) -> tuple:
        """
        建立 键→来源文件 / +=值→来源文件。
        优先 mem.key_sources；缺的再按加载顺序扫磁盘上各文件中的该节。
        注意：不用 mem.source_file 作为「每个键」的来源（那是最后合并文件，会把整表写进一个文件）。
        orphan_default 仅用于完全找不到来源的新键。
        """
        origin_by_key: dict = {}
        origin_by_plus_val: dict = {}

        if mem:
            for k in mem.key_order:
                src = (mem.key_sources or {}).get(k) or ""
                if not src:
                    continue
                src = self._resolve_key_origin(src)
                if not src:
                    continue
                if str(k).startswith("+@"):
                    val = (mem.keys.get(k) or "").strip().lower()
                    if val:
                        origin_by_plus_val[val] = src
                else:
                    origin_by_key[str(k).lower()] = src

        # 磁盘补全：按加载顺序，后加载覆盖先加载（与 Ares 合并一致）
        ini = prefer_ini or self.active_ini()
        paths: list = []
        if ini:
            for src, names in (ini.file_sections or {}).items():
                if any(str(n).lower() == section_id.lower() for n in names):
                    paths.append(str(src))
            for f in ini.loaded_files or []:
                s = str(f)
                if s not in paths:
                    # 仍扫描：有的文件有节但 file_sections 未登记
                    paths.append(s)
        # 注册表索引
        try:
            for p in self.files_with_type_list(section_id) or []:
                s = str(Path(p).resolve()) if Path(p).is_file() else str(p)
                if s not in paths:
                    paths.append(s)
        except Exception:
            pass

        for src in paths:
            path = Path(src)
            if not path.is_file():
                rp = self._resolve_name(src)
                path = rp if rp else path
            if not path or not Path(path).is_file():
                continue
            raw = self._extract_section_raw_from_file(Path(path), section_id)
            if not raw.strip():
                continue
            resolved = self._resolve_key_origin(str(path))
            for item in self._parse_section_kv_lines(section_id, raw):
                k, v, _c = item[0], item[1], item[2] if len(item) > 2 else ""
                if k in ("+", "+=", "++"):
                    vl = (v or "").strip().lower()
                    if vl:
                        origin_by_plus_val[vl] = resolved  # 后写覆盖
                else:
                    origin_by_key[str(k).lower()] = resolved

        return origin_by_key, origin_by_plus_val, orphan_default

    def plan_section_write(
        self,
        section_id: str,
        section_text: str,
        target_path: Optional[Path] = None,
        is_new: bool = False,
        prefer: str | None = None,
        write_mode: str | None = None,
        baseline_text: str | None = None,
        new_key_default: Optional[Path] = None,
        baseline_keys: Optional[set] = None,
        baseline_plus: Optional[set] = None,
    ) -> dict:
        """
        按键来源生成多文件写入计划（不落盘）。
        write_mode: full（默认）| incremental（仅脏键）。
        new_key_default: 无来源的新键写入文件（合并节下拉）；不影响已有键来源。
        baseline_keys / baseline_plus: 打开节时锁定的普通键与 += 值。
        """
        pref = (prefer or "").strip().lower()
        prefer_ini = None
        if pref == "art":
            prefer_ini = self.art
        elif pref == "ai":
            prefer_ini = self.ai

        if self.work_mode == "single" and self.single_path:
            path = self.single_path
        else:
            path = (
                Path(target_path)
                if target_path
                else self.get_source_path_for_section(section_id, prefer=pref or None)
            )
        # 无来源新键的默认文件：优先下拉选择，否则 target/解析路径
        orphan = None
        if new_key_default is not None:
            orphan = Path(new_key_default)
        elif path is not None:
            orphan = Path(path)
        if path is None and orphan is None:
            return {"ok": False, "need_path": True, "message": "无法确定默认写入文件", "files": []}
        if path is None:
            path = orphan

        default = self._resolve_key_origin(str(orphan or path))
        mem = self.get_section(section_id, prefer=prefer_ini)
        parsed = self._parse_section_kv_lines(section_id, section_text)

        origin_by_key, origin_by_plus_val, _ = self._collect_key_origins(
            section_id, mem, prefer_ini=prefer_ini, orphan_default=default
        )

        mode = (write_mode or "").strip().lower()
        if not mode:
            try:
                mode = str((self.config.get("settings") or {}).get("save_write_mode") or "full").lower()
            except Exception:
                mode = "full"

        # 类型注册表（InfantryTypes 等）强制全量：多文件 + 序号键 + +=，增量极易漏删漏增
        sid_l = (section_id or "").strip().lower()
        type_list_names = {n.lower() for n in DEFAULT_TYPE_LISTS}
        try:
            type_list_names |= {
                str(n).lower()
                for n in (self.profile.get("type_lists") or [])
            }
        except Exception:
            pass
        if sid_l in type_list_names:
            mode = "full"

        if mode in ("incremental", "delta", "patch") and not is_new:
            inc = self._plan_section_write_incremental(
                section_id,
                section_text,
                parsed,
                mem,
                default,
                baseline_text,
                origin_by_key=origin_by_key,
                origin_by_plus_val=origin_by_plus_val,
                baseline_keys=baseline_keys,
                baseline_plus=baseline_plus,
            )
            # 正文相对基线有变化，但增量引擎没找出键 → 回退全量
            if not any(
                not f.get("skip") and (
                    int(f.get("count") or 0) > 0 or f.get("deletes") or f.get("incremental")
                )
                for f in (inc.get("files") or [])
            ):
                def _norm_txt(t: str) -> str:
                    lines = []
                    for ln in (t or "").splitlines():
                        s = ln.strip()
                        if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                            continue
                        lines.append(s.lower().replace(" ", ""))
                    return "\n".join(lines)

                if baseline_text and _norm_txt(baseline_text) != _norm_txt(section_text):
                    pass  # 回退全量
                else:
                    return inc
            else:
                return inc

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

        # 曾经出现过键的文件也要进计划（用于删除键时从该文件去掉）
        for src in set(origin_by_key.values()) | set(origin_by_plus_val.values()):
            if src and src not in groups:
                groups[src] = []

        cur_keys_l = set()
        for item in parsed:
            k = item[0]
            if k not in ("+", "+=", "++"):
                cur_keys_l.add(str(k).lower())

        files = []
        skipped_empty = []
        for fpath, kvs in groups.items():
            if not fpath:
                continue
            body = self._build_body_preserving_comments(section_id, fpath, kvs)
            item = {
                "path": fpath,
                "body": body,
                "count": len(kvs),
                "keys": [a for a, _, _ in kvs],
            }
            # 该文件原先有、现在正文里没有的键 → 必须写回以完成删除
            disk_only = [
                kl for kl, src in origin_by_key.items()
                if src == fpath and kl not in cur_keys_l
            ]
            if len(kvs) == 0 and not disk_only:
                item["skip"] = True
                item["skip_reason"] = "无待写键且无删除，保留原内容"
                skipped_empty.append(fpath)
            elif disk_only:
                item["deletes"] = disk_only
                item["count"] = max(len(kvs), len(disk_only))
            files.append(item)
        files.sort(key=lambda x: x["path"].lower())
        msg = "计划写入 %d 个文件（全量）" % sum(1 for f in files if not f.get("skip"))
        if skipped_empty:
            msg += "；%d 个文件无变更已跳过" % len(skipped_empty)
        return {
            "ok": True,
            "files": files,
            "default_path": default,
            "section_id": section_id,
            "message": msg,
            "skipped_empty": skipped_empty,
            "write_mode": "full",
        }

    def _plan_section_write_incremental(
        self,
        section_id: str,
        section_text: str,
        parsed: list,
        mem,
        default: str,
        baseline_text: str | None,
        origin_by_key: dict | None = None,
        origin_by_plus_val: dict | None = None,
        baseline_keys: Optional[set] = None,
        baseline_plus: Optional[set] = None,
    ) -> dict:
        """
        增量写回计划。
        删除：打开时键集合 baseline_keys（或基线正文/磁盘来源）有、当前没有。
        += ：打开时 baseline_plus 与当前 += 值集合比较。
        修改/新增：相对基线正文的值变化。
        """
        origin_by_key = dict(origin_by_key or {})
        origin_by_plus_val = dict(origin_by_plus_val or {})

        def load_maps(text_or_parsed, is_parsed=False):
            normal, plus = {}, []
            items = text_or_parsed if is_parsed else self._parse_section_kv_lines(
                section_id, text_or_parsed or ""
            )
            for item in items:
                k, v, cmt = item[0], item[1], item[2] if len(item) > 2 else ""
                if k in ("+", "+=", "++"):
                    plus.append(((v or "").strip(), cmt or ""))
                else:
                    normal[str(k).lower()] = (k, v or "", cmt or "")
            return normal, plus

        cur_normal, cur_plus = load_maps(parsed, is_parsed=True)

        if baseline_text:
            base_normal, base_plus = load_maps(baseline_text)
        elif mem:
            base_normal, base_plus = {}, []
            for k in mem.key_order:
                if str(k).startswith("+@"):
                    base_plus.append(
                        ((mem.keys.get(k) or "").strip(), (mem.inline_comments or {}).get(k, ""))
                    )
                else:
                    base_normal[str(k).lower()] = (
                        k,
                        mem.keys.get(k) or "",
                        (mem.inline_comments or {}).get(k, ""),
                    )
        else:
            base_normal, base_plus = {}, []

        # 打开时锁定的键名：删除检测的主依据
        locked = set()
        if baseline_keys:
            locked = {str(x).lower() for x in baseline_keys}
        else:
            locked = set(base_normal.keys()) | set(origin_by_key.keys())

        def origin_of(kl: str, val_for_plus: str = "") -> str:
            if val_for_plus:
                return origin_by_plus_val.get(val_for_plus.lower()) or default
            return origin_by_key.get(kl) or default

        dirty_set: dict = {}
        dirty_del: dict = {}

        # 删除：打开时有的键，现在正文里没了
        for kl in locked:
            if kl in cur_normal:
                continue
            src = origin_of(kl) or default
            dirty_del.setdefault(src, set()).add(kl)

        # 新增 / 修改
        for kl, cv in cur_normal.items():
            bv = base_normal.get(kl)
            src = origin_of(kl) or default
            if bv is None:
                if kl not in locked:
                    dirty_set.setdefault(src, {})[kl] = cv
            elif cv[1] != bv[1] or (cv[2] or "") != (bv[2] or ""):
                dirty_set.setdefault(src, {})[kl] = cv

        # += 列表：锁定集合 + 基线正文 + 磁盘来源
        cur_plus_set = {v.lower() for v, _ in cur_plus if v}
        base_plus_set = {v.lower() for v, _ in base_plus if v}
        if baseline_plus:
            base_plus_set |= {str(x).lower() for x in baseline_plus}
        base_plus_set |= set(origin_by_plus_val.keys())
        plus_changed = cur_plus_set != base_plus_set
        plus_by_file: dict = {}
        if plus_changed:
            # 当前有的 += 全部按来源写回（无来源 → default / 下拉）
            for v, c in cur_plus:
                if not v:
                    continue
                src = origin_of("", v) or default
                plus_by_file.setdefault(src, []).append((v, c))
            # 打开时有、现在没有的 +=：确保对应文件进入计划（replace_plus 时用当前列表）
            for vlow in base_plus_set:
                if vlow in cur_plus_set:
                    continue
                src = origin_by_plus_val.get(vlow) or default
                plus_by_file.setdefault(src, plus_by_file.get(src, []))

        paths = set(dirty_set) | set(dirty_del) | set(plus_by_file)
        files = []
        if not paths:
            return {
                "ok": True,
                "files": [],
                "default_path": default,
                "section_id": section_id,
                "message": "增量：未检测到键新增/修改/删除，无需写入",
                "write_mode": "incremental",
            }

        for fpath in sorted(p for p in paths if p):
            sm = dirty_set.get(fpath) or {}
            ds = dirty_del.get(fpath) or set()
            pl = plus_by_file.get(fpath) if plus_changed else None
            n = len(sm) + len(ds) + (len(pl) if pl else 0)
            if n == 0:
                continue
            body = self._build_body_with_patches(
                section_id,
                fpath,
                sm,
                ds,
                plus_list=pl if pl is not None else None,
                replace_plus=(pl is not None),
            )
            plus_keys = [f"+={v}" for v, _ in (pl or [])]
            files.append({
                "path": fpath,
                "body": body,
                "count": n,
                "keys": list(sm.keys()) + [f"-{k}" for k in ds] + plus_keys,
                "deletes": list(ds),
                "incremental": True,
            })
        files.sort(key=lambda x: x["path"].lower())
        if not files:
            return {
                "ok": True,
                "files": [],
                "default_path": default,
                "section_id": section_id,
                "message": "增量：未检测到键新增/修改/删除，无需写入",
                "write_mode": "incremental",
            }
        n_del = sum(len(f.get("deletes") or []) for f in files)
        n_set = sum(len([k for k in (f.get("keys") or []) if not str(k).startswith("-")]) for f in files)
        return {
            "ok": True,
            "files": files,
            "default_path": default,
            "section_id": section_id,
            "message": "增量：%d 个文件（改/增 %d 键，删 %d 键）" % (len(files), n_set, n_del),
            "write_mode": "incremental",
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
        proj = self.project_dir.resolve() if self.project_dir else None

        for item in files:
            path = Path(item["path"])
            body = item["body"]
            count = int(item.get("count") or 0)
            # 仅明确 skip 才跳过；count==0 但带 deletes 的也要写（删键）
            if item.get("skip"):
                messages.append(f"跳过 {path.name}（无待写键，保留原内容）")
                written.append({"path": str(path), "ok": True, "msg": "skipped", "skipped": True})
                continue
            if count == 0 and not item.get("deletes") and not item.get("incremental"):
                messages.append(f"跳过 {path.name}（无变更）")
                written.append({"path": str(path), "ok": True, "msg": "skipped", "skipped": True})
                continue
            # 工程模式下拒绝写到工程目录外，防止选错盘符文件
            if proj is not None:
                try:
                    path.resolve().relative_to(proj)
                except Exception:
                    return {
                        "ok": False,
                        "message": f"拒绝写入工程目录外的文件:\n{path}",
                        "written": written,
                        "path": str(path),
                    }
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

        # 内存合并：已写入文件的键 + 跳过文件中仍保留的旧键（避免误丢拆分来源）
        new_sec = INISection(section_id)
        skipped_paths = {
            str(Path(i["path"]).resolve())
            for i in files
            if i.get("skip")
        }
        old_sec = self.get_section(section_id)
        if old_sec and skipped_paths:
            for k in old_sec.key_order:
                src = (old_sec.key_sources or {}).get(k) or old_sec.source_file or ""
                try:
                    rs = str(Path(src).resolve()) if src else ""
                except Exception:
                    rs = str(src)
                if rs in skipped_paths:
                    val = old_sec.keys.get(k, "")
                    cmt = (old_sec.inline_comments or {}).get(k, "")
                    if str(k).startswith("+@"):
                        new_sec.set("+", val, cmt, source_file=src)
                    else:
                        new_sec.set(k, val, cmt, source_file=src)

        for item in files:
            if item.get("skip"):
                continue
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

        written_files = [
            f for f in files
            if not f.get("skip") and (
                int(f.get("count") or 0) > 0 or f.get("deletes") or f.get("incremental")
            )
        ]
        if section_id and written_files:
            try:
                self.section_sources[section_id.lower()] = str(
                    Path(written_files[0]["path"]).resolve()
                )
            except Exception:
                pass

        return {
            "ok": True,
            "message": "；".join(messages),
            "written": written,
            "path": written_files[0]["path"] if written_files else "",
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
        prefer: str | None = None,
        write_mode: str | None = None,
        baseline_text: str | None = None,
        new_key_default: Optional[Path] = None,
        baseline_keys: Optional[set] = None,
        baseline_plus: Optional[set] = None,
    ) -> dict:
        """
        按键来源拆分写回。
        confirmed=False：只返回 need_confirm + plan，不落盘。
        confirmed=True：执行写入。
        prefer: art/ai 时避免写回 rules。
        write_mode / baseline_text / baseline_keys / baseline_plus: 增量保存时使用。
        new_key_default: 无来源新键的目标文件。
        """
        plan = self.plan_section_write(
            section_id,
            section_text,
            target_path=target_path,
            is_new=is_new,
            prefer=prefer,
            write_mode=write_mode,
            baseline_text=baseline_text,
            new_key_default=new_key_default,
            baseline_keys=baseline_keys,
            baseline_plus=baseline_plus,
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
