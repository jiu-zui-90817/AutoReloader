"""
战术工坊字段表：对齐旧版可调项，但 UI 用新版纵排（无分组框）。
每项: (ini键, 显示标签, entry|combo, Codex源名或None)
"""

from __future__ import annotations

TREE_ORDER = [
    ("Infantry", "步兵"),
    ("Vehicle", "载具"),
    ("Aircraft", "飞行器"),
    ("Building", "建筑"),
    ("Weapons", "武器"),
    ("Warheads", "弹头"),
]

FORM_UNITS = [
    ("Strength", "生命值 (Strength)", "entry", None),
    ("Armor", "装甲类型 (Armor)", "combo", "Armors"),
    ("Image", "模型换皮 (Image)", "combo", "DYNAMIC_IMAGE"),
    ("SelfHealing", "自动回血 (SelfHealing)", "combo", "Booleans"),
    ("RadarInvisible", "雷达隐形 (RadarInvisible)", "combo", "Booleans"),
    ("Primary", "主武器 (Primary)", "combo", "WeaponList"),
    ("Secondary", "副武器 (Secondary)", "combo", "WeaponList"),
    ("ElitePrimary", "精英主武 (ElitePrimary)", "combo", "WeaponList"),
    ("EliteSecondary", "精英副武 (EliteSecondary)", "combo", "WeaponList"),
    ("OccupyWeapon", "进驻武器 (OccupyWeapon)", "combo", "WeaponList"),
    ("EliteOccupyWeapon", "精英进驻 (EliteOccupy)", "combo", "WeaponList"),
    ("OpportunityFire", "移动开火 (Opp.Fire)", "combo", "Booleans"),
    ("Sight", "视野范围 (Sight)", "entry", None),
    ("Speed", "移动速度 (Speed)", "entry", None),
    ("ROT", "转身速度 (ROT)", "entry", None),
    ("Locomotor", "移动引擎 (Locomotor)", "combo", "Locomotors"),
    ("Passengers", "载客数量 (Passengers)", "entry", None),
    ("Crusher", "允许碾压步兵 (Crusher)", "combo", "Booleans"),
    ("OmniCrushResistant", "免疫巨型碾压 (OmniCrushResistant)", "combo", "Booleans"),
    ("EMP.Threshold", "EMP瘫痪抗性 (EMP.Threshold)", "entry", None),
    ("AEPreset_Passive", "💡 套用现成光环", "combo", "Presets_Passive"),
    ("AttachEffect.Animation", "状态绑定动画", "combo", "AnimList"),
    ("AttachEffect.Duration", "持续时长 (填-1为永久)", "entry", None),
    ("AttachEffect.InitialDelay", "生效延迟 (0立刻)", "entry", None),
    ("AttachEffect.Delay", "冷却时间 (负值不重置)", "entry", None),
    ("AttachEffect.DiscardOnEntry", "进入建筑/载具时失效", "combo", "Booleans"),
    ("AttachEffect.Cloakable", "赋予隐形能力", "combo", "Booleans"),
    ("AttachEffect.SpeedMultiplier", "移速倍率", "entry", None),
    ("AttachEffect.ArmorMultiplier", "护甲倍率", "entry", None),
    ("AttachEffect.FirepowerMultiplier", "伤害倍率", "entry", None),
    ("AttachEffect.ROFMultiplier", "攻击间隔倍率", "entry", None),
]

RULES_UNITS = {
    "OccupyWeapon": ["Infantry"],
    "EliteOccupyWeapon": ["Infantry"],
    "OpportunityFire": ["Vehicle", "Aircraft"],
    "Passengers": ["Vehicle", "Aircraft", "Building"],
    "Crusher": ["Vehicle"],
    "ROT": ["Vehicle", "Aircraft"],
}

FORM_WEAPONS = [
    ("Damage", "伤害值 (Damage)", "entry", None),
    ("ROF", "开火间隔/射速 (ROF)", "entry", None),
    ("Range", "射程 (Range)", "entry", None),
    ("MinimumRange", "最小射程 (MinRange)", "entry", None),
    ("Projectile", "抛射体引擎 (Projectile)", "entry", None),
    ("Speed", "弹道飞行速度 (Speed)", "entry", None),
    ("Warhead", "弹头绑定 (Warhead)", "combo", "WarheadList"),
    ("Report", "开火音效 (Report)", "entry", None),
    ("Anim", "枪口动画 (Anim)", "combo", "AnimList"),
]

FORM_WARHEADS = [
    ("CellSpread", "爆炸波及格数 (CellSpread)", "entry", None),
    ("PercentAtMax", "边缘伤害衰减 (PercentAtMax)", "entry", None),
    ("Verses", "对全装甲伤害比例 (Verses)", "entry", None),
    ("WallAbsoluteDestroyer", "强制摧毁围墙", "combo", "Booleans"),
    ("InfDeath", "步兵死亡特效类型 (InfDeath)", "entry", None),
    ("Rocker", "爆炸震荡屏幕 (Rocker)", "combo", "Booleans"),
    ("MindControl", "心灵控制 (MindControl)", "combo", "Booleans"),
    ("Parasite", "寄生蜘蛛 (Parasite)", "combo", "Booleans"),
    ("AEPreset_Attack", "💡 套用现成打击方案", "combo", "Presets_Attack"),
    ("AttachEffect.Animation", "受击特效动画", "combo", "AnimList"),
    ("AttachEffect.Duration", "状态附着时长 (1秒≈15帧)", "entry", None),
    ("AttachEffect.Cumulative", "允许多次叠加", "combo", "Booleans"),
    ("AttachEffect.AnimResetOnReapply", "重复命中重置动画", "combo", "Booleans"),
    ("AttachEffect.ForceDecloak", "命中强制破隐", "combo", "Booleans"),
    ("AttachEffect.SpeedMultiplier", "移速倍率 (0定身)", "entry", None),
    ("AttachEffect.ArmorMultiplier", "护甲倍率", "entry", None),
    ("AttachEffect.FirepowerMultiplier", "伤害倍率", "entry", None),
    ("AttachEffect.ROFMultiplier", "射速因数", "entry", None),
]
