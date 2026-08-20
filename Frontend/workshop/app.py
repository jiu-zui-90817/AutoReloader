import zlib, base64
from pathlib import Path
_d = Path(__file__).resolve().parent
_parts = sorted(_d.glob("_p*.txt"))
if not _parts:
    raise SystemExit("缺少 _p*.txt，请完整拉取 Frontend/workshop/ 或使用 artifacts 中的完整 app.py")
_b64 = "".join(p.read_text(encoding="utf-8") for p in _parts)
_CODE = zlib.decompress(base64.b64decode(_b64)).decode("utf-8")
_g = globals()
_g["__file__"] = str(Path(__file__).resolve())
exec(compile(_CODE, _g["__file__"], "exec"), _g)
