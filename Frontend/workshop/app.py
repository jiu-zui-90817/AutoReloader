"""
战术工坊 2.x — 对齐经典版布局：
  顶栏绑定路径 | 安全模式 | 部署/恢复
  页签 单位/武器/弹头
  左树 + 中部分组表单（中文标签 | 控件 横排）+ 右侧绿字预览 + 底部一键复制
无 Codex：对象树与下拉从工程 rules/CSF 动态生成。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QLineEdit, QLabel, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QFileDialog, QToolBar,
    QStatusBar, QSizePolicy, QCheckBox, QInputDialog, QTabWidget, QGroupBox,
    QFormLayout, QDialog, QDialogButtonBox,
)

from fields import (
    TAB_GROUPS, GROUP_LABELS, DEFAULT_ARMORS, DEFAULT_LOCOMOTORS,
    form_keys,
)


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def ensure_shared_path() -> None:
    root = get_repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


ensure_shared_path()

from shared.project_scan import GameProject, load_profiles  # noqa: E402
from shared.hotfix_io import save_section_to_file, normalize_section_body, read_text  # noqa: E402


class NoWheelFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, QComboBox) and obj.view().isVisible():
                return False
            return True
        return super().eventFilter(obj, event)


class AddKeyDialog(QDialog):
    """样式正常的添加属性对话框（避免黑底空框）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加属性")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("键名（INI 字段名，如 Strength）："))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("例如 Primary")
        lay.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.setStyleSheet("""
            QDialog { background: #2b2b2b; color: #eee; }
            QLabel { color: #eee; }
            QLineEdit {
                background: #1e1e1e; color: #eee;
                border: 1px solid #555; padding: 6px; border-radius: 4px;
            }
            QPushButton { min-width: 72px; padding: 6px 12px; }
        """)

    def key_name(self) -> str:
        return self.edit.text().strip()


class WorkshopWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_dir = get_app_dir()
        self.repo_root = get_repo_root()
        self.config_path = self.app_dir / "workshop_config.json"
        self.profiles = load_profiles(self.repo_root / "shared" / "profiles.json")
        if not (self.repo_root / "shared" / "profiles.json").exists():
            alt = self.app_dir / "profiles.json"
            if alt.exists():
                self.profiles = load_profiles(alt)

        self.settings = self._load_settings()
        self.mode = self.settings.get("mode", "safe")
        self.assist = bool(self.settings.get("assist_mode", True))
        self.game: Optional[GameProject] = None
        self.hotfix_path: Optional[Path] = None
        self.current_id: Optional[str] = None
        self.current_tab: str = "units"
        self.entries: Dict[str, QWidget] = {}
        self.extra_keys: List[str] = []
        self._loading = False
        self._no_wheel = NoWheelFilter(self)
        self._option_cache: Dict[str, List[str]] = {}
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self.refresh_tree)
        self._watch_mtime = 0.0
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._file_watch)
        self._watch.start(1500)

        self.setWindowTitle("战术工坊 2.x")
        self.resize(1180, 800)
        self._build_ui()
        self._apply_style()
        self._update_mode_ui()
        self.statusBar().showMessage("请先打开游戏目录，再绑定 hotfix.ini")

    def _load_settings(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_settings(self) -> None:
        data = {
            "mode": self.mode,
            "assist_mode": self.assist,
            "last_game_dir": self.settings.get("last_game_dir", ""),
            "last_hotfix": str(self.hotfix_path) if self.hotfix_path else self.settings.get("last_hotfix", ""),
            "profile": self.settings.get("profile", self.profiles.get("active_profile", "MentalOmega")),
        }
        try:
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.settings = data

    def _profile(self) -> dict:
        name = self.settings.get("profile") or self.profiles.get("active_profile", "MentalOmega")
        return self.profiles.get("profiles", {}).get(name, {})

    def _build_ui(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        btn_bind = QPushButton("📂 绑定工程文件")
        btn_bind.setObjectName("bindBtn")
        btn_bind.clicked.connect(self.choose_hotfix)
        tb.addWidget(btn_bind)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("当前目标: 未选择")
        self.path_edit.setMinimumWidth(280)
        tb.addWidget(self.path_edit)

        self.btn_mode = QPushButton()
        self.btn_mode.clicked.connect(self.toggle_mode)
        tb.addWidget(self.btn_mode)

        self.mode_hint = QLabel()
        self.mode_hint.setStyleSheet("color:#00cc00; padding:0 8px;")
        tb.addWidget(self.mode_hint)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.btn_restore = QPushButton("🔄 恢复原版")
        self.btn_restore.setObjectName("restoreBtn")
        self.btn_restore.clicked.connect(self.restore_default)
        tb.addWidget(self.btn_restore)

        self.btn_deploy = QPushButton("💾 测试部署 (Ctrl+S)")
        self.btn_deploy.setObjectName("primaryBtn")
        self.btn_deploy.clicked.connect(self.deploy)
        tb.addWidget(self.btn_deploy)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        row2 = QHBoxLayout()
        btn_game = QPushButton("打开游戏目录")
        btn_game.clicked.connect(self.open_game_dir)
        row2.addWidget(btn_game)
        self.dir_label = QLabel("游戏目录：未打开")
        self.dir_label.setStyleSheet("color:#7dd3fc;")
        row2.addWidget(self.dir_label, 1)
        self.chk_assist = QCheckBox("辅助下拉（可选项）")
        self.chk_assist.setChecked(self.assist)
        self.chk_assist.toggled.connect(self._on_assist)
        row2.addWidget(self.chk_assist)
        root.addLayout(row2)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        for tid, meta in TAB_GROUPS.items():
            self.tabs.addTab(QWidget(), meta["title"])
        self.tabs.currentChanged.connect(self._on_tab_changed)
        ll.addWidget(self.tabs)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("🔍 搜索:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("注册名 / 中文…")
        self.filter_edit.textChanged.connect(lambda: self._filter_timer.start(160))
        search_row.addWidget(self.filter_edit, 1)
        ll.addLayout(search_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self.on_tree_click)
        ll.addWidget(self.tree, 1)
        left.setMinimumWidth(240)
        left.setMaximumWidth(360)
        split.addWidget(left)

        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(4, 0, 4, 0)
        ml.setSpacing(4)
        self.sec_title = QLabel("选择图纸后显示参数")
        self.sec_title.setObjectName("secTitle")
        ml.addWidget(self.sec_title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.StyledPanel)
        self.form_inner = QWidget()
        self.form_layout = QVBoxLayout(self.form_inner)
        self.form_layout.setAlignment(Qt.AlignTop)
        self.form_layout.setSpacing(8)
        self.form_layout.setContentsMargins(6, 6, 6, 6)
        self.scroll.setWidget(self.form_inner)
        ml.addWidget(self.scroll, 1)

        foot = QHBoxLayout()
        b_add = QPushButton("+ 属性")
        b_add.clicked.connect(self.add_key)
        foot.addWidget(b_add)
        foot.addStretch()
        ml.addLayout(foot)
        split.addWidget(mid)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(4)
        rl.addWidget(QLabel("工程沙盒代码预览"))
        self.code = QPlainTextEdit()
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code.setObjectName("codeEdit")
        self.code.setFont(QFont("Consolas", 10))
        rl.addWidget(self.code, 1)
        self.btn_copy = QPushButton("📋 一键复制完整代码 (含原版属性)")
        self.btn_copy.setObjectName("copyBtn")
        self.btn_copy.setMinimumHeight(40)
        self.btn_copy.clicked.connect(self.copy_full_code)
        rl.addWidget(self.btn_copy)
        right.setMinimumWidth(260)
        right.setMaximumWidth(380)
        split.addWidget(right)

        split.setSizes([280, 560, 300])
        QAction("deploy", self, shortcut=QKeySequence("Ctrl+S"), triggered=self.deploy)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; color: #e8e8e8; }
            QWidget { color: #e8e8e8; font-size: 13px; }
            QToolBar {
                background: #1e1e1e; border-bottom: 1px solid #333;
                spacing: 8px; padding: 8px 10px;
            }
            QStatusBar { background: #1a1a1a; color: #aaa; }
            QTabWidget::pane { border: 1px solid #333; background: #1e1e1e; }
            QTabBar::tab {
                background: #2a2a2a; color: #ccc; padding: 8px 14px;
                border: 1px solid #333; border-bottom: none; margin-right: 2px;
            }
            QTabBar::tab:selected { background: #3a3a3a; color: #fff; font-weight: 700; }
            QTreeWidget {
                background: #252526; border: 1px solid #3c3c3c;
                outline: none; font-size: 12px;
            }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected { background: #094771; }
            QPlainTextEdit#codeEdit {
                background: #0a0a0a; color: #00ff00;
                border: 1px solid #333;
                font-family: Consolas, "Courier New", monospace;
            }
            QLineEdit, QComboBox {
                background: #2d2d30; border: 1px solid #3f3f46;
                border-radius: 3px; padding: 4px 8px; min-height: 22px;
                color: #e8e8e8;
            }
            QComboBox { padding-right: 28px; }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 22px; border-left: 1px solid #3f3f46; background: #3a3a40;
            }
            QComboBox::down-arrow {
                width: 0; height: 0;
                border-left: 5px solid transparent; border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0; margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #2d2d30; color: #eee; selection-background-color: #094771;
            }
            QPushButton {
                background: #333; border: 1px solid #555; border-radius: 4px;
                padding: 6px 12px; color: #eee;
            }
            QPushButton:hover { background: #404040; }
            QPushButton#primaryBtn {
                background: #8b0000; border-color: #a00; color: #fff; font-weight: 700;
            }
            QPushButton#primaryBtn:hover { background: #a01010; }
            QPushButton#restoreBtn { background: #004488; border-color: #0066aa; color: #fff; }
            QPushButton#bindBtn { background: #333; font-weight: 700; }
            QPushButton#copyBtn {
                background: #2d7d46; border-color: #3a9; color: #fff;
                font-weight: 700; font-size: 13px;
            }
            QPushButton#copyBtn:hover { background: #359653; }
            QLabel#secTitle { font-weight: 700; font-size: 14px; color: #ddd; padding: 4px 0; }
            QGroupBox {
                border: 1px solid #3c3c3c; border-radius: 4px;
                margin-top: 12px; padding-top: 8px; font-weight: 700;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 6px;
                color: #c8c8c8;
            }
            QScrollArea { border: 1px solid #333; background: #252526; }
            QCheckBox { spacing: 6px; }
        """)

    def _update_mode_ui(self):
        if self.mode == "safe":
            self.btn_mode.setText("🔒 安全模式 (仅限hotfix.ini)")
            self.btn_mode.setStyleSheet(
                "background:#2d5a2d; color:#fff; font-weight:700; border-radius:4px; padding:6px 10px;"
            )
            self.mode_hint.setText("当前模式：安全模式（仅限hotfix.ini）")
            self.mode_hint.setStyleSheet("color:#00cc00; padding:0 8px;")
            self.btn_restore.setEnabled(True)
        else:
            self.btn_mode.setText("🔓 高级模式 (读写任意ini)")
            self.btn_mode.setStyleSheet(
                "background:#5a3a2a; color:#fff; font-weight:700; border-radius:4px; padding:6px 10px;"
            )
            self.mode_hint.setText("当前模式：高级模式（恢复原版已禁用）")
            self.mode_hint.setStyleSheet("color:orange; padding:0 8px;")
            self.btn_restore.setEnabled(False)

    def toggle_mode(self):
        if self.mode == "safe":
            ok = QMessageBox.question(
                self, "切换到高级模式",
                "高级模式允许读写任意 .ini 文件。\n\n"
                "⚠️「恢复原版」将被禁用。\n是否继续？",
            )
            if ok != QMessageBox.Yes:
                return
            self.mode = "advanced"
        else:
            ok = QMessageBox.question(
                self, "切换到安全模式",
                "安全模式仅允许操作 hotfix.ini，并重新启用恢复原版。\n是否切换？",
            )
            if ok != QMessageBox.Yes:
                return
            self.mode = "safe"
        self._update_mode_ui()
        self._save_settings()

    def _on_assist(self, checked: bool):
        self.assist = checked
        self._save_settings()
        if self.current_id:
            self.load_section(self.current_id)

    def _on_tab_changed(self, index: int):
        keys = list(TAB_GROUPS.keys())
        if 0 <= index < len(keys):
            self.current_tab = keys[index]
            self.refresh_tree()
            self.current_id = None
            self.sec_title.setText("选择图纸后显示参数")
            self._clear_form()
            self.code.clear()

    def open_game_dir(self):
        start = self.settings.get("last_game_dir") or str(Path.home())
        path = QFileDialog.getExistingDirectory(self, "打开游戏 / Mod 根目录", start)
        if not path:
            return
        prof = self._profile()
        if not prof:
            QMessageBox.warning(self, "配置", "profiles 中没有可用 profile")
            return
        self.statusBar().showMessage("正在加载 rules / CSF…")
        QApplication.processEvents()
        try:
            self.game = GameProject(Path(path), prof)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
            return
        if not self.game.rules:
            QMessageBox.warning(
                self, "加载",
                f"未找到 rules（尝试: {', '.join(prof.get('rules_files', []))}）",
            )
            return
        self.settings["last_game_dir"] = path
        self._save_settings()
        self._option_cache.clear()
        self.dir_label.setText(f"游戏目录：{path}  |  CSF {len(self.game.csf.strings)} 条")
        self.refresh_tree()
        n = sum(len(v) for v in self.game.list_groups().values())
        self.statusBar().showMessage(f"已加载 {n} 个可调对象")

    def choose_hotfix(self):
        start = self.settings.get("last_hotfix") or self.settings.get("last_game_dir") or str(Path.home())
        if self.mode == "safe":
            path, _ = QFileDialog.getSaveFileName(
                self, "绑定 hotfix.ini（安全模式）",
                str(Path(start) / "hotfix.ini"),
                "hotfix.ini (hotfix.ini)",
            )
            if path and Path(path).name.lower() != "hotfix.ini":
                QMessageBox.warning(self, "安全模式", "安全模式只能使用名为 hotfix.ini 的文件。")
                return
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "绑定目标 INI", start, "INI (*.ini)",
            )
        if not path:
            return
        p = Path(path)
        if not p.exists():
            p.write_text("; Tactical Workshop target\n", encoding="utf-8")
        self.hotfix_path = p
        self.settings["last_hotfix"] = str(p)
        self._save_settings()
        self.path_edit.setText(str(p))
        self.path_edit.setStyleSheet("color:#00ff00;")
        self._watch_mtime = p.stat().st_mtime if p.exists() else 0
        self.statusBar().showMessage(f"已绑定 {p}")

    def refresh_tree(self):
        self.tree.clear()
        if not self.game:
            return
        filt = self.filter_edit.text().strip().lower()
        meta = TAB_GROUPS[self.current_tab]
        all_groups = self.game.list_groups()
        for gname in meta["groups"]:
            ids = all_groups.get(gname, [])
            items = []
            for uid in ids:
                disp = self.game.display_name(uid)
                if filt and filt not in uid.lower() and filt not in disp.lower():
                    continue
                items.append((uid, disp))
            if not items and filt:
                continue
            label = GROUP_LABELS.get(gname, gname)
            node = QTreeWidgetItem(self.tree, [f"{label} ({len(items) if filt else len(ids)})"])
            node.setData(0, Qt.UserRole, None)
            for uid, disp in items:
                text = disp if disp != uid else uid
                if " - " not in text and disp != uid:
                    text = f"{disp} [{uid}]"
                child = QTreeWidgetItem(node, [text])
                child.setData(0, Qt.UserRole, uid)
            if filt:
                node.setExpanded(True)

    def on_tree_click(self, item: QTreeWidgetItem, _col: int):
        sid = item.data(0, Qt.UserRole)
        if not sid:
            return
        self.load_section(str(sid))

    def _clear_form(self):
        while self.form_layout.count():
            it = self.form_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        self.entries.clear()

    def _get_options(self, kind: str) -> List[str]:
        if kind in self._option_cache:
            return self._option_cache[kind]
        opts: List[str] = []
        if not self.game:
            self._option_cache[kind] = opts
            return opts
        if kind == "_armors":
            opts = list(DEFAULT_ARMORS)
        elif kind == "_locomotors":
            opts = list(DEFAULT_LOCOMOTORS)
        elif kind == "bool":
            opts = ["", "yes", "no", "true", "false"]
        elif kind == "_images":
            groups = self.game.list_groups()
            for g in ("InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes"):
                opts.extend(groups.get(g, []))
            opts = sorted(set(opts))
        elif kind == "Animations":
            opts = self.game.list_options("Animations") or self.game.list_options("AnimTypes") or []
        else:
            opts = self.game.list_options(kind) or []
            if not opts and kind in self.game.list_groups():
                opts = self.game.list_groups().get(kind, [])
        self._option_cache[kind] = opts
        return opts

    def _make_control(self, wtype: str, src: Optional[str], value: str) -> QWidget:
        if wtype == "combo" and self.assist and src:
            combo = QComboBox()
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.NoInsert)
            opts = self._get_options(src)
            items: List[str] = [""]
            if value and value not in opts and value not in items:
                items.append(value)
            items.extend(opts)
            seen = set()
            uniq = []
            for x in items:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            combo.addItems(uniq)
            combo.setCurrentText(value)
            combo.installEventFilter(self._no_wheel)
            if combo.lineEdit():
                combo.lineEdit().installEventFilter(self._no_wheel)
            combo.currentTextChanged.connect(lambda *_: self.sync_form_to_code())
            return combo
        edit = QLineEdit(value)
        edit.installEventFilter(self._no_wheel)
        edit.textChanged.connect(lambda *_: self.sync_form_to_code())
        return edit

    def _add_form_from_config(self, form_config, values: Dict[str, str]):
        lower = {k.lower(): (k, v) for k, v in values.items()}
        shown = set()

        for group_title, fields in form_config:
            box = QGroupBox(group_title)
            fl = QFormLayout(box)
            fl.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            fl.setFormAlignment(Qt.AlignTop)
            fl.setHorizontalSpacing(12)
            fl.setVerticalSpacing(6)
            fl.setContentsMargins(12, 16, 12, 10)
            fl.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

            for ini_key, label_text, wtype, src in fields:
                real_key, val = ini_key, ""
                if ini_key.lower() in lower:
                    real_key, val = lower[ini_key.lower()]
                ctrl = self._make_control(wtype, src, val)
                lab = QLabel(label_text)
                lab.setMinimumWidth(220)
                fl.addRow(lab, ctrl)
                self.entries[real_key] = ctrl
                shown.add(real_key.lower())

            self.form_layout.addWidget(box)

        extras = []
        for k, v in values.items():
            if k.lower() not in shown:
                extras.append((k, v))
        for k in self.extra_keys:
            if k.lower() not in shown and k not in values:
                extras.append((k, ""))
        if extras:
            box = QGroupBox("其他属性 (Other)")
            fl = QFormLayout(box)
            fl.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            fl.setHorizontalSpacing(12)
            fl.setVerticalSpacing(6)
            fl.setContentsMargins(12, 16, 12, 10)
            for k, v in extras:
                ctrl = self._make_control("entry", None, v)
                lab = QLabel(k)
                lab.setMinimumWidth(220)
                fl.addRow(lab, ctrl)
                self.entries[k] = ctrl
            self.form_layout.addWidget(box)

        self.form_layout.addStretch(1)

    def _widget_value(self, w: QWidget) -> str:
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""

    def load_section(self, section_id: str):
        if not self.game:
            return
        self.current_id = section_id
        self.extra_keys = []
        self.sec_title.setText(self.game.display_name(section_id))

        body = ""
        if self.hotfix_path and self.hotfix_path.exists():
            body = self._read_section_from_file(self.hotfix_path, section_id)
        if not body.strip() or body.strip() == f"[{section_id}]":
            body = self.game.get_section_text(section_id)

        keys: Dict[str, str] = {}
        for line in normalize_section_body(section_id, body).splitlines():
            s = line.strip()
            if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                continue
            if "=" in s:
                if ";" in s:
                    s = s.split(";", 1)[0].strip()
                k, _, v = s.partition("=")
                k, v = k.strip(), v.strip()
                if k:
                    keys[k] = v

        form_config = TAB_GROUPS[self.current_tab]["form"]
        self._loading = True
        self._clear_form()
        self._add_form_from_config(form_config, keys)

        self.code.blockSignals(True)
        text = normalize_section_body(section_id, body)
        self.code.setPlainText(text if text.endswith("\n") else text + "\n")
        self.code.blockSignals(False)
        self._loading = False
        self.sync_form_to_code()

    def _read_section_from_file(self, path: Path, section_id: str) -> str:
        try:
            text, _ = read_text(path)
        except Exception:
            return ""
        m = re.search(
            rf"(?im)^\[{re.escape(section_id)}(?:\s*:[^\]]*)?\][^\n]*\r?\n?",
            text,
        )
        if not m:
            return ""
        start = m.start()
        rest = text[m.end():]
        nxt = re.search(r"(?m)^\[", rest)
        end = m.end() + (nxt.start() if nxt else len(rest))
        return text[start:end]

    def sync_form_to_code(self):
        if self._loading or not self.current_id:
            return
        form_map = {k.lower(): (k, self._widget_value(w)) for k, w in self.entries.items()}
        old_lines = self.code.toPlainText().splitlines()
        new_lines: List[str] = []
        written = set()
        if old_lines and old_lines[0].strip().startswith("["):
            new_lines.append(old_lines[0].rstrip())
            rest = old_lines[1:]
        else:
            new_lines.append(f"[{self.current_id}]")
            rest = old_lines

        for line in rest:
            clean = line.split(";")[0].strip()
            if "=" in clean and not clean.startswith("["):
                k = clean.split("=", 1)[0].strip().lower()
                if k in form_map:
                    rk, val = form_map[k]
                    if val != "":
                        new_lines.append(f"{rk}={val}")
                    written.add(k)
                else:
                    new_lines.append(line.rstrip())
            else:
                if line.strip() or (new_lines and new_lines[-1].strip()):
                    new_lines.append(line.rstrip())

        for kl, (rk, val) in form_map.items():
            if kl not in written and val != "":
                new_lines.append(f"{rk}={val}")

        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
        self._loading = True
        self.code.setPlainText("\n".join(new_lines) + "\n")
        self._loading = False

    def add_key(self):
        if not self.current_id:
            QMessageBox.information(self, "添加", "请先选择一个图纸")
            return
        dlg = AddKeyDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        key = dlg.key_name()
        if not key:
            return
        if any(k.lower() == key.lower() for k in self.entries):
            QMessageBox.information(self, "添加", "该键已在表单中")
            return
        self.extra_keys.append(key)
        vals = {k: self._widget_value(w) for k, w in self.entries.items()}
        vals[key] = ""
        form_config = TAB_GROUPS[self.current_tab]["form"]
        self._loading = True
        self._clear_form()
        self._add_form_from_config(form_config, vals)
        self._loading = False
        self.sync_form_to_code()

    def deploy(self):
        if not self.current_id:
            QMessageBox.information(self, "部署", "请先选择图纸")
            return
        if not self.hotfix_path:
            self.choose_hotfix()
            if not self.hotfix_path:
                return
        self.sync_form_to_code()
        body = self.code.toPlainText()
        backup_root = self.hotfix_path.parent / "backups"
        exists = self.hotfix_path.exists()
        result = save_section_to_file(
            self.hotfix_path, self.current_id, body,
            backup_root=backup_root, is_new=not exists, peer_section_names=[],
        )
        if exists and (not result.get("ok") or "未找到" in (result.get("message") or "")):
            result = save_section_to_file(
                self.hotfix_path, self.current_id, body,
                backup_root=backup_root, is_new=True, peer_section_names=[],
            )
        if result.get("ok"):
            self._watch_mtime = self.hotfix_path.stat().st_mtime
            QTimer.singleShot(5000, self.clean_hotfix_silent)
            QMessageBox.information(
                self, "部署成功",
                f"[{self.current_id}] 已写入工程文件。\n游戏内热重载后生效。\n满意请用右下角「一键复制」带走完整代码。",
            )
            self.statusBar().showMessage(f"已部署 {self.current_id}", 6000)
        else:
            QMessageBox.critical(self, "部署失败", result.get("message", ""))

    def restore_default(self):
        if self.mode != "safe":
            QMessageBox.warning(self, "恢复原版", "高级模式下已禁用，请切回安全模式。")
            return
        if not self.current_id or not self.game:
            return
        if not self.hotfix_path:
            QMessageBox.information(self, "恢复", "请先绑定 hotfix.ini")
            return
        base = self.game.get_section_text(self.current_id)
        result = save_section_to_file(
            self.hotfix_path, self.current_id, base,
            backup_root=self.hotfix_path.parent / "backups",
            is_new=not self.hotfix_path.exists(), peer_section_names=[],
        )
        if not result.get("ok"):
            result = save_section_to_file(
                self.hotfix_path, self.current_id, base,
                backup_root=self.hotfix_path.parent / "backups",
                is_new=True, peer_section_names=[],
            )
        if result.get("ok"):
            self.load_section(self.current_id)
            QTimer.singleShot(5000, self.clean_hotfix_silent)
            QMessageBox.information(self, "恢复", f"[{self.current_id}] 已写回原版数值到 hotfix。")
        else:
            QMessageBox.critical(self, "恢复失败", result.get("message", ""))

    def clean_hotfix_silent(self):
        if not self.hotfix_path or not self.hotfix_path.exists() or not self.game:
            return
        if not self.current_id:
            return
        try:
            text, enc = read_text(self.hotfix_path)
        except Exception:
            return
        sid = self.current_id
        m = re.search(rf"(?im)^\[{re.escape(sid)}\][^\n]*\r?\n?", text)
        if not m:
            return
        start = m.end()
        rest = text[start:]
        nxt = re.search(r"(?m)^\[", rest)
        end = start + (nxt.start() if nxt else len(rest))
        block = text[start:end]
        base = self.game.get_section(sid)
        base_map = {}
        if base:
            for k, v in base.keys.items():
                base_map[k.lower()] = v.strip().lower()
        kill_default = {
            "attacheffect.animation": {"none", "0", ""},
            "attacheffect.duration": {"0"},
            "attacheffect.speedmultiplier": {"1", "1.0"},
            "attacheffect.armormultiplier": {"1", "1.0"},
            "attacheffect.firepowermultiplier": {"1", "1.0"},
            "attacheffect.rofmultiplier": {"1", "1.0"},
            "image": {sid.lower()},
        }
        new_lines = []
        has_custom = False
        for line in block.splitlines(keepends=True):
            clean = line.split(";")[0].strip()
            if "=" in clean:
                k, _, v = clean.partition("=")
                kl, vl = k.strip().lower(), v.strip().lower()
                if kl in base_map and base_map[kl] == vl:
                    continue
                if kl in kill_default and vl in kill_default[kl]:
                    continue
                has_custom = True
                new_lines.append(line if line.endswith("\n") else line + "\n")
            elif line.strip():
                new_lines.append(line if line.endswith("\n") else line + "\n")
        if not has_custom:
            new_text = text[: m.start()] + text[end:]
        else:
            header = text[m.start(): m.end()]
            new_text = text[: m.start()] + header + "".join(new_lines) + text[end:]
        try:
            self.hotfix_path.write_text(new_text, encoding=enc)
            self._watch_mtime = self.hotfix_path.stat().st_mtime
        except Exception:
            pass

    def copy_full_code(self):
        if not self.current_id or not self.game:
            QMessageBox.information(self, "复制", "请先选择图纸")
            return
        self.sync_form_to_code()
        base = self.game.get_section(self.current_id)
        ui = {k.lower(): (k, self._widget_value(w)) for k, w in self.entries.items()}
        lines = [f"[{self.current_id}]"]
        written = set()
        if base:
            for k in base.key_order:
                kl = k.lower()
                if kl in ui and ui[kl][1] != "":
                    lines.append(f"{ui[kl][0]}={ui[kl][1]}")
                    written.add(kl)
                else:
                    lines.append(f"{k}={base.keys.get(k, '')}")
                    written.add(kl)
        for kl, (k, v) in ui.items():
            if kl not in written and v != "":
                lines.append(f"{k}={v}")
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        QMessageBox.information(
            self, "复制成功",
            "✅ 完整代码（原版底包 + 修改）已复制到剪贴板。\n可直接粘贴覆盖源 INI 区块。",
        )

    def _file_watch(self):
        if not self.hotfix_path or not self.hotfix_path.exists():
            return
        try:
            mt = self.hotfix_path.stat().st_mtime
        except Exception:
            return
        if mt > self._watch_mtime + 0.2 and self.current_id:
            self._watch_mtime = mt
            body = self._read_section_from_file(self.hotfix_path, self.current_id)
            if body.strip():
                self.code.blockSignals(True)
                self.code.setPlainText(body if body.endswith("\n") else body + "\n")
                self.code.blockSignals(False)

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("战术工坊 2.x")
    app.setStyle("Fusion")
    win = WorkshopWindow()
    win.show()
    last = win.settings.get("last_game_dir")
    if last and Path(last).is_dir():
        try:
            win.game = GameProject(Path(last), win._profile())
            if win.game.rules:
                win.dir_label.setText(
                    f"游戏目录：{last}  |  CSF {len(win.game.csf.strings)} 条"
                )
                win.refresh_tree()
        except Exception:
            pass
    hf = win.settings.get("last_hotfix")
    if hf and Path(hf).exists():
        win.hotfix_path = Path(hf)
        win.path_edit.setText(hf)
        win.path_edit.setStyleSheet("color:#00ff00;")
    sys.exit(app.exec())
