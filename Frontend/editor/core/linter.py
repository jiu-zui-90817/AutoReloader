"""
轻量 INI 校验（Ares 基线，尽量完整）。

热重载 / 工程编辑默认存在 Ares。规则侧重「引用是否解析得到」，
未知扩展键默认不报，避免误杀 Phobos 等后续扩展。
校验作用域：rules 只查 rules；art/ai 可回退到 rules（弹头/武器等在 rules）。
rules↔art 同名单位不报「多源冲突」。

前置组：
  [General] PrerequisiteXxx= / PrerequisiteXxxAlternate=
  [GenericPrerequisites] 自定义别名（可覆盖 General 同名）

引用类（注册表 + 启发式分类）：
  武器 / 弹头 / 抛射体 / 单位建筑 / 超武 / 动画 / 粒子 等

保存时：仅 error 会打断（可仍保存）；warning/info 不打断。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .ini_parser import INISection
from .project_index import iter_sections, known_ids

# ---------------------------------------------------------------------------
# 键 → 期望类型（键名一律小写匹配；支持前缀规则见 _expect_for_key）
# ---------------------------------------------------------------------------

REF_KEYS_WEAPON: Set[str] = {
    "primary", "secondary", "eliteprimary", "elitesecondary",
    "occupyweapon", "eliteoccupyweapon", "deathweapon", "deathtooltip",
    "opentopped.weapon", "drainweapon", "mindcontrol.permanentweapon",
    "weapon1", "weapon2", "weapon3", "weapon4", "weapon5",
    "weapon6", "weapon7", "weapon8", "weapon9", "weapon10",
    "eliteweapon1", "eliteweapon2", "eliteweapon3", "eliteweapon4", "eliteweapon5",
}
# 键名正则式前缀：weapon5 已在集合；WeaponX.xxx 不解析为武器 ID

REF_KEYS_WARHEAD: Set[str] = {
    "warhead", "animwarhead", "deathwarhead", "crush.warhead",
    "electricdeathwarhead",
}

REF_KEYS_PROJECTILE: Set[str] = {
    "projectile",
}

REF_KEYS_UNIT: Set[str] = {
    # 多数前置走专用逻辑；这里是明确指向 Techno 的键
    "gunner.ifvweapon",  # 少见
}

REF_KEYS_SUPERWEAPON: Set[str] = {
    "superweapon", "superweapon2", "superweapon3", "superweapon4",
    "sw", "supershort",
}

REF_KEYS_ANIM: Set[str] = {
    "anim", "idleanim", "auxanims", "secondaryidleanim",
    "deployanim", "underwateranim", "fallinganim",
    "damageanims", "destroyanim", "dieanims",
    "trailer", "traileranim", "weaponbaranim",
    "moveanim", "specialanim", "specialanimtwo", "specialanimthree", "specialanimfour",
}

REF_KEYS_PARTICLE: Set[str] = {
    "attachedparticle", "damagedparticle", "damagedparticlesystem",
}

REF_KEYS_HOUSE: Set[str] = {
    "owner", "requiredhouses", "forbiddenhouses", "factoryowners",
}

PREREQ_ALLOWLIST = {
    "none", "no", "<none>", "0", "", "n/a",
    "all", "any", "default", "yes", "true", "false",
}

PREREQ_NON_BUILDING_SUFFIXES = {
    "requiredtheaters", "display", "list", "groups", "lists",
}

TECHLEVEL_MIN, TECHLEVEL_MAX = -1, 15

GENERIC_PREREQ_SECTION = "genericprerequisites"
GENERAL_SECTION = "general"
GENERAL_PREREQ_PREFIX = "prerequisite"

TYPE_LIST_MAP = {
    "WeaponTypes": "weapon",
    "Warheads": "warhead",
    "ProjectileTypes": "projectile",
    "Projectiles": "projectile",
    "InfantryTypes": "unit",
    "VehicleTypes": "unit",
    "AircraftTypes": "unit",
    "BuildingTypes": "unit",
    "TerrainTypes": "unit",
    "OverlayTypes": "unit",
    "SuperWeaponTypes": "superweapon",
    "Animations": "animation",
    "Particles": "particle",
    "ParticleSystems": "particlesystem",
    "VoxelAnims": "animation",
    "AttachEffectTypes": "attacheffect",
}

# 期望类型的中文名（报错用）
EXPECT_REGISTRY = {
    "weapon": "WeaponTypes",
    "warhead": "Warheads",
    "projectile": "ProjectileTypes/Projectiles",
    "unit": "Infantry/Vehicle/Aircraft/BuildingTypes",
    "superweapon": "SuperWeaponTypes",
    "animation": "Animations",
    "particle": "Particles",
    "particlesystem": "ParticleSystems",
    "attacheffect": "AttachEffectTypes",
}

EXPECT_LABEL = {
    "weapon": "武器",
    "warhead": "弹头",
    "projectile": "抛射体",
    "unit": "单位/建筑",
    "superweapon": "超级武器",
    "animation": "动画",
    "particle": "粒子",
    "particlesystem": "粒子系统",
    "attacheffect": "AttachEffect",
}


@dataclass
class LintIssue:
    severity: str
    section_id: str
    key: str
    message: str
    source: str = ""

    def label(self) -> str:
        loc = f"[{self.section_id}]"
        if self.key:
            loc += f".{self.key}"
        src = f" ({self.source})" if self.source else ""
        return f"[{self.severity}] {loc}{src}: {self.message}"


@dataclass
class TypeSets:
    weapon: Set[str] = field(default_factory=set)
    warhead: Set[str] = field(default_factory=set)
    projectile: Set[str] = field(default_factory=set)
    unit: Set[str] = field(default_factory=set)
    superweapon: Set[str] = field(default_factory=set)
    animation: Set[str] = field(default_factory=set)
    particle: Set[str] = field(default_factory=set)
    particlesystem: Set[str] = field(default_factory=set)
    attacheffect: Set[str] = field(default_factory=set)
    any: Set[str] = field(default_factory=set)
    generic_prereq: Dict[str, List[str]] = field(default_factory=dict)


def _split_list(val: str) -> List[str]:
    return [p.strip() for p in val.replace(";", ",").split(",") if p.strip()]


def _known_ids_scoped(project, sources: Optional[Set[str]] = None) -> Dict[str, Set[str]]:
    m: Dict[str, Set[str]] = {}
    for src, name, _sec in iter_sections(project):
        if sources is not None and src not in sources:
            continue
        m.setdefault(name.lower(), set()).add(src)
    return m


def _scope_for_source(source: str) -> Set[str]:
    """节所属源 → 参与校验的 ini 族。

    - rules：只看 rules（逻辑与注册表所在）
    - art：art + rules（IdleAnim 等仍可单独跳过；Warhead/武器等在 rules）
    - ai：ai + rules
    - 不在 art 里找弹头、不在 rules 里用 art 顶逻辑注册
    """
    s = (source or "rules").lower()
    if s == "single":
        return {"single", "rules", "art", "ai"}
    if s == "rules":
        return {"rules"}
    if s == "art":
        return {"art", "rules"}
    if s == "ai":
        return {"ai", "rules"}
    return {s}


def _is_prereq_key(kl: str) -> bool:
    return kl == "prerequisite" or kl.startswith("prerequisite")


def _prereq_value_is_building_list(kl: str) -> bool:
    if kl in ("prerequisite", "prerequisiteoverride", "prerequisitenegative"):
        return True
    if not kl.startswith("prerequisite."):
        return False
    suffix = kl.split(".", 1)[1]
    if suffix in PREREQ_NON_BUILDING_SUFFIXES:
        return False
    # Prerequisite.List1 / List2 … Ares 多前置列表
    if suffix.startswith("list") and suffix[4:].isdigit():
        return True
    if suffix in ("negative", "override"):
        return True
    return False


def _expect_for_key(kl: str) -> Optional[str]:
    """返回期望类型名，或 None 表示不校验该键。"""
    if kl in REF_KEYS_WEAPON:
        return "weapon"
    if kl in REF_KEYS_WARHEAD:
        return "warhead"
    if kl in REF_KEYS_PROJECTILE:
        return "projectile"
    if kl in REF_KEYS_SUPERWEAPON:
        return "superweapon"
    if kl in REF_KEYS_ANIM:
        return "animation"
    if kl in REF_KEYS_PARTICLE:
        return "particle"
    if kl in REF_KEYS_HOUSE:
        return "house"

    # Ares / 常见点号扩展
    if kl.startswith("attacheffect.") and (
        kl.endswith(".types") or kl.endswith(".type") or kl == "attacheffect.types"
    ):
        return "attacheffect"
    if kl in ("attacheffect", "attacheffect.types"):
        return "attacheffect"

    if kl.startswith("sw.") and kl.endswith("warhead"):
        return "warhead"
    # SW.Animation / SW.Anim 才是动画引用；Visibility 等是枚举
    if kl.startswith("sw.") and ("anim" in kl) and "visibility" not in kl and "sound" not in kl:
        if kl.endswith("anim") or ".anim" in kl or kl.endswith("animation") or ".animation" in kl:
            return "animation"

    # DeathWeapon 已在集合；EliteOccupyWeapon 等同
    if kl.endswith("weapon") and not kl.startswith("weapon."):
        # 避免把 UseWeapon=yes 之类布尔算进去：值侧再过滤
        if kl in ("useweapon", "isweapon", "weaponstage", "weaponcount"):
            return None
        if "range" in kl or "sound" in kl or "flash" in kl:
            return None
        return "weapon"

    if kl.endswith("warhead") or ".warhead" in kl:
        return "warhead"

    return None


def _register_prereq_alias(sets: TypeSets, alias: str, targets: List[str]) -> None:
    alias = alias.strip().lower()
    if not alias:
        return
    incoming = [t.lower() for t in targets if t]
    prev = sets.generic_prereq.get(alias, [])
    merged: List[str] = []
    for x in prev + incoming:
        if x not in merged:
            merged.append(x)
    sets.generic_prereq[alias] = merged
    sets.any.add(alias)


def _ingest_general_prereq_aliases(sets: TypeSets, sec: INISection) -> None:
    for k, v in sec.keys.items():
        kl = str(k).strip().lower()
        if not kl.startswith(GENERAL_PREREQ_PREFIX):
            continue
        rest = kl[len(GENERAL_PREREQ_PREFIX) :]
        if not rest:
            continue
        targets = _split_list(str(v))
        if rest.endswith("alternate"):
            base = rest[: -len("alternate")]
            if not base:
                continue
            existing = sets.generic_prereq.get(base, [])
            _register_prereq_alias(sets, base, existing + targets)
            continue
        _register_prereq_alias(sets, rest, targets)


def _build_type_sets(project, sources: Optional[Set[str]] = None) -> TypeSets:
    """sources 为 None 表示全部；否则只扫给定源（rules/art/ai/single）。"""
    sets = TypeSets()

    for _src, name, sec in iter_sections(project):
        if sources is not None and _src not in sources:
            continue
        nl = name.lower()
        sets.any.add(nl)

        if nl == GENERIC_PREREQ_SECTION:
            for k, v in sec.keys.items():
                alias = str(k).strip().lower()
                if not alias or alias.startswith(";"):
                    continue
                sets.generic_prereq[alias] = [x.lower() for x in _split_list(str(v))]
                sets.any.add(alias)
            continue

        if nl == GENERAL_SECTION:
            _ingest_general_prereq_aliases(sets, sec)
            continue

        kind = None
        for list_name, knd in TYPE_LIST_MAP.items():
            if nl == list_name.lower():
                kind = knd
                bucket: Set[str] = getattr(sets, knd)
                for _k, v in sec.keys.items():
                    v = str(v).strip()
                    if v:
                        vl = v.lower()
                        bucket.add(vl)
                        sets.any.add(vl)
                break

        if kind is None:
            keys_l = {k.lower() for k in sec.keys}
            # 启发式：未进注册表也能被引用到的节
            if "damage" in keys_l and (
                "spread" in keys_l
                or "cellspread" in keys_l
                or "percentatmax" in keys_l
                or "verses" in keys_l
                or "animlist" in keys_l
            ):
                sets.warhead.add(nl)
            elif "range" in keys_l and ("projectile" in keys_l or "warhead" in keys_l or "rof" in keys_l):
                sets.weapon.add(nl)
            elif "type" in keys_l and str(sec.keys.get("Type", sec.keys.get("type", ""))).lower().startswith("swtype"):
                sets.superweapon.add(nl)
            elif "strength" in keys_l:
                sets.unit.add(nl)
            elif "loopcount" in keys_l or "report" in keys_l and "rate" in keys_l:
                # 弱：动画特征不稳定，仅作 any 已足够
                pass

    for builtin in ("power", "factory", "barracks", "radar", "tech", "proc"):
        sets.generic_prereq.setdefault(builtin, [])
        sets.any.add(builtin)

    return sets


def _pool(sets: TypeSets, expect: str) -> Set[str]:
    if expect == "particle":
        return sets.particle | sets.particlesystem
    return getattr(sets, expect, sets.any)


def _check_prereq_token(
    token: str,
    sets: TypeSets,
    id_index: Dict[str, Set[str]],
    section_id: str,
    key: str,
    source: str,
) -> List[LintIssue]:
    issues: List[LintIssue] = []
    pl = token.lower()
    if pl in PREREQ_ALLOWLIST or pl.isdigit():
        return issues

    if pl in sets.generic_prereq:
        targets = sets.generic_prereq[pl]
        missing = [
            t
            for t in targets
            if t not in sets.unit and t not in id_index and t not in sets.any
        ]
        if missing:
            issues.append(
                LintIssue(
                    "warning",
                    section_id,
                    key,
                    f"前置组 {token!r} 已注册，但展开项未找到: {', '.join(missing[:8])}"
                    + ("…" if len(missing) > 8 else ""),
                    source,
                )
            )
        return issues

    if pl in sets.unit or pl in id_index or pl in sets.any:
        return issues

    looks_like_group = token.isupper() or (token.isalnum() and token == token.upper())
    issues.append(
        LintIssue(
            "warning" if looks_like_group else "error",
            section_id,
            key,
            f"前置 {token!r} 未在单位/建筑、[General] Prerequisite* 或 [GenericPrerequisites] 中解析到"
            + ("（若为自定义组，请写入 [GenericPrerequisites]）" if looks_like_group else ""),
            source,
        )
    )
    return issues


def _check_ref_token(
    token: str,
    expect: str,
    sets: TypeSets,
    id_index: Dict[str, Set[str]],
    section_id: str,
    key: str,
    source: str,
) -> List[LintIssue]:
    issues: List[LintIssue] = []
    pl = token.lower()
    if pl in PREREQ_ALLOWLIST:
        return issues
    # 布尔 / 数字误写
    if pl in ("yes", "no", "true", "false") or (pl.isdigit() and expect != "unit"):
        return issues

    if expect == "house":
        if pl not in id_index and pl not in sets.any:
            issues.append(
                LintIssue(
                    "info",
                    section_id,
                    key,
                    f"未在工程中找到国家/方 {token!r}（可能是引擎内置）",
                    source,
                )
            )
        return issues

    pool = _pool(sets, expect)
    label = EXPECT_LABEL.get(expect, expect)
    reg = EXPECT_REGISTRY.get(expect, expect)

    # 1) 在注册表或启发式分类中 → 通过
    if pl in pool:
        return issues

    # 2) 有同名节，但既不在对应注册表、也未被启发式判为该类型
    if pl in id_index or pl in sets.any:
        issues.append(
            LintIssue(
                "warning",
                section_id,
                key,
                f"{token!r} 不是{label}类型，或未在 {reg} 注册表注册",
                source,
            )
        )
        return issues

    # 3) 完全找不到
    sev = "warning" if expect in ("animation", "particle", "particlesystem", "attacheffect") else "error"
    issues.append(
        LintIssue(
            sev,
            section_id,
            key,
            f"引用的{label} {token!r} 在工程中未找到",
            source,
        )
    )
    return issues


def lint_section(
    project,
    section_id: str,
    sec: Optional[INISection],
    source: str = "",
    type_sets: Optional[TypeSets] = None,
    id_index: Optional[Dict[str, Set[str]]] = None,
) -> List[LintIssue]:
    if not sec:
        return [LintIssue("warning", section_id, "", "节不存在或无法解析", source)]

    scope = _scope_for_source(source)
    sets = type_sets or _build_type_sets(project, sources=scope)
    id_index = id_index or _known_ids_scoped(project, sources=scope)
    issues: List[LintIssue] = []

    for k, v in sec.keys.items():
        if k.lower() == "owner" and not str(v).strip():
            issues.append(LintIssue("warning", section_id, k, "Owner 为空", source))

    for k, v in sec.keys.items():
        if k.lower() != "techlevel":
            continue
        s = str(v).strip()
        if not s:
            issues.append(LintIssue("warning", section_id, k, "TechLevel 为空", source))
            continue
        try:
            n = int(s)
            if n < TECHLEVEL_MIN or n > TECHLEVEL_MAX:
                issues.append(
                    LintIssue(
                        "info",
                        section_id,
                        k,
                        f"TechLevel={n} 超出常见范围 [{TECHLEVEL_MIN},{TECHLEVEL_MAX}]（MOD 可忽略）",
                        source,
                    )
                )
        except ValueError:
            issues.append(LintIssue("error", section_id, k, f"TechLevel 不是整数: {s!r}", source))

    for k, v in sec.keys.items():
        kl = k.lower()
        raw = str(v).strip()
        if not raw:
            continue

        if _is_prereq_key(kl):
            if not _prereq_value_is_building_list(kl):
                continue
            for p in _split_list(raw):
                issues.extend(
                    _check_prereq_token(p, sets, id_index, section_id, k, source)
                )
            continue

        expect = _expect_for_key(kl)
        if expect is None:
            continue

        # art 中 IdleAnim / SpecialAnim / Trailer 等大量指向 SHP 序列名，
        # 通常不在 [Animations] 注册，也不单独成节 → 不做动画/粒子引用校验
        src_l = (source or "").lower()
        if src_l == "art" and expect in (
            "animation", "particle", "particlesystem",
        ):
            continue

        parts = _split_list(raw) if ("," in raw or ";" in raw or expect == "house") else [raw]
        for p in parts:
            issues.extend(
                _check_ref_token(p, expect, sets, id_index, section_id, k, source)
            )

    return issues



# 不做「废弃」提示的节名（全局表 / 注册表本身）
_DEAD_SKIP_NAMES = {
    "general", "combatdamage", "combattamage", "audiovisual", "specialweapons",
    "jumpjetcontrols", "ai", "iq", "rocketdata", "crate", "powerups", "powersups",
    "radiation", "easy", "normal", "difficult", "multiplayerdialogsettings",
    "genericprerequisites", "basic", "map", "digest",
} | {n.lower() for n in TYPE_LIST_MAP.keys()}


def _collect_value_references(project, sources: Optional[Set[str]] = None) -> Set[str]:
    """收集「使用向」引用：普通节的键值 token。
    不含类型注册表（WeaponTypes/Warheads…）里的登记项，登记≠被使用。
    """
    refs: Set[str] = set()
    skip_sections = {n.lower() for n in TYPE_LIST_MAP.keys()} | {
        "genericprerequisites", "countries", "sides", "colors",
    }
    for src, name, sec in iter_sections(project):
        if sources is not None and src not in sources:
            continue
        if name.lower() in skip_sections:
            continue
        for _k, v in sec.keys.items():
            raw = str(v).strip()
            if not raw:
                continue
            for part in _split_list(raw):
                pl = part.lower()
                if pl and pl not in PREREQ_ALLOWLIST and not pl.isdigit():
                    refs.add(pl)
    return refs


def _lint_unused_sections(project, limit_left: int) -> List[LintIssue]:
    """
    可能废弃：在 rules 中有节（或仅在注册表出现），但全工程没有任何键值引用到该 ID。
    仅 info；地图/CSF/AI 未加载时会有误报，属提示性质。
    """
    if limit_left <= 0:
        return []
    # 引用跨 rules/art/ai 统计；候选主要来自 rules（逻辑对象）
    refs = _collect_value_references(project, sources=None)
    issues: List[LintIssue] = []

    # 注册表中的 ID（即使无节体）
    rules_sets = _build_type_sets(project, sources={"rules"})
    registered: Set[str] = set()
    for bucket in (
        rules_sets.weapon, rules_sets.warhead, rules_sets.projectile,
        rules_sets.unit, rules_sets.superweapon, rules_sets.animation,
        rules_sets.attacheffect,
    ):
        registered |= bucket

    candidates: Dict[str, str] = {}  # lower -> display name
    for src, name, sec in iter_sections(project):
        if src != "rules":
            continue
        nl = name.lower()
        if nl in _DEAD_SKIP_NAMES or name.startswith("#"):
            continue
        if not sec.keys and nl not in registered:
            continue
        candidates[nl] = name

    for rid in registered:
        if rid not in candidates and rid not in _DEAD_SKIP_NAMES:
            candidates[rid] = rid

    for nl, display in sorted(candidates.items(), key=lambda x: x[0]):
        if nl in refs:
            continue
        # 自己的节名不会出现在自己的值里时仍算未引用
        in_reg = nl in registered
        tip = "已在类型注册表中，但" if in_reg else "未在类型注册表中，且"
        issues.append(
            LintIssue(
                "info",
                display,
                "",
                f"{tip}工程内无其它代码引用，可能是废弃代码",
                "rules",
            )
        )
        if len(issues) >= limit_left:
            break
    return issues


def _resolve_scope_for_kind(kind: str) -> Set[str]:
    """注册条目对应的节体通常在哪一类 ini。"""
    # 动画/粒子/体素动画：多在 art；逻辑单位/武器：在 rules
    if kind in ("animation", "particle", "particlesystem"):
        return {"art", "rules"}
    if kind in ("weapon", "warhead", "projectile", "unit", "superweapon", "attacheffect"):
        return {"rules"}
    return {"rules", "art"}



def _skip_type_lists(project) -> Set[str]:
    """首选项 settings.lint_skip_type_lists：不校验的注册表名（小写）。默认含 animations。"""
    st = {}
    try:
        st = (project.config or {}).get("settings") or {}
    except Exception:
        pass
    raw = st.get("lint_skip_type_lists")
    if raw is None:
        raw = ["Animations"]  # 默认跳过动画注册校验（官方常有有表无节）
    return {str(x).strip().lower() for x in raw if str(x).strip()}

def _lint_invalid_registrations(project, limit_left: int) -> List[LintIssue]:
    """
    无效注册：类型注册表里有 ID，但在「该类型应存在的 ini 族」中找不到 [ID] 节。

    例：Animations 可在 rules 或 art 登记，节体常在 art → 必须查 art，不能只查 rules。
    """
    if limit_left <= 0:
        return []
    issues: List[LintIssue] = []
    list_to_kind = {k.lower(): v for k, v in TYPE_LIST_MAP.items()}
    # 缓存各 scope 的 id 集合
    id_cache: Dict[frozenset, Dict[str, Set[str]]] = {}

    def ids_for(scope: Set[str]) -> Dict[str, Set[str]]:
        key = frozenset(scope)
        if key not in id_cache:
            id_cache[key] = _known_ids_scoped(project, sources=scope)
        return id_cache[key]

    # 注册表节本身可能在 rules 或 art（artmd 常有 [Animations]）
    for src, name, sec in iter_sections(project):
        if src not in ("rules", "art"):
            continue
        kind = list_to_kind.get(name.lower())
        if not kind:
            continue
        if name.lower() in _skip_type_lists(project):
            continue
        label = EXPECT_LABEL.get(kind, kind)
        scope = _resolve_scope_for_kind(kind)
        id_index = ids_for(scope)

        for k in sec.key_order:
            val = (sec.keys.get(k) or "").strip()
            if k.startswith("+@") or k.strip() in ("+", "+=", "++"):
                uid = val
            elif k.strip().isdigit():
                uid = val
            else:
                uid = val or k.strip()
            if not uid or uid.startswith(";") or uid.lower() in PREREQ_ALLOWLIST:
                continue
            if uid.isdigit():
                continue
            ul = uid.lower()
            if ul in id_index:
                continue
            issues.append(
                LintIssue(
                    "warning",
                    name,
                    k if not k.startswith("+@") else "+=",
                    f"注册表中的 {uid!r} 无对应 [{uid}] 节（无效/缺失的{label}注册；已查 {', '.join(sorted(scope))}）",
                    src,
                )
            )
            if len(issues) >= limit_left:
                return issues
    return issues


def lint_project(project, limit: int = 400) -> List[LintIssue]:
    """按源隔离校验；同名仅当在同一源族内重复出现才提示。"""
    issues: List[LintIssue] = []
    # 各源独立索引，避免 rules 引用去对 art 的节「类型不对」
    cache_sets: Dict[str, TypeSets] = {}
    cache_ids: Dict[str, Dict[str, Set[str]]] = {}
    # 同名：按源分别计数（rules 合并后同名只应一次；若真重复再 info）
    seen_in_source: Dict[str, Dict[str, int]] = {}

    for src, name, sec in iter_sections(project):
        scope_key = src
        if scope_key not in cache_sets:
            scope = _scope_for_source(src)
            cache_sets[scope_key] = _build_type_sets(project, sources=scope)
            cache_ids[scope_key] = _known_ids_scoped(project, sources=scope)
        seen_in_source.setdefault(src, {})
        seen_in_source[src][name.lower()] = seen_in_source[src].get(name.lower(), 0) + 1

        for iss in lint_section(
            project,
            name,
            sec,
            source=src,
            type_sets=cache_sets[scope_key],
            id_index=cache_ids[scope_key],
        ):
            issues.append(iss)
            if len(issues) >= limit:
                return issues

    # 仅「同一源内」同名多次才提示（正常 rules+art 同 ID 不再刷屏）
    for src, counts in seen_in_source.items():
        for nl, cnt in counts.items():
            if cnt > 1:
                issues.append(
                    LintIssue(
                        "info",
                        nl,
                        "",
                        f"在 {src} 内同名节出现 {cnt} 次（可能重复定义）",
                        src,
                    )
                )
                if len(issues) >= limit:
                    return issues

    # 无效注册：注册表有 ID 但无节体
    left = limit - len(issues)
    if left > 0:
        issues.extend(_lint_invalid_registrations(project, min(left, 60)))

    # 可能废弃：无任何键值引用到的 rules 对象
    left = limit - len(issues)
    if left > 0:
        issues.extend(_lint_unused_sections(project, min(left, 80)))
    return issues
