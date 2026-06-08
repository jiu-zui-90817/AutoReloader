import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

# ========================================================
# ToolTip 类（用于路径框悬停提示）
# ========================================================
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind('<Enter>', self.show_tip)
        widget.bind('<Leave>', self.hide_tip)

    def show_tip(self, event):
        if self.tipwindow or not self.text:
            return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, background="#ffffe0", relief="solid", borderwidth=1)
        label.pack()

    def hide_tip(self, event):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

# ========================================================
# 0. 引擎安全启动与架构配置
# ========================================================
root = tk.Tk()
root.withdraw()

CODEX_FILE = "Codex_ZH.json"
RULES_FILE = "rulesmo.ini"
CONFIG_FILE = "console_config.json"
target_filepath = ""
last_file_mtime = 0
base_rules_data = {}

current_mode = "safe"  # safe / advanced

# ========================================================
# 持久化配置读写
# ========================================================
def load_config():
    global current_mode
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                current_mode = config.get("mode", "safe")
        except Exception:
            pass

def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"mode": current_mode}, f, indent=2)
    except Exception:
        pass

# ========================================================
# 字典加载
# ========================================================
if not os.path.exists(CODEX_FILE):
    messagebox.showerror("致命错误", f"找不到核心武器库：{CODEX_FILE}")
    sys.exit()

try:
    with open(CODEX_FILE, "r", encoding="utf-8") as f:
        codex = json.load(f)
except Exception as e:
    messagebox.showerror("致命错误", f"解析 {CODEX_FILE} 失败！\n\n报错信息: {str(e)}")
    sys.exit()

# ========================================================
# 支持 ARES #include 的 ini 解析器（多文件合并）
# ========================================================
def parse_single_ini(filepath):
    ini_data = {}
    current_section = None
    try:
        with open(filepath, 'r', encoding='ansi', errors='ignore') as f:
            for line in f:
                line = line.split(';')[0].strip()
                if not line:
                    continue
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1].strip()
                    if current_section not in ini_data:
                        ini_data[current_section] = {}
                elif '=' in line and current_section:
                    key, val = line.split('=', 1)
                    ini_data[current_section][key.strip()] = val.strip()
    except Exception as e:
        print(f"解析 {filepath} 出错: {e}")
    return ini_data

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

        for section, kv in data.items():
            if section not in total_data:
                total_data[section] = {}
            total_data[section].update(kv)

        include_section = data.get('#include', {})
        include_files = []
        for k, v in include_section.items():
            k_lower = k.lower()
            if k_lower == 'include' or k_lower.startswith('include'):
                include_files.append(v)
            elif k.isdigit():
                include_files.append(v)
        seen = set()
        unique_include = []
        for f in include_files:
            if f not in seen:
                seen.add(f)
                unique_include.append(f)
        for inc_file in unique_include:
            load_file(inc_file, depth + 1)

    load_file(main_filepath)
    if log_func:
        log_func(f"[加载] 共合并 {len(processed_files)} 个规则文件")
    return total_data

if os.path.exists(RULES_FILE):
    base_rules_data = parse_cnc_ini_with_includes(RULES_FILE, print)
    print(f"[引擎挂载] 成功读取 {RULES_FILE} 及其所有 #include 文件，引擎待命中！")
else:
    messagebox.showwarning("警告", f"找不到 {RULES_FILE}，恢复原版功能将不可用。")

root.deiconify()
root.title("MO 战术工坊")
root.geometry("1180x800")
if sv_ttk:
    sv_ttk.set_theme("dark")

try:
    root.iconbitmap("app_icon.ico")
except Exception:
    pass

# ========================================================
# 1. 兵器谱图纸全量字典
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
    ("单位专属光环 (Ares AttachEffect)", [
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
    ("武器打击效果 (Ares AttachEffect)", [
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
# 2. 核心交互引擎
# ========================================================
tabs_info = {}
is_switching_unit = False

def extract_real_id(text):
    if not text:
        return ""
    if " - " in text:
        return text.split(" - ")[0].strip()
    if " [" in text and text.endswith("]"):
        return text.split('[')[-1].replace(']', '').strip()
    return text.strip()

def apply_ae_preset(preset_name, t_vars):
    all_presets = {**codex.get("Presets_Passive", {}), **codex.get("Presets_Attack", {})}
    if preset_name not in all_presets:
        return

    preset_data = all_presets[preset_name]
    for key, val in preset_data.items():
        for form_key, var in t_vars.items():
            if form_key.lower() == key.lower():
                var.set(val)

def replace_ini_section(filepath, section, block_text):
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="ansi") as f:
            f.write("; Auto-generated by Tactical Console\n")

    lines = []
    with open(filepath, "r", encoding="ansi") as f:
        lines = f.readlines()

    out_lines = []
    in_sec = False
    sec_found = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_sec:
                in_sec = False
            if stripped[1:-1].strip().lower() == section.lower():
                in_sec = True
                sec_found = True
                out_lines.append(block_text + "\n")
                continue
        if not in_sec:
            out_lines.append(line)

    if not sec_found:
        if out_lines and not out_lines[-1].endswith("\n"):
            out_lines.append("\n")
        out_lines.append("\n" + block_text + "\n")

    with open(filepath, "w", encoding="ansi") as f:
        f.writelines(out_lines)

def on_tree_select(tab_id):
    global is_switching_unit
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
                        if in_sec:
                            break
                        if stripped[1:-1].strip().lower() == obj_id.lower():
                            in_sec = True
                            continue
                    elif in_sec:
                        raw_lines.append(line.rstrip())
                        clean = line.split(';')[0].strip()
                        if '=' in clean:
                            k, v = clean.split('=', 1)
                            ini_data[k.strip().lower()] = v.strip()
        except Exception:
            pass

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
                if ctrl:
                    ctrl.config(state="disabled")
                continue
            else:
                if ctrl:
                    ctrl.config(state="normal")

            if w_type == "entry":
                var.set(val_ini)
            elif w_type == "combo":
                if d_name == "DYNAMIC_IMAGE" and ctrl:
                    img_dict = codex.get(f"{u_type}Images", {})
                    new_options = [""] + [f"{v} [{k}]" for k, v in img_dict.items()]
                    ctrl['values'] = new_options
                    ctrl.full_values = new_options

                if val_ini == "":
                    var.set("")
                else:
                    matched = next((v for v in ctrl['values'] if v.startswith(f"{val_ini} -") or v.endswith(f"[{val_ini}]") or v == val_ini), "")
                    var.set(matched if matched else val_ini)

    is_switching_unit = False

def update_preview(*args):
    if is_switching_unit:
        return
    try:
        current_text = txt_preview.get("1.0", tk.END).split('\n')
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
        sel = tab["tree"].selection()
        if not sel or not tab["tree"].item(sel[0]).get("values"):
            return
        obj_id = tab["tree"].item(sel[0])["values"][0]
    except Exception:
        return

    ui_data = {}
    for ini_key, var in tab["vars"].items():
        if ini_key.startswith("AEPreset"):
            continue
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
                if val != "":
                    new_lines.append(f"{ini_key}={val}")
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
    while new_lines and not new_lines[-1].strip():
        new_lines.pop()
    txt_preview.insert(tk.END, '\n'.join(new_lines))
    txt_preview.mark_set(tk.INSERT, cursor_pos)
    txt_preview.yview_moveto(scroll_y[0])

# ========================================================
# 树形视图搜索过滤功能
# ========================================================
def filter_data(data, filter_text):
    if not filter_text:
        return data
    lower_filter = filter_text.lower()
    filtered = {}
    for key, value in data.items():
        key_matched = lower_filter in key.lower()
        if isinstance(value, dict):
            if key_matched:
                filtered[key] = value
            else:
                sub_filtered = filter_data(value, filter_text)
                if sub_filtered:
                    filtered[key] = sub_filtered
        else:
            display_text = f"{value} [{key}]"
            if key_matched or lower_filter in key.lower() or lower_filter in value.lower() or lower_filter in display_text.lower():
                filtered[key] = value
    return filtered

def rebuild_tree(tab_id):
    tab = tabs_info[tab_id]
    tab["search_after_id"] = None
    tree = tab["tree"]
    original_data = tab["original_data"]
    search_entry = tab["search_entry"]
    filter_text = search_entry.get()

    for item in tree.get_children():
        tree.delete(item)

    if filter_text:
        filtered = filter_data(original_data, filter_text)
        if not filtered:
            return
        data_to_show = filtered
    else:
        data_to_show = original_data

    def populate_tree(parent_node, current_data):
        for k, v in current_data.items():
            if isinstance(v, dict):
                folder = tree.insert(parent_node, tk.END, text=k, open=False)
                populate_tree(folder, v)
            else:
                tree.insert(parent_node, tk.END, text=f"{v} [{k}]", values=(k,))

    populate_tree("", data_to_show)

def on_search(event, tab_id):
    tab = tabs_info[tab_id]
    prev_id = tab.get("search_after_id")
    if prev_id is not None:
        try:
            root.after_cancel(prev_id)
        except Exception:
            pass
    tab["search_after_id"] = root.after(300, lambda: rebuild_tree(tab_id))

def create_editor_tab(notebook_parent, tab_id, tab_text, data_dict, form_config, rules_dict=None):
    frame_bg = tk.Frame(notebook_parent)
    notebook_parent.add(frame_bg, text=tab_text)

    frame_tree = tk.Frame(frame_bg, padx=5, pady=5)
    frame_tree.pack(side=tk.LEFT, fill=tk.Y)

    search_frame = tk.Frame(frame_tree)
    search_frame.pack(fill=tk.X, pady=(0, 5))
    tk.Label(search_frame, text="🔍 搜索:").pack(side=tk.LEFT)
    search_entry = tk.Entry(search_frame)
    search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    tree = ttk.Treeview(frame_tree, show="tree", selectmode="browse")
    sb = ttk.Scrollbar(frame_tree, command=tree.yview)
    tree.config(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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
                        if event.keysym in ("Up", "Down", "Return", "Escape", "Left", "Right", "Tab"):
                            return
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
        "tree": tree,
        "vars": t_vars,
        "widgets": t_widgets,
        "form_config": form_config,
        "rules": rules_dict,
        "original_data": data_dict,
        "search_entry": search_entry,
        "search_after_id": None
    }

    search_entry.bind("<KeyRelease>", lambda e, tid=tab_id: on_search(e, tid))

    def populate_tree_initial(parent_node, current_data):
        for k, v in current_data.items():
            if isinstance(v, dict):
                folder = tree.insert(parent_node, tk.END, text=k, open=False)
                populate_tree_initial(folder, v)
            else:
                tree.insert(parent_node, tk.END, text=f"{v} [{k}]", values=(k,))

    populate_tree_initial("", data_dict)

    tree.bind("<<TreeviewSelect>>", lambda e: on_tree_select(tab_id))
    return frame_bg

# ========================================================
# 模式切换与文件选择逻辑
# ========================================================
def toggle_mode():
    global current_mode
    if current_mode == "safe":
        result = messagebox.askyesno(
            "切换到高级模式",
            "高级模式允许您读写任意 .ini 文件（不限制文件名）。\n\n"
            "⚠️ 警告：\n"
            "- “恢复原版”功能将被禁用（防止误覆盖您的源文件）。\n"
            "- 请自行备份您要编辑的重要文件。\n\n"
            "是否继续切换到高级模式？"
        )
        if result:
            current_mode = "advanced"
            mode_btn.config(text="🔓 高级模式 (读写任意ini)", bg="#5a3a2a")
            mode_label.config(text="当前模式：高级模式（恢复原版已禁用）", fg="orange")
            restore_btn.config(state="disabled")
            save_config()
            messagebox.showinfo("模式切换", "已切换到高级模式。\n现在可以选择任意 .ini 文件进行操作。")
        else:
            return
    else:
        result = messagebox.askyesno(
            "切换到安全模式",
            "安全模式仅允许读写名为 hotfix.ini 的工程文件。\n\n"
            "将重新启用“恢复原版”功能。\n\n"
            "是否继续切换回安全模式？"
        )
        if result:
            current_mode = "safe"
            mode_btn.config(text="🔒 安全模式 (仅限hotfix.ini)", bg="#2d5a2d")
            mode_label.config(text="当前模式：安全模式（仅限hotfix.ini）", fg="#00cc00")
            restore_btn.config(state="normal")
            save_config()
            messagebox.showinfo("模式切换", "已切换回安全模式。\n只能操作 hotfix.ini 文件。")
        else:
            return

def choose_file():
    global target_filepath, last_file_mtime

    if current_mode == "safe":
        fp = filedialog.askopenfilename(
            title="请定位到工程文件 (仅限 hotfix.ini)",
            defaultextension=".ini",
            filetypes=[("战术工坊工程文件", "hotfix.ini")]
        )
        if not fp:
            fp = filedialog.asksaveasfilename(
                title="或新建临时工程文件 (仅限 hotfix.ini)",
                initialfile="hotfix.ini",
                defaultextension=".ini",
                filetypes=[("战术工坊工程文件", "hotfix.ini")]
            )
        if fp:
            filename = os.path.basename(fp).lower()
            if filename != "hotfix.ini":
                messagebox.showwarning(
                    "⚠️ 文件选择受限",
                    "安全模式下，战术工坊只能操作专属的临时工程草稿文件！\n\n"
                    "✅ 仅允许的文件名：hotfix.ini\n"
                    f"❌ 您选择的是：{filename}\n\n"
                    "请重新选择或将您的测试文件重命名为 hotfix.ini，\n"
                    "或切换到“高级模式”以支持任意文件。"
                )
                return
    else:
        fp = filedialog.askopenfilename(
            title="选择要编辑的 INI 文件",
            defaultextension=".ini",
            filetypes=[("INI 文件", "*.ini"), ("所有文件", "*.*")]
        )
        if not fp:
            fp = filedialog.asksaveasfilename(
                title="新建 INI 文件",
                defaultextension=".ini",
                filetypes=[("INI 文件", "*.ini"), ("所有文件", "*.*")]
            )
        if fp:
            if not os.path.basename(fp).lower().endswith(".ini"):
                if not messagebox.askyesno("确认", "文件扩展名不是 .ini，继续操作可能无效。是否继续？"):
                    return

    if fp:
        target_filepath = fp
        # 更新路径显示框（只读、可滚动）
        path_entry.config(state='normal')
        path_entry.delete(0, tk.END)
        path_entry.insert(0, fp)
        path_entry.config(state='readonly')
        # 可选：改变前景色提示已选择文件（sv_ttk dark 下有效）
        path_entry.config(foreground="#00ff00")
        try:
            if not os.path.exists(fp):
                with open(fp, 'w', encoding='ansi') as f:
                    f.write("; Tactical Console Target File\n\n")
            last_file_mtime = os.path.getmtime(fp)
            current_tab_idx = notebook.index(notebook.select())
            on_tree_select(list(tabs_info.keys())[current_tab_idx])
        except Exception as e:
            messagebox.showerror("错误", f"无法创建/打开文件：{str(e)}")

# ========================================================
# 一键提取完美代码 (原版底包 + 修改项)
# ========================================================
def copy_full_code():
    try:
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
        sel = tab["tree"].selection()
        if not sel or not tab["tree"].item(sel[0]).get("values"):
            return messagebox.showwarning("提示", "请先在左侧选择一个图纸！")
        obj_id = tab["tree"].item(sel[0])["values"][0]
    except Exception:
        return

    base_props = base_rules_data.get(obj_id, {})
    ui_data = {}
    for ini_key, var in tab["vars"].items():
        if ini_key.startswith("AEPreset"):
            continue
        ctrl = tab["widgets"].get(ini_key)
        if ctrl and str(ctrl.cget("state")) != "disabled":
            val = extract_real_id(var.get())
            if val != "":
                ui_data[ini_key.lower()] = (ini_key, val)

    lines = [f"[{obj_id}]"]

    for k, v in base_props.items():
        k_lower = k.lower()
        if k_lower in ui_data:
            lines.append(f"{ui_data[k_lower][0]}={ui_data[k_lower][1]}")
            del ui_data[k_lower]
        else:
            lines.append(f"{k}={v}")

    for k_lower, (ini_key, val) in ui_data.items():
        lines.append(f"{ini_key}={val}")

    full_text = "\n".join(lines)
    root.clipboard_clear()
    root.clipboard_append(full_text)
    messagebox.showinfo("复制成功", "✅ 完整代码（原版底包 + 您的修改）已生成并复制到剪贴板！\n\n您可以直接去自己的 INI 源码中粘贴，彻底覆盖原有区块！")

# ========================================================
# 静默清理（5秒后自动瘦身）
# ========================================================
def clean_ini_silent():
    if not target_filepath or not os.path.exists(target_filepath):
        return
    if not base_rules_data:
        return

    lines = []
    with open(target_filepath, 'r', encoding='ansi') as f:
        lines = f.readlines()

    out_lines = []
    current_section = None
    section_lines = []

    def process_section():
        if not current_section:
            return
        base_props = base_rules_data.get(current_section, {})
        base_props_lower = {k.lower(): v.lower() for k, v in base_props.items()}
        cleaned_section_lines = [section_lines[0]]
        has_custom = False

        kill_cmds = {
            "attacheffect.animation": ["none", "0", ""],
            "attacheffect.duration": ["0"],
            "attacheffect.speedmultiplier": ["1", "1.0"],
            "attacheffect.armormultiplier": ["1", "1.0"],
            "attacheffect.firepowermultiplier": ["1", "1.0"],
            "attacheffect.rofmultiplier": ["1", "1.0"],
            "attacheffect.delay": ["0"],
            "attacheffect.initialdelay": ["0"],
            "attacheffect.cumulative": ["no", "false", "0"],
            "image": [current_section.lower()]
        }

        for line in section_lines[1:]:
            clean_line = line.split(';')[0].strip()
            if '=' in clean_line:
                k, v = clean_line.split('=', 1)
                k_lower, v_lower = k.strip().lower(), v.strip().lower()

                if k_lower in base_props_lower and base_props_lower[k_lower] == v_lower:
                    continue

                if k_lower in kill_cmds and v_lower in kill_cmds[k_lower]:
                    continue

                has_custom = True
                cleaned_section_lines.append(line)
            else:
                if line.strip():
                    cleaned_section_lines.append(line)

        if has_custom:
            out_lines.extend(cleaned_section_lines)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            process_section()
            current_section = stripped[1:-1].strip()
            section_lines = [line]
        else:
            section_lines.append(line)

    process_section()

    with open(target_filepath, 'w', encoding='ansi') as f:
        f.writelines(out_lines)

    global last_file_mtime
    last_file_mtime = os.path.getmtime(target_filepath)

    try:
        current_tab_idx = notebook.index(notebook.select())
        on_tree_select(list(tabs_info.keys())[current_tab_idx])
    except Exception:
        pass

# ========================================================
# 恢复原版（安全模式专用）
# ========================================================
def restore_default():
    if current_mode != "safe":
        messagebox.showwarning("功能禁用", "当前处于“高级模式”，为防止误覆盖，恢复原版功能已被禁用。\n如需使用，请切换回“安全模式”。")
        return
    if not target_filepath:
        messagebox.showwarning("警告", "请先选择目标文件！")
        return
    if not base_rules_data:
        messagebox.showwarning("警告", "未挂载原版规则数据（可能 rulesmo.ini 不存在或解析失败）！")
        return

    try:
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
        sel = tab["tree"].selection()
        if not sel or not tab["tree"].item(sel[0]).get("values"):
            return
        obj_id = tab["tree"].item(sel[0])["values"][0]
    except Exception:
        return

    base_props = base_rules_data.get(obj_id, {})
    if not base_props:
        return messagebox.showinfo("提示", "原版引擎中不存在该图纸数据。")

    lines = [f"[{obj_id}]"]
    base_keys_lower = {k.lower(): k for k in base_props.keys()}

    if "image" not in base_keys_lower:
        lines.append(f"Image={obj_id}")
    for k, v in base_props.items():
        lines.append(f"{k}={v}")

    has_ae = any(k.startswith("attacheffect.") for k in base_keys_lower)
    if not has_ae:
        lines.extend([
            "AttachEffect.Animation=none", "AttachEffect.Duration=0", "AttachEffect.SpeedMultiplier=1",
            "AttachEffect.ArmorMultiplier=1", "AttachEffect.FirepowerMultiplier=1", "AttachEffect.ROFMultiplier=1",
            "AttachEffect.Delay=0", "AttachEffect.InitialDelay=0", "AttachEffect.Cumulative=no"
        ])

    replace_ini_section(target_filepath, obj_id, '\n'.join(lines))

    global last_file_mtime
    last_file_mtime = os.path.getmtime(target_filepath)
    on_tree_select(list(tabs_info.keys())[tab_idx])

    root.after(5000, clean_ini_silent)
    messagebox.showinfo("重置成功", f"[{obj_id}] 强行覆盖为官方默认值！\n\n5秒后将自动进行静默瘦身，清除临时强杀指令。")

# ========================================================
# 部署（写入工程文件）
# ========================================================
def deploy(event=None):
    if not target_filepath:
        return messagebox.showinfo("提示", "请先选择工程文件！")
    try:
        tab_idx = notebook.index(notebook.select())
        tab = tabs_info[list(tabs_info.keys())[tab_idx]]
        sel = tab["tree"].selection()
        if not sel or not tab["tree"].item(sel[0]).get("values"):
            return
        obj_id = tab["tree"].item(sel[0])["values"][0]
    except Exception:
        return

    raw_content = txt_preview.get("1.0", tk.END).strip()
    try:
        replace_ini_section(target_filepath, obj_id, raw_content)
        global last_file_mtime
        last_file_mtime = os.path.getmtime(target_filepath)
        root.after(5000, clean_ini_silent)
        messagebox.showinfo("部署成功", "配置已推入工程文件，游戏内已生效！\n若满意请使用右下角的【一键复制代码】功能带走参数。")
    except Exception as e:
        messagebox.showerror("错误", str(e))

# ========================================================
# 文件守护线程（自动刷新预览）
# ========================================================
def file_watchdog():
    global last_file_mtime
    if target_filepath and os.path.exists(target_filepath):
        try:
            current_mtime = os.path.getmtime(target_filepath)
            if current_mtime > last_file_mtime:
                try:
                    current_tab_idx = notebook.index(notebook.select())
                    on_tree_select(list(tabs_info.keys())[current_tab_idx])
                except Exception:
                    pass
                last_file_mtime = current_mtime
        except Exception:
            pass
    root.after(1000, file_watchdog)

# ========================================================
# 4. GUI 构建与挂载
# ========================================================
load_config()

frame_top = tk.Frame(root, bg="#1e1e1e", padx=10, pady=10)
frame_top.pack(fill=tk.X)

# 左侧：文件绑定按钮
btn_choose = tk.Button(frame_top, text="📂 绑定工程文件", command=choose_file, bg="#333333", fg="white", font=("", 10, "bold"))
btn_choose.pack(side=tk.LEFT)

# 中间：路径显示区域（可滚动）
path_frame = tk.Frame(frame_top)
path_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(15, 5))
path_entry = ttk.Entry(path_frame, state='readonly', font=("", 9))
path_entry.pack(fill=tk.X, expand=True)
path_entry.config(state='normal')
path_entry.insert(0, "当前目标: 未选择")
path_entry.config(state='readonly')
# 添加 ToolTip（悬停提示）
ToolTip(path_entry, "当前文件路径（可左右拖动光标查看完整路径）")

# 中间偏右：模式切换按钮和状态指示
mode_btn = tk.Button(frame_top, text="", command=toggle_mode, font=("", 9, "bold"))
mode_btn.pack(side=tk.LEFT, padx=10)
mode_label = tk.Label(frame_top, text="", bg="#1e1e1e", font=("", 9))
mode_label.pack(side=tk.LEFT, padx=5)

# 右侧：部署和恢复按钮
deploy_btn = tk.Button(frame_top, text="💾 测试部署 (Ctrl+S)", bg="darkred", fg="white", font=("", 10, "bold"), command=deploy)
deploy_btn.pack(side=tk.RIGHT)
restore_btn = tk.Button(frame_top, text="🔄 恢复原版", bg="#004488", fg="white", font=("", 10, "bold"), command=restore_default)
restore_btn.pack(side=tk.RIGHT, padx=(10, 10))

# 根据保存的模式设置界面初始状态
if current_mode == "safe":
    mode_btn.config(text="🔒 安全模式 (仅限hotfix.ini)", bg="#2d5a2d")
    mode_label.config(text="当前模式：安全模式（仅限hotfix.ini）", fg="#00cc00")
    restore_btn.config(state="normal")
else:
    mode_btn.config(text="🔓 高级模式 (读写任意ini)", bg="#5a3a2a")
    mode_label.config(text="当前模式：高级模式（恢复原版已禁用）", fg="orange")
    restore_btn.config(state="disabled")

root.bind("<Control-s>", deploy)
root.bind("<Control-S>", deploy)

frame_main = tk.Frame(root)
frame_main.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

frame_preview = tk.Frame(frame_main, width=280)
frame_preview.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
tk.Label(frame_preview, text="工程沙盒代码预览").pack()

txt_preview = tk.Text(frame_preview, width=38, bg="#0a0a0a", fg="#00ff00", font=("Consolas", 10))
txt_preview.pack(fill=tk.BOTH, expand=True)

frame_copy = tk.Frame(frame_preview, pady=5)
frame_copy.pack(fill=tk.X)
tk.Button(frame_copy, text="📋 一键复制完整代码 (含原版属性)", bg="#2d7d46", fg="white", font=("", 10, "bold"), pady=8, command=copy_full_code).pack(fill=tk.X)

notebook = ttk.Notebook(frame_main)
notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

create_editor_tab(notebook, "tab_unit", "🪖 战术单位 (Units)", codex.get("Units", {}), FORM_UNITS, RULES_UNITS)
create_editor_tab(notebook, "tab_weap", "⚔️ 武器图纸 (Weapons)", codex.get("Weapons", {}), FORM_WEAPONS)
create_editor_tab(notebook, "tab_warh", "💥 弹头破坏 (Warheads)", codex.get("Warheads", {}), FORM_WARHEADS)

notebook.bind("<<NotebookTabChanged>>", lambda e: update_preview())
root.after(1000, file_watchdog)
root.mainloop()
