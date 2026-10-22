"""移动规则探针：对原版服务端发一串 0x06，看哪些被接受（收到 S2C 0x06 回显）。

    python tools/move_probe.py --jyid 8617293 --start 524,418 --steps 9,0 10,0 11,0 0,10 7,7 --trail 000000

--start 是服务端当前认为的位置（登录包里 0x08 帧给出，之后每次被接受的移动都会更新）。
每个 step 是 dx,dy；被接受后位置前进。--trail 是 3 字节尾部（十六进制）。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--start", help="x,y；默认用登录序列里 0x08 给的位置")
    ap.add_argument("--steps", nargs="+", required=True, help="dx,dy ...")
    ap.add_argument("--trail", default="000000")
    ap.add_argument("--raw", action="append", default=[], help="额外原样发送的 6 号指令载荷(十六进制)")
    args = ap.parse_args()

    c = Client("A", args.host, args.port, args.jyid, None)
    if not c.login():
        print("login failed")
        return 1
    c.drain(0.5)
    pos = c.position()
    print("server says position (map,x,y):", pos)
    x, y = (int(v) for v in args.start.split(",")) if args.start else pos[1:]
    trail = bytes.fromhex(args.trail)
    for st in args.steps:
        dx, dy = (int(v) for v in st.split(","))
        nx, ny = x + dx, y + dy
        c.send(0x06, struct.pack("<HHHH", x, y, nx, ny) + trail)
        got = [f for f in c.drain(0.8) if f.opcode == 0x06]
        ok = bool(got)
        print(f"({x},{y}) -> ({nx},{ny}) d=({dx},{dy}) {'ACCEPT' if ok else 'reject'}" + (f"  {got[0].payload.hex(' ')}" if ok else ""))
        if ok:
            x, y = nx, ny
    for r in args.raw:
        c.send(0x06, bytes.fromhex(r.replace(" ", "")))
        print("raw", r, [f"{f.opcode:02x}:{f.payload.hex(' ')}" for f in c.drain(0.8)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
