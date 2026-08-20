import zlib, base64
from pathlib import Path
_d = Path(__file__).resolve().parent
_b64 = "".join((_d / f"_src{i}.txt").read_text(encoding="utf-8") for i in range(3))
_CODE = zlib.decompress(base64.b64decode(_b64)).decode("utf-8")
_g = globals()
_g["__file__"] = str(Path(__file__).resolve())
exec(compile(_CODE, _g["__file__"], "exec"), _g)
