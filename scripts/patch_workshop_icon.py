"""CI helper: patch workshop app.py icon paths after restoring from a full commit."""
from pathlib import Path

p = Path("Frontend/workshop/app.py")
t = p.read_text(encoding="utf-8")

old = """        try:
            from pathlib import Path as _Path
            for cand in (
                _Path(__file__).resolve().parents[2] / "assets" / "workshop.ico",
                _Path(__file__).resolve().parent / "assets" / "workshop.ico",
                _Path.cwd() / "assets" / "workshop.ico",
            ):
                if cand.is_file():
                    self.setWindowIcon(QIcon(str(cand)))
                    break
        except Exception:
            pass"""

new = """        try:
            for cand in (
                get_app_dir() / "workshop.ico",
                get_app_dir() / "editor.ico",
                get_app_dir() / "assets" / "workshop.ico",
                get_bundle_dir() / "workshop.ico",
                get_repo_root() / "assets" / "workshop.ico",
                Path(__file__).resolve().parents[2] / "assets" / "workshop.ico",
                Path(__file__).resolve().parent / "assets" / "workshop.ico",
                Path.cwd() / "assets" / "workshop.ico",
            ):
                if cand.is_file():
                    self.setWindowIcon(QIcon(str(cand)))
                    break
        except Exception:
            pass"""

if old in t:
    t = t.replace(old, new, 1)
    print("patched window icon block")
else:
    print("window icon block already patched or missing")

ro = "def run():\n    app = QApplication.instance() or QApplication(sys.argv)"
rn = """def run():
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        for cand in (
            get_app_dir() / "workshop.ico",
            get_app_dir() / "editor.ico",
            get_app_dir() / "assets" / "workshop.ico",
            get_bundle_dir() / "workshop.ico",
            get_repo_root() / "assets" / "workshop.ico",
        ):
            if cand.is_file():
                app.setWindowIcon(QIcon(str(cand)))
                break
    except Exception:
        pass"""

if ro in t and 'get_app_dir() / "workshop.ico"' not in t[t.find("def run()") : t.find("def run()") + 500]:
    t = t.replace(ro, rn, 1)
    print("patched run() icon")
else:
    print("run() icon already patched or pattern missing")

p.write_text(t, encoding="utf-8")
print("final size", p.stat().st_size)
