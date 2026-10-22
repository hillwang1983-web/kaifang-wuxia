#!/usr/bin/env python3
"""战斗收发测试：jyfight 纯函数 + jyclient 对 combat_server.py（jyserver + 模拟战斗，隔离副本）。
    python test_fight.py            # 自起隔离服务端
"""
import asyncio
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402
import jyfight as J  # noqa: E402
from jyclient import JyClient  # noqa: E402

RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def le(v):
    return struct.pack("<I", v)


def unit():
    f = J.FightState()
    me = 12345
    mob1, mob2 = 100038166, 100138166
    # D5 我方 / 敌方，A/B 两字节
    f.apply(0xD5, struct.pack("<H", 1) + le(me) + bytes([0x14, 0x09]), me)
    f.apply(0xD5, struct.pack("<H", 2) + le(mob1) + bytes([0x55, 0x08]) + le(mob2) + bytes([0x55, 0x08]), me)
    check(set(f.ents) == {me, mob1, mob2} and f.ents[mob1].team == 2 and f.ents[me].team == 1, "D5：6 字节记录按 id 分队")
    check((f.ents[mob1].A, f.ents[mob1].B) == (0x55, 0x08) and (f.ents[me].A, f.ents[me].B) == (0x14, 0x09), "D5：A/B 是两个独立字节，不是 LE16 类型")
    check(J.mob_id(mob1) == 38166 and J.mob_slot(mob2) == 1, "实体 id → mob_id / 槽位")
    # DC
    dc = struct.pack("<H", 1) + le(me) + b"\x01\x00\x00\x00" + le(69000) + b"\x00" * 9
    f.apply(0xDC, dc, me)
    check(f.ents[me].hp == 69000 and f.ents[me].maxhp == 69000, "DC：id@2 气血@10")
    f.apply(0xDC, struct.pack("<H", 2) + le(mob1) + b"\x01\x00\x00\x00" + le(19000) + b"\x00" * 9 + le(mob2) + b"\x01\x00\x00\x00" + le(19000) + b"\x00" * 9, me)
    check(f.ents[mob2].hp == 19000, "DC：两条记录步长 21")
    # D8 绝对值 + 差值
    mf = {}
    f.apply(0xD8, b"\x01" + le(mob1) + le(12000), me, mf)
    check(f.ents[mob1].hp == 12000 and f.events[-1]["delta"] == 7000, "D8：怪气血绝对值，差值=旧-新")
    f.apply(0xD8, b"\x01" + le(me) + le(68880) + le(mob2) + le(0), me, mf)
    check(mf.get("dangqianxue") == 68880 and not f.ents[mob2].alive, "D8：多条记录；玩家气血同步；气血 0 = 死亡")
    # D7 / D4 / E4 / E8 / E6
    f.apply(0xD7, le(mob1) + bytes([2, 1]) + le(800301) + bytes([5, 30, 27, 24, 31, 3]), me)
    check(f.events[-1]["k"] == "act" and f.events[-1]["skill"] == 800301 and (f.events[-1]["tcol"], f.events[-1]["trow"]) == (24, 31) and f.events[-1]["dir"] == 3, "D7：前 16 字节解析")
    f.apply(0xD4, le(mob1) + bytes([29, 29]), me)
    check((f.ents[mob1].col, f.ents[mob1].row) == (29, 29), "D4：怪移动到 (col,row)")
    f.apply(0xE4, bytes([30, 27]) + struct.pack("<H", 15019) + bytes([31, 28]) + struct.pack("<H", 100), me)
    check(f.items == {(30, 27): 15019, (31, 28): 100}, "E4：N×[col,row,item LE16]")
    f.apply(0xE8, le(me) + bytes([30, 27]), me)
    check(f.items == {(31, 28): 100} and f.events[-1]["item"] == 15019, "E8：拾走该格物品")
    f.apply(0xE6, le(mob2), me)
    check(f.ents[mob2].left and not f.ended_by_server, "E6：怪离场")
    # 判定
    f.result = 0
    check(f.judge(1000.0) == 0, "判定：双方都有人 = 进行中")
    f.apply(0xD8, b"\x01" + le(mob1) + le(0), me)
    check(f.judge(1000.0) == J.RES_WIN and not f.end_due(1005.0) and f.end_due(1015.0), "判定：敌方全灭 = 0x16，等满 15 秒才该发 E5")
    g = J.FightState()
    g.apply(0xD5, struct.pack("<H", 1) + le(me) + bytes([0x14, 0x09]), me)
    g.apply(0xD5, struct.pack("<H", 1) + le(mob1) + bytes([0x55, 0x08]), me)
    g.apply(0xD8, b"\x01" + le(me) + le(0), me)
    check(g.judge(10.0) == J.RES_LOSE, "判定：我方全灭 = 0x0B")
    # AI
    h = J.FightState()
    h.apply(0xD5, struct.pack("<H", 1) + le(me) + bytes([0x14, 0x09]), me)
    h.apply(0xD5, struct.pack("<H", 2) + le(mob1) + bytes([0x55, 0x08]) + le(mob2) + bytes([0x55, 0x08]), me)
    r = type("R", (), {"random": staticmethod(lambda: 0.0)})
    check(h.plan_enemy_acts(me, 100.0, rng=r) == [], "AI：第一次只排期不出手")
    acts = h.plan_enemy_acts(me, 102.0, rng=r)
    check(sorted(a[0] for a in acts) == [mob1, mob2] and all(a[1] == me for a in acts), "AI：到点的怪各出一招，目标是玩家")
    check(h.plan_enemy_acts(me, 102.5, rng=r) == [], "AI：出完手要等间隔")
    # 载荷
    pl = J.build_act(me, 2, 800301, (24, 31), (30, 27), level=0, tick=7, direction=3, seed=5)
    check(len(pl) == 28 and struct.unpack_from("<I", pl, 0)[0] == me and struct.unpack_from("<I", pl, 6)[0] == 800301 and pl[11:13] == bytes([24, 31]), "D7 载荷：28 字节，施术者/武功/格子")
    check(pl[13] == ((me + 5 + 0x0B) % 100) ^ 30 and pl[14] == ((me + 5 + 0x17) % 100) ^ 27, "D7 玩家 [13][14] = 混淆值（文档 §2.1）")
    pm = J.build_act(mob1, 2, 800301, (30, 27), (24, 31), mob=True)
    check(pm[13:15] == bytes([24, 31]) and pm[10] == 5, "D7 怪：[13][14] 直接是目标格，[10]=5")
    check(J.build_encounter(100038166) == le(100038166) + b"\x00" * 19, "0x30 载荷：id + 19 零字节")
    check(len(J.build_enter(me, 24, 31)) == 8 and J.build_end(me)[:4] == le(me) and len(J.build_end(me)) == 5, "E3 8 字节 / E5 5 字节")


async def integ(port):
    c = JyClient("127.0.0.1", port, name="fight")
    await c.connect()
    assert await c.login(123456)
    await c.start()
    await c.drain(0.4)
    me = c.me["fields"]["jyid"]
    bag0 = c.bag_count(15019)
    f = c.fight
    # 小 id：只回我方名单，不进战斗
    await c.fight_encounter(38166)
    await c.drain(0.4)
    check(not any(e.team == 2 for e in f.ents.values()) and f.d1 is None, "实体 id < 10000001：不进战斗（只回我方 D5）")
    # 正常遭遇
    await c.fight_encounter(100038166)
    await c.drain(0.5)
    hp0 = f.ents[me].hp
    check(f.d1 is not None and len(f.d1) == 24 and hp0 == 69000 and c.me["fields"]["dangqianxue"] == hp0, "0x30 → D1(24B) + 82 + DC：我方气血（服务端设 69000）")
    await c.fight_enter()
    await c.drain(0.6)
    en = [e for e in f.ents.values() if e.team == 2]
    check(len(en) == 3 and all(e.hp == 19000 and e.col is not None for e in en) and f.ready, "E3 → D5×2 + D4 + DC + C6：3 只怪，血 19000，有格子")
    mob = sorted(en, key=lambda e: e.id)[0]
    for hit, want in ((1, 12000), (2, 5000), (3, 0)):
        await c.fight_act(me, (mob.col, mob.row))
        await c.drain(0.35)
        check(mob.hp == want, "玩家 D7 第 %d 招 → D8 绝对气血 %d" % (hit, want))
    check(f.events and any(e["k"] == "act" and e["id"] == me for e in f.events), "S2C D7 转发被解析成出招事件")
    check(not mob.alive and mob.left, "怪气血 0 → E6 离场")
    check(f.items == {} and any(e["k"] == "pick" and e["item"] == 15019 for e in f.events), "掉落 E4 → 拾取 E8：格子清空")
    check(c.bag_count(15019) == bag0 + 1, "掉落 0x77 进背包 +1")
    # 怪 AI（客户端替怪发 D7）→ 服务端扣玩家血
    n0 = len([e for e in f.events if e["k"] == "act" and J.is_mob(e["id"])])
    t = time.time() + 100
    sent = []
    for k in range(6):
        sent += [a for a in await c.fight_tick(now=t + k * 10, delay=999) if a[0] == "mob_act"]
        await c.drain(0.25)
    n1 = len([e for e in f.events if e["k"] == "act" and J.is_mob(e["id"])])
    check(len(sent) >= 4 and n1 - n0 == len(sent), "怪 AI：到点替怪发 D7，服务端转发回来 %d 招" % len(sent))
    check(f.ents[me].hp == hp0 - 120 * len(sent) and c.me["fields"]["dangqianxue"] == f.ents[me].hp, "怪的招 → 玩家气血 D8/7B 同步（每招 -120）")
    # 打死剩下两只 → 判定胜 → E5
    for e in sorted((e for e in f.ents.values() if e.team == 2 and e.alive), key=lambda e: e.id):
        while e.alive:
            await c.fight_act(me, (e.col, e.row))
            await c.drain(0.3)
    check(f.judge() == J.RES_WIN and f.counts() == (1, 0), "敌方全灭 → 客户端判 0x16")
    check(f.items == {} , "三只怪的掉落都已拾走")
    r = await c.fight_tick(now=time.time(), delay=999)
    check(r == [] and not f.end_sent, "未等够延迟：不发 E5")
    r = await c.fight_tick(now=time.time() + 20, delay=15)
    await c.drain(0.5)
    check(r == [("end", J.RES_WIN)] and f.end_sent, "等够 15 秒：发 E5")
    check(f.srv_result == 1 and f.ended_by_server, "E5 → 0x81(01) + E6(自己)：战斗结束")
    check(c.me["fields"]["dangqianxue"] == hp0 - 120 * len(sent), "结束后 7B 18：气血与服务端一致")
    await c.close()


def run_with_server(coro, env=None):
    tmp = tempfile.mkdtemp(prefix="jyfight-")
    db = os.path.join(tmp, "chars.sqlite")
    pr = None
    try:
        T.make_copy(db, T.csv_rows("药品.csv", "ID"))
        port = T.free_port()
        out = open(os.path.join(tmp, "server.log"), "w")
        pr = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "combat_server.py"), "--port", str(port), "--chars", db, "--tick", "0", "--autosave", "0"],
                              cwd=T.REPO, stdout=out, stderr=subprocess.STDOUT, env=dict(os.environ, **(env or {})))
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            print(open(out.name, encoding="utf8", errors="replace").read())
            raise SystemExit("战斗服务端没起来")
        asyncio.run(coro(port))
    finally:
        if pr:
            pr.terminate()
            try:
                pr.wait(5)
            except subprocess.TimeoutExpired:
                pr.kill()
        shutil.rmtree(tmp, ignore_errors=True)


async def integ_lose(port):
    c = JyClient("127.0.0.1", port, name="lose")
    await c.connect()
    assert await c.login(123456)
    await c.start()
    await c.drain(0.4)
    me = c.me["fields"]["jyid"]
    f = c.fight
    await c.fight_encounter(100038166)
    await c.drain(0.4)
    await c.fight_enter()
    await c.drain(0.5)
    check(f.ents[me].hp == 1, "（1 点血的测试号）")
    t = time.time() + 100
    await c.fight_tick(now=t, delay=999)
    await c.fight_tick(now=t + 10, delay=999)
    await c.drain(0.4)
    check(f.ents[me].hp == 0 and not f.ents[me].alive and f.judge() == J.RES_LOSE, "怪的招把玩家打到 0 → 客户端判 0x0B")
    r = await c.fight_tick(now=time.time() + 20, delay=15)
    await c.drain(0.5)
    check(r == [("end", J.RES_LOSE)] and f.srv_result == 2 and f.ended_by_server, "败：E5 → 0x81(02) + E6(自己)")
    await c.close()


def unit_cmds():
    check(J.CMD["defend"] == 7 and J.CMD["dodge"] == 8 and J.CMD["rest"] == 9 and J.CMD["escape"] == 10 and J.CMD["auto"] == 11 and J.CMD["equip"] == 12,
          "命令号 = 命令表下标：防禦 7 / 閃躲 8 / 養精蓄銳 9 / 逃跑 10 / 自動 11 / 裝備 12")
    check(J.CMD_NAMES[2] == "一般攻擊" and J.CMD_NAMES[10] == "逃跑", "命令名表")
    pl = J.build_pose(8617293, 7, counter=0x01020304, tail=5)
    check(len(pl) == 10 and pl[:4] == struct.pack("<I", 8617293) and pl[4] == 7 and pl[5:9] == bytes([4, 3, 2, 1]) and pl[9] == 5, "C2S 0xDE：jyid(4) + 命令号 + 计数器(LE32) + 校验 = 10 字节")
    check(J.build_escape() == b"" and J.OP_POSE == 0xDE and J.OP_ESCAPE == 0xF9, "C2S 0xF9 空载荷；操作码 0xDE / 0xF9")
    f = J.FightState()
    f.apply(0xD7, struct.pack("<I", 8617293) + bytes([7]) + bytes(11), 8617293)
    check(f.events[-1]["k"] == "act" and f.events[-1]["cmd"] == 7, "D7 转发 cmd=7 → act 事件带命令号")
    g = J.FightState()
    g.apply(0xD1, bytes(24))
    g.apply(0xD5, struct.pack("<H", 2) + struct.pack("<I", 8617293) + bytes([0x14, 9]) + struct.pack("<I", 100038166) + bytes([0x55, 8]), 8617293)
    g.ents[8617293].team, g.ents[100038166].team = 1, 2
    g.apply(0xF9, b"\x00")
    check(g.events[-1] == dict(g.events[-1], k="escape", ok=False) and not g.escaped and g.judge() == 0 and not g.end_due(), "S2C F9=00 → 逃跑失败：战斗继续、不上报")
    g.apply(0xF9, b"\x01")
    check(g.events[-1]["ok"] is True and g.escaped and g.judge() == J.RES_ESCAPE == 6, "S2C F9=01 → 逃跑成功：结果码 6")
    check(g.end_due(now=time.time()), "逃跑成功 → 立刻该上报 E5（不等 15 秒）")
    check(g.plan_enemy_acts(8617293) == [], "逃跑成功后怪不再出招")


def main():
    unit()
    unit_cmds()
    run_with_server(integ, {"COMBAT_HP": "69000"})
    run_with_server(integ_lose)
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
