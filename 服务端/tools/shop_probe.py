"""商店探针：对原版发 C2S 0x09（开店）/ 0x0A（买），打印所有回包，下线后读库看背包和金钱怎么存的。

    python tools/shop_probe.py --jyid 8617293 --password 8617293 --open 53 --buy 28026:3,28005:2 [--port 6731] [--db]

--buy 是 `物品ID:数量` 逗号列表，同一个包里发（批量购买）。--db 在下线后查 MySQL（只对原版有意义）。
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402


def show(frames):
    for f in frames:
        if f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
            continue  # 服务端的换密钥帧，Client.drain 已经跟了
        txt = ""
        if f.opcode in (0x1A, 0x14):
            txt = "  | " + (f.payload[1:] if f.opcode == 0x14 else f.payload).decode("big5", "replace")
        print(f"   <- 0x{f.opcode:02x}{' W' if f.wide else ''} len={len(f.payload)} {f.payload.hex(' ')[:240]}{txt}")


def inventory_counts(login_frames):
    inv = next(f for f in login_frames if f.opcode == 0x1E).payload
    n = int.from_bytes(inv[4:6], "little")
    counts: dict[int, int] = {}
    for i in range(n):
        iid = int.from_bytes(inv[6 + 5 * i : 10 + 5 * i], "little")
        if iid:
            counts[iid] = counts.get(iid, 0) + 1
    tail = 6 + 5 * n - 121
    return n, counts, int.from_bytes(inv[tail + 299 : tail + 303], "little")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password")
    ap.add_argument("--open", type=int, action="append", default=[])
    ap.add_argument("--buy", action="append", default=[], help="物品ID:数量,物品ID:数量 ；可重复，每次一个包")
    ap.add_argument("--db", action="store_true")
    args = ap.parse_args()

    c = Client("A", args.host, args.port, args.jyid, args.password)
    if not c.login():
        print("login failed")
        return 1
    n, counts, money = inventory_counts(c.login_frames)
    print(f"login: inventory records N={n}, money={money}, item counts={dict(sorted(counts.items())[:12])}")
    c.drain(0.3)
    for npc in args.open:
        c.send(0x09, struct.pack("<H", npc))
        print(f"== open shop {npc}")
        show(c.drain(1.2))
    for spec in args.buy:
        payload = b"".join(struct.pack("<II", int(a), int(b)) for a, b in (s.split(":") for s in spec.split(",")))
        c.send(0x0A, payload)
        print(f"== buy {spec}  ({payload.hex(' ')})")
        show(c.drain(1.2))
    c.sock.close()
    if args.db:
        import layout_probe as lp

        time.sleep(4)
        print("db money:", lp.sql(f"select jy_money from renwu where jyid={args.jyid}")[0][0])
        rows = lp.sql(f"select item_id, shuliang from item where jyid={args.jyid} and item_id>0 order by id")
        print("db item rows:", [(int(a), int(b)) for a, b in rows])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
