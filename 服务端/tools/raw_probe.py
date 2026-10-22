"""通用探针：登录一个号，依次发任意 C2S 包，打印服务端所有回包（可同时登录第二个号观察广播）。

    python tools/raw_probe.py --jyid 8617293 --watch 1234567 0D:7a6d0000c801010000 0D:...

每个参数是 `操作码十六进制:载荷十六进制`。--watch 指定的号只登录并旁观，打印它收到的帧。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def show(tag: str, frames) -> None:
    for f in frames:
        txt = ""
        if f.opcode in (0x1A, 0x14, 0x04):
            body = f.payload[1:] if f.opcode in (0x14, 0x04) else f.payload
            txt = "  | " + body.decode("big5", errors="replace")
        print(f"    {tag} <- 0x{f.opcode:02x}{' wide' if f.wide else ''} {f.payload.hex(' ')}{txt}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password")
    ap.add_argument("--watch", type=int)
    ap.add_argument("--watch-password")
    ap.add_argument("--wait", type=float, default=1.2)
    ap.add_argument("cmds", nargs="+")
    args = ap.parse_args()
    c = Client("A", args.host, args.port, args.jyid, args.password)
    if not c.login():
        print("login failed")
        return 1
    c.drain(0.5)
    w = None
    if args.watch:
        w = Client("W", args.host, args.port, args.watch, args.watch_password)
        if not w.login():
            print("watch login failed")
            return 1
        w.drain(0.5)
        c.drain(0.5)
    for cmd in args.cmds:
        who = "A"
        if cmd[:2] in ("A:", "W:"):  # 前缀 W: 让旁观号发包
            who, cmd = cmd[0], cmd[2:]
        op, _, hx = cmd.partition(":")
        if "{" in hx:  # 如 0D:{28026}c801000000，{N} 展开为 LE32
            import re
            import struct

            hx = re.sub(r"\{(\d+)\}", lambda m: struct.pack("<I", int(m.group(1))).hex(), hx)
        payload = bytes.fromhex(hx.replace(" ", ""))
        sender = w if who == "W" else c
        sender.send(int(op, 16), payload)
        print(f"== {who} sends 0x{int(op, 16):02x} {payload.hex(' ')}")
        show("A", c.drain(args.wait))
        if w:
            show("W", w.drain(0.3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
