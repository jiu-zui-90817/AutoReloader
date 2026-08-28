
"""
PySide6 主界面
- 打开工程 / 打开单文件
- 合并视图 / 工程内单文件
- 工具菜单预留
- 新增单位向导（第一版）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional, List

from PySide6.QtCore import Qt, QTimer, QSize, QRect
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QTextCursor, QPainter, QColor, QFont, QTextFormat, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QLineEdit, QLabel, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QFileDialog, QToolBar,
    QStatusBar, QTabWidget, QSizePolicy, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QCheckBox, QTextEdit, QMenu, QListWidget, QListWidgetItem, QAbstractItemView,
)

from core.project import Project
from paths import app_dir, bundle_dir, user_config_path, user_cache_dir, is_frozen

APP_TITLE = "INI 工程编辑器"
APP_TITLE_EN = "INI Project Editor"
APP_VERSION = "2.0"

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class CodeEditor(QPlainTextEdit):
    """带行号的代码编辑框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(max(1, self.blockCount()))))
        # 左右留白，避免数字贴边或盖住正文
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _=0):
        w = self.line_number_area_width()
        self.setViewportMargins(w, 0, 0, 0)
        self._sync_line_area_geometry()

    def _sync_line_area_geometry(self):
        cr = self.contentsRect()
        w = self.line_number_area_width()
        self._line_area.setGeometry(QRect(cr.left(), cr.top(), w, cr.height()))

    def update_line_number_area(self, rect, dy):
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_line_number_area_width(0)

    def setPlainText(self, text: str):
        super().setPlainText(text)
        # setPlainText 后立刻按新行数调整边距，避免首屏行号盖住代码
        self.update_line_number_area_width(0)
        # 再延迟一帧，等布局完成（首次显示时 contentsRect 可能尚未稳定）
        QTimer.singleShot(0, lambda: self.update_line_number_area_width(0))

    def showEvent(self, event):
        super().showEvent(event)
        self.update_line_number_area_width(0)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor("#1a1a1e"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#6a6a75"))
                painter.drawText(
                    0, top, self._line_area.width() - 6,
                    height,
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def highlight_current_line(self):
        from PySide6.QtWidgets import QTextEdit
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#2a2a35"))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

from ui.debug_window import DebugWindow


# 新增时的简易模板
NEW_TEMPLATES = {
    "InfantryTypes": """[{id}]
UIName=Name:{id}
Name={id}
Image={id}
Category=Soldier
Primary=none
Strength=100
Armor=none
TechLevel=1
Sight=5
Speed=4
Owner=British,French,Germans,Americans,Alliance
Cost=100
Points=5
Prerequisite=none
""",
    "VehicleTypes": """[{id}]
UIName=Name:{id}
Name={id}
Image={id}
Category=Armored
Primary=none
Strength=200
Armor=light
TechLevel=2
Sight=6
Speed=6
Owner=British,French,Germans,Americans,Alliance
Cost=500
Points=25
Prerequisite=none
""",
    "AircraftTypes": """[{id}]
UIName=Name:{id}
Name={id}
Image={id}
Strength=150
Armor=light
TechLevel=5
Sight=8
Speed=12
Owner=British,French,Germans,Americans,Alliance
Cost=1000
Points=30
Prerequisite=none
""",
    "BuildingTypes": """[{id}]
UIName=Name:{id}
Name={id}
Image={id}
BuildCat=Combat
Strength=500
Armor=concrete
TechLevel=1
Sight=5
Owner=British,French,Germans,Americans,Alliance
Cost=500
Points=30
Power=0
Prerequisite=none
""",
    "WeaponTypes": """[{id}]
Damage=25
ROF=20
Range=5
Projectile=Invisible
Warhead=SA
Report=none
""",
    "Warheads": """[{id}]
CellSpread=0.3
PercentAtMax=1
Verses=100%,100%,100%,100%,100%,100%,100%,100%,100%,100%,100%
""",
    "Animations": """[{id}]
Image={id}
LoopCount=-1
Rate=400
""",
    "Particles": """[{id}]
MaxDC=0
MaxEC=0
BehavesLike=Spark
""",
    "ParticleSystems": """[{id}]
HoldsWhat=none
BehavesLike=Smoke
""",
    "Projectiles": """[{id}]
Image=none
SubjectToCliffs=no
SubjectToElevation=no
SubjectToWalls=no
Proximity=no
Ranged=no
""",
}

TYPE_LABELS = {
    "InfantryTypes": "步兵 InfantryTypes",
    "VehicleTypes": "载具 VehicleTypes",
    "AircraftTypes": "飞行器 AircraftTypes",
    "BuildingTypes": "建筑 BuildingTypes",
    "WeaponTypes": "武器 WeaponTypes",
    "Warheads": "弹头 Warheads",
    "ProjectileTypes": "抛射体 ProjectileTypes",
    "SuperWeaponTypes": "超武 SuperWeaponTypes",
    "Animations": "动画 Animations",
    "Particles": "粒子 Particles",
    "ParticleSystems": "粒子系统 ParticleSystems",
    "Projectiles": "抛射体(Ares) Projectiles",
}


class NewUnitDialog(QDialog):
    """新增 section 向导：单位体文件任意选；注册表只可选「已有该注册表节」的文件。"""

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("新增")
        self.setMinimumWidth(460)
        layout = QFormLayout(self)

        self.type_combo = QComboBox()
        for k in NEW_TEMPLATES:
            self.type_combo.addItem(TYPE_LABELS.get(k, k), k)
        self.type_combo.currentIndexChanged.connect(self._refresh_register_files)
        layout.addRow("类型（注册表）", self.type_combo)

        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("例如 MYINF1（注册名，勿重复）")
        layout.addRow("注册名", self.id_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("可选，写入 Name=")
        layout.addRow("显示名 Name", self.name_edit)

        # 单位代码写入文件（不限制）
        self.body_combo = QComboBox()
        self._all_files = list(project.list_ini_files())
        if project.work_mode == "single" and project.single_path:
            sp = project.single_path.resolve()
            if sp not in [f.resolve() for f in self._all_files]:
                self._all_files.insert(0, sp)
        for f in self._all_files:
            self.body_combo.addItem(self._label(f), str(f))
        if self.body_combo.count() == 0:
            self.body_combo.addItem("（稍后手动选择…）", "")
        layout.addRow("写入单位代码到", self.body_combo)

        self.also_register = QCheckBox("同时写入注册表")
        self.also_register.setChecked(True)
        self.also_register.toggled.connect(self._on_reg_toggled)
        layout.addRow(self.also_register)

        self.reg_combo = QComboBox()
        layout.addRow("写入注册表到", self.reg_combo)
        self.reg_hint = QLabel("仅列出包含该注册表节（如 [InfantryTypes]）的文件")
        self.reg_hint.setStyleSheet("color:#b0b8c4; font-size:13px;")
        self.reg_hint.setWordWrap(True)
        layout.addRow(self.reg_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._refresh_register_files()
        self._on_reg_toggled(self.also_register.isChecked())

    def _label(self, f: Path) -> str:
        try:
            if self.project.project_dir:
                return str(f.relative_to(self.project.project_dir))
        except Exception:
            pass
        return f.name

    def _files_with_type_list(self, type_list: str) -> list:
        """只用工程加载时建好的索引，禁止再扫盘/重解析。"""
        files = self.project.files_with_type_list(type_list)
        if files:
            return files
        # 单文件模式：当前文件若带有该节
        if self.project.single_ini and self.project.single_path:
            if self.project.single_ini.get_section(type_list):
                return [self.project.single_path]
        return []

    def _refresh_register_files(self):
        type_list = self.type_combo.currentData() or "InfantryTypes"
        self.reg_combo.clear()
        files = self._files_with_type_list(type_list)
        for f in files:
            self.reg_combo.addItem(self._label(f), str(f))
        if not files:
            self.reg_combo.addItem("（没有文件含此注册表）", "")
            self.reg_hint.setText(
                f"当前没有文件包含 [{type_list}]。可取消勾选「同时写入注册表」，"
                f"或先在某个 ini 里建好该注册表节。"
            )
            self.reg_hint.setStyleSheet("color:#f59e0b; font-size:11px;")
        else:
            self.reg_hint.setText(f"仅列出包含 [{type_list}] 的文件（共 {len(files)} 个）")
            self.reg_hint.setStyleSheet("color:#b0b8c4; font-size:13px;")
            # 若当前单文件正好有注册表，优先选中
            if self.project.single_path:
                sp = str(self.project.single_path.resolve())
                for i in range(self.reg_combo.count()):
                    if self.reg_combo.itemData(i) and Path(self.reg_combo.itemData(i)).resolve() == Path(sp):
                        self.reg_combo.setCurrentIndex(i)
                        break

    def _on_reg_toggled(self, checked: bool):
        self.reg_combo.setEnabled(checked)
        self.reg_hint.setEnabled(checked)

    def _try_accept(self):
        sid = self.id_edit.text().strip()
        if not sid or any(c.isspace() for c in sid):
            QMessageBox.warning(self, "新增", "请填写有效的注册名（不能有空格）")
            return
        # 校验是否已存在
        if self.project.get_section(sid):
            QMessageBox.warning(
                self, "新增",
                f"注册名 [{sid}] 已存在于当前工程/文件中，请换一个名字。"
            )
            return
        if self.also_register.isChecked():
            reg = self.reg_combo.currentData()
            if not reg:
                QMessageBox.warning(
                    self, "新增",
                    "已勾选「同时写入注册表」，但没有可选的注册表文件。\n"
                    "请取消勾选，或换一个含有该注册表的类型/工程文件。"
                )
                return
        self.accept()

    def result_data(self) -> Optional[dict]:
        sid = self.id_edit.text().strip()
        if not sid:
            return None
        body = self.body_combo.currentData() or ""
        reg = self.reg_combo.currentData() or "" if self.also_register.isChecked() else ""
        return {
            "id": sid,
            "type_list": self.type_combo.currentData(),
            "name": self.name_edit.text().strip(),
            "also_register": self.also_register.isChecked() and bool(reg),
            "path": body,           # 单位代码
            "register_path": reg,   # 注册表文件（可与 body 不同）
        }



class PropPanel(QWidget):
    """只读属性说明面板：展示键 / 当前值 / 词典解释，不在此编辑。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        head = QLabel("属性说明")
        head.setStyleSheet("font-weight:600; font-size:15px; color:#e5e5e5;")
        outer.addWidget(head)

        self.title = QLabel("")
        self.title.setStyleSheet("font-weight:600; font-size:13px; color:#c4b5fd;")
        self.title.setWordWrap(True)
        outer.addWidget(self.title)

        self.hint = QLabel("此处只读。改数值请用中间代码区，或「打开调试」做热重载试调。")
        self.hint.setStyleSheet("color:#b0b8c4; font-size:13px;")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.inner = QWidget()
        self.inner.setStyleSheet("background: transparent;")
        self.form = QVBoxLayout(self.inner)
        self.form.setAlignment(Qt.AlignTop)
        self.form.setSpacing(4)
        self.scroll.setWidget(self.inner)
        outer.addWidget(self.scroll, 1)

    def clear(self):
        while self.form.count():
            item = self.form.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.title.setText("")

    def set_section(self, section_id: str, display: str, sec, schema: dict, src_name: str = "", on_jump_editor=None, on_jump_tree=None):
        self.clear()
        self._on_jump_editor = on_jump_editor  # callable(key)
        self._on_jump_tree = on_jump_tree  # callable(value)
        self._section_id = section_id
        self.title.setText(display or section_id)
        if src_name:
            lab = QLabel(f"来源: {src_name}")
            lab.setStyleSheet("color:#7dd3fc; font-size:11px;")
            lab.setWordWrap(True)
            self.form.addWidget(lab)
        if not sec:
            return
        keys = list(sec.key_order)
        TYPE_HINTS = {
            "animations", "voxelanims", "particles", "particlesystems",
            "weapontypes", "warheads", "projectiletypes", "projectiles",
            "infantrytypes", "vehicletypes", "aircrafttypes", "buildingtypes",
            "superweapontypes", "overlaytypes", "smudgetypes", "terraintypes",
            "countries", "sides", "colors", "attacheffecttypes",
            "taskforces", "scripttypes", "teamtypes", "aitriggertypes",
            "genericprerequisites", "aitriggertypesenable",
        }
        if section_id.lower() in TYPE_HINTS:
            tip = QLabel(
                f"[{section_id}] 为类型注册表（共 {len(keys)} 条）。"
                "属性区已隐藏，请在中间代码区编辑。"
            )
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#94a3b8; font-size:13px; padding:8px;")
            self.form.addWidget(tip)
            return
        for key in keys:
            value = sec.keys.get(key, "")
            box = QFrame()
            box.setObjectName("propRow")
            lay = QVBoxLayout(box)
            lay.setContentsMargins(6, 4, 6, 4)
            lay.setSpacing(2)
            row = QHBoxLayout()
            kl = QLabel(key)
            kl.setFixedWidth(118)
            kl.setStyleSheet("font-weight:600;")
            row.addWidget(kl)
            vl = QLabel(value)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vl.setStyleSheet("color:#e5e5e5;")
            vl.setWordWrap(True)
            row.addWidget(vl, 1)
            lay.addLayout(row)
            desc = (schema.get(key) or {}).get("desc_zh") or (schema.get(key) or {}).get("desc_en") or ""
            if desc:
                dl = QLabel(desc)
                dl.setStyleSheet("color:#b0b8c4; font-size:13px;")
                dl.setWordWrap(True)
                lay.addWidget(dl)
            else:
                dl = QLabel("（词典暂无说明，可在 common_flags.json 中补充）")
                dl.setStyleSheet("color:#8b919a; font-size:12px;")
                lay.addWidget(dl)
            box.setProperty("prop_key", key)
            box.setProperty("prop_value", value)
            # 左键：仅在编辑器中定位（按键名）；右键菜单另有对象树/编辑器
            box.mousePressEvent = self._make_row_click(box, key)
            box.setContextMenuPolicy(Qt.CustomContextMenu)
            box.customContextMenuRequested.connect(
                lambda pos, b=box, k=key, v=value: self._prop_menu(b, pos, k, v)
            )
            self.form.addWidget(box)

    def _make_row_click(self, box, key):
        def handler(event):
            if event.button() == Qt.LeftButton and callable(getattr(self, "_on_jump_editor", None)):
                self._on_jump_editor(key)
            QFrame.mousePressEvent(box, event)
        return handler

    def _prop_menu(self, box, pos, key, value):
        menu = QMenu(box)
        act_tree = menu.addAction("在对象树中定位")
        act_editor = menu.addAction("在编辑器中定位")
        menu.addSeparator()
        act_copy_key = menu.addAction("复制键名")
        act_copy_val = menu.addAction("复制值")
        act_copy_line = menu.addAction("复制整行 (键=值)")
        menu.addSeparator()
        act_select = menu.addAction("全选属性文本")
        chosen = menu.exec(box.mapToGlobal(pos))
        clip = QApplication.clipboard()
        if chosen == act_tree and callable(getattr(self, "_on_jump_tree", None)):
            self._on_jump_tree(value, silent=False)
        elif chosen == act_editor and callable(getattr(self, "_on_jump_editor", None)):
            self._on_jump_editor(key)
        elif chosen == act_copy_key:
            clip.setText(key)
        elif chosen == act_copy_val:
            clip.setText(value)
        elif chosen == act_copy_line:
            clip.setText(f"{key}={value}")
        elif chosen == act_select:
            for lab in box.findChildren(QLabel):
                if lab.text() == value:
                    if hasattr(lab, "setSelection"):
                        lab.setSelection(0, len(value))
                    break


class ProjectSearchDialog(QDialog):
    """全工程搜索 / 引用查找。双击结果跳转。"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.win = parent
        self.setWindowTitle("全工程搜索")
        self.resize(720, 480)

        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; font-size: 14px; }
            QLineEdit, QListWidget, QCheckBox {
                background: #252830; color: #f1f3f5;
                border: 1px solid #3d4450; border-radius: 4px;
                font-size: 14px; padding: 4px 6px;
            }
            QListWidget { font-size: 14px; outline: none; }
            QListWidget::item { padding: 6px 8px; color: #f1f3f5; }
            QListWidget::item:selected { background: #3b82f6; color: #ffffff; }
            QListWidget::item:hover { background: #2f3542; }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover { background: #3d4450; }
            QCheckBox { color: #e8eaed; font-size: 13px; spacing: 6px; }
        """)

        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("节名 / 键名 / 值；或 Primary=M60；或仅 ID 再点「查找引用」")
        self.edit.returnPressed.connect(self.do_search)
        row.addWidget(self.edit, 1)
        b = QPushButton("搜索")
        b.clicked.connect(self.do_search)
        row.addWidget(b)
        b2 = QPushButton("查找引用")
        b2.setToolTip("把输入当作 ID，查找谁在值里引用了它")
        b2.clicked.connect(self.do_refs)
        row.addWidget(b2)
        lay.addLayout(row)

        opt = QHBoxLayout()
        self.cb_sec = QCheckBox("节名")
        self.cb_sec.setChecked(True)
        self.cb_key = QCheckBox("键名")
        self.cb_key.setChecked(True)
        self.cb_val = QCheckBox("值")
        self.cb_val.setChecked(True)
        opt.addWidget(self.cb_sec)
        opt.addWidget(self.cb_key)
        opt.addWidget(self.cb_val)
        opt.addStretch(1)
        lay.addLayout(opt)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(self._jump)
        lay.addWidget(self.list, 1)

        self.status = QLabel("")
        lay.addWidget(self.status)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        lay.addWidget(bb)

        self._hits = []

    def do_search(self):
        from core.project_index import search_project
        q = self.edit.text().strip()
        if not q:
            return
        hits = search_project(
            self.win.project, q,
            in_section=self.cb_sec.isChecked(),
            in_key=self.cb_key.isChecked(),
            in_value=self.cb_val.isChecked(),
        )
        self._fill(hits, f"搜索 {q!r}")

    def do_refs(self):
        from core.project_index import find_references
        q = self.edit.text().strip()
        if not q:
            return
        # 若是 Key=Val，取 Val
        if "=" in q:
            q = q.split("=", 1)[1].strip()
        hits = find_references(self.win.project, q)
        self._fill(hits, f"引用 {q!r}")

    def _fill(self, hits, title: str):
        self._hits = hits
        self.list.clear()
        for h in hits:
            item = QListWidgetItem(h.label())
            item.setData(Qt.UserRole, h)
            self.list.addItem(item)
        self.status.setText(f"{title} — 共 {len(hits)} 条（双击跳转）")

    def _jump(self, item: QListWidgetItem):
        h = item.data(Qt.UserRole)
        if not h:
            return
        prefer = ""
        if h.source == "art":
            prefer = "art"
        elif h.source == "ai":
            prefer = "ai"
        self.win.open_section_tab(h.section_id, prefer=prefer)
        if h.key:
            self.win.jump_to_editor_key(h.key)
        self.win.statusBar().showMessage(f"已跳转 {h.section_id}.{h.key}", 5000)


class LintDialog(QDialog):
    # 按严重级别着色（样式表不强制 item 前景色，否则会盖掉 setForeground）
    _SEV_COLOR = {
        "error": QColor("#ff6b6b"),
        "warning": QColor("#ffc107"),
        "info": QColor("#64b5f6"),
    }
    _SEV_RANK = {"error": 0, "warning": 1, "info": 2}

    def __init__(self, parent: "MainWindow", issues: list, title: str = "校验结果"):
        super().__init__(parent)
        self.win = parent
        self.setWindowTitle(title)
        self.resize(820, 520)
        self._issues = list(issues or [])

        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; font-size: 13px; }
            QLineEdit, QComboBox {
                background: #252830; color: #f1f3f5; border: 1px solid #3d4450;
                border-radius: 4px; padding: 4px 8px; font-size: 13px; min-height: 28px;
            }
            QListWidget {
                background: #252830; border: 1px solid #3d4450; border-radius: 4px;
                font-size: 14px; outline: none; padding: 2px;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background: #3b82f6; }
            QListWidget::item:hover { background: #2f3542; }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover { background: #3d4450; }
            QCheckBox { color: #e8eaed; font-size: 13px; spacing: 6px; }
        """)

        lay = QVBoxLayout(self)

        # —— 顶栏：搜索 / 级别筛选 / 排序 ——
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索节名、键、消息…")
        self.search.textChanged.connect(self._rebuild_list)
        bar.addWidget(self.search, 2)

        self.cb_error = QCheckBox("错误")
        self.cb_warn = QCheckBox("警告")
        self.cb_info = QCheckBox("信息")
        n_err = sum(1 for i in self._issues if (i.severity or "").lower() == "error")
        n_warn = sum(1 for i in self._issues if (i.severity or "").lower() == "warning")
        n_info = sum(1 for i in self._issues if (i.severity or "").lower() == "info")
        self.cb_error.setText(f"错误 ({n_err})")
        self.cb_warn.setText(f"警告 ({n_warn})")
        self.cb_info.setText(f"信息 ({n_info})")
        self.cb_error.setChecked(True)
        self.cb_warn.setChecked(True)
        self.cb_info.setChecked(n_info > 0 and n_err + n_warn == 0)  # 仅有 info 时默认勾上
        if n_err or n_warn:
            self.cb_info.setChecked(False)  # 有硬问题时默认先藏 info，界面清爽
        for cb in (self.cb_error, self.cb_warn, self.cb_info):
            cb.stateChanged.connect(self._rebuild_list)
            bar.addWidget(cb)

        bar.addWidget(QLabel("排序"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("按严重级别", "severity")
        self.sort_combo.addItem("按节名", "section")
        self.sort_combo.addItem("按来源", "source")
        self.sort_combo.addItem("按消息", "message")
        self.sort_combo.currentIndexChanged.connect(self._rebuild_list)
        bar.addWidget(self.sort_combo)
        lay.addLayout(bar)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._jump)
        lay.addWidget(self.list, 1)

        self.status = QLabel("")
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.btn_continue = QPushButton("仍然保存")
        self.btn_cancel = QPushButton("取消")
        self.btn_continue.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_continue)
        lay.addLayout(row)

        self._rebuild_list()

    def _filtered_sorted(self) -> list:
        q = (self.search.text() or "").strip().lower()
        allow = set()
        if self.cb_error.isChecked():
            allow.add("error")
        if self.cb_warn.isChecked():
            allow.add("warning")
        if self.cb_info.isChecked():
            allow.add("info")

        rows = []
        for iss in self._issues:
            sev = (iss.severity or "info").lower()
            if sev not in allow:
                continue
            if q:
                blob = f"{iss.section_id} {iss.key} {iss.message} {iss.source} {sev}".lower()
                if q not in blob:
                    continue
            rows.append(iss)

        mode = self.sort_combo.currentData() or "severity"
        if mode == "severity":
            rows.sort(key=lambda i: (
                self._SEV_RANK.get((i.severity or "info").lower(), 9),
                (i.section_id or "").lower(),
                (i.key or "").lower(),
            ))
        elif mode == "section":
            rows.sort(key=lambda i: (
                (i.section_id or "").lower(),
                self._SEV_RANK.get((i.severity or "info").lower(), 9),
            ))
        elif mode == "source":
            rows.sort(key=lambda i: (
                (i.source or "").lower(),
                self._SEV_RANK.get((i.severity or "info").lower(), 9),
                (i.section_id or "").lower(),
            ))
        else:
            rows.sort(key=lambda i: ((i.message or "").lower(), (i.section_id or "").lower()))
        return rows

    def _rebuild_list(self, *_args):
        self.list.clear()
        rows = self._filtered_sorted()
        for iss in rows:
            item = QListWidgetItem(iss.label())
            item.setData(Qt.UserRole, iss)
            sev = (iss.severity or "info").lower()
            item.setForeground(self._SEV_COLOR.get(sev, self._SEV_COLOR["info"]))
            self.list.addItem(item)
        total = len(self._issues)
        self.status.setText(
            f"显示 {len(rows)} / 共 {total} 条（双击跳转）"
            + (" · 提示：默认隐藏「信息」，可勾选查看废弃/重复等" if not self.cb_info.isChecked() and total > len(rows) else "")
        )

    def _jump(self, item):
        iss = item.data(Qt.UserRole)
        if not iss:
            return
        prefer = "art" if iss.source == "art" else ("ai" if iss.source == "ai" else "")
        self.win.open_section_tab(iss.section_id, prefer=prefer)
        if iss.key:
            self.win.jump_to_editor_key(iss.key)



class MainWindow(QMainWindow):
    def __init__(self, project: Project):
        super().__init__()
        try:
            for cand in (
                app_dir() / "assets" / "editor.ico",
                app_dir().parent.parent / "assets" / "editor.ico",
                Path(__file__).resolve().parents[3] / "assets" / "editor.ico",
            ):
                if cand.is_file():
                    self.setWindowIcon(QIcon(str(cand)))
                    break
        except Exception:
            pass
        self.project = project
        self.flag_schema: dict = {}
        self._display_cache: Dict[str, str] = {}
        self.current_section_id: Optional[str] = None
        self.current_prefer: str = ""
        self.current_group: str = ""  # 树分组，消歧同名 section
        self._mem_sections: Dict[str, str] = {}
        self._dirty = False
        self._loading_section = False
        self._file_map: Dict[str, Path] = {}
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self.refresh_tree)

        # 工具扩展点：name -> callable
        self.tool_registry: Dict[str, callable] = {}

        self._load_schema()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._apply_style()
        self._register_builtin_tools()
        self._update_chrome()
        self.statusBar().showMessage("文件 → 打开游戏文件夹 / 打开单文件")

    def _load_schema(self):
        """开发：shared 唯一源；打包：exe 旁 / _MEIPASS 内的 schemas。"""
        import sys
        candidates = []
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            meipass = getattr(sys, "_MEIPASS", None)
            candidates += [
                exe_dir / "schemas" / "common_flags.json",
                exe_dir / "shared" / "schemas" / "common_flags.json",
            ]
            if meipass:
                mp = Path(meipass)
                candidates += [
                    mp / "schemas" / "common_flags.json",
                    mp / "shared" / "schemas" / "common_flags.json",
                ]
        else:
            here = Path(__file__).resolve().parent.parent  # Frontend/editor
            repo = here.parents[1]  # repo root (editor -> Frontend -> root)
            candidates += [
                repo / "shared" / "schemas" / "common_flags.json",
                here / "schemas" / "common_flags.json",
            ]
        for path in candidates:
            try:
                if path.is_file():
                    self.flag_schema = json.loads(path.read_text(encoding="utf-8"))
                    return
            except Exception:
                continue
        self.flag_schema = {}

    def register_tool(self, name: str, callback, menu_text: str = None):
        """供未来插件/功能注册到「工具」菜单。"""
        self.tool_registry[name] = callback
        act = QAction(menu_text or name, self)
        act.triggered.connect(callback)
        self.menu_tools.addAction(act)

    def _register_builtin_tools(self):
        self.register_tool(
            "reload_csf",
            self._tool_reload_csf,
            "重新加载 CSF 字符串表",
        )
        self.menu_tools.addSeparator()
        # AutoReloader 搭配
        act_hr = QAction("热重载（AutoReloader）", self)
        act_hr.setEnabled(False)
        self.menu_tools.addAction(act_hr)
        self.register_tool(
            "deploy_hotfix",
            self._tool_deploy_hotfix,
            "部署当前单位到 hotfix.ini",
        )
        self.register_tool(
            "deploy_hotfix_save",
            self._tool_deploy_hotfix_and_save,
            "保存工程 + 部署到 hotfix",
        )
        self.register_tool(
            "set_hotfix_path",
            self._tool_set_hotfix_path,
            "设置 hotfix 路径…",
        )
        self.register_tool(
            "open_hotfix",
            self._tool_open_hotfix,
            "打开 hotfix 文件",
        )

    def _tool_reload_csf(self):
        if not self.project.project_dir:
            QMessageBox.information(self, "CSF", "请先打开工程目录（CSF 从工程加载）")
            return
        from core.csf_parser import load_csf_files
        self.project.csf = load_csf_files(
            self.project.profile.get("csf_files", []), self.project.project_dir
        )
        self._display_cache.clear()
        self.refresh_tree()
        QMessageBox.information(self, "CSF", f"已重新加载，共 {len(self.project.csf.strings)} 条")

    def _hotfix_path(self) -> Optional[Path]:
        hr = self.project.config.get("hotreload") or {}
        name = hr.get("target_ini") or "hotfix.ini"
        p = Path(name)
        if p.is_file():
            return p.resolve()
        if self.project.project_dir:
            cand = self.project.project_dir / name
            return cand
        return p

    def _tool_set_hotfix_path(self):
        cur = self._hotfix_path()
        path_str, _ = QFileDialog.getSaveFileName(
            self, "设置 hotfix / 热重载目标 INI",
            str(cur or self.project.project_dir or Path.home()),
            "INI (*.ini)",
        )
        if not path_str:
            return
        path = Path(path_str)
        hr = self.project.config.setdefault("hotreload", {})
        # 若在工程目录下，存相对名，方便移植
        if self.project.project_dir:
            try:
                rel = path.resolve().relative_to(self.project.project_dir.resolve())
                hr["target_ini"] = str(rel)
            except ValueError:
                hr["target_ini"] = str(path.resolve())
        else:
            hr["target_ini"] = str(path.resolve())
        self.project.save_config()
        QMessageBox.information(self, "热重载", f"目标文件已设为:\n{hr['target_ini']}")

    def _tool_open_hotfix(self):
        path = self._hotfix_path()
        if not path or not path.exists():
            QMessageBox.information(self, "热重载", f"文件还不存在:\n{path}\n部署一次后会创建。")
            return
        if not self.project.open_single_file(path):
            QMessageBox.warning(self, "热重载", "无法打开该文件")
            return
        self.project._add_allowed(path)
        self._refresh_file_combo()
        self.act_single.setChecked(True)
        self.file_row.show()
        self._display_cache.clear()
        self.tabs.clear()
        self._dirty = False
        self._update_chrome()
        self.refresh_tree()

    def _tool_deploy_hotfix(self):
        """把当前节部署到 hotfix.ini（AutoReloader TargetINI），不改工程源文件。"""
        if not self.current_section_id:
            QMessageBox.information(self, "热重载", "请先选择一个单位/section")
            return
        path = self._hotfix_path()
        if path is None:
            QMessageBox.information(self, "热重载", "请先在「首选项」或菜单中设置 hotfix 路径")
            return
        from core.save_util import normalize_section_body, save_section_to_file

        sid = self.current_section_id
        body = normalize_section_body(sid, self.code.toPlainText())
        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        result = save_section_to_file(
            path, sid, body, backup_root=backup_root,
            is_new=not path.exists(), peer_section_names=[],
        )
        if result.get("ok"):
            self.statusBar().showMessage(f"已部署 [{sid}] → {path.name}", 8000)
            QMessageBox.information(
                self, "已部署到热重载文件",
                f"[{sid}] 已写入:\n{path}\n\n"
                f"请确认游戏目录 ReloaderConfig.ini 的 TargetINI 包含该文件名，\n"
                f"并用启动器以管理员运行游戏；保存后 AutoMonitor 或热键即可重载。",
            )
        else:
            QMessageBox.critical(self, "部署失败", result.get("message", ""))

    def _tool_deploy_hotfix_and_save(self):

        self.save_current()
        if self._dirty:
            return
        self._tool_deploy_hotfix()

    def _build_menu(self):
        mb = self.menuBar()

        m_file = mb.addMenu("文件(&F)")
        act_open = QAction("打开游戏文件夹…", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self.open_project)
        m_file.addAction(act_open)

        act_open_file = QAction("打开单文件…", self)
        act_open_file.setShortcut(QKeySequence("Ctrl+Shift+O"))
        act_open_file.triggered.connect(self.open_loose_file)
        m_file.addAction(act_open_file)

        m_file.addSeparator()
        act_save_cur = QAction("保存当前单位", self)
        act_save_cur.setShortcut(QKeySequence("Ctrl+S"))
        act_save_cur.triggered.connect(self.save_current)
        m_file.addAction(act_save_cur)

        act_save_all = QAction("保存全部", self)
        act_save_all.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_all.triggered.connect(self.save_all)
        m_file.addAction(act_save_all)

        # 合并视图下很少需要；保留给「拷到别的文件」
        act_saveas = QAction("另存为…", self)
        act_saveas.triggered.connect(self.save_as)
        m_file.addAction(act_saveas)

        m_file.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_edit = mb.addMenu("编辑(&E)")
        act_find = QAction("查找…", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self.show_find_dialog)
        m_edit.addAction(act_find)
        act_find_next = QAction("查找下一个", self)
        act_find_next.setShortcut(QKeySequence("F3"))
        act_find_next.triggered.connect(self.find_next)
        m_edit.addAction(act_find_next)
        act_psearch = QAction("全工程搜索…", self)
        act_psearch.setShortcut(QKeySequence("Ctrl+Shift+F"))
        act_psearch.triggered.connect(self.show_project_search)
        m_edit.addAction(act_psearch)
        act_lint = QAction("校验当前节", self)
        act_lint.triggered.connect(self.lint_current_section)
        m_edit.addAction(act_lint)
        act_lint_all = QAction("校验整个工程", self)
        act_lint_all.triggered.connect(self.lint_whole_project)
        m_edit.addAction(act_lint_all)
        act_rep = QAction("替换…", self)
        act_rep.setShortcut(QKeySequence("Ctrl+H"))
        act_rep.triggered.connect(self.show_replace_dialog)
        m_edit.addAction(act_rep)
        m_edit.addSeparator()
        self.act_word_wrap = QAction("自动换行", self)
        self.act_word_wrap.setCheckable(True)
        self.act_word_wrap.setShortcut(QKeySequence("Alt+Z"))
        self.act_word_wrap.triggered.connect(self.toggle_word_wrap)
        m_edit.addAction(self.act_word_wrap)
        m_edit.addSeparator()
        act_new = QAction("新增 section…", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self.on_add_new)
        m_edit.addAction(act_new)
        act_dbg = QAction("打开单位调试…", self)
        act_dbg.setShortcut(QKeySequence("Ctrl+D"))
        act_dbg.triggered.connect(self.open_debug_window)
        m_edit.addAction(act_dbg)

        m_view = mb.addMenu("视图(&V)")
        m_mode = m_view.addMenu("工作模式")
        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.act_merged = QAction("合并视图（推荐）", self)
        self.act_merged.setCheckable(True)
        self.act_merged.setChecked(True)
        self.act_merged.setData("merged")
        self.act_single = QAction("工程内单文件", self)
        self.act_single.setCheckable(True)
        self.act_single.setData("single")
        self.mode_group.addAction(self.act_merged)
        self.mode_group.addAction(self.act_single)
        m_mode.addAction(self.act_merged)
        m_mode.addAction(self.act_single)
        self.mode_group.triggered.connect(self.on_mode_action)
        m_view.addSeparator()
        act_refresh = QAction("刷新对象树", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        act_refresh.triggered.connect(self.refresh_tree)
        m_view.addAction(act_refresh)

        # 工具菜单（预留扩展）
        self.menu_tools = mb.addMenu("工具(&T)")

        # 配置：选择兼容的 profile（config.json 里的 profiles）
        self.menu_config = mb.addMenu("配置(&C)")
        self.menu_profile = self.menu_config.addMenu("兼容配置")
        self.profile_group = QActionGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_group.triggered.connect(self.on_profile_chosen)
        self._rebuild_profile_menu()
        self.menu_config.addSeparator()
        act_open_cfg = QAction("打开 config.json…", self)
        act_open_cfg.triggered.connect(self.open_config_file)
        self.menu_config.addAction(act_open_cfg)
        act_reload_cfg = QAction("重新加载配置", self)
        act_reload_cfg.triggered.connect(self.reload_config)
        self.menu_config.addAction(act_reload_cfg)
        self.menu_config.addSeparator()
        act_settings = QAction("首选项…", self)
        act_settings.setShortcut(QKeySequence("Ctrl+,"))
        act_settings.triggered.connect(self.open_settings)
        self.menu_config.addAction(act_settings)

        m_help = mb.addMenu("帮助(&H)")
        act_help = QAction("使用说明…", self)
        act_help.setShortcut(QKeySequence("F1"))
        act_help.triggered.connect(self.show_help)
        m_help.addAction(act_help)
        act_about = QAction("关于", self)
        act_about.triggered.connect(self.show_about)
        m_help.addAction(act_about)

    def _build_toolbar(self):
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)
        for text, slot in [
            ("打开工程", self.open_project),
            ("打开文件", self.open_loose_file),
            ("保存全部", self.save_all),
            ("+ 新增", self.on_add_new),
            ("全工程搜索", self.show_project_search),
        ]:
            a = QAction(text, self)
            a.triggered.connect(slot)
            tb.addAction(a)
        tb.addSeparator()
        self.dir_label = QLabel("  未打开")
        self.dir_label.setStyleSheet("color:#9ca3af; padding-left:8px;")
        tb.addWidget(self.dir_label)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.mode_badge = QPushButton("合并视图")
        self.mode_badge.setObjectName("modeBadge")
        self.mode_badge.setToolTip("点击切换：合并视图 ↔ 单文件")
        self.mode_badge.clicked.connect(self._toggle_view_mode)
        tb.addWidget(self.mode_badge)

    def _build_body(self):
        conf = self.project.config.get("window", {})
        self.resize(conf.get("width", 1500), conf.get("height", 900))
        split = QSplitter(Qt.Horizontal)
        self.setCentralWidget(split)

        left = QWidget()
        left.setObjectName("leftPanel")
        left.setMinimumWidth(270)
        left.setMaximumWidth(400)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)
        title = QLabel("对象树")
        title.setObjectName("panelTitle")
        ll.addWidget(title)

        self.file_row = QWidget()
        fr = QHBoxLayout(self.file_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.addWidget(QLabel("文件"))
        self.file_combo = QComboBox()
        self.file_combo.currentTextChanged.connect(self.on_file_chosen)
        fr.addWidget(self.file_combo, 1)
        ll.addWidget(self.file_row)
        self.file_row.hide()

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("过滤注册名 / 中文名…")
        self.filter_edit.textChanged.connect(lambda: self._filter_timer.start(140))
        ll.addWidget(self.filter_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self.on_tree_click)
        self.tree.itemExpanded.connect(self.on_tree_expanded)
        ll.addWidget(self.tree, 1)
        split.addWidget(left)

        mid = QWidget()
        mid.setObjectName("midPanel")
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(8, 8, 8, 8)
        ml.setSpacing(6)

        code_title = QLabel("代码编辑")
        code_title.setObjectName("panelTitle")
        ml.addWidget(code_title)

        top_mid = QHBoxLayout()
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        top_mid.addWidget(self.tabs, 1)
        b_prev, b_next = QPushButton("上一个"), QPushButton("下一个")
        b_prev.clicked.connect(self.prev_tab)
        b_next.clicked.connect(self.next_tab)
        b_dbg = QPushButton("调试")
        b_dbg.setToolTip("Ctrl+D · 单单位调试")
        b_dbg.clicked.connect(self.open_debug_window)
        b_save = QPushButton("保存当前")
        b_save.setObjectName("primaryBtn")
        b_save.setToolTip("Ctrl+S · 将当前单位写回来源文件")
        b_save.clicked.connect(self.save_current)
        b_del = QPushButton("删除")
        b_del.setToolTip("删除当前 section（需确认）")
        b_del.clicked.connect(self.delete_current_section)
        top_mid.addWidget(b_prev)
        top_mid.addWidget(b_next)
        top_mid.addWidget(b_dbg)
        top_mid.addWidget(b_save)
        top_mid.addWidget(b_del)
        ml.addLayout(top_mid)

        # 查找/替换改到「编辑」菜单，这里只保留隐藏输入供逻辑复用
        self.find_edit = QLineEdit(self)
        self.find_edit.hide()
        self.replace_edit = QLineEdit(self)
        self.replace_edit.hide()

        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color:#7dd3fc; font-size:12px;")
        ml.addWidget(self.source_label)

        self.code = CodeEditor()
        self.code.setTabStopDistance(32)
        self.code.cursorPositionChanged.connect(self.on_code_cursor)
        self.code.textChanged.connect(self._on_code_edited)
        ml.addWidget(self.code, 1)
        # 自动换行（编辑菜单，默认开，写入 settings）
        st = self.project.config.setdefault("settings", {})
        wrap = st.get("code_word_wrap", True)
        self.act_word_wrap.setChecked(bool(wrap))
        self._apply_word_wrap(bool(wrap), save=False)
        split.addWidget(mid)

        self.prop = PropPanel()
        self.prop.setObjectName("rightPanel")
        self.prop.setMinimumWidth(300)
        self.prop.setMaximumWidth(420)
        split.addWidget(self.prop)

        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 0)
        split.setSizes([300, 820, 360])

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #121212; color: #e8e8e8; }
            QWidget { color: #e8e8e8; }
            QMenuBar {
                background: #1a1a1a; color: #e8e8e8; padding: 3px;
                border-bottom: 1px solid #333;
            }
            QMenuBar::item:selected { background: #3d3d3d; }
            QMenu { background: #252526; color: #e8e8e8; border: 1px solid #444; }
            QMenu::item:selected { background: #5b4b8a; }
            QToolBar {
                background: #1a1a1a; border-bottom: 1px solid #333;
                spacing: 8px; padding: 6px 8px;
            }
            QStatusBar { background: #1a1a1a; color: #aaa; border-top: 1px solid #333; }

            QWidget#leftPanel {
                background: #1a1a1e;
                border-right: 1px solid #2a2a32;
            }
            QWidget#midPanel {
                background: #0d0d0f;
            }
            QLabel#panelTitle {
                font-weight: 700; font-size: 13px; color: #f0f0f0;
                padding: 2px 0 6px 0;
            }

            QTreeWidget {
                background: #141418; color: #ddd;
                border: 1px solid #2e2e38; border-radius: 6px;
                font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 12px;
                outline: none; padding: 4px;
            }
            QTreeWidget::item { padding: 4px 6px; border-radius: 3px; }
            QTreeWidget::item:selected { background: #5b4b8a; color: #fff; }
            QTreeWidget::item:hover:!selected { background: #2a2a35; }

            QPlainTextEdit {
                background: #0a0a0c; color: #d4d4d4;
                border: 1px solid #3a3a48; border-radius: 6px;
                font-family: Consolas, "Cascadia Mono", monospace; font-size: 13px;
                selection-background-color: #5b4b8a;
                padding: 4px;
            }
            QLineEdit {
                background: #1e1e24; border: 1px solid #3a3a48; border-radius: 5px;
                padding: 6px 8px; selection-background-color: #5b4b8a;
            }
            QComboBox {
                background: #1e1e24; border: 1px solid #3a3a48; border-radius: 5px;
                padding: 6px 28px 6px 8px;
                selection-background-color: #5b4b8a;
                min-height: 24px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: center right;
                width: 22px;
                border-left: 1px solid #3a3a48;
                background: #2c2c34;
            }
            QComboBox::down-arrow {
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e24; color: #e8e8e8;
                selection-background-color: #5b4b8a;
                border: 1px solid #3a3a48;
            }

            QPushButton {
                background: #2c2c34; border: 1px solid #45454f; border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #3a3a45; }
            QPushButton#debugBtn {
                background: #6d28d9; border: 1px solid #8b5cf6; color: #fff;
                font-weight: 700; padding: 7px 16px; border-radius: 6px;
            }
            QPushButton#debugBtn:hover { background: #7c3aed; }
            QPushButton#primaryBtn { background: #2d6a4f; border-color: #40916c; color: #fff; }
            QPushButton#primaryBtn:hover { background: #1b4332; }

            QTabWidget::pane {
                border: 1px solid #3a3a48; border-radius: 6px;
                background: #0a0a0c; top: -1px;
            }
            QTabBar::tab {
                background: #1e1e24; color: #bbb; padding: 8px 14px; margin-right: 3px;
                border-top-left-radius: 5px; border-top-right-radius: 5px;
            }
            QTabBar::tab:selected { background: #5b4b8a; color: #fff; }
            QTabBar::tab:hover:!selected { background: #2a2a35; }
            QTabBar::scroller { width: 0px; }
            QTabBar QToolButton { background: #2c2c34; border: 1px solid #45454f; color: #e8e8e8; }
            QTabBar QToolButton:hover { background: #3a3a45; }


            QScrollArea { border: none; background: transparent; }
            QFrame#propRow { background: #22222a; border-radius: 5px; border: 1px solid #2e2e38; }
            QAbstractScrollArea { background: #1a1a1e; }
            QAbstractScrollArea::viewport { background: #1a1a1e; }
            QPushButton#modeBadge {
                background: #6d28d9; color: #fff; border-radius: 10px;
                border: 1px solid #8b5cf6;
                padding: 6px 14px; margin-right: 8px; font-size: 12px; font-weight: 700;
            }
            QPushButton#modeBadge:hover { background: #7c3aed; }
            QSplitter::handle { background: #2a2a32; width: 2px; }

            QWidget#rightPanel {
                background: #1a1a1e;
                border-left: 1px solid #2a2a32;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollArea QWidget {
                background: transparent;
            }
            QDialog { background: #1e1e1e; }
        """)

    def _update_chrome(self):
        if self.project.work_mode == "single" and self.project.single_path:
            mode = f"单文件 · {self.project.single_path.name}"
            self.mode_badge.setText("单文件 · 点此切换")
            self.act_single.setChecked(True)
            # 无工程时禁用合并视图
            self.act_merged.setEnabled(self.project.project_dir is not None and self.project.rules is not None)
        else:
            mode = "合并视图"
            self.mode_badge.setText("合并视图 · 点此切换")
            self.act_merged.setChecked(True)
            self.act_merged.setEnabled(True)
        d = self.project.project_dir
        prof = self.project.profile.get("display_name", self.project.profile_name)
        if d:
            self.setWindowTitle(f"{APP_TITLE}  —  {prof}  —  {mode}  —  {d}")
            self.dir_label.setText(f"  [{prof}]  {d}")
        elif self.project.single_path:
            self.setWindowTitle(f"{APP_TITLE}  —  {mode}")
            self.dir_label.setText(f"  {self.project.single_path}")
        else:
            self.setWindowTitle(APP_TITLE)
            self.dir_label.setText("  未打开")

    def _mem_key(self, section_id: str = None, prefer: str = None) -> str:
        sid = section_id if section_id is not None else self.current_section_id
        pref = prefer if prefer is not None else getattr(self, "current_prefer", "")
        if not sid:
            return ""
        if pref == "art":
            return f"art::{sid}"
        if pref == "ai":
            return f"ai::{sid}"
        return sid

    def _store_current_to_mem(self):
        """把当前编辑器内容写入内存（不落盘）"""
        if not self.current_section_id:
            return
        key = self._mem_key()
        if key:
            self._mem_sections[key] = self.code.toPlainText()

    def _on_code_edited(self):
        if not self._loading_section:
            self._dirty = True
            self._store_current_to_mem()

    def _toggle_view_mode(self):
        """右上角紫色按钮：合并 ↔ 单文件"""
        if self.project.work_mode == "merged":
            self._quick_view("single")
        else:
            self._quick_view("merged")

    def _confirm_discard_if_dirty(self) -> bool:
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("未保存的修改")
        box.setText("当前代码区有未保存的修改。")
        box.setInformativeText("继续将可能丢失这些修改。")
        save_btn = box.addButton("保存后继续", QMessageBox.AcceptRole)
        disc_btn = box.addButton("丢弃修改", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return False
        if clicked == save_btn:
            self.save_current()
            return not self._dirty
        self._dirty = False
        return True

    def on_mode_action(self, action: QAction):
        data = action.data()
        cur = "single" if self.project.work_mode == "single" else "merged"
        if data == cur:
            return
        if data == "merged" and (not self.project.project_dir or not self.project.rules):
            QMessageBox.information(self, "提示", "合并视图需要先「打开游戏文件夹」并成功加载 rules。")
            self.act_single.setChecked(True)
            return
        if not self._confirm_discard_if_dirty():
            if cur == "merged":
                self.act_merged.setChecked(True)
            else:
                self.act_single.setChecked(True)
            return
        if data == "single":
            self.file_row.show()
            self._ensure_single_file()
        else:
            self.file_row.hide()
            self.project.set_merged_mode()
        self._display_cache.clear()
        self.tabs.clear()
        self.current_section_id = None
        self._dirty = False
        self.code.setPlainText("")
        self.prop.clear()
        self.source_label.setText("")
        self._update_chrome()
        self.refresh_tree()

    def _ensure_single_file(self):
        lab = self.file_combo.currentText()
        path = self._file_map.get(lab)
        if path:
            self.project.open_single_file(path)
        else:
            files = self.project.list_ini_files()
            if files:
                self.project.open_single_file(files[0])

    def _rebuild_profile_menu(self):
        self.menu_profile.clear()
        for a in self.profile_group.actions():
            self.profile_group.removeAction(a)
        profiles = self.project.config.get("profiles", {})
        active = self.project.profile_name
        for name, conf in profiles.items():
            label = conf.get("display_name", name)
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(name)
            if name == active:
                act.setChecked(True)
            self.profile_group.addAction(act)
            self.menu_profile.addAction(act)

    def on_profile_chosen(self, action: QAction):
        name = action.data()
        if not name or name == self.project.profile_name:
            return
        if not self._confirm_discard_if_dirty():
            self._rebuild_profile_menu()
            return
        self.project.set_active_profile(name)
        # 若已打开工程，用新 profile 重新加载
        if self.project.project_dir:
            path = self.project.project_dir
            self.statusBar().showMessage(f"正在用配置 [{name}] 重新加载…")
            QApplication.processEvents()
            if not self.project.open_directory(path):
                QMessageBox.warning(self, "配置", "用新配置加载失败，请检查该 profile 的 rules_files 等路径")
            self._display_cache.clear()
            self.tabs.clear()
            self._refresh_file_combo()
            self.act_merged.setChecked(True)
            self.file_row.hide()
            self._dirty = False
            self.refresh_tree()
        self._update_chrome()
        disp = self.project.profile.get("display_name", name)
        self.statusBar().showMessage(f"当前兼容配置: {disp}", 6000)
        QMessageBox.information(
            self, "兼容配置",
            f"已切换为：{disp}\n\n"
            f"rules: {', '.join(self.project.profile.get('rules_files', []))}\n"
            f"art: {', '.join(self.project.profile.get('art_files', []))}\n"
            f"ai: {', '.join(self.project.profile.get('ai_files', []))}"
        )

    def open_config_file(self):
        cfg = user_config_path()
        if not cfg.exists():
            QMessageBox.warning(self, "配置", f"未找到 {cfg}")
            return
        # Windows: 用默认编辑器打开
        import os
        try:
            os.startfile(str(cfg))  # type: ignore
        except Exception:
            QMessageBox.information(self, "配置", f"请手动编辑:\n{cfg}")


    def open_settings(self):
        """软件内设置入口，写入 config.json 的 settings 段。"""
        st = self.project.config.setdefault("settings", {})
        dlg = QDialog(self)
        dlg.setWindowTitle("首选项")
        dlg.setMinimumWidth(480)
        dlg.resize(520, 560)
        dlg.setStyleSheet(
            "QDialog { background: #1a1d24; color: #e8eaed; }"
            "QLabel { color: #e8eaed; font-size: 13px; }"
            "QLineEdit, QSpinBox {"
            "  background: #252830; color: #f1f3f5; border: 1px solid #3d4450;"
            "  border-radius: 4px; padding: 4px 8px; min-height: 26px; }"
            "QCheckBox { color: #e8eaed; font-size: 13px; spacing: 6px; }"
            "QFrame#sep { background: #3d4450; max-height: 1px; margin: 6px 0; }"
            "QLabel#sec { color: #a5b4fc; font-size: 13px; font-weight: 600; padding-top: 4px; }"
            "QPushButton {"
            "  background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;"
            "  border-radius: 4px; padding: 6px 14px; }"
        )
        root = QVBoxLayout(dlg)
        root.setSpacing(8)

        def add_sep():
            line = QFrame()
            line.setObjectName("sep")
            line.setFrameShape(QFrame.HLine)
            root.addWidget(line)

        def add_sec(text: str):
            lab = QLabel(text)
            lab.setObjectName("sec")
            root.addWidget(lab)

        add_sec("编辑与调试")
        chk_assist = QCheckBox("调试默认开启辅助模式（引用字段可下拉，仍可手输）")
        chk_assist.setChecked(bool(st.get("debug_assist_mode", True)))
        root.addWidget(chk_assist)

        add_sep()
        add_sec("校验")
        chk_lint = QCheckBox("保存时自动校验（单节 / 保存全部）")
        chk_lint.setChecked(bool(st.get("auto_lint_on_save", True)))
        root.addWidget(chk_lint)
        root.addWidget(QLabel("不校验的注册表（勾选 = 跳过无效注册检查）"))
        default_skip = ["Animations"]
        cur_skip = st.get("lint_skip_type_lists")
        if cur_skip is None:
            cur_skip = list(default_skip)
        cur_skip_l = {str(x).lower() for x in cur_skip}
        skip_names = [
            "Animations", "VoxelAnims", "Particles", "ParticleSystems",
            "WeaponTypes", "Warheads", "ProjectileTypes", "Projectiles",
            "InfantryTypes", "VehicleTypes", "AircraftTypes", "BuildingTypes",
            "SuperWeaponTypes", "OverlayTypes", "SmudgeTypes", "TerrainTypes",
        ]
        skip_scroll = QScrollArea()
        skip_scroll.setWidgetResizable(True)
        skip_scroll.setMaximumHeight(160)
        skip_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #3d4450; border-radius: 4px; background: #252830; }"
        )
        skip_inner = QWidget()
        skip_lay = QVBoxLayout(skip_inner)
        skip_lay.setContentsMargins(8, 6, 8, 6)
        skip_cbs = []
        for nm in skip_names:
            cb = QCheckBox(nm)
            cb.setChecked(nm.lower() in cur_skip_l)
            skip_lay.addWidget(cb)
            skip_cbs.append((nm, cb))
        skip_scroll.setWidget(skip_inner)
        root.addWidget(skip_scroll)

        add_sep()
        add_sec("自动备份")
        root.addWidget(QLabel("按原文件名分子文件夹，例如 backups/rulesmd.ini/"))
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("每个文件最多保留份数"))
        spin_keep = QSpinBox()
        spin_keep.setRange(0, 9999)
        spin_keep.setSpecialValueText("不限制")
        try:
            spin_keep.setValue(int(st.get("backup_keep", 100)))
        except (TypeError, ValueError):
            spin_keep.setValue(100)
        spin_keep.setToolTip("0 表示不限制。默认 100。")
        keep_row.addWidget(spin_keep)
        keep_row.addStretch(1)
        root.addLayout(keep_row)

        add_sep()
        add_sec("热重载")
        hr = self.project.config.setdefault("hotreload", {})
        edit_hotfix = QLineEdit(hr.get("target_ini", "hotfix.ini"))
        hr_row = QHBoxLayout()
        hr_row.addWidget(QLabel("目标文件"))
        hr_row.addWidget(edit_hotfix, 1)
        root.addLayout(hr_row)

        tip = QLabel("以上设置写入 config.json，重启后仍有效。")
        tip.setStyleSheet("color:#94a3b8; font-size:12px;")
        tip.setWordWrap(True)
        root.addWidget(tip)
        root.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        root.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.Accepted:
            return
        st["debug_assist_mode"] = chk_assist.isChecked()
        st["auto_lint_on_save"] = chk_lint.isChecked()
        st["lint_skip_type_lists"] = [nm for nm, cb in skip_cbs if cb.isChecked()]
        st["backup_keep"] = int(spin_keep.value())
        hr["target_ini"] = edit_hotfix.text().strip() or "hotfix.ini"
        self.project.save_config()
        QMessageBox.information(self, "首选项", "已保存。")

    def reload_config(self):
        self.project.load_config()
        self._rebuild_profile_menu()
        QMessageBox.information(self, "配置", "已重新读取 config.json（未自动重载工程，可再开一次工程目录）")

    def open_project(self, path: str | None = None):
        if not path:
            st = self.project.config.setdefault("settings", {})
            start = st.get("last_project_dir") or ""
            if not start or not Path(start).is_dir():
                start = str(Path.home())
            path = QFileDialog.getExistingDirectory(
                self, "打开游戏文件夹 / Mod 根目录", start
            )
        if not path:
            return
        if not self._confirm_discard_if_dirty():
            return
        self.statusBar().showMessage("正在加载…")
        QApplication.processEvents()
        if not self.project.open_directory(path):
            QMessageBox.critical(self, "错误", "未找到 rules 或配置中的 ini")
            self.statusBar().showMessage("加载失败")
            return
        st = self.project.config.setdefault("settings", {})
        st["last_project_dir"] = str(Path(path).resolve())
        try:
            self.project.save_config()
        except Exception:
            pass
        self._display_cache.clear()
        self._load_display_cache_file()
        self.tabs.clear()
        self._refresh_file_combo()
        self.act_merged.setChecked(True)
        self.file_row.hide()
        self.project.set_merged_mode()
        self._dirty = False
        self._update_chrome()
        self.refresh_tree()
        self.statusBar().showMessage(
            f"{self.project.get_loaded_files_summary()}  |  CSF {len(self.project.csf.strings)} 条"
        )
        QTimer.singleShot(50, self._warm_display_cache)

    def open_loose_file(self):
        """不依赖工程：直接打开一个 ini 进入单文件模式"""
        if not self._confirm_discard_if_dirty():
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self, "打开单文件",
            str(self.project.project_dir or Path.home()),
            "INI 文件 (*.ini);;所有文件 (*.*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if not self.project.open_single_file(path):
            QMessageBox.warning(self, "错误", f"无法解析:\n{path}")
            return
        # 加入允许列表显示
        self.project._add_allowed(path)
        self._refresh_file_combo()
        # 选中该项
        for i in range(self.file_combo.count()):
            if self._file_map.get(self.file_combo.itemText(i), Path()).resolve() == path.resolve():
                self.file_combo.blockSignals(True)
                self.file_combo.setCurrentIndex(i)
                self.file_combo.blockSignals(False)
                break
        self.act_single.setChecked(True)
        self.file_row.show()
        self._display_cache.clear()
        self.tabs.clear()
        self._dirty = False
        self._update_chrome()
        self.refresh_tree()
        self.statusBar().showMessage(f"已打开单文件: {path}")

    def _refresh_file_combo(self):
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        self._file_map.clear()
        for f in self.project.list_ini_files():
            try:
                lab = str(f.relative_to(self.project.project_dir)) if self.project.project_dir else f.name
            except Exception:
                lab = f.name
            if lab in self._file_map:
                lab = f"{f.parent.name}/{f.name}"
            self._file_map[lab] = f
            self.file_combo.addItem(lab)
        self.file_combo.blockSignals(False)

    def on_file_chosen(self, lab: str):
        if not self.act_single.isChecked() and self.project.work_mode != "single":
            return
        path = self._file_map.get(lab)
        if not path:
            return
        if self.project.single_path and path.resolve() == self.project.single_path.resolve():
            return
        if not self._confirm_discard_if_dirty():
            if self.project.single_path:
                for i in range(self.file_combo.count()):
                    lab2 = self.file_combo.itemText(i)
                    fp = self._file_map.get(lab2)
                    if fp and fp.resolve() == self.project.single_path.resolve():
                        self.file_combo.blockSignals(True)
                        self.file_combo.setCurrentIndex(i)
                        self.file_combo.blockSignals(False)
                        break
            return
        if not self.project.open_single_file(path):
            QMessageBox.warning(self, "错误", f"无法打开:\n{path}")
            return
        self._display_cache.clear()
        self.tabs.clear()
        self._dirty = False
        self._update_chrome()
        self.refresh_tree()

    def _disp(self, sid: str) -> str:
        if sid not in self._display_cache:
            self._display_cache[sid] = self.project.get_display_name(
                sid, prefer=self.project.active_ini()
            )
        return self._display_cache[sid]

    def _norm_prefer(self, prefer: str) -> str:
        """rules 用空串，与树上 UserRole+2 一致。"""
        p = (prefer or "").strip()
        return "" if p in ("", "rules") else p

    def _tab_meta(self, prefer: str = "", group: str = "") -> str:
        return f"prefer={self._norm_prefer(prefer) or 'rules'};group={group or ''}"

    def _parse_tab_meta(self, tip: str) -> tuple:
        prefer, group = "", ""
        tip = tip or ""
        for part in tip.split(";"):
            part = part.strip()
            if part.startswith("prefer="):
                prefer = self._norm_prefer(part[7:])
            elif part.startswith("group="):
                group = part[6:]
        return prefer, group

    def _project_fingerprint(self) -> str:
        """用 rules/art/ai 主文件 mtime 做指纹；外部编辑器改过会变。"""
        parts = []
        for ini in (self.project.rules, self.project.art, self.project.ai):
            if not ini or not getattr(ini, "filepath", None):
                continue
            try:
                fp = Path(ini.filepath)
                if fp.is_file():
                    st = fp.stat()
                    parts.append(f"{fp.name}:{st.st_mtime_ns}:{st.st_size}")
            except Exception:
                continue
        # 也扫 allowed 主文件
        for key in ("rules_files", "art_files", "ai_files"):
            for name in self.project.profile.get(key) or []:
                if self.project.project_dir:
                    fp = self.project.project_dir / name
                    if fp.is_file():
                        try:
                            st = fp.stat()
                            parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")
                        except Exception:
                            pass
        return "|".join(sorted(set(parts)))

    def _cache_dir(self) -> Path:
        """显示名缓存：exe 旁或 LocalAppData（打包可写）。"""
        return user_cache_dir()


    def _cache_file(self) -> Path:
        import hashlib
        key = str(self.project.project_dir or self.project.single_path or "default")
        h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
        return self._cache_dir() / f"display_{h}.json"

    def _warm_display_cache(self):
        """内存预热 + 带指纹的磁盘缓存（外部改文件则自动失效）。"""
        if not self.project.project_dir and not self.project.rules:
            return
        try:
            ini = self.project.rules or self.project.active_ini()
            if not ini:
                return
            groups = self.project.classify_sections(ini)
            ids = []
            for lst in groups.values():
                ids.extend(lst)
            seen, uniq = set(), []
            for u in ids:
                if u.lower() not in seen:
                    seen.add(u.lower())
                    uniq.append(u)
            for u in uniq:
                if u not in self._display_cache:
                    self._display_cache[u] = self.project.get_display_name(
                        u, prefer=self.project.active_ini()
                    )
            fp = self._project_fingerprint()
            payload = {
                "fingerprint": fp,
                "project": str(self.project.project_dir or ""),
                "names": self._display_cache,
            }
            path = self._cache_file()
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self.statusBar().showMessage(
                f"显示名缓存 {len(self._display_cache)} 项 → {path}", 5000
            )
        except Exception as e:
            self.statusBar().showMessage(f"词典预热跳过: {e}", 5000)

    def _load_display_cache_file(self):
        """指纹一致才用磁盘缓存；否则丢弃（应对外部编辑器改过 ini）。"""
        try:
            path = self._cache_file()
            if not path.is_file():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            fp_now = self._project_fingerprint()
            if data.get("fingerprint") != fp_now:
                # 外部改过或文件变了
                return
            names = data.get("names") or {}
            if isinstance(names, dict):
                self._display_cache.update({str(k): str(v) for k, v in names.items()})
        except Exception:
            pass

    def schedule_display_cache_rebuild(self):
        self._display_cache.clear()
        QTimer.singleShot(100, self._warm_display_cache)

    def select_tree_item(self, section_id: str, group: str = "", prefer: str = ""):
        """严格按 prefer（rules/art/ai）+ 可选 group 定位，绝不跨 Art/Rules 串。"""
        prefer = self._norm_prefer(prefer)
        self.tree.blockSignals(True)
        try:
            root = self.tree.invisibleRootItem()
            self._expand_groups_for(root, section_id, group=group, prefer=prefer)
            it = self._find_tree_item(root, section_id, group=group, prefer=prefer)
            if it:
                self.tree.setCurrentItem(it)
                self.tree.scrollToItem(it)
                p = it.parent()
                while p:
                    p.setExpanded(True)
                    p = p.parent()
        finally:
            self.tree.blockSignals(False)

    def _expand_groups_for(self, parent, section_id: str, group: str = "", prefer: str = ""):
        prefer = self._norm_prefer(prefer)
        for i in range(parent.childCount()):
            child = parent.child(i)
            ids = child.data(0, Qt.UserRole + 1)
            g = child.data(0, Qt.UserRole + 3) or ""
            pref = self._norm_prefer(child.data(0, Qt.UserRole + 2) or "")
            # 先递归子节点
            self._expand_groups_for(child, section_id, group=group, prefer=prefer)
            if not ids:
                continue
            if not any(str(u).lower() == section_id.lower() for u in ids):
                continue
            # prefer 必须一致（rules 空 == 空）
            if pref != prefer:
                continue
            if group and g and g.lower() != group.lower():
                continue
            if child.childCount() == 1 and child.child(0).data(0, Qt.UserRole) is None:
                self._fill_tree_children(child, ids, prefer=pref, group=g or group)
            child.setExpanded(True)

    def _find_tree_item(self, parent, section_id: str, group: str = "", prefer: str = ""):
        """只返回 prefer 一致的节点；group 有则再精确，否则同 prefer 下第一个。"""
        prefer = self._norm_prefer(prefer)
        exact, soft = None, None
        for i in range(parent.childCount()):
            child = parent.child(i)
            # 深度优先先搜子树，保证先处理更具体的路径
            found = self._find_tree_item(child, section_id, group=group, prefer=prefer)
            if found:
                return found
            role = child.data(0, Qt.UserRole)
            if role is None or str(role).lower() != section_id.lower():
                continue
            pref = self._norm_prefer(child.data(0, Qt.UserRole + 2) or "")
            if pref != prefer:
                continue  # 绝不把 art 当 rules，反之亦然
            g = child.data(0, Qt.UserRole + 3) or ""
            if group:
                if g.lower() == group.lower():
                    return child
                # group 不符：同 prefer 下仅作候选
                if soft is None:
                    soft = child
            else:
                # 未指定 group：同 prefer 即可
                if exact is None:
                    exact = child
        return exact or soft

    def refresh_tree(self):
        """对象树：分类节点先建好；子节点展开时再填充（避免一次插入上千项卡死）"""
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            filt = self.filter_edit.text().strip().lower()
            ini = self.project.rules if self.project.work_mode == "merged" else self.project.active_ini()
            if not ini:
                QTreeWidgetItem(self.tree, ["（无数据）"])
                return

            def match(uid: str) -> bool:
                if not filt:
                    return True
                return filt in uid.lower() or filt in self._disp(uid).lower()

            groups = self.project.classify_sections(ini)
            type_map = {
                "InfantryTypes": "步兵", "VehicleTypes": "载具", "AircraftTypes": "飞行器",
                "BuildingTypes": "建筑", "WeaponTypes": "武器", "Warheads": "弹头",
                "ProjectileTypes": "抛射体", "SuperWeaponTypes": "超武",
                "Animations": "动画", "Particles": "粒子", "ParticleSystems": "粒子系统",
                "Projectiles": "抛射体", "Countries": "国家", "Sides": "阵营", "Colors": "颜色",
                "TaskForces": "特遣队", "ScriptTypes": "脚本", "TeamTypes": "小队",
                "AITriggerTypes": "AI触发",
                "注册表": "注册表", "国家 Country": "国家", "其他": "其他",
            }

            if self.project.work_mode == "single":
                title = self.project.single_path.name if self.project.single_path else "当前文件"
                root = QTreeWidgetItem(self.tree, [f"📄 {title}"])
                root.setExpanded(True)
                parent_for_groups = root
            else:
                parent_for_groups = None

            for group_name, ids in groups.items():
                items = [u for u in ids if match(u)]
                if filt and not items:
                    continue
                cn = type_map.get(group_name, group_name)
                if group_name in type_map and (
                    group_name.endswith("Types") or group_name in (
                        "Warheads", "WeaponTypes", "ProjectileTypes", "SuperWeaponTypes"
                    )
                ):
                    label = f"{cn} · {group_name}"
                else:
                    label = cn
                count = len(items) if filt else len(ids)
                label += f" ({count})"
                info = (self.flag_schema.get("_type_lists") or {}).get(group_name) or {}
                desc = info.get("desc_zh") or ""
                if desc:
                    label += f"  ·  {(desc[:12] + '…') if len(desc) > 12 else desc}"

                if parent_for_groups is not None:
                    node = QTreeWidgetItem(parent_for_groups, [label])
                else:
                    node = QTreeWidgetItem(self.tree, [label])

                # 存 ids 供懒加载；分组名用于同名 section 消歧
                node.setData(0, Qt.UserRole + 1, items if filt else list(ids))
                node.setData(0, Qt.UserRole + 3, group_name)
                if filt or count <= 40:
                    self._fill_tree_children(node, items if filt else ids, group=group_name)
                    if filt:
                        node.setExpanded(True)
                else:
                    ph = QTreeWidgetItem(node, ["（展开以加载…）"])
                    ph.setData(0, Qt.UserRole, None)

            if self.project.work_mode == "merged" and self.project.art:
                art_root = QTreeWidgetItem(self.tree, ["Art"])
                art_root.setData(0, Qt.UserRole + 2, "art")
                art_ids = [s for s in self.project.art.section_order if not s.startswith("#")]
                if filt:
                    art_ids = [s for s in art_ids if match(s)]
                art_root.setData(0, Qt.UserRole + 1, art_ids)
                if filt or len(art_ids) <= 40:
                    self._fill_tree_children(art_root, art_ids, prefer="art")
                else:
                    ph = QTreeWidgetItem(art_root, ["（展开以加载…）"])
                    ph.setData(0, Qt.UserRole, None)

            # AI：配置里的 ai_files 已加载，但合并树以前只画 rules/art
            if self.project.work_mode == "merged" and self.project.ai:
                ai_root = QTreeWidgetItem(self.tree, ["AI"])
                ai_root.setData(0, Qt.UserRole + 2, "ai")
                ai_groups = self.project.classify_sections(self.project.ai)
                ai_type_labels = {
                    "TaskForces": "特遣队 · TaskForces",
                    "ScriptTypes": "脚本 · ScriptTypes",
                    "TeamTypes": "小队 · TeamTypes",
                    "AITriggerTypes": "AI触发 · AITriggerTypes",
                    "注册表": "注册表",
                }
                any_child = False
                for gname, ids in ai_groups.items():
                    items = [u for u in ids if match(u)]
                    if filt and not items:
                        continue
                    label = ai_type_labels.get(gname, gname)
                    count = len(items) if filt else len(ids)
                    node = QTreeWidgetItem(ai_root, [f"{label} ({count})"])
                    node.setData(0, Qt.UserRole + 2, "ai")
                    node.setData(0, Qt.UserRole + 3, gname)
                    show_ids = items if filt else ids
                    node.setData(0, Qt.UserRole + 1, show_ids)
                    if filt or len(show_ids) <= 40:
                        self._fill_tree_children(node, show_ids, prefer="ai", group=gname)
                    else:
                        ph = QTreeWidgetItem(node, ["（展开以加载…）"])
                        ph.setData(0, Qt.UserRole, None)
                    any_child = True
                if not any_child and not filt:
                    # 兜底：平铺全部 AI section
                    ai_ids = [s for s in self.project.ai.section_order if not s.startswith("#")]
                    ai_root.setData(0, Qt.UserRole + 1, ai_ids)
                    if len(ai_ids) <= 40:
                        self._fill_tree_children(ai_root, ai_ids, prefer="ai")
                    else:
                        ph = QTreeWidgetItem(ai_root, ["（展开以加载…）"])
                        ph.setData(0, Qt.UserRole, None)
        finally:
            self.tree.blockSignals(False)
            self.tree.setUpdatesEnabled(True)

    def _fill_tree_children(self, node: QTreeWidgetItem, ids: list, prefer: str = "", group: str = ""):
        node.takeChildren()
        if not prefer:
            prefer = node.data(0, Qt.UserRole + 2) or ""
        if not group:
            group = node.data(0, Qt.UserRole + 3) or ""
        parent_label = node.text(0) if node else ""
        is_reg_group = parent_label.startswith("注册表")
        for uid in ids:
            if is_reg_group or uid in TYPE_LABELS:
                label = TYPE_LABELS.get(uid, uid)
            else:
                label = self._disp(uid)
            child = QTreeWidgetItem(node, [label])
            child.setData(0, Qt.UserRole, uid)
            child.setData(0, Qt.UserRole + 2, prefer)
            child.setData(0, Qt.UserRole + 3, group)
            tip = uid
            if group:
                tip += f" · {group}"
            if prefer == "art":
                tip += " · Art"
            elif prefer == "ai":
                tip += " · AI"
            child.setToolTip(0, tip)

    def on_tree_expanded(self, item: QTreeWidgetItem):
        ids = item.data(0, Qt.UserRole + 1)
        if not ids:
            return
        # 若只有占位符则填充
        if item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) is None:
            self.tree.setUpdatesEnabled(False)
            try:
                self._fill_tree_children(item, ids, prefer=item.data(0, Qt.UserRole + 2) or "", group=item.data(0, Qt.UserRole + 3) or "")
            finally:
                self.tree.setUpdatesEnabled(True)

    def on_tree_click(self, item: QTreeWidgetItem, _col: int):
        sid = item.data(0, Qt.UserRole)
        if sid:
            prefer = item.data(0, Qt.UserRole + 2) or ""
            group = item.data(0, Qt.UserRole + 3) or ""
            self.open_section_tab(str(sid), prefer=prefer, group=str(group) if group else "")

    def open_section_tab(self, section_id: str, prefer: str = "", group: str = ""):
        """同一 (section_id, prefer) 只保留一个标签，重复点击只切换不新建。"""
        prefer = self._norm_prefer(prefer)
        section_id = str(section_id)
        if prefer == "art":
            tab_title = f"{section_id} · Art"
        elif prefer == "ai":
            tab_title = f"{section_id} · AI"
        else:
            tab_title = section_id
        meta = self._tab_meta(prefer, group)

        # 1) 按标题 + prefer 精确找
        for i in range(self.tabs.count()):
            title = self.tabs.tabText(i)
            # 兼容旧标签无带多余空格
            base = title.split(" · ")[0].strip() if " · " in title else title.strip()
            old_pref, _ = self._parse_tab_meta(self.tabs.tabToolTip(i) or "")
            same_id = base.lower() == section_id.lower() or title.strip() == tab_title
            # rules：标题等于 id；art/ai：标题带后缀
            if prefer == "art":
                same_id = title.strip() == f"{section_id} · Art" or (
                    base.lower() == section_id.lower() and old_pref == "art"
                )
            elif prefer == "ai":
                same_id = title.strip() == f"{section_id} · AI" or (
                    base.lower() == section_id.lower() and old_pref == "ai"
                )
            else:
                same_id = (
                    title.strip() == section_id
                    or (base.lower() == section_id.lower() and old_pref in ("", "rules"))
                )
            if same_id and old_pref == prefer:
                self.tabs.setTabToolTip(i, meta)
                # 避免 currentChanged 递归时重复加载：仅在索引变化时 setCurrent
                if self.tabs.currentIndex() != i:
                    self.tabs.setCurrentIndex(i)
                else:
                    self.show_section(section_id, prefer=prefer, group=group)
                return

        # 2) 没有则新建一个
        idx = self.tabs.addTab(QWidget(), tab_title)
        self.tabs.setTabToolTip(idx, meta)
        self.tabs.setCurrentIndex(idx)
        self.show_section(section_id, prefer=prefer, group=group)

    def close_tab(self, index: int):
        title = self.tabs.tabText(index)
        sid = title.split(" · ")[0] if " · " in title else title
        self.tabs.removeTab(index)
        if self.current_section_id == sid:
            if self.tabs.count():
                self.on_tab_changed(self.tabs.currentIndex())
            else:
                self.current_section_id = None
                self.code.setPlainText("")
                self.prop.clear()
                self.source_label.setText("")

    def on_tab_changed(self, index: int):
        self._store_current_to_mem()
        if index >= 0:
            title = self.tabs.tabText(index)
            prefer, group = self._parse_tab_meta(self.tabs.tabToolTip(index) or "")
            sid = title.split(" · ")[0] if " · " in title else title
            self.show_section(sid, prefer=prefer, group=group)
            self.select_tree_item(sid, group=group, prefer=prefer)

    def prev_tab(self):
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % n)

    def next_tab(self):
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % n)

    def show_section(self, section_id: str, prefer: str = "", group: str = ""):
        self.current_section_id = section_id
        self.current_prefer = prefer or ""
        self.current_group = group or ""
        prefer_ini = None
        if prefer == "art" and self.project.art:
            prefer_ini = self.project.art
        elif prefer == "ai" and self.project.ai:
            prefer_ini = self.project.ai
        key = self._mem_key(section_id, prefer)
        if key and key in self._mem_sections:
            body = self._mem_sections[key]
            from_mem = True
        else:
            body = self.project.get_section_text(section_id, prefer=prefer_ini)
            from_mem = False
        self._loading_section = True
        self.code.blockSignals(True)
        self.code.setPlainText(body if body.endswith("\n") else body + "\n")
        self.code.blockSignals(False)
        self._loading_section = False
        if hasattr(self.code, "update_line_number_area_width"):
            self.code.update_line_number_area_width(0)
        # 内存中有未保存稿则保持 dirty
        self._dirty = from_mem and (key in self._mem_sections)

        if prefer == "art" and self.project.art:
            sec = self.project.art.get_section(section_id)
            # art 来源
            src = None
            if sec and sec.source_file:
                src = self.project._resolve_name(sec.source_file)
            if not src:
                for src_path, names in (self.project.art.file_sections or {}).items():
                    if any(n.lower() == section_id.lower() for n in names):
                        src = Path(src_path)
                        break
        else:
            src = self.project.get_source_path_for_section(section_id)
            sec = self.project.get_section(section_id, prefer=prefer_ini or self.project.active_ini())

        if self.project.work_mode == "single":
            self.source_label.setText(f"写入目标（当前文件）: {src}")
        else:
            tag = " [Art]" if prefer == "art" else (" [AI]" if prefer == "ai" else "")
            self.source_label.setText(
                f"写入目标{tag}: {src}" if src else "写入目标: 未知 — 保存时将请你选择文件"
            )
        self.prop.set_section(
            section_id, self._disp(section_id), sec, self.flag_schema,
            src_name=str(src) if src else "",
            on_jump_editor=self.jump_to_editor_key,
            on_jump_tree=self.jump_to_tree_value,
        )

    def on_code_cursor(self):
        cur = self.code.textCursor()
        cur.select(QTextCursor.LineUnderCursor)
        line = cur.selectedText().strip()
        if "=" in line and not line.startswith(";") and not line.startswith("["):
            key = line.split("=", 1)[0].strip()
            desc = (self.flag_schema.get(key) or {}).get("desc_zh") or ""
            if desc:
                self.prop.hint.setText(f"{key}: {desc}")

    def jump_to_editor_key(self, key: str):
        """按属性键在代码编辑器中定位（按文档块遍历，避免行号/换行错位）。"""
        if not key:
            return
        key_l = key.strip().lower()
        doc = self.code.document()
        block = doc.begin()
        while block.isValid():
            raw = block.text()
            s = raw.strip()
            if s and not s.startswith(";") and not s.startswith("["):
                if "=" in s:
                    left = s.split("=", 1)[0].strip().lower()
                    if left == key_l:
                        cur = QTextCursor(block)
                        cur.movePosition(QTextCursor.StartOfBlock)
                        cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                        self.code.setTextCursor(cur)
                        self.code.setFocus()
                        self.code.centerCursor()
                        self.statusBar().showMessage(f"已在编辑器定位: {key}", 2000)
                        return
            block = block.next()
        self.statusBar().showMessage(f"编辑器中未找到键: {key}", 3000)


    def jump_to_tree_value(self, value: str, silent: bool = False) -> bool:
        """属性值 → 对象树定位并打开（逗号分隔则逐个尝试）。"""
        if not value:
            if not silent:
                self.statusBar().showMessage("值为空，无法在对象树定位", 3000)
            return False
        tokens = []
        for part in str(value).replace(";", ",").split(","):
            part = part.strip()
            if not part or part.lower() in ("none", "no", "yes", "true", "false"):
                continue
            if part.replace(".", "", 1).isdigit():
                continue
            tokens.append(part)
        if not tokens:
            if not silent:
                self.statusBar().showMessage(f"无法解析为对象 ID: {value}", 3000)
            return False
        root = self.tree.invisibleRootItem()
        for tok in tokens:
            for prefer in ("", "art", "ai"):
                it = self._find_tree_item(root, tok, group="", prefer=prefer)
                if it:
                    group = it.data(0, Qt.UserRole + 3) or ""
                    pref = it.data(0, Qt.UserRole + 2) or ""
                    self.select_tree_item(tok, group=str(group) if group else "", prefer=pref or prefer)
                    self.open_section_tab(tok, prefer=pref or prefer, group=str(group) if group else "")
                    self.statusBar().showMessage(f"已在对象树定位: {tok}", 2500)
                    return True
            sec = self.project.get_section(tok)
            if sec:
                self.open_section_tab(tok, prefer="", group="")
                self.select_tree_item(tok, group="", prefer="")
                self.statusBar().showMessage(f"已打开: {tok}（树中可能需展开）", 2500)
                return True
        if not silent:
            self.statusBar().showMessage(f"对象树中未找到: {value}", 3000)
        return False


    def toggle_word_wrap(self, checked: bool = None):
        if checked is None:
            checked = self.act_word_wrap.isChecked()
        else:
            self.act_word_wrap.setChecked(bool(checked))
        self._apply_word_wrap(bool(checked), save=True)

    def _apply_word_wrap(self, enabled: bool, save: bool = True):
        if not hasattr(self, "code") or self.code is None:
            return
        mode = QPlainTextEdit.WidgetWidth if enabled else QPlainTextEdit.NoWrap
        self.code.setLineWrapMode(mode)
        # 换行时用软换行，不插入真实换行符
        if hasattr(self.code, "setWordWrapMode"):
            from PySide6.QtGui import QTextOption
            self.code.setWordWrapMode(
                QTextOption.WrapAtWordBoundaryOrAnywhere if enabled else QTextOption.NoWrap
            )
        if save:
            st = self.project.config.setdefault("settings", {})
            st["code_word_wrap"] = bool(enabled)
            try:
                self.project.save_config()
            except Exception:
                pass
            self.statusBar().showMessage(
                "已开启自动换行" if enabled else "已关闭自动换行", 2500
            )

    def find_next(self):
        needle = self.find_edit.text()
        if not needle:
            return
        if not self.code.find(needle):
            c = self.code.textCursor()
            c.movePosition(QTextCursor.Start)
            self.code.setTextCursor(c)
            self.code.find(needle)

    def replace_all(self):
        a, b = self.find_edit.text(), self.replace_edit.text()
        if not a:
            QMessageBox.information(self, "替换", "请填写查找内容")
            return
        content = self.code.toPlainText()
        n = content.count(a)
        if not n:
            QMessageBox.information(self, "替换", "未找到")
            return
        self.code.setPlainText(content.replace(a, b))
        QMessageBox.information(self, "替换", f"已替换 {n} 处（尚未写盘，请保存）")



    def show_project_search(self):
        if not self.project.rules and not self.project.single_ini and not self.project.art:
            QMessageBox.information(self, "搜索", "请先打开工程或单文件")
            return
        dlg = ProjectSearchDialog(self)
        if self.current_section_id:
            dlg.edit.setText(self.current_section_id)
        dlg.exec()

    def lint_current_section(self):
        from core.linter import lint_section
        if not self.current_section_id:
            QMessageBox.information(self, "校验", "请先选择一个 section")
            return
        prefer = self.current_prefer or ""
        prefer_ini = None
        if prefer == "art" and self.project.art:
            prefer_ini = self.project.art
        elif prefer == "ai" and self.project.ai:
            prefer_ini = self.project.ai
        sec = self.project.get_section(self.current_section_id, prefer=prefer_ini)
        # 用编辑器正文覆盖内存键值再校验更准：简单解析 key=
        if sec and self.code.toPlainText().strip():
            from core.save_util import normalize_section_body
            body = normalize_section_body(self.current_section_id, self.code.toPlainText())
            for line in body.splitlines():
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("["):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    sec.set(k.strip(), v.strip())
        issues = lint_section(self.project, self.current_section_id, sec, source=prefer or "rules")
        if not issues:
            QMessageBox.information(self, "校验", "当前节未发现明显问题")
            return
        LintDialog(self, issues, "当前节校验").exec()

    def lint_whole_project(self):
        from core.linter import lint_project
        if not self.project.rules and not self.project.single_ini:
            QMessageBox.information(self, "校验", "请先打开工程")
            return
        issues = lint_project(self.project)
        if not issues:
            QMessageBox.information(self, "校验", "工程扫描完成，未发现明显问题")
            return
        LintDialog(self, issues, "工程校验").exec()

    def _auto_lint_enabled(self) -> bool:
        st = self.project.config.get("settings") or {}
        return bool(st.get("auto_lint_on_save", True))

    def _lint_before_save(self, section_id: str) -> bool:
        """单个保存：只校验当前节。True=继续保存。"""
        if not self._auto_lint_enabled():
            return True
        from core.linter import lint_section
        prefer = self.current_prefer or ""
        prefer_ini = None
        if prefer == "art" and self.project.art:
            prefer_ini = self.project.art
        elif prefer == "ai" and self.project.ai:
            prefer_ini = self.project.ai
        sec = self.project.get_section(section_id, prefer=prefer_ini)
        if sec and self.code.toPlainText().strip():
            from core.save_util import normalize_section_body
            body = normalize_section_body(section_id, self.code.toPlainText())
            for line in body.splitlines():
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("["):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    sec.set(k.strip(), v.strip())
        issues = lint_section(self.project, section_id, sec, source=prefer or "rules")
        errors = [i for i in issues if i.severity == "error"]
        if not errors:
            return True
        dlg = LintDialog(self, issues, "保存前校验（当前节）— 发现错误")
        return dlg.exec() == QDialog.Accepted

    def _lint_before_save_all(self) -> bool:
        """保存全部：校验整个工程。True=继续保存。"""
        if not self._auto_lint_enabled():
            return True
        from core.linter import lint_project
        issues = lint_project(self.project)
        errors = [i for i in issues if i.severity == "error"]
        if not errors:
            return True
        dlg = LintDialog(self, issues, "保存全部前校验（工程）— 发现错误")
        return dlg.exec() == QDialog.Accepted


    def show_find_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "查找", "查找内容:", text=self.find_edit.text())
        if ok and text:
            self.find_edit.setText(text)
            self.find_next()

    def show_replace_dialog(self):
        from PySide6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("替换")
        form = QFormLayout(dlg)
        fe = QLineEdit(self.find_edit.text())
        re_ = QLineEdit(self.replace_edit.text())
        form.addRow("查找", fe)
        form.addRow("替换为", re_)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Yes | QDialogButtonBox.No | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Yes).setText("全部替换")
        buttons.button(QDialogButtonBox.No).setText("查找下一个")
        form.addRow(buttons)

        def do_all():
            self.find_edit.setText(fe.text())
            self.replace_edit.setText(re_.text())
            self.replace_all()
            dlg.accept()

        def do_find():
            self.find_edit.setText(fe.text())
            self.replace_edit.setText(re_.text())
            self.find_next()

        buttons.button(QDialogButtonBox.Yes).clicked.connect(do_all)
        buttons.button(QDialogButtonBox.No).clicked.connect(do_find)
        buttons.rejected.connect(dlg.reject)
        dlg.exec()


    def _format_save_plan(self, plan: dict) -> str:
        files = plan.get("files") or []
        lines = ["将按键来源写入以下文件（确定后才会落盘）：", ""]
        for item in files:
            p = item.get("path") or ""
            n = int(item.get("count") or 0)
            name = Path(p).name if p else "?"
            if n == 0:
                lines.append("  • %s  — 清空本文件中该节的键" % name)
            else:
                lines.append("  • %s  — %d 条键" % (name, n))
            lines.append("      %s" % p)
        lines.append("")
        lines.append("是否继续保存？")
        return chr(10).join(lines)

    def _confirm_save_plan(self, plan: dict, title: str = "确认保存") -> bool:
        ret = QMessageBox.question(
            self,
            title,
            self._format_save_plan(plan),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return ret == QMessageBox.Yes

    def _save_section_with_confirm(
        self,
        section_id: str,
        body: str,
        path: Path,
        is_new: bool = False,
        peers=None,
    ) -> dict:
        """先出计划确认，再 confirmed 写盘。"""
        peers = peers or []
        if not self.project.project_dir and self.project.work_mode != "single":
            # 无工程：仍走旧单文件
            backup_root = Path(path).parent / "backups"
            return self._save_with_backup_root(section_id, body, path, is_new, peers, backup_root)

        plan = self.project.plan_section_write(
            section_id, body, target_path=Path(path), is_new=is_new
        )
        if not plan.get("ok"):
            return plan
        if not self._confirm_save_plan(plan, title="确认保存 [%s]" % section_id):
            return {"ok": False, "cancelled": True, "message": "已取消保存"}
        return self.project.save_section_text(
            section_id,
            body,
            target_path=Path(path),
            is_new=is_new,
            peer_ids=peers,
            confirmed=True,
        )

    def save_all(self):
        """保存所有内存中有草稿的单位 + 当前编辑区。"""
        self._store_current_to_mem()
        # 收集要保存的 key
        keys = set(self._mem_sections.keys())
        if self.current_section_id:
            keys.add(self._mem_key())
        if not keys:
            # 仍尝试保存当前
            if self.current_section_id:
                self.save_current()
            else:
                QMessageBox.information(self, "保存全部", "没有可保存的内容")
            return
        # 保存全部：自动校验整个工程（可在首选项关闭）
        if not self._lint_before_save_all():
            return
        ok_n, fail = 0, []
        # 静默保存：临时去掉每成功一次的弹窗
        old_code = self.code.toPlainText()
        old_sid = self.current_section_id
        old_prefer = self.current_prefer
        for key in sorted(keys):
            if key.startswith("art::"):
                sid, prefer = key[5:], "art"
            else:
                sid, prefer = key, ""
            body = self._mem_sections.get(key)
            if body is None and sid == old_sid:
                body = old_code
            if not body:
                continue
            # 切到该 section 的上下文写盘
            self.current_section_id = sid
            self.current_prefer = prefer
            path = None
            if prefer == "art" and self.project.art:
                sec = self.project.art.get_section(sid)
                if sec and sec.source_file:
                    path = self.project._resolve_name(sec.source_file)
            if path is None:
                path = self.project.get_source_path_for_section(sid)
            if path is None or not Path(path).is_file():
                fail.append(f"{sid}: 无来源文件")
                continue
            peers = self._peers_for(sid)
            backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
            result = self._save_section_with_confirm(
                sid, body, Path(path), is_new=False, peers=peers
            )
            if result.get("ok"):
                ok_n += 1
                self._mem_sections[key] = body
            elif result.get("cancelled"):
                fail.append(f"{sid}: 用户取消")
                break
            else:
                fail.append(f"{sid}: {result.get('message', '失败')}")
        # 恢复当前编辑视图
        self.current_section_id = old_sid
        self.current_prefer = old_prefer
        self._dirty = False
        msg = f"已保存 {ok_n} 个单位到磁盘。"
        if fail:
            msg += "\n失败:\n" + "\n".join(fail[:8])
            QMessageBox.warning(self, "保存全部", msg)
        else:
            QMessageBox.information(self, "保存全部", msg)
        self.statusBar().showMessage(msg.replace("\n", " "), 8000)

    def save_current(self):
        """保存 = 写回当前 section 的来源文件（或单文件模式下的当前文件）"""
        if not self.current_section_id:
            QMessageBox.information(self, "提示", "请先选择一个 section")
            return
        section_id = self.current_section_id
        if not self._lint_before_save(section_id):
            return
        body = self.code.toPlainText()
        path = self.project.get_source_path_for_section(section_id)
        is_new = False
        if path is None or not Path(path).is_file():
            path_str, _ = QFileDialog.getOpenFileName(
                self, "选择要写入的 INI 文件",
                str(self.project.project_dir or Path.home()),
                "INI (*.ini);;All (*.*)",
            )
            if not path_str:
                return
            path = Path(path_str)
            is_new = True
        peers = self._peers_for(section_id)
        result = self._save_section_with_confirm(
            section_id, body, Path(path), is_new=is_new, peers=peers
        )
        if result.get("ok"):
            self._dirty = False
            k = self._mem_key(section_id)
            if k:
                self._mem_sections[k] = body
            files = result.get("files") or []
            if files:
                parts = ["已写入 %d 个文件:" % len(files)]
                for f in files:
                    parts.append(
                        "  %s (%d 键)" % (Path(f.get("path", "")).name, int(f.get("count") or 0))
                    )
                summary = chr(10).join(parts)
            else:
                summary = result.get("message", "已写入磁盘")
            QMessageBox.information(self, "保存成功", summary)
            self.statusBar().showMessage("已保存 %s" % section_id, 8000)
        elif result.get("cancelled"):
            self.statusBar().showMessage("已取消保存", 3000)
        else:
            QMessageBox.critical(self, "保存失败", result.get("message", "失败"))

    def _save_with_backup_root(self, section_id, body, path, is_new, peers, backup_root):
        from core.save_util import save_section_to_file
        return save_section_to_file(
            Path(path), section_id, body, backup_root=backup_root,
            is_new=is_new, peer_section_names=peers,
        )

    def save_as(self):
        """另存为：仅把「当前编辑器中的这一节」写到新文件，不改原文件。"""
        if not self.current_section_id:
            QMessageBox.information(self, "提示", "请先选择一个 section")
            return
        section_id = self.current_section_id
        path_str, _ = QFileDialog.getSaveFileName(
            self, "另存为（只写入当前单位/节，不改原文件）",
            str(self.project.project_dir or Path.home()),
            "INI 文件 (*.ini)",
        )
        if not path_str:
            return
        path = Path(path_str)
        from core.save_util import normalize_section_body, save_section_to_file, encode_ini_bytes, read_text

        body = normalize_section_body(section_id, self.code.toPlainText())
        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")

        # 新文件：只写这一节，绝不把整个工程塞进去
        # 已存在：只替换/插入这一节一次（save_section_to_file 内部已处理“找不到则追加”）
        if not path.exists():
            try:
                backup_root.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                data = encode_ini_bytes(
                    f"; Saved by INI Project Editor — section only\n{body}",
                    "utf-8",
                )
                path.write_bytes(data)
                result = {"ok": True, "message": f"已新建并写入 [{section_id}] → {path}", "path": str(path)}
            except Exception as e:
                result = {"ok": False, "message": str(e)}
        else:
            result = save_section_to_file(
                path, section_id, body, backup_root=backup_root,
                is_new=False, peer_section_names=[],
            )

        if not result.get("ok"):
            QMessageBox.critical(self, "另存为失败", result.get("message", ""))
            return

        # 同步编辑器为规范后的单节，避免界面仍显示重复头
        self._loading_section = True
        self.code.blockSignals(True)
        self.code.setPlainText(body if body.endswith("\n") else body + "\n")
        self.code.blockSignals(False)
        self._loading_section = False

        box = QMessageBox(self)
        box.setWindowTitle("另存为成功")
        box.setText(result.get("message", "OK"))
        box.setInformativeText("是否用该文件作为单文件模式打开？（原工程文件不会被修改）")
        yes = box.addButton("打开新文件", QMessageBox.AcceptRole)
        box.addButton("保持当前", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == yes:
            self.project.open_single_file(path)
            self.project._add_allowed(path)
            self._refresh_file_combo()
            self.act_single.setChecked(True)
            self.file_row.show()
            self._update_chrome()
            self.refresh_tree()
            self.open_section_tab(section_id)
        self.statusBar().showMessage(f"另存为 → {path}", 8000)

    def _peers_for(self, section_id: str) -> List[str]:
        peers = []
        ini = self.project.active_ini()
        if ini:
            for ids in self.project.get_type_lists(ini).values():
                if any(i.lower() == section_id.lower() for i in ids):
                    return list(ids)
        return peers


    def open_debug_window(self):
        """单单位调试：动态字段 + hotfix 部署 + 回写工程"""
        if not self.current_section_id:
            QMessageBox.information(self, "调试", "请先在对象树中选择一个单位/section")
            return
        sid = self.current_section_id
        # 优先用代码区当前内容（可能已改未保存）
        if self.code.toPlainText().strip():
            initial = self.code.toPlainText()
        else:
            initial = self.project.get_section_text(sid)
        # 保持窗口引用，避免被回收
        if not hasattr(self, "_debug_windows"):
            self._debug_windows = {}

        def on_written(section_id: str):
            if self.current_section_id == section_id:
                self.show_section(section_id)
            self._display_cache.pop(section_id, None)
            self.statusBar().showMessage(f"调试回写完成: {section_id}", 5000)

        # 若已有该单位调试窗，激活
        old = self._debug_windows.get(sid)
        if old is not None:
            try:
                old.raise_()
                old.activateWindow()
                return
            except Exception:
                pass

        win = DebugWindow(
            self.project, sid, initial, self.flag_schema,
            parent=self, on_written_back=on_written,
        )
        self._debug_windows[sid] = win

        def _clear(_sid=sid):
            self._debug_windows.pop(_sid, None)

        win.finished.connect(lambda _r: _clear())
        win.show()

    def on_add_new(self):
        if not self.project.project_dir and not self.project.single_path:
            QMessageBox.information(self, "新增", "请先打开工程或单文件")
            return
        dlg = NewUnitDialog(self.project, self)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.result_data()
        if not data:
            QMessageBox.warning(self, "新增", "注册名无效")
            return
        sid = data["id"]
        type_list = data["type_list"]
        path_str = data["path"]
        if not path_str:
            path_str, _ = QFileDialog.getSaveFileName(
                self, "选择写入单位代码的 INI", str(self.project.project_dir or Path.home()), "INI (*.ini)"
            )
            if not path_str:
                return
        path = Path(path_str)
        tmpl = NEW_TEMPLATES.get(type_list, "[{id}]\nName={id}\n")
        body = tmpl.format(id=sid)
        if data["name"]:
            lines = []
            for ln in body.splitlines():
                if ln.startswith("Name="):
                    lines.append(f"Name={data['name']}")
                else:
                    lines.append(ln)
            body = "\n".join(lines) + "\n"

        peers = []
        ini = self.project.active_ini()
        if ini:
            peers = ini.get_list(type_list)

        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        from core.save_util import save_section_to_file
        result = save_section_to_file(
            path, sid, body, backup_root=backup_root, is_new=True, peer_section_names=peers
        )
        if not result.get("ok"):
            QMessageBox.critical(self, "新增失败", result.get("message", ""))
            return

        # 注册表：只写到含有该注册表的文件
        reg_msg = ""
        if data.get("also_register") and data.get("register_path"):
            reg_result = self._append_to_type_list(Path(data["register_path"]), type_list, sid)
            reg_msg = reg_result.get("message", "")
            if not reg_result.get("ok"):
                QMessageBox.warning(self, "注册表写入失败", reg_msg)
        # 同步进工程内存，对象树立刻能看见
        self.project.inject_section_memory(
            sid, body, source_path=path,
            type_list=type_list if data.get("also_register") else None,
        )
        # 编辑器内存草稿
        self._mem_sections[sid] = body
        if self.project.work_mode == "single" and self.project.single_path:
            self.project.open_single_file(self.project.single_path)
            self.project.inject_section_memory(
                sid, body, source_path=path,
                type_list=type_list if data.get("also_register") else None,
            )
        self._display_cache.clear()
        self.refresh_tree()
        self.open_section_tab(sid)
        QMessageBox.information(
            self, "新增成功",
            f"代码: [{sid}] → {path}\n{result.get('message', '')}\n注册表: {reg_msg or '（未写入注册表）'}"
        )

    def _append_to_type_list(self, path: Path, type_list: str, new_id: str) -> dict:
        """在 [TypeList] 末尾追加注册。优先 +=ID（Ares）；失败回退数字序号。返回 {ok, message}"""
        from core.save_util import read_text, backup_file
        import re
        path = Path(path)
        if not path.is_file():
            # 相对工程目录再试
            if self.project.project_dir:
                alt = self.project.project_dir / path
                if alt.is_file():
                    path = alt
                else:
                    return {"ok": False, "message": f"注册表文件不存在: {path}"}
            else:
                return {"ok": False, "message": f"注册表文件不存在: {path}"}
        try:
            text, enc = read_text(path)
        except Exception as e:
            return {"ok": False, "message": f"读取注册表失败: {e}"}

        m = re.search(rf"(?im)^\[{re.escape(type_list)}\]\s*\r?\n", text)
        if not m:
            backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
            try:
                backup_file(path, backup_root)
            except Exception:
                pass
            add = f"\n[{type_list}]\n+={new_id}\n"
            try:
                path.write_text(text + add, encoding=enc)
            except Exception as e:
                return {"ok": False, "message": f"写入失败: {e}"}
            return {"ok": True, "message": f"已新建 [{type_list}] 并注册 +={new_id} → {path}"}

        start = m.end()
        rest = text[start:]
        next_sec = re.search(r"(?m)^\[", rest)
        end = start + (next_sec.start() if next_sec else len(rest))
        block = text[start:end]
        # 已存在？
        if re.search(rf"(?im)^[^=]+=\s*{re.escape(new_id)}\s*$", block):
            return {"ok": True, "message": f"[{new_id}] 已在注册表中"}
        if re.search(rf"(?im)^\+=\s*{re.escape(new_id)}\s*$", block):
            return {"ok": True, "message": f"[{new_id}] 已在注册表中"}

        # 优先 += ；若文件全是数字键也可 +=
        insert_line = f"+={new_id}\n"
        block_stripped = block.rstrip("\r\n") + "\n" + insert_line
        if block.endswith("\n\n"):
            block_stripped += "\n"
        new_text = text[:start] + block_stripped + text[end:]
        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        try:
            backup_file(path, backup_root)
        except Exception:
            pass
        try:
            path.write_text(new_text, encoding=enc)
        except Exception as e:
            return {"ok": False, "message": f"写入注册表失败: {e}"}
        return {"ok": True, "message": f"已注册 +={new_id} → {path.name} [{type_list}]"}

    def _quick_view(self, mode: str):
        """工具栏快捷切换合并/单文件视图"""
        if mode == "merged":
            if not self.project.project_dir:
                QMessageBox.information(self, "视图", "请先打开工程目录")
                return
            if not self._confirm_discard_if_dirty():
                return
            self._store_current_to_mem()
            self.act_merged.setChecked(True)
            self.project.set_merged_mode()
            self.file_row.hide()
            self.tabs.clear()
            # 切换视图清空内存草稿，避免串文件
            self._mem_sections.clear()
            self._dirty = False
            self._update_chrome()
            self.refresh_tree()
        else:
            if not self._confirm_discard_if_dirty():
                return
            files = self.project.list_ini_files()
            if self.project.single_path:
                path = self.project.single_path
            elif files:
                path = files[0]
            else:
                QMessageBox.information(self, "视图", "没有可切换的单文件")
                return
            self._store_current_to_mem()
            self.project.open_single_file(path)
            self.act_single.setChecked(True)
            self.file_row.show()
            self._refresh_file_combo()
            self.tabs.clear()
            self._mem_sections.clear()
            self._dirty = False
            self._update_chrome()
            self.refresh_tree()

    def delete_current_section(self):
        """删除当前 section：源文件 + 内存 + 可选从注册表去掉。"""
        sid = self.current_section_id
        if not sid:
            QMessageBox.information(self, "删除", "请先选择一个 section")
            return
        prefer = getattr(self, "current_prefer", "") or ""
        src = None
        if prefer == "art" and self.project.art:
            sec = self.project.art.get_section(sid)
            if sec and sec.source_file:
                src = self.project._resolve_name(sec.source_file)
            if not src:
                for sp, names in (self.project.art.file_sections or {}).items():
                    if any(n.lower() == sid.lower() for n in names):
                        src = Path(sp)
                        break
        if src is None:
            src = self.project.get_source_path_for_section(sid)
        if not src or not Path(src).is_file():
            QMessageBox.warning(self, "删除", "无法确定源文件，取消删除")
            return

        ret = QMessageBox.question(
            self, "确认删除",
            f"确定从文件中删除 [{sid}]？\n\n{src}\n\n会先自动备份。\n"
            f"（若在注册表中也会尽量去掉对应项）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        from core.save_util import read_text, backup_file
        import re
        path = Path(src)
        try:
            text, enc = read_text(path)
        except Exception as e:
            QMessageBox.critical(self, "删除", f"读取失败: {e}")
            return

        # 兼容 CRLF / 大小写 / 行尾注释
        pat = re.compile(
            rf"(?ims)^\[{re.escape(sid)}\][^\n\r]*\r?\n.*?(?=^\[|\Z)"
        )
        new_text, n = pat.subn("", text, count=1)
        if n == 0:
            # 再试：只匹配节名行后直到下一节（更宽松）
            pat2 = re.compile(
                rf"(?is)\[{re.escape(sid)}\][^\n\r]*\r?\n.*?(?=\[|\Z)"
            )
            new_text, n = pat2.subn("", text, count=1)
        if n == 0:
            QMessageBox.warning(self, "删除", f"在文件中未找到 [{sid}] 节\n文件: {path}")
            return

        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        try:
            backup_file(path, backup_root)
        except Exception:
            pass
        try:
            path.write_text(new_text, encoding=enc)
        except Exception as e:
            QMessageBox.critical(self, "删除", f"写入失败: {e}")
            return

        # 从各注册表文件去掉该 ID（磁盘）
        reg_notes = []
        for tl, files in list((self.project.type_list_index or {}).items()):
            for fp in files:
                r = self._remove_from_type_list(Path(fp), tl, sid)
                if r.get("ok") and r.get("changed"):
                    reg_notes.append(f"{tl}@{Path(fp).name}")

        # 内存清理
        self._remove_section_from_memory(sid, prefer=prefer)
        self._mem_sections.pop(sid, None)
        self._mem_sections.pop(f"art::{sid}", None)

        # 关 tab
        for i in range(self.tabs.count() - 1, -1, -1):
            title = self.tabs.tabText(i)
            if title == sid or title.startswith(sid + " ·"):
                self.tabs.removeTab(i)
        self.current_section_id = None
        self.current_prefer = ""
        self.code.setPlainText("")
        self.prop.clear()
        self.source_label.setText("")
        self._dirty = False
        self._display_cache.clear()
        self.refresh_tree()
        self.schedule_display_cache_rebuild()
        extra = ("\n注册表已清理: " + ", ".join(reg_notes)) if reg_notes else ""
        QMessageBox.information(self, "删除", f"已删除 [{sid}]\n文件: {path}\n备份: {backup_root}{extra}")

    def _remove_from_type_list(self, path: Path, type_list: str, unit_id: str) -> dict:
        """从 [TypeList] 中删除某 ID 行。"""
        from core.save_util import read_text, backup_file
        import re
        path = Path(path)
        if not path.is_file():
            return {"ok": False, "changed": False}
        try:
            text, enc = read_text(path)
        except Exception:
            return {"ok": False, "changed": False}
        m = re.search(rf"(?im)^\[{re.escape(type_list)}\]\s*\r?\n", text)
        if not m:
            return {"ok": True, "changed": False}
        start = m.end()
        rest = text[start:]
        next_sec = re.search(r"(?m)^\[", rest)
        end = start + (next_sec.start() if next_sec else len(rest))
        block = text[start:end]
        new_block, n = re.subn(
            rf"(?im)^[^=\n]+=\s*{re.escape(unit_id)}\s*\r?\n",
            "",
            block,
        )
        if n == 0:
            return {"ok": True, "changed": False}
        new_text = text[:start] + new_block + text[end:]
        backup_root = (self.project.project_dir / "backups") if self.project.project_dir else (path.parent / "backups")
        try:
            backup_file(path, backup_root)
        except Exception:
            pass
        try:
            path.write_text(new_text, encoding=enc)
        except Exception as e:
            return {"ok": False, "changed": False, "message": str(e)}
        return {"ok": True, "changed": True}

    def _remove_section_from_memory(self, section_id: str, prefer: str = ""):
        """从已加载的 INI 对象中去掉该节，并清理注册表内存项。"""
        inis = []
        if prefer == "art" and self.project.art:
            inis = [self.project.art]
        else:
            for ini in (self.project.rules, self.project.art, self.project.ai, self.project.single_ini):
                if ini:
                    inis.append(ini)
        sid_l = section_id.lower()
        for ini in inis:
            dead = [k for k in list(ini.sections.keys()) if k.lower() == sid_l]
            for k in dead:
                del ini.sections[k]
            ini.section_order = [x for x in ini.section_order if x.lower() != sid_l]
            # 注册表值里去掉
            for name, sec in list(ini.sections.items()):
                if not name.endswith("Types") and name not in (
                    "Warheads", "Animations", "Particles", "ParticleSystems", "Projectiles", "Countries"
                ):
                    # 仍检查所有像列表的节
                    pass
                to_del = []
                for k, v in list(sec.keys.items()):
                    if v.strip().lower() == sid_l:
                        to_del.append(k)
                for k in to_del:
                    if k in sec.keys:
                        del sec.keys[k]
                    if k in sec.key_order:
                        sec.key_order.remove(k)
        self.project.section_sources.pop(sid_l, None)


    def show_help(self):
        text = (
            f"<h3>{APP_TITLE}</h3>"
            "<p><b>适用</b>：红警2 尤里的复仇 / 心灵终结 等基于 INI 的 Mod 工程。</p>"
            "<p><b>打开</b>：工程目录（按 profile 读 rules/art/ai/csf）或单个 ini。</p>"
            "<p><b>编辑</b>：对象树选择单位；中间改代码；右侧为属性说明（只读）。</p>"
            "<p><b>保存</b>：保存当前 / 保存全部 → 写回来源文件（自动备份）。"
            "编码为 <b>UTF-8（无 BOM）</b>，兼容游戏引擎与热重载。</p>"
            "<p><b>调试</b>：可部署到 hotfix.ini，配合 AutoReloader 热重载。</p>"
            "<p><b>配置</b>：菜单「配置」可选 Mental Omega / Yuri's Revenge 等 profile。</p>"
        )
        box = QMessageBox(self)
        box.setWindowTitle("使用说明")
        box.setTextFormat(Qt.RichText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def show_about(self):
        QMessageBox.about(
            self,
            "关于",
            f"{APP_TITLE} ({APP_TITLE_EN})\n"
            f"版本 {APP_VERSION}\n\n"
            "AutoReloader 工具链 · 前端工程编辑器\n"
            "开源仓库以 AutoReloader 为准。\n\n"
            "保存格式：UTF-8 无 BOM\n"
            "热重载：配合 AutoReloader.dll + 启动器",
        )

    def closeEvent(self, event):
        if not self._confirm_discard_if_dirty():
            event.ignore()
            return
        try:
            if self.project.project_dir:
                st = self.project.config.setdefault("settings", {})
                st["last_project_dir"] = str(Path(self.project.project_dir).resolve())
                self.project.save_config()
        except Exception:
            pass
        event.accept()


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("INI 工程编辑器")
    app.setStyle("Fusion")
    cfg = user_config_path()
    win = MainWindow(Project(cfg))
    win.show()
    try:
        st = win.project.config.get("settings") or {}
        last = st.get("last_project_dir") or ""
        if last and Path(last).is_dir():
            from PySide6.QtCore import QTimer
            QTimer.singleShot(200, lambda: win.open_project(last))
    except Exception:
        pass
    sys.exit(app.exec())
