"""对原版（或新服务端）测删除角色：A 进入世界后发 0x33，看 A 自己和同图旁观号 W 各收到什么。

    python tools/delete_probe.py --port 6731 --a 9999004 --a-password 8617293 --w 1234567 [--no-enter]

不加 --no-enter 时 A 先发 0x19 进入世界。W 只登录并进入世界。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def show(tag, frames):
    for f in frames:
        if f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
            continue
        txt = ""
        if f.opcode in (0x1A, 0x14):
            body = f.payload[1:] if f.opcode == 0x14 else f.payload[1:]
            txt = "  | " + body.decode("big5", errors="replace")
        print(f"    {tag} <- 0x{f.opcode:02x}{' wide' if f.wide else ''} {f.payload.hex(' ')}{txt}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--a", type=int, required=True)
    ap.add_argument("--a-password")
    ap.add_argument("--w", type=int, required=True)
    ap.add_argument("--w-password")
    ap.add_argument("--no-enter", action="store_true")
    ap.add_argument("--payload", default="00 07 38363137323933")
    a = ap.parse_args()
    w = Client("W", "127.0.0.1", a.port, a.w, a.w_password)
    assert w.login()
    w.send(0x19, b"\x00")
    w.drain(1.5)
    c = Client("A", "127.0.0.1", a.port, a.a, a.a_password)
    assert c.login()
    if not a.no_enter:
        c.send(0x19, b"\x00")
        c.drain(1.5)
        w.drain(0.5)
    print("== A sends 0x33", a.payload)
    c.send(0x33, bytes.fromhex(a.payload.replace(" ", "")))
    show("A", c.drain(1.5))
    show("W", w.drain(0.5))
    print("== A sends 0x02 chat after delete")
    try:
        c.send(0x02, b"\x01hi")
        show("A", c.drain(1.0))
        show("W", w.drain(0.5))
    except OSError as e:
        print("   A connection error:", e)
    time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
