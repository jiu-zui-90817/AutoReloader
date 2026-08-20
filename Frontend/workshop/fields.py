"""
战术工坊：树分类标签 + 下拉默认值。
字段中文解释不再写死在这里，统一读 shared/schemas/common_flags.json
（与编辑器共用）。
"""

from __future__ import annotations

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

# 常见键优先排序（其余按原文件顺序跟在后面）
PREFERRED_KEYS = [
    "UIName", "Name", "Image", "Category",
    "Strength", "Armor", "Cost", "Soylent", "Points", "TechLevel",
    "Primary", "Secondary", "ElitePrimary", "EliteSecondary",
    "OccupyWeapon", "EliteOccupyWeapon",
    "Damage", "ROF", "Range", "Projectile", "Warhead",
    "Speed", "Sight", "ROT", "Locomotor",
    "Owner", "Prerequisite",
    "SelfHealing", "RadarInvisible", "OpportunityFire",
    "Passengers", "Crusher", "OmniCrushResistant",
]

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
