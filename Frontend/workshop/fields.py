"""
战术工坊默认快调字段（优先显示）+ 引用下拉来源。
其余键从 section 动态补全。
"""

from __future__ import annotations

PRIORITY_UNIT = [
    "UIName", "Name", "Image", "Strength", "Armor", "Category", "TechLevel",
    "Cost", "Points", "Owner", "Prerequisite", "Primary", "Secondary",
    "ElitePrimary", "EliteSecondary", "Sight", "Speed", "ROT", "Locomotor",
    "SelfHealing", "RadarInvisible", "OpportunityFire", "Passengers", "Crusher",
    "OmniCrushResistant",
    "AttachEffect.Animation", "AttachEffect.Duration", "AttachEffect.InitialDelay",
    "AttachEffect.Delay", "AttachEffect.SpeedMultiplier", "AttachEffect.ArmorMultiplier",
    "AttachEffect.FirepowerMultiplier", "AttachEffect.ROFMultiplier",
    "AttachEffect.Cloakable", "AttachEffect.DiscardOnEntry",
]

PRIORITY_WEAPON = [
    "Damage", "ROF", "Range", "MinimumRange", "Projectile", "Speed",
    "Warhead", "Report", "Anim",
]

PRIORITY_WARHEAD = [
    "CellSpread", "PercentAtMax", "Verses", "WallAbsoluteDestroyer",
    "InfDeath", "Rocker", "MindControl", "Parasite",
    "AttachEffect.Animation", "AttachEffect.Duration", "AttachEffect.Cumulative",
    "AttachEffect.SpeedMultiplier", "AttachEffect.ArmorMultiplier",
    "AttachEffect.FirepowerMultiplier", "AttachEffect.ROFMultiplier",
    "AttachEffect.ForceDecloak",
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
}

REF_KEYS = {
    "primary": "WeaponTypes",
    "secondary": "WeaponTypes",
    "eliteprimary": "WeaponTypes",
    "elitesecondary": "WeaponTypes",
    "occupyweapon": "WeaponTypes",
    "eliteoccupyweapon": "WeaponTypes",
    "warhead": "Warheads",
    "projectile": "ProjectileTypes",
    "armor": "_armors",
    "locomotor": "_locomotors",
}

DEFAULT_ARMORS = ["none", "flak", "plate", "light", "medium", "heavy", "wood", "steel", "concrete"]
DEFAULT_LOCOMOTORS = [
    "{4A582744-9839-11d1-B709-00A024D04B5C}",
    "{4A582746-9839-11d1-B709-00A024D04B5C}",
    "{4A582741-9839-11d1-B709-00A024D04B5C}",
    "{4A582742-9839-11d1-B709-00A024D04B5C}",
    "{4A582743-9839-11d1-B709-00A024D04B5C}",
    "{4A582745-9839-11d1-B709-00A024D04B5C}",
]
BOOLISH = {"yes", "no", "true", "false", "1", "0"}


def priority_for(group: str) -> list:
    g = group.lower()
    if "weapon" in g:
        return list(PRIORITY_WEAPON)
    if "warhead" in g:
        return list(PRIORITY_WARHEAD)
    return list(PRIORITY_UNIT)


def ordered_keys(keys: dict, group: str) -> list:
    pri = priority_for(group)
    lower_map = {k.lower(): k for k in keys}
    ordered, seen = [], set()
    for pk in pri:
        if pk.lower() in lower_map:
            real = lower_map[pk.lower()]
            ordered.append(real)
            seen.add(real.lower())
    for k in keys:
        if k.lower() not in seen:
            ordered.append(k)
    return ordered
