
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

from PySide6.QtCore import Qt, QTimer, QSize, QRect, QPoint
from PySide6.QtGui import (
    QPainterPath, QAction, QActionGroup, QKeySequence, QTextCursor, QPainter, QColor, QFont,
    QTextFormat, QIcon, QMouseEvent, QBrush, QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsSimpleTextItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QLineEdit, QLabel, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QFileDialog, QToolBar,
    QStatusBar, QTabWidget, QSizePolicy, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QCheckBox, QTextEdit, QMenu, QListWidget, QListWidgetItem, QAbstractItemView,
)

from core.project import Project
from paths import app_dir, bundle_dir, user_config_path, user_cache_dir, is_frozen

APP_TITLE = "INI 工程编辑器"
APP_TITLE_EN = "INI Project Editor"
APP_VERSION = "2.1.0"

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event):
        if hasattr(self.editor, "line_number_area_mouse_press"):
            self.editor.line_number_area_mouse_press(event)
        else:
            super().mousePressEvent(event)


class CodeEditor(QPlainTextEdit):
    """带行号、INI 高亮的代码编辑框。注释折叠不改动 QTextBlock 布局，避免行号错乱。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_area = LineNumberArea(self)
        self._comments_collapsed = False
        self._text_before_fold: str = ""
        self._lint_selections: list = []
        self._lint_tooltips: dict = {}  # block_number -> message
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        try:
            from ui.ini_highlighter import IniHighlighter
            self._highlighter = IniHighlighter(self.document(), dark=True)
        except Exception:
            self._highlighter = None
        self.setMouseTracking(True)

    def set_editor_font_size(self, pt: int):
        """用控件级样式设置字号（覆盖全局 QSS 时也生效）。"""
        pt = max(9, min(28, int(pt)))
        self._font_pt = pt
        self.setStyleSheet(
            "QPlainTextEdit {"
            "  background: #0a0a0c; color: #d4d4d4;"
            "  border: 1px solid #3a3a48; border-radius: 6px;"
            f"  font-family: Consolas, 'Cascadia Mono', 'Courier New', monospace;"
            f"  font-size: {pt}pt;"
            "  selection-background-color: #5b4b8a;"
            "  padding: 4px;"
            "}"
        )
        f = self.font()
        f.setFamily("Consolas")
        f.setPointSize(pt)
        self.setFont(f)
        self.update_line_number_area_width(0)
        self.viewport().update()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(max(1, self.blockCount()))))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

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
        self._comments_collapsed = False
        self._text_before_fold = ""
        super().setPlainText(text)
        self.update_line_number_area_width(0)
        QTimer.singleShot(0, lambda: self.update_line_number_area_width(0))

    def showEvent(self, event):
        super().showEvent(event)
        self.update_line_number_area_width(0)

    @staticmethod
    def _is_comment_line(text: str) -> bool:
        s = (text or "").lstrip()
        return bool(s) and s.startswith(";")

    def fold_all_comments(self) -> int:
        """
        用「去掉注释行」的方式折叠，不调用 QTextBlock.setVisible，
        避免破坏布局导致行号重复/错乱。展开时恢复原文。
        """
        if self._comments_collapsed:
            return 0
        full = self.toPlainText()
        lines = full.splitlines(keepends=True)
        kept = []
        n = 0
        for line in lines:
            raw = line[:-1] if line.endswith("\n") else line
            if raw.endswith("\r"):
                raw = raw[:-1]
            if self._is_comment_line(raw):
                n += 1
                continue
            kept.append(line)
        if n == 0:
            return 0
        self._text_before_fold = full
        self._comments_collapsed = True
        # 保持光标尽量不乱：直接替换正文
        cur = self.textCursor().position()
        self.blockSignals(True)
        super().setPlainText("".join(kept))
        self.blockSignals(False)
        self.update_line_number_area_width(0)
        # 提示：折叠中编辑会在展开时被原文覆盖风险——折叠仅作阅读
        return n

    def expand_all_folds(self) -> int:
        if not self._comments_collapsed or not self._text_before_fold:
            self._comments_collapsed = False
            self._text_before_fold = ""
            return 0
        text = self._text_before_fold
        self._comments_collapsed = False
        self._text_before_fold = ""
        self.blockSignals(True)
        super().setPlainText(text)
        self.blockSignals(False)
        self.update_line_number_area_width(0)
        return text.count("\n") + 1

    def line_number_area_paint_event(self, event):
        """标准 QPlainTextEdit 行号绘制：严格用 block.blockNumber()。"""
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), QColor("#1a1a1e"))

        block = self.firstVisibleBlock()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = block.blockNumber() + 1
                painter.setPen(QColor("#6a6a75"))
                painter.drawText(
                    0, top, self._line_area.width() - 4, height,
                    Qt.AlignRight | Qt.AlignVCenter,
                    str(number),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

    def line_number_area_mouse_press(self, event: QMouseEvent):
        # 不再用行号区点选折叠，避免误触
        pass

    def highlight_current_line(self):
        from PySide6.QtWidgets import QTextEdit
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor("#2a2a35"))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        # 保留校验波浪线，叠在当前行高亮之上
        extras = [selection]
        extras.extend(getattr(self, "_lint_selections", []) or [])
        self.setExtraSelections(extras)

    def clear_lint_marks(self):
        self._lint_selections = []
        self._lint_tooltips = {}
        self.highlight_current_line()

    def apply_lint_marks(self, issues: list):
        """
        issues: LintIssue 或 dict，需有 key / message / severity。
        按文档中「key=」行画红色波浪下划线；悬停行号区域或行上显示原因。
        """
        from PySide6.QtWidgets import QTextEdit
        from PySide6.QtGui import QTextCharFormat

        self._lint_selections = []
        self._lint_tooltips = {}
        if not issues:
            self.highlight_current_line()
            return

        # key(lower) -> messages
        by_key: dict = {}
        for iss in issues:
            if hasattr(iss, "key"):
                k = (iss.key or "").strip()
                msg = iss.message or ""
                sev = getattr(iss, "severity", "warning") or "warning"
            else:
                k = str(iss.get("key") or "").strip()
                msg = str(iss.get("message") or "")
                sev = str(iss.get("severity") or "warning")
            if not k:
                continue
            by_key.setdefault(k.lower(), []).append((sev, msg))

        doc = self.document()
        block = doc.begin()
        while block.isValid():
            text = block.text().strip()
            if text and not text.startswith(";") and not text.startswith("[") and "=" in text:
                key = text.split("=", 1)[0].strip()
                msgs = by_key.get(key.lower())
                if msgs:
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    sel = QTextEdit.ExtraSelection()
                    fmt = QTextCharFormat()
                    is_err = any(s == "error" for s, _ in msgs)
                    if is_err:
                        fmt.setUnderlineColor(QColor("#f87171"))
                        fmt.setBackground(QColor(127, 29, 29, 90))
                    else:
                        fmt.setUnderlineColor(QColor("#fb923c"))
                        fmt.setBackground(QColor(120, 53, 15, 80))
                    # WaveUnderline 在部分主题下不明显，再加 SpellCheck 风格兜底
                    try:
                        fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
                    except Exception:
                        fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)
                    sel.format = fmt
                    sel.cursor = cursor
                    self._lint_selections.append(sel)
                    tip = "\n".join(m for _, m in msgs)
                    self._lint_tooltips[block.blockNumber()] = tip
            block = block.next()
        self.highlight_current_line()

    def event(self, event):
        # 悬停显示校验原因
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.ToolTip:
            try:
                from PySide6.QtGui import QCursor
                pos = self.viewport().mapFromGlobal(QCursor.pos())
                cursor = self.cursorForPosition(pos)
                bn = cursor.blockNumber()
                tip = (self._lint_tooltips or {}).get(bn)
                if tip:
                    from PySide6.QtWidgets import QToolTip
                    QToolTip.showText(QCursor.pos(), tip, self)
                    return True
            except Exception:
                pass
        return super().event(event)


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
        self.name_edit.setPlaceholderText("可选，写入 Name=（编辑器/内部名）")
        layout.addRow("内部名 Name=", self.name_edit)

        self.csf_zh_edit = QLineEdit()
        self.csf_zh_edit.setPlaceholderText("游戏界面中文 → CSF 键 Name:注册名")
        layout.addRow("CSF 中文名", self.csf_zh_edit)
        self.write_csf = QCheckBox("保存时写入 CSF（UIName=Name:ID）")
        self.write_csf.setChecked(True)
        self.write_csf.setToolTip(
            "写入 CSF：Name:ID = 中文名；与 Name= 内部名无关。不填中文则跳过。"
        )
        layout.addRow(self.write_csf)

        self.body_combo = QComboBox()
        self._all_files = list(project.list_ini_files())
        if project.work_mode == "single" and project.single_path:
            sp = project.single_path.resolve()
            if sp not in [f.resolve() for f in self._all_files]:
                self._all_files.insert(0, sp)
        for f in self._all_files:
            self.body_combo.addItem(self._label(f), str(f))
        if self.body_combo.count() == 0:
            self.body_combo.addItem("（稍后选择）", "")
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
            "write_csf": bool(getattr(self, "write_csf", None) and self.write_csf.isChecked()),
            "csf_text": (getattr(self, "csf_zh_edit", None).text().strip()
                         if getattr(self, "csf_zh_edit", None) else ""),
        }




class CloneUnitDialog(QDialog):
    """B1 克隆单位向导：模板 → 新 ID、可选复制 art、注册表、CSF、重名校验。"""

    def __init__(self, project: Project, parent=None, default_src: str = ""):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("克隆单位")
        self.setMinimumWidth(520)
        layout = QFormLayout(self)

        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("模板注册名，例如 GACNST / E1")
        if default_src:
            self.src_edit.setText(default_src)
        layout.addRow("模板 ID", self.src_edit)

        self.src_info = QLabel("")
        self.src_info.setStyleSheet("color:#b0b8c4; font-size:12px;")
        self.src_info.setWordWrap(True)
        layout.addRow("", self.src_info)

        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("新注册名（勿重复、勿空格）")
        layout.addRow("新注册名", self.id_edit)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("可选：覆盖 Name=；空则沿用模板")
        layout.addRow("内部名 Name=", self.name_edit)

        self.csf_zh_edit = QLineEdit()
        self.csf_zh_edit.setPlaceholderText("游戏界面中文 → CSF 键 Name:新ID")
        layout.addRow("CSF 中文名", self.csf_zh_edit)
        self.write_csf = QCheckBox("保存时写入 CSF（UIName=Name:ID）")
        self.write_csf.setChecked(True)
        self.write_csf.setToolTip("写入 CSF：Name:ID = 中文名；与 Name= 无关。不填中文则跳过。")
        layout.addRow(self.write_csf)

        self.type_combo = QComboBox()
        for k in list(NEW_TEMPLATES.keys()) + [
            "SuperWeaponTypes", "ProjectileTypes", "TaskForces", "ScriptTypes", "TeamTypes"
        ]:
            if self.type_combo.findData(k) < 0:
                self.type_combo.addItem(TYPE_LABELS.get(k, k), k)
        self.type_combo.currentIndexChanged.connect(self._refresh_register_files)
        layout.addRow("注册表类型", self.type_combo)

        self.body_combo = QComboBox()
        self._all_files = list(project.list_ini_files())
        if project.work_mode == "single" and project.single_path:
            sp = project.single_path.resolve()
            if sp not in [f.resolve() for f in self._all_files]:
                self._all_files.insert(0, sp)
        for f in self._all_files:
            self.body_combo.addItem(self._label(f), str(f))
        if self.body_combo.count() == 0:
            self.body_combo.addItem("（与模板同文件）", "")
        layout.addRow("写入 rules 代码到", self.body_combo)

        self.copy_art = QCheckBox("同时克隆 Art 节（若模板有同名 art）")
        self.copy_art.setChecked(True)
        layout.addRow(self.copy_art)

        self.also_register = QCheckBox("写入注册表（推荐 +=ID）")
        self.also_register.setChecked(True)
        self.also_register.toggled.connect(self._on_reg_toggled)
        layout.addRow(self.also_register)

        self.reg_combo = QComboBox()
        layout.addRow("写入注册表到", self.reg_combo)
        self.reg_hint = QLabel("")
        self.reg_hint.setStyleSheet("color:#b0b8c4; font-size:12px;")
        self.reg_hint.setWordWrap(True)
        layout.addRow(self.reg_hint)

        self.rewrite_identity = QCheckBox("改写 Image / UIName 中的模板 ID → 新 ID")
        self.rewrite_identity.setChecked(True)
        layout.addRow(self.rewrite_identity)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._try_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.src_edit.textChanged.connect(self._on_src_changed)
        self._on_src_changed(self.src_edit.text())
        self._on_reg_toggled(True)

    def _label(self, f: Path) -> str:
        try:
            if self.project.project_dir:
                return str(f.relative_to(self.project.project_dir))
        except Exception:
            pass
        return f.name

    def _guess_type_list(self, sid: str) -> str:
        ini = self.project.rules or self.project.active_ini()
        if not ini:
            return "VehicleTypes"
        try:
            groups = self.project.classify_sections(ini)
            for gname, ids in groups.items():
                if any(u.lower() == sid.lower() for u in ids):
                    if gname in TYPE_LABELS or gname.endswith("Types") or gname in (
                        "Warheads", "Animations", "Projectiles"
                    ):
                        return gname
        except Exception:
            pass
        return "VehicleTypes"

    def _on_src_changed(self, _t: str = ""):
        sid = self.src_edit.text().strip()
        if not sid:
            self.src_info.setText("输入模板 ID 后显示来源信息")
            return
        sec = self.project.get_section(sid)
        if not sec:
            self.src_info.setText(f"未在 rules 中找到 [{sid}]")
            self.src_info.setStyleSheet("color:#f59e0b; font-size:12px;")
            return
        src = self.project.get_source_path_for_section(sid) or "?"
        has_art = bool(self.project.art and self.project.art.get_section(sid))
        tl = self._guess_type_list(sid)
        if hasattr(self, "type_combo"):
            idx = self.type_combo.findData(tl)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        if src and src != "?" and hasattr(self, "body_combo"):
            sp = str(Path(src).resolve())
            for i in range(self.body_combo.count()):
                d = self.body_combo.itemData(i)
                if d and Path(d).resolve() == Path(sp):
                    self.body_combo.setCurrentIndex(i)
                    break
        self.src_info.setText(
            f"模板 [{sid}] · 类型约 {tl} · 来源 {src}"
            + (" · 有 Art" if has_art else " · 无 Art 节")
        )
        self.src_info.setStyleSheet("color:#86efac; font-size:12px;")
        if hasattr(self, "copy_art"):
            self.copy_art.setEnabled(has_art)
            if not has_art:
                self.copy_art.setChecked(False)
        if hasattr(self, "type_combo"):
            self._refresh_register_files()

    def _files_with_type_list(self, type_list: str) -> list:
        files = self.project.files_with_type_list(type_list)
        if files:
            return files
        if self.project.single_ini and self.project.single_path:
            if self.project.single_ini.get_section(type_list):
                return [self.project.single_path]
        return []

    def _refresh_register_files(self):
        type_list = self.type_combo.currentData() or "VehicleTypes"
        self.reg_combo.clear()
        files = self._files_with_type_list(type_list)
        for f in files:
            self.reg_combo.addItem(self._label(f), str(f))
        if not files:
            self.reg_combo.addItem("（没有文件含此注册表）", "")
            self.reg_hint.setText(f"无文件包含 [{type_list}]，可取消注册或换类型")
            self.reg_hint.setStyleSheet("color:#f59e0b; font-size:12px;")
        else:
            self.reg_hint.setText(f"含 [{type_list}] 的文件共 {len(files)} 个")
            self.reg_hint.setStyleSheet("color:#b0b8c4; font-size:12px;")

    def _on_reg_toggled(self, checked: bool):
        self.reg_combo.setEnabled(checked)
        self.reg_hint.setEnabled(checked)
        if checked:
            self._refresh_register_files()

    def _try_accept(self):
        src = self.src_edit.text().strip()
        new_id = self.id_edit.text().strip()
        if not src:
            QMessageBox.warning(self, "克隆", "请填写模板 ID")
            return
        if not self.project.get_section(src):
            QMessageBox.warning(self, "克隆", f"模板 [{src}] 不存在于 rules/当前工程")
            return
        if not new_id or any(c.isspace() for c in new_id):
            QMessageBox.warning(self, "克隆", "请填写有效的新注册名（不能有空格）")
            return
        if new_id.lower() == src.lower():
            QMessageBox.warning(self, "克隆", "新 ID 不能与模板相同")
            return
        if self.project.get_section(new_id):
            QMessageBox.warning(self, "克隆", f"[{new_id}] 已存在于 rules，请换名")
            return
        if self.project.art and self.project.art.get_section(new_id) and self.copy_art.isChecked():
            QMessageBox.warning(self, "克隆", f"Art 中已有 [{new_id}]，请换名或取消克隆 Art")
            return
        if self.also_register.isChecked() and not self.reg_combo.currentData():
            QMessageBox.warning(self, "克隆", "已勾选写入注册表，但没有可选文件")
            return
        self.accept()

    def result_data(self) -> Optional[dict]:
        src = self.src_edit.text().strip()
        new_id = self.id_edit.text().strip()
        if not src or not new_id:
            return None
        reg = self.reg_combo.currentData() or "" if self.also_register.isChecked() else ""
        return {
            "src_id": src,
            "id": new_id,
            "type_list": self.type_combo.currentData(),
            "name": self.name_edit.text().strip(),
            "path": self.body_combo.currentData() or "",
            "also_register": self.also_register.isChecked() and bool(reg),
            "register_path": reg,
            "copy_art": self.copy_art.isChecked(),
            "rewrite_identity": self.rewrite_identity.isChecked(),
            "write_csf": bool(self.write_csf.isChecked()),
            "csf_text": self.csf_zh_edit.text().strip(),
        }


class _DepNodeItem(QGraphicsRectItem):
    """依赖图节点：双击打开对应节。"""

    KIND_COLORS = {
        "unit": ("#3b82f6", "#1e3a5f"),
        "weapon": ("#eab308", "#5c4d0e"),
        "warhead": ("#ef4444", "#5c1a1a"),
        "projectile": ("#22c55e", "#14532d"),
        "animation": ("#a855f7", "#3b0764"),
        "particle": ("#14b8a6", "#134e4a"),
        "particle_system": ("#14b8a6", "#134e4a"),
        "building": ("#f97316", "#7c2d12"),
        "art": ("#06b6d4", "#164e63"),
        "group": ("#94a3b8", "#1e293b"),
    }

    def __init__(self, node: dict, w: float = 188, h: float = 58):
        super().__init__(0, 0, w, h)
        self.node_id = node.get("id") or ""
        self.kind = node.get("kind") or "unit"
        self._exists = node.get("exists", True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        border, fill = self.KIND_COLORS.get(self.kind, ("#94a3b8", "#334155"))
        if not node.get("exists", True):
            border, fill = "#f59e0b", "#422006"
        self.setBrush(QBrush(QColor(fill)))
        self.setPen(QPen(QColor(border), 2.0))
        self.setToolTip(self._tip(node))

        # 分组节点：标题用中文角色，不用内部唯一 id
        if self.kind == "group":
            title = (node.get("role") or node.get("field") or self.node_id)
            if "·" in str(self.node_id) and not node.get("role"):
                title = self.node_id.split("·", 1)[0]
        else:
            title = self.node_id
        if len(title) > 18:
            title = title[:16] + "…"
        kind_zh = {
            "unit": "单位", "weapon": "武器", "warhead": "弹头",
            "projectile": "抛射体", "animation": "动画",
            "particle": "粒子", "particle_system": "粒子系统",
            "building": "建筑", "art": "Art", "group": "分组",
        }.get(self.kind, self.kind)
        role = (node.get("role") or "").strip()
        extra = (node.get("extra") or "").strip()
        # 拆出中文名与状态标记
        status = ""
        cname = extra
        for tag in ("（已展开过）", "（被引用方）", "（未展开）"):
            if tag in cname:
                status += tag
                cname = cname.replace(tag, "").strip(" ·")
        cname = cname.strip(" ·")
        if cname and len(cname) > 16:
            cname = cname[:14] + "…"
        # 第二行：中文名优先，再角色/类型（小白可读）
        parts = []
        if cname:
            parts.append(cname)
        if role:
            parts.append(role)
        elif self.kind == "group":
            pass
        else:
            parts.append(kind_zh)
        line2 = " · ".join(parts) if parts else kind_zh
        if status:
            line2 += " " + status
        if not node.get("exists", True):
            line2 += " ⚠不存在"

        t1 = QGraphicsSimpleTextItem(title, self)
        t1.setBrush(QBrush(QColor("#f8fafc")))
        f = t1.font()
        f.setBold(True)
        f.setPointSize(10)
        t1.setFont(f)
        t1.setPos(8, 6)

        t2 = QGraphicsSimpleTextItem(line2, self)
        t2.setBrush(QBrush(QColor("#cbd5e1")))
        f2 = t2.font()
        f2.setPointSize(9)
        t2.setFont(f2)
        t2.setPos(8, 26)

    def _tip(self, node: dict) -> str:
        status = "正常" if node.get("exists", True) else "问题：工程中无此对象（引用目标不存在）"
        lines = [f"[{node.get('id')}] ({node.get('kind')})"]
        if node.get("extra"):
            lines.append(str(node.get("extra")))
        lines.append(status)
        if node.get("exists", True):
            lines.append("双击打开")
        return "\n".join(lines)

    def set_highlight(self, on: bool):
        if on:
            self.setPen(QPen(QColor("#38bdf8"), 3.0))
            self.setZValue(5)
        else:
            border, fill = self.KIND_COLORS.get(self.kind, ("#94a3b8", "#334155"))
            if not getattr(self, "_exists", True):
                border = "#f59e0b"
            self.setPen(QPen(QColor(border), 2.0))
            self.setZValue(2)

    def mousePressEvent(self, event):
        sc = self.scene()
        if sc and hasattr(sc, "dep_select"):
            sc.dep_select(self.node_id)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        sc = self.scene()
        if sc and hasattr(sc, "dep_highlight"):
            sc.dep_highlight(self.node_id, transient=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        sc = self.scene()
        if sc and hasattr(sc, "dep_restore_selection_highlight"):
            sc.dep_restore_selection_highlight()
        super().hoverLeaveEvent(event)




class _DepEdgeItem(QGraphicsPathItem):
    def __init__(self, x1, y1, x2, y2, label: str = "", src_id: str = "", dst_id: str = ""):
        super().__init__()
        self.src_id = (src_id or "").lower()
        self.dst_id = (dst_id or "").lower()
        self._normal = QPen(QColor("#64748b"), 1.6)
        self._hi = QPen(QColor("#38bdf8"), 3.2)
        self._dim = QPen(QColor("#334155"), 1.0)
        path = QPainterPath()
        path.moveTo(x1, y1)
        # 上下布局：控制点在垂直中段，横向略弯
        cy = (y1 + y2) / 2
        path.cubicTo(x1, cy, x2, cy, x2, y2)
        self.setPath(path)
        self.setPen(self._normal)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        self._label_text = label or ""
        self._label_item = None
        # 连线不常驻写字（会糊成一团）；悬停高亮时再显示
        if label:
            self.setToolTip(label)
            mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2 - 12
            self._label_item = QGraphicsSimpleTextItem(label, self)
            self._label_item.setBrush(QBrush(QColor("#e0f2fe")))
            f = self._label_item.font()
            f.setPointSize(12)
            f.setBold(True)
            self._label_item.setFont(f)
            self._label_item.setPos(mid_x - len(label) * 4.5, mid_y - 4)
            self._label_item.setVisible(False)


    def set_highlight(self, mode: str):
        """mode: normal | hi | dim"""
        if mode == "hi":
            self.setPen(self._hi)
            self.setZValue(3)
            if self._label_item:
                self._label_item.setVisible(True)
                self._label_item.setBrush(QBrush(QColor("#e0f2fe")))
        elif mode == "dim":
            self.setPen(self._dim)
            self.setZValue(0)
            if self._label_item:
                self._label_item.setVisible(False)
        else:
            self.setPen(self._normal)
            self.setZValue(1)
            if self._label_item:
                self._label_item.setVisible(False)

    def hoverEnterEvent(self, event):
        sc = self.scene()
        if sc and hasattr(sc, "dep_highlight"):
            sc.dep_highlight(self.src_id, self.dst_id, transient=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        sc = self.scene()
        if sc and hasattr(sc, "dep_restore_selection_highlight"):
            sc.dep_restore_selection_highlight()
        super().hoverLeaveEvent(event)


class _DepGraphScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.node_items = {}  # id_lower -> _DepNodeItem
        self.edge_items = []
        self._selected_id: str = ""  # 点击选中后常亮

    def dep_select(self, node_id: str):
        """点击节点：固定高亮其相关连线，直到点其它节点或空白。"""
        self._selected_id = (node_id or "").lower()
        if self._selected_id:
            self.dep_highlight(self._selected_id, transient=False)
        else:
            self.dep_clear_highlight()

    def dep_highlight(self, *ids, transient: bool = False):
        """
        高亮 focus 相关边/节点。
        transient=True：悬停预览；离开后会回到选中态。
        """
        focus = {str(i).lower() for i in ids if i}
        if not focus and self._selected_id and not transient:
            focus = {self._selected_id}
        related = set(focus)
        for e in self.edge_items:
            if e.src_id in focus or e.dst_id in focus:
                related.add(e.src_id)
                related.add(e.dst_id)
        for e in self.edge_items:
            if e.src_id in related and e.dst_id in related and (
                e.src_id in focus or e.dst_id in focus
            ):
                e.set_highlight("hi")
            else:
                e.set_highlight("dim")
        for k, item in self.node_items.items():
            item.set_highlight(k in related)

    def dep_restore_selection_highlight(self):
        """悬停离开：若有选中则恢复常亮，否则全部恢复默认。"""
        if self._selected_id:
            self.dep_highlight(self._selected_id, transient=False)
        else:
            self.dep_clear_highlight()

    def dep_clear_highlight(self):
        self._selected_id = ""
        for e in self.edge_items:
            e.set_highlight("normal")
        for item in self.node_items.values():
            item.set_highlight(False)

    def mousePressEvent(self, event):
        # 点空白处取消常亮
        from PySide6.QtGui import QTransform
        item = self.itemAt(event.scenePos(), QTransform())
        # 点到线上的标签也算线，只有真空白才清
        if item is None:
            self.dep_clear_highlight()
        super().mousePressEvent(event)


class DependencyGraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#0f1218")))
        self._win = None
        self._scene = _DepGraphScene(self)
        self.setScene(self._scene)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        item = self.itemAt(pos)
        while item is not None and not isinstance(item, _DepNodeItem):
            item = item.parentItem()
        if isinstance(item, _DepNodeItem) and self._win and item.node_id:
            if getattr(item, "kind", "") == "group":
                return
            self._win.open_section_tab(item.node_id)
            w = self.window()
            if isinstance(w, QDialog):
                w.accept()
            return
        super().mouseDoubleClickEvent(event)

    def load_graph(self, root_id: str, nodes: list, edges: list, positions: dict):
        sc = self._scene
        sc.clear()
        sc.node_items = {}
        sc.edge_items = []
        nw, nh = 188.0, 58.0
        node_pos = {}
        for n in nodes:
            k = n["id"].lower()
            x, y = positions.get(k, (0, 0))
            node_pos[k] = (x, y)
        for e in edges:
            s, d = e["src"].lower(), e["dst"].lower()
            if s not in node_pos or d not in node_pos:
                continue
            x1, y1 = node_pos[s]
            x2, y2 = node_pos[d]
            fld = e.get("field") or ""
            try:
                from core.dependency_view import field_role_zh
                lab = field_role_zh(fld) or fld
            except Exception:
                lab = fld
            # 上下布局：父节点底边中点 → 子节点顶边中点
            edge = _DepEdgeItem(
                x1 + nw / 2, y1 + nh, x2 + nw / 2, y2,
                lab, src_id=s, dst_id=d,
            )
            sc.addItem(edge)
            sc.edge_items.append(edge)
        for n in nodes:
            k = n["id"].lower()
            x, y = node_pos.get(k, (0, 0))
            item = _DepNodeItem(n, nw, nh)
            item.setPos(x, y)
            sc.addItem(item)
            sc.node_items[k] = item
        sc.setSceneRect(sc.itemsBoundingRect().adjusted(-40, -40, 40, 40))
        self.fitInView(sc.sceneRect(), Qt.KeepAspectRatio)



class DependencyTreeDialog(QDialog):
    """C1：依赖关系图 — 上下布局、分组、过滤、简洁模式。"""

    def __init__(self, win: "MainWindow", root_id: str, tree: dict = None, lines: list = None):
        super().__init__(win)
        self.win = win
        self.root_id = root_id
        self.setWindowTitle(f"依赖关系图 · [{root_id}]")
        self.resize(1100, 720)
        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; }
            QCheckBox { color: #e8eaed; spacing: 6px; }
            QPlainTextEdit {
                background: #252830; color: #f1f3f5; border: 1px solid #3d4450;
                border-radius: 4px; font-size: 12px;
            }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background: #3d4450; }
        """)
        lay = QVBoxLayout(self)

        # 过滤条
        filt = QHBoxLayout()
        self.chk_concise = QCheckBox("简洁模式")
        self.chk_concise.setChecked(True)
        self.chk_concise.setToolTip("武器只到抛射体/弹头；爆炸动画只显示分组不展开每一项")
        self.chk_weapons = QCheckBox("武器")
        self.chk_weapons.setChecked(True)
        self.chk_prereq = QCheckBox("建造前提")
        self.chk_prereq.setChecked(True)
        self.chk_art = QCheckBox("Art/图像")
        self.chk_art.setChecked(True)
        self.chk_anims = QCheckBox("动画/粒子")
        self.chk_anims.setChecked(True)
        self.chk_expand_anims = QCheckBox("展开动画明细")
        self.chk_expand_anims.setChecked(False)
        self.chk_expand_anims.setToolTip("勾选后把「爆炸动画 N 项」拆成每个紫节点（可能很宽）")
        self.chk_spawns = QCheckBox("子机/生成")
        self.chk_spawns.setChecked(True)
        self.chk_reverse = QCheckBox("反向：谁引用了我")
        self.chk_reverse.setChecked(False)
        self.chk_reverse.setToolTip(
            "向上追查：哪些单位/武器的字段指向当前 ID（改共享弹头/武器前建议看）"
        )
        for c in (
            self.chk_concise, self.chk_weapons, self.chk_prereq, self.chk_art,
            self.chk_anims, self.chk_expand_anims, self.chk_spawns, self.chk_reverse,
        ):
            filt.addWidget(c)
            c.toggled.connect(self._rebuild)
        filt.addStretch(1)
        lay.addLayout(filt)

        lay.addWidget(QLabel(
            "正向=向下依赖 · 反向=谁在用我 · 悬停显关系 · 双击打开"
        ))

        self.view = DependencyGraphView()
        self.view._win = win
        lay.addWidget(self.view, 3)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumHeight(120)
        lay.addWidget(QLabel("文本大纲（可复制）"))
        lay.addWidget(self.text)

        row = QHBoxLayout()
        b_fit = QPushButton("适应窗口")
        b_fit.clicked.connect(self._fit)
        b_copy = QPushButton("复制文本")
        b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_fit)
        row.addWidget(b_copy)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addLayout(row)

        self._rebuild()

    def _options(self) -> dict:
        return dict(
            show_weapons=self.chk_weapons.isChecked(),
            show_prereq=self.chk_prereq.isChecked(),
            show_art=self.chk_art.isChecked(),
            show_anims=self.chk_anims.isChecked(),
            expand_anims=self.chk_expand_anims.isChecked(),
            show_spawns=self.chk_spawns.isChecked(),
            concise=self.chk_concise.isChecked(),
        )

    def _rebuild(self):
        from core.dependency_view import (
            build_dependency_tree, build_reverse_tree, build_reverse_index,
            tree_to_lines, collect_graph, layout_layers,
        )
        prefer_ini = None
        prefer = (getattr(self.win, "current_prefer", None) or "").strip().lower()
        if prefer == "art" and self.win.project.art:
            prefer_ini = self.win.project.art
        elif prefer == "ai" and self.win.project.ai:
            prefer_ini = self.win.project.ai
        try:
            if self.chk_reverse.isChecked():
                cache = getattr(self.win, "_dep_reverse_index", None)
                cache_key = id(prefer_ini or self.win.project.rules)
                if not cache or cache.get("key") != cache_key:
                    idx = build_reverse_index(self.win.project, prefer=prefer_ini)
                    self.win._dep_reverse_index = {"key": cache_key, "index": idx}
                else:
                    idx = cache["index"]
                tree = build_reverse_tree(
                    self.win.project, self.root_id, prefer=prefer_ini, index=idx
                )
            else:
                tree = build_dependency_tree(
                    self.win.project, self.root_id, prefer=prefer_ini, **self._options()
                )
            lines = tree_to_lines(tree)
            nodes, edges = collect_graph(tree)
            positions = layout_layers(nodes, edges, self.root_id)
        except Exception as e:
            self.text.setPlainText(f"分析失败: {e}")
            return
        self.view.load_graph(self.root_id, nodes, edges, positions)
        self.text.setPlainText("\n".join(lines))
        self._fit()

    def _fit(self):
        sc = self.view.scene()
        if not sc:
            return
        rect = sc.sceneRect()
        self.view.fitInView(rect, Qt.KeepAspectRatio)
        # 防止节点极少时被放得过大、极多时过小到无法点
        tr = self.view.transform()
        scale = tr.m11()
        if scale > 1.4:
            self.view.setTransform(tr.scale(1.4 / scale, 1.4 / scale))
        elif scale < 0.35:
            self.view.setTransform(tr.scale(0.35 / scale, 0.35 / scale))



class SessionChangesDialog(QDialog):
    """B2：本会话改过的 section 列表，可打开 / 导出。"""

    def __init__(self, win: "MainWindow", rows: list):
        super().__init__(win)
        self.win = win
        self.rows = list(rows or [])
        self.setWindowTitle("会话改动集")
        self.resize(720, 420)
        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; }
            QListWidget {
                background: #252830; color: #f1f3f5; border: 1px solid #3d4450;
                border-radius: 4px; font-size: 13px;
            }
            QListWidget::item { padding: 6px 8px; }
            QListWidget::item:selected { background: #3b82f6; }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background: #3d4450; }
        """)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            f"本会话共 {len(self.rows)} 项改动（含未保存草稿与新增/克隆）。"
            "导出仅生成节片段，不会改动工程文件。"
        ))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for r in self.rows:
            sid = r.get("section_id") or r.get("key")
            prefer = r.get("prefer") or "rules"
            kind = r.get("kind") or "edit"
            if r.get("is_new"):
                kind = r.get("kind") or "new"
            saved = "已保存" if r.get("saved") else "未保存"
            ts = r.get("last_at") or r.get("first_at") or ""
            label = f"[{sid}]  ·  {prefer}  ·  {kind}  ·  {saved}  ·  {ts}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, r.get("key"))
            self.list.addItem(item)
        self.list.itemDoubleClicked.connect(self._open_current)
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        b_open = QPushButton("打开选中")
        b_open.clicked.connect(self._open_current)
        b_exp_sel = QPushButton("导出选中…")
        b_exp_sel.clicked.connect(self._export_selected)
        b_exp_all = QPushButton("导出全部…")
        b_exp_all.clicked.connect(self._export_all)
        b_close = QPushButton("关闭")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_open)
        row.addWidget(b_exp_sel)
        row.addWidget(b_exp_all)
        row.addStretch(1)
        row.addWidget(b_close)
        lay.addLayout(row)

    def _selected_keys(self) -> list:
        keys = []
        for item in self.list.selectedItems():
            k = item.data(Qt.UserRole)
            if k:
                keys.append(k)
        return keys

    def _open_current(self):
        keys = self._selected_keys()
        if not keys:
            cur = self.list.currentItem()
            if cur:
                keys = [cur.data(Qt.UserRole)]
        if not keys:
            return
        key = keys[0]
        prefer = ""
        sid = key
        if isinstance(key, str) and key.startswith("art::"):
            sid, prefer = key[5:], "art"
        elif isinstance(key, str) and key.startswith("ai::"):
            sid, prefer = key[4:], "ai"
        self.win.open_section_tab(sid, prefer=prefer)
        self.accept()

    def _export_selected(self):
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, "导出", "请先选中要导出的项")
            return
        if self.win.export_session_changes(keys):
            self.accept()

    def _export_all(self):
        if self.win.export_session_changes(None):
            self.accept()


class SectionOriginsDialog(QDialog):
    """B3：同节多文件来源对照 — 查看各拆分文件中的原始片段与合并键来源。"""

    def __init__(self, parent, project: Project, section_id: str, prefer: str = ""):
        super().__init__(parent)
        self.project = project
        self.section_id = section_id
        self.setWindowTitle(f"多文件来源 · [{section_id}]")
        self.resize(900, 560)
        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; }
            QListWidget, QPlainTextEdit, QTableWidget {
                background: #252830; color: #f1f3f5; border: 1px solid #3d4450;
                border-radius: 4px; font-size: 13px;
            }
            QListWidget::item:selected { background: #3b82f6; }
            QHeaderView::section { background: #2f3542; color: #e8eaed; padding: 4px; }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 12px;
            }
            QPushButton:hover { background: #3d4450; }
        """)

        prefer_ini = None
        if prefer == "art" and project.art:
            prefer_ini = project.art
        elif prefer == "ai" and project.ai:
            prefer_ini = project.ai
        self.data = project.analyze_section_origins(section_id, prefer=prefer_ini)

        root = QVBoxLayout(self)
        n = len(self.data.get("files") or [])
        summary = QLabel(
            f"[{section_id}] 出现在 {n} 个文件中"
            + ("（后加载覆盖先加载，与 Ares 合并方向一致）" if n > 1 else "（仅单文件，无覆盖）")
        )
        summary.setWordWrap(True)
        root.addWidget(summary)

        split = QSplitter(Qt.Horizontal)

        # 左：文件列表
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("文件（加载顺序，上=先/底，下=后/覆盖）"))
        self.file_list = QListWidget()
        for fr in self.data.get("files") or []:
            item = QListWidgetItem(f"{fr['order']+1}. {fr['name']}  ({fr['key_count']} 键)")
            item.setData(Qt.UserRole, fr)
            self.file_list.addItem(item)
        self.file_list.currentRowChanged.connect(self._on_file_changed)
        ll.addWidget(self.file_list, 1)
        split.addWidget(left)

        # 中：该文件原始节
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("该文件中的原始 [节]（只读）"))
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        font = self.raw_view.font()
        font.setFamily("Consolas")
        font.setPointSize(11)
        self.raw_view.setFont(font)
        ml.addWidget(self.raw_view, 1)
        split.addWidget(mid)

        # 右：合并后键来源
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("合并后生效的键 → 来源文件"))
        from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.key_table = QTableWidget(0, 3)
        self.key_table.setHorizontalHeaderLabels(["键", "值", "来源"])
        self.key_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.key_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.key_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.key_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.key_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        keys = self.data.get("keys") or []
        self.key_table.setRowCount(len(keys))
        for i, row in enumerate(keys):
            self.key_table.setItem(i, 0, QTableWidgetItem(str(row.get("key", ""))))
            self.key_table.setItem(i, 1, QTableWidgetItem(str(row.get("value", ""))))
            self.key_table.setItem(i, 2, QTableWidgetItem(str(row.get("source_name") or "—")))
        rl.addWidget(self.key_table, 1)
        split.addWidget(right)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 3)
        root.addWidget(split, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        close_btn = bb.button(QDialogButtonBox.Close)
        if close_btn:
            close_btn.clicked.connect(self.accept)
        root.addWidget(bb)

        if self.file_list.count():
            self.file_list.setCurrentRow(0)

    def _on_file_changed(self, row: int):
        if row < 0:
            self.raw_view.setPlainText("")
            return
        item = self.file_list.item(row)
        fr = item.data(Qt.UserRole) or {}
        raw = fr.get("raw") or f"; 文件中无 [{self.section_id}]"
        self.raw_view.setPlainText(raw)


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

        # 光标行提示：默认隐藏，避免占一大块；需要时在首选项打开
        self.hint = QLabel("")
        self.hint.setObjectName("propHint")
        self.hint.setWordWrap(True)
        self.hint.hide()
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

    def set_hint_font_size(self, pt: int):
        pt = max(11, min(22, int(pt)))
        self.hint.setStyleSheet(
            "QLabel#propHint {"
            f"  color:#e2e8f0; font-size:{pt}px;"
            "  background:#1e293b; border:1px solid #334155; border-radius:4px;"
            "  padding:6px 8px;"
            "}"
        )

    def clear(self):
        while self.form.count():
            item = self.form.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.title.setText("")
        self.hint.hide()
        self.hint.clear()

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


class SectionDiffDialog(QDialog):
    """A3：当前节键级 Diff 列表。"""

    def __init__(self, parent, title: str, changes: list, summary: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 420)
        self.setStyleSheet("""
            QDialog { background: #1a1d24; color: #e8eaed; }
            QLabel { color: #e8eaed; font-size: 13px; }
            QListWidget {
                background: #252830; border: 1px solid #3d4450; border-radius: 4px;
                font-size: 13px; font-family: Consolas, "Courier New", monospace;
            }
            QListWidget::item { padding: 5px 8px; }
            QListWidget::item:selected { background: #3b82f6; }
            QPushButton {
                background: #2f3542; color: #f1f3f5; border: 1px solid #4b5563;
                border-radius: 4px; padding: 6px 14px;
            }
        """)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(summary if changes else "无键级差异（正文可能仅有空行/注释不同）"))
        lst = QListWidget()
        colors = {
            "added": QColor("#81c784"),
            "removed": QColor("#e57373"),
            "changed": QColor("#ffb74d"),
        }
        for c in changes:
            item = QListWidgetItem(c.label())
            item.setForeground(colors.get(c.kind, QColor("#e8eaed")))
            lst.addItem(item)
        if not changes:
            lst.addItem(QListWidgetItem("（无差异）"))
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


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
        # 新增/克隆：仅内存，点「保存」才落盘。key=section id 或 art::id
        self._pending_new: Dict[str, dict] = {}
        # A3：会话内「刚打开该节时」的正文基线（mem key -> text）
        self._section_baseline: Dict[str, str] = {}
        # 打开该节时的键集合（小写），增量删除主要靠它，不依赖正文是否被污染
        self._section_baseline_keys: Dict[str, set] = {}
        # 打开该节时的 += 值集合（小写）
        self._section_baseline_plus: Dict[str, set] = {}
        # B2：本会话改过的节（mem key -> meta）
        self._session_changes: Dict[str, dict] = {}
        # 多文件合并节：用户为「无来源新键」指定的写入文件 section_id -> path str
        self._merge_newkey_target: Dict[str, str] = {}
        self._dirty = False
        self._loading_section = False
        self._file_map: Dict[str, Path] = {}
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self.refresh_tree)
        self._live_lint_timer = QTimer(self)
        self._live_lint_timer.setSingleShot(True)
        self._live_lint_timer.timeout.connect(self._run_live_lint)
        # 过滤时单组最多直接铺开的子项数（超出仍可展开加载）
        self._tree_filter_fill_cap = 120
        # 无过滤时超过此数只放占位（原 40）
        self._tree_lazy_threshold = 40

        # 工具扩展点：name -> callable
        self.tool_registry: Dict[str, callable] = {}

        self._load_schema()
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._apply_style()
        self._apply_ui_prefs()
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
        m_edit.addSeparator()
        act_diff_disk = QAction("当前节 Diff（相对磁盘）…", self)
        act_diff_disk.setShortcut(QKeySequence("Ctrl+Shift+D"))
        act_diff_disk.triggered.connect(lambda: self.show_section_diff("disk"))
        m_edit.addAction(act_diff_disk)
        act_diff_open = QAction("当前节 Diff（相对打开时）…", self)
        act_diff_open.triggered.connect(lambda: self.show_section_diff("baseline"))
        m_edit.addAction(act_diff_open)
        act_origins = QAction("同节多文件来源…", self)
        act_origins.setShortcut(QKeySequence("Ctrl+Shift+U"))
        act_origins.setToolTip("查看当前节在各拆分文件中的原文与键来源（Ctrl+Shift+U）")
        act_origins.triggered.connect(self.show_section_origins)
        m_edit.addAction(act_origins)
        act_session = QAction("会话改动集…", self)
        act_session.setShortcut(QKeySequence("Ctrl+Shift+M"))
        act_session.triggered.connect(self.show_session_changes)
        m_edit.addAction(act_session)
        act_dep = QAction("依赖关系视图…", self)
        act_dep.setShortcut(QKeySequence("Ctrl+Shift+G"))
        act_dep.setToolTip("依赖关系图（Ctrl+Shift+G）；原 Ctrl+Shift+D 已用于 Diff")
        act_dep.triggered.connect(self.show_dependency_tree)
        m_edit.addAction(act_dep)
        m_edit.addSeparator()
        act_rep = QAction("替换…", self)
        act_rep.setShortcut(QKeySequence("Ctrl+H"))
        act_rep.triggered.connect(self.show_replace_dialog)
        m_edit.addAction(act_rep)
        m_edit.addSeparator()
        act_fold_c = QAction("折叠全部注释", self)
        act_fold_c.triggered.connect(self.fold_comment_blocks)
        m_edit.addAction(act_fold_c)
        act_expand_f = QAction("展开全部折叠", self)
        act_expand_f.triggered.connect(self.expand_all_folds)
        m_edit.addAction(act_expand_f)
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
        act_clone = QAction("克隆单位…", self)
        act_clone.setShortcut(QKeySequence("Ctrl+Shift+N"))
        act_clone.triggered.connect(self.on_clone_unit)
        m_edit.addAction(act_clone)
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
        self.act_prop_panel = QAction("属性说明面板", self)
        self.act_prop_panel.setCheckable(True)
        self.act_prop_panel.setChecked(True)
        self.act_prop_panel.setShortcut("Ctrl+Shift+P")
        self.act_prop_panel.triggered.connect(self._toggle_prop_panel)
        m_view.addAction(self.act_prop_panel)
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
            ("克隆", self.on_clone_unit),
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
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.ElideRight)
        # 标签多时出现左右滚动按钮，而不是挤成一条
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        top_mid.addWidget(self.tabs, 1)
        # 下拉快速跳转到已打开的节（打开很多时比来回点标签方便）
        self.tab_picker = QComboBox()
        self.tab_picker.setMinimumWidth(220)
        self.tab_picker.setMaximumWidth(360)
        self.tab_picker.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.tab_picker.setMinimumContentsLength(18)
        self.tab_picker.setToolTip("已打开的单位（含中文名）— 下拉切换")
        self.tab_picker.activated.connect(self._on_tab_picker_activated)
        top_mid.addWidget(self.tab_picker)
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
        self.source_label.setWordWrap(True)
        ml.addWidget(self.source_label)

        # 仅多文件合并节显示：无来源的新键写到哪个文件
        self.merge_target_row = QWidget()
        _mtr = QHBoxLayout(self.merge_target_row)
        _mtr.setContentsMargins(0, 0, 0, 0)
        _mtr.setSpacing(8)
        self.merge_target_hint = QLabel("无来源的新键写入：")
        self.merge_target_hint.setStyleSheet("color:#94a3b8; font-size:12px;")
        self.merge_target_combo = QComboBox()
        self.merge_target_combo.setMinimumWidth(280)
        self.merge_target_combo.setToolTip(
            "仅影响「还没有来源文件」的新键；已有键仍按各自来源拆回。\n"
            "单文件节不会显示此项。"
        )
        self.merge_target_combo.currentIndexChanged.connect(self._on_merge_target_changed)
        _mtr.addWidget(self.merge_target_hint)
        _mtr.addWidget(self.merge_target_combo, 1)
        ml.addWidget(self.merge_target_row)
        self.merge_target_row.hide()

        self.code = CodeEditor()
        self.code.setTabStopDistance(32)
        self.code.cursorPositionChanged.connect(self.on_code_cursor)
        self.code.textChanged.connect(self._on_code_edited)
        ml.addWidget(self.code, 1)

        # 未选节时的空状态（打开工程后引导）
        self.empty_hint = QLabel()
        self.empty_hint.setObjectName("emptyHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            "QLabel#emptyHint { color:#94a3b8; font-size:14px; padding:24px; "
            "background:#1a1d24; border:1px dashed #3d4450; border-radius:8px; }"
        )
        self.empty_hint.setText(
            "工程已加载。\n\n"
            "在左侧对象树中选择单位或注册表开始编辑。\n"
            "常用：全工程搜索 · 依赖关系 · 本会话改动 · 新增/克隆\n\n"
            "修改后标签会显示 ●，标题栏也会标记；Ctrl+S 保存当前。"
        )
        self.empty_hint.hide()
        ml.addWidget(self.empty_hint, 1)
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
        self._main_split = split
        self._prop_panel_sizes = None  # 隐藏前记住分割比例

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
                font-family: Consolas, "Cascadia Mono", "Courier New", monospace;
                selection-background-color: #5b4b8a;
                padding: 4px;
            }
            /* 字号由 CodeEditor.set_editor_font_size 控制，勿在此写死 font-size */
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
        dirty_mark = " ●" if getattr(self, "_dirty", False) else ""
        if d:
            self.setWindowTitle(f"{APP_TITLE}{dirty_mark}  —  {prof}  —  {mode}  —  {d}")
            self.dir_label.setText(f"  [{prof}]  {d}")
        elif self.project.single_path:
            self.setWindowTitle(f"{APP_TITLE}{dirty_mark}  —  {mode}")
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
            self._set_dirty(True)
            self._store_current_to_mem()
            self._touch_session_change()
            # 实时校验波浪线（防抖）
            if getattr(self, "_live_lint_timer", None):
                self._live_lint_timer.start(450)

    def _set_dirty(self, dirty: bool):
        """统一脏标记：当前标签加点、标题栏 *、状态栏提示。"""
        self._dirty = bool(dirty)
        try:
            i = self.tabs.currentIndex()
            if i >= 0:
                title = self.tabs.tabText(i)
                base = title[2:] if title.startswith("● ") else title
                # 去掉可能的旧 *
                if base.startswith("*"):
                    base = base[1:].lstrip()
                new_t = (f"● {base}" if dirty else base)
                if new_t != title:
                    self.tabs.setTabText(i, new_t)
                    self._sync_tab_picker()
        except Exception:
            pass
        try:
            self._update_chrome()
        except Exception:
            pass
        try:
            if dirty and self.current_section_id:
                self.statusBar().showMessage(
                    f"未保存：[{self.current_section_id}] — Ctrl+S 写回磁盘", 0
                )
            elif not dirty:
                # 不抢加载完成等其它状态栏信息时仅短提示
                cur = self.statusBar().currentMessage() or ""
                if cur.startswith("未保存"):
                    self.statusBar().clearMessage()
        except Exception:
            pass

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
        if getattr(self, "merge_target_row", None):
            self.merge_target_row.hide()
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

            def _prog(msg: str) -> None:
                self.statusBar().showMessage(msg)
                QApplication.processEvents()

            if not self.project.open_directory(path, progress=_prog):
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
        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("代码区字号"))
        spin_font = QSpinBox()
        spin_font.setRange(9, 28)
        try:
            spin_font.setValue(int(st.get("editor_font_size", 13)))
        except (TypeError, ValueError):
            spin_font.setValue(13)
        font_row.addWidget(spin_font)
        font_row.addWidget(QLabel("属性说明字号"))
        spin_prop = QSpinBox()
        spin_prop.setRange(11, 22)
        try:
            spin_prop.setValue(int(st.get("prop_hint_font_size", 14)))
        except (TypeError, ValueError):
            spin_prop.setValue(14)
        font_row.addWidget(spin_prop)
        font_row.addStretch(1)
        root.addLayout(font_row)
        chk_prop_panel = QCheckBox("显示右侧属性说明区（关闭后中间编辑区更宽；也可在「视图」菜单切换）")
        chk_prop_panel.setChecked(bool(st.get("show_prop_panel", True)))
        root.addWidget(chk_prop_panel)

        add_sep()
        add_sec("校验")
        chk_lint = QCheckBox("保存时自动校验（单节 / 保存全部）")
        chk_lint.setChecked(bool(st.get("auto_lint_on_save", True)))
        root.addWidget(chk_lint)
        chk_live = QCheckBox("编辑时在问题行显示波浪线（引用缺失、非法数值等）")
        chk_live.setChecked(bool(st.get("live_lint", True)))
        root.addWidget(chk_live)
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
        add_sec("保存写入方式")
        root.addWidget(QLabel(
            "全量：按键来源把该节在各文件中整段写回（更稳妥，默认）。\n"
            "增量：只写相对打开时有变化的键（适合单个单位/武器等小节）。\n"
            "InfantryTypes 等类型注册表始终全量（多文件+序号++=，增量易漏）。"
        ))
        from PySide6.QtWidgets import QComboBox as _QComboBox
        combo_write = _QComboBox()
        combo_write.addItem("全量写入（推荐）", "full")
        combo_write.addItem("增量写入（注册表仍全量）", "incremental")
        cur_mode = str(st.get("save_write_mode") or "full").lower()
        idx = combo_write.findData("incremental" if cur_mode in ("incremental", "delta", "patch") else "full")
        if idx >= 0:
            combo_write.setCurrentIndex(idx)
        root.addWidget(combo_write)

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
        st["live_lint"] = chk_live.isChecked()
        st["show_prop_panel"] = chk_prop_panel.isChecked()
        st["editor_font_size"] = int(spin_font.value())
        st["prop_hint_font_size"] = int(spin_prop.value())
        st["lint_skip_type_lists"] = [nm for nm, cb in skip_cbs if cb.isChecked()]
        st["backup_keep"] = int(spin_keep.value())
        st["save_write_mode"] = combo_write.currentData() or "full"
        hr["target_ini"] = edit_hotfix.text().strip() or "hotfix.ini"
        self.project.save_config()
        self._apply_ui_prefs()
        QMessageBox.information(self, "首选项", "已保存。")

    def reload_config(self):
        self.project.load_config()
        self._rebuild_profile_menu()
        QMessageBox.information(self, "配置", "已重新读取 config.json（未自动重载工程，可再开一次工程目录）")

    def _reset_editor_session_state(self):
        """打开工程/单文件时清空会话态，强制从磁盘重载，避免草稿/基线残留。"""
        self._mem_sections.clear()
        self._section_baseline.clear()
        self._section_baseline_keys.clear()
        self._section_baseline_plus.clear()
        self._session_changes.clear()
        self._pending_new.clear()
        self._merge_newkey_target.clear()
        self.current_section_id = None
        self.current_prefer = ""
        self.current_group = ""
        self._dirty = False
        if hasattr(self, "_dep_reverse_index"):
            self._dep_reverse_index = None
        try:
            self.code.blockSignals(True)
            self.code.setPlainText("")
            self.code.blockSignals(False)
        except Exception:
            pass
        if getattr(self, "merge_target_row", None):
            self.merge_target_row.hide()
        if getattr(self, "source_label", None):
            self.source_label.setText("")
        try:
            self.prop.clear()
        except Exception:
            pass

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

        def _prog(msg: str) -> None:
            self.statusBar().showMessage(msg)
            QApplication.processEvents()

        _prog("正在加载…")
        if not self.project.open_directory(path, progress=_prog):
            QMessageBox.critical(self, "错误", "未找到 rules 或配置中的 ini")
            self.statusBar().showMessage("加载失败")
            return
        st = self.project.config.setdefault("settings", {})
        st["last_project_dir"] = str(Path(path).resolve())
        try:
            self.project.save_config()
        except Exception:
            pass
        # 必须清会话：否则仍显示上一轮内存草稿，像「没真正重载」
        self._reset_editor_session_state()
        self._display_cache.clear()
        self._load_display_cache_file()
        self.tabs.clear()
        self._refresh_file_combo()
        self.act_merged.setChecked(True)
        self.file_row.hide()
        self.project.set_merged_mode()
        self._dirty = False
        self._update_chrome()
        _prog("建立对象树…")
        self.refresh_tree()
        self.statusBar().showMessage(
            f"{self.project.get_loaded_files_summary()}  |  CSF {len(self.project.csf.strings)} 条"
            f"  |  在左侧选择单位或注册表开始编辑"
        )
        self._show_editor_pane(False)
        # P0-3：默认不全量预热显示名（大工程会卡）；设置 warm_display_names_on_open=true 才开
        st_warm = self.project.config.get("settings") or {}
        if st_warm.get("warm_display_names_on_open", False):
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
        self._reset_editor_session_state()
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
        """显式重建显示名缓存（不依赖 warm_on_open 设置）。"""
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

    def _tree_id_matches(self, uid: str, filt: str) -> bool:
        """过滤匹配：优先 ID；显示名仅用已有缓存，避免过滤时全量 CSF 查询。"""
        if not filt:
            return True
        if filt in uid.lower():
            return True
        cached = self._display_cache.get(uid)
        if cached and filt in cached.lower():
            return True
        return False

    def _should_fill_children(self, count: int, filt: str) -> bool:
        """无过滤：≤阈值才直接填；有过滤：≤ filter_cap 才直接填。"""
        if filt:
            return count <= self._tree_filter_fill_cap
        return count <= self._tree_lazy_threshold

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
                items = [u for u in ids if self._tree_id_matches(u, filt)] if filt else list(ids)
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
                count = len(items)
                label += f" ({count})"
                info = (self.flag_schema.get("_type_lists") or {}).get(group_name) or {}
                desc = info.get("desc_zh") or ""
                if desc:
                    label += f"  ·  {(desc[:12] + '…') if len(desc) > 12 else desc}"

                if parent_for_groups is not None:
                    node = QTreeWidgetItem(parent_for_groups, [label])
                else:
                    node = QTreeWidgetItem(self.tree, [label])

                # 存完整匹配列表供懒加载；分组名用于同名 section 消歧
                node.setData(0, Qt.UserRole + 1, items)
                node.setData(0, Qt.UserRole + 3, group_name)
                if self._should_fill_children(count, filt):
                    self._fill_tree_children(node, items, group=group_name)
                    if filt:
                        node.setExpanded(True)
                else:
                    tip = "（展开以加载…）" if not filt else f"（展开以加载 {count} 项…）"
                    ph = QTreeWidgetItem(node, [tip])
                    ph.setData(0, Qt.UserRole, None)
                    if filt:
                        node.setExpanded(False)

            if self.project.work_mode == "merged" and self.project.art:
                art_root = QTreeWidgetItem(self.tree, ["Art"])
                art_root.setData(0, Qt.UserRole + 2, "art")
                art_ids = [s for s in self.project.art.section_order if not s.startswith("#")]
                if filt:
                    art_ids = [s for s in art_ids if self._tree_id_matches(s, filt)]
                art_root.setData(0, Qt.UserRole + 1, art_ids)
                art_root.setText(0, f"Art ({len(art_ids)})")
                if self._should_fill_children(len(art_ids), filt):
                    self._fill_tree_children(art_root, art_ids, prefer="art")
                    if filt and art_ids:
                        art_root.setExpanded(True)
                else:
                    tip = "（展开以加载…）" if not filt else f"（展开以加载 {len(art_ids)} 项…）"
                    ph = QTreeWidgetItem(art_root, [tip])
                    ph.setData(0, Qt.UserRole, None)

            # AI：配置里的 ai_files 已加载
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
                    items = [u for u in ids if self._tree_id_matches(u, filt)] if filt else list(ids)
                    if filt and not items:
                        continue
                    label = ai_type_labels.get(gname, gname)
                    count = len(items)
                    node = QTreeWidgetItem(ai_root, [f"{label} ({count})"])
                    node.setData(0, Qt.UserRole + 2, "ai")
                    node.setData(0, Qt.UserRole + 3, gname)
                    node.setData(0, Qt.UserRole + 1, items)
                    if self._should_fill_children(count, filt):
                        self._fill_tree_children(node, items, prefer="ai", group=gname)
                        if filt:
                            node.setExpanded(True)
                    else:
                        tip = "（展开以加载…）" if not filt else f"（展开以加载 {count} 项…）"
                        ph = QTreeWidgetItem(node, [tip])
                        ph.setData(0, Qt.UserRole, None)
                    any_child = True
                if not any_child and not filt:
                    # 兜底：平铺全部 AI section
                    ai_ids = [s for s in self.project.ai.section_order if not s.startswith("#")]
                    ai_root.setData(0, Qt.UserRole + 1, ai_ids)
                    if self._should_fill_children(len(ai_ids), ""):
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

    def _tab_title_base(self, title: str) -> str:
        """去掉脏标记 ● / * 后的标签标题。"""
        t = (title or "").strip()
        if t.startswith("● "):
            t = t[2:]
        if t.startswith("*"):
            t = t[1:].lstrip()
        return t

    def _show_editor_pane(self, show_code: bool):
        """有选中节时显示代码区；否则显示空状态引导。"""
        try:
            if show_code:
                self.code.show()
                self.source_label.show()
                if getattr(self, "empty_hint", None):
                    self.empty_hint.hide()
            else:
                self.code.hide()
                self.source_label.hide()
                if getattr(self, "merge_target_row", None):
                    self.merge_target_row.hide()
                if getattr(self, "empty_hint", None):
                    self.empty_hint.show()
        except Exception:
            pass

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
            title = self._tab_title_base(self.tabs.tabText(i))
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
        self._sync_tab_picker()
        self.show_section(section_id, prefer=prefer, group=group)

    def close_tab(self, index: int):
        title = self._tab_title_base(self.tabs.tabText(index))
        sid = title.split(" · ")[0] if " · " in title else title
        self.tabs.removeTab(index)
        self._sync_tab_picker()
        if self.tabs.count() == 0:
            self.current_section_id = None
            self._set_dirty(False)
            self._show_editor_pane(False)
        if self.current_section_id == sid:
            if self.tabs.count():
                self.on_tab_changed(self.tabs.currentIndex())
            else:
                self.current_section_id = None
                self.code.setPlainText("")
                self.prop.clear()
                self.source_label.setText("")
        if getattr(self, "merge_target_row", None):
            self.merge_target_row.hide()

    def on_tab_changed(self, index: int):
        self._store_current_to_mem()
        self._sync_tab_picker()
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

    def _sync_tab_picker(self):
        """同步「已打开」下拉与标签页（显示 ID + 中文名）。"""
        if not hasattr(self, "tab_picker"):
            return
        self.tab_picker.blockSignals(True)
        self.tab_picker.clear()
        cur = self.tabs.currentIndex()
        for i in range(self.tabs.count()):
            title = self._tab_title_base(self.tabs.tabText(i))
            # 标签可能是 "GACNST" 或 "GACNST · Art"
            sid = title.split(" · ")[0] if " · " in title else title
            try:
                disp = self._disp(sid)
            except Exception:
                disp = sid
            # _disp 可能已是 "ID  -  中文"
            if disp and disp != sid and not disp.startswith(sid):
                label = f"{sid}  -  {disp}"
            else:
                label = disp or sid
            if " · " in title:
                # 保留 Art/AI 后缀
                suffix = title.split(" · ", 1)[1]
                if suffix and suffix not in label:
                    label = f"{label} · {suffix}"
            self.tab_picker.addItem(label, i)
        if self.tabs.count():
            self.tab_picker.setCurrentIndex(max(0, cur))
            self.tab_picker.setEnabled(True)
        else:
            self.tab_picker.setEnabled(False)
        self.tab_picker.blockSignals(False)

    def _on_tab_picker_activated(self, index: int):
        if index < 0:
            return
        tab_i = self.tab_picker.itemData(index)
        if tab_i is None:
            tab_i = index
        try:
            tab_i = int(tab_i)
        except Exception:
            return
        if 0 <= tab_i < self.tabs.count():
            self.tabs.setCurrentIndex(tab_i)

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
        disk_body = self.project.get_section_text(section_id, prefer=prefer_ini)
        if key and key in self._mem_sections:
            body = self._mem_sections[key]
            from_mem = True
        else:
            body = disk_body
            from_mem = False
        # 增量基线：第一次打开时锁定正文 + 普通键 + += 值
        if key and key not in self._section_baseline:
            base = body if not from_mem else disk_body
            self._section_baseline[key] = base if base.endswith("\n") else base + "\n"
            keys_set = set()
            plus_set = set()
            try:
                for item in self.project._parse_section_kv_lines(section_id, base):
                    k0 = item[0]
                    if k0 in ("+", "+=", "++"):
                        if item[1]:
                            plus_set.add(str(item[1]).strip().lower())
                    else:
                        keys_set.add(str(k0).lower())
                origins = self.project._collect_key_origins(
                    section_id,
                    self.project.get_section(section_id, prefer=prefer_ini),
                    prefer_ini=prefer_ini,
                )
                keys_set |= set((origins[0] or {}).keys())
                plus_set |= set((origins[1] or {}).keys())
            except Exception:
                pass
            self._section_baseline_keys[key] = keys_set
            self._section_baseline_plus[key] = plus_set
        self._loading_section = True
        self.code.blockSignals(True)
        self.code.setPlainText(body if body.endswith("\n") else body + "\n")
        self.code.blockSignals(False)
        self._loading_section = False
        if hasattr(self.code, "update_line_number_area_width"):
            self.code.update_line_number_area_width(0)
        # 内存中有未保存稿则保持 dirty
        self._set_dirty(bool(from_mem and key and key in self._mem_sections))
        self._show_editor_pane(True)
        if getattr(self, "_live_lint_timer", None):
            self._live_lint_timer.start(200)

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

        multi_hint = ""
        multi_files = []
        try:
            origins = self.project.analyze_section_origins(
                section_id, prefer=prefer_ini or self.project.active_ini()
            )
            multi_files = origins.get("files") or []
            nfiles = len(multi_files)
            if nfiles > 1:
                names = []
                for fr in multi_files[:5]:
                    names.append(fr.get("name") or Path(fr.get("path") or "").name)
                more = f" 等{nfiles}个" if nfiles > 5 else ""
                multi_hint = (
                    f"  · 合并自 {nfiles} 个文件：{' / '.join(names)}{more}"
                    f"（已有键按来源拆回；Ctrl+Shift+U 查看明细）"
                )
            elif nfiles == 1:
                multi_hint = "  · 单文件"
        except Exception:
            pass

        # 下拉：仅多文件合并时显示
        self._fill_merge_target_combo(section_id, multi_files, src)

        if self.project.work_mode == "single":
            self.source_label.setText(f"当前文件：{src}")
        else:
            tag = "（Art）" if prefer == "art" else ("（AI）" if prefer == "ai" else "")
            if len(multi_files) > 1:
                names = []
                for fr in multi_files[:4]:
                    names.append(fr.get("name") or Path(fr.get("path") or "").name)
                more = f" 等 {len(multi_files)} 个" if len(multi_files) > 4 else ""
                default_name = Path(src).name if src else "（未定）"
                base = (
                    f"合并了 {len(multi_files)} 个文件{tag}：{' / '.join(names)}{more}\n"
                    f"已有条目保存时写回各自原来的文件；"
                    f"新加的条目写入下方所选文件（当前：{default_name}）。"
                    f"明细：Ctrl+Shift+U"
                )
            elif src:
                base = f"保存到{tag}：{src}"
            else:
                base = "尚未确定保存文件 — 保存时会请你选择"
            self.source_label.setText(base)
        self.prop.set_section(
            section_id, self._disp(section_id), sec, self.flag_schema,
            src_name=str(src) if src else "",
            on_jump_editor=self.jump_to_editor_key,
            on_jump_tree=self.jump_to_tree_value,
        )

    def on_code_cursor(self):
        """光标在「键=值」行时显示顶部说明；否则隐藏（不占位）。"""
        if not getattr(self, "prop", None) or not self.prop.isVisible():
            return
        cur = self.code.textCursor()
        cur.select(QTextCursor.LineUnderCursor)
        line = cur.selectedText().strip()
        if "=" in line and not line.startswith(";") and not line.startswith("["):
            key = line.split("=", 1)[0].strip()
            val = line.split("=", 1)[1].split(";")[0].strip() if "=" in line else ""
            desc = (self.flag_schema.get(key) or {}).get("desc_zh") or ""
            if not desc:
                desc = (self.flag_schema.get(key) or {}).get("desc_en") or ""
            lint_tip = ""
            try:
                lint_tip = (self.code._lint_tooltips or {}).get(self.code.textCursor().blockNumber()) or ""
            except Exception:
                pass
            if desc:
                text = f"{key} = {val}\n{desc}"
            else:
                text = f"{key} = {val}\n（暂无词典说明）"
            if lint_tip:
                text += f"\n⚠ {lint_tip}"
            self.prop.hint.setText(text)
            self.prop.hint.show()
        else:
            self.prop.hint.hide()
            self.prop.hint.clear()

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

    def _collect_current_lint_issues(self):
        """对当前编辑器正文跑校验，返回 LintIssue 列表（始终以代码区为准）。"""
        from core.linter import lint_section
        from core.save_util import normalize_section_body
        from core.ini_parser import INISection

        if not self.current_section_id:
            return []
        prefer = self.current_prefer or ""
        source = prefer if prefer in ("art", "ai") else "rules"
        body = (self.code.toPlainText() or "").strip()
        if not body:
            return []

        # 始终从编辑器解析，不依赖磁盘节是否存在
        tmp = INISection(self.current_section_id)
        norm = normalize_section_body(self.current_section_id, body)
        for line in norm.splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("["):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                tmp.set(k.strip(), v.strip().split(";")[0].strip())
        return lint_section(
            self.project, self.current_section_id, tmp, source=source
        ) or []

    def _run_live_lint(self):
        st = self.project.config.get("settings") or {}
        if not bool(st.get("live_lint", True)):
            try:
                self.code.clear_lint_marks()
            except Exception:
                pass
            return
        if not self.current_section_id or self._loading_section:
            return
        try:
            issues = self._collect_current_lint_issues()
            self.code.apply_lint_marks(issues)
            if issues:
                n_err = sum(1 for i in issues if getattr(i, "severity", "") == "error")
                n_warn = len(issues) - n_err
                parts = []
                if n_err:
                    parts.append(f"{n_err} 错误")
                if n_warn:
                    parts.append(f"{n_warn} 警告")
                self.statusBar().showMessage(
                    "校验：" + "、".join(parts) + "（问题行有底色+下划线，悬停查看）",
                    6000,
                )
            else:
                # 有脏编辑时清掉「校验：」残留
                msg = self.statusBar().currentMessage() or ""
                if msg.startswith("校验："):
                    self.statusBar().clearMessage()
        except Exception as e:
            try:
                self.statusBar().showMessage(f"实时校验异常: {e}", 8000)
            except Exception:
                pass

    def _set_prop_panel_visible(self, visible: bool):
        """显示/隐藏整个右侧属性说明区。"""
        if not getattr(self, "prop", None):
            return
        visible = bool(visible)
        split = getattr(self, "_main_split", None)
        if visible:
            self.prop.show()
            if split and self._prop_panel_sizes:
                try:
                    split.setSizes(self._prop_panel_sizes)
                except Exception:
                    pass
        else:
            if split:
                try:
                    self._prop_panel_sizes = split.sizes()
                except Exception:
                    pass
            self.prop.hide()
        if getattr(self, "act_prop_panel", None):
            self.act_prop_panel.blockSignals(True)
            self.act_prop_panel.setChecked(visible)
            self.act_prop_panel.blockSignals(False)
        st = self.project.config.setdefault("settings", {})
        st["show_prop_panel"] = visible
        try:
            self.project.save_config()
        except Exception:
            pass

    def _toggle_prop_panel(self, checked: bool = None):
        if checked is None:
            checked = not self.prop.isVisible()
        self._set_prop_panel_visible(bool(checked))

    def _apply_ui_prefs(self):
        st = self.project.config.get("settings") or {}
        try:
            self.code.set_editor_font_size(int(st.get("editor_font_size", 13)))
        except Exception:
            pass
        try:
            self.prop.set_hint_font_size(int(st.get("prop_hint_font_size", 14)))
        except Exception:
            pass
        try:
            # 不重复写 config：只同步可见性与菜单勾选
            vis = bool(st.get("show_prop_panel", True))
            if getattr(self, "prop", None):
                if vis:
                    self.prop.show()
                else:
                    self.prop.hide()
            if getattr(self, "act_prop_panel", None):
                self.act_prop_panel.blockSignals(True)
                self.act_prop_panel.setChecked(vis)
                self.act_prop_panel.blockSignals(False)
        except Exception:
            pass

    def lint_current_section(self):
        if not self.current_section_id:
            QMessageBox.information(self, "校验", "请先选择一个 section")
            return
        issues = self._collect_current_lint_issues()
        try:
            self.code.apply_lint_marks(issues)
        except Exception:
            pass
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

    def fold_comment_blocks(self):
        if not hasattr(self.code, "fold_all_comments"):
            return
        n = self.code.fold_all_comments()
        if n:
            self.statusBar().showMessage(
                f"已临时隐藏 {n} 行注释（仅便于阅读；展开后恢复原文，折叠期间请勿当正式编辑）", 6000
            )
        else:
            self.statusBar().showMessage("当前节没有以 ; 开头的注释行", 4000)

    def expand_all_folds(self):
        if not hasattr(self.code, "expand_all_folds"):
            return
        n = self.code.expand_all_folds()
        if n:
            self.statusBar().showMessage(f"已展开/恢复（处理 {n} 处）", 4000)
        else:
            self.statusBar().showMessage("当前没有折叠中的内容", 3000)


    def _touch_session_change(self, mem_key: str = None, *, is_new: bool = False, kind: str = "edit"):
        """B2：记录本会话对该节的改动。"""
        from datetime import datetime
        key = mem_key or self._mem_key()
        if not key:
            return
        sid = self.current_section_id or ""
        prefer = (self.current_prefer or "").strip().lower()
        if str(key).startswith("art::"):
            sid, prefer = key[5:], "art"
        elif str(key).startswith("ai::"):
            sid, prefer = key[4:], "ai"
        elif not sid:
            sid = key
        now = datetime.now().strftime("%H:%M:%S")
        rec = self._session_changes.get(key) or {
            "key": key,
            "section_id": sid,
            "prefer": prefer,
            "first_at": now,
            "saved": False,
            "kind": kind,
        }
        rec["last_at"] = now
        rec["section_id"] = sid or rec.get("section_id")
        rec["prefer"] = prefer if prefer is not None else (rec.get("prefer") or "")
        if is_new:
            rec["kind"] = kind if kind != "edit" else "new"
            rec["is_new"] = True
        if key in (self._mem_sections or {}):
            rec["has_draft"] = True
        self._session_changes[key] = rec

    def _mark_session_saved(self, mem_key: str = None):
        key = mem_key or self._mem_key()
        if not key:
            return
        rec = self._session_changes.get(key)
        if not rec:
            self._touch_session_change(key)
            rec = self._session_changes.get(key)
        if rec:
            from datetime import datetime
            rec["saved"] = True
            rec["saved_at"] = datetime.now().strftime("%H:%M:%S")
            rec["has_draft"] = key in (self._mem_sections or {})

    def _session_change_rows(self) -> list:
        rows = []
        seen = set()
        for key, rec in (self._session_changes or {}).items():
            rows.append(dict(rec))
            seen.add(key)
        for key, body in (self._mem_sections or {}).items():
            if key in seen:
                continue
            sid, prefer = key, ""
            if str(key).startswith("art::"):
                sid, prefer = key[5:], "art"
            elif str(key).startswith("ai::"):
                sid, prefer = key[4:], "ai"
            rows.append({
                "key": key,
                "section_id": sid,
                "prefer": prefer,
                "first_at": "—",
                "last_at": "—",
                "saved": False,
                "kind": "draft",
                "has_draft": True,
            })
        for sid, pend in (self._pending_new or {}).items():
            key = sid
            if key in seen:
                for r in rows:
                    if r["key"] == key:
                        r["kind"] = pend.get("kind") or "new"
                        r["is_new"] = True
                continue
            rows.append({
                "key": key,
                "section_id": sid,
                "prefer": "",
                "first_at": "—",
                "last_at": "—",
                "saved": False,
                "kind": pend.get("kind") or "new",
                "is_new": True,
                "has_draft": key in (self._mem_sections or {}),
            })
        rows.sort(key=lambda r: (str(r.get("last_at") or ""), str(r.get("section_id") or "")))
        return rows

    def show_dependency_tree(self):
        """C1：当前节依赖关系图。"""
        sid = self.current_section_id
        if not sid:
            QMessageBox.information(self, "依赖关系", "请先选择一个 section")
            return
        dlg = DependencyTreeDialog(self, sid)
        dlg.exec()

    def show_session_changes(self):

        """B2：本会话改动集 — 列表 / 打开 / 导出变更片段。"""
        self._store_current_to_mem()
        rows = self._session_change_rows()
        dlg = SessionChangesDialog(self, rows)
        dlg.exec()

    def export_session_changes(self, keys: list = None) -> bool:
        """导出选中（或全部）会话改动为目录：每节一个片段 + manifest。"""
        self._store_current_to_mem()
        rows = self._session_change_rows()
        if keys is not None:
            keyset = set(keys)
            rows = [r for r in rows if r.get("key") in keyset]
        if not rows:
            QMessageBox.information(self, "导出改动集", "没有可导出的改动")
            return False
        from datetime import datetime
        default_name = "changeset_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.project.project_dir or Path.home()
        out_dir = QFileDialog.getExistingDirectory(
            self, "选择导出目录（将在其下创建改动集文件夹）", str(base)
        )
        if not out_dir:
            return False
        dest = Path(out_dir) / default_name
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return False

        manifest = [
            "# AutoReloader session changeset",
            f"# time: {datetime.now().isoformat(timespec='seconds')}",
            f"# project: {self.project.project_dir or ''}",
            f"# count: {len(rows)}",
            "",
        ]
        written = 0
        for r in rows:
            key = r.get("key") or ""
            sid = r.get("section_id") or key
            prefer = (r.get("prefer") or "").strip().lower()
            body = (self._mem_sections or {}).get(key)
            if body is None and sid == self.current_section_id:
                cur_pref = (self.current_prefer or "").strip().lower()
                if cur_pref == prefer or (not prefer and not cur_pref):
                    body = self.code.toPlainText()
            if body is None:
                prefer_ini = None
                if prefer == "art":
                    prefer_ini = self.project.art
                elif prefer == "ai":
                    prefer_ini = self.project.ai
                body = self.project.get_section_text(sid, prefer=prefer_ini)
            if not body:
                continue
            from core.save_util import normalize_section_body
            try:
                body = normalize_section_body(sid, body)
            except Exception:
                pass
            tag = prefer or "rules"
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(sid))[:80]
            fname = f"{safe}__{tag}.ini"
            fpath = dest / fname
            n = 1
            while fpath.exists():
                fpath = dest / f"{safe}__{tag}_{n}.ini"
                n += 1
            try:
                fpath.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
            except Exception as e:
                manifest.append(f"# FAIL {sid}: {e}")
                continue
            written += 1
            status = "saved" if r.get("saved") else "unsaved"
            kind = r.get("kind") or "edit"
            manifest.append(
                f"{fname}\t[{sid}]\t{tag}\t{kind}\t{status}\t{r.get('last_at') or ''}"
            )

        (dest / "manifest.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        QMessageBox.information(
            self, "导出完成",
            f"已导出 {written} 个节片段到:\n{dest}\n\n见 manifest.txt 索引。",
        )
        self.statusBar().showMessage(f"改动集已导出 → {dest}", 8000)
        return True

    def show_section_origins(self):
        """B3：查看当前节在各拆分文件中的原始内容与键来源。"""
        sid = self.current_section_id
        if not sid:
            QMessageBox.information(self, "多文件来源", "请先选择一个 section")
            return
        prefer = (self.current_prefer or "").strip().lower()
        dlg = SectionOriginsDialog(self, self.project, sid, prefer=prefer)
        dlg.exec()

    def show_section_diff(self, mode: str = "disk"):

        """A3：当前编辑器正文 vs 磁盘 / vs 打开时基线。"""
        from core.section_diff import diff_kv, summarize_changes

        sid = self.current_section_id
        if not sid:
            QMessageBox.information(self, "Diff", "请先选择一个 section")
            return
        prefer = self.current_prefer or ""
        prefer_ini = None
        if prefer == "art" and self.project.art:
            prefer_ini = self.project.art
        elif prefer == "ai" and self.project.ai:
            prefer_ini = self.project.ai
        current = self.code.toPlainText()
        key = self._mem_key(sid, prefer)
        if mode == "baseline":
            base = self._section_baseline.get(key or "", "")
            title = f"Diff · [{sid}] 相对打开时"
            if not base:
                QMessageBox.information(self, "Diff", "尚无打开时基线（重新点选该节后即可）")
                return
        else:
            base = self.project.get_section_text(sid, prefer=prefer_ini)
            title = f"Diff · [{sid}] 相对磁盘"
        changes = diff_kv(base, current)
        dlg = SectionDiffDialog(self, title, changes, summarize_changes(changes))
        dlg.exec()

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
        """精简确认文案：默认只列将写入的文件；跳过的收成一行。"""
        files = plan.get("files") or []
        mode = plan.get("write_mode") or "full"
        mode_zh = "增量" if mode == "incremental" else "全量"
        writes = []
        skips = []
        for item in files:
            p = item.get("path") or ""
            n = int(item.get("count") or 0)
            name = Path(p).name if p else "?"
            if item.get("skip") or (n == 0 and not item.get("deletes") and not item.get("incremental")):
                skips.append(name)
            else:
                n_del = len(item.get("deletes") or [])
                if n_del and n:
                    writes.append(f"  • {name}  — 写入约 {n} 项（含删除 {n_del}）")
                elif n_del:
                    writes.append(f"  • {name}  — 删除 {n_del} 项")
                else:
                    writes.append(f"  • {name}  — 约 {n} 项")
                if p:
                    writes.append(f"      {p}")
        lines = [
            f"写入方式：{mode_zh}（按各条原来所在文件写回，确定后才落盘）",
            "",
        ]
        if writes:
            lines.append("将写入：")
            lines.extend(writes)
        else:
            lines.append("没有需要写入的文件。")
        if skips:
            lines.append("")
            lines.append("未改动而跳过：%s" % "、".join(skips[:8]) + ("…" if len(skips) > 8 else ""))
        lines.append("")
        lines.append("是否继续？")
        return chr(10).join(lines)

    def _confirm_danger(self, title: str, text: str, detail: str = "") -> bool:
        """统一危险操作确认：默认「否」。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        if detail:
            box.setInformativeText(detail)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec() == QMessageBox.Yes

    def _confirm_save_plan(self, plan: dict, title: str = "确认保存") -> bool:
        return self._confirm_danger(title, self._format_save_plan(plan))

    def _guard_save_body(self) -> str | None:
        """
        取可安全写盘的正文。
        注释折叠阅读模式下禁止保存，避免把去掉注释的文本写回工程。
        """
        if getattr(self.code, "_comments_collapsed", False):
            QMessageBox.warning(
                self,
                "无法保存",
                "当前处于「折叠注释」阅读模式。\n\n"
                "请先：编辑 → 展开全部折叠，再保存。\n"
                "否则可能把注释从工程文件里抹掉。",
            )
            return None
        return self.code.toPlainText()

    def _fill_merge_target_combo(self, section_id: str, multi_files: list, default_src):
        """多文件合并节：填充「无来源新键写入」下拉；单文件则隐藏。"""
        combo = getattr(self, "merge_target_combo", None)
        row = getattr(self, "merge_target_row", None)
        if combo is None or row is None:
            return
        combo.blockSignals(True)
        combo.clear()
        if len(multi_files or []) <= 1 or self.project.work_mode == "single":
            row.hide()
            combo.blockSignals(False)
            return
        paths = []
        for fr in multi_files:
            p = fr.get("path") or ""
            if not p:
                continue
            try:
                rp = str(Path(p).resolve())
            except Exception:
                rp = str(p)
            if rp not in paths:
                paths.append(rp)
            name = fr.get("name") or Path(p).name
            combo.addItem(name, rp)
        # 若默认 src 不在列表里也加上
        if default_src:
            try:
                ds = str(Path(default_src).resolve())
            except Exception:
                ds = str(default_src)
            if ds not in paths and Path(ds).is_file():
                combo.addItem(Path(ds).name + "（默认）", ds)
                paths.append(ds)
        # 恢复用户上次选择
        remembered = self._merge_newkey_target.get(section_id.lower())
        pick = remembered
        if not pick and default_src:
            try:
                pick = str(Path(default_src).resolve())
            except Exception:
                pick = str(default_src)
        if pick:
            for i in range(combo.count()):
                if (combo.itemData(i) or "") == pick:
                    combo.setCurrentIndex(i)
                    break
        row.show()
        combo.blockSignals(False)
        # 同步当前选择到记忆
        cur = combo.currentData()
        if cur and section_id:
            self._merge_newkey_target[section_id.lower()] = str(cur)

    def _on_merge_target_changed(self, _idx: int = 0):
        sid = self.current_section_id
        if not sid:
            return
        cur = self.merge_target_combo.currentData()
        if cur:
            self._merge_newkey_target[sid.lower()] = str(cur)

    def _merge_newkey_path(self, section_id: str) -> Path | None:
        """多文件节上用户为无来源新键指定的文件。"""
        if not section_id:
            return None
        row = getattr(self, "merge_target_row", None)
        if row is None or not row.isVisible():
            # 仍可用记忆
            p = self._merge_newkey_target.get(section_id.lower())
            return Path(p) if p else None
        cur = self.merge_target_combo.currentData()
        if cur:
            return Path(str(cur))
        p = self._merge_newkey_target.get(section_id.lower())
        return Path(p) if p else None

    def _resolve_save_path(self, section_id: str, prefer: str = "") -> Path | None:
        """按当前标签（rules/art/ai）解析写入路径（已有节主来源；新键下拉另传 new_key_default）。"""
        prefer = (prefer or "").strip().lower()
        path = None
        if prefer == "art" and self.project.art:
            sec = self.project.art.get_section(section_id)
            if sec and sec.source_file:
                path = self.project._resolve_name(sec.source_file)
            if path is None:
                path = self.project.get_source_path_for_section(section_id, prefer="art")
        elif prefer == "ai" and self.project.ai:
            sec = self.project.ai.get_section(section_id)
            if sec and sec.source_file:
                path = self.project._resolve_name(sec.source_file)
            if path is None:
                path = self.project.get_source_path_for_section(section_id, prefer="ai")
        else:
            path = self.project.get_source_path_for_section(section_id, prefer="")
        return Path(path) if path else None

    def _save_section_with_confirm(
        self,
        section_id: str,
        body: str,
        path: Path,
        is_new: bool = False,
        peers=None,
        prefer: str = "",
    ) -> dict:
        """先出计划确认，再 confirmed 写盘。"""
        peers = peers or []
        if not self.project.project_dir and self.project.work_mode != "single":
            # 无工程：仍走旧单文件
            backup_root = Path(path).parent / "backups"
            return self._save_with_backup_root(section_id, body, path, is_new, peers, backup_root)

        st = self.project.config.get("settings") or {}
        write_mode = str(st.get("save_write_mode") or "full")
        baseline = None
        baseline_keys = None
        baseline_plus = None
        if write_mode.lower() in ("incremental", "delta", "patch"):
            k = self._mem_key(section_id)
            baseline = self._section_baseline.get(k) if k else None
            baseline_keys = self._section_baseline_keys.get(k) if k else None
            baseline_plus = self._section_baseline_plus.get(k) if k else None
        new_key_default = self._merge_newkey_path(section_id)
        plan = self.project.plan_section_write(
            section_id,
            body,
            target_path=Path(path),
            is_new=is_new,
            prefer=prefer or None,
            write_mode=write_mode,
            baseline_text=baseline,
            new_key_default=new_key_default,
            baseline_keys=baseline_keys,
            baseline_plus=baseline_plus,
        )
        if not plan.get("ok"):
            return plan
        writable = [
            f for f in (plan.get("files") or [])
            if not f.get("skip") and (
                int(f.get("count") or 0) > 0
                or f.get("deletes")
                or f.get("incremental")
            )
        ]
        if not writable and not is_new:
            # 诊断：帮助确认是「真没改」还是「+=/基线」问题
            try:
                cur_p = self.project._parse_section_kv_lines(section_id, body)
                ck = sum(1 for it in cur_p if it[0] not in ("+", "+=", "++"))
                cp = sum(1 for it in cur_p if it[0] in ("+", "+=", "++"))
            except Exception:
                ck = cp = -1
            bk = len(baseline_keys or [])
            bp = len(baseline_plus or [])
            mode_zh = "增量" if write_mode.lower() in ("incremental", "delta", "patch") else "全量"
            QMessageBox.information(
                self,
                "无需保存",
                f"没有检测到需要写入的变更（模式：{mode_zh}）。\n\n"
                f"打开时：普通键 {bk} 个，+= {bp} 条\n"
                f"当前：普通键 {ck} 个，+= {cp} 条\n\n"
                "说明：若你先加了 += 又删掉且从未成功保存，相对打开时确实无净变更。\n"
                "改已有「键=值」或保留新的 += 后再保存。",
            )
            return {"ok": False, "cancelled": True, "message": "无需写入"}
        if not self._confirm_save_plan(plan, title="确认保存 [%s]" % section_id):
            return {"ok": False, "cancelled": True, "message": "已取消保存"}
        return self.project.save_section_text(
            section_id,
            body,
            target_path=Path(path),
            is_new=is_new,
            peer_ids=peers,
            confirmed=True,
            prefer=prefer or None,
            write_mode=write_mode,
            baseline_text=baseline,
            new_key_default=new_key_default,
            baseline_keys=baseline_keys,
            baseline_plus=baseline_plus,
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
        if getattr(self.code, "_comments_collapsed", False):
            QMessageBox.warning(
                self, "无法保存全部",
                "当前编辑区处于「折叠注释」阅读模式。\n请先展开全部折叠后再保存全部。",
            )
            return
        for key in sorted(keys):
            if key.startswith("art::"):
                sid, prefer = key[5:], "art"
            elif key.startswith("ai::"):
                sid, prefer = key[4:], "ai"
            else:
                sid, prefer = key, ""
            body = self._mem_sections.get(key)
            if body is None and sid == old_sid and prefer == (old_prefer or ""):
                body = old_code
            if not body:
                continue
            # 切到该 section 的上下文写盘
            self.current_section_id = sid
            self.current_prefer = prefer
            path = self._resolve_save_path(sid, prefer=prefer)
            if path is None or not Path(path).is_file():
                fail.append(f"{sid} ({prefer or 'rules'}): 无来源文件")
                continue
            peers = self._peers_for(sid)
            result = self._save_section_with_confirm(
                sid, body, Path(path), is_new=False, peers=peers, prefer=prefer
            )
            if result.get("ok"):
                ok_n += 1
                self._mem_sections[key] = body
                self._mark_session_saved(key)
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
        prefer = (self.current_prefer or "").strip().lower()
        body = self._guard_save_body()
        if body is None:
            return
        if not self._lint_before_save(section_id):
            return

        pending = (self._pending_new or {}).get(section_id) if prefer not in ("art", "ai") else None
        is_new = bool(pending and pending.get("is_new"))

        if pending and pending.get("path") and prefer not in ("art", "ai"):
            path = Path(pending["path"])
        else:
            path = self._resolve_save_path(section_id, prefer=prefer)

        if path is None or (not Path(path).is_file() and not is_new):
            path_str, _ = QFileDialog.getOpenFileName(
                self, "选择要写入的 INI 文件",
                str(self.project.project_dir or Path.home()),
                "INI (*.ini);;All (*.*)",
            )
            if not path_str:
                return
            path = Path(path_str)
            is_new = True

        path = Path(path)
        # 文件在、节不在 → 按新增追加，避免“未找到原块又乱插”
        if not is_new and path.is_file():
            from core.save_util import read_text, find_section_span
            try:
                text, _ = read_text(path)
                if find_section_span(text, section_id) is None:
                    is_new = True
            except Exception:
                pass

        peers = self._peers_for(section_id)
        result = self._save_section_with_confirm(
            section_id, body, path, is_new=is_new, peers=peers, prefer=prefer
        )
        if result.get("ok"):
            extra_msgs = []
            if pending and prefer not in ("art", "ai"):
                if pending.get("also_register") and pending.get("register_path"):
                    reg = self._append_to_type_list(
                        Path(pending["register_path"]),
                        pending.get("type_list") or "VehicleTypes",
                        section_id,
                    )
                    extra_msgs.append("注册表: " + (reg.get("message") or ""))
                    if not reg.get("ok"):
                        QMessageBox.warning(self, "注册表写入失败", reg.get("message", ""))
                if pending.get("write_csf"):
                    zh = (pending.get("csf_text") or "").strip()
                    if not zh:
                        extra_msgs.append("CSF: 已勾选但未填「CSF 中文名」，已跳过")
                    else:
                        csf_res = self._write_csf_uiname(section_id, zh)
                        extra_msgs.append("CSF: " + (csf_res.get("message") or ""))
                        if not csf_res.get("ok"):
                            QMessageBox.warning(self, "CSF 写入失败", csf_res.get("message", ""))
                art_body = pending.get("art_body")
                art_path = pending.get("art_path")
                if art_body and art_path:
                    from core.save_util import save_section_to_file
                    backup_root = (
                        (self.project.project_dir / "backups")
                        if self.project.project_dir
                        else (Path(art_path).parent / "backups")
                    )
                    ar = save_section_to_file(
                        Path(art_path), section_id, art_body,
                        backup_root=backup_root, is_new=True, peer_section_names=[],
                    )
                    if ar.get("ok"):
                        extra_msgs.append(f"Art: {art_path}")
                    else:
                        extra_msgs.append("Art 失败: " + (ar.get("message") or ""))
                self._pending_new.pop(section_id, None)

            self._set_dirty(False)
            k = self._mem_key(section_id)
            if k:
                self._mem_sections[k] = body
                nb = body if body.endswith("\n") else body + "\n"
                self._section_baseline[k] = nb
                try:
                    ks = set()
                    ps = set()
                    for item in self.project._parse_section_kv_lines(section_id, nb):
                        if item[0] in ("+", "+=", "++"):
                            if item[1]:
                                ps.add(str(item[1]).strip().lower())
                        else:
                            ks.add(str(item[0]).lower())
                    self._section_baseline_keys[k] = ks
                    self._section_baseline_plus[k] = ps
                except Exception:
                    pass
                self._mark_session_saved(k)
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
            if extra_msgs:
                summary = summary + "\n" + "\n".join(extra_msgs)
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
        """新增：只写入内存与对象树，不落盘；用户点保存才写文件。"""
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
                self, "选择计划写入的 INI（仍不会立即写盘）",
                str(self.project.project_dir or Path.home()), "INI (*.ini)",
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

        self.project.inject_section_memory(
            sid, body, source_path=path,
            type_list=type_list if data.get("also_register") else None,
        )
        self._mem_sections[sid] = body
        self._pending_new[sid] = {
            "id": sid,
            "path": str(path),
            "type_list": type_list,
            "also_register": bool(data.get("also_register")),
            "register_path": data.get("register_path") or "",
            "is_new": True,
            "kind": "new",
            "write_csf": bool(data.get("write_csf")),
            "csf_text": (data.get("csf_text") or "").strip(),
        }
        self._touch_session_change(sid, is_new=True, kind="new")
        self._dirty = True
        self.project.invalidate_classify_cache()
        self._display_cache.clear()
        self.refresh_tree()
        self.open_section_tab(sid)
        QMessageBox.information(
            self, "已加入编辑器（未写盘）",
            f"[{sid}] 已在内存中创建。\n"
            f"计划写入: {path}\n"
            f"注册表: {'是 → ' + (data.get('register_path') or '') if data.get('also_register') else '否'}\n\n"
            f"请检查后点「保存当前」才会写入文件并备份。",
        )

    def _rewrite_clone_body(self, src_id: str, new_id: str, body: str, *, name: str = "", rewrite_identity: bool = True) -> str:
        """把模板节改成新 ID；可选改写 Image/UIName/Name 中的模板名。"""
        from core.save_util import normalize_section_body
        text = normalize_section_body(src_id, body)
        lines = []
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("[") and s.endswith("]"):
                lines.append(f"[{new_id}]")
                continue
            if name and s.lower().startswith("name="):
                lines.append(f"Name={name}")
                continue
            if rewrite_identity and "=" in s and not s.startswith(";"):
                k, _, v = s.partition("=")
                kl = k.strip().lower()
                val = v.strip()
                if kl in ("image", "uiname", "name") and src_id.lower() in val.lower():
                    # 简单替换 ID 片段（大小写不敏感）
                    import re as _re
                    val2 = _re.sub(_re.escape(src_id), new_id, val, flags=_re.IGNORECASE)
                    lines.append(f"{k.strip()}={val2}")
                    continue
            lines.append(ln.rstrip())
        out = "\n".join(lines)
        if not out.endswith("\n"):
            out += "\n"
        return out

    def on_clone_unit(self):
        """B1 克隆：只进内存，点保存才写盘。"""
        if not self.project.project_dir and not self.project.single_path:
            QMessageBox.information(self, "克隆", "请先打开工程或单文件")
            return
        default_src = ""
        if self.current_section_id and (self.current_prefer or "") not in ("art", "ai"):
            default_src = self.current_section_id
        dlg = CloneUnitDialog(self.project, self, default_src=default_src)
        if dlg.exec() != QDialog.Accepted:
            return
        data = dlg.result_data()
        if not data:
            return
        src_id = data["src_id"]
        sid = data["id"]
        type_list = data["type_list"]
        src_body = self.project.get_section_text(src_id)
        body = self._rewrite_clone_body(
            src_id, sid, src_body,
            name=data.get("name") or "",
            rewrite_identity=bool(data.get("rewrite_identity")),
        )
        path_str = data.get("path") or ""
        if not path_str:
            src_path = self.project.get_source_path_for_section(src_id)
            path_str = str(src_path) if src_path else ""
        if not path_str:
            path_str, _ = QFileDialog.getSaveFileName(
                self, "选择计划写入的 INI（不会立即写盘）",
                str(self.project.project_dir or Path.home()), "INI (*.ini)",
            )
            if not path_str:
                return
        path = Path(path_str)

        self.project.inject_section_memory(
            sid, body, source_path=path,
            type_list=type_list if data.get("also_register") else None,
        )
        self._mem_sections[sid] = body
        pending = {
            "id": sid,
            "path": str(path),
            "type_list": type_list,
            "also_register": bool(data.get("also_register")),
            "register_path": data.get("register_path") or "",
            "is_new": True,
            "kind": "clone",
            "src_id": src_id,
            "write_csf": bool(data.get("write_csf")),
            "csf_text": (data.get("csf_text") or "").strip(),
        }

        art_note = "否"
        if data.get("copy_art") and self.project.art and self.project.art.get_section(src_id):
            art_body_src = self.project.get_section_text(src_id, prefer=self.project.art)
            art_body = self._rewrite_clone_body(
                src_id, sid, art_body_src,
                name=data.get("name") or "",
                rewrite_identity=bool(data.get("rewrite_identity")),
            )
            art_path = self.project.get_source_path_for_section(src_id, prefer="art")
            if art_path and Path(art_path).is_file():
                # art 也先只进内存
                from core.ini_parser import INISection
                from core.save_util import normalize_section_body
                nb = normalize_section_body(sid, art_body)
                sec = INISection(sid)
                sec.source_file = Path(art_path).name
                for line in nb.splitlines():
                    s = line.strip()
                    if not s or s.startswith(";") or (s.startswith("[") and "]" in s):
                        continue
                    if "=" in s:
                        if ";" in s:
                            s = s.split(";", 1)[0].strip()
                        k, _, v = s.partition("=")
                        if k.strip():
                            sec.set(k.strip(), v.strip())
                self.project.art.sections[sid] = sec
                if sid not in self.project.art.section_order:
                    self.project.art.section_order.append(sid)
                self._mem_sections[f"art::{sid}"] = art_body if art_body.endswith("\n") else art_body + "\n"
                pending["art_path"] = str(art_path)
                pending["art_body"] = self._mem_sections[f"art::{sid}"]
                art_note = f"内存中已克隆，计划 → {art_path}"
            else:
                art_note = "模板无 Art 源文件"

        self._pending_new[sid] = pending
        self._touch_session_change(sid, is_new=True, kind="clone")
        self._dirty = True
        self.project.invalidate_classify_cache()
        self._display_cache.clear()
        self.refresh_tree()
        self.open_section_tab(sid)
        QMessageBox.information(
            self, "已克隆到编辑器（未写盘）",
            f"[{src_id}] → [{sid}]\n"
            f"计划 rules: {path}\n"
            f"注册表: {'是 → ' + (data.get('register_path') or '') if data.get('also_register') else '否'}\n"
            f"Art: {art_note}\n\n"
            f"请检查后点「保存当前」才会写入文件并备份。",
        )

    def _resolve_type_list_file(self, type_list: str, preferred: str = "") -> Path | None:
        """解析真正含有 [type_list] 的文件；优先 preferred，否则用工程索引。"""
        from core.save_util import read_text, find_section_span
        candidates: list[Path] = []
        if preferred:
            p = Path(preferred)
            if not p.is_file() and self.project.project_dir:
                alt = self.project.project_dir / p
                if alt.is_file():
                    p = alt
            if p.is_file():
                candidates.append(p.resolve())
        for f in self.project.files_with_type_list(type_list) or []:
            rp = Path(f).resolve()
            if rp not in candidates:
                candidates.append(rp)
        # 单文件模式
        if self.project.single_path and self.project.single_path.is_file():
            rp = self.project.single_path.resolve()
            if rp not in candidates:
                candidates.append(rp)
        for path in candidates:
            try:
                text, _ = read_text(path)
            except Exception:
                continue
            if find_section_span(text, type_list) is not None:
                return path
        return None

    def _write_csf_uiname(self, section_id: str, display_text: str) -> dict:
        """
        写入游戏界面中文到 CSF（不是 Name= 内部名）。
        标签大小写跟目标文件惯例；多文件时写优先级最高的 stringtable。
        """
        from core.csf_parser import upsert_label_to_file, resolve_csf_write_target
        if not self.project.project_dir:
            return {"ok": False, "message": "无工程目录，无法定位 CSF"}
        patterns = list(self.project.profile.get("csf_files") or []) or [
            "stringtable*.csf", "ra2md.csf", "ra2.csf"
        ]
        target = resolve_csf_write_target(self.project.project_dir, patterns)
        if not target:
            return {"ok": False, "message": "工程中未找到可写的 CSF（检查 profile.csf_files）"}
        value = (display_text or "").strip()
        if not value:
            return {"ok": False, "message": "CSF 中文名为空，已跳过"}
        backup_root = self.project.project_dir / "backups"
        res = upsert_label_to_file(
            target, "", value, backup_root=backup_root, section_id=section_id
        )
        if res.get("ok"):
            label = res.get("label") or ""
            try:
                if label:
                    self.project.csf.set(label, value)
            except Exception:
                pass
            try:
                self._display_cache[section_id.lower()] = value
            except Exception:
                pass
        return res

    def _append_to_type_list(self, path: Path, type_list: str, new_id: str) -> dict:

        """
        在已有 [TypeList] 末尾追加 + =ID。
        - 节头允许行尾注释（与 find_section_span 一致）
        - 若指定文件没有该节：自动改到工程里真正含有该节的文件
        - 绝不擅自「新建」空的 [InfantryTypes] 污染无关 ini
        """
        from core.save_util import read_text, backup_file, find_section_span, encode_ini_bytes
        import re

        type_list = (type_list or "").strip()
        new_id = (new_id or "").strip()
        if not type_list or not new_id:
            return {"ok": False, "message": "注册表类型或 ID 为空"}

        preferred = str(path) if path else ""
        resolved = self._resolve_type_list_file(type_list, preferred=preferred)
        if resolved is None:
            return {
                "ok": False,
                "message": (
                    f"工程中找不到已有的 [{type_list}] 节，已中止注册（不会新建空注册表）。\n"
                    f"请确认 rules/扩展 ini 里存在该注册表，或在克隆时改选正确的注册表文件。"
                ),
            }
        path = resolved

        try:
            text, enc = read_text(path)
        except Exception as e:
            return {"ok": False, "message": f"读取注册表失败: {e}"}

        span = find_section_span(text, type_list)
        if span is None:
            return {"ok": False, "message": f"{path.name} 中未找到 [{type_list}]"}

        start, end = span
        # 块内从节头下一行到节尾
        header_end = text.find("\n", start)
        if header_end < 0:
            header_end = end
        else:
            header_end += 1
        block = text[header_end:end]

        # 已存在？
        if re.search(rf"(?im)^[^=]+=\s*{re.escape(new_id)}\s*(;.*)?$", block):
            return {"ok": True, "message": f"[{new_id}] 已在 {path.name} 的 [{type_list}] 中"}
        if re.search(rf"(?im)^\+=\s*{re.escape(new_id)}\s*(;.*)?$", block):
            return {"ok": True, "message": f"[{new_id}] 已在 {path.name} 的 [{type_list}] 中"}

        insert_line = f"+={new_id}\n"
        # 保持节末至多一个空行
        block_core = block.rstrip("\r\n") + "\n" + insert_line
        # 若原节后还有内容且是下一节，由 find 的 end 已不含“节间空行之外”的误伤
        new_text = text[:header_end] + block_core + text[end:]
        # 节与下一节之间补一个空行
        rest = text[end:]
        if rest.lstrip().startswith("["):
            # block_core 已以 \n 结尾，再加一个 \n 形成空行；吃掉 rest 原有前导空行
            i = 0
            while i < len(rest) and rest[i] in "\r\n":
                i += 1
            new_text = text[:header_end] + block_core + "\n" + rest[i:]

        backup_root = (
            (self.project.project_dir / "backups")
            if self.project.project_dir
            else (path.parent / "backups")
        )
        try:
            backup_file(path, backup_root)
        except Exception as e:
            return {"ok": False, "message": f"注册表备份失败，已中止: {e}"}
        try:
            path.write_bytes(encode_ini_bytes(new_text, enc))
        except Exception as e:
            return {"ok": False, "message": f"写入注册表失败: {e}"}

        # 同步内存里的类型表，对象树能立刻看到
        try:
            ini = self.project.rules or self.project.active_ini()
            if ini:
                lst = ini.get_section(type_list)
                if lst is not None and hasattr(lst, "set"):
                    # 用唯一数字键或 += 形式注入内存
                    lst.set("+", new_id, source_file=path.name)
        except Exception:
            pass

        note = ""
        if preferred and Path(preferred).resolve() != path.resolve():
            note = f"（已自动改用真正含 [{type_list}] 的文件，而非 {Path(preferred).name}）"
        return {
            "ok": True,
            "message": f"已注册 +={new_id} → {path.name} [{type_list}]{note}",
            "path": str(path),
        }

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

        if not self._confirm_danger(
            "确认删除",
            f"确定删除节 [{sid}]？",
            f"将从文件中移除该节（先自动备份）：\n{src}\n\n"
            "若它还在类型注册表里，会尽量一并去掉对应项。",
        ):
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
        if getattr(self, "merge_target_row", None):
            self.merge_target_row.hide()
        self._dirty = False
        self._display_cache.clear()
        self.project.invalidate_classify_cache()
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
        text = f"""<h3>{APP_TITLE}</h3>
<p>面向 <b>红警 2 / 尤里的复仇 / 心灵终结</b> 等基于 INI 的 Mod 工程，
用于浏览、编辑、保存规则文件，并可与 AutoReloader 热重载配合调试。</p>
<hr>
<p><b>打开工程</b>：选择游戏或 Mod 目录，按当前配置档读取 rules / art / ai 与字符串表。
也支持只打开单个 ini。</p>
<p><b>编辑</b>：左侧对象树选择单位或注册表；中间为代码区；右侧为字段说明（只读参考）。</p>
<p><b>保存</b>：写回来源文件并自动备份。拆分在多份 ini 中的节会按键来源分别写回。
可在「首选项」中选择全量或增量写入。文件编码为 <b>UTF-8（无 BOM）</b>。</p>
<p><b>常用功能</b></p>
<ul>
<li>全工程搜索、当前节与磁盘/打开时对比</li>
<li>新增 / 克隆单位（先改内存，确认保存后再写盘）</li>
<li>依赖关系图（可查看引用与被引用）</li>
<li>本会话改动列表与片段导出</li>
<li>同节多文件来源查看（Ctrl+Shift+U）</li>
</ul>
<p><b>调试</b>：可将单单位部署到 hotfix.ini，配合注入组件在游戏中热重载。</p>
<p><b>配置</b>：菜单「配置」切换 Mental Omega / Yuri's Revenge 等配置档；
「首选项」可调整校验、备份与保存方式。</p>
"""
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
            f"{APP_TITLE}\n"
            f"{APP_TITLE_EN}\n"
            f"版本 {APP_VERSION}\n\n"
            "AutoReloader 工具链组件之一，用于 Mod 工程的 INI 浏览与编辑。\n"
            "与热重载 DLL、启动器、战术工坊配合使用。\n\n"
            "主要能力：\n"
            "· 工程级合并视图与按来源写回\n"
            "· 搜索、对比、依赖关系、会话改动\n"
            "· 新增/克隆与 CSF 界面名写入\n\n"
            "保存编码：UTF-8（无 BOM）\n"
            "开源仓库：github.com/jiu-zui-90817/AutoReloader",
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
