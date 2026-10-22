"""看「别人上线 / 下线」时各方收到什么：A 先登录，2.6 秒后 B 登录，再让 A 下线。

    python tools/enter_probe.py --a 8617293 --b 1234567 [--port 6731]

打印 B 登录序列里「A 已在线」带来的额外帧（和单独登录相比多出的），A 看到的 B 上线帧，以及 A 断开后 B 收到的帧。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client, show  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--a", type=int, required=True)
    ap.add_argument("--b", type=int, required=True)
    ap.add_argument("--dump", help="把 A 看到的 B 上线帧存成 JSON（夹具）")
    args = ap.parse_args()
    a = Client("A", args.host, args.port, args.a, None)
    assert a.login()
    time.sleep(2.6)
    b = Client("B", args.host, args.port, args.b, None)
    assert b.login()
    print("B login stream opcodes:", [f"{f.opcode:02x}" for f in b.login_frames])
    seen = {0x01, 0x1E, 0x44, 0x14, 0xBC, 0x32, 0x08, 0x02, 0x6D, 0x3D, 0x31, 0x2F, 0xA9}
    show("B(login)", [f for f in b.login_frames if f.opcode in (0x60, 0x02) and len(f.payload) > 0 or f.opcode == 0x14 and f.payload[:1] == b"\x08"])
    seen_by_a = a.drain(1.0)
    show("A(sees B)", seen_by_a)
    if args.dump:
        Path(args.dump).write_text(
            json.dumps({"jyid": args.b, "frames": [{"opcode": f.opcode, "wide": f.wide, "payload": f.payload.hex()} for f in seen_by_a]}, indent=1),
            encoding="utf-8",
        )
    a.sock.close()
    show("B(after A leaves)", b.drain(3.0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
