import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys
import time
try:
    import sv_ttk
except ImportError:
    sv_ttk = None

# ========================================================
# 🚀 0. 引擎安全启动与字典加载
# ========================================================
root = tk.Tk()
root.withdraw() 

CODEX_FILE = "Codex_ZH.json"
RULES_FILE = "rulesmo.ini"  
base_rules_data = {}        
last_file_mtime = 0  

if not os.path.exists(CODEX_FILE):
    messagebox.showerror("致命错误", f"找不到核心武器库：{CODEX_FILE}")
    sys.exit()

try:
    with open(CODEX_FILE, "r", encoding="utf-8") as f: 
        codex = json.load(f)
except Exception as e:
    messagebox.showerror("致命错误", f"解析 {CODEX_FILE} 失败！\n\n报错信息: {str(e)}")
    sys.exit()

def parse_cnc_ini(filepath):
    ini_data = {}
    current_section = None
    try:
        with open(filepath, 'r', encoding='ansi', errors='ignore') as f:
            for line in f:
                line = line.split(';')[0].strip()
                if not line: continue
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    if current_section not in ini_data: ini_data[current_section] = {}
                elif '=' in line and current_section:
                    key, val = line.split('=', 1)
                    ini_data[current_section][key.strip()] = val.strip()
    except Exception: pass
    return ini_data

if os.path.exists(RULES_FILE):
    base_rules_data = parse_cnc_ini(RULES_FILE)
    print(f"[引擎挂载] 成功读取本地 {RULES_FILE}，引擎待命中！")

root.deiconify()
root.title("MO 战术工坊")
root.geometry("1180x800") 
if sv_ttk: sv_ttk.set_theme("dark")

try:
    root.iconbitmap("app_icon.ico")
except Exception: pass

# ========================================================
# 🎨 1. 兵器谱图纸全量字典
# ========================================================
FORM_UNITS = [
    ("基础生存与外观 (Base & Visuals)", [
        ("Strength", "生命值 (Strength)", "entry", None),
        ("Cost", "造价 (Cost)", "entry", None),
        ("TechLevel", "科技等级 (TechLevel)", "entry", None),
        ("Armor", "装甲类型 (Armor)", "combo", "Armors"),
        ("Image", "模型换皮 (Image)", "combo", "DYNAMIC_IMAGE"),
        ("SelfHealing", "自动回血 (SelfHealing)", "combo", "Booleans"),
        ("RadarInvisible", "雷达隐形 (RadarInvisible)", "combo", "Booleans")
    ]),
    ("武器火控 (Combat)", [
        ("Primary", "主武器 (Primary)", "combo", "WeaponList"), 
        ("Secondary", "副武器 (Secondary)", "combo", "WeaponList"), 
        ("ElitePrimary", "精英主武 (ElitePrimary)", "combo", "WeaponList"), 
        ("EliteSecondary", "精英副武 (EliteSecondary)", "combo", "WeaponList"), 
        ("OccupyWeapon", "进驻武器 (OccupyWeapon)", "combo", "WeaponList"), 
        ("EliteOccupyWeapon", "精英进驻 (EliteOccupy)", "combo", "WeaponList"), 
        ("OpportunityFire", "移动开火 (Opp.Fire)", "combo", "Booleans"),
        ("Sight", "视野范围 (Sight)", "entry", None) 
    ]),
    ("机动与战术 (Mobility & Tactics)", [
        ("Speed", "移动速度 (Speed)", "entry", None),
        ("ROT", "转身速度 (ROT)", "entry", None), 
        ("Locomotor", "移动引擎 (Locomotor)", "combo", "Locomotors"),
        ("Passengers", "载客数量 (Passengers)", "entry", None), 
        ("Crusher", "允许碾压步兵 (Crusher)", "combo", "Booleans"),
        ("OmniCrushResistant", "免疫巨型碾压 (OmniCrushResistant)", "combo", "Booleans"), 
        ("EMP.Threshold", "EMP瘫痪抗性 (EMP.Threshold)", "entry", None) 
    ]),
    ("单位专属光环 (Ares AttachEffect) （实验性功能，不完整支持）", [
        ("AEPreset_Passive", "💡 直接套用游戏现成光环", "combo", "Presets_Passive"), 
        ("AttachEffect.Animation", "状态绑定动画", "combo", "AnimList"),
        ("AttachEffect.Duration", "持续时长 (填-1为永久)", "entry", None),
        ("AttachEffect.InitialDelay", "生效延迟 (0为立刻生效)", "entry", None),
        ("AttachEffect.Delay", "冷却时间 (负值为不重置)", "entry", None),
        ("AttachEffect.DiscardOnEntry", "进入建筑/载具时失效", "combo", "Booleans"),
        ("AttachEffect.Cloakable", "赋予隐形能力", "combo", "Booleans"),
        ("AttachEffect.TemporalHidesAnim", "超时空冻结不隐藏动画", "combo", "Booleans"),
        ("AttachEffect.SpeedMultiplier", "移速倍率 (1为不变, >1加速)", "entry", None),
        ("AttachEffect.ArmorMultiplier", "护甲倍率 (1不变, <1减伤, >1变脆)", "entry", None),
        ("AttachEffect.FirepowerMultiplier", "伤害倍率 (1不变, >1增伤)", "entry", None),
        ("AttachEffect.ROFMultiplier", "攻击间隔 (1不变, <1射速变快)", "entry", None)
    ])
]

RULES_UNITS = {
    "OccupyWeapon": ["Infantry"],         
    "EliteOccupyWeapon": ["Infantry"],    
    "OpportunityFire": ["Vehicle", "Aircraft"],
    "Passengers": ["Vehicle", "Aircraft", "Building"],
    "Crusher": ["Vehicle"],
    "ROT": ["Vehicle", "Aircraft"]
}

FORM_WEAPONS = [
    ("火力与毁伤 (Firepower)", [
        ("Damage", "伤害值 (Damage)", "entry", None),
        ("ROF", "开火间隔/射速 (ROF)", "entry", None),
        ("Range", "射程 (Range)", "entry", None),
        ("MinimumRange", "最小射程 (MinRange)", "entry", None)
    ]),
    ("弹道与特效 (Ballistics)", [
        ("Projectile", "抛射体引擎 (Projectile)", "entry", None),
        ("Speed", "弹道飞行速度 (Speed)", "entry", None),
        ("Warhead", "弹头绑定 (Warhead)", "combo", "WarheadList"), 
        ("Report", "开火音效 (Report)", "entry", None),
        ("Anim", "枪口动画 (Anim)", "combo", "AnimList")
    ])
]

FORM_WARHEADS = [
    ("破坏与装甲穿透 (Damage & Armor)", [
        ("CellSpread", "爆炸波及格数 (CellSpread)", "entry", None),
        ("PercentAtMax", "边缘伤害衰减 (PercentAtMax)", "entry", None),
        ("Verses", "⚠️对全装甲伤害比例(极长,慎改)", "entry", None), 
        ("WallAbsoluteDestroyer", "强制摧毁围墙 (WallDestroyer)", "combo", "Booleans")
    ]),
    ("特殊伤害效果 (Status Effects)", [
        ("InfDeath", "步兵死亡特效类型 (InfDeath)", "entry", None), 
        ("Rocker", "爆炸震荡屏幕 (Rocker)", "combo", "Booleans"), 
        ("MindControl", "心灵控制 (MindControl)", "combo", "Booleans"),
        ("Parasite", "寄生蜘蛛 (Parasite)", "combo", "Booleans")
    ]),
    ("武器打击效果 (Ares AttachEffect) （实验性功能，不完整支持）", [
        ("AEPreset_Attack", "💡 直接套用游戏现成打击方案", "combo", "Presets_Attack"),
        ("AttachEffect.Animation", "受击特效动画", "combo", "AnimList"),
        ("AttachEffect.Duration", "状态附着时长 (1秒=15帧)", "entry", None),
        ("AttachEffect.Cumulative", "允许多次叠加效果", "combo", "Booleans"),
        ("AttachEffect.AnimResetOnReapply", "重复命中时重置动画", "combo", "Booleans"),
        ("AttachEffect.ForceDecloak", "命中强制破除隐形", "combo", "Booleans"),
        ("AttachEffect.SpeedMultiplier", "移速倍率 (0为定身, 0.5减半)", "entry", None),
        ("AttachEffect.ArmorMultiplier", "护甲倍率 (1.5为破甲/受伤增加)", "entry", None),
        ("AttachEffect.FirepowerMultiplier", "伤害倍率 (0为缴械哑火)", "entry", None),
        ("AttachEffect.ROFMultiplier", "射速因数 (2.0为开火变慢)", "entry", None)
    ])
]

# ========================================================
# 🚀 2. 核心交互与绝对覆盖引擎
# ========================================================
target_filepath = ""
tabs_info = {} 
is_switching_unit = False 

def extract_real_id(text):
    if not text: return ""
    if " - " in text: return text.split(" - ")[0].strip()
    if " [" in text and text.endswith("]"): return text.split('[')[-1].replace(']', '').strip()
    return text.strip()

def apply_ae_preset(preset_name, t_vars):
    all_presets = {**codex.get("Presets_Passive", {}), **codex.get("Presets_Attack", {})}
    if preset_name not in all_presets: return
    
    preset_data = all_presets[preset_name]
    for key, val in preset_data.items():
        for form_key, var in t_vars.items():
            if form_key.lower() == key.lower():
                var.set(val)

def replace_ini_section(filepath, section, block_text):
    lines = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="ansi") as f: lines = f.readlines()
    
    out_lines = []
    in_sec = False
    sec_found = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_sec: in_sec = False
            if stripped[1:-1].strip().lower() == section.lower():
                in_sec = True
                sec_found = True
                out_lines.append(block_text + "\n")
                continue
        if not in_sec:
            out_lines.append(line)
            
    if not sec_found:
        if out_lines and not out_lines[-1].endswith("\n"): out_lines.append("\n")
        out_lines.append("\n" + block_text + "\n")
        
    with open(filepath, "w", encoding="ansi") as f: f.writelines(out_lines)

def on_tree_select(tab_id):
    global target_filepath, is_switching_unit
    is_switching_unit = True 
    
    tab = tabs_info[tab_id]
    sel = tab["tree"].selection()
    if not sel or not tab["tree"].item(sel[0]).get("values"): 
        is_switching_unit = False
        return
    
    obj_id = tab["tree"].item(sel[0])["values"][0]
    
    raw_lines = [f"[{obj_id}]"]
    ini_data = {} 
    if target_filepath and os.path.exists(target_filepath):
        in_sec = False
        try:
            with open(target_filepath, "r", encoding="ansi") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        if in_sec: break 
                        if stripped[1:-1].strip().lower() == obj_id.lower():
                            in_sec = True
                            continue
                    elif in_sec:
                        raw_lines.append(line.rstrip())
                        clean = line.split(';')[0].strip()
                        if '=' in clean:
                            k, v = clean.split('=', 1)
                            ini_data[k.strip().lower()] = v.strip()
        except Exception: pass
        
    txt_preview.delete("1.0", tk.END)
    txt_preview.insert(tk.END, '\n'.join(raw_lines))
    
    u_type = codex.get("UnitTypeMap", {}).get(obj_id, "Unknown")
    for group, fields in tab["form_config"]:
        for ini_key, label_text, w_type, d_name in fields:
            var = tab["vars"][ini_key]
            ctrl = tab["widgets"].get(ini_key)
            val_ini = ini_data.get(ini_key.lower(), "")
            
            rules = tab.get("rules", {})
            if rules and ini_key in rules and u_type not in rules[ini_key]:
                var.set("")
                if ctrl: ctrl.config(state="disabled")
                continue
            else:
                if ctrl: ctrl.config(state="normal")
            
            if w_type == "entry":
                var.set(val_ini)
            elif w_type == "combo":
                if d_name == "DYNAMIC_IMAGE" and ctrl:
                    img_dict = codex.get(f"{u_type}Images", {})
                    new_options = [""] + [f"{v} [{k}]" for k, v in img_dict.items()]
                    ctrl['values'] = new_options
                    ctrl.full_values = new_options 
                
                if val_ini == "": var.set("")
                else:
                    matched = next((v for v in ctrl['values'] if v.startswith(f"{val_ini} -") or v.endswith(f"[{val_ini}]") or v == val_ini), "")
                    var.set(matched if matched else val_ini)
                    
    is_switching_unit = False 

def update_preview(*args):
    if is_switching_unit: return 
    try:
        current_text = txt_preview.get("1.0", tk.END).split('\n')
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
        sel = tab["tree"].selection()
        if not sel or not tab["tree"].item(sel[0]).get("values"): return
        obj_id = tab["tree"].item(sel[0])["values"][0]
    except Exception: return

    ui_data = {}
    for ini_key, var in tab["vars"].items():
        if ini_key.startswith("AEPreset"): continue 
        ctrl = tab["widgets"].get(ini_key)
        if ctrl and str(ctrl.cget("state")) != "disabled":
            ui_data[ini_key.lower()] = (ini_key, extract_real_id(var.get()))

    new_lines = []
    ui_keys_written = set()
    
    if current_text and current_text[0].strip().startswith('['):
        new_lines.append(current_text[0].rstrip())
        lines_to_process = current_text[1:]
    else:
        new_lines.append(f"[{obj_id}]")
        lines_to_process = current_text
        
    for line in lines_to_process:
        clean_line = line.split(';')[0].strip()
        if '=' in clean_line and not clean_line.startswith('['):
            k = clean_line.split('=', 1)[0].strip().lower()
            if k in ui_data:
                ini_key, val = ui_data[k]
                if val != "": new_lines.append(f"{ini_key}={val}")
                ui_keys_written.add(k)
            else:
                new_lines.append(line.rstrip())
        else:
            if line.strip() or (new_lines and new_lines[-1].strip()):
                new_lines.append(line.rstrip())
                
    for k, (ini_key, val) in ui_data.items():
        if k not in ui_keys_written and val != "":
            new_lines.append(f"{ini_key}={val}")
            
    cursor_pos = txt_preview.index(tk.INSERT)
    scroll_y = txt_preview.yview()
    txt_preview.delete("1.0", tk.END)
    while new_lines and not new_lines[-1].strip(): new_lines.pop()
    txt_preview.insert(tk.END, '\n'.join(new_lines))
    txt_preview.mark_set(tk.INSERT, cursor_pos)
    txt_preview.yview_moveto(scroll_y[0])

def create_editor_tab(notebook_parent, tab_id, tab_text, data_dict, form_config, rules_dict=None):
    frame_bg = tk.Frame(notebook_parent)
    notebook_parent.add(frame_bg, text=tab_text)
    
    frame_tree = tk.Frame(frame_bg, padx=5, pady=5)
    frame_tree.pack(side=tk.LEFT, fill=tk.Y)
    
    tree = ttk.Treeview(frame_tree, show="tree", selectmode="browse")
    sb = ttk.Scrollbar(frame_tree, command=tree.yview)
    tree.config(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def populate_tree(parent_node, current_data):
        for k, v in current_data.items():
            if isinstance(v, dict): 
                folder = tree.insert(parent_node, tk.END, text=k, open=False)
                populate_tree(folder, v)
            else: 
                tree.insert(parent_node, tk.END, text=f"{v} [{k}]", values=(k,))
    populate_tree("", data_dict)
            
    frame_form_container = tk.Frame(frame_bg, padx=5, pady=5)
    frame_form_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    canvas = tk.Canvas(frame_form_container, highlightthickness=0)
    scrollbar_y = ttk.Scrollbar(frame_form_container, orient="vertical", command=canvas.yview)
    frame_form = tk.Frame(canvas)
    
    frame_form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
    canvas_window = canvas.create_window((0, 0), window=frame_form, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar_y.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind('<Enter>', lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all("<MouseWheel>"))

    t_vars, t_widgets = {}, {}
    for group, fields in form_config:
        lf = tk.LabelFrame(frame_form, text=group, font=("", 9, "bold"), padx=10, pady=5)
        lf.pack(fill=tk.X, pady=5, padx=5)
        for ini_key, label_text, w_type, d_name in fields:
            row = tk.Frame(lf)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label_text, width=28, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar()
            var.trace_add("write", update_preview)
            t_vars[ini_key] = var
            
            if w_type == "entry":
                ctrl = tk.Entry(row, textvariable=var)
            elif w_type == "combo":
                ctrl = ttk.Combobox(row, textvariable=var)
                if d_name == "DYNAMIC_IMAGE":
                    pass 
                elif d_name in ["Presets_Passive", "Presets_Attack"]:
                    options = [""] + list(codex.get(d_name, {}).keys())
                    ctrl['values'] = options
                    ctrl.full_values = options
                elif d_name:
                    options = [""] + [f"{k} - {v}" if k != v else k for k, v in codex.get(d_name, {}).items()]
                    ctrl['values'] = options
                    ctrl.full_values = options
                else:
                    ctrl.full_values = []
                
                def make_on_type(w):
                    def on_type(event):
                        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right", "Tab"): return
                        typed = w.get()
                        full_vals = getattr(w, 'full_values', [])
                        if not typed:
                            w['values'] = full_vals
                        else:
                            w['values'] = [v for v in full_vals if typed.lower() in v.lower()]
                    return on_type
                
                ctrl.bind("<KeyRelease>", make_on_type(ctrl))

            ctrl.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            t_widgets[ini_key] = ctrl
            
            if ini_key in ["AEPreset_Passive", "AEPreset_Attack"]:
                ctrl.bind("<<ComboboxSelected>>", lambda e, w=ctrl, v_dict=t_vars: apply_ae_preset(w.get(), v_dict))
            
    tabs_info[tab_id] = {
        "tree": tree, "vars": t_vars, "widgets": t_widgets, 
        "form_config": form_config, "rules": rules_dict
    }
    tree.bind("<<TreeviewSelect>>", lambda e: on_tree_select(tab_id))
    return frame_bg

def choose_file():
    global target_filepath, last_file_mtime
    fp = filedialog.askopenfilename(defaultextension=".ini", filetypes=[("INI", "*.ini")])
    if not fp: fp = filedialog.asksaveasfilename(defaultextension=".ini", filetypes=[("INI", "*.ini")])
    if fp:
        target_filepath = fp
        lbl_file.config(text=f"当前目标: {fp}", fg="#00ff00")
        try:
            if not os.path.exists(fp):
                with open(fp, 'w', encoding='ansi') as f: f.write("; AutoReloader Target File\n\n")
            last_file_mtime = os.path.getmtime(fp)
            current_tab_idx = notebook.index(notebook.select())
            on_tree_select(list(tabs_info.keys())[current_tab_idx])
        except Exception: pass

def clean_ini_silent():
    if not target_filepath or not os.path.exists(target_filepath) or not base_rules_data:
        return

    try:
        with open(target_filepath, "r", encoding="ansi") as f: lines = f.readlines()
        out_lines, current_sec, cleaned_count = [], None, 0

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_sec = stripped[1:-1].strip()
                out_lines.append(line)
                continue

            if current_sec and "=" in line and not stripped.startswith(";"):
                k, v = line.split("=", 1)
                base_v = next((bv for bk, bv in base_rules_data.get(current_sec, {}).items() if bk.lower() == k.strip().lower()), None)
                if base_v is not None and base_v.lower() == v.strip().lower():
                    cleaned_count += 1
                    continue 
            out_lines.append(line)

        if cleaned_count > 0:
            with open(target_filepath, "w", encoding="ansi") as f: f.writelines(out_lines)
            global last_file_mtime
            last_file_mtime = os.path.getmtime(target_filepath)
            
            try:
                current_tab_idx = notebook.index(notebook.select())
                on_tree_select(list(tabs_info.keys())[current_tab_idx])
            except Exception: pass
            print(f"后台瘦身触发完毕，静默删除了 {cleaned_count} 条代码。")
            
    except Exception as e:
        print(f"后台瘦身失败: {str(e)}")

# ========================================================
# 🚨 核心逻辑升级：绝对清除机制 (模型与 AE)
# ========================================================
def restore_default():
    if not base_rules_data:
        return messagebox.showwarning("警告", "未挂载原版 rulesmo.ini，无法获取官方默认值！")
        
    try:
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
    except Exception: return
        
    sel = tab["tree"].selection()
    if not sel or not tab["tree"].item(sel[0]).get("values"): return
    
    obj_id = tab["tree"].item(sel[0])["values"][0]
    base_props = base_rules_data.get(obj_id, {})
    
    if not base_props:
        return messagebox.showinfo("提示", "原版引擎中不存在该图纸数据。")
        
    lines = [f"[{obj_id}]"]
    base_keys_lower = {k.lower(): k for k in base_props.keys()}
    
    # 🔥 修复 1：如果没有原生 Image 标签，强制将模型指定为其 ID (防载具模型卡死)
    if "image" not in base_keys_lower:
        lines.append(f"Image={obj_id}")
        
    for k, v in base_props.items(): lines.append(f"{k}={v}")
    
    # 🔥 修复 2：如果没有原生 AE 标签，强制下发绝对清除指令 (防残留)
    has_ae = any(k.startswith("attacheffect.") for k in base_keys_lower)
    if not has_ae:
        lines.extend([
            "AttachEffect.Animation=none",
            "AttachEffect.Duration=0",
            "AttachEffect.SpeedMultiplier=1",
            "AttachEffect.ArmorMultiplier=1",
            "AttachEffect.FirepowerMultiplier=1",
            "AttachEffect.ROFMultiplier=1",
            "AttachEffect.Delay=0",
            "AttachEffect.InitialDelay=0",
            "AttachEffect.Cumulative=no"
        ])
    
    replace_ini_section(target_filepath, obj_id, '\n'.join(lines))
    
    global last_file_mtime
    last_file_mtime = os.path.getmtime(target_filepath)
    
    on_tree_select(list(tabs_info.keys())[tab_idx])
    root.after(5000, clean_ini_silent)
    messagebox.showinfo("准备就绪", f"{obj_id} 官方参数及绝对清除指令已注入！\n\n👉 5秒后将自动执行静默清理，请火速触发热重载！")

def deploy(event=None):
    if not target_filepath: return messagebox.showinfo("提示", "请先选择目标INI！")
    
    try:
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
    except Exception: return
        
    sel = tab["tree"].selection()
    if not sel or not tab["tree"].item(sel[0]).get("values"): return
    
    obj_id = tab["tree"].item(sel[0])["values"][0]
    raw_content = txt_preview.get("1.0", tk.END).strip()
    
    present_keys = set()
    for line in raw_content.split('\n'):
        clean_line = line.split(';')[0].strip()
        if '=' in clean_line and not clean_line.startswith('['):
            present_keys.add(clean_line.split('=', 1)[0].strip().lower())
            
    lines_to_add = []
    original_props = base_rules_data.get(obj_id, {})
    original_props_lower = {k.lower(): v for k, v in original_props.items()}
    
    for ini_key, var in tab["vars"].items():
        if ini_key.startswith("AEPreset"): continue 
        ctrl = tab["widgets"].get(ini_key)
        if ctrl and str(ctrl.cget("state")) != "disabled":
            if extract_real_id(var.get()) == "":
                if ini_key.lower() not in present_keys:
                    if base_rules_data and ini_key.lower() in original_props_lower:
                        lines_to_add.append(f"{ini_key}={original_props_lower[ini_key.lower()]}")
    
    final_block_text = raw_content
    if lines_to_add:
        final_block_text += "\n" + "\n".join(lines_to_add)
            
    try:
        replace_ini_section(target_filepath, obj_id, final_block_text)
        global last_file_mtime
        last_file_mtime = os.path.getmtime(target_filepath)
        if base_rules_data: root.after(5000, clean_ini_silent)
        messagebox.showinfo("保存成功", "参数已注入目标文件！(Ctrl+S)\n\n⚠️ 5秒后后台将自动蒸发冗余出厂代码，请尽快触发重载！")
    except Exception as e: messagebox.showerror("错误", str(e))

# ========================================================
# 🛡️ 3. 守护神线程 (Watchdog: 防护与双向同步)
# ========================================================
def file_watchdog():
    global last_file_mtime
    if target_filepath and os.path.exists(target_filepath):
        try:
            current_mtime = os.path.getmtime(target_filepath)
            if current_mtime > last_file_mtime:
                with open(target_filepath, 'rb+') as f:
                    f.seek(0, 2)
                    if f.tell() > 0:
                        f.seek(-1, 2)
                        if f.read(1) not in (b'\n', b'\r'):
                            f.write(b'\r\n')
                            current_mtime = os.path.getmtime(target_filepath)
                try:
                    current_tab_idx = notebook.index(notebook.select())
                    on_tree_select(list(tabs_info.keys())[current_tab_idx])
                except Exception: pass
                last_file_mtime = current_mtime
        except Exception: pass
    root.after(1000, file_watchdog)

# ========================================================
# 🚀 4. GUI 构建与挂载
# ========================================================
frame_top = tk.Frame(root, bg="#1e1e1e", padx=10, pady=10)
frame_top.pack(fill=tk.X)
tk.Button(frame_top, text="📂 选择目标文件", command=choose_file).pack(side=tk.LEFT)
lbl_file = tk.Label(frame_top, text="当前目标: 未选择", bg="#1e1e1e", fg="red", font=("", 10, "bold"))
lbl_file.pack(side=tk.LEFT, padx=15)

tk.Button(frame_top, text="💾 部署 (Ctrl+S)", bg="darkred", fg="white", font=("", 10, "bold"), command=deploy).pack(side=tk.RIGHT)
tk.Button(frame_top, text="🔄 恢复原版", bg="#004488", fg="white", font=("", 10, "bold"), command=restore_default).pack(side=tk.RIGHT, padx=(10, 10))

root.bind("<Control-s>", deploy)
root.bind("<Control-S>", deploy)

frame_main = tk.Frame(root)
frame_main.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

frame_preview = tk.Frame(frame_main, width=280)
frame_preview.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,0))
tk.Label(frame_preview, text="代码沙盒 (真理源：所见即所得)").pack()
txt_preview = tk.Text(frame_preview, width=35, bg="#0a0a0a", fg="#00ff00", font=("Consolas", 10))
txt_preview.pack(fill=tk.BOTH, expand=True)

notebook = ttk.Notebook(frame_main)
notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

create_editor_tab(notebook, "tab_unit", "🪖 战术单位 (Units)", codex.get("Units", {}), FORM_UNITS, RULES_UNITS)
create_editor_tab(notebook, "tab_weap", "⚔️ 武器图纸 (Weapons)", codex.get("Weapons", {}), FORM_WEAPONS)
create_editor_tab(notebook, "tab_warh", "💥 弹头破坏 (Warheads)", codex.get("Warheads", {}), FORM_WARHEADS)

notebook.bind("<<NotebookTabChanged>>", lambda e: update_preview())
root.after(1000, file_watchdog)
root.mainloop()
