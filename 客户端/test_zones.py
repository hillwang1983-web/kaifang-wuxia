#!/usr/bin/env python3
"""门 / 出入口触发区（npcdata.parse_zones）+ 事件动作 3 = 传送（evtengine）+ NpcMrg3 / EvtMrg3 优先。用原版 share\\pic；找不到就跳过。"""
import os
import random
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evtdata  # noqa: E402
import evtengine  # noqa: E402
import npcdata  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def teleports(rec, evs):
    out = []
    for e in evs:
        if 0 <= e < len(rec["nodes"]):
            for ai in rec["nodes"][e]["M"]:
                a = rec["acts"][ai]
                if a["kind"] == 3 and len(a.get("raw") or b"") >= 13:
                    out.append(struct.unpack_from("<I", a["raw"], 0)[0])
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    pic = os.path.join(here, "share", "pic") if os.path.isdir(os.path.join(here, "share", "pic")) else os.path.join(here, "..", "share", "pic")
    if not os.path.exists(os.path.join(pic, "NpcMrg3.Mrg")):
        print("SKIP 找不到 NpcMrg3.Mrg")
        return 0
    npc, ev, T = npcdata.NpcIndex(pic), evtdata.EventIndex(pic), evtdata.TextStore(pic)
    # NpcMrg3 / EvtMrg3 优先：2802 图有『新手總指導員-小蘭』（旧规则下被 NpcMrg5 / 4 的旧版本盖掉）
    names = {n["name"] for n in npc.get("8105")}
    check("新手總指導員-小蘭" in names and "特別傳送員" in names, "8105 图用 NpcMrg3：有『新手總指導員-小蘭』『特別傳送員』")
    z = npc.zones("8105")
    check(len(z) == 5 and all(q["kind"] == "door" for q in z), "8105 图 5 个門（%d）" % len(z))
    d1 = next(q for q in z if q["id"] == 0)
    check((d1["x"], d1["y"], d1["w"], d1["h"]) == (1, 41, 60, 200) and d1["events"] == [0], "門 0：格 (1, 41)，60 × 200 像素，事件 [0]")
    rec = ev.get("8105")
    check(teleports(rec, d1["events"]) == [8102], "門 0 的事件 0 = 传送到 8102")
    z2801 = {(q["x"], q["y"]): q for q in npc.zones("2801")}
    q = z2801.get((234, 73))
    check(q and q["events"] == [3] and teleports(ev.get("2801"), q["events"]) == [2803], "2801 图 (234, 73) 的門 → 事件 3 → 传送到 2803（药店）")
    check(len(npc.zones("2801")) == 18, "2801 图 18 个触发区")
    # 事件表归属（2026-10-21 更正：属于它前面的那条记录）：8122 图 4 个 NPC + 1 个門，最后一个表属于小芊
    n8122 = {n["name"]: n["events"] for n in npc.get("8122")}
    check(n8122.get("新手指導員-小芊") == [14, 15, 17, 18, 19, 20, 21, 22] and n8122.get("錢莊老闆史耀乾") == [1, 2, 3, 4, 5, 6, 7] and npc.zones("8122")[0]["events"] == [0, 16],
          "8122 图：事件表跟着它前面的那条记录（小芊 / 錢莊老闆 / 門）")
    check({"保險箱管理員", "銀票兌換員"} <= set(n8122) and len(n8122) == 4, "8122 图 4 个 NPC 都解出来了（名字后面有旧名字残字的两个以前被漏掉；名字按长度字节取）：%s" % sorted(n8122))
    n8104 = npc.get("8104")
    check(len(n8104) == 17 and not any(npcdata.SLOT_RE.fullmatch(n["name"]) for n in n8104) and len(npcdata.parse_npcs(npc._raw("8104"))) == 85,
          "8104 图：68 个怪物攻城刷怪位（首領 / 小隊長 / 嘍嘍N，没有事件）不算 NPC，剩 17 个")
    check(all("�" not in n["name"] for m in ("8104", "8105", "2801") for n in npc.get(m)), "名字里没有乱码（残字不再拼进名字）")
    n8105 = {n["name"]: n["events"] for n in npc.get("8105")}
    check(n8105["新手總指導員-小蘭"][:1] == [231] and n8105["特別傳送員"][:1] == [66], "8105 图：小蘭 = 新手起头（事件 231…），特別傳送員 = 传送选单")
    # 动作 3 = 传送：特別傳送員 选单第 3 项 → 2000 图
    n = next(x for x in npc.get("8105") if x["name"] == "特別傳送員")
    eng = evtengine.Engine(rec, T, evtengine.PlayerState([], {"school": 0}), me_name="我", npc_name=n["name"], rng=random.Random(1))
    g = eng.talk(n["events"])
    steps, picks = [], iter([2, 0])
    try:
        st = next(g)
        while True:
            steps.append(st)
            st = g.send(next(picks, 0)) if st["t"] == "menu" else next(g)
    except StopIteration:
        pass
    check(steps and steps[-1] == {"t": "teleport", "map": 2000, "x": 155, "y": 46, "dir": 0}, "特別傳送員：选第 3 项 → teleport 2000 格 (155, 46)")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
