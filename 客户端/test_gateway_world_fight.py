#!/usr/bin/env python3
"""地图遇怪：点怪物刷新点（talk）→ 网关直接开战（怪 = 刷新点型号）；事件里的战斗动作（kind 2）解析。对真 jyserver（隔离库）。
    python test_gateway_world_fight.py
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402
import test_gateway_social as GS  # noqa: E402
import test_gateway_fight_real as R  # noqa: E402
import evtengine  # noqa: E402
from npcdata import NpcIndex  # noqa: E402

check = T.check
PIC = r"C:\游戏\网金最原始文件\网金最原始文件\客户端\share\pic"
SERVER_DATA = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"


def unit():
    one = evtengine.fight_mobs({"v": [55439, 23, 4294967295], "l26": []})
    check(one == [{"mob": 55439, "name": "", "n": 1}], "战斗动作：l26 为空时 v[0] = MOB id")
    rec = b"\x15\x95\x08\xa8\xb8\xb1\xd0\xb1\xd0\xa5D" + bytes(12) + b"&\x00\x03"
    many = evtengine.fight_mobs({"v": [0, 1, 2], "l26": [rec, rec[:2] + bytes(24)]})
    check(len(rec) == 26 and many[0]["mob"] == 38165 and many[0]["n"] == 3 and many[0]["name"], "战斗动作：l26 记录 = mob id + 名字 + 数量（%s）" % many)
    check(evtengine.fight_mobs({"v": [0, 1, 2], "l26": []}) == [], "没有对手 = 空")


def pick():
    rows = list(csv.reader(open(os.path.join(SERVER_DATA, "MOB数据.csv"), encoding="gbk", errors="replace", newline="")))
    mobs = {int(r[0]) for r in rows[1:] if r and r[0].isdigit()}
    idx = NpcIndex(PIC)
    for m in sorted(idx.index, key=lambda s: int(s) if s.isdigit() else 0):
        for n in idx.get(m):
            if n["model"] >= 50000 and not n["events"] and n["model"] in mobs and m.isdigit() and int(m) < 65000:
                return int(m), n
    return None, None


def world(gport):
    mp, n = pick()
    check(n is not None, "找到一个没有事件的怪物刷新点（地图 %s 型号 %s）" % (mp, n and n["model"]))
    w = GS.W(gport)
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "登录")
    w.send(op="teleport", map=mp, x=n["x"] * 20 + 10, y=n["y"] * 20 + 60)
    w.wait(lambda m: m["ev"] == "pos" and m.get("tp"), 4)
    w.drain(0.5)
    w.send(op="talk", npc=n["id"])
    f = w.wait(lambda m: m["ev"] == "fight" and any(e["team"] == 2 for e in m["ents"]), 8)
    check(f is not None, "点刷新点 → 网关直接开战")
    if f is None:
        return
    en = [e for e in f["ents"] if e["team"] == 2]
    check(en and en[0]["mob"] == n["model"], "对手 = 刷新点型号 %s" % n["model"])
    check(f.get("npc") == n["id"], "战斗消息带着刷新点 id（页面据此隐藏这只怪）")
    # 离得太远
    w.send(op="talk", npc=n["id"])
    check(w.wait(lambda m: m["ev"] == "error" and "已经在战斗" in m["msg"], 3) is not None, "战斗中再点同一只怪 → 被拒")
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)


def main():
    unit()
    R.with_stack(30000, world)
    print("\n%d/%d 通过" % (sum(T.RES), len(T.RES)))
    return 0 if all(T.RES) else 1


if __name__ == "__main__":
    sys.exit(main())
