"""战斗对照：原版(6731)和新服务端(6732)各跑同一串指令，比 A 的回包（只比原版实测过的部分：遭遇 / 小实体 / 无此NPC / D4 / D8 / E5）。

    python tools/battle_compare.py

D1 里的随机数（原版 8–93，新服务端 1–100）不比较；D4 的回包原版带每人不同的异或密钥，新服务端原样回显，所以这里不发 D4。
"""

from __future__ import annotations

import difflib
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

JY = 8617293
Z19 = "00" * 19


def le(n):
    return struct.pack("<I", n).hex()


STEPS = [
    (0x30, le(100038166) + Z19),
    (0xE5, le(JY) + "01"),
    (0x30, le(38166) + Z19),
    (0x30, le(100000001) + Z19),
    (0x30, le(100138166) + Z19),
    (0xD8, "00" * 13),
    (0x30, le(100038166) + Z19),
    (0xD8, "00" * 13),
    (0xE5, le(JY) + "01"),
    (0xD8, "00" * 13),
    (0xE5, le(JY) + "01"),
    (0xE6, le(JY) + "01"),
    (0x30, ""),
    (0x30, "01"),
]


def run(port):
    time.sleep(2)
    c = Client("A", "127.0.0.1", port, JY, None)
    assert c.login()
    c.drain(1.0)
    out = []
    for op, hx in STEPS:
        out.append(f"== 0x{op:02x} {hx}")
        c.send(op, bytes.fromhex(hx))
        for f in c.drain(0.7):
            if f.opcode in (0x33, 0x08, 0x02, 0x6D, 0x3D, 0x31) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            p = f.payload
            if f.opcode == 0xD1:
                p = p[:16] + b"??" + p[18:]
            out.append(f"    <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {p.hex(' ')}")
    c.sock.close()
    return out


def main():
    a = run(6731)
    time.sleep(2)
    b = run(6732)
    print(f"original {len(a)} lines, new {len(b)} lines")
    if a == b:
        print("identical")
        return 0
    for l in difflib.unified_diff(a, b, "original", "new", lineterm="", n=1):
        print("  ", l[:200])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
