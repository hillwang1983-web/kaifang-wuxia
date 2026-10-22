"""按虚拟地址直接从 服务端.exe 文件读字节（不经过 REA），免得每次读几个常量字符串都吃一大段证据样板。

    python tools/va_bytes.py 0x9d62a4 0x9d6984 [--len 24]

每个地址打印：十六进制 + 到第一个 00 为止的 GBK 文本。
"""

import argparse
import struct
from pathlib import Path

EXE = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端\服务端.exe")


def load_sections(data: bytes):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    secs = []
    off = pe + 24 + opt_size
    for i in range(nsec):
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, off + 8 + 40 * i)  # 节名占 8 字节
        secs.append((base + va, max(vsize, rsize), raw, rsize))
    return secs


def read_va(data: bytes, secs, va: int, n: int) -> bytes:
    for start, size, raw, rsize in secs:
        if start <= va < start + size:
            o = raw + (va - start)
            return data[o : o + n]
    return b""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("addr", nargs="+")
    ap.add_argument("--len", type=int, default=24)
    a = ap.parse_args()
    data = EXE.read_bytes()
    secs = load_sections(data)
    for s in a.addr:
        va = int(s, 16)
        b = read_va(data, secs, va, a.len)
        t = b.split(b"\0")[0].decode("gbk", errors="replace")
        print(f"{va:#x}: {b.hex(' ')}  | {t!r}")


if __name__ == "__main__":
    main()
