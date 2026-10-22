"""对一个号（kf 表里放了几条武功）发 C2S 0x61（装备武功）的 槽位×武功 矩阵，看每格的回包，找出槽位规则。

    python tools/kf_matrix.py --port 6731 --jyid 8617293 --ids 1000,1002,1003 --slots 0-14 [--reverse]

每格打印 `slot id -> 回包摘要`：6E=成功回显；14=全服「嘗試刷武功」公告；空 = 无回包。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def summary(frames) -> str:
    out = []
    for f in frames:
        if f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
            continue
        if f.opcode == 0x14:
            out.append("14:" + f.payload[1:].decode("big5", errors="replace")[-8:])
        else:
            out.append(f"{f.opcode:02x}:{f.payload.hex()}")
    return " | ".join(out) or "-"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--slots", default="0-14")
    ap.add_argument("--reverse", action="store_true")
    ap.add_argument("--wait", type=float, default=0.5)
    a = ap.parse_args()
    lo, _, hi = a.slots.partition("-")
    slots = list(range(int(lo), int(hi or lo) + 1))
    ids = [int(x) for x in a.ids.split(",")]
    if a.reverse:
        slots.reverse()
    c = Client("A", "127.0.0.1", a.port, a.jyid, None)
    assert c.login()
    c.drain(1.0)
    for kid in ids:
        for s in slots:
            c.send(0x61, bytes([s]) + struct.pack("<H", kid))
            print(f"slot {s:2d} id {kid}: {summary(c.drain(a.wait))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
