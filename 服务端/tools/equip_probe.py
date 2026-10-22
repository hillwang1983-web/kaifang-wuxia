"""装备槽位探针：逐个槽位脱装备，重登录读 0x1E 里的装备记录，看哪一格空了，再把它穿回去。

    python tools/equip_probe.py --jyid 123456 [--port 6731] [--slots 1 2 3 ...]

0x1E 里装备栏是 9 条 5 字节记录（物品ID LE32 + 状态），起点 = 6 + 5N（N = 背包记录数，载荷[4:6]）。
**会改原版服务端里这个号的装备**；脚本结束前会把脱掉的装备按 0x15 穿回去，但中途出错就要手动恢复。
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

REC_NAMES = ["toukui", "xianglian", "yifu", "pifeng", "wuqi", "wuqi2", "huwan", "jiezhi", "xiezi"]
GAP = 4.5  # 单点登录：断开后要等一会儿才能重新登录


def equip_block(c: Client) -> list[tuple[int, int]]:
    for f in c.login_frames:
        if f.opcode == 0x1E:
            p = f.payload
            n = int.from_bytes(p[4:6], "little")
            base = 6 + 5 * n
            return [(int.from_bytes(p[base + 5 * i : base + 5 * i + 4], "little"), p[base + 5 * i + 4]) for i in range(9)]
    raise RuntimeError("no 0x1E")


def session(host, port, jyid):
    c = Client("A", host, port, jyid, None)
    if not c.login():
        raise SystemExit("login failed")
    c.drain(0.3)
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--slots", type=int, nargs="+", default=list(range(0, 11)))
    args = ap.parse_args()

    c = session(args.host, args.port, args.jyid)
    base = equip_block(c)
    print("initial:", [(REC_NAMES[i], v[0], v[1]) for i, v in enumerate(base)])
    c.sock.close()
    for n in args.slots:
        time.sleep(GAP)
        c = session(args.host, args.port, args.jyid)
        c.send(0x16, bytes([n]))
        rep = [(f.opcode, f.payload.hex(" ")) for f in c.drain(0.8)]
        c.sock.close()
        time.sleep(GAP)
        c = session(args.host, args.port, args.jyid)
        now = equip_block(c)
        gone = [REC_NAMES[i] for i in range(9) if now[i] != base[i]]
        print(f"slot {n}: reply {rep}  -> changed records: {gone}")
        # 穿回去：对每条变化的记录，用它原来的 id 和状态，穿进同一个槽位号
        for i in range(9):
            if now[i] != base[i]:
                c.send(0x15, bytes([n]) + struct.pack("<I", base[i][0]) + bytes([base[i][1]]))
                print("   re-equip", REC_NAMES[i], [(f.opcode, f.payload.hex(" ")) for f in c.drain(0.8)])
        c.sock.close()
    time.sleep(GAP)
    c = session(args.host, args.port, args.jyid)
    final = equip_block(c)
    print("restored:", "OK" if final == base else f"DIFFERENT {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
