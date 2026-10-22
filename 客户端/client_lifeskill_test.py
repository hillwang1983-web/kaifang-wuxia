#!/usr/bin/env python3
"""生活技能对原版服务端的联调（伐木）：开始 → 状态 3 → 做两轮（精 −1、S2C 0x64 结果）→ 停止 → 状态 0。
需要原版服务端（默认 127.0.0.1:6731）、一个账号、该账号是 GM（@wp 要 gm_lvl=1，用来加斧头）、Windows + loginp.exe + unicorn（会话校验字节）。
    python client_lifeskill_test.py [--host H] [--port P] [--jyid 8617293]
缺什么都按"跳过"处理。会让该号掉几点精、背包加一把斧头。"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402
import lifeskill  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    a = ap.parse_args()
    c = None
    for _ in range(6):
        c = JyClient(a.host, a.port, name="W")
        try:
            await c.connect()
            if await asyncio.wait_for(c.login(a.jyid), 10):
                await c.start()
                await c.drain(1.0, 3)
                break
        except (OSError, asyncio.TimeoutError):
            pass
        try:
            await c.close()
        except Exception:
            pass
        c = None
        await asyncio.sleep(5)
    if c is None:
        print("SKIP 连不上原版服务端或登不进去")
        return 0
    if c.checksum_provider(bytes.fromhex(c.rekeys[-1][1]), 2) is None:
        print("SKIP 这台机器算不出会话校验字节")
        await c.close()
        return 0
    await c.teleport(2801, 1500, 900)
    await c.drain(1.0)
    if not any(s["item_id"] == 45010 for s in c.me["bag"]):
        await c.command("@wp 45010")
        await c.drain(1.5)
    if not any(s["item_id"] == 45010 for s in c.me["bag"]):
        print("SKIP @wp 45010 没有给到斧头（不是 GM？）")
        await c.close()
        return 0
    jing0 = c.me["fields"]["dangqianjing"]
    c.work_results.clear()
    await c.work_start(1, 45010)
    await c.drain(1.5)
    check(c.my_state == 3, "开始伐木：自己的实体状态 = 3（S2C 0x82）")
    for _ in range(2):
        await asyncio.sleep(lifeskill.TICK_SECS + 0.2)
        await c.work_tick()
        await c.drain(1.5)
    check(len(c.work_results) >= 2 and all(r["item_id"] == 44156 and r["ok"] for r in c.work_results), "做两轮：收到 S2C 0x64 结果（44156 相思木，成功）%s" % c.work_results[:2])
    check(c.me["fields"]["dangqianjing"] == jing0 - 2, "每轮精 −1（%d → %d）" % (jing0, c.me["fields"]["dangqianjing"]))
    await c.work_stop()
    await c.drain(1.5)
    check(c.my_state == 0 and c.work is None, "停止：实体状态回 0")
    await c.close()
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
