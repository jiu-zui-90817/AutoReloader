"""
战术工坊 2.x — 无 Codex 的快调前端。
选游戏目录 → 对象树 → 改常用/动态参数 → 部署 hotfix → 热重载。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QLineEdit, QLabel, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QFileDialog, QToolBar,
    QStatusBar, QSizePolicy, QCheckBox, QInputDialog,
)

from fields import (
    GROUP_LABELS, REF_KEYS, DEFAULT_ARMORS, DEFAULT_LOCOMOTORS, BOOLISH,
    ordered_keys,
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
from shared.ini_loader import INISection  # noqa: E402


class NoWheelFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, QComboBox) and obj.view().isVisible():
                return False
            return True
        return super().eventFilter(obj, event)


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
        self.current_group: str = ""
        self.entries: Dict[str, QWidget] = {}
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

        act_game = QAction("打开游戏目录", self)
        act_game.triggered.connect(self.open_game_dir)
        tb.addAction(act_game)

        act_hf = QAction("绑定 hotfix", self)
        act_hf.triggered.connect(self.choose_hotfix)
        tb.addAction(act_hf)

        tb.addSeparator()
        self.btn_mode = QPushButton()
        self.btn_mode.clicked.connect(self.toggle_mode)
        tb.addWidget(self.btn_mode)

        tb.addSeparator()
        self.btn_deploy = QPushButton("部署 (Ctrl+S)")
        self.btn_deploy.setObjectName("primaryBtn")
        self.btn_deploy.clicked.connect(self.deploy)
        tb.addWidget(self.btn_deploy)

        self.btn_restore = QPushButton("恢复原版")
        self.btn_restore.clicked.connect(self.restore_default)
        tb.addWidget(self.btn_restore)

        self.btn_copy = QPushButton("复制完整代码")
        self.btn_copy.clicked.connect(self.copy_full_code)
        tb.addWidget(self.btn_copy)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.path_label = QLabel("未绑定")
        self.path_label.setStyleSheet("color:#9ca3af; padding-right:12px;")
        tb.addWidget(self.path_label)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        self.dir_label = QLabel("游戏目录：未打开")
        self.dir_label.setStyleSheet("color:#7dd3fc;")
        top.addWidget(self.dir_label, 1)
        self.chk_assist = QCheckBox("辅助下拉")
        self.chk_assist.setChecked(self.assist)
        self.chk_assist.toggled.connect(self._on_assist)
        top.addWidget(self.chk_assist)
        root.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("搜索注册名 / 中文…")
        self.filter_edit.textChanged.connect(lambda: self._filter_timer.start(160))
        ll.addWidget(self.filter_edit)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self.on_tree_click)
        ll.addWidget(self.tree, 1)
        left.setMinimumWidth(260)
        left.setMaximumWidth(380)
        split.addWidget(left)

        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(4, 0, 4, 0)
        self.sec_title = QLabel("选择单位后显示参数")
        self.sec_title.setStyleSheet("font-weight:700; font-size:14px; color:#c4b5fd;")
        ml.addWidget(self.sec_title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.form_inner = QWidget()
        self.form_layout = QVBoxLayout(self.form_inner)
        self.form_layout.setAlignment(Qt.AlignTop)
        self.form_layout.setSpacing(0)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.form_inner)
        ml.addWidget(self.scroll, 1)
        row = QHBoxLayout()
        b_add = QPushButton("+ 属性")
        b_add.clicked.connect(self.add_key)
        b_sync = QPushButton("表单 → 预览")
        b_sync.clicked.connect(self.sync_form_to_code)
        row.addWidget(b_add)
        row.addWidget(b_sync)
        row.addStretch()
        ml.addLayout(row)
        split.addWidget(mid)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("代码预览"))
        self.code = QPlainTextEdit()
        self.code.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.code.setObjectName("codeEdit")
        rl.addWidget(self.code, 1)
        right.setMinimumWidth(240)
        right.setMaximumWidth(360)
        split.addWidget(right)

        split.setSizes([300, 560, 300])
        QAction("deploy", self, shortcut=QKeySequence("Ctrl+S"), triggered=self.deploy)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #121212; color: #e8e8e8; }
            QWidget { color: #e8e8e8; }
            QToolBar { background: #1a1a1a; border-bottom: 1px solid #333; spacing: 8px; padding: 6px; }
            QStatusBar { background: #1a1a1a; color: #aaa; }
            QTreeWidget {
                background: #141418; border: 1px solid #2e2e38; border-radius: 6px;
                font-size: 12px; outline: none;
            }
            QTreeWidget::item { padding: 4px 6px; }
            QTreeWidget::item:selected { background: #5b4b8a; }
            QPlainTextEdit#codeEdit {
                background: #0a0a0a; color: #00cc66;
                border: 1px solid #333; border-radius: 4px;
                font-family: Consolas, monospace; font-size: 12px;
            }
            QLineEdit, QComboBox {
                background: #1e1e24; border: 1px solid #3a3a48; border-radius: 4px;
                padding: 4px 8px; min-height: 24px;
            }
            QComboBox { padding-right: 28px; }
            QComboBox::drop-down {
                subcontrol-origin: padding; subcontrol-position: center right;
                width: 22px; border-left: 1px solid #3a3a48; background: #2c2c34;
            }
            QComboBox::down-arrow {
                width: 0; height: 0;
                border-left: 5px solid transparent; border-right: 5px solid transparent;
                border-top: 6px solid #e0e0e0; margin-right: 6px;
            }
            QPushButton {
                background: #2c2c34; border: 1px solid #45454f; border-radius: 5px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #3a3a45; }
            QPushButton#primaryBtn { background: #8b1a1a; border-color: #a33; color: #fff; font-weight: 700; }
            QFrame#propRow { background: #2d2d30; }
            QFrame#propSep { background: #c8c8d0; max-height: 1px; min-height: 1px; }
            QLabel#propKey { font-weight: 700; font-size: 13px; }
            QLabel#propDesc { color: #a8a8b0; font-size: 11px; }
            QScrollArea { border: none; background: #1a1a1e; }
        """)

    def _update_mode_ui(self):
        if self.mode == "safe":
            self.btn_mode.setText("🔒 安全模式")
            self.btn_mode.setStyleSheet("background:#2d5a2d; color:#fff; font-weight:700;")
            self.btn_restore.setEnabled(True)
        else:
            self.btn_mode.setText("🔓 高级模式")
            self.btn_mode.setStyleSheet("background:#5a3a2a; color:#fff; font-weight:700;")
            self.btn_restore.setEnabled(False)

    def toggle_mode(self):
        if self.mode == "safe":
            ok = QMessageBox.question(
                self, "高级模式",
                "高级模式可读写任意 .ini。\n「恢复原版」将禁用。\n是否切换？",
            )
            if ok != QMessageBox.Yes:
                return
            self.mode = "advanced"
        else:
            ok = QMessageBox.question(self, "安全模式", "仅允许操作 hotfix.ini，并重新启用恢复原版。是否切换？")
            if ok != QMessageBox.Yes:
                return
            self.mode = "safe"
        self._update_mode_ui()
        self._save_settings()

    def _on_assist(self, checked: bool):
        self.assist = checked
        self._save_settings()
        if self.current_id:
            self.load_section(self.current_id, self.current_group)

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
        self.path_label.setText(str(p))
        self._watch_mtime = p.stat().st_mtime if p.exists() else 0
        self.statusBar().showMessage(f"已绑定 {p}")

    def refresh_tree(self):
        self.tree.clear()
        if not self.game:
            return
        filt = self.filter_edit.text().strip().lower()
        groups = self.game.list_groups()
        for gname, ids in groups.items():
            label = GROUP_LABELS.get(gname, gname)
            items = []
            for uid in ids:
                disp = self.game.display_name(uid)
                if filt and filt not in uid.lower() and filt not in disp.lower():
                    continue
                items.append((uid, disp))
            if not items and filt:
                continue
            node = QTreeWidgetItem(self.tree, [f"{label} ({len(items) if filt else len(ids)})"])
            node.setData(0, Qt.UserRole, None)
            node.setData(0, Qt.UserRole + 1, gname)
            for uid, disp in (items if filt else [(i, self.game.display_name(i)) for i in ids]):
                child = QTreeWidgetItem(node, [disp])
                child.setData(0, Qt.UserRole, uid)
                child.setData(0, Qt.UserRole + 1, gname)
            if filt:
                node.setExpanded(True)

    def on_tree_click(self, item: QTreeWidgetItem, _col: int):
        sid = item.data(0, Qt.UserRole)
        if not sid:
            return
        group = item.data(0, Qt.UserRole + 1) or ""
        self.load_section(str(sid), str(group))

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
            opts = ["yes", "no", "true", "false"]
        else:
            opts = self.game.list_options(kind)
        self._option_cache[kind] = opts
        return opts

    def _ref_kind(self, key: str, value: str) -> Optional[str]:
        if not self.assist:
            return None
        kl = key.lower()
        if kl in REF_KEYS:
            return REF_KEYS[kl]
        if value.strip().lower() in BOOLISH:
            return "bool"
        return None

    def _add_row(self, key: str, value: str):
        box = QFrame()
        box.setObjectName("propRow")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        kl = QLabel(key)
        kl.setObjectName("propKey")
        lay.addWidget(kl)
        dl = QLabel("")
        dl.setObjectName("propDesc")
        lay.addWidget(dl)
        kind = self._ref_kind(key, value)
        if kind:
            combo = QComboBox()
            combo.setEditable(True)
            combo.setFixedHeight(28)
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
            combo.currentTextChanged.connect(lambda *_: self.sync_form_to_code())
            lay.addWidget(combo)
            self.entries[key] = combo
        else:
            edit = QLineEdit(value)
            edit.setFixedHeight(28)
            edit.installEventFilter(self._no_wheel)
            edit.textChanged.connect(lambda *_: self.sync_form_to_code())
            lay.addWidget(edit)
            self.entries[key] = edit
        self.form_layout.addWidget(box)
        sep = QFrame()
        sep.setObjectName("propSep")
        sep.setFixedHeight(1)
        self.form_layout.addWidget(sep)

    def _widget_value(self, w: QWidget) -> str:
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QLineEdit):
            return w.text()
        return ""

    def load_section(self, section_id: str, group: str = ""):
        if not self.game:
            return
        self.current_id = section_id
        self.current_group = group
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
        self._loading = True
        self._clear_form()
        for k in ordered_keys(keys, group):
            self._add_row(k, keys[k])
        if not keys:
            for k in ordered_keys({x: "" for x in ordered_keys({}, group)[:12]}, group):
                self._add_row(k, "")
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
        import re
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
        lines = [f"[{self.current_id}]"]
        for key, w in self.entries.items():
            val = self._widget_value(w)
            if val != "":
                lines.append(f"{key}={val}")
        self._loading = True
        self.code.setPlainText("\n".join(lines) + "\n")
        self._loading = False

    def add_key(self):
        if not self.current_id:
            return
        key, ok = QInputDialog.getText(self, "添加属性", "键名:")
        if not ok or not key.strip():
            return
        key = key.strip()
        if key in self.entries:
            QMessageBox.information(self, "添加", "已存在")
            return
        self._add_row(key, "")
        self.sync_form_to_code()

    def deploy(self):
        if not self.current_id:
            QMessageBox.information(self, "部署", "请先选择单位")
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
                backup_root=backup_root, is_new=False, peer_section_names=[],
            )
            if not result.get("ok"):
                result = save_section_to_file(
                    self.hotfix_path, self.current_id, body,
                    backup_root=backup_root, is_new=True, peer_section_names=[],
                )
        if result.get("ok"):
            self._watch_mtime = self.hotfix_path.stat().st_mtime
            QTimer.singleShot(5000, self.clean_hotfix_silent)
            QMessageBox.information(self, "部署成功", f"[{self.current_id}] → {self.hotfix_path}")
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
            self.load_section(self.current_id, self.current_group)
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
        import re
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
        QMessageBox.information(self, "已复制", "完整代码（原版 + 修改）已复制到剪贴板。")

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
                win.dir_label.setText(f"游戏目录：{last}  |  CSF {len(win.game.csf.strings)} 条")
                win.refresh_tree()
        except Exception:
            pass
    hf = win.settings.get("last_hotfix")
    if hf and Path(hf).exists():
        win.hotfix_path = Path(hf)
        win.path_label.setText(hf)
    sys.exit(app.exec())
