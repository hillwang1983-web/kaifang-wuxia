#!/usr/bin/env python3
"""消点（C2S 0x5E）对原版服务端的联调：给测试号写一门武功 + 学习点、放到师傅所在的地图，花点数看 S2C 0x68，再试一个师傅不教的组合看 0x14 03。
需要原版服务端（默认 127.0.0.1:6731 + 同机 MySQL5.5）、Windows + loginp.exe + unicorn（会话校验字节）。会改测试号的 renwu / kf 表，结束时还原。
    python client_study_test.py [--host H] [--port P] [--jyid 8617293] [--mysql 路径]
缺什么都按"跳过"处理。不发会让武功掉级的组合（地图 / 门派不对）。"""
import argparse
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
MASTER, KF, MAP = 10003, 1014, 2411          # 师傅.csv：玄悲教伏魔剑法（级数 80，门派 0），在 2411 图
RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def sql(stmt):
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


async def connect(a):
    for _ in range(6):
        c = JyClient(a.host, a.port, name="S")
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


def kf_lv(c, kf):
    for h in c.me.get("kf_rows", []):
        b = bytes.fromhex(h)
        if int.from_bytes(b[7:9], "little") == kf:
            return int.from_bytes(b[1:3], "little"), int.from_bytes(b[3:7], "little")
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
        print("SKIP 找不到 mysql.exe（要改测试号的武功 / 学习点）")
        return 0
    old = sql("select map,x,y,study_count,school from renwu where jyid=%d" % a.jyid).split("\t")
    old_kf = [l.split("\t") for l in sql("select kf_id,kf_lvl,kf_exp from kf where jyid=%d" % a.jyid).splitlines() if l]
    if len(old) != 5:
        print("SKIP 读不到测试号 %d 的 renwu 行" % a.jyid)
        return 0
    c = None
    try:
        sql("update renwu set map=%d,x=1500,y=900,study_count=100,school=0 where jyid=%d; delete from kf where jyid=%d; insert into kf (jyid,kf_id,kf_lvl,kf_exp) values (%d,%d,5,0)" % (MAP, a.jyid, a.jyid, a.jyid, KF))
        c = await connect(a)
        if c is None:
            print("SKIP 连不上原版服务端或登不进去")
            return 0
        if c.checksum_provider(bytes.fromhex(c.rekeys[-1][1]), 2) is None:
            print("SKIP 这台机器算不出会话校验字节")
            return 0
        got = []
        c.listeners.append(lambda f: got.append((f.type, bytes(f.payload))))
        check(kf_lv(c, KF) == (5, 0) and c.me["fields"]["study_count"] == 100, "起点：伏魔剑法 Lv5 经验 0，学习点 100")
        await c.study(MASTER, KF, 1)
        await c.drain(1.5)
        r = c.study_log[-1] if c.study_log else None
        check(r and r["kf"] == KF and r["lv"] == 5 and r["exp"] == 31 and r["study"] == 99 and not r["lost"], "消点 1 点：S2C 0x68 经验 31、学习点 99（%s）" % r)
        check(kf_lv(c, KF) == (5, 31) and c.me["fields"]["study_count"] == 99, "本地 kf 行和学习点跟着改了")
        got.clear()
        n = len(c.study_log)
        await c.study(10004, KF, 1)                  # 玄净不教伏魔剑法：只回提示，不掉级（学习点还够，否则服务端先因点数不够静默）
        await c.drain(1.5)
        txts = [p[1:].decode("big5", "ignore") for t, p in got if t == 0x14]
        check(any("無此師傅代碼" in t and "10004" in t for t in txts) and len(c.study_log) == n, "师傅不教这门武功：0x14 提示『無此師傅代碼…10004﹔1014』%s" % txts[:1])
        await c.study(MASTER, KF, 99)
        await c.drain(1.5)
        r = c.study_log[-1]
        check(r["study"] == 0 and r["lv"] > 5 and r["exp"] > 31, "再花 99 点：学习点 0，升级（Lv%d，经验 %d）" % (r["lv"], r["exp"]))
        n = len(c.study_log)
        await c.study(MASTER, KF, 5)                 # 学习点已经是 0：原版静默不理
        await c.drain(1.5)
        check(len(c.study_log) == n, "点数 > 学习点：服务端静默，没有 0x68")
    finally:
        if c is not None:
            await c.close()
            await asyncio.sleep(1)
        if len(old) == 5:
            sql("update renwu set map=%s,x=%s,y=%s,study_count=%s,school=%s where jyid=%d; delete from kf where jyid=%d" % (*old, a.jyid, a.jyid))
            if old_kf:
                sql("insert into kf (jyid,kf_id,kf_lvl,kf_exp) values " + ",".join("(%d,%s,%s,%s)" % (a.jyid, *r) for r in old_kf))
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
