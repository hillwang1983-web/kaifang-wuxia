#!/usr/bin/env python3
"""对原版服务端（缺省 127.0.0.1:6731）的战斗状态探测，只发最小的包。2026-10-20 用它得出"原版单人遭遇后已在战斗中、E3 不回包"。

    python probe_original.py state            # 遭遇 / 不遭遇 / 遭遇+E3 三种状态下，D8 和 D4 各回什么
    python probe_original.py sweep 24 31 1    # 对 E3 (col,row,朝向) 把尾字节 0..255 全试一遍，看有没有回应（过滤掉周期性的 0x33 / 0x99）
    python probe_original.py seed             # 打印这个会话的种子和（装了 unicorn 时）k=2 / k=6 的校验字节

注意：原版强制单点登录、会写库；账号默认 8617293（服务端会话对照用的测试号），用 --jyid 改。每个实验开头都会先发 E5 清掉上一场遗留状态，
否则原版对 0x30 不回 D1（"禁止快速进战斗"之外的另一种表现：遭遇还挂着）。
"""
import argparse
import asyncio
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402
import jyfight  # noqa: E402

PERIODIC = (0x33, 0x99)          # 原版周期性发的保活 + 换密钥，不是对我们的回应
MOB = 100038166                  # 倭寇


def fr(got):
    return [(hex(f.type), f.payload.hex()) for f in got if f.type not in PERIODIC]


async def login(a):
    c = JyClient(a.host, a.port, name="probe")
    await c.connect()
    assert await c.login(a.jyid), "登录失败"
    await c.start()
    await c.drain(0.8, 3)
    return c, c.me["fields"]["jyid"]


async def clear_and_encounter(c, me, enc=True):
    await c.send(0xE5, jyfight.build_end(me))
    await c.drain(0.6, 2)
    await asyncio.sleep(1.5)
    if enc:
        await c.fight_encounter(MOB)
        return fr(await c.drain(0.7, 3))
    return []


async def state(a):
    c, me = await login(a)
    d8 = struct.pack("<I", me) + bytes(10)
    print("== 没遭遇")
    await clear_and_encounter(c, me, enc=False)
    await c.send(0xD8, d8); print("  D8 →", fr(await c.drain(0.7, 2.5)))
    await c.send(0xD4, jyfight.build_move(me, 26, 30, 7)); print("  D4 →", fr(await c.drain(0.7, 2.5)))
    print("== 只遭遇（没发 E3）")
    print("  遭遇 →", await clear_and_encounter(c, me))
    await c.send(0xD8, d8); print("  D8 →", fr(await c.drain(0.7, 2.5)))
    print("== 遭遇 + E3")
    await clear_and_encounter(c, me)
    await c.send(0xE3, jyfight.build_enter(me, 24, 31)); print("  E3 →", fr(await c.drain(0.7, 2.5)))
    await c.send(0xD8, d8); print("  D8 →", fr(await c.drain(0.7, 2.5)))
    await c.send(0xD4, jyfight.build_move(me, 26, 30, 7)); print("  D4 →", fr(await c.drain(0.7, 2.5)))
    await c.send(0xE5, jyfight.build_end(me)); await c.drain(0.6, 2)
    await c.close()


async def sweep(a):
    c, me = await login(a)
    await clear_and_encounter(c, me)
    hits = []
    for tail in range(256):
        await c.send(0xE3, struct.pack("<I", me) + bytes([a.col, a.row, a.dir, tail]))
        r = []
        try:
            r.append(await asyncio.wait_for(c.frames.get(), 0.30))
            r += await c.drain(0.3, 1.5)
        except asyncio.TimeoutError:
            pass
        r = [f for f in r if f.type not in PERIODIC]
        if r:
            hits.append(tail)
            print("尾字节 0x%02x 有回应: %s" % (tail, [(hex(f.type), f.payload.hex()) for f in r]), flush=True)
    print("扫完，有回应的尾字节:", [hex(h) for h in hits] or "无")
    await c.send(0xE5, jyfight.build_end(me)); await c.drain(0.6, 2)
    await c.close()


async def seed(a):
    c, me = await login(a)
    print("rekeys:", c.rekeys)
    try:
        from session_key_emu import SessionKey
        sk = SessionKey(bytes.fromhex(c.rekeys[-1][1]))
        print("M =", sk.modulus, " k=2:", sk.provider(2), " k=6:", sk.provider(6), " 状态:", sk.doubles())
    except Exception as e:  # noqa: BLE001
        print("（没有 unicorn / loginp.exe，跳过校验字节）", repr(e))
    await c.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["state", "sweep", "seed"])
    ap.add_argument("col", nargs="?", type=int, default=24)
    ap.add_argument("row", nargs="?", type=int, default=31)
    ap.add_argument("dir", nargs="?", type=int, default=1)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    a = ap.parse_args()
    asyncio.run({"state": state, "sweep": sweep, "seed": seed}[a.cmd](a))


if __name__ == "__main__":
    main()
