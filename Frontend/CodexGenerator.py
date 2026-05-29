import json
import os

TRANSLATE_FILE = "NameList.txt"  
RULES_FILE = "rulesmo.ini"       
OUTPUT_FILE = "Codex_ZH.json"    

BASE_CODEX = {
    "Armors": { "none": "无装甲", "flak": "防弹衣", "light": "轻型装甲", "medium": "中型装甲", "heavy": "重型装甲", "wood": "木制", "steel": "钢制", "concrete": "混凝土" },
    "Locomotors": { 
        "{4A582741-9839-11D1-B709-00A024DDAFD1}": "载具驱动 (Drive)",
        "{4A582742-9839-11D1-B709-00A024DDAFD1}": "气垫两栖 (Hover)",
        "{4A582743-9839-11D1-B709-00A024DDAFD1}": "地底潜行 (Tunnel/Subterranean)（非载具禁用）",
        "{4A582744-9839-11D1-B709-00A024DDAFD1}": "步兵步行 (Walk)",
        "{4A582746-9839-11D1-B709-00A024DDAFD1}": "战机飞行 (Fly)",
        "{4A582747-9839-11D1-B709-00A024DDAFD1}": "超时空传送 (Teleport)",
        "{55D141B8-DB94-11D1-AC98-006008055BB5}": "机甲？ (Mech)",
        "{2BEA74E1-7CCA-11D3-BE14-00104B62A16C}": "舰船水面航行 (Ship)"
    },
    "Booleans": { "yes": "是 (开启)", "no": "否 (关闭)", "true": "是 (开启)", "false": "否 (关闭)" }
}

TAG_ZH = {
    'primary': '主武', 'secondary': '副武', 'eliteprimary': '精英主武',
    'elitesecondary': '精英副武', 'occupyweapon': '进驻', 'eliteoccupyweapon': '精英进驻'
}

COMMON_AE_ANIMS = {
    "ironfx": "铁幕无敌护盾", "forcefield": "力盾防御特效", "sphere": "超时空静止球体",
    "emp_fx": "EMP瘫痪电弧", "rad_fx": "辐射绿光污染", "sirenk": "塞壬声波护盾",
    "mininuke": "微型核爆蕈状云", "nuke": "核弹级大爆炸"
}

def parse_translation_list(filepath):
    unit_dict = {}
    current_category = "未分类部队"
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_category = line[1:-1]
                if current_category not in unit_dict: unit_dict[current_category] = {}
            elif '--' in line:
                parts = line.split('--')
                if len(parts) == 2:
                    unit_dict[current_category][parts[1].strip()] = parts[0].strip()
    return unit_dict

def parse_cnc_ini(filepath):
    ini_data = {}
    current_section = None
    with open(filepath, 'r', encoding='ansi', errors='ignore') as f:
        for line in f:
            line = line.split(';')[0].strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1].strip().lower()
                if current_section not in ini_data: ini_data[current_section] = {}
            elif '=' in line and current_section:
                key, val = line.split('=', 1)
                ini_data[current_section][key.strip().lower()] = val.strip()
    return ini_data

def generate_codex():
    if not os.path.exists(TRANSLATE_FILE) or not os.path.exists(RULES_FILE):
        print("[错误] 找不到 NameList.txt 或 rulesmo.ini！")
        return

    unit_dict = parse_translation_list(TRANSLATE_FILE)
    rules_data = parse_cnc_ini(RULES_FILE)
    
    infantry_list = [v.strip().lower() for k, v in rules_data.get('infantrytypes', {}).items()]
    vehicle_list = [v.strip().lower() for k, v in rules_data.get('vehicletypes', {}).items()]
    aircraft_list = [v.strip().lower() for k, v in rules_data.get('aircrafttypes', {}).items()]
    building_list = [v.strip().lower() for k, v in rules_data.get('buildingtypes', {}).items()]

    weapon_dict, warhead_dict = {}, {}
    weapon_list_flat, warhead_list_flat = {}, {}
    processed_weapons, processed_warheads = set(), set()
    unit_type_map = {} 
    image_dicts = { "Infantry": {}, "Vehicle": {}, "Aircraft": {}, "Building": {}, "Unknown": {} }
    armor_dict = dict(BASE_CODEX["Armors"])
    locomotor_dict = {k.upper(): v for k, v in BASE_CODEX["Locomotors"].items()}
    
    # ========================================================
    # 注入“绝对清除指令 (Nullifier)”
    # ========================================================
    presets_passive = {
        "❌ 【一键卸载】清除所有被动光环": {
            "attacheffect.animation": "none",
            "attacheffect.duration": "0",
            "attacheffect.speedmultiplier": "1",
            "attacheffect.armormultiplier": "1",
            "attacheffect.firepowermultiplier": "1",
            "attacheffect.rofmultiplier": "1",
            "attacheffect.delay": "0",
            "attacheffect.initialdelay": "0"
        }
    }
    presets_attack = {
        "❌ 【一键卸载】清除所有打击控制": {
            "attacheffect.animation": "none",
            "attacheffect.duration": "0",
            "attacheffect.speedmultiplier": "1",
            "attacheffect.armormultiplier": "1",
            "attacheffect.firepowermultiplier": "1",
            "attacheffect.rofmultiplier": "1",
            "attacheffect.cumulative": "no"
        }
    }

    eng_to_zh_map = {}
    for category, units in unit_dict.items():
        for eng_id, zh_name in units.items():
            eng_to_zh_map[eng_id.lower()] = zh_name

    anim_detective_map = {}
    for eng_id_lower, zh_name in eng_to_zh_map.items():
        if eng_id_lower in rules_data:
            props = rules_data[eng_id_lower]
            
            unit_ae_tags = {k: v for k, v in props.items() if k.startswith('attacheffect.')}
            if unit_ae_tags: presets_passive[f"【现成光环】{zh_name}"] = unit_ae_tags
            
            if 'attacheffect.animation' in props:
                anim_detective_map[props['attacheffect.animation'].lower()] = f"[{zh_name}] 出厂光环"

            for w_tag in TAG_ZH.keys():
                if w_tag in props and props[w_tag].lower() != 'none':
                    w_id_lower = props[w_tag].lower()
                    if w_id_lower in rules_data:
                        w_props = rules_data[w_id_lower]
                        if 'anim' in w_props: anim_detective_map[w_props['anim'].lower()] = f"[{zh_name}] 枪口火花"
                        
                        if 'warhead' in w_props and w_props['warhead'].lower() != 'none':
                            wh_id_lower = w_props['warhead'].lower()
                            if wh_id_lower in rules_data:
                                wh_props = rules_data[wh_id_lower]
                                
                                wh_ae_tags = {k: v for k, v in wh_props.items() if k.startswith('attacheffect.')}
                                if wh_ae_tags: presets_attack[f"【现成打击】{zh_name} (弹头:{w_props['warhead']})"] = wh_ae_tags
                                
                                if 'animlist' in wh_props:
                                    first_anim = wh_props['animlist'].split(',')[0].strip().lower()
                                    if first_anim not in anim_detective_map: anim_detective_map[first_anim] = f"[{zh_name}] 爆炸特效"
                                        
                                if 'attacheffect.animation' in wh_props:
                                    ae_anim = wh_props['attacheffect.animation'].lower()
                                    if ae_anim not in anim_detective_map: anim_detective_map[ae_anim] = f"[{zh_name}] 命中附加AE"

    anim_list_flat = {}
    if 'animations' in rules_data:
        for idx, anim_id in rules_data['animations'].items():
            anim_id_lower = anim_id.lower()
            match_found = False
            for key, translated in COMMON_AE_ANIMS.items():
                if key in anim_id_lower:
                    anim_list_flat[anim_id] = f"{anim_id} - {translated}"
                    match_found = True
                    break
            if match_found: continue
            if anim_id_lower in anim_detective_map:
                anim_list_flat[anim_id] = f"{anim_id} - {anim_detective_map[anim_id_lower]}"

    for category, units in unit_dict.items():
        if category not in weapon_dict: weapon_dict[category] = {}
        if category not in warhead_dict: warhead_dict[category] = {}
        
        for eng_id, zh_name in units.items():
            eng_id_lower = eng_id.lower() 
            if eng_id_lower in rules_data:
                props = rules_data[eng_id_lower]
                u_type = "Unknown"
                if eng_id_lower in infantry_list: u_type = "Infantry"
                elif eng_id_lower in vehicle_list: u_type = "Vehicle"
                elif eng_id_lower in aircraft_list: u_type = "Aircraft"
                elif eng_id_lower in building_list: u_type = "Building"
                unit_type_map[eng_id] = u_type 
                folder_name = f"{zh_name} 的武装"

                for w_tag, zh_tag in TAG_ZH.items():
                    if w_tag in props and props[w_tag].lower() != 'none':
                        w_id = props[w_tag]
                        w_id_lower = w_id.lower()
                        if w_id_lower not in processed_weapons:
                            processed_weapons.add(w_id_lower)
                            weapon_dict[category].setdefault(folder_name, {})[w_id] = f"{zh_tag}武器"
                            weapon_list_flat[w_id] = f"{zh_name} [{zh_tag}]"
                            
                        if w_id_lower in rules_data:
                            w_props = rules_data[w_id_lower]
                            if 'warhead' in w_props and w_props['warhead'].lower() != 'none':
                                wh_id = w_props['warhead']
                                wh_id_lower = wh_id.lower()
                                if wh_id_lower not in processed_warheads:
                                    processed_warheads.add(wh_id_lower)
                                    warhead_dict[category].setdefault(folder_name, {})[wh_id] = f"{zh_tag}弹头"
                                    warhead_list_flat[wh_id] = f"{zh_name} [{zh_tag}弹头]"

                img_id = props.get('image', eng_id) 
                image_dicts[u_type][img_id] = f"[{zh_name}] 专属模型"

                if 'armor' in props:
                    ar_id = props['armor'].lower()
                    if ar_id not in [k.lower() for k in armor_dict.keys()]: armor_dict[props['armor']] = f"特种装甲 ({props['armor']}) - [{zh_name}]"
                if 'locomotor' in props:
                    loc_id = props['locomotor'].upper() 
                    if loc_id not in locomotor_dict: locomotor_dict[loc_id] = f"未知神秘引擎 - [{zh_name}]"

        if not weapon_dict[category]: del weapon_dict[category]
        if not warhead_dict[category]: del warhead_dict[category]

    final_codex = {
        "Units": unit_dict, "Weapons": weapon_dict, "Warheads": warhead_dict,
        "WeaponList": weapon_list_flat, "WarheadList": warhead_list_flat, "AnimList": anim_list_flat, 
        
        "Presets_Passive": presets_passive,
        "Presets_Attack": presets_attack,
        
        "Armors": armor_dict, "Locomotors": locomotor_dict, "Booleans": BASE_CODEX["Booleans"],
        "UnitTypeMap": unit_type_map, "InfantryImages": image_dicts["Infantry"],
        "VehicleImages": image_dicts["Vehicle"], "AircraftImages": image_dicts["Aircraft"],
        "BuildingImages": image_dicts["Building"], "UnknownImages": image_dicts["Unknown"]
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_codex, f, ensure_ascii=False, indent=2)
        print(f"[完成] 提取完毕！")

if __name__ == "__main__":
    generate_codex()
