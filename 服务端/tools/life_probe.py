"""生活技能 / 农夫探测：对原版（6731）发 C2S 0x5A / 0x5B / 0x5C，打印回包，并给出 jineng / item 在下线后的变化。

    python tools/life_probe.py work <B 1伐木 2捕魚 3採礦> <轮数> [间隔秒]
    python tools/life_probe.py farm
"""

from __future__ import annotations

import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

JY = 8617293
MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"


def mysql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


def life(seq: int, a: int, b: int, f: int = 0, chk: int = 0) -> bytes:
    """C2S 0x5A：序号 LE32 | A(1 开始 2 一轮 3 停止) | B(1 伐木 2 捕魚 3 採礦) | F 工具位置 | E LE16 | D LE16 | C | 校验"""
    return struct.pack("<IBBBHHBB", seq, a, b, f, 0, 0, 0, chk)


def plant(plot: int, seed: int) -> bytes:
    """C2S 0x5B：田块号(1) | 种子物品 ID LE16"""
    return struct.pack("<BH", plot, seed)


def farm(seq: int, plot: int, action: int) -> bytes:
    """C2S 0x5C：序号 LE32 | 田块号 | 动作(1 耕種 2 收成) | E LE16 | D LE16 | C | 校验"""
    return struct.pack("<IBBHHBB", seq, plot, action, 0, 0, 0, 0)


def show(frames):
    for f in frames:
        if f.opcode in (0x33, 0x99) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
            continue
        print(f"   <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {f.payload.hex(' ')}")


def main() -> int:
    mode = sys.argv[1]
    c = Client("A", "127.0.0.1", 6731, JY, None)
    assert c.login()
    c.drain(1.0)
    before = mysql(f"select * from jineng where jyid={JY}")
    print("jineng before:", before)
    if mode == "work":
        b, rounds = int(sys.argv[2]), int(sys.argv[3])
        gaps = [float(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else [1.0]
        for name, payload in (("start", life(1, 1, b)),) + tuple((f"round {i + 1}", life(2 + i, 2, b)) for i in range(rounds)) + (("stop", life(900, 3, b)),):
            gap = gaps[min(len(gaps) - 1, int(name.split()[1]) - 1)] if name.startswith("round") else 1.0
            print("==", name, f"(wait {gap}s after)")
            c.send(0x5A, payload)
            show(c.drain(gap))
    if mode == "farm":
        seed, cycles = int(sys.argv[2]), int(sys.argv[3])
        gap = float(sys.argv[4]) if len(sys.argv) > 4 else 4.5
        for i in range(cycles):
            for name, op, payload in (("plant", 0x5B, plant(3, seed)), ("till", 0x5C, farm(10 + 3 * i, 3, 1)), ("harvest", 0x5C, farm(11 + 3 * i, 3, 2))):
                print("==", f"cycle {i + 1} {name}")
                c.send(op, payload)
                show(c.drain(gap if name == "harvest" else 1.0))
    c.sock.close()
    time.sleep(4)
    print("jineng after:", mysql(f"select * from jineng where jyid={JY}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
