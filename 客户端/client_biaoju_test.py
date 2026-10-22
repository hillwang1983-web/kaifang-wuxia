#!/usr/bin/env python3
"""鏢局（託鏢）对原版服务端的联调：A 託鏢给 B，B 查看存放。需要原版服务端（默认 127.0.0.1:6731）、两个账号、A 是 GM（@wp 要 gm_lvl=1）。
    python client_biaoju_test.py [--host H] [--port P] [--a 8617293] [--b 123456]
连不上 / 登不进去 / @wp 没给到物品都按"跳过"处理（不算失败）。注意：会往 A 的背包加一件物品、往 B 的鏢局存放加一条。"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402
import biaoju  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


async def login(host, port, jy, tag):
    for _ in range(6):
        c = JyClient(host, port, name=tag)
        try:
            await c.connect()
            if await asyncio.wait_for(c.login(jy), 10):
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
    ap.add_argument("--a", type=int, default=8617293)
    ap.add_argument("--b", type=int, default=123456)
    a_ = ap.parse_args()
    a = await login(a_.host, a_.port, a_.a, "A")
    b = await login(a_.host, a_.port, a_.b, "B") if a else None
    if not a or not b:
        print("SKIP 连不上原版服务端或登不进去")
        return 0
    ga, gb = [], []
    a.listeners.append(lambda f: ga.append((f.type, bytes(f.payload))))
    b.listeners.append(lambda f: gb.append((f.type, bytes(f.payload))))
    await a.teleport(2801, 1500, 900)
    await a.drain(1.0)
    if not any(s["item_id"] == 47001 for s in a.me["bag"]):
        await a.command("@wp 47001")
        await a.drain(1.5)
    if not any(s["item_id"] == 47001 for s in a.me["bag"]):
        print("SKIP @wp 47001 没有给到物品（A 不是 GM？）")
        return 0
    check(biaoju.is_job_item(47001), "47001 是打工物品")

    ga.clear()
    await a.biaoju_send(b.me["name"], 47001, 1)
    await a.drain(1.5)
    await b.drain(0.5)
    check(any(t == 0x1A and p[:1] == b"\x0e" for t, p in ga), "A 收到 1A 0E「託鏢成功」")
    check(any(t == 0x1A and p[:1] == b"\x64" and "鏢給你".encode("big5") in p for t, p in gb), "B 收到 1A 64「…鏢給你」")

    gb.clear()
    await b.biaoju_query()
    await b.drain(1.5)
    check(any(r["item_id"] == 47001 and r["from"] == a.me["name"] for r in b.biaoju_list), "B 查存放：S2C 0x49 里有 A 託的 47001（託鏢人 = A 的名字）")

    # 取鏢：要会话校验字节（Windows + loginp.exe + unicorn），算不了就跳过这一项
    if b.checksum_provider(bytes.fromhex(b.rekeys[-1][1]), 2) is None:
        print("SKIP 取鏢：这台机器算不出会话校验字节")
    else:
        for _ in range(2):                                   # 再託两件，凑 3 行（3 个行号字节正好让校验下标 k = 2，不用补位）
            await a.command("@wp 47001")
            await a.drain(1.0)
            await a.biaoju_send(b.me["name"], 47001, 1)
            await a.drain(1.0)
        await b.biaoju_query()
        await b.drain(1.5)
        before = sum(1 for s in b.me["bag"] if s["item_id"] == 47001)
        n_store = len(b.biaoju_list)
        check(n_store >= 3, "B 的存放里至少 3 条（%d）" % n_store)
        await b.biaoju_claim([1, 2, 3])
        await b.drain(2.5)
        check(sum(1 for s in b.me["bag"] if s["item_id"] == 47001) == before + 3, "取鏢 0x3F：S2C 0x4B 把 3 件物品送进背包")
        await b.biaoju_query()
        await b.drain(1.5)
        check(len(b.biaoju_list) == n_store - 3, "取鏢后存放清单少 3 条")
    gb.clear()
    await b.biaoju_jobs(0)
    await b.drain(1.5)
    check(b.biaoju_info.get(4) == [5000], "C2S 0x40 → S2C 0x4D 04 <5000>")
    await a.close()
    await b.close()
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
