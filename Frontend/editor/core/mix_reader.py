"""Read-only RA2 / YR MIX archive reader.

Supports unencrypted and RSA/Blowfish encrypted MIX archives (XCC format).
No write support: extracted files are temporary and never written back.
"""

from __future__ import annotations

import base64
import mmap
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


class MixError(Exception):
    pass


PUBKEY_STR = "AihRvNoIbTn85FZRYNZRcT+i6KpU+maCsEqr3Q5q+LDB5tH7Tz2qQ38V"
PUBLIC_EXPONENT = 0x10001
MIX_DB_ID = 0x366E051F
MIX_DB_FILENAME = "local mix database.dat"
ENCRYPTED_FLAG = 0x00020000


@dataclass
class MixEntry:
    id: int
    offset: int
    size: int
    name: str = ""

    @property
    def display_name(self) -> str:
        return self.name or f"ID_{self.id:08X}.bin"

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.lower() if self.name else ""


def _obfuscate_filename(filename: str) -> bytes:
    raw = filename.encode("ascii", errors="ignore")
    length = len(raw)
    salt = length & 0xFFFFFFFC
    out = bytearray(filename.upper().encode("ascii", errors="ignore"))
    if length & 3:
        out.append(length - salt)
        for _ in range(3 - (length & 3)):
            out.append(out[salt] if salt < len(out) else ord("A"))
    return bytes(out)


def ra2_crc(filename: str) -> int:
    return zlib.crc32(_obfuscate_filename(filename)) & 0xFFFFFFFF


def _rsa_blowfish_key(key_source: bytes) -> bytes:
    if len(key_source) < 80:
        raise MixError("encrypted MIX key block is too short")
    try:
        from Crypto.Cipher import Blowfish  # noqa: F401
    except Exception as exc:  # pragma: no cover - dependency check
        raise MixError(
            "读取加密 MIX 需要 pycryptodome；请先安装 requirements.txt 中的 pycryptodome"
        ) from exc

    raw = base64.b64decode(PUBKEY_STR + "=" * (-len(PUBKEY_STR) % 4))
    if len(raw) >= 2 and raw[0] == 0x02:
        mod_len = raw[1]
        modulus = int.from_bytes(raw[2:2 + mod_len], "big")
    else:
        modulus = int.from_bytes(raw, "big")
    if not modulus:
        raise MixError("invalid MIX RSA modulus")

    out_a = 40
    chunk_in = 40
    if out_a <= 0:
        raise MixError("invalid MIX RSA key size")
    out = bytearray()
    offset = 0
    while offset + chunk_in <= len(key_source) and len(out) < 56:
        chunk = int.from_bytes(key_source[offset:offset + chunk_in], "little")
        value = pow(chunk, PUBLIC_EXPONENT, modulus)
        out.extend(value.to_bytes(out_a, "little", signed=False)[:out_a])
        offset += chunk_in
    if len(out) < 56:
        raise MixError("MIX Blowfish key derivation failed")
    return bytes(out[:56])


def _decrypt_header(data, key: bytes) -> Tuple[int, int, bytes]:
    try:
        from Crypto.Cipher import Blowfish
    except Exception as exc:  # pragma: no cover
        raise MixError("读取加密 MIX 需要 pycryptodome") from exc

    cipher = Blowfish.new(key, Blowfish.MODE_ECB)
    enc = data[84:84 + 8]
    if len(enc) < 8:
        raise MixError("encrypted MIX header truncated")
    first = cipher.decrypt(enc)
    count = struct.unpack_from("<H", first, 0)[0]
    total = 6 + count * 12
    blocks = (total + 7) // 8
    enc_len = blocks * 8
    encrypted = bytes(data[84:84 + enc_len])
    if len(encrypted) < enc_len:
        raise MixError("encrypted MIX index truncated")
    decrypted = cipher.decrypt(encrypted)
    data_size = struct.unpack_from("<I", decrypted, 2)[0]
    return count, data_size, decrypted[:total]


def _collect_game_names(root: Optional[Path]) -> set[str]:
    names = {
        "rules.ini", "rulesmd.ini", "art.ini", "artmd.ini", "ai.ini", "aimd.ini",
        "ra2.csf", "ra2md.csf", "stringtable.csf", "stringtablemd.csf",
        "local mix database.dat", "global mix database.dat",
    }
    if not root or not root.is_dir():
        return names
    try:
        for path in root.rglob("*"):
            if path.is_file():
                names.add(path.name)
                try:
                    names.add(str(path.relative_to(root)).replace("\\", "/"))
                except Exception:
                    pass
    except Exception:
        pass
    return names


class MixArchive:
    def __init__(self, path: Path, data, entries: List[MixEntry], names: Dict[int, str], file_handle=None):
        self.path = Path(path)
        self._data = data
        self._file = file_handle
        self.entries = entries
        self._names = names

    @classmethod
    def load(cls, path: Path, game_root: Optional[Path] = None) -> "MixArchive":
        path = Path(path)
        try:
            fh = open(path, "rb")
            data = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        except Exception as exc:
            raise MixError(f"无法打开 MIX: {exc}") from exc

        # Keep the file handle alive for the mmap lifetime.
        fh = fh  # noqa: F841
        try:
            if len(data) < 6:
                raise MixError("MIX 文件过短")
            first = struct.unpack_from("<H", data, 0)[0]
            if first != 0:
                count = first
                entries_at = 6
                data_start = 6 + count * 12
                encrypted = False
            else:
                flags = struct.unpack_from("<I", data, 0)[0]
                count = struct.unpack_from("<H", data, 4)[0]
                entries_at = 10
                encrypted = bool(flags & ENCRYPTED_FLAG)
                if encrypted:
                    raise MixError(
                        "检测到加密 MIX。当前版本只支持未加密 MIX 的只读浏览；"
                        "可先用 XCC Mixer 解包后再打开。"
                    )
                else:
                    index = None
                    data_start = 10 + count * 12
            if encrypted:
                raw_index = index
            else:
                raw_index = data[entries_at:entries_at + count * 12]
            if len(raw_index) < count * 12:
                raise MixError("MIX 索引不完整")
            entries: List[MixEntry] = []
            for i in range(count):
                eid, offset, size = struct.unpack_from("<III", raw_index, i * 12)
                absolute = data_start + offset
                if size == 0 or absolute >= len(data):
                    continue
                if absolute + size > len(data):
                    size = max(0, len(data) - absolute)
                entries.append(MixEntry(eid, absolute, size))

            names: Dict[int, str] = {}
            for name in _collect_game_names(game_root):
                names[ra2_crc(name)] = name

            # A local mix database inside the archive maps many more IDs.
            db_entry = next((e for e in entries if e.id == MIX_DB_ID), None)
            if db_entry:
                try:
                    strings = bytes(data[db_entry.offset:db_entry.offset + db_entry.size]).split(b"\x00")
                    for raw in strings:
                        text = raw.decode("latin-1", errors="ignore").strip()
                        if text and ("." in text) and len(text) < 260:
                            names.setdefault(ra2_crc(text), text)
                except Exception:
                    pass

            for entry in entries:
                entry.name = names.get(entry.id, "")
            return cls(path, data, entries, names, fh)
        except Exception:
            data.close()
            fh.close()
            raise

    def close(self) -> None:
        try:
            self._data.close()
        except Exception:
            pass
        try:
            if self._file is not None:
                self._file.close()
        except Exception:
            pass

    def extract(self, entry: MixEntry) -> bytes:
        return bytes(self._data[entry.offset:entry.offset + entry.size])

    def read_head(self, entry: MixEntry, size: int = 4096) -> bytes:
        end = entry.offset + min(max(0, int(size)), entry.size)
        return bytes(self._data[entry.offset:end])


    def file_name(self, entry: MixEntry) -> str:
        return entry.name or f"ID_{entry.id:08X}.bin"


def guess_entry_kind(data: bytes) -> str:
    """Best-effort text/CSF/INI detection for the browser preview."""
    if data[:4] == b" FSC":
        return "csf"
    head = data[:4096].lstrip(b"\xef\xbb\xbf\r\n\t ")
    if head.startswith(b"[") or b"\n[" in head or b"\r\n[" in head:
        return "ini"
    return "bin"
