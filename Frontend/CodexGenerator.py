import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import os
import sys
import glob

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

# ========================================================
# 全局配置与静态字典
# ========================================================
TRANSLATE_FILE = "NameList.txt"  
RULES_FILE = "rulesmo.ini"       
OUTPUT_FILE = "Codex_ZH.json"    
EXTRA_UNITS_FILE = "扩展单位_Export.txt"   # 扩展单位导出文件

BASE_CODEX = {
    "Armors": { "none": "无装甲", "flak": "防弹衣", "light": "轻型装甲", "medium": "中型装甲", "heavy": "重型装甲", "wood": "木制", "steel": "钢制", "concrete": "混凝土" },
    "Locomotors": { 
        "{4A582741-9839-11D1-B709-00A024DDAFD1}": "载具驱动 (Drive)",
        "{4A582742-9839-11D1-B709-00A024DDAFD1}": "气垫两栖 (Hover)",
        "{4A582743-9839-11D1-B709-00A024DDAFD1}": "地底潜行 (Tunnel)（非载具禁用）",
        "{4A582744-9839-11D1-B709-00A024DDAFD1}": "步兵步行 (Walk)",
        "{4A582746-9839-11D1-B709-00A024DDAFD1}": "战机飞行 (Fly)",
        "{4A582747-9839-11D1-B709-00A024DDAFD1}": "超时空传送 (Teleport)",
        "{55D141B8-DB94-11D1-AC98-006008055BB5}": "机甲？ (Mech)",
        "{2BEA74E1-7CCA-11D3-BE14-00104B62A16C}": "舰船水面航行 (Ship)"
    },
    "Booleans": { "yes": "是 (开启)", "no": "否 (关闭)", "true": "是 (开启)", "false": "否 (关闭)" }
}

TAG_ZH = { 'primary': '主武', 'secondary': '副武', 'eliteprimary': '精英主武', 'elitesecondary': '精英副武', 'occupyweapon': '进驻', 'eliteoccupyweapon': '精英进驻' }

COMMON_AE_ANIMS = {
    "ironfx": "铁幕无敌护盾", "forcefield": "力盾防御特效", "sphere": "超时空静止球体",
    "emp_fx": "EMP瘫痪电弧", "rad_fx": "辐射绿光污染", "sirenk": "塞壬声波护盾",
    "mininuke": "微型核爆蕈状云", "nuke": "核弹级大爆炸"
}

# ========================================================
# 纯 Python 底层二进制 CSF 解析器
# ========================================================
def parse_csf_binary(filepath, log_func):
    csf_dict = {}
    try:
        with open(filepath, 'rb') as f:
            header = f.read(24)
            magic = header[:4]
            if magic != b' FSC': 
                log_func(f"[CSF] 格式拦截：{filepath} 的头部是 {magic}，跳过该文件。")
                return {}
            
            num_labels = int.from_bytes(header[8:12], 'little')
            log_func(f"[CSF] 接入 {filepath}，正在解码 {num_labels} 个原生词条...")
            
            for _ in range(num_labels):
                lbl_magic = f.read(4)
                if lbl_magic != b' LBL': break
                num_strs = int.from_bytes(f.read(4), 'little')
                name_len = int.from_bytes(f.read(4), 'little')
                lbl_name = f.read(name_len).decode('ascii', errors='ignore').lower()
                
                for __ in range(num_strs):
                    str_magic = f.read(4)
                    if str_magic == b' RTS':
                        str_len = int.from_bytes(f.read(4), 'little')
                        raw_data = f.read(str_len * 2)
                        decoded_chars = [chr((~int.from_bytes(raw_data[i*2:i*2+2], 'little')) & 0xFFFF) for i in range(str_len)]
                        csf_dict[lbl_name] = "".join(decoded_chars)
                    elif str_magic == b'WRTS':
                        str_len = int.from_bytes(f.read(4), 'little')
                        raw_data = f.read(str_len * 2)
                        extra_data_len = int.from_bytes(f.read(4), 'little')
                        f.read(extra_data_len) 
                        decoded_chars = [chr((~int.from_bytes(raw_data[i*2:i*2+2], 'little')) & 0xFFFF) for i in range(str_len)]
                        csf_dict[lbl_name] = "".join(decoded_chars)
        return csf_dict
    except Exception as e:
        log_func(f"[CSF] 解析异常: {e}")
        return {}

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

# 单文件解析（供 include 调用）
def parse_single_ini(filepath):
    ini_data = {}
    current_section = None
    try:
        with open(filepath, 'r', encoding='ansi', errors='ignore') as f:
            for line in f:
                line = line.split(';')[0].strip()
                if not line: continue
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].strip().lower()
                    if current_section not in ini_data:
                        ini_data[current_section] = {}
                elif '=' in line and current_section:
                    key, val = line.split('=', 1)
                    ini_data[current_section][key.strip().lower()] = val.strip()
    except Exception as e:
        print(f"解析 {filepath} 出错: {e}")
    return ini_data

# ========================================================
# 支持 ARES #include 的 ini 解析器（多文件合并）
# ========================================================
def parse_cnc_ini_with_includes(main_filepath, log_func=None):
    base_dir = os.path.dirname(main_filepath) or '.'
    total_data = {}
    processed_files = set()

    def load_file(filepath, depth=0):
        abs_path = os.path.join(base_dir, filepath) if not os.path.isabs(filepath) else filepath
        abs_path = os.path.normpath(abs_path)
        if abs_path in processed_files:
            if log_func:
                log_func(f"[加载] 跳过重复文件: {abs_path}")
            return
        processed_files.add(abs_path)

        if log_func:
            log_func(f"[加载] 正在解析: {abs_path}")
        data = parse_single_ini(abs_path)

        # 合并到总数据中（后加载的覆盖先加载的）
        for section, kv in data.items():
            if section not in total_data:
                total_data[section] = {}
            total_data[section].update(kv)

        # 处理 [#include] 节
        include_section = data.get('#include', {})
        include_files = []
        for k, v in include_section.items():
            k_lower = k.lower()
            if k_lower == 'include' or k_lower.startswith('include'):
                include_files.append(v)
            elif k.isdigit():
                include_files.append(v)
        # 去重保持顺序
        seen = set()
        unique_include = []
        for f in include_files:
            if f not in seen:
                seen.add(f)
                unique_include.append(f)
        for inc_file in unique_include:
            load_file(inc_file, depth+1)

    load_file(main_filepath)
    if log_func:
        log_func(f"[加载] 共合并 {len(processed_files)} 个规则文件")
    return total_data


class CodexApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MO 战术工坊 - 词典编译器 (Codex Engine)")
        self.root.geometry("650x450")
        # 兼容打包后的 sv_ttk 资源缺失问题
        if sv_ttk:
            try:
                sv_ttk.set_theme("dark")
            except Exception:
                # 打包后可能缺少资源文件，静默使用默认主题
                pass
        self.setup_ui()

    def setup_ui(self):
        top_frame = tk.Frame(self.root, padx=15, pady=10)
        top_frame.pack(fill=tk.X)
        tk.Label(top_frame, text="⚙️ Codex 核心词典构建引擎", font=("", 14, "bold")).pack(side=tk.LEFT)
        self.btn_start = tk.Button(top_frame, text="🚀 一键扫描并生成", bg="#005f3c", fg="white", font=("", 11, "bold"), command=self.start_generation, padx=15)
        self.btn_start.pack(side=tk.RIGHT)

        log_frame = tk.Frame(self.root, padx=15, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, bg="#0a0a0a", fg="#00ff00", font=("Consolas", 10), state=tk.DISABLED)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=15, pady=(0, 15))

        self.log("系统就绪。准备扫描目录下的底包数据...")
        self.log("提示：已支持 ARES #include 拆分规则文件，自动合并所有相关 ini。")

    def log(self, message):
        self.root.after(0, self._safe_log, message)

    def _safe_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_generation(self):
        self.btn_start.config(state=tk.DISABLED)
        self.progress.start(10)
        self.log("\n==============================================")
        self.log("[启动] 词典构建线程已启动...")
        threading.Thread(target=self.run_generator, daemon=True).start()

    def run_generator(self):
        try:
            if not os.path.exists(TRANSLATE_FILE) or not os.path.exists(RULES_FILE):
                self.log(f"[错误] 缺失核心底包：请确保 {TRANSLATE_FILE} 和 {RULES_FILE} 存在！")
                self.finish_generation(False)
                return

            self.log(f"[读取] 正在解析基础阵营框架 ({TRANSLATE_FILE})...")
            unit_dict = parse_translation_list(TRANSLATE_FILE)

            self.log(f"[读取] 正在加载主规则文件 {RULES_FILE} 及其所有 #include 拆分文件...")
            rules_data = parse_cnc_ini_with_includes(RULES_FILE, self.log)

            # 提前抓取官方大名单！
            infantry_list = [v.strip().lower() for k, v in rules_data.get('infantrytypes', {}).items()]
            vehicle_list = [v.strip().lower() for k, v in rules_data.get('vehicletypes', {}).items()]
            aircraft_list = [v.strip().lower() for k, v in rules_data.get('aircrafttypes', {}).items()]
            building_list = [v.strip().lower() for k, v in rules_data.get('buildingtypes', {}).items()]

            # --- 全目录 CSF 智能扫描与合并 ---
            csf_dict = {}
            csf_files = glob.glob("*.csf")
            
            if not csf_files:
                self.log("[跳过] 未在当前目录下检测到任何 .csf 文本库，将降级使用基础预设中文。")
            else:
                self.log(f"[扫描] 发现 {len(csf_files)} 个 CSF 文件，开始批量解析合并...")
                for csf_name in csf_files:
                    temp_dict = parse_csf_binary(csf_name, self.log)
                    if temp_dict: csf_dict.update(temp_dict)
                self.log(f"[汇总] 共计获取到 {len(csf_dict)} 条官方原版文本！")

            # --- 智能关联 CSF 中文 (针对已有骨架) ---
            self.log("[合并] 正在将 CSF 原生文本与基础名录进行量子纠缠...")
            existing_ids = set()
            for category, units in unit_dict.items():
                for eng_id in list(units.keys()):
                    existing_ids.add(eng_id.lower())
                    props = rules_data.get(eng_id.lower(), {})
                    uiname = props.get('uiname', '').lower()
                    if uiname and uiname in csf_dict: units[eng_id] = csf_dict[uiname]
                    elif eng_id.lower() in csf_dict: units[eng_id] = csf_dict[eng_id.lower()]

            # ========================================================
            # 🚨 核心新功能：全局拾荒者 (补全不在 NameList 里的单位)
            # ========================================================
            self.log("[侦测] 正在对比底层大名单，搜寻扩展单位与隐藏单位...")
            all_registered = set(infantry_list + vehicle_list + aircraft_list + building_list)
            missing_ids = all_registered - existing_ids
            
            # 用于存储扩展单位（按分类）
            missing_units_report = {"步兵": {}, "载具": {}, "飞机": {}, "建筑": {}, "未分类": {}}
            
            if missing_ids:
                self.log(f"[扩展] 发现 {len(missing_ids)} 个未注册扩展单位！正在自动检索 CSF 赋名并建立独立图册...")
                for m_id in missing_ids:
                    if m_id not in rules_data: continue
                    props = rules_data[m_id]
                    
                    # 尝试寻找名字
                    final_name = m_id.upper()
                    uiname = props.get('uiname', '').lower()
                    name_prop = props.get('name', '').lower()
                    if uiname and uiname in csf_dict: final_name = csf_dict[uiname]
                    elif name_prop and name_prop in csf_dict: final_name = csf_dict[name_prop]
                    elif m_id in csf_dict: final_name = csf_dict[m_id]
                    else: final_name = props.get('name', m_id.upper())

                    # 自动归类
                    cat_name = "【扩展】未分类图纸"
                    report_cat = "未分类"
                    if m_id in infantry_list:
                        cat_name = "🏃 【扩展】新增步兵单元"
                        report_cat = "步兵"
                    elif m_id in vehicle_list:
                        cat_name = "🚙 【扩展】新增装甲载具"
                        report_cat = "载具"
                    elif m_id in aircraft_list:
                        cat_name = "✈️ 【扩展】新增飞行单位"
                        report_cat = "飞机"
                    elif m_id in building_list:
                        cat_name = "🏢 【扩展】新增建筑群"
                        report_cat = "建筑"

                    if cat_name not in unit_dict:
                        unit_dict[cat_name] = {}
                    unit_dict[cat_name][m_id.upper()] = final_name
                    missing_units_report[report_cat][m_id.upper()] = final_name
            else:
                self.log("[扩展] 未发现额外扩展单位，所有单位均已在 NameList 中注册。")

            # ========================================================
            # 📄 导出扩展单位名单到单独文件
            # ========================================================
            if any(missing_units_report.values()):
                try:
                    with open(EXTRA_UNITS_FILE, 'w', encoding='utf-8') as f:
                        f.write("# 自动拾荒到的扩展单位列表（未在 NameList.txt 中注册）\n")
                        f.write("# 格式：中文名 = 英文ID\n\n")
                        for category, units_dict in missing_units_report.items():
                            if not units_dict:
                                continue
                            f.write(f"[{category}]\n")
                            for eng_id, zh_name in units_dict.items():
                                f.write(f"{zh_name} -- {eng_id}\n")
                            f.write("\n")
                    self.log(f"[导出] 已生成扩展单位名单文件：{EXTRA_UNITS_FILE} (共 {sum(len(v) for v in missing_units_report.values())} 条)")
                except Exception as e:
                    self.log(f"[警告] 扩展单位名单写入失败：{e}")

            # --- 构建数据结构 ---
            self.log("[构建] 正在扫描全部系统的武器/挂载/特效图纸...")
            weapon_dict, warhead_dict = {}, {}
            weapon_list_flat, warhead_list_flat = {}, {}
            processed_weapons, processed_warheads = set(), set()
            unit_type_map = {} 
            image_dicts = { "Infantry": {}, "Vehicle": {}, "Aircraft": {}, "Building": {}, "Unknown": {} }
            armor_dict = dict(BASE_CODEX["Armors"])
            locomotor_dict = {k.upper(): v for k, v in BASE_CODEX["Locomotors"].items()}

            presets_passive = {
                "❌ 【一键卸载】清除所有被动光环": {
                    "attacheffect.animation": "none", "attacheffect.duration": "0",
                    "attacheffect.speedmultiplier": "1", "attacheffect.armormultiplier": "1",
                    "attacheffect.firepowermultiplier": "1", "attacheffect.rofmultiplier": "1",
                    "attacheffect.delay": "0", "attacheffect.initialdelay": "0"
                }
            }
            presets_attack = {
                "❌ 【一键卸载】清除所有打击控制": {
                    "attacheffect.animation": "none", "attacheffect.duration": "0",
                    "attacheffect.speedmultiplier": "1", "attacheffect.armormultiplier": "1",
                    "attacheffect.firepowermultiplier": "1", "attacheffect.rofmultiplier": "1",
                    "attacheffect.cumulative": "no"
                }
            }

            eng_to_zh_map = {eng_id.lower(): zh_name for units in unit_dict.values() for eng_id, zh_name in units.items()}
            anim_detective_map = {}
            for eng_id_lower, zh_name in eng_to_zh_map.items():
                if eng_id_lower in rules_data:
                    props = rules_data[eng_id_lower]
                    unit_ae_tags = {k: v for k, v in props.items() if k.startswith('attacheffect.')}
                    if unit_ae_tags: presets_passive[f"【光环】{zh_name}"] = unit_ae_tags
                    if 'attacheffect.animation' in props: anim_detective_map[props['attacheffect.animation'].lower()] = f"[{zh_name}] 出厂光环"

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
                                        if wh_ae_tags: presets_attack[f"【打击】{zh_name}"] = wh_ae_tags
                                        if 'animlist' in wh_props:
                                            first_anim = wh_props['animlist'].split(',')[0].strip().lower()
                                            if first_anim not in anim_detective_map: anim_detective_map[first_anim] = f"[{zh_name}] 爆炸特效"
                                        if 'attacheffect.animation' in wh_props:
                                            ae_anim = wh_props['attacheffect.animation'].lower()
                                            if ae_anim not in anim_detective_map: anim_detective_map[ae_anim] = f"[{zh_name}] 附加AE"

            anim_list_flat = {}
            if 'animations' in rules_data:
                for idx, anim_id in rules_data['animations'].items():
                    anim_id_lower = anim_id.lower()
                    match_found = False
                    for key, translated in COMMON_AE_ANIMS.items():
                        if key in anim_id_lower:
                            anim_list_flat[anim_id] = f"{anim_id} - {translated}"
                            match_found = True; break
                    if match_found: continue
                    if anim_id_lower in anim_detective_map: anim_list_flat[anim_id] = f"{anim_id} - {anim_detective_map[anim_id_lower]}"

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
                                    
                                    w_zh_name = zh_name
                                    if w_id_lower in rules_data:
                                        w_props = rules_data[w_id_lower]
                                        w_uiname = w_props.get('uiname', '').lower()
                                        if w_uiname and w_uiname in csf_dict: w_zh_name = csf_dict[w_uiname]
                                        elif w_props.get('name', '').lower() in csf_dict: w_zh_name = csf_dict[w_props['name'].lower()]
                                    
                                    weapon_list_flat[w_id] = f"{w_zh_name} [{zh_tag}]"
                                    
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
                        image_dicts[u_type][img_id] = f"[{zh_name}] 模型"

                        if 'armor' in props:
                            ar_id = props['armor'].lower()
                            if ar_id not in [k.lower() for k in armor_dict.keys()]: armor_dict[props['armor']] = f"特种装甲 ({props['armor']})"
                        if 'locomotor' in props:
                            loc_id = props['locomotor'].upper() 
                            if loc_id not in locomotor_dict: locomotor_dict[loc_id] = f"未知引擎 ({loc_id})"

                if not weapon_dict[category]: del weapon_dict[category]
                if not warhead_dict[category]: del warhead_dict[category]

            final_codex = {
                "Units": unit_dict, "Weapons": weapon_dict, "Warheads": warhead_dict,
                "WeaponList": weapon_list_flat, "WarheadList": warhead_list_flat, "AnimList": anim_list_flat, 
                "Presets_Passive": presets_passive, "Presets_Attack": presets_attack,
                "Armors": armor_dict, "Locomotors": locomotor_dict, "Booleans": BASE_CODEX["Booleans"],
                "UnitTypeMap": unit_type_map, "InfantryImages": image_dicts["Infantry"],
                "VehicleImages": image_dicts["Vehicle"], "AircraftImages": image_dicts["Aircraft"],
                "BuildingImages": image_dicts["Building"], "UnknownImages": image_dicts["Unknown"]
            }
            
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(final_codex, f, ensure_ascii=False, indent=2)
                
            self.log(f"\n[大功告成] 所有编译步骤完成！已生成词典：{OUTPUT_FILE}")
            self.finish_generation(True)

        except Exception as e:
            self.log(f"\n[致命错误] 发生崩溃: {str(e)}")
            self.finish_generation(False)

    def finish_generation(self, success):
        self.root.after(0, self._safe_finish, success)

    def _safe_finish(self, success):
        self.progress.stop()
        self.btn_start.config(state=tk.NORMAL)
        if success:
            messagebox.showinfo("编译完成", "✅ Codex 词典已生成完毕！\n同时已导出扩展单位列表（扩展单位_Export.txt）")

if __name__ == "__main__":
    root = tk.Tk()
    app = CodexApp(root)
    root.mainloop()
