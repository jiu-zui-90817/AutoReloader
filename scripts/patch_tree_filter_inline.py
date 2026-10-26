"""对 Frontend/editor/ui/main_window.py 就地修补对象树过滤逻辑。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "Frontend" / "editor" / "ui" / "main_window.py"

OLD_MATCH = '''    def _tree_id_matches(self, uid: str, filt: str) -> bool:
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
'''

NEW_MATCH = '''    def _tree_id_matches(self, uid: str, filt: str) -> bool:
        """过滤匹配：ID + 显示名。过滤时按需解析显示名（不必先展开树）。"""
        if not filt:
            return True
        if filt in uid.lower():
            return True
        cached = self._display_cache.get(uid)
        if cached is None:
            try:
                cached = self._disp(uid)
            except Exception:
                cached = uid
        if cached and filt in str(cached).lower():
            return True
        return False

    def _should_fill_children(self, count: int, filt: str) -> bool:
        """无过滤：大组懒加载；有过滤：命中项直接填出。"""
        if filt:
            return True
        return count <= self._tree_lazy_threshold
'''

OLD_EXP = '''    def on_tree_expanded(self, item: QTreeWidgetItem):
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
'''

NEW_EXP = '''    def on_tree_expanded(self, item: QTreeWidgetItem):
        ids = item.data(0, Qt.UserRole + 1)
        if not ids:
            return
        need = item.childCount() == 0
        if not need and item.childCount() == 1 and item.child(0).data(0, Qt.UserRole) is None:
            need = True
        if need:
            self.tree.setUpdatesEnabled(False)
            try:
                self._fill_tree_children(
                    item,
                    ids,
                    prefer=item.data(0, Qt.UserRole + 2) or "",
                    group=item.data(0, Qt.UserRole + 3) or "",
                )
            finally:
                self.tree.setUpdatesEnabled(True)
'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "过滤时按需解析显示名" in text:
        print("already patched")
        return 0
    if OLD_MATCH not in text:
        raise SystemExit("match block not found — wrong base file?")
    text = text.replace(OLD_MATCH, NEW_MATCH, 1)
    if OLD_EXP not in text:
        raise SystemExit("expand block not found")
    text = text.replace(OLD_EXP, NEW_EXP, 1)
    TARGET.write_text(text, encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
