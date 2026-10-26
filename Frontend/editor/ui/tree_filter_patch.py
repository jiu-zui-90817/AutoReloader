"""对象树过滤补丁：未展开也能按中文名命中，过滤结果直接填子节点。"""
from __future__ import annotations


def apply_tree_filter_patch(MainWindow) -> None:
    def _tree_id_matches(self, uid: str, filt: str) -> bool:
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
        if filt:
            return True
        return count <= getattr(self, "_tree_lazy_threshold", 40)

    def on_tree_expanded(self, item) -> None:
        from PySide6.QtCore import Qt

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

    MainWindow._tree_id_matches = _tree_id_matches  # type: ignore[method-assign]
    MainWindow._should_fill_children = _should_fill_children  # type: ignore[method-assign]
    MainWindow.on_tree_expanded = on_tree_expanded  # type: ignore[method-assign]
