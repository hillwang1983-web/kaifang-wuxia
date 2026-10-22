"""多人场景对照：同一串「谁:操作码:载荷」，对原版(6731)和新服务端(6732)各跑一遍，比每一方收到的帧。

    python tools/team_compare.py [场景名 ...]

三个号：A=8617293、W=1234567（都放在地图 2200），C=123456（地图 2801）。登录时的出现 / 在线公告帧不比较，只比较指令之后的帧。
改地图要写库（MySQL / SQLite 两边），所以跑之前请确认两边没有这几个号在线。
"""

from __future__ import annotations

import json
import re
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
WHO = {"A": 8617293, "W": 1234567, "C": 123456}
MAPS = {"A": 2200, "W": 2200, "C": 2801}
NOISE = (0x33, 0x08, 0x02, 0x6D, 0x3D, 0x31, 0x62, 0x61, 0x82)  # 心跳、传送流程帧、可见性帧

SCENARIOS = {
    "basic": ["A:26:", "A:2C:{1234567}", "W:2D:01{8617293}", "A:2E:68656c6c6f", "W:2E:68", "C:2E:61", "A:2E:", "A:29:", "W:29:"],
    "join-mismatch": ["C:26:", "W:2D:01{123456}", "A:2D:01{123456}", "W:2D:02{123456}", "W:2D:01", "C:27:"],
    "forbidden": ["A:5D:b70d3201a001", "A:26:", "A:5D:9808d200c201", "A:26:", "A:27:"],
    "disband-by-member": ["A:26:", "W:2D:01{8617293}", "C:2D:01{8617293}", "W:27:", "A:2E:00000000aa", "A:29:", "A:27:"],
    "leader-logout": ["A:26:", "W:2D:01{8617293}", "A:close:", "W:2E:00000000bb"],
    "member-logout": ["A:26:", "W:2D:01{8617293}", "W:close:", "A:2E:00000000cc", "A:29:"],
    "invite": ["A:2C:{8617293}", "A:2C:{123456}", "A:2C:{99999}", "A:2C:", "A:2C:0102", "A:2C:{1234567}aabb", "A:2C:87d612", "W:2C:{8617293}"],
    "double-join": ["A:26:", "W:2D:01{8617293}", "W:2D:01{8617293}", "W:29:", "W:29:", "A:2E:00000000dd", "A:27:"],
    "two-teams": ["A:26:", "W:26:", "C:2E:00000000ee", "W:2D:01{8617293}", "A:2E:00000000ff", "W:27:", "A:2E:00000000ab"],
}


def mysql(stmt: str) -> None:
    subprocess.run([MYSQL, "-uroot", "-p123456", "jydata", "-e", stmt], capture_output=True)


def set_maps() -> None:
    for k, jy in WHO.items():
        mysql(f"update renwu set map={MAPS[k]},x=512,y=410 where jyid={jy}")
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    for k, jy in WHO.items():
        d = json.loads(c.execute("select rows from characters where jyid=?", (jy,)).fetchone()[0])
        d["renwu"][0].update(map=str(MAPS[k]), x="512", y="410")
        c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), jy))
    c.commit()
    c.close()


def run(port: int, steps: list[str]) -> list[str]:
    time.sleep(3.5)
    clients: dict[str, Client] = {}
    for name, jy in WHO.items():
        c = Client(name, "127.0.0.1", port, jy, None)
        if not c.login():
            return [f"login failed for {name}"]
        clients[name] = c
    for c in clients.values():
        c.drain(1.5)
    out: list[str] = []

    def show(tag, frames):
        for f in frames:
            if f.opcode in NOISE or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            if f.opcode == 0x14 and f.payload[:1] == b"\x0e" and f.payload.endswith(b"\xb6\x7d\xb1\xd2\xa1\x54"):
                continue  # 定时的「网金送礼战」公告
            out.append(f"    {tag} <- 0x{f.opcode:02x} {f.payload.hex(' ')}")

    for step in steps:
        who, op, hx = step.split(":", 2)
        if op == "close":
            clients[who].sock.close()
            out.append(f"== {who} disconnects")
            del clients[who]
            for name, c in clients.items():
                show(name, c.drain(1.0))
            continue
        hx = re.sub(r"\{(\d+)\}", lambda m: struct.pack("<I", int(m.group(1))).hex(), hx)
        payload = bytes.fromhex(hx.replace(" ", ""))
        clients[who].send(int(op, 16), payload)
        out.append(f"== {who} sends 0x{int(op, 16):02x} {payload.hex(' ')}")
        for name, c in clients.items():
            show(name, c.drain(0.8 if name == who else 0.3))
    for c in clients.values():
        try:
            c.sock.close()
        except OSError:
            pass
    return out


def main() -> int:
    import difflib

    names = sys.argv[1:] or list(SCENARIOS)
    bad = 0
    for name in names:
        res = {}
        for port in (6731, 6732):
            set_maps()
            res[port] = run(port, SCENARIOS[name])
            time.sleep(1.5)
        same = res[6731] == res[6732]
        print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
        if not same:
            bad += 1
            for l in difflib.unified_diff(res[6731], res[6732], "original", "new", lineterm="", n=1):
                print("   ", l)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
