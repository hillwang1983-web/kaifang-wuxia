"""对原版抽样农夫收成：连种 / 耕 / 收 N 轮，统计每次收成的「另外的物品」（0x77 + 1A）出现的概率和物品 ID 分布。

    python tools/farm_sample.py <种子ID> <轮数>      （先把背包里放够种子，重启原版）
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from life_probe import JY, farm, plant  # noqa: E402
from multi_probe import Client  # noqa: E402


def main() -> int:
    seed, cycles = int(sys.argv[1]), int(sys.argv[2])
    c = Client("A", "127.0.0.1", 6731, JY, None)
    assert c.login()
    c.drain(1.0)
    extras = collections.Counter()
    crops = collections.Counter()
    n_extra = 0
    shapes = collections.Counter()
    for i in range(cycles):
        c.send(0x5B, plant(i % 8, seed))
        c.drain(0.6)
        c.send(0x5C, farm(100 + 3 * i, i % 8, 1))
        c.drain(0.6)
        c.send(0x5C, farm(101 + 3 * i, i % 8, 2))
        got = c.drain(4.2)
        shape = tuple(f.opcode for f in got if f.opcode not in (0x33,))
        shapes[shape] += 1
        for f in got:
            if f.opcode == 0x64:
                crops[int.from_bytes(f.payload[:2], "little")] += 1
            if f.opcode == 0x77:
                n_extra += 1
                extras[int.from_bytes(f.payload[:4], "little")] += 1
    c.sock.close()
    print("cycles", cycles, "extras", n_extra)
    print("crops", dict(crops))
    print("extra items", dict(extras))
    print("shapes", {" ".join(f"{x:02x}" for x in k): v for k, v in shapes.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
