#!/usr/bin/env python3
"""農夫（播種 C2S 0x5B → 耕種 0x5C/1 → 收成 0x5C/2）对原版服务端的联调。
需要原版服务端（默认 127.0.0.1:6731）、一个 GM 账号（@wp 要 gm_lvl=1，用来加锄头和稻米种子）、Windows + loginp.exe + unicorn（0x5C 的会话校验字节）。
    python client_farm_test.py [--host H] [--port P] [--jyid 8617293]
缺什么都按"跳过"处理。会消耗一颗稻米种子、收一个稻米，背包里加一把锄头。"""
import argparse
import asyncio
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402

SEED, CROP, HOE = 44201, 44206, 45014
RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


async def connect(a):
    for _ in range(6):
        c = JyClient(a.host, a.port, name="F")
        try:
            await c.connect()
            if await asyncio.wait_for(c.login(a.jyid), 10):
                await c.start()
                await c.drain(1.0, 3)
                return c
        except (OSError, asyncio.TimeoutError):
            pass
        try:
            await c.close()
        except Exception:
            pass
        await asyncio.sleep(5)
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    a = ap.parse_args()
    c = await connect(a)
    if c is None:
        print("SKIP 连不上原版服务端或登不进去")
        return 0
    if c.checksum_provider(bytes.fromhex(c.rekeys[-1][1]), 2) is None:
        print("SKIP 这台机器算不出会话校验字节")
        await c.close()
        return 0
    for it in (HOE, SEED):
        if not any(s["item_id"] == it for s in c.me["bag"]):
            await c.command("@wp %d" % it)
            await c.drain(1.5)
    if not all(any(s["item_id"] == it for s in c.me["bag"]) for it in (HOE, SEED)):
        print("SKIP @wp 没有给到锄头 / 种子（不是 GM？）")
        await c.close()
        return 0
    n = lambda c, i: collections.Counter(s["item_id"] for s in c.me["bag"])[i]  # noqa: E731
    seeds0, crops0 = n(c, SEED), n(c, CROP)
    c.work_results.clear()
    await c.farm_plant(7, SEED)
    await c.drain(1.5)
    check(c.farm_plots.get(7) == {"seed": SEED, "status": 1}, "播種：S2C 0x66 田块 7 状态 1，种子 %d（%s）" % (SEED, c.farm_plots.get(7)))
    check(n(c, SEED) == seeds0 - 1, "播種：本地背包少一颗种子（%d → %d）" % (seeds0, n(c, SEED)))
    await c.farm_till(7)
    await c.drain(1.5)
    check(c.farm_plots.get(7) == {"seed": SEED, "status": 3} and c.my_state == 6, "耕種：0x66 状态 3、自己的实体状态 6（%s / %s）" % (c.farm_plots.get(7), c.my_state))
    await c.farm_harvest(7)
    await c.drain(1.5)
    check(any(r["item_id"] == CROP and r["ok"] for r in c.work_results), "收成：S2C 0x64 得到稻米（%s）" % c.work_results[:1])
    check(n(c, CROP) == crops0 + 1, "收成：本地背包多一个稻米（%d → %d）" % (crops0, n(c, CROP)))
    await c.close()
    c2 = await connect(a)
    if c2 is not None:
        check(n(c2, CROP) == crops0 + 1 and n(c2, SEED) == seeds0 - 1, "重新登录：服务端背包里稻米 +1、种子 −1（%d / %d）" % (n(c2, CROP) - crops0, n(c2, SEED) - seeds0))
        await c2.close()
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
