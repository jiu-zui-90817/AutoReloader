import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Frontend" / "editor"))
sys.path.insert(0, str(ROOT / "Frontend" / "workshop"))

try:
    from PySide6.QtWidgets import QApplication, QMessageBox

    HAS_QT = True
except Exception:  # pragma: no cover
    HAS_QT = False


def _install_quiet_dialogs():
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
    QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)


@unittest.skipUnless(HAS_QT, "PySide6 not installed")
class UIRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_quiet_dialogs()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        base = os.environ.get("AR_TEST_TMP") or None
        self.tmp = Path(tempfile.mkdtemp(prefix="ar_ui_", dir=base))
        self._make_project()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_project(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / "rules.ini").write_text(
            "[InfantryTypes]\n0=E1\n1=E2\n\n[E1]\nStrength=100\n\n[E2]\nStrength=50\n",
            encoding="utf-8",
        )
        (proj / "art.ini").write_text("[E1]\nImage=E1\n", encoding="utf-8")
        cfg = self.tmp / "config.json"
        cfg.write_text(
            '{"active_profile":"X","profiles":{"X":{"display_name":"X",'
            '"rules_files":["rules.ini"],"art_files":["art.ini"],"ai_files":[],'
            '"csf_files":[],"type_lists":["InfantryTypes"]}},"settings":{}}',
            encoding="utf-8",
        )
        self.proj = proj
        self.cfg = cfg

    def _window(self):
        from core.project import Project
        from ui.main_window import MainWindow

        p = Project(self.cfg)
        w = MainWindow(p)
        w.open_project(str(self.proj))
        w._confirm_save_plan = lambda *a, **k: True
        w._lint_before_save = lambda *a, **k: True
        w._lint_before_save_all = lambda *a, **k: True
        return w

    def test_saved_section_is_not_dirty_after_reopen(self):
        w = self._window()
        try:
            w.open_section_tab("E1")
            w.code.setPlainText("[E1]\nStrength=123\n")
            self.assertIn("E1", w._dirty_keys)
            w.save_current()
            self.assertNotIn("E1", w._dirty_keys)
            w.show_section("E1")
            self.assertNotIn("E1", w._dirty_keys)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_save_all_writes_pending_new_unit(self):
        w = self._window()
        try:
            body = "[NEW1]\nStrength=10\n"
            new_path = self.proj / "units.ini"
            w.project.inject_section_memory(
                "NEW1", body, source_path=new_path, type_list="InfantryTypes"
            )
            w._mem_sections["NEW1"] = body
            w._pending_new["NEW1"] = {
                "id": "NEW1", "path": str(new_path), "type_list": "InfantryTypes",
                "also_register": False, "register_path": "", "is_new": True,
                "kind": "new", "write_csf": False, "csf_text": "",
            }
            w._dirty_keys.add("NEW1")
            w.open_section_tab("NEW1")
            w.save_all()
            self.assertTrue(new_path.is_file())
            self.assertIn("[NEW1]", new_path.read_text(encoding="utf-8"))
            self.assertNotIn("NEW1", w._dirty_keys)
            self.assertNotIn("NEW1", w._pending_new)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_discard_clears_draft(self):
        w = self._window()
        try:
            w.open_section_tab("E1")
            w.code.setPlainText("[E1]\nStrength=777\n")
            self.assertIn("E1", w._dirty_keys)
            w._discard_all_dirty()
            self.assertNotIn("E1", w._dirty_keys)
            self.assertNotIn("E1", w._mem_sections)
            w.show_section("E1")
            self.assertIn("Strength=100", w.code.toPlainText())
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_save_all_keeps_dirty_when_failed(self):
        w = self._window()
        try:
            ghost = "[GHOST]\nA=1\n"
            w._mem_sections["GHOST"] = ghost
            w._dirty_keys.add("GHOST")
            w.current_section_id = "GHOST"
            w.current_prefer = ""
            w.code.setPlainText(ghost)
            w.save_all()
            self.assertIn("GHOST", w._dirty_keys)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_delete_section_does_not_add_bom(self):
        rules = self.proj / "rules.ini"
        rules.write_bytes(b"\xef\xbb\xbf" + rules.read_text(encoding="utf-8").encode("utf-8"))
        w = self._window()
        try:
            w._confirm_danger = lambda *a, **k: True
            w.open_section_tab("E2")
            w.delete_current_section()
            data = rules.read_bytes()
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"[E2]", data)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_save_all_clone_art_written_once(self):
        from core.ini_parser import INISection

        w = self._window()
        try:
            sid = "z1"  # 小写且排在 art:: 之后，用于验证 art 不会被提前重复写
            rules_body = f"[{sid}]\nStrength=10\n"
            art_body = f"[{sid}]\nImage={sid}\n"
            units = self.proj / "units.ini"
            art_file = self.proj / "art.ini"

            sec = INISection(sid)
            sec.source_file = str(art_file.resolve())
            sec.set("Image", sid)
            w.project.art.sections[sid] = sec
            w.project.art.section_order.append(sid)

            w.project.inject_section_memory(
                sid, rules_body, source_path=units, type_list="InfantryTypes"
            )
            w._mem_sections[sid] = rules_body
            w._mem_sections[f"art::{sid}"] = art_body
            w._pending_new[sid] = {
                "id": sid, "path": str(units), "type_list": "InfantryTypes",
                "also_register": False, "register_path": "", "is_new": True,
                "kind": "clone", "write_csf": False, "csf_text": "",
                "art_path": str(art_file), "art_body": art_body,
            }
            w._dirty_keys.add(sid)
            w.open_section_tab(sid)
            w.save_all()

            art_text = art_file.read_text(encoding="utf-8")
            self.assertEqual(art_text.count(f"[{sid}]"), 1)
            self.assertTrue(units.is_file())
            self.assertEqual(units.read_text(encoding="utf-8").count(f"[{sid}]"), 1)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_tool_deploy_hotfix_appends_missing_section(self):
        w = self._window()
        try:
            hot = self.tmp / "hotfix.ini"
            hot.write_text("[OTHER]\nStrength=1\n", encoding="utf-8")
            w._hotfix_path = lambda: hot
            w.current_section_id = "E1"
            w.current_prefer = ""
            w.code.setPlainText("[E1]\nStrength=999\n")
            w._tool_deploy_hotfix()
            text = hot.read_text(encoding="utf-8")
            self.assertIn("[E1]", text)
            self.assertIn("Strength=999", text)
        finally:
            w._dirty_keys.clear()
            w.deleteLater()

    def test_workshop_clean_ignores_non_hotfix_file(self):
        import app as wsapp

        target = self.tmp / "advanced.ini"
        original = "[E1]\nStrength=150\n\n[E2]\nCost=50\n"
        target.write_text(original, encoding="utf-8")

        class FakeGame:
            def get_section_text(self, sid):
                return {
                    "E1": "[E1]\nStrength=100",
                    "E2": "[E2]\nCost=50",
                }.get(sid, "")

        w = wsapp.WorkshopWindow()
        try:
            w.game = FakeGame()
            w.hotfix_path = target
            w.mode = "advanced"
            w._clean_hotfix_file()
            self.assertEqual(target.read_text(encoding="utf-8"), original)
        finally:
            w.deleteLater()


if __name__ == "__main__":
    unittest.main()
