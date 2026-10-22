"""使用物品探针：登录一个号，发 C2S 0x0B（物品ID(LE32) + 后缀），打印服务端所有回包。

    python tools/use_probe.py --jyid 9999001 31011:c8 31170:c801 28178:

每个参数是 `物品ID:后缀十六进制`。每条之间等 --wait 秒。
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
    ap.add_argument("--wait", type=float, default=1.0)
    ap.add_argument("--password")
    ap.add_argument("uses", nargs="+")
    args = ap.parse_args()
    c = Client("A", args.host, args.port, args.jyid, args.password)
    if not c.login():
        print("login failed")
        return 1
    c.drain(0.3)
    for u in args.uses:
        iid, _, suffix = u.partition(":")
        payload = struct.pack("<I", int(iid)) + bytes.fromhex(suffix)
        c.send(0x0B, payload)
        print(f"== use {iid} suffix {suffix or '-'}  ({payload.hex(' ')})")
        for f in c.drain(args.wait):
            txt = ""
            if f.opcode in (0x1A, 0x14):
                body = f.payload[1:] if f.opcode == 0x14 else f.payload
                txt = "  | " + body.decode("big5", errors="replace")
            print(f"    <- 0x{f.opcode:02x}{' wide' if f.wide else ''} {f.payload.hex(' ')}{txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
