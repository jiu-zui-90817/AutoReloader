"""
战术工坊词典构建（逻辑对齐旧版 CodexGenerator）：
  - 单位中文：CSF / UIName / Name
  - 武器下拉：ID - 所属单位 [主武/副武/…]
  - 弹头 / 动画 / 模型 / AE 预设
首次打开工程时生成，写入持久缓存，下次直接加载。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .ini_loader import INIFile
from .csf_loader import CSFParser, load_csf_files


TAG_ZH = {
    "primary": "主武",
    "secondary": "副武",
    "eliteprimary": "精英主武",
    "elitesecondary": "精英副武",
    "occupyweapon": "进驻",
    "eliteoccupyweapon": "精英进驻",
}

BASE_ARMORS = {
    "none": "无装甲",
    "flak": "防弹衣",
    "light": "轻型装甲",
    "medium": "中型装甲",
    "heavy": "重型装甲",
    "wood": "木制",
    "steel": "钢制",
    "concrete": "混凝土",
}

BASE_LOCOMOTORS = {
    "{4A582741-9839-11D1-B709-00A024DDAFD1}": "载具驱动 (Drive)",
    "{4A582742-9839-11D1-B709-00A024DDAFD1}": "气垫两栖 (Hover)",
    "{4A582743-9839-11D1-B709-00A024DDAFD1}": "地底潜行 (Tunnel)",
    "{4A582744-9839-11D1-B709-00A024DDAFD1}": "步兵步行 (Walk)",
    "{4A582746-9839-11D1-B709-00A024DDAFD1}": "战机飞行 (Fly)",
    "{4A582747-9839-11D1-B709-00A024DDAFD1}": "超时空传送 (Teleport)",
    "{55D141B8-DB94-11D1-AC98-006008055BB5}": "机甲 (Mech)",
    "{2BEA74E1-7CCA-11D3-BE14-00104B62A16C}": "舰船水面航行 (Ship)",
}

BASE_BOOLEANS = {
    "yes": "是 (开启)",
    "no": "否 (关闭)",
    "true": "是 (开启)",
    "false": "否 (关闭)",
}

COMMON_AE_ANIMS = {
    "ironfx": "铁幕无敌护盾",
    "forcefield": "力盾防御特效",
    "sphere": "超时空静止球体",
    "emp_fx": "EMP瘫痪电弧",
    "rad_fx": "辐射绿光污染",
    "sirenk": "塞壬声波护盾",
    "mininuke": "微型核爆",
    "nuke": "核弹级爆炸",
}

UNIT_LISTS = [
    ("InfantryTypes", "Infantry"),
    ("VehicleTypes", "Vehicle"),
    ("AircraftTypes", "Aircraft"),
    ("BuildingTypes", "Building"),
]


def _sec_map(ini: Optional[INIFile]) -> Dict[str, Dict[str, str]]:
    """section_id.lower() -> {key.lower(): value}"""
    out: Dict[str, Dict[str, str]] = {}
    if not ini:
        return out
    for name, sec in ini.sections.items():
        props = {k.lower(): v for k, v in sec.keys.items()}
        out[name.lower()] = props
        out[name.lower()]["_id"] = name  # 保留原始大小写
    return out


def _csf_get(csf: CSFParser, key: str) -> str:
    if not key:
        return ""
    v = csf.get_uiname(key) if hasattr(csf, "get_uiname") else ""
    if v:
        return v
    return csf.get(key) or csf.get(key.lower()) or ""


def build_codex(
    game_dir: Path,
    profile: dict,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    """从游戏目录构建与旧版 Codex_ZH.json 结构兼容的词典。"""

    def L(msg: str) -> None:
        if log:
            log(msg)

    game_dir = Path(game_dir)
    rules: Optional[INIFile] = None
    for name in profile.get("rules_files") or ["rulesmo.ini", "rulesmd.ini"]:
        path = game_dir / name
        if path.is_file():
            ini = INIFile()
            if ini.load_with_includes(path, game_dir):
                rules = ini
                L(f"rules: {name} ({len(ini.sections)} sections)")
                break
    if not rules:
        L("未找到 rules 文件")
        return _empty_codex()

    art: Optional[INIFile] = None
    for name in profile.get("art_files") or ["artmo.ini", "artmd.ini"]:
        path = game_dir / name
        if path.is_file():
            ini = INIFile()
            if ini.load_with_includes(path, game_dir):
                art = ini
                L(f"art: {name}")
                break

    patterns = profile.get("csf_files") or ["ra2md.csf", "stringtable*.csf"]
    try:
        csf = load_csf_files(patterns, game_dir)
        L(f"CSF: {len(csf.strings)} 条")
    except Exception as e:
        L(f"CSF 加载失败: {e}")
        csf = CSFParser()

    rules_map = _sec_map(rules)
    # 注册表 ID 列表（保留原始大小写）
    def reg_ids(list_name: str) -> List[str]:
        ids = list(rules.get_list(list_name) or [])
        if art and list_name in ("Animations", "AnimTypes", "Particles", "ParticleSystems"):
            for x in art.get_list(list_name) or []:
                if x not in ids:
                    ids.append(x)
            for alt in ("Animations", "AnimTypes"):
                if alt == list_name:
                    continue
                for x in (art.get_list(alt) or []) + (rules.get_list(alt) or []):
                    if x not in ids:
                        ids.append(x)
        return ids

    unit_dict: Dict[str, Dict[str, str]] = {
        "Infantry": {},
        "Vehicle": {},
        "Aircraft": {},
        "Building": {},
    }
    unit_type_map: Dict[str, str] = {}
    unit_owners: Dict[str, str] = {}
    unit_sides: Dict[str, str] = {}
    eng_to_zh: Dict[str, str] = {}

    # ---------- 主阵营：规则驱动，扫所有带 Side= 的非单位 section ----------
    unit_id_lower: Set[str] = set()
    for list_name, _cat in UNIT_LISTS:
        for uid in reg_ids(list_name):
            unit_id_lower.add(uid.lower())

    country_side: Dict[str, str] = {}  # house/country id lower -> Side
    side_labels: Dict[str, str] = {}
    owner_labels: Dict[str, str] = {}

    def remember_side_label(side_key: str) -> None:
        """解析主阵营显示名：CSF 优先；引擎内置 Side 无文案时才用显示回退。"""
        if not side_key or side_key in ("未分类", "通用"):
            return
        existing = side_labels.get(side_key) or side_labels.get(side_key.lower())
        if existing and existing.lower() != side_key.lower():
            owner_labels[side_key] = existing
            owner_labels[side_key.lower()] = existing
            return

        props = rules_map.get(side_key.lower(), {})
        candidates = []
        if props:
            for k in ("uiname", "name", "loadingscreentext.name", "ui.name"):
                v = (props.get(k) or "").strip()
                if v:
                    candidates.append(v)

        sk = side_key
        # 尽量覆盖 YR / MO / 中文包常见键（仍是按 Side 标识查，不是国家硬编码）
        candidates.extend([
            f"Name:{sk}", f"NAME:{sk}", f"name:{sk}",
            f"UIName:{sk}", f"STT:PlayerSide{sk}", f"STT:Side{sk}",
            f"STT:PlayerSide{sk.upper()}", f"STT:Side{sk.upper()}",
            f"NOSTR:Side{sk}", f"Side:{sk}", f"SIDE:{sk}",
            f"Tooltip:{sk}", sk,
        ])
        # 从属于该 Side 的国家上「借」阵营文案（有的包只给国家写了侧别说明）
        for cid_l, s in country_side.items():
            if s.lower() != sk.lower():
                continue
            cp = rules_map.get(cid_l, {})
            for k in ("uiname", "name", "loadingscreentext.color"):
                v = (cp.get(k) or "").strip()
                if v:
                    candidates.append(v)
            break

        def _looks_chinese(s: str) -> bool:
            return any("一" <= ch <= "鿿" for ch in s)

        zh = ""
        for c in candidates:
            if not c:
                continue
            for got in (_csf_get(csf, c), csf.get(c, "") if hasattr(csf, "get") else ""):
                if not got or got == c:
                    continue
                # 优先中文结果
                if _looks_chinese(got):
                    zh = got
                    break
                if not zh:
                    zh = got
            if zh and _looks_chinese(zh):
                break

        if not zh and props.get("name") and _looks_chinese(props["name"]):
            zh = props["name"]

        # 仅当 CSF/规则都没有可读中文时：对引擎内置 Side 标识做「显示名」回退
        # （分类仍用规则里的 Side= 原值，这里只影响树节点标题）
        if not zh or not _looks_chinese(zh):
            display_fallback = {
                "gdi": "盟军",
                "nod": "苏联",
                "thirdside": "尤里",
                "civilian": "中立",
                "neutral": "中立",
            }
            fb = display_fallback.get(sk.lower())
            if fb:
                zh = fb
            elif not zh:
                zh = sk

        side_labels[side_key] = zh
        side_labels[side_key.lower()] = zh
        owner_labels[side_key] = zh
        owner_labels[side_key.lower()] = zh

    for cid in reg_ids("Countries"):
        props = rules_map.get(cid.lower(), {})
        side = (props.get("side") or "").strip()
        if side:
            country_side[cid.lower()] = side
            remember_side_label(side)

    for sec_name_l, props in list(rules_map.items()):
        if sec_name_l in unit_id_lower:
            continue
        if sec_name_l in {
            "countries", "sides", "infantrytypes", "vehicletypes",
            "aircrafttypes", "buildingtypes", "weapontypes", "warheads",
            "superweapontypes", "projectiletypes", "animations",
        }:
            continue
        side = (props.get("side") or "").strip()
        if not side:
            continue
        country_side[sec_name_l] = side
        remember_side_label(side)

    for sid in reg_ids("Sides"):
        country_side.setdefault(sid.lower(), sid)
        remember_side_label(sid)

    def resolve_side_from_token(token: str) -> str:
        if not token:
            return ""
        tok = token.strip()
        if not tok or tok.lower() in ("none", "all", "<all>"):
            return ""
        if tok.lower() in country_side:
            return country_side[tok.lower()]
        known = {v.lower(): v for v in country_side.values()}
        if tok.lower() in known:
            return known[tok.lower()]
        for s in side_labels:
            if s.lower() == tok.lower():
                return s
        props = rules_map.get(tok.lower(), {})
        side = (props.get("side") or "").strip()
        if side:
            country_side[tok.lower()] = side
            remember_side_label(side)
            return side
        return ""

    def _is_non_combat_side(side: str) -> bool:
        """中立/平民类 Side 不参与「是否跨主阵营」判断。"""
        s = (side or "").lower()
        return s in {
            "civilian", "neutral", "special", "mutant",
            "中立", "平民", "通用", "未分类",
        }

    def classify_unit_side(props: Dict[str, str]) -> str:
        """
        - Owner 里战斗主阵营只有 1 种 → 归该主阵营（子阵营特有单位也如此）
        - 战斗主阵营 ≥2 种 → 通用
        - 只有中立/平民 → 归中立类 Side
        - 解析不出 → 未分类

        说明：Neutral/Civilian 常和国家写在同一行 Owner 里，
        不能因此把「英国专属」打成通用。
        """
        owner_raw = props.get("owner") or props.get("requiredhouses") or ""
        tokens = [x.strip() for x in owner_raw.split(",") if x.strip()]
        tokens = [x for x in tokens if x.lower() not in ("none", "all", "<all>")]

        sides_found: list = []
        seen_l = set()
        for tok in tokens:
            side = resolve_side_from_token(tok)
            if not side:
                continue
            canon = side
            for k in side_labels:
                if k.lower() == side.lower():
                    canon = k
                    break
            if canon.lower() not in seen_l:
                seen_l.add(canon.lower())
                sides_found.append(canon)

        combat = [s for s in sides_found if not _is_non_combat_side(s)]
        non_combat = [s for s in sides_found if _is_non_combat_side(s)]

        if len(combat) == 1:
            return combat[0]
        if len(combat) >= 2:
            return "通用"
        if non_combat:
            return non_combat[0]

        self_side = (props.get("side") or "").strip()
        if self_side:
            mapped = resolve_side_from_token(self_side) or self_side
            return mapped
        return "未分类"


    for list_name, cat in UNIT_LISTS:
        for uid in reg_ids(list_name):
            props = rules_map.get(uid.lower(), {})
            uiname = props.get("uiname", "")
            name = props.get("name", "")
            zh = _csf_get(csf, uiname) or name or _csf_get(csf, f"Name:{uid}") or _csf_get(csf, uid) or uid
            unit_dict[cat][uid] = zh
            unit_type_map[uid] = cat
            eng_to_zh[uid.lower()] = zh
            side_key = classify_unit_side(props)
            unit_sides[uid] = side_key
            unit_owners[uid] = side_key
            if side_key != "未分类":
                remember_side_label(side_key)

    owner_labels["未分类"] = "未分类"
    side_labels["未分类"] = "未分类"
    owner_labels["通用"] = "通用"
    side_labels["通用"] = "通用"

    L(
        f"单位: {sum(len(v) for v in unit_dict.values())}，"
        f"主阵营: {sorted(set(unit_sides.values()))}，"
        f"势力条目: {len(country_side)}"
    )

    weapon_list_flat: Dict[str, str] = {}
    warhead_list_flat: Dict[str, str] = {}
    processed_w: Set[str] = set()
    processed_wh: Set[str] = set()
    image_dicts = {k: {} for k in ("Infantry", "Vehicle", "Aircraft", "Building", "Unknown")}
    armor_dict = dict(BASE_ARMORS)
    locomotor_dict = dict(BASE_LOCOMOTORS)
    presets_passive: Dict[str, dict] = {
        "❌ 【一键卸载】清除所有被动光环": {
            "attacheffect.animation": "none",
            "attacheffect.duration": "0",
            "attacheffect.speedmultiplier": "1",
            "attacheffect.armormultiplier": "1",
            "attacheffect.firepowermultiplier": "1",
            "attacheffect.rofmultiplier": "1",
            "attacheffect.delay": "0",
            "attacheffect.initialdelay": "0",
        }
    }
    presets_attack: Dict[str, dict] = {
        "❌ 【一键卸载】清除所有打击控制": {
            "attacheffect.animation": "none",
            "attacheffect.duration": "0",
            "attacheffect.speedmultiplier": "1",
            "attacheffect.armormultiplier": "1",
            "attacheffect.firepowermultiplier": "1",
            "attacheffect.rofmultiplier": "1",
            "attacheffect.cumulative": "no",
        }
    }
    anim_detective: Dict[str, str] = {}

    for uid_l, zh_name in eng_to_zh.items():
        props = rules_map.get(uid_l, {})
        if not props:
            continue
        uid = props.get("_id", uid_l)
        u_type = unit_type_map.get(uid, "Unknown")

        # 单位自带 AE → 被动预设
        ae_tags = {k: v for k, v in props.items() if k.startswith("attacheffect.")}
        if ae_tags:
            presets_passive[f"【光环】{zh_name}"] = ae_tags
        if "attacheffect.animation" in props:
            anim_detective[props["attacheffect.animation"].lower()] = f"[{zh_name}] 出厂光环"

        for w_tag, zh_tag in TAG_ZH.items():
            if w_tag not in props or props[w_tag].lower() == "none":
                continue
            w_id = props[w_tag]
            w_l = w_id.lower()
            if w_l not in processed_w:
                processed_w.add(w_l)
                w_zh = zh_name
                w_props = rules_map.get(w_l, {})
                if w_props:
                    wu = w_props.get("uiname", "")
                    wn = w_props.get("name", "")
                    w_zh = _csf_get(csf, wu) or wn or _csf_get(csf, w_id) or zh_name
                    if "anim" in w_props:
                        anim_detective.setdefault(w_props["anim"].lower(), f"[{zh_name}] 枪口火花")
                weapon_list_flat[w_id] = f"{w_zh} [{zh_tag}]"

            # 弹头
            w_props = rules_map.get(w_l, {})
            if w_props and "warhead" in w_props and w_props["warhead"].lower() != "none":
                wh_id = w_props["warhead"]
                wh_l = wh_id.lower()
                if wh_l not in processed_wh:
                    processed_wh.add(wh_l)
                    warhead_list_flat[wh_id] = f"{zh_name} [{zh_tag}弹头]"
                    wh_props = rules_map.get(wh_l, {})
                    if wh_props:
                        ae = {k: v for k, v in wh_props.items() if k.startswith("attacheffect.")}
                        if ae:
                            presets_attack[f"【打击】{zh_name}"] = ae
                        if "animlist" in wh_props:
                            first = wh_props["animlist"].split(",")[0].strip().lower()
                            anim_detective.setdefault(first, f"[{zh_name}] 爆炸特效")
                        if "attacheffect.animation" in wh_props:
                            anim_detective.setdefault(
                                wh_props["attacheffect.animation"].lower(),
                                f"[{zh_name}] 附加AE",
                            )

        img_id = props.get("image", uid)
        image_dicts.setdefault(u_type, {})[img_id] = f"[{zh_name}] 模型"

        if "armor" in props:
            ar = props["armor"]
            if ar.lower() not in {k.lower() for k in armor_dict}:
                armor_dict[ar] = f"特种装甲 ({ar})"
        if "locomotor" in props:
            loc = props["locomotor"]
            if loc.upper() not in {k.upper() for k in locomotor_dict}:
                locomotor_dict[loc] = f"未知引擎 ({loc})"

    # 注册表里有、但未被单位引用的武器也补上
    for w_id in reg_ids("WeaponTypes"):
        if w_id.lower() in processed_w:
            continue
        props = rules_map.get(w_id.lower(), {})
        zh = props.get("name") or _csf_get(csf, props.get("uiname", "")) or w_id
        weapon_list_flat[w_id] = f"{zh} [未挂载]"
        processed_w.add(w_id.lower())

    for wh_id in reg_ids("Warheads"):
        if wh_id.lower() in processed_wh:
            continue
        props = rules_map.get(wh_id.lower(), {})
        zh = props.get("name") or wh_id
        warhead_list_flat[wh_id] = f"{zh} [未挂载]"
        processed_wh.add(wh_id.lower())

    # 动画列表
    anim_list_flat: Dict[str, str] = {}
    for anim_id in reg_ids("Animations") + reg_ids("AnimTypes"):
        al = anim_id.lower()
        if al in anim_list_flat:
            continue
        label = anim_detective.get(al, "")
        if not label:
            for key, translated in COMMON_AE_ANIMS.items():
                if key in al:
                    label = translated
                    break
        anim_list_flat[anim_id] = f"{anim_id} - {label}" if label else anim_id

    # 再补 detective 里出现但不在注册表的
    for al, label in anim_detective.items():
        # 找原始大小写
        found = None
        for k in anim_list_flat:
            if k.lower() == al:
                found = k
                break
        if found:
            if " - " not in anim_list_flat[found]:
                anim_list_flat[found] = f"{found} - {label}"
        else:
            anim_list_flat[al] = f"{al} - {label}"

    L(f"武器 {len(weapon_list_flat)} / 弹头 {len(warhead_list_flat)} / 动画 {len(anim_list_flat)}")

    return {
        "Units": unit_dict,
        "WeaponList": weapon_list_flat,
        "WarheadList": warhead_list_flat,
        "AnimList": anim_list_flat,
        "Presets_Passive": presets_passive,
        "Presets_Attack": presets_attack,
        "Armors": armor_dict,
        "Locomotors": locomotor_dict,
        "Booleans": BASE_BOOLEANS,
        "UnitTypeMap": unit_type_map,
        "UnitOwners": unit_owners,
        "UnitSides": unit_sides,
        "OwnerLabels": owner_labels,
        "InfantryImages": image_dicts["Infantry"],
        "VehicleImages": image_dicts["Vehicle"],
        "AircraftImages": image_dicts["Aircraft"],
        "BuildingImages": image_dicts["Building"],
        "UnknownImages": image_dicts["Unknown"],
        "_meta": {
            "units": sum(len(v) for v in unit_dict.values()),
            "weapons": len(weapon_list_flat),
            "warheads": len(warhead_list_flat),
            "anims": len(anim_list_flat),
        },
    }


def _empty_codex() -> dict:
    return {
        "Units": {"Infantry": {}, "Vehicle": {}, "Aircraft": {}, "Building": {}},
        "WeaponList": {},
        "WarheadList": {},
        "AnimList": {},
        "Presets_Passive": {},
        "Presets_Attack": {},
        "Armors": dict(BASE_ARMORS),
        "Locomotors": dict(BASE_LOCOMOTORS),
        "Booleans": dict(BASE_BOOLEANS),
        "UnitTypeMap": {},
        "UnitOwners": {},
        "UnitSides": {},
        "OwnerLabels": {},
        "InfantryImages": {},
        "VehicleImages": {},
        "AircraftImages": {},
        "BuildingImages": {},
        "UnknownImages": {},
        "_meta": {},
    }


def save_codex(codex: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(codex, ensure_ascii=False), encoding="utf-8")


def load_codex(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "WeaponList" in data:
            return data
    except Exception:
        pass
    return None
