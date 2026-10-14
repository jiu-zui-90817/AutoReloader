"""
C1：依赖关系视图
单位 → 武器槽 / 建造前提 / 子机… → 弹头 / 抛射体 / 建筑…
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

# 字段英文 → 中文角色（节点上显示，避免全是「武器」分不清）
FIELD_ROLE_ZH: Dict[str, str] = {
    "Primary": "主武器",
    "Secondary": "副武器",
    "ElitePrimary": "精英主武器",
    "EliteSecondary": "精英副武器",
    "DeathWeapon": "死亡武器",
    "OccupyWeapon": "进驻武器",
    "EliteOccupyWeapon": "精英进驻武器",
    "OpenTransportWeapon": "运输内开火",
    "Weapon1": "武器1",
    "Weapon2": "武器2",
    "Weapon3": "武器3",
    "Weapon4": "武器4",
    "Weapon5": "武器5",
    "Weapon6": "武器6",
    "Weapons": "武器列表",
    "AirburstWeapon": "空爆子武器",
    "ShrapnelWeapon": "溅射子武器",
    "Projectile": "抛射体",
    "Warhead": "弹头",
    "Anim": "动画",
    "AnimList": "动画列表",
    "OccupantAnim": "进驻动画",
    "Particle": "粒子",
    "ParticleSystem": "粒子系统",
    "Prerequisite": "建造前提",
    "PrerequisiteOverride": "前提覆盖",
    "Soylent": "",  # 非引用
    "Image": "图像/Art",
    "Spawns": "子机/生成",
    "MissileType": "导弹类型",
    "Spawns.Types": "子机类型",
    "Gunner": "炮手逻辑",
    "IFVWeapon": "IFV武器",
    "Explosion": "爆炸动画",
    "DestroyAnim": "摧毁动画",
    "DebrisAnims": "碎片动画",
    "VoiceSelect": "选择音",
    "CrushSound": "碾压音",
}

# 单位/建筑上常见的武器槽
UNIT_WEAPON_KEYS = (
    "Primary",
    "Secondary",
    "ElitePrimary",
    "EliteSecondary",
    "DeathWeapon",
    "OccupyWeapon",
    "EliteOccupyWeapon",
    "OpenTransportWeapon",
    "Weapon1",
    "Weapon2",
    "Weapon3",
    "Weapon4",
    "Weapon5",
    "Weapon6",
)

# 单位上非武器、但仍指向其它 section 的依赖
UNIT_OTHER_REFS = (
    ("Prerequisite", "building", True),
    ("PrerequisiteOverride", "building", True),
    ("Prerequisite.RequiredTheaters", "skip", True),  # 非 section
    ("PrerequisitePower", "building", True),
    ("PrerequisiteProc", "building", True),
    ("PrerequisiteProcAlternate", "building", True),
    ("RequiresStolenAlliedTech", "skip", False),
    ("RequiresStolenSovietTech", "skip", False),
    ("RequiresStolenThirdTech", "skip", False),
    ("Spawns", "unit", False),
    ("MissileType", "unit", False),
    ("Image", "art", False),
    ("Explosion", "animation", True),
    ("DestroyAnim", "animation", True),
    ("DebrisAnims", "animation", True),
)

# 武器节上指向下游的键
WEAPON_DOWNSTREAM = (
    ("Projectile", "projectile"),
    ("Warhead", "warhead"),
    ("Anim", "animation"),
    ("OccupantAnim", "animation"),
    ("AirburstWeapon", "weapon"),
    ("ShrapnelWeapon", "weapon"),
)

# 弹头上可再展开的引用（浅一层）
WARHEAD_REFS = (
    ("Anim", "animation"),
    ("AnimList", "animation_list"),
    ("Particle", "particle"),
    ("ParticleSystem", "particle_system"),
)


def field_role_zh(field: str) -> str:
    if not field:
        return ""
    # Weapons[0] → 武器列表
    base = field.split("[", 1)[0]
    return FIELD_ROLE_ZH.get(base) or FIELD_ROLE_ZH.get(field) or field


def _display_of(project, section_id: str) -> str:
    """CSF / Name 中文显示名，失败则空。"""
    if not section_id or not project:
        return ""
    try:
        if hasattr(project, "get_display_name"):
            d = project.get_display_name(section_id) or ""
            if d and d.strip().lower() != section_id.strip().lower():
                return d.strip()
            return d.strip() if d else ""
    except Exception:
        pass
    try:
        sec = project.get_section(section_id)
        if sec:
            n = (sec.get("Name") or "").strip()
            if n:
                return n
    except Exception:
        pass
    return ""


def _sec_get(sec, key: str) -> str:
    if not sec:
        return ""
    try:
        return (sec.get(key) or "").strip()
    except Exception:
        return ""


def _split_list(val: str) -> List[str]:
    if not val:
        return []
    parts = []
    for chunk in val.replace(";", ",").split(","):
        s = chunk.strip()
        if s:
            parts.append(s)
    return parts


def _is_plausible_id(val: str) -> bool:
    """过滤明显不是 section 名的值：纯数字序号、yes/no、过短无意义符号。"""
    s = (val or "").strip()
    if not s:
        return False
    low = s.lower()
    if low in ("none", "null", "yes", "no", "true", "false"):
        return False
    # DeployFireWeapon=0/1 这类槽位序号，不是武器名
    if s.isdigit():
        return False
    if len(s) == 1 and not s.isalnum():
        return False
    return True


def _node(
    kind: str,
    id_: str,
    *,
    field: str = "",
    exists: bool = True,
    extra: str = "",
    children: Optional[List[dict]] = None,
) -> dict:
    role = field_role_zh(field)
    return {
        "kind": kind,
        "id": id_,
        "field": field,
        "role": role,  # 中文角色：主武器 / 建造前提 …
        "exists": exists,
        "extra": extra,
        "children": children or [],
    }


def build_dependency_tree(
    project,
    root_id: str,
    *,
    prefer=None,
    max_depth: int = 4,
    show_weapons: bool = True,
    show_prereq: bool = True,
    show_art: bool = True,
    show_anims: bool = True,
    expand_anims: bool = False,
    show_spawns: bool = True,
    concise: bool = True,
) -> dict:
    """
    以 root_id 为根构建依赖树。
    concise: 武器只展到抛射体/弹头，弹头不再展开动画；爆炸动画仅显示分组不展开。
    expand_anims: True 时展开动画组内每个 ID。
    """
    root_id = (root_id or "").strip()
    visited: Set[Tuple[str, str]] = set()  # (kind, id_lower)
    if concise:
        max_depth = min(max_depth, 3)

    def get_sec(name: str):
        if not name:
            return None
        try:
            return project.get_section(name, prefer=prefer)
        except TypeError:
            return project.get_section(name)
        except Exception:
            return None

    def walk_weapon(wid: str, field: str, depth: int) -> dict:
        key = ("weapon", wid.lower())
        sec = get_sec(wid)
        node = _node(
            "weapon", wid, field=field, exists=bool(sec),
            extra=_display_of(project, wid),
        )
        if key in visited or depth >= max_depth:
            if key in visited:
                node["extra"] = (node.get("extra") or "") + "（已展开过）"
            return node
        visited.add(key)
        if not sec:
            return node

        for item in WEAPON_DOWNSTREAM:
            if isinstance(item, str):
                continue  # Report 等噪音不进图
            k, kind = item
            val = _sec_get(sec, k)
            if not _is_plausible_id(val):
                continue
            if kind == "projectile":
                node["children"].append(walk_simple("projectile", val, k, depth + 1))
            elif kind == "warhead":
                node["children"].append(walk_warhead(val, k, depth + 1))
            elif kind == "animation":
                if not show_anims:
                    continue
                if expand_anims and not concise:
                    node["children"].append(walk_simple("animation", val, k, depth + 1))
                else:
                    # 单动画也只挂一层点，不继续深挖
                    node["children"].append(walk_simple("animation", val, k, depth + 1))
            elif kind == "weapon":
                if show_weapons:
                    node["children"].append(walk_weapon(val, k, depth + 1))
        return node

    def walk_warhead(wid: str, field: str, depth: int) -> dict:
        key = ("warhead", wid.lower())
        sec = get_sec(wid)
        node = _node(
            "warhead", wid, field=field, exists=bool(sec),
            extra=_display_of(project, wid),
        )
        if key in visited or depth >= max_depth:
            if key in visited:
                node["extra"] = (node.get("extra") or "") + "（已展开过）"
            return node
        visited.add(key)
        if not sec:
            return node
        if concise or not show_anims:
            return node  # 简洁：弹头不再挂动画/粒子
        for k, kind in WARHEAD_REFS:
            val = _sec_get(sec, k)
            if not val:
                continue
            if kind == "animation_list":
                aids = [a for a in _split_list(val) if _is_plausible_id(a)]
                if not aids:
                    continue
                role = field_role_zh(k) or "动画列表"
                if not expand_anims:
                    node["children"].append(
                        _node(
                            "group",
                            f"{role}·{k}",
                            field=k,
                            exists=True,
                            extra=f"{len(aids)} 项（未展开）",
                        )
                    )
                    node["children"][-1]["role"] = role
                    continue
                if len(aids) == 1:
                    node["children"].append(
                        walk_simple("animation", aids[0], k, depth + 1)
                    )
                else:
                    grp = _node(
                        "group",
                        f"{role}·{k}",
                        field=k,
                        exists=True,
                        extra=f"{len(aids)} 项",
                    )
                    grp["role"] = role
                    for i, aid in enumerate(aids):
                        grp["children"].append(
                            walk_simple("animation", aid, f"{k}[{i}]", depth + 2)
                        )
                    node["children"].append(grp)
            else:
                if _is_plausible_id(val):
                    node["children"].append(walk_simple(kind, val, k, depth + 1))
        return node

    def walk_simple(kind: str, iid: str, field: str, depth: int) -> dict:
        key = (kind, iid.lower())
        sec = get_sec(iid)
        node = _node(
            kind, iid, field=field, exists=bool(sec),
            extra=_display_of(project, iid),
        )
        if key in visited:
            node["extra"] = (node.get("extra") or "") + "（已展开过）"
        else:
            visited.add(key)
        return node

    def walk_unit(uid: str, depth: int = 0) -> dict:
        sec = get_sec(uid)
        display = _display_of(project, uid)
        if not display and sec:
            display = _sec_get(sec, "Name")
        node = _node(
            "unit",
            uid,
            exists=bool(sec),
            extra=display,
        )
        if not sec:
            return node
        key = ("unit", uid.lower())
        if key in visited:
            node["extra"] = (node["extra"] + " （已展开过）").strip()
            return node
        visited.add(key)

        if show_weapons:
            for wk in UNIT_WEAPON_KEYS:
                val = _sec_get(sec, wk)
                if not _is_plausible_id(val):
                    continue
                node["children"].append(walk_weapon(val, wk, depth + 1))

            for i, wid in enumerate(_split_list(_sec_get(sec, "Weapons"))):
                if not _is_plausible_id(wid):
                    continue
                node["children"].append(walk_weapon(wid, f"Weapons[{i}]", depth + 1))

        # 建造前提：先收集，多个时挂「建造前提」分组节点再展开
        prereq_items = []  # (field, id)

        def _add_prereq_vals(key: str, raw: str, is_list: bool):
            vals = _split_list(raw) if is_list else [raw]
            for i, vid in enumerate(vals):
                if not _is_plausible_id(vid):
                    continue
                fld = f"{key}[{i}]" if is_list and len(vals) > 1 else key
                prereq_items.append((fld, vid))

        for key, kind, is_list in UNIT_OTHER_REFS:
            if kind == "skip":
                continue
            raw = _sec_get(sec, key)
            if not raw:
                continue
            if kind == "building":
                _add_prereq_vals(key, raw, is_list)
                continue
            vals = [v for v in (_split_list(raw) if is_list else [raw]) if _is_plausible_id(v)]
            if not vals:
                continue
            if kind == "unit":
                if not show_spawns:
                    continue
                for i, vid in enumerate(vals):
                    fld = f"{key}[{i}]" if is_list and len(vals) > 1 else key
                    node["children"].append(walk_simple("unit", vid, fld, depth + 1))
            elif kind == "art":
                if not show_art:
                    continue
                for i, vid in enumerate(vals):
                    fld = f"{key}[{i}]" if is_list and len(vals) > 1 else key
                    art_sec = None
                    try:
                        if getattr(project, "art", None):
                            art_sec = project.art.get_section(vid)
                    except Exception:
                        art_sec = None
                    node["children"].append(
                        _node(
                            "art",
                            vid,
                            field=fld,
                            exists=bool(art_sec) or bool(get_sec(vid)),
                        )
                    )
            elif kind in ("animation", "particle", "particle_system"):
                if not show_anims:
                    continue
                role = field_role_zh(key) or key
                if not expand_anims or len(vals) > 1:
                    # 默认：只显示分组（含数量），不把每个紫块铺开
                    grp = _node(
                        "group",
                        f"{role}·{key}",
                        field=key,
                        exists=True,
                        extra=f"{len(vals)} 项" + ("" if expand_anims else "（未展开）"),
                    )
                    grp["role"] = role
                    if expand_anims:
                        for i, vid in enumerate(vals):
                            fld = f"{key}[{i}]" if len(vals) > 1 else key
                            grp["children"].append(
                                walk_simple(kind, vid, fld, depth + 2)
                            )
                    node["children"].append(grp)
                else:
                    node["children"].append(
                        walk_simple(kind, vals[0], key, depth + 1)
                    )
            else:
                for i, vid in enumerate(vals):
                    fld = f"{key}[{i}]" if is_list and len(vals) > 1 else key
                    node["children"].append(walk_simple(kind, vid, fld, depth + 1))

        # 动态 Prerequisite.* 
        try:
            keys = list(sec.key_order or [])
        except Exception:
            keys = []
        known = {k for k, _, _ in UNIT_OTHER_REFS}
        for key in keys:
            if key in known:
                continue
            kl = key.lower()
            if not kl.startswith("prerequisite"):
                continue
            if kl in ("prerequisite", "prerequisiteoverride"):
                continue
            raw = _sec_get(sec, key)
            if not raw or raw.lower() in ("yes", "no", "true", "false"):
                continue
            _add_prereq_vals(key, raw, True)

        # 去重保序
        seen_p = set()
        uniq_prereq = []
        for fld, vid in prereq_items:
            lk = vid.lower()
            if lk in seen_p:
                continue
            seen_p.add(lk)
            uniq_prereq.append((fld, vid))

        if not show_prereq:
            uniq_prereq = []
        if len(uniq_prereq) == 1:
            fld, vid = uniq_prereq[0]
            node["children"].append(walk_simple("building", vid, fld or "Prerequisite", depth + 1))
        elif len(uniq_prereq) > 1:
            grp = _node(
                "group",
                "建造前提·Prerequisite",
                field="Prerequisite",
                exists=True,
                extra=f"{len(uniq_prereq)} 项",
            )
            grp["role"] = "建造前提"
            for fld, vid in uniq_prereq:
                grp["children"].append(
                    walk_simple("building", vid, fld or "Prerequisite", depth + 2)
                )
            node["children"].append(grp)

        return node

    # 若当前就是武器/弹头，从对应类型开根
    root_sec = get_sec(root_id)
    if root_sec is not None:
        # 粗判：有 Projectile 或 Warhead 键 → 当武器
        if _sec_get(root_sec, "Projectile") or _sec_get(root_sec, "Warhead"):
            if not _sec_get(root_sec, "Primary") and not _sec_get(root_sec, "Strength"):
                return walk_weapon(root_id, "(root)", 0)
        if _sec_get(root_sec, "Verses") or (
            _sec_get(root_sec, "Anim") and not _sec_get(root_sec, "Primary")
            and not _sec_get(root_sec, "Strength")
        ):
            # 弱启发：弹头常有 Verses
            if _sec_get(root_sec, "Verses"):
                return walk_warhead(root_id, "(root)", 0)

    return walk_unit(root_id, 0)


def tree_to_lines(node: dict, indent: int = 0) -> List[str]:
    """纯文本展开，便于复制。"""
    kind_zh = {
        "unit": "单位",
        "weapon": "武器",
        "warhead": "弹头",
        "projectile": "抛射体",
        "animation": "动画",
        "particle": "粒子",
        "particle_system": "粒子系统",
        "building": "建筑/前提",
        "art": "Art/图像",
        "group": "分组",
        "value": "值",
    }
    pad = "  " * indent
    mark = "" if node.get("exists", True) else " ⚠缺失"
    extra = f"  {node['extra']}" if node.get("extra") else ""
    role = node.get("role") or field_role_zh(node.get("field") or "")
    role_s = f"{role} · " if role else ""
    field = node.get("field") or ""
    field_s = f"{field} = " if field and node.get("kind") != "unit" else ""
    if node.get("kind") == "unit" and not node.get("field"):
        field_s = ""
    label = kind_zh.get(node.get("kind", ""), node.get("kind", ""))
    line = f"{pad}{role_s}{field_s}[{node.get('id','')}]  ({label}){mark}{extra}"
    lines = [line]
    for ch in node.get("children") or []:
        lines.extend(tree_to_lines(ch, indent + 1))
    return lines


def flatten_jump_targets(node: dict) -> List[str]:
    """可跳转的 section id 列表（去重保序）。"""
    out: List[str] = []
    seen: Set[str] = set()

    def rec(n: dict):
        if n.get("kind") in (
            "unit",
            "weapon",
            "warhead",
            "projectile",
            "animation",
            "particle",
            "particle_system",
            "building",
            "art",
        ) and n.get("kind") != "group":
            iid = n.get("id") or ""
            if iid and iid.lower() not in seen and n.get("exists", True):
                seen.add(iid.lower())
                out.append(iid)
        for ch in n.get("children") or []:
            rec(ch)

    rec(node)
    return out


def collect_graph(node: dict) -> Tuple[List[dict], List[dict]]:
    """
    把树展成图：nodes[{id, kind, exists, extra}], edges[{src, dst, field}].
    同一 id 只保留一个节点（kind 取第一次）。
    """
    nodes: Dict[str, dict] = {}
    edges: List[dict] = []

    def add_node(n: dict):
        iid = n.get("id") or ""
        if not iid or n.get("kind") == "value":
            return
        k = iid.lower()
        if k not in nodes:
            nodes[k] = {
                "id": iid,
                "kind": n.get("kind") or "unit",
                "exists": n.get("exists", True),
                "extra": n.get("extra") or "",
            }
        else:
            if n.get("extra") and not nodes[k].get("extra"):
                nodes[k]["extra"] = n["extra"]
            if n.get("exists") is False:
                nodes[k]["exists"] = False

    def rec(n: dict, parent_id: str = ""):
        add_node(n)
        iid = n.get("id") or ""
        if parent_id and iid and n.get("kind") != "value":
            edges.append({
                "src": parent_id,
                "dst": iid,
                "field": n.get("field") or "",
            })
        for ch in n.get("children") or []:
            if ch.get("kind") == "value":
                # 叶子值挂在边上说明即可，不建节点
                continue
            rec(ch, iid if iid else parent_id)

    rec(node)
    return list(nodes.values()), edges


def layout_layers(nodes: List[dict], edges: List[dict], root_id: str) -> Dict[str, Tuple[float, float]]:
    """上下分层：深度越大越靠下；同层按类型+名称横向排开。"""
    kind_rank = {
        "unit": 0,
        "group": 1,
        "weapon": 2,
        "building": 2,
        "art": 2,
        "projectile": 3,
        "warhead": 3,
        "animation": 4,
        "particle": 4,
        "particle_system": 4,
    }
    depth: Dict[str, int] = {}
    root_l = (root_id or "").lower()
    # group 节点 id 可能是中文「建造前提」
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e["src"].lower(), []).append(e["dst"].lower())
    from collections import deque
    q = deque()
    if root_l:
        depth[root_l] = 0
        q.append(root_l)
    # 若 root 大小写不一致
    id_map = {n["id"].lower(): n for n in nodes}
    if root_l not in depth:
        for n in nodes:
            if n.get("kind") == "unit":
                depth[n["id"].lower()] = 0
                q.append(n["id"].lower())
                break
    while q:
        u = q.popleft()
        for v in adj.get(u, []):
            nd = depth[u] + 1
            if v not in depth or nd < depth[v]:
                depth[v] = nd
                q.append(v)

    buckets: Dict[int, List[str]] = {}
    for n in nodes:
        k = n["id"].lower()
        d = depth.get(k)
        if d is None:
            d = kind_rank.get(n.get("kind"), 1)
        buckets.setdefault(d, []).append(k)

    positions: Dict[str, Tuple[float, float]] = {}
    x_gap, y_gap = 190.0, 110.0
    max_per_row = 6  # 同层过多则换行，避免一条横幅铺满屏幕
    # 层与层之间额外留出行内折行高度
    y_cursor = 0.0
    for d, ids in sorted(buckets.items()):
        ids_sorted = sorted(
            ids,
            key=lambda i: (
                kind_rank.get(id_map[i].get("kind"), 9),
                id_map[i].get("role") or "",
                id_map[i].get("id") or "",
            ),
        )
        n = len(ids_sorted)
        rows = max(1, (n + max_per_row - 1) // max_per_row)
        for i, iid in enumerate(ids_sorted):
            row = i // max_per_row
            col = i % max_per_row
            # 当前行实际数量
            in_row = min(max_per_row, n - row * max_per_row)
            x = (col - (in_row - 1) / 2.0) * x_gap
            y = y_cursor + row * (y_gap * 0.85)
            positions[iid] = (x, y)
        y_cursor += max(rows, 1) * y_gap
    return positions



# ---------- 反向依赖：谁引用了当前 ID ----------

# 扫描时关注的键 → 关系角色
_REVERSE_SCAN_KEYS = (
    list(UNIT_WEAPON_KEYS)
    + ["Weapons", "Prerequisite", "PrerequisiteOverride", "Spawns", "MissileType", "Image",
       "Explosion", "DestroyAnim", "DebrisAnims",
       "Projectile", "Warhead", "Anim", "AnimList", "OccupantAnim",
       "AirburstWeapon", "ShrapnelWeapon", "Particle", "ParticleSystem"]
)


def build_reverse_index(project, prefer=None) -> Dict[str, List[dict]]:
    """
    target_id_lower -> [{source, field, role}, ...]
    一次扫描 rules（或 prefer）全部 section，供反向查询。
    """
    ini = prefer or getattr(project, "rules", None) or project.active_ini()
    index: Dict[str, List[dict]] = {}
    if not ini:
        return index
    try:
        sections = getattr(ini, "sections", None) or {}
        items = list(sections.items()) if hasattr(sections, "items") else []
    except Exception:
        items = []
    if not items:
        # fallback: classify + get_section
        try:
            groups = project.classify_sections(ini) or {}
            names = []
            for ids in groups.values():
                names.extend(ids)
            items = [(n, project.get_section(n, prefer=ini)) for n in names]
        except Exception:
            items = []

    scan_keys = set(_REVERSE_SCAN_KEYS)
    for sname, sec in items:
        if not sec or not sname:
            continue
        # 跳过类型注册表本身
        if str(sname).endswith("Types") or str(sname) in (
            "Warheads", "Animations", "Projectiles", "VariableNames"
        ):
            continue
        try:
            keys = list(sec.key_order or [])
        except Exception:
            try:
                keys = list(sec.keys.keys()) if hasattr(sec, "keys") else []
            except Exception:
                keys = []
        for key in keys:
            base = key.split("[", 1)[0]
            # Prerequisite.* 也扫
            if base not in scan_keys and not base.lower().startswith("prerequisite"):
                continue
            try:
                raw = (sec.get(key) or "").strip()
            except Exception:
                raw = ""
            if not raw:
                continue
            for part in raw.replace(";", ",").split(","):
                tid = part.strip()
                if not tid or tid.isdigit():
                    continue
                if tid.lower() in ("none", "null", "yes", "no"):
                    continue
                role = field_role_zh(key) or key
                index.setdefault(tid.lower(), []).append(
                    {"source": sname, "field": key, "role": role}
                )
    return index


def build_reverse_tree(
    project,
    root_id: str,
    *,
    prefer=None,
    index: Optional[Dict[str, List[dict]]] = None,
    max_sources: int = 40,
) -> dict:
    """
    以 root 为中心，列出引用它的 section（向上追查）。
    按角色分组：主武器、弹头、建造前提…
    """
    root_id = (root_id or "").strip()
    if index is None:
        index = build_reverse_index(project, prefer=prefer)
    refs = list(index.get(root_id.lower()) or [])

    # 当前节是否存在
    try:
        exists = bool(project.get_section(root_id, prefer=prefer))
    except TypeError:
        exists = bool(project.get_section(root_id))
    except Exception:
        exists = True

    disp = _display_of(project, root_id)
    root = _node(
        "unit", root_id, exists=exists,
        extra=(f"{disp} · " if disp else "") + "（被引用方）",
    )
    # 猜测类型
    try:
        sec = project.get_section(root_id, prefer=prefer)
        if sec and (_sec_get(sec, "Projectile") or _sec_get(sec, "Warhead")):
            root["kind"] = "weapon"
        elif sec and _sec_get(sec, "Verses"):
            root["kind"] = "warhead"
    except Exception:
        pass

    if not refs:
        root["extra"] = "（没有找到引用方 — 或未被扫描键引用）"
        return root

    # 按 role 分组
    by_role: Dict[str, List[dict]] = {}
    for r in refs:
        role = r.get("role") or r.get("field") or "引用"
        by_role.setdefault(role, []).append(r)

    total = 0
    for role, items in sorted(by_role.items(), key=lambda x: x[0]):
        # 去重 source
        seen = set()
        uniq = []
        for it in items:
            s = it["source"]
            if s.lower() in seen:
                continue
            seen.add(s.lower())
            uniq.append(it)
        grp = _node(
            "group",
            f"引用·{role}",
            field=role,
            exists=True,
            extra=f"{len(uniq)} 个",
        )
        grp["role"] = role
        for it in uniq:
            if total >= max_sources:
                grp["children"].append(
                    _node("group", "…更多", field="", exists=True, extra="已截断")
                )
                break
            src = it["source"]
            try:
                ex = bool(project.get_section(src, prefer=prefer))
            except Exception:
                ex = True
            # 粗判 kind
            kind = "unit"
            try:
                ssec = project.get_section(src, prefer=prefer)
                if ssec and (_sec_get(ssec, "Projectile") or _sec_get(ssec, "Warhead")):
                    kind = "weapon"
                elif ssec and _sec_get(ssec, "Strength") is not None:
                    kind = "unit"
            except Exception:
                pass
            dname = _display_of(project, src)
            child = _node(
                kind, src, field=it.get("field") or "", exists=ex, extra=dname
            )
            child["role"] = role
            grp["children"].append(child)
            total += 1
        root["children"].append(grp)
        if total >= max_sources:
            break
    return root
