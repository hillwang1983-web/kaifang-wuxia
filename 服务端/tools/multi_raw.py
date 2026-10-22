"""多客户端原始指令探针：同时登录并进入世界若干号，按顺序发任意 C2S 包，打印每一方收到的帧。

    python tools/multi_raw.py --port 6731 --who A=8617293 W=1234567 C=123456 -- "A:26:" "A:2C:{1234567}" "W:2D:01{8617293}"

每个 cmd 是 `谁:操作码:载荷`，载荷里 `{N}` 展开成 LE32；`谁` 是 --who 里的名字。--no-enter 名字 让某人只登录不进入世界。
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def show(tag, frames):
    for f in frames:
        if f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
            continue
        txt = ""
        if f.opcode in (0x1A, 0x14):
            txt = "  | " + f.payload[1:].decode("big5", errors="replace")
        print(f"    {tag} <- 0x{f.opcode:02x}{' wide' if f.wide else ''} {f.payload.hex(' ')}{txt}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--who", nargs="+", required=True, help="名字=jyid")
    ap.add_argument("--wait", type=float, default=1.0)
    ap.add_argument("cmds", nargs="*")
    a = ap.parse_args()
    clients: dict[str, Client] = {}
    for spec in a.who:
        name, _, jy = spec.partition("=")
        c = Client(name, "127.0.0.1", a.port, int(jy), None)
        if not c.login():
            print("login failed for", name)
            return 1
        clients[name] = c
    for c in clients.values():
        c.drain(1.5)
    for cmd in a.cmds:
        who, op, hx = cmd.split(":", 2)
        hx = re.sub(r"\{(\d+)\}", lambda m: struct.pack("<I", int(m.group(1))).hex(), hx)
        if op == "close":  # 伪操作：断开这个客户端
            clients[who].sock.close()
            print(f"== {who} disconnects")
            del clients[who]
            for name, c in clients.items():
                show(name, c.drain(a.wait))
            continue
        payload = bytes.fromhex(hx.replace(" ", ""))
        clients[who].send(int(op, 16), payload)
        print(f"== {who} sends 0x{int(op, 16):02x} {payload.hex(' ')}")
        for name, c in clients.items():
            show(name, c.drain(a.wait if name == who else 0.3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
