"""
战术工坊 2.x（逻辑对齐旧版 TacticalConsole + CodexGenerator，UI 为现代对象树）

- 词典：打开游戏目录后自动构建/加载 Codex（武器显示为「ID - 单位名 [主武]」）
- 对象树：步兵/载具/飞行器/建筑/武器/弹头
- 属性：旧版固定字段，标签在上、值在下
- 部署：安全模式只写 hotfix.ini；高级模式可写任意工程文件
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QLineEdit, QLabel, QPushButton,
    QComboBox, QScrollArea, QFrame, QMessageBox, QFileDialog, QToolBar,
    QStatusBar, QSizePolicy, QCheckBox,
)

from fields import (
    TREE_ORDER,
    FORM_UNITS,
    FORM_WEAPONS,
    FORM_WARHEADS,
    RULES_UNITS,
)


def _is_ephemeral(path: Path) -> bool:
    s = str(path).replace("\\", "/").lower()
    return any(n in s for n in (
        "/temp/", "/tmp/", "appdata/local/temp", "onefile_", "/onefile/", "nuitka_temp",
    ))


def is_frozen() -> bool:
    if getattr(sys, "frozen", False):
        return True
    import os
    if os.environ.get("NUITKA_ONEFILE_PARENT"):
        return True
    try:
        import __main__
        if getattr(__main__, "__compiled__", None) is not None:
            return True
    except Exception:
        pass
    try:
        if _is_ephemeral(Path(__file__).resolve().parent):
            return True
    except Exception:
        pass
    return False


def local_appdata() -> Path:
    import os
    env = os.environ.get("LOCALAPPDATA") or os.environ.get("LocalAppData")
    if env:
        return Path(env)
    return Path.home() / "AppData" / "Local"


def get_app_dir() -> Path:
    if is_frozen():
        parent = Path(sys.executable).resolve().parent
        if not _is_ephemeral(parent):
            return parent
        try:
            a0 = Path(sys.argv[0]).resolve()
            if a0.suffix.lower() == ".exe" and not _is_ephemeral(a0.parent):
                return a0.parent
        except Exception:
            pass
        return parent
    return Path(__file__).resolve().parent


def get_bundle_dir() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        try:
            return Path(__file__).resolve().parent
        except Exception:
            return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_repo_root() -> Path:
    if is_frozen():
        return get_app_dir()
    return Path(__file__).resolve().parents[2]



def ensure_shared_path() -> None:
    for p in (get_repo_root(), get_bundle_dir(), get_app_dir()):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


ensure_shared_path()

from shared.project_scan import GameProject, load_profiles  # noqa: E402
from shared.hotfix_io import save_section_to_file, normalize_section_body, read_text  # noqa: E402
from shared.codex_builder import build_codex, load_codex, save_codex  # noqa: E402


def load_common_flags() -> dict:
    """开发读 shared；打包读 exe/_MEIPASS 旁 schemas（构建时从 shared 拷入）。"""
    app = get_app_dir()
    bundle = get_bundle_dir()
    root = get_repo_root()
    candidates = [
        # 打包：与 exe 同级（Pack 步骤会复制）
        app / "schemas" / "common_flags.json",
        app / "shared" / "schemas" / "common_flags.json",
        # 打包：包内资源
        bundle / "schemas" / "common_flags.json",
        bundle / "shared" / "schemas" / "common_flags.json",
        # 源码开发：仓库唯一源
        root / "shared" / "schemas" / "common_flags.json",
        root / "Frontend" / "workshop" / "schemas" / "common_flags.json",
        root / "Frontend" / "editor" / "schemas" / "common_flags.json",
    ]
    for path in candidates:
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            continue
    return {}


def flag_label(flags: dict, key: str) -> str:
    meta = flags.get(key) if flags else None
    if not isinstance(meta, dict):
        kl = key.lower()
        for k, v in (flags or {}).items():
            if k.startswith("_"):
                continue
            if k.lower() == kl and isinstance(v, dict):
                meta = v
                break
    if not isinstance(meta, dict):
        return key
    zh = (meta.get("desc_zh") or "").strip()
    if zh:
        if key.lower() in zh.lower() or f"({key})" in zh:
            return zh
        return f"{zh} ({key})"
    return key


def infer_field_spec(key: str, value: str, flags: dict) -> tuple:
    """动态键 → (label, wtype, src)。"""
    label = flag_label(flags, key)
    meta = {}
    if flags:
        if key in flags and isinstance(flags[key], dict):
            meta = flags[key]
        else:
            for k, v in flags.items():
                if not k.startswith("_") and k.lower() == key.lower() and isinstance(v, dict):
                    meta = v
                    break
    typ = (meta.get("type") or "").lower()
    kl = key.lower()

    if typ == "weapon" or kl in {
        "primary", "secondary", "eliteprimary", "elitesecondary",
        "occupyweapon", "eliteoccupyweapon", "deathweapon",
    }:
        return label, "combo", "WeaponList"
    if typ == "warhead" or kl == "warhead":
        return label, "combo", "WarheadList"
    if typ in ("animation", "anim") or kl in {"anim", "attacheffect.animation"}:
        return label, "combo", "AnimList"
    if typ == "armor" or kl == "armor":
        return label, "combo", "Armors"
    if typ == "locomotor" or kl == "locomotor":
        return label, "combo", "Locomotors"
    if typ == "bool" or kl in {
        "selfhealing", "radarinvisible", "opportunityfire", "crusher",
        "omnicrushresistant", "cloakable", "trainable", "crewed", "capturable",
        "rocker", "mindcontrol", "parasite", "wallabsolutedestroyer",
        "attacheffect.cumulative", "attacheffect.animresetonreapply",
        "attacheffect.forcedecloak", "attacheffect.discardonentry",
        "attacheffect.cloakable",
    }:
        return label, "combo", "Booleans"
    if str(value).lower() in {"yes", "no", "true", "false"}:
        return label, "combo", "Booleans"
    if kl == "image":
        return label, "combo", "DYNAMIC_IMAGE"
    return label, "entry", None



def extract_real_id(text: str) -> str:
    """从「ID - 中文 [主武]」或「中文 [ID]」还原真正的 ini 值。"""
    if not text:
        return ""
    text = text.strip()
    if " - " in text:
        return text.split(" - ", 1)[0].strip()
    if " [" in text and text.endswith("]"):
        return text.split("[")[-1].replace("]", "").strip()
    return text


class NoWheelFilter(QObject):
    """禁止在下拉框外的控件上滚轮改值。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QComboBox):
            if not obj.view().isVisible():
                return True
        return super().eventFilter(obj, event)


class WorkshopWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("战术工坊 2.x")
        self.resize(1280, 800)

        self.settings = self._load_settings()
        self.mode = self.settings.get("mode", "safe")  # safe | advanced
        self.assist = bool(self.settings.get("assist", True))
        self.expand_all = bool(self.settings.get("expand_all", False))
        self.flags = load_common_flags()
        self.game: Optional[GameProject] = None
        self.codex: dict = {}
        self.hotfix_path: Optional[Path] = None
        self.current_id: Optional[str] = None
        self.current_kind: str = "unit"  # unit | weapon | warhead
        self.current_utype: str = "Unknown"
        self._widgets: Dict[str, QWidget] = {}
        self._switching = False
        self._wheel_filter = NoWheelFilter(self)

        self._build_ui()
        self._apply_style()
        self._update_mode_ui()

        last = self.settings.get("last_game_dir")
        if last and Path(last).is_dir():
            QTimer.singleShot(150, lambda p=last: self.open_game_dir(p))
        elif last:
            # 路径失效则清掉，避免每次弹错
            self.settings.pop("last_game_dir", None)
            self._save_settings()

        self._watch = QTimer(self)
        self._watch.timeout.connect(self._file_watch)
        self._watch.start(1500)

    # ---------- settings ----------
    def _settings_path(self) -> Path:
        """可写 console_config。禁止写临时目录。"""
        candidates = []
        ad = get_app_dir()
        if not _is_ephemeral(ad):
            candidates.append(ad / "console_config.json")
        candidates.append(local_appdata() / "TacticalWorkshop" / "console_config.json")
        candidates.append(Path.home() / ".tactical_workshop" / "console_config.json")
        for path in candidates:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.is_file():
                    return path
                probe = path.parent / ".w"
                probe.write_text("1", encoding="utf-8")
                probe.unlink(missing_ok=True)
                return path
            except Exception:
                continue
        fallback = local_appdata() / "TacticalWorkshop" / "console_config.json"
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return fallback


    def _load_settings(self) -> dict:
        p = self._settings_path()
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_settings(self) -> None:
        try:
            self._settings_path().write_text(
                json.dumps(self.settings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _profile(self) -> dict:
        root = get_repo_root()
        candidates = [
            root / "shared" / "profiles.json",
            get_app_dir() / "shared" / "profiles.json",
            get_bundle_dir() / "shared" / "profiles.json",
        ]
        data = {}
        for p in candidates:
            if p.is_file():
                try:
                    data = load_profiles(p)
                    break
                except Exception:
                    pass
        if not data:
            data = load_profiles(Path("__missing__"))
        active = data.get("active_profile") or "MentalOmega"
        return (data.get("profiles") or {}).get(active) or {
            "rules_files": ["rulesmo.ini", "rulesmd.ini"],
            "art_files": ["artmo.ini", "artmd.ini"],
            "csf_files": ["ra2md.csf", "stringtable*.csf"],
        }

    def _cache_dir(self) -> Path:
        candidates = []
        ad = get_app_dir()
        if not _is_ephemeral(ad):
            candidates.append(ad / "cache")
        candidates.append(local_appdata() / "TacticalWorkshop" / "cache")
        candidates.append(Path.home() / ".tactical_workshop" / "cache")
        for d in candidates:
            try:
                d.mkdir(parents=True, exist_ok=True)
                probe = d / ".w"
                probe.write_text("1", encoding="utf-8")
                probe.unlink(missing_ok=True)
                return d
            except Exception:
                continue
        import tempfile
        d = Path(tempfile.gettempdir()) / "tactical_workshop_cache"
        d.mkdir(parents=True, exist_ok=True)
        return d


    def _codex_path(self, game_dir: str) -> Path:
        safe = re.sub(r"[^\w\-]+", "_", str(game_dir).strip("\\/"))[:80] or "default"
        return self._cache_dir() / f"codex_{safe}.json"

    # ---------- UI ----------
    def _build_ui(self):
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        act_open = QAction("打开游戏目录", self)
        act_open.triggered.connect(lambda: self.open_game_dir())
        tb.addAction(act_open)

        act_hf = QAction("绑定工程文件", self)
        act_hf.triggered.connect(self.choose_hotfix)
        tb.addAction(act_hf)

        tb.addSeparator()
        self.mode_btn = QPushButton()
        self.mode_btn.clicked.connect(self.toggle_mode)
        tb.addWidget(self.mode_btn)

        self.assist_cb = QCheckBox("辅助下拉")
        self.assist_cb.setToolTip("开启：武器等显示「ID - 单位名 [主武]」；关闭：仅 ID")
        self.assist_cb.setChecked(self.assist)
        self.assist_cb.toggled.connect(self._on_assist)
        tb.addWidget(self.assist_cb)

        self.expand_cb = QCheckBox("展开全部键")
        self.expand_cb.setToolTip("关闭：经典快调固定字段；开启：该单位/武器实际存在的全部键（现代动态）")
        self.expand_cb.setChecked(self.expand_all)
        self.expand_cb.toggled.connect(self._on_expand)
        tb.addWidget(self.expand_cb)

        tb.addSeparator()
        act_dep = QAction("测试部署 (Ctrl+S)", self)
        act_dep.setShortcut(QKeySequence.Save)
        act_dep.triggered.connect(self.deploy)
        tb.addAction(act_dep)

        act_rst = QAction("恢复默认", self)
        act_rst.triggered.connect(self.restore_default)
        tb.addAction(act_rst)

        act_copy = QAction("复制代码", self)
        act_copy.triggered.connect(self.copy_full_code)
        tb.addAction(act_copy)

        act_rebuild = QAction("重建词典", self)
        act_rebuild.triggered.connect(self.rebuild_codex)
        tb.addAction(act_rebuild)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        self.dir_label = QLabel("游戏目录：未绑定")
        self.dir_label.setObjectName("pathLabel")
        self.hf_label = QLabel("工程文件：未绑定")
        self.hf_label.setObjectName("pathLabel")
        top = QHBoxLayout()
        top.addWidget(self.dir_label, 1)
        top.addWidget(self.hf_label, 1)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # 左：搜索 + 对象树
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索单位 / 武器 / 弹头…")
        self.search.textChanged.connect(self.refresh_tree)
        ll.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_tree_click)
        ll.addWidget(self.tree, 1)
        split.addWidget(left)

        # 中：属性表单
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.form_title = QLabel("选择左侧对象开始调试")
        self.form_title.setObjectName("formTitle")
        ml.addWidget(self.form_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #252526; border: 1px solid #333; }")
        self.form_host = QWidget()
        self.form_host.setObjectName("formHost")
        self.form_host.setStyleSheet("background: #252526;")
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(0)
        scroll.setWidget(self.form_host)
        ml.addWidget(scroll, 1)
        split.addWidget(mid)

        # 右：预览
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(QLabel("代码预览（可手改，部署时以预览为准）"))
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("preview")
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.preview.setFont(font)
        rl.addWidget(self.preview, 1)
        split.addWidget(right)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 4)
        split.setStretchFactor(2, 2)
        split.setSizes([260, 520, 320])

        self.setStatusBar(QStatusBar())

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #1e1e1e;
                color: #e8e8e8;
                font-size: 13px;
            }
            QToolBar {
                background: #1e1e1e;
                border-bottom: 1px solid #333;
                spacing: 8px;
                padding: 6px 10px;
            }
            QToolBar QToolButton {
                padding: 4px 10px;
                color: #e8e8e8;
            }
            QStatusBar {
                background: #1a1a1a;
                color: #aaa;
            }
            QTreeWidget {
                background: #252526;
                border: 1px solid #3c3c3c;
                outline: none;
                font-size: 12px;
            }
            QTreeWidget::item { padding: 3px 4px; }
            QTreeWidget::item:selected { background: #094771; color: #fff; }
            QTreeWidget::item:hover { background: #2a2d2e; }
            QScrollArea {
                border: 1px solid #333;
                background: #252526;
            }
            QScrollArea > QWidget > QWidget { background: #252526; }
            QWidget#formHost { background: #252526; }
            QWidget#propBlock {
                background: #252526;
                border: none;
            }
            QFrame#propSep {
                background: #3c3c3c;
                border: none;
                max-height: 1px;
                margin: 0 4px;
            }
            QLabel#formTitle {
                font-weight: 700;
                font-size: 14px;
                color: #eee;
                padding: 6px 4px 8px 4px;
                background: transparent;
            }
            QLabel#propLabel {
                color: #d0d0d0;
                font-size: 12px;
                background: transparent;
            }
            QLabel#pathLabel {
                color: #a0a0a0;
                font-size: 12px;
                background: transparent;
            }
            QLabel {
                background: transparent;
                color: #d0d0d0;
            }
            QLineEdit, QComboBox {
                background: #1e1e22;
                border: 1px solid #3f3f46;
                border-radius: 3px;
                padding: 3px 8px;
                min-height: 24px;
                max-height: 28px;
                max-width: 420px;
                color: #e8e8e8;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #5a7aa0;
            }
            QComboBox {
                padding-right: 22px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0; height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #b0b0b0;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background: #1e1e22;
                color: #eee;
                selection-background-color: #094771;
                border: 1px solid #3f3f46;
                outline: none;
            }
            QPlainTextEdit#preview {
                background: #0a0a0a;
                color: #00ff00;
                border: 1px solid #333;
                font-family: Consolas, "Courier New", monospace;
            }
            QPushButton {
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 12px;
                color: #eee;
            }
            QPushButton:hover { background: #404040; }
            QCheckBox { spacing: 6px; color: #ccc; }
            QSplitter::handle {
                background: #333;
                width: 3px;
            }
        """)


    def _update_mode_ui(self):
        if self.mode == "safe":
            self.mode_btn.setText("🔒 安全模式 (仅 hotfix.ini)")
            self.mode_btn.setStyleSheet("background:#2d5a2d; color:#b6ffb6;")
        else:
            self.mode_btn.setText("⚠️ 高级模式 (可写任意 ini)")
            self.mode_btn.setStyleSheet("background:#5a2d2d; color:#ffb6b6;")

    def toggle_mode(self):
        if self.mode == "safe":
            r = QMessageBox.warning(
                self, "切换高级模式",
                "高级模式可写入任意工程文件，有风险。\n确定切换？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
            self.mode = "advanced"
        else:
            self.mode = "safe"
            QMessageBox.information(self, "模式", "已回到安全模式（仅 hotfix.ini）")
        self.settings["mode"] = self.mode
        self._save_settings()
        self._update_mode_ui()

    def _on_assist(self, checked: bool):
        self.assist = checked
        self.settings["assist"] = checked
        self._save_settings()
        if self.current_id:
            self.load_section(self.current_id, self.current_kind)

    def _on_expand(self, checked: bool):
        self.expand_all = checked
        self.settings["expand_all"] = checked
        self._save_settings()
        if self.current_id:
            self.load_section(self.current_id, self.current_kind)

    # ---------- open / codex ----------
    def open_game_dir(self, path: Optional[str] = None):
        if not path:
            start = self.settings.get("last_game_dir") or str(Path.home())
            if not Path(start).is_dir():
                start = str(Path.home())
            path = QFileDialog.getExistingDirectory(
                self, "选择游戏 / 工程目录", start
            )
        if not path:
            return
        path = str(Path(path))
        self.statusBar().showMessage("正在加载…")
        QApplication.processEvents()
        try:
            self.game = GameProject(Path(path), self._profile())
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
            return

        self.settings["last_game_dir"] = path
        self._save_settings()
        self.flags = load_common_flags()
        self.dir_label.setText(f"游戏目录：{path}")

        # 默认 hotfix
        hf = Path(path) / "hotfix.ini"
        if hf.is_file() or self.mode == "safe":
            self.hotfix_path = hf
            self.hf_label.setText(f"工程文件：{hf.name}")

        # 词典：缓存优先，否则构建
        cpath = self._codex_path(path)
        cached = load_codex(cpath)
        if cached and cached.get("WeaponList"):
            self.codex = cached
            meta = cached.get("_meta") or {}
            self.statusBar().showMessage(
                f"词典缓存已加载：武器 {meta.get('weapons', '?')} / "
                f"弹头 {meta.get('warheads', '?')} / 动画 {meta.get('anims', '?')}"
            )
        else:
            self.statusBar().showMessage("正在构建词典（首次较慢）…")
            QApplication.processEvents()
            self._do_build_codex(path)

        self.refresh_tree()
        n = sum(len(v) for v in (self.codex.get("Units") or {}).values())
        self.statusBar().showMessage(f"就绪：{n} 个单位，词典武器 {len(self.codex.get('WeaponList') or {})}")

    def _do_build_codex(self, game_dir: str):
        logs: List[str] = []
        try:
            self.codex = build_codex(Path(game_dir), self._profile(), log=logs.append)
            save_codex(self.codex, self._codex_path(game_dir))
            meta = self.codex.get("_meta") or {}
            self.statusBar().showMessage(
                f"词典已生成：单位 {meta.get('units')} / 武器 {meta.get('weapons')} / "
                f"弹头 {meta.get('warheads')} / 动画 {meta.get('anims')}"
            )
        except Exception as e:
            self.codex = self.codex or {}
            QMessageBox.warning(self, "词典构建失败", f"{e}\n\n" + "\n".join(logs[-8:]))

    def rebuild_codex(self):
        d = self.settings.get("last_game_dir")
        if not d:
            QMessageBox.information(self, "提示", "请先打开游戏目录")
            return
        self.statusBar().showMessage("重建词典中…")
        QApplication.processEvents()
        self._do_build_codex(d)
        self.refresh_tree()
        if self.current_id:
            self.load_section(self.current_id, self.current_kind)

    def choose_hotfix(self):
        if self.mode == "safe":
            path, _ = QFileDialog.getOpenFileName(
                self, "选择 hotfix.ini",
                self.settings.get("last_game_dir") or "",
                "hotfix.ini (hotfix.ini);;All (*.*)",
            )
            if path and Path(path).name.lower() != "hotfix.ini":
                QMessageBox.warning(self, "安全模式", "安全模式只能绑定名为 hotfix.ini 的文件")
                return
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择工程 ini",
                self.settings.get("last_game_dir") or "",
                "INI (*.ini);;All (*.*)",
            )
        if not path:
            return
        self.hotfix_path = Path(path)
        self.hf_label.setText(f"工程文件：{self.hotfix_path.name}")
        if self.current_id:
            self.load_section(self.current_id, self.current_kind)

    # ---------- tree ----------
    def refresh_tree(self):
        self.tree.clear()
        q = (self.search.text() or "").strip().lower()
        units = self.codex.get("Units") or {}
        wlist = self.codex.get("WeaponList") or {}
        whlist = self.codex.get("WarheadList") or {}
        sides = self.codex.get("UnitSides") or {}
        # 无 UnitSides 时退回 UnitOwners（旧缓存）
        if not sides:
            sides = self.codex.get("UnitOwners") or {}
        side_labels = self.codex.get("OwnerLabels") or {}

        def side_title(key: str) -> str:
            if not key:
                return "未分类"
            return side_labels.get(key) or side_labels.get(key.lower()) or key

        def add_leaf(parent, oid: str, zh: str, kind: str) -> bool:
            text = f"{oid}  -  {zh}" if zh and zh != oid else oid
            if q and q not in text.lower() and q not in oid.lower():
                return False
            it = QTreeWidgetItem([text])
            it.setData(0, Qt.ItemDataRole.UserRole, (kind, oid))
            parent.addChild(it)
            return True

        for key, title in TREE_ORDER:
            if key in ("Infantry", "Vehicle", "Aircraft", "Building"):
                data = units.get(key) or {}
                if not data:
                    continue
                by_side: dict = {}
                for oid, zh in data.items():
                    sk = sides.get(oid) or sides.get(oid.upper()) or sides.get(oid.lower()) or "未分类"
                    by_side.setdefault(sk, []).append((oid, zh))

                cat = QTreeWidgetItem([f"{title} ({len(data)})"])
                cat.setFlags(cat.flags() & ~Qt.ItemFlag.ItemIsSelectable)

                for sk in sorted(by_side.keys(), key=lambda x: side_title(x).lower()):
                    items = by_side[sk]
                    side_node = QTreeWidgetItem([f"{side_title(sk)} ({len(items)})"])
                    side_node.setFlags(side_node.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    n = 0
                    for oid, zh in sorted(items, key=lambda x: x[0].lower()):
                        if add_leaf(side_node, oid, zh, "unit"):
                            n += 1
                    if n:
                        cat.addChild(side_node)
                        side_node.setExpanded(bool(q))

                if cat.childCount():
                    self.tree.addTopLevelItem(cat)
                    cat.setExpanded(bool(q))

            elif key == "Weapons" and wlist:
                cat = QTreeWidgetItem([f"武器 ({len(wlist)})"])
                cat.setFlags(cat.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for oid, zh in sorted(wlist.items(), key=lambda x: x[0].lower()):
                    add_leaf(cat, oid, zh, "weapon")
                if cat.childCount():
                    self.tree.addTopLevelItem(cat)
                    cat.setExpanded(bool(q))

            elif key == "Warheads" and whlist:
                cat = QTreeWidgetItem([f"弹头 ({len(whlist)})"])
                cat.setFlags(cat.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                for oid, zh in sorted(whlist.items(), key=lambda x: x[0].lower()):
                    add_leaf(cat, oid, zh, "warhead")
                if cat.childCount():
                    self.tree.addTopLevelItem(cat)
                    cat.setExpanded(bool(q))


    def on_tree_click(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, oid = data
        self.load_section(oid, kind)

    # ---------- form ----------
    def _clear_form(self):
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._widgets.clear()

    def _combo_options(self, src: str) -> List[str]:
        """对齐旧版：`ID - 中文说明`。"""
        if not self.assist:
            # 纯 ID
            if src == "DYNAMIC_IMAGE":
                d = self.codex.get(f"{self.current_utype}Images") or {}
                return [""] + sorted(d.keys(), key=str.lower)
            raw = self.codex.get(src) or {}
            if src in ("Presets_Passive", "Presets_Attack"):
                return [""] + list(raw.keys())
            return [""] + sorted(raw.keys(), key=str.lower)

        if src == "DYNAMIC_IMAGE":
            d = self.codex.get(f"{self.current_utype}Images") or {}
            return [""] + [f"{k} - {v}" if v else k for k, v in sorted(d.items(), key=lambda x: x[0].lower())]
        if src in ("Presets_Passive", "Presets_Attack"):
            return [""] + list((self.codex.get(src) or {}).keys())
        d = self.codex.get(src) or {}
        # 旧版：f"{k} - {v}"
        return [""] + [f"{k} - {v}" if v and k != v else k for k, v in sorted(d.items(), key=lambda x: x[0].lower())]

    def _match_combo(self, value: str, items: List[str]) -> str:
        if not value:
            return ""
        for v in items:
            if not v:
                continue
            if v == value:
                return v
            if v.startswith(f"{value} -"):
                return v
            if v.endswith(f"[{value}]"):
                return v
            if extract_real_id(v) == value:
                return v
        return value

    def _make_control(self, wtype: str, src: Optional[str], value: str) -> QWidget:
        if wtype == "combo" and src:
            cb = QComboBox()
            cb.setEditable(True)
            cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cb.setMaximumWidth(420)
            opts = self._combo_options(src)
            cb.addItems(opts)
            cb.setCurrentText(self._match_combo(value, opts))
            cb.installEventFilter(self._wheel_filter)
            cb.currentTextChanged.connect(lambda _t: self.sync_form_to_code())
            return cb
        le = QLineEdit(value)
        le.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        le.setMaximumWidth(420)
        le.textChanged.connect(lambda _t: self.sync_form_to_code())
        return le


    def _build_form(self, fields, values: Dict[str, str], utype: str):
        """纵排：标签在上、控件在下；行间分割线。fields 为 (key, label, wtype, src) 列表。"""
        self._clear_form()
        for item in fields:
            if not item or len(item) < 4:
                continue
            key, label, wtype, src = item[0], item[1], item[2], item[3]
            if key in RULES_UNITS and utype not in RULES_UNITS[key] and not self.expand_all:
                # 展开模式下不过滤类型限制，让用户看到真实键
                continue
            block = QWidget()
            block.setObjectName("propBlock")
            vl = QVBoxLayout(block)
            vl.setContentsMargins(10, 8, 10, 6)
            vl.setSpacing(4)

            lab = QLabel(label)
            lab.setObjectName("propLabel")
            lab.setWordWrap(True)
            vl.addWidget(lab)

            val = values.get(key, values.get(key.lower(), ""))
            ctrl = self._make_control(wtype, src, val)
            ctrl.setMaximumWidth(420)
            vl.addWidget(ctrl)

            self.form_layout.addWidget(block)
            self._widgets[key] = ctrl

            sep = QFrame()
            sep.setObjectName("propSep")
            sep.setFixedHeight(1)
            sep.setFrameShape(QFrame.Shape.HLine)
            self.form_layout.addWidget(sep)

            if key in ("AEPreset_Passive", "AEPreset_Attack") and isinstance(ctrl, QComboBox):
                ctrl.currentTextChanged.connect(
                    lambda name, k=key: self._apply_ae_preset(name, k)
                )

        self.form_layout.addStretch(1)

    def _resolve_fields(self, kind: str, values: Dict[str, str]) -> list:
        """经典固定表 或 固定优先 + 动态补全全部键。"""
        if kind == "weapon":
            base = list(FORM_WEAPONS)
        elif kind == "warhead":
            base = list(FORM_WARHEADS)
        else:
            base = list(FORM_UNITS)

        if not self.expand_all:
            return base

        # 展开：固定字段优先，再追加 section 里多出来的键
        ordered = []
        seen = set()
        for key, label, wtype, src in base:
            ordered.append((key, label, wtype, src))
            seen.add(key.lower())

        # values 里既有原始大小写键也有 lower；只收非 lower 重复
        raw_keys = []
        for k in values.keys():
            if k != k.lower() or k.lower() not in {x.lower() for x in values if x != x.lower()}:
                # prefer original casing if both exist
                pass
        # 更稳：从 preview 顺序已体现在 values 插入顺序；过滤纯 lower 副本
        preferred_case = {}
        for k in values.keys():
            kl = k.lower()
            if kl in preferred_case:
                # 若已有非全小写，跳过全小写副本
                if k == kl and preferred_case[kl] != kl:
                    continue
            if kl not in preferred_case or (preferred_case[kl] == kl and k != kl):
                preferred_case[kl] = k

        for kl, k in preferred_case.items():
            if kl in seen:
                continue
            if k.startswith("AEPreset_"):
                continue
            val = values.get(k, values.get(kl, ""))
            label, wtype, src = infer_field_spec(k, val, self.flags)
            ordered.append((k, label, wtype, src))
            seen.add(kl)
        return ordered


    def _widget_value(self, w: QWidget) -> str:
        if isinstance(w, QComboBox):
            return extract_real_id(w.currentText())
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""

    def _apply_ae_preset(self, preset_name: str, which: str):
        if self._switching or not preset_name:
            return
        bucket = "Presets_Passive" if "Passive" in which else "Presets_Attack"
        data = (self.codex.get(bucket) or {}).get(preset_name)
        if not isinstance(data, dict):
            return
        self._switching = True
        try:
            for k, v in data.items():
                # 找到大小写匹配的控件
                for wk, w in self._widgets.items():
                    if wk.lower() == k.lower():
                        if isinstance(w, QComboBox):
                            opts = [w.itemText(i) for i in range(w.count())]
                            w.setCurrentText(self._match_combo(str(v), opts))
                        elif isinstance(w, QLineEdit):
                            w.setText(str(v))
                        break
        finally:
            self._switching = False
        self.sync_form_to_code()

    def load_section(self, section_id: str, kind: str = "unit"):
        self._switching = True
        self.current_id = section_id
        self.current_kind = kind
        self.current_utype = (self.codex.get("UnitTypeMap") or {}).get(section_id, "Unknown")
        if kind == "weapon":
            self.current_utype = "Weapon"
        elif kind == "warhead":
            self.current_utype = "Warhead"

        zh = ""
        if kind == "unit":
            for cat, mp in (self.codex.get("Units") or {}).items():
                if section_id in mp:
                    zh = mp[section_id]
                    self.current_utype = cat
                    break
        elif kind == "weapon":
            zh = (self.codex.get("WeaponList") or {}).get(section_id, "")
        else:
            zh = (self.codex.get("WarheadList") or {}).get(section_id, "")

        title = f"{section_id}  -  {zh}" if zh else section_id
        self.form_title.setText(title)

        # 优先工程文件中的覆盖，否则 rules 原文
        values: Dict[str, str] = {}
        body_lines = [f"[{section_id}]"]
        src_text = ""
        if self.hotfix_path and self.hotfix_path.is_file():
            src_text = self._read_section_from_file(self.hotfix_path, section_id)
        if not src_text and self.game:
            src_text = self.game.get_section_text(section_id)

        if src_text:
            for line in src_text.splitlines():
                s = line.strip()
                if not s or s.startswith(";"):
                    continue
                if s.startswith("[") and s.endswith("]"):
                    body_lines = [s]
                    continue
                body_lines.append(line.rstrip())
                clean = s.split(";", 1)[0].strip()
                if "=" in clean:
                    k, v = clean.split("=", 1)
                    values[k.strip()] = v.strip()
                    values[k.strip().lower()] = v.strip()

        fields = self._resolve_fields(kind, values)
        self._build_form(fields, values, self.current_utype)
        self.preview.setPlainText("\n".join(body_lines))
        mode = "全部键" if self.expand_all else "经典快调"
        self.statusBar().showMessage(f"[{section_id}] {mode} · {len(fields)} 项", 4000)
        self._switching = False

    def _read_section_from_file(self, path: Path, section_id: str) -> str:
        try:
            if path.is_file():
                text, _enc = read_text(path)
            else:
                text = ""
        except Exception:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return ""
        lines = []
        in_sec = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                name = s[1:-1].strip()
                if in_sec:
                    break
                if name.lower() == section_id.lower():
                    in_sec = True
                    lines.append(line)
                continue
            if in_sec:
                lines.append(line)
        return "\n".join(lines)

    def sync_form_to_code(self):
        if self._switching or not self.current_id:
            return
        lines = [f"[{self.current_id}]"]
        # 保留预览里未出现在表单中的键
        existing: Dict[str, str] = {}
        for line in self.preview.toPlainText().splitlines():
            s = line.strip()
            if not s or s.startswith(";") or (s.startswith("[") and s.endswith("]")):
                continue
            clean = s.split(";", 1)[0].strip()
            if "=" in clean:
                k, v = clean.split("=", 1)
                existing[k.strip()] = v.strip()

        form_keys = set()
        for key, w in self._widgets.items():
            if key.startswith("AEPreset_"):
                continue
            val = self._widget_value(w)
            form_keys.add(key.lower())
            if val != "":
                lines.append(f"{key}={val}")
            elif key in existing:
                # 空值表示用户清空 → 不写
                pass

        for k, v in existing.items():
            if k.lower() not in form_keys:
                lines.append(f"{k}={v}")

        self._switching = True
        self.preview.setPlainText("\n".join(lines))
        self._switching = False

    # ---------- deploy / restore（对齐旧版 TacticalConsole 行为）----------
    def deploy(self):
        """把当前预览写入 hotfix，并瘦身与 rules 相同的键（旧版 clean_ini）。"""
        if not self.current_id:
            QMessageBox.information(self, "提示", "请先选择单位")
            return
        if not self.hotfix_path:
            QMessageBox.information(self, "提示", "请先绑定工程文件（hotfix.ini）")
            return
        if self.mode == "safe" and self.hotfix_path.name.lower() != "hotfix.ini":
            QMessageBox.warning(self, "安全模式", "只能写入 hotfix.ini")
            return

        self.sync_form_to_code()
        body = normalize_section_body(self.current_id, self.preview.toPlainText())
        backup_root = get_app_dir() / "backups"
        try:
            backup_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            backup_root = self._cache_dir() / "backups"
            backup_root.mkdir(parents=True, exist_ok=True)
        try:
            result = save_section_to_file(
                self.hotfix_path, self.current_id, body, backup_root
            )
            if isinstance(result, dict) and not result.get("ok", True):
                QMessageBox.critical(self, "部署失败", result.get("message") or str(result))
                return
            # 部署后瘦身：去掉与 rules 完全一致的键、以及无意义的 AE 默认值
            self._clean_hotfix_file()
            # 重新载入以反映文件真实内容
            self.load_section(self.current_id, self.current_kind)
            self.statusBar().showMessage(
                f"已部署 [{self.current_id}] → {self.hotfix_path.name}", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "部署失败", str(e))

    def restore_default(self):
        """
        安全模式：用 rules 原文覆盖 hotfix 中该 section（旧版「恢复原版」）。
        高级模式：禁止写回，防止误覆盖工程源文件。
        """
        if not self.current_id or not self.game:
            return
        if self.mode != "safe":
            QMessageBox.warning(
                self,
                "功能禁用",
                "当前为高级模式，为防止误覆盖源文件，「恢复默认」已禁用。\n"
                "请切换回安全模式后再用（仅操作 hotfix.ini）。",
            )
            return
        if not self.hotfix_path:
            QMessageBox.information(self, "提示", "请先绑定 hotfix.ini")
            return
        if self.hotfix_path.name.lower() != "hotfix.ini":
            QMessageBox.warning(self, "安全模式", "只能操作 hotfix.ini")
            return

        rules_text = self.game.get_section_text(self.current_id) or ""
        if not rules_text.strip():
            QMessageBox.information(self, "提示", "原版 rules 中不存在该图纸数据")
            return

        # 与旧版一致：补 Image=自身、无 AE 时写一组清零
        lines = []
        for line in rules_text.splitlines():
            s = line.rstrip()
            if s.strip():
                lines.append(s)
        if not lines or not lines[0].strip().startswith("["):
            lines.insert(0, f"[{self.current_id}]")

        keys_lower = set()
        for line in lines[1:]:
            clean = line.split(";", 1)[0].strip()
            if "=" in clean:
                keys_lower.add(clean.split("=", 1)[0].strip().lower())

        body_lines = list(lines)
        if "image" not in keys_lower:
            body_lines.append(f"Image={self.current_id}")
        has_ae = any(k.startswith("attacheffect.") for k in keys_lower)
        if not has_ae:
            body_lines.extend(
                [
                    "AttachEffect.Animation=none",
                    "AttachEffect.Duration=0",
                    "AttachEffect.SpeedMultiplier=1",
                    "AttachEffect.ArmorMultiplier=1",
                    "AttachEffect.FirepowerMultiplier=1",
                    "AttachEffect.ROFMultiplier=1",
                    "AttachEffect.Delay=0",
                    "AttachEffect.InitialDelay=0",
                    "AttachEffect.Cumulative=no",
                ]
            )
        body = "\n".join(body_lines)
        if not body.endswith("\n"):
            body += "\n"

        backup_root = get_app_dir() / "backups"
        try:
            backup_root.mkdir(parents=True, exist_ok=True)
        except Exception:
            backup_root = self._cache_dir() / "backups"
            backup_root.mkdir(parents=True, exist_ok=True)

        try:
            result = save_section_to_file(
                self.hotfix_path, self.current_id, body, backup_root
            )
            if isinstance(result, dict) and not result.get("ok", True):
                QMessageBox.critical(self, "恢复失败", result.get("message") or str(result))
                return
            self._clean_hotfix_file()
            self.load_section(self.current_id, self.current_kind)
            self.statusBar().showMessage(
                f"已恢复 [{self.current_id}] 为 rules 并写回 hotfix", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", str(e))

    def _clean_hotfix_file(self) -> None:
        """对齐旧版 clean_ini_silent：去掉与 rules 相同的键及无意义 AE 默认。"""
        if not self.hotfix_path or not self.hotfix_path.is_file() or not self.game:
            return
        try:
            text, _enc = read_text(self.hotfix_path)
        except Exception:
            return

        out_lines: list[str] = []
        section_id: str | None = None
        section_buf: list[str] = []

        kill_cmds = {
            "attacheffect.animation": {"none", "0", ""},
            "attacheffect.duration": {"0"},
            "attacheffect.speedmultiplier": {"1", "1.0"},
            "attacheffect.armormultiplier": {"1", "1.0"},
            "attacheffect.firepowermultiplier": {"1", "1.0"},
            "attacheffect.rofmultiplier": {"1", "1.0"},
            "attacheffect.delay": {"0"},
            "attacheffect.initialdelay": {"0"},
            "attacheffect.cumulative": {"no", "false", "0"},
        }

        def flush():
            nonlocal section_buf, section_id
            if not section_id or not section_buf:
                section_buf = []
                section_id = None
                return
            base = {}
            if self.game:
                raw = self.game.get_section_text(section_id) or ""
                for line in raw.splitlines():
                    c = line.split(";", 1)[0].strip()
                    if "=" in c and not c.startswith("["):
                        k, v = c.split("=", 1)
                        base[k.strip().lower()] = v.strip().lower()
            kept = [section_buf[0]]
            has_custom = False
            for line in section_buf[1:]:
                clean = line.split(";", 1)[0].strip()
                if "=" in clean:
                    k, v = clean.split("=", 1)
                    kl, vl = k.strip().lower(), v.strip().lower()
                    if kl in base and base[kl] == vl:
                        continue
                    if kl in kill_cmds and vl in kill_cmds[kl]:
                        continue
                    if kl == "image" and vl == section_id.lower():
                        continue
                    has_custom = True
                    kept.append(line if line.endswith("\n") else line + "\n")
                else:
                    if line.strip():
                        kept.append(line if line.endswith("\n") else line + "\n")
            if has_custom:
                out_lines.extend(kept)
                if not str(kept[-1]).endswith("\n"):
                    out_lines.append("\n")
            section_buf = []
            section_id = None

        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                flush()
                section_id = stripped[1:-1].strip()
                section_buf = [line if line.endswith("\n") else line + "\n"]
            else:
                if section_id is not None:
                    section_buf.append(line if line.endswith("\n") else line + "\n")
                else:
                    out_lines.append(line if line.endswith("\n") else line + "\n")
        flush()

        try:
            # 无 BOM UTF-8
            data = "".join(out_lines).encode("utf-8")
            tmp = self.hotfix_path.with_suffix(self.hotfix_path.suffix + ".tmp_clean")
            tmp.write_bytes(data)
            tmp.replace(self.hotfix_path)
        except Exception:
            pass

    def copy_full_code(self):

        QApplication.clipboard().setText(self.preview.toPlainText())
        self.statusBar().showMessage("已复制到剪贴板", 3000)

    def _file_watch(self):
        # 预留：监测 hotfix 外部修改
        pass

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    win = WorkshopWindow()
    win.show()
    sys.exit(app.exec())
