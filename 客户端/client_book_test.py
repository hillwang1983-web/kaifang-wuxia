#!/usr/bin/env python3
"""读秘笈（C2S 0x60）对原版服务端的联调：属性不够 → 『需要全屬性50』书不扣；属性够 + 已自宫 → 葵花宝典学到 Lv1、书没了；再读一本 → 被网关预检拦下。
需要原版服务端（默认 127.0.0.1:6731 + 同机 MySQL5.5）、测试号要能 @wp 加书（脚本临时把 account.gm_lvl 设 1）。会改测试号的 renwu（属性 / 自宫）、kf、account.gm_lvl，结束时还原。
    python client_book_test.py [--host H] [--port P] [--jyid 8617293] [--mysql 路径]
缺什么都按"跳过"处理。不要求会话校验字节（0x60 没有校验）。"""
import argparse
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402
import books  # noqa: E402

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
BOOK, KF = 35031, 3004          # 葵花宝典 → 武功 3004，要全属性 50 + 自宫
RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def sql(stmt):
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


async def connect(a):
    for _ in range(6):
        c = JyClient(a.host, a.port, name="B")
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
    global MYSQL
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    ap.add_argument("--mysql", default=MYSQL)
    a = ap.parse_args()
    MYSQL = a.mysql
    if not os.path.exists(MYSQL):
        print("SKIP 找不到 mysql.exe（要改测试号的属性 / 自宫 / gm_lvl）")
        return 0
    cols = "str,crg,wint,luk,dex,agi,vit,zigong"
    old = sql("select %s from renwu where jyid=%d" % (cols, a.jyid)).split("\t")
    old_gm = sql("select gm_lvl from account where jyid=%d" % a.jyid)
    old_kf = [l.split("\t") for l in sql("select kf_id,kf_lvl,kf_exp from kf where jyid=%d" % a.jyid).splitlines() if l]
    if len(old) != 8 or not old_gm:
        print("SKIP 读不到测试号 %d 的 renwu / account 行" % a.jyid)
        return 0
    c = None
    try:
        sql("update account set gm_lvl=1 where jyid=%d; update renwu set str=40,crg=60,wint=60,luk=60,dex=60,agi=60,vit=60,zigong=0 where jyid=%d; delete from kf where jyid=%d" % (a.jyid, a.jyid, a.jyid))
        c = await connect(a)
        if c is None:
            print("SKIP 连不上原版服务端或登不进去")
            return 0
        if not any(s["item_id"] == BOOK for s in c.me["bag"]):
            await c.command("@wp %d" % BOOK)
            await c.drain(1.5)
        if not any(s["item_id"] == BOOK for s in c.me["bag"]):
            print("SKIP @wp %d 没有给到书（不是 GM？）" % BOOK)
            return 0
        n0 = sum(1 for s in c.me["bag"] if s["item_id"] == BOOK)
        got = []
        c.listeners.append(lambda f: got.append((f.type, bytes(f.payload))))
        check(books.check(BOOK, c.me["fields"], set()) == "需要全屬性50", "预检：臂力 40 → 需要全屬性50（和服务端一样的话）")
        await c.read_book(BOOK)
        await c.drain(1.5)
        txt = [p[1:].decode("big5", "ignore") for t, p in got if t == 0x1A]
        check(any("需要全" in t for t in txt) and not c.study_log, "属性不够：原版回『需要全屬性50…』，没学到武功 %s" % txt[:1])
        await c.close()
        sql("update renwu set str=60 where jyid=%d" % a.jyid)
        c = await connect(a)
        got = []
        c.listeners.append(lambda f: got.append((f.type, bytes(f.payload))))
        n1 = sum(1 for s in c.me["bag"] if s["item_id"] == BOOK)
        check(n1 == n0, "书没被扣（重新登录后还是 %d 本）" % n1)
        check(books.check(BOOK, c.me["fields"], set()) == "需要全屬性50,需要自宮", "预检：全属性 60 但还没自宫 → 需要自宮")
        await c.zigong("nope")
        await c.drain(1.0)
        check(not c.me["fields"].get("zigong") and c.pw_result is None, "自宫（0x98 0D）密码错：不会自宫")
        await c.zigong(str(a.jyid))
        await c.drain(1.0)
        check(c.pw_result and c.pw_result[0] == 0x10 and c.me["fields"].get("zigong") == 1, "自宫（0x98 0D）密码对：0xB8 10『自宮成功』，zigong = 1")
        check(books.check(BOOK, c.me["fields"], set()) is None, "预检：全属性 60 + 自宫 → 可以读")
        await c.read_book(BOOK)
        await c.drain(1.5)
        r = c.study_log[-1] if c.study_log else None
        check(r and r["kf"] == KF and r["lv"] == 1 and r["exp"] == 0, "属性够 + 自宫：S2C 0x68 学到武功 %d Lv1（%s）" % (KF, r))
        check(sum(1 for s in c.me["bag"] if s["item_id"] == BOOK) == n1 - 1, "书从本地背包里没了一本（0x0B / 0x6B）")
        check(any(int.from_bytes(bytes.fromhex(h)[7:9], "little") == KF for h in c.me["kf_rows"]), "本地 kf 行里有了 %d" % KF)
        check(books.check(BOOK, c.me["fields"], {KF}) is not None, "再读一本：预检拦下（原版会扣书）")
    finally:
        if c is not None:
            await c.close()
            await asyncio.sleep(1)
        sql("update account set gm_lvl=%s where jyid=%d; update renwu set str=%s,crg=%s,wint=%s,luk=%s,dex=%s,agi=%s,vit=%s,zigong=%s where jyid=%d; delete from kf where jyid=%d" % (old_gm, a.jyid, *old, a.jyid, a.jyid))
        if old_kf:
            sql("insert into kf (jyid,kf_id,kf_lvl,kf_exp) values " + ",".join("(%d,%s,%s,%s)" % (a.jyid, *r) for r in old_kf))
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
