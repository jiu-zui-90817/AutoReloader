import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Frontend" / "editor"))
sys.path.insert(0, str(ROOT))

from core.csf_parser import CSFParser, upsert_label_to_file  # noqa: E402
from core.project import Project  # noqa: E402
from core.save_util import normalize_section_body, save_section_to_file  # noqa: E402
from shared import hotfix_io as shared_hotfix  # noqa: E402


def make_csf_with_wave(label="NAME:E1", text="测试单位", wave=b"e1_voice.wav\x00"):
    label_b = label.encode("ascii")
    val = text.encode("utf-16-le")
    inv = bytes((~b) & 0xFF for b in val)
    wave_val = "声效".encode("utf-16-le")
    wave_inv = bytes((~b) & 0xFF for b in wave_val)
    out = bytearray()
    out += b" FSC" + struct.pack("<IIIII", 3, 1, 2, 0, 0)
    out += b" LBL" + struct.pack("<II", 2, len(label_b)) + label_b
    out += b" RTS" + struct.pack("<I", len(val) // 2) + inv
    out += b"WRTS" + struct.pack("<I", len(wave_val) // 2) + wave_inv
    out += struct.pack("<I", len(wave)) + wave
    return bytes(out)


class RegressionTests(unittest.TestCase):
    def setUp(self):
        base = os.environ.get("AR_TEST_TMP") or None
        self.tmp = Path(tempfile.mkdtemp(prefix="ar_test_", dir=base))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- CSF ----------
    def test_csf_upsert_preserves_wave_pair(self):
        csf = self.tmp / "stringtable_test.csf"
        csf.write_bytes(make_csf_with_wave())
        res = upsert_label_to_file(csf, "", "新名字", backup_root=self.tmp / "backups", section_id="E1")
        self.assertTrue(res.get("ok"), res.get("message"))

        p = CSFParser()
        self.assertTrue(p.load(csf))
        self.assertEqual(p.get("NAME:E1"), "新名字")

        entries = p.pairs.get("name:e1") or []
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1][0], b"WRTS")
        self.assertIn(b"e1_voice.wav", entries[1][2])

    def test_csf_new_label_still_written(self):
        csf = self.tmp / "stringtable_test.csf"
        csf.write_bytes(make_csf_with_wave())
        res = upsert_label_to_file(csf, "", "另一个", backup_root=self.tmp / "backups", section_id="E2")
        self.assertTrue(res.get("ok"))
        p = CSFParser()
        p.load(csf)
        self.assertEqual(p.get("NAME:E2"), "另一个")
        self.assertEqual(p.get("NAME:E1"), "测试单位")  # 原有文本未被误改

    # ---------- normalize ----------
    def test_editor_normalize_header_comment_and_no_blank(self):
        out = normalize_section_body("E1", "[E1] ; header comment\nStrength=1\n")
        self.assertEqual(out, "[E1] ; header comment\nStrength=1\n")
        plain = normalize_section_body("E1", "[E1]\nStrength=1\n")
        self.assertEqual(plain, "[E1]\nStrength=1\n")
        self.assertEqual(normalize_section_body("E1", plain), plain)

    def test_editor_config_survives_update_overwrite(self):
        import json
        import os
        import tempfile as _tempfile

        old_la = os.environ.get("LOCALAPPDATA")
        try:
            with _tempfile.TemporaryDirectory() as la:
                os.environ["LOCALAPPDATA"] = la
                cfg = self.tmp / "config.json"
                cfg.write_text(
                    json.dumps({
                        "active_profile": "X",
                        "profiles": {"X": {"display_name": "X", "rules_files": ["rules.ini"]}},
                        "settings": {"last_game_dir": "BASE"},
                    }), encoding="utf-8"
                )
                p = Project(cfg)
                p.config["settings"]["last_game_dir"] = "USER"
                p.save_config()

                # 模拟覆盖更新：安装目录 config 被默认值替换
                cfg.write_text(json.dumps({
                    "active_profile": "X",
                    "profiles": {"X": {"display_name": "X", "rules_files": ["rules.ini"]}},
                    "settings": {"last_game_dir": "NEW_DEFAULT"},
                }), encoding="utf-8")
                p2 = Project(cfg)
                self.assertEqual(p2.config["settings"]["last_game_dir"], "USER")
        finally:
            if old_la is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_la

    def test_common_flag_dictionary_has_ares_art_and_indexed_keys(self):
        import json
        schema = json.loads(
            (ROOT / "shared" / "schemas" / "common_flags.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(schema), 1000)
        for key in (
            "Foundation", "NewTheater", "WaterImage", "Prerequisite.List1",
            "Bounty.Value", "HealthBar.Hide", "Versus",
        ):
            self.assertIn(key, schema)
            self.assertTrue(
                (schema[key].get("desc_zh") or schema[key].get("desc_en")),
                key,
            )

    def test_save_guard_rejects_empty_and_duplicate_and_wrong_file(self):
        art = self.tmp / "artmo.ini"
        rules_body = "[GACNST]\nName=Allied Construction Yard\nStrength=2500\n"
        art_body = "[GACNST]\nImage=GGCNST\nFoundation=4x4\n"

        art.write_text("[GACNST]\nImage=GGCNST\nFoundation=4x4\n", encoding="utf-8")
        r = save_section_to_file(art, "GACNST", rules_body, self.tmp / "backups")
        self.assertFalse(r.get("ok"))

        art.write_text("[GACNST]\nImage=GGCNST\nFoundation=4x4\n", encoding="utf-8")
        r = save_section_to_file(art, "GACNST", "[GACNST]\n; empty\n", self.tmp / "backups")
        self.assertFalse(r.get("ok"))

        art.write_text("[GACNST]\nImage=GGCNST\n[GACNST]\nName=X\n", encoding="utf-8")
        r = save_section_to_file(art, "GACNST", art_body, self.tmp / "backups")
        self.assertFalse(r.get("ok"))

        art.write_text("[GACNST]\nImage=GGCNST\nFoundation=4x4\n", encoding="utf-8")
        r = save_section_to_file(art, "GACNST", art_body, self.tmp / "backups")
        self.assertTrue(r.get("ok"), r.get("message"))

    def test_shared_normalize_header_comment_and_no_blank(self):
        out = shared_hotfix.normalize_section_body("E1", "[E1] ; header comment\nStrength=1\n")
        self.assertEqual(out, "[E1] ; header comment\nStrength=1\n")
        plain = shared_hotfix.normalize_section_body("E1", "[E1]\n\nStrength=1\n")
        self.assertEqual(plain, "[E1]\nStrength=1\n")

    # ---------- project save ----------
    def _make_project(self):
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / "rules.ini").write_text("[#include]\n1=a.ini\n2=b.ini\n", encoding="utf-8")
        (proj / "a.ini").write_text("[E1]\nStrength=100\nSpeed=5\n", encoding="utf-8")
        (proj / "b.ini").write_text("[E1]\nStrength=150\n", encoding="utf-8")
        cfg = proj / "config.json"
        cfg.write_text(
            '{"active_profile":"X","profiles":{"X":{"display_name":"X","rules_files":["rules.ini"],'
            '"art_files":[],"ai_files":[],"csf_files":[],"type_lists":[]}}}',
            encoding="utf-8",
        )
        p = Project(cfg)
        self.assertTrue(p.open_directory(proj))
        return proj, p

    def test_full_save_keeps_shadowed_override(self):
        proj, p = self._make_project()
        body = p.get_section_text("E1")
        res = p.save_section_text("E1", body, confirmed=True)
        self.assertTrue(res.get("ok"), res.get("message"))
        a_text = (proj / "a.ini").read_text(encoding="utf-8")
        self.assertIn("Strength=100", a_text)  # 被 b.ini 覆盖的旧值不能被删
        self.assertIn("Speed=5", a_text)

    def test_full_save_deletes_key_from_all_sources(self):
        proj, p = self._make_project()
        body = p.get_section_text("E1")
        body = body.replace("Strength=150\n", "")
        res = p.save_section_text("E1", body, confirmed=True)
        self.assertTrue(res.get("ok"), res.get("message"))
        for name in ("a.ini", "b.ini"):
            self.assertNotIn("Strength", (proj / name).read_text(encoding="utf-8"), name)

    def test_full_save_deletes_only_target_key(self):
        proj, p = self._make_project()
        body = p.get_section_text("E1").replace("Speed=5", "")
        res = p.save_section_text("E1", body, confirmed=True)
        self.assertTrue(res.get("ok"), res.get("message"))
        a_text = (proj / "a.ini").read_text(encoding="utf-8")
        b_text = (proj / "b.ini").read_text(encoding="utf-8")
        self.assertNotIn("Speed", a_text)
        self.assertIn("Strength=100", a_text)
        self.assertIn("Strength=150", b_text)

    def test_multi_file_change_still_splits(self):
        proj, p = self._make_project()
        body = p.get_section_text("E1").replace("Strength=150", "Strength=250")
        res = p.save_section_text("E1", body, confirmed=True)
        self.assertTrue(res.get("ok"), res.get("message"))
        self.assertIn("Strength=100", (proj / "a.ini").read_text(encoding="utf-8"))
        self.assertIn("Strength=250", (proj / "b.ini").read_text(encoding="utf-8"))

    # ---------- include ----------
    def test_nested_include_relative_to_including_file(self):
        proj = self.tmp / "incproj"
        (proj / "sub").mkdir(parents=True)
        (proj / "rules.ini").write_text("[#include]\n1=sub/inc.ini\n", encoding="utf-8")
        (proj / "sub" / "inc.ini").write_text("[#include]\n1=deeper.ini\n", encoding="utf-8")
        (proj / "sub" / "deeper.ini").write_text("[E1]\nStrength=1\n", encoding="utf-8")
        cfg = proj / "config.json"
        cfg.write_text(
            '{"active_profile":"X","profiles":{"X":{"display_name":"X","rules_files":["rules.ini"],'
            '"art_files":[],"ai_files":[],"csf_files":[],"type_lists":[]}}}',
            encoding="utf-8",
        )
        p = Project(cfg)
        self.assertTrue(p.open_directory(proj))
        self.assertIsNotNone(p.get_section("E1"))

    # ---------- shared ----------
    def test_shared_hotfix_appends_missing_section(self):
        hot = self.tmp / "hotfix.ini"
        hot.write_text("[OTHER]\nStrength=1\n", encoding="utf-8")
        res = shared_hotfix.save_section_to_file(
            hot, "NEWUNIT", "[NEWUNIT]\nStrength=9\n", backup_root=self.tmp / "backups"
        )
        self.assertTrue(res.get("ok"), res.get("message"))
        self.assertIn("[NEWUNIT]", hot.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
