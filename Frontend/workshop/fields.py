"""
战术工坊快调字段（经典分组 + 中文标签）。
对象树统一展示全部类型；选中后按 group 选对应 FORM。
"""

from __future__ import annotations

# (ini_key, 中文标签, entry|combo, 选项源)
FORM_UNITS = [
    ("基础生存与外观 (Base & Visuals)", [
        ("Strength", "生命值 (Strength)", "entry", None),
        ("Cost", "造价 (Cost)", "entry", None),
        ("TechLevel", "科技等级 (TechLevel)", "entry", None),
        ("Armor", "装甲类型 (Armor)", "combo", "_armors"),
        ("Image", "模型换皮 (Image)", "combo", "_images"),
        ("SelfHealing", "自动回血 (SelfHealing)", "combo", "bool"),
        ("RadarInvisible", "雷达隐形 (RadarInvisible)", "combo", "bool"),
    ]),
    ("武器火控 (Combat)", [
        ("Primary", "主武器 (Primary)", "combo", "WeaponTypes"),
        ("Secondary", "副武器 (Secondary)", "combo", "WeaponTypes"),
        ("ElitePrimary", "精英主武 (ElitePrimary)", "combo", "WeaponTypes"),
        ("EliteSecondary", "精英副武 (EliteSecondary)", "combo", "WeaponTypes"),
        ("OccupyWeapon", "进驻武器 (OccupyWeapon)", "combo", "WeaponTypes"),
        ("EliteOccupyWeapon", "精英进驻 (EliteOccupy)", "combo", "WeaponTypes"),
        ("OpportunityFire", "移动开火 (Opp.Fire)", "combo", "bool"),
        ("Sight", "视野范围 (Sight)", "entry", None),
    ]),
    ("机动与战术 (Mobility & Tactics)", [
        ("Speed", "移动速度 (Speed)", "entry", None),
        ("ROT", "转身速度 (ROT)", "entry", None),
        ("Locomotor", "移动引擎 (Locomotor)", "combo", "_locomotors"),
        ("Passengers", "载客数量 (Passengers)", "entry", None),
        ("Crusher", "允许碾压步兵 (Crusher)", "combo", "bool"),
        ("OmniCrushResistant", "免疫巨型碾压 (OmniCrushResistant)", "combo", "bool"),
        ("EMP.Threshold", "EMP瘫痪抗性 (EMP.Threshold)", "entry", None),
    ]),
    ("单位专属光环 (Ares AttachEffect)", [
        ("AttachEffect.Animation", "状态绑定动画", "combo", "Animations"),
        ("AttachEffect.Duration", "持续时长 (填-1为永久)", "entry", None),
        ("AttachEffect.InitialDelay", "生效延迟 (0为立刻生效)", "entry", None),
        ("AttachEffect.Delay", "冷却时间 (负值为不重置)", "entry", None),
        ("AttachEffect.DiscardOnEntry", "进入建筑/载具时失效", "combo", "bool"),
        ("AttachEffect.Cloakable", "赋予隐形能力", "combo", "bool"),
        ("AttachEffect.TemporalHidesAnim", "超时空冻结不隐藏动画", "combo", "bool"),
        ("AttachEffect.SpeedMultiplier", "移速倍率 (1为不变, >1加速)", "entry", None),
        ("AttachEffect.ArmorMultiplier", "护甲倍率 (1不变, <1减伤, >1变脆)", "entry", None),
        ("AttachEffect.FirepowerMultiplier", "伤害倍率 (1不变, >1增伤)", "entry", None),
        ("AttachEffect.ROFMultiplier", "攻击间隔 (1不变, <1射速变快)", "entry", None),
    ]),
]

FORM_WEAPONS = [
    ("火力与毁伤 (Firepower)", [
        ("Damage", "伤害值 (Damage)", "entry", None),
        ("ROF", "开火间隔/射速 (ROF)", "entry", None),
        ("Range", "射程 (Range)", "entry", None),
        ("MinimumRange", "最小射程 (MinRange)", "entry", None),
    ]),
    ("弹道与特效 (Ballistics)", [
        ("Projectile", "抛射体引擎 (Projectile)", "combo", "ProjectileTypes"),
        ("Speed", "弹道飞行速度 (Speed)", "entry", None),
        ("Warhead", "弹头绑定 (Warhead)", "combo", "Warheads"),
        ("Report", "开火音效 (Report)", "entry", None),
        ("Anim", "枪口动画 (Anim)", "combo", "Animations"),
    ]),
]

FORM_WARHEADS = [
    ("破坏与装甲穿透 (Damage & Armor)", [
        ("CellSpread", "爆炸波及格数 (CellSpread)", "entry", None),
        ("PercentAtMax", "边缘伤害衰减 (PercentAtMax)", "entry", None),
        ("Verses", "对全装甲伤害比例(极长,慎改)", "entry", None),
        ("WallAbsoluteDestroyer", "强制摧毁围墙 (WallDestroyer)", "combo", "bool"),
    ]),
    ("特殊伤害效果 (Status Effects)", [
        ("InfDeath", "步兵死亡特效类型 (InfDeath)", "entry", None),
        ("Rocker", "爆炸震荡屏幕 (Rocker)", "combo", "bool"),
        ("MindControl", "心灵控制 (MindControl)", "combo", "bool"),
        ("Parasite", "寄生蜘蛛 (Parasite)", "combo", "bool"),
    ]),
    ("武器打击效果 (Ares AttachEffect)", [
        ("AttachEffect.Animation", "受击特效动画", "combo", "Animations"),
        ("AttachEffect.Duration", "状态附着时长 (1秒=15帧)", "entry", None),
        ("AttachEffect.Cumulative", "允许多次叠加效果", "combo", "bool"),
        ("AttachEffect.AnimResetOnReapply", "重复命中时重置动画", "combo", "bool"),
        ("AttachEffect.ForceDecloak", "命中强制破除隐形", "combo", "bool"),
        ("AttachEffect.SpeedMultiplier", "移速倍率 (0为定身, 0.5减半)", "entry", None),
        ("AttachEffect.ArmorMultiplier", "护甲倍率 (1.5为破甲/受伤增加)", "entry", None),
        ("AttachEffect.FirepowerMultiplier", "伤害倍率 (0为缴械哑火)", "entry", None),
        ("AttachEffect.ROFMultiplier", "射速因数 (2.0为开火变慢)", "entry", None),
    ]),
]

# 对象树展示顺序（全部挂在同一棵树上）
TREE_ORDER = [
    "InfantryTypes",
    "VehicleTypes",
    "AircraftTypes",
    "BuildingTypes",
    "WeaponTypes",
    "Warheads",
    "ProjectileTypes",
    "SuperWeaponTypes",
]

GROUP_LABELS = {
    "InfantryTypes": "步兵",
    "VehicleTypes": "载具",
    "AircraftTypes": "飞行器",
    "BuildingTypes": "建筑",
    "WeaponTypes": "武器",
    "Warheads": "弹头",
    "ProjectileTypes": "抛射体",
    "SuperWeaponTypes": "超武",
    "Animations": "动画",
}

DEFAULT_ARMORS = [
    "none", "flak", "plate", "light", "medium", "heavy",
    "wood", "steel", "concrete", "special_1", "special_2",
]
DEFAULT_LOCOMOTORS = [
    "{4A582744-9839-11d1-B709-00A024D04B5C}",
    "{4A582746-9839-11d1-B709-00A024D04B5C}",
    "{4A582741-9839-11d1-B709-00A024D04B5C}",
    "{4A582742-9839-11d1-B709-00A024D04B5C}",
    "{4A582743-9839-11d1-B709-00A024D04B5C}",
    "{4A582745-9839-11d1-B709-00A024D04B5C}",
]

BOOLISH = {"yes", "no", "true", "false", "1", "0"}


def form_for_group(group: str):
    """根据对象树分组选预设表单。"""
    g = (group or "").lower()
    if "weapon" in g:
        return FORM_WEAPONS
    if "warhead" in g:
        return FORM_WARHEADS
    if "projectile" in g:
        return FORM_WEAPONS
    return FORM_UNITS
