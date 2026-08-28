"""
单单位调试窗口
- 左：代码预览（次要、可拖条）
- 右：属性（主区域）三行：参数名 / 说明 / 值
- 辅助模式：引用键用可编辑下拉，行高与输入框一致
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Callable, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QWidget, QFrame, QMessageBox, QPlainTextEdit, QSplitter,
    QComboBox, QCheckBox, QInputDialog, QFileDialog, QSizePolicy,
)

from PySide6.QtCore import QObject, QEvent
from core.project import Project
from core.save_util import save_section_to_file, normalize_section_body


PRIORITY_KEYS = [
    "UIName", "Name", "Image", "Strength", "Armor", "Category", "TechLevel",
    "Cost", "Points", "Owner", "Prerequisite", "Primary", "Secondary",
    "ElitePrimary", "EliteSecondary", "Sight", "Speed", "ROF", "Damage",
    "Range", "Warhead", "Projectile", "Locomotor",
]

REF_KEY_SOURCES = {
    "primary": "weapons", "secondary": "weapons",
    "eliteprimary": "weapons", "elitesecondary": "weapons",
    "occupyweapon": "weapons", "eliteoccupyweapon": "weapons",
    "deathweapon": "weapons", "weapon": "weapons",
    "warhead": "warheads", "projectile": "projectiles",
    "armor": "armors", "image": "images", "locomotor": "locomotors",
}

BOOLISH = {"yes", "no", "true", "false", "1", "0"}
DEFAULT_ARMORS = ["none", "flak", "plate", "light", "medium", "heavy", "wood", "steel", "concrete"]
DEFAULT_LOCOMOTORS = [
    "{4A582744-9839-11d1-B709-00A024D04B5C}",
    "{4A582746-9839-11d1-B709-00A024D04B5C}",
    "{4A582741-9839-11d1-B709-00A024D04B5C}",
    "{4A582742-9839-11d1-B709-00A024D04B5C}",
    "{4A582743-9839-11d1-B709-00A024D04B5C}",
    "{4A582745-9839-11d1-B709-00A024D04B5C}",
]


class NoWheelFilter(QObject):
    """禁止在输入框/下拉合拢时用滚轮改值，避免误触。"""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, QComboBox) and obj.view().isVisible():
                return False
            return True
        return super().eventFilter(obj, event)


class DebugWindow(QDialog):

    def __init__(
        self,
        project: Project,
        section_id: str,
        initial_text: str,
        schema: dict,
        parent=None,
        on_written_back: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(parent)
        self.project = project
        self.section_id = section_id
        self.schema = schema or {}
        self.on_written_back = on_written_back
        self.entries: Dict[str, QWidget] = {}
        self._loading = False
        self._no_wheel = NoWheelFilter(self)
        self._option_cache: Dict[str, List[str]] = {}

        st = (project.config.get("settings") or {})
        self.assist_mode = bool(st.get("debug_assist_mode", True))
        w = int(st.get("debug_window_width", 900))
        h = int(st.get("debug_window_height", 680))

        self.setWindowTitle(f"调试 · {section_id}")
        self.resize(w, h)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        head = QLabel(f"单位 / Section：{section_id}")
        head.setStyleSheet("font-size:15px; font-weight:600; color:#c4b5fd;")
        root.addWidget(head)

        src = project.get_source_path_for_section(section_id)
        src_lab = QLabel(f"工程来源：{src or '（未知）'}")
        src_lab.setStyleSheet("color:#7dd3fc; font-size:12px;")
        src_lab.setWordWrap(True)
        root.addWidget(src_lab)

        hr = project.config.get("hotreload") or {}
        hf = QLabel(f"热重载目标：{hr.get('target_ini') or 'hotfix.ini'}")
        hf.setStyleSheet("color:#9a9a9a; font-size:11px;")
        root.addWidget(hf)

        mode_row = QHBoxLayout()
        self.chk_assist = QCheckBox("辅助模式（引用字段可下拉，仍可手输）")
        self.chk_assist.setChecked(self.assist_mode)
        self.chk_assist.toggled.connect(self._on_assist_toggled)
        mode_row.addWidget(self.chk_assist)
        mode_row.addStretch()
        root.addLayout(mode_row)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(6)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        code_panel = QWidget()
        code_panel.setObjectName("codePanel")
        code_panel.setMinimumWidth(160)
        cl = QVBoxLayout(code_panel)
        cl.setContentsMargins(8, 8, 8, 8)
        cl.addWidget(QLabel("代码预览"))
        self.code = QPlainTextEdit()
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code.setObjectName("codeEdit")
        cl.addWidget(self.code, 1)
        split.addWidget(code_panel)

        form_panel = QWidget()
        form_panel.setObjectName("formPanel")
        fl = QVBoxLayout(form_panel)
        fl.setContentsMargins(8, 8, 8, 8)
        fl.addWidget(QLabel("参数（参数名 / 说明 / 值）"))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.form_inner = QWidget()
        self.form_inner.setObjectName("formInner")
        self.form_layout = QVBoxLayout(self.form_inner)
        self.form_layout.setAlignment(Qt.AlignTop)
        self.form_layout.setSpacing(0)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.form_inner)
        fl.addWidget(self.scroll, 1)
        split.addWidget(form_panel)

        split.setSizes([240, 620])
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)

        row = QHBoxLayout()
        self.btn_add = QPushButton("+ 添加属性")
        self.btn_add.clicked.connect(self.add_key)
        self.btn_sync = QPushButton("从表单刷新代码")
        self.btn_sync.clicked.connect(self.sync_form_to_code)
        self.btn_deploy = QPushButton("部署到 hotfix")
        self.btn_deploy.setObjectName("primaryBtn")
        self.btn_deploy.clicked.connect(self.deploy_hotfix)
        self.btn_writeback = QPushButton("保存到工程文件")
        self.btn_writeback.clicked.connect(self.write_back)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_add, self.btn_sync, self.btn_deploy, self.btn_writeback, self.btn_close):
            row.addWidget(b)
        root.addLayout(row)

        self.setStyleSheet("""
            QDialog { background: #1e1e1e; color: #e8e8e8; }
            QWidget#codePanel, QWidget#formPanel {
                background: #252526; border: 1px solid #3c3c3c; border-radius: 4px;
            }
            QWidget#formInner { background: #252526; }
            QPlainTextEdit#codeEdit {
                background: #0a0a0a; color: #00cc66;
                border: 1px solid #333; border-radius: 3px;
                font-family: Consolas, monospace; font-size: 12px;
            }
            QFrame#propRow {
                background: #2d2d30;
                border: none;
            }
            QFrame#propSep {
                background: #c8c8d0;
                border: none;
                max-height: 1px;
                min-height: 1px;
            }
            QLabel#propKey { font-weight: 700; font-size: 13px; color: #fff; }
            QLabel#propDesc { color: #a8a8b0; font-size: 11px; }
            QLineEdit {
                background: #1e1e1e; color: #f0f0f0;
                border: 1px solid #555; border-radius: 3px;
                padding: 4px 8px;
                min-height: 24px;
                max-height: 28px;
            }
            QComboBox {
                background: #1e1e1e; color: #f0f0f0;
                border: 1px solid #555; border-radius: 3px;
                padding: 4px 28px 4px 8px;
                min-height: 24px;
                max-height: 28px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 22px;
                border-left: 1px solid #555;
                background: #3a3a42;
            }
            QComboBox::down-arrow {
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e1e; color: #f0f0f0;
                selection-background-color: #5b4b8a;
                border: 1px solid #555;
            }
            QPushButton {
                background: #3c3c3c; border: 1px solid #555; border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #4a4a4a; }
            QPushButton#primaryBtn {
                background: #8b1a1a; border-color: #a33; color: #fff; font-weight: 600;
            }
            QCheckBox { color: #ddd; spacing: 8px; }
            QScrollArea { border: none; background: #252526; }
            QSplitter::handle { background: #555; width: 6px; }
            QSplitter::handle:hover { background: #6d28d9; }
        """)

        self._load_from_text(initial_text)

    def closeEvent(self, event):
        st = self.project.config.setdefault("settings", {})
        st["debug_window_width"] = self.width()
        st["debug_window_height"] = self.height()
        st["debug_assist_mode"] = self.chk_assist.isChecked()
        try:
            self.project.save_config()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_assist_toggled(self, checked: bool):
        self.assist_mode = checked
        st = self.project.config.setdefault("settings", {})
        st["debug_assist_mode"] = checked
        try:
            self.project.save_config()
        except Exception:
            pass
        self._load_from_text(self.code.toPlainText())

    def _get_options(self, kind: str) -> List[str]:
        if kind in self._option_cache:
            return self._option_cache[kind]
        opts: List[str] = []
        ini = self.project.rules or self.project.active_ini()
        if kind == "weapons":
            opts = self._list_from_type(ini, "WeaponTypes")
        elif kind == "warheads":
            opts = self._list_from_type(ini, "Warheads")
        elif kind == "projectiles":
            opts = self._list_from_type(ini, "ProjectileTypes")
        elif kind == "armors":
            opts = list(DEFAULT_ARMORS)
        elif kind == "locomotors":
            opts = list(DEFAULT_LOCOMOTORS)
        elif kind == "images":
            if ini:
                for ln in ("InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes"):
                    opts.extend(self._list_from_type(ini, ln))
            seen, uniq = set(), []
            for x in opts:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            opts = uniq
        elif kind == "bool":
            opts = ["yes", "no", "true", "false"]
        self._option_cache[kind] = opts
        return opts

    def _list_from_type(self, ini, list_name: str) -> List[str]:
        if not ini:
            return []
        try:
            return list(ini.get_list(list_name) or [])
        except Exception:
            return []

    def _ref_kind_for_key(self, key: str, value: str) -> Optional[str]:
        if not self.assist_mode:
            return None
        kl = key.lower()
        if kl in REF_KEY_SOURCES:
            return REF_KEY_SOURCES[kl]
        if value.strip().lower() in BOOLISH:
            return "bool"
        return None

    def _clear_form(self):
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.entries.clear()

    def _ordered_keys(self, keys: Dict[str, str]) -> list:
        lower_map = {k.lower(): k for k in keys}
        ordered, seen = [], set()
        for pk in PRIORITY_KEYS:
            if pk.lower() in lower_map:
                real = lower_map[pk.lower()]
                ordered.append(real)
                seen.add(real.lower())
        for k in keys:
            if k.lower() not in seen:
                ordered.append(k)
        return ordered

    def _widget_value(self, w: QWidget) -> str:
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QLineEdit):
            return w.text()
        return ""

    def _add_row(self, key: str, value: str):
        box = QFrame()
        box.setObjectName("propRow")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        kl = QLabel(key)
        kl.setObjectName("propKey")
        lay.addWidget(kl)

        desc = (self.schema.get(key) or {}).get("desc_zh") or (self.schema.get(key) or {}).get("desc_en") or ""
        dl = QLabel(desc if desc else "（暂无说明）")
        dl.setObjectName("propDesc")
        dl.setWordWrap(True)
        dl.setMaximumHeight(36)
        lay.addWidget(dl)

        kind = self._ref_kind_for_key(key, value)
        if kind:
            combo = QComboBox()
            combo.setEditable(True)
            combo.setFixedHeight(28)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            opts = self._get_options(kind)
            items = []
            if value and value not in opts:
                items.append(value)
            items.extend(opts)
            combo.addItems(items)
            combo.setCurrentText(value)
            combo.setInsertPolicy(QComboBox.NoInsert)
            combo.installEventFilter(self._no_wheel)
            if combo.lineEdit():
                combo.lineEdit().installEventFilter(self._no_wheel)
            lay.addWidget(combo)
            self.entries[key] = combo
        else:
            edit = QLineEdit(value)
            edit.setFixedHeight(28)
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            edit.installEventFilter(self._no_wheel)
            lay.addWidget(edit)
            self.entries[key] = edit

        self.form_layout.addWidget(box)

        sep = QFrame()
        sep.setObjectName("propSep")
        sep.setFixedHeight(1)
        self.form_layout.addWidget(sep)

    def _load_from_text(self, text: str):
        self._loading = True
        self._clear_form()
        body = normalize_section_body(self.section_id, text)
        keys: Dict[str, str] = {}
        for line in body.splitlines():
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
        for k in self._ordered_keys(keys):
            self._add_row(k, keys[k])
        self.code.blockSignals(True)
        self.code.setPlainText(body if body.endswith("\n") else body + "\n")
        self.code.blockSignals(False)
        self._loading = False

    def sync_form_to_code(self):
        lines = [f"[{self.section_id}]"]
        for key, w in self.entries.items():
            lines.append(f"{key}={self._widget_value(w)}")
        self._loading = True
        self.code.setPlainText("\n".join(lines) + "\n")
        self._loading = False

    def add_key(self):
        key, ok = QInputDialog.getText(self, "添加属性", "键名（如 Strength）:")
        if not ok or not key.strip():
            return
        key = key.strip()
        if key in self.entries:
            QMessageBox.information(self, "添加", "该键已存在")
            return
        self._add_row(key, "")
        self.sync_form_to_code()

    def current_body(self) -> str:
        if self.entries:
            self.sync_form_to_code()
        return self.code.toPlainText()

    def _hotfix_path(self) -> Path:
        hr = self.project.config.get("hotreload") or {}
        name = hr.get("target_ini") or "hotfix.ini"
        p = Path(name)
        if p.is_file():
            return p.resolve()
        if self.project.project_dir:
            return self.project.project_dir / name
        return p

    def deploy_hotfix(self):
        body = self.current_body()
        path = self._hotfix_path()
        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        exists = path.exists()
        result = save_section_to_file(
            path, self.section_id, body, backup_root=backup_root,
            is_new=not exists, peer_section_names=[],
        )
        if exists and (not result.get("ok") or "未找到" in (result.get("message") or "")):
            result = save_section_to_file(
                path, self.section_id, body, backup_root=backup_root,
                is_new=False, peer_section_names=[],
            )
            if not result.get("ok"):
                result = save_section_to_file(
                    path, self.section_id, body, backup_root=backup_root,
                    is_new=True, peer_section_names=[],
                )
        if result.get("ok"):
            QMessageBox.information(self, "已部署", f"[{self.section_id}] → {path}")
        else:
            QMessageBox.critical(self, "部署失败", result.get("message", ""))

    def write_back(self):
        body = self.current_body()
        path = self.project.get_source_path_for_section(self.section_id)
        is_new = False
        if path is None or not Path(path).is_file():
            path_str, _ = QFileDialog.getOpenFileName(
                self, "选择要回写的工程 INI",
                str(self.project.project_dir or Path.home()),
                "INI (*.ini)",
            )
            if not path_str:
                return
            path = Path(path_str)
            is_new = True
        else:
            path = Path(path)
        result = self.project.save_section_text(
            self.section_id, body, target_path=path, is_new=is_new, peer_ids=[]
        )
        if not result.get("ok"):
            backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
            result = save_section_to_file(
                path, self.section_id, body, backup_root=backup_root,
                is_new=is_new, peer_section_names=[],
            )
        if result.get("ok"):
            QMessageBox.information(self, "回写成功", result.get("message", f"已写回 {path}"))
            if self.on_written_back:
                self.on_written_back(self.section_id)
        else:
            QMessageBox.critical(self, "回写失败", result.get("message", ""))
