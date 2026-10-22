"""给新服务端灌随机包，看有没有处理函数抛异常 / 服务端卡死。

    python tools/fuzz_server.py [--rounds 3000] [--seed 1]

在进程内起一个服务端（内存角色库，三个夹具号），三个模拟客户端进入世界，轮流发随机 opcode + 随机载荷（长度 0..40，一半用已知 opcode，
一半完全随机；载荷里夹杂合法的 jyid / 物品 / 武功 ID）。dispatch 被包了一层记录异常；跑完打印「opcode → 异常」去重清单，有异常退出码为 1。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import struct
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jyserver.server import DEFAULT_DATA_DIR, GameServer  # noqa: E402
from jyserver.state import ItemTable  # noqa: E402
from jyserver.store import CharacterStore  # noqa: E402
from multi_probe import Client  # noqa: E402

FIX = ROOT / "data" / "fixtures"
JYIDS = (8617293, 1234567, 123456)


class Spy(GameServer):
    errors: dict = {}

    def dispatch(self, c, f):
        try:
            super().dispatch(c, f)
        except Exception:  # noqa: BLE001
            key = (f.opcode, traceback.format_exc().strip().splitlines()[-1])
            if key not in Spy.errors:
                Spy.errors[key] = (f.payload.hex(), traceback.format_exc())
            raise


def start_server():
    ready = threading.Event()
    box = {}

    async def main():
        store = CharacterStore()  # sqlite 连接要在跑事件循环的同一个线程里建
        for jyid in JYIDS:
            rows = json.loads((FIX / f"char-{jyid}.json").read_text(encoding="utf-8"))["rows"]
            for r in rows.get("renwu", []):
                r["map"] = "2200"
            store.put(jyid, str(jyid), rows)
        gs = Spy(store, ItemTable.load(DEFAULT_DATA_DIR), rng=random.Random(1))
        box["gs"] = gs
        box["srv"] = await gs.serve("127.0.0.1", 0)
        box["port"] = box["srv"].sockets[0].getsockname()[1]
        ready.set()
        await asyncio.sleep(10**6)

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(main())
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=run, daemon=True).start()
    ready.wait(10)
    return box["gs"], box["port"]


def risky_run(gs, port, rnd, rounds) -> int:
    """每包一个新连接：登录（可选先进入世界）后发一个随机的 登录 / 进入 / 建号 / 删号 / 改外号 包，看会不会抛异常。"""
    for n in range(rounds):
        jy = rnd.choice(JYIDS)
        c = Client(str(jy), "127.0.0.1", port, jy, None)
        try:
            if rnd.random() < 0.5:
                if not c.login():
                    continue
            else:  # 只握手、不进世界
                c.send(0x01, struct.pack("<II", jy, 0x0005FCF7) + str(jy).encode())
                c.drain(0.3)
            op = rnd.choice((0x01, 0x19, 0x20, 0x33, 0x13, 0x76, 0x98))
            payload = bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 30)))
            if rnd.random() < 0.4:
                payload = bytes([rnd.randrange(3), len(str(jy))]) + str(jy).encode() + payload
            c.send(op, payload)
            c.drain(0.1)
        except OSError:
            pass
        finally:
            try:
                c.sock.close()
            except OSError:
                pass
        time.sleep(0.05)
    time.sleep(0.5)
    print(f"risky: {rounds} connections, distinct errors: {len(Spy.errors)}")
    for (op, line), (hx, tb) in sorted(Spy.errors.items()):
        print(f"  op 0x{op:02x}: {line}  payload={hx}")
    if Spy.errors:
        print(next(iter(Spy.errors.values()))[1])
    return 1 if Spy.errors else 0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--risky", action="store_true", help="只发 0x01 / 0x19 / 0x20 / 0x33 / 0x13（会让连接掉线，掉了就重连）")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    gs, port = start_server()
    if a.risky:
        return risky_run(gs, port, rnd, min(a.rounds, 150))
    clients = []
    for jy in JYIDS:
        c = Client(str(jy), "127.0.0.1", port, jy, None)
        assert c.login(), jy
        c.drain(0.3)
        clients.append(c)
    known = sorted(gs.handlers)
    ids = [struct.pack("<I", j) for j in JYIDS] + [struct.pack("<I", 99999)]
    items = [struct.pack("<I", i) for i in (28290, 58182, 13066, 40145, 0, 99999999)]
    skills = [struct.pack("<H", i) for i in (0, 1000, 1046, 3860, 9999, 65535)]
    sent = 0
    for n in range(a.rounds):
        c = clients[n % len(clients)]
        if c.sock.fileno() == -1:
            continue
        op = rnd.choice(known) if rnd.random() < 0.6 else rnd.randrange(256)
        risky = (0x01, 0x19, 0x20, 0x33, 0x13)
        if a.risky:
            op = rnd.choice(risky)
            if c.sock.fileno() == -1:
                continue
        elif op in risky:  # 登录 / 进入 / 建删角色会把测试连接搞掉，单独用 --risky 测
            continue
        parts = []
        for _ in range(rnd.randrange(0, 6)):
            parts.append(rnd.choice([rnd.choice(ids), rnd.choice(items), rnd.choice(skills), bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 5)))]))
        payload = b"".join(parts)[: rnd.randrange(0, 41)]
        try:
            c.send(op, payload)
        except OSError:
            continue
        sent += 1
        if n % 25 == 0:
            for cc in clients:
                cc.drain(0.02)
    time.sleep(0.5)
    for cc in clients:
        cc.drain(0.2)
    alive = sum(1 for c in clients if c.sock.fileno() != -1)
    print(f"sent {sent} packets, online now {len(gs.online)}/{len(clients)}, distinct errors: {len(Spy.errors)}")
    for (op, line), (hx, tb) in sorted(Spy.errors.items()):
        print(f"  op 0x{op:02x}: {line}  payload={hx}")
    if Spy.errors:
        k = next(iter(Spy.errors.values()))
        print(k[1])
    return 1 if Spy.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
