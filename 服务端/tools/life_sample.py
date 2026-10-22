"""对原版抽样生活技能产出：把某项生活技能设到指定等级，连发 N 轮（间隔 4.3 秒），统计 0x64 里的物品 ID 分布，并和 data/life_items.json 的预测比较。

    python tools/life_sample.py <famu|buyu|caikuang> <等级> <轮数>
"""

from __future__ import annotations

import collections
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from life_probe import JY, life, mysql  # noqa: E402
from multi_probe import Client  # noqa: E402

B = {"famu": 1, "buyu": 2, "caikuang": 3}
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    skill, level, rounds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    mysql(f"update renwu set dangqianjing=5000, wint=33 where jyid={JY}")
    mysql(f"update jineng set famu=0,famuexp=0,buyu=0,buyuexp=0,caikuang=0,caikuangexp=0 where jyid={JY}")
    mysql(f"update jineng set {skill}={level},{skill}exp=0 where jyid={JY}")
    c = Client("A", "127.0.0.1", 6731, JY, None)
    assert c.login()
    c.drain(1.0)
    c.send(0x5A, life(1, 1, B[skill]))
    c.drain(1.0)
    dumped: list[int] = []
    seen = collections.Counter()
    levels = collections.Counter()
    for i in range(rounds):
        c.send(0x5A, life(2 + i, 2, B[skill]))
        got = c.drain(4.3)
        item = None
        for f in got:
            if f.opcode == 0x64:
                item = int.from_bytes(f.payload[:2], "little")
                levels[f.payload[4]] += 1
        if any(f.opcode == 0x1A and f.payload[1:5] == bytes.fromhex("b8 54 a4 ee") for f in got):
            item = "rejected"
        seen[item] += 1
        if item == 0 and not dumped:
            dumped.append(1)
            print("item-0 round frames:")
            for f in got:
                print(f"   <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {f.payload.hex(' ')}")
    c.send(0x5A, life(900, 3, B[skill]))
    c.drain(1.0)
    c.sock.close()
    print("levels seen:", dict(levels))
    print("items:", dict(seen))
    table = json.loads((ROOT / "data" / "life_items.json").read_text(encoding="utf-8")) if (ROOT / "data" / "life_items.json").exists() else json.loads((ROOT / "scratch" / "life_items.json").read_text(encoding="utf-8"))
    for lv in sorted(levels):
        exp = collections.Counter()
        for lo, hi, item in table[skill][str(lv)]:
            exp[item] += (hi - lo + 1) / 100
        print("level", lv, "predicted share:", {k: round(v, 2) for k, v in exp.items()})
    time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
