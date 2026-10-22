#!/usr/bin/env python3
"""事件脚本 / 对话文本 / 对话引擎的离线测试（不需要服务端）。只用标准库。

    python test_evt.py [--pic ..\\share\\pic]
"""
import argparse
import os
import random
import sys

import evtdata
import evtengine
import npcdata

RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def run(eng, events, picks=()):
    g = eng.talk(events)
    out, it = [], iter(picks)
    try:
        st = next(g)
        while True:
            out.append(st)
            st = g.send(next(it, 0)) if st["t"] == "menu" else next(g)
    except StopIteration:
        pass
    return out


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--pic", default=os.path.join(here, "share", "pic") if os.path.isdir(os.path.join(here, "share", "pic")) else os.path.join(here, "..", "share", "pic"))
    a = ap.parse_args()
    ev, npc, T = evtdata.EventIndex(a.pic), npcdata.NpcIndex(a.pic), evtdata.TextStore(a.pic)

    # ---- 文本库
    check(len(T) > 160000, "对话文本 %d 条（TextMrg + 2 + 3 + 4）" % len(T))
    check(T.get(10001) == "佛渡有緣人，看施主俱足善根，不知是否願意皈依我佛修行度世？並戒守少林寺規：", "文本 10001 解密正确（奇偶位翻转 + XOR 0x6B）")
    check(T.get(26063) == "評定大會終於來了，真希望能快一點知道自己的結果。" and T.get(69476).startswith("哼！我念在"), "文本 26063 / 69476")
    check(evtdata.decode_text(b"") == b"" and T.get(999999999) is None, "空串 / 不存在的编号")

    # ---- 事件记录
    check(len(ev.index) == 3433, "事件记录 %d 张地图" % len(ev.index))
    bad = [m for m in ev.index if ev.get(m) is None]
    check(not bad, "全部记录按原版加载器的文法解析成功（失败 %d）%s" % (len(bad), bad[:5]))
    unk = [m for m in ev.index if any(x["kind"] > 0x24 and x["kind"] < 0xFE for x in ev.get(m)["acts"])]
    check(sorted(unk) == ["1319"], "只有 1 张图（%s）解析中途跑偏（动作种类 62 / 74 / 119，原版加载器有没写到的分支）；254 / 255 是无载荷的占位种类（EvtMrg3 优先后 2102 不再跑偏）" % ",".join(unk))
    rec = ev.get("2801")
    check(len(rec["nodes"]) == 1276 and len(rec["conds"]) > 500 and len(rec["acts"]) > 1000, "2801：%d 节点 / %d 条件 / %d 动作" % (len(rec["nodes"]), len(rec["conds"]), len(rec["acts"])))
    check(ev.get("14") is not None and ev.get("0014") is not None and len(ev.get("14")["nodes"]) == 18, "小编号地图 14 = 记录 0014（补零查找）")
    check(len(npc.get("14")) > 0, "NPC 摆放同样按 14 -> 0014 查找")
    # 事件 id = 节点 0 起序号：服务端 事件.csv 里 (2801, 53) 的结果标记在节点 53 的动作里
    n53 = rec["nodes"][53]
    marks = {m for ai in n53["M"] for m in [x[0] for x in rec["acts"][ai].get("marks", [])]}
    check({40354, 51238} <= marks and n53["name"] == "43-英雄宴-勝利", "节点序号 = 服务端事件 id：2801 事件 53 的效果 {40354, 51238} 在节点 53 里")

    # ---- 条件
    F = {"school": 0, "fame_val": 4000, "combat_exp": 1200, "exp_val": 0, "jy_money": 100, "dangqianxue": 2000}
    S = evtengine.PlayerState([50527, 50527, 40373], F)
    h = evtengine.holds
    check(h({"type": 1, "marks": [(50527, 1)], "items": [], "attrs": []}, S)[0] and not h({"type": 1, "marks": [(50527, 3)], "items": [], "attrs": []}, S)[0], "type1：标记 / 物品数量不少于 n")
    check(h({"type": 2, "marks": [(1, 1)], "items": [], "attrs": []}, S)[0] and not h({"type": 2, "marks": [(40373, 1)], "items": [], "attrs": []}, S)[0], "type2：这些标记都没有")
    check(h({"type": 1, "marks": [], "items": [], "attrs": [(61, 300)]}, S)[0] and not h({"type": 1, "marks": [], "items": [], "attrs": [(61, 5000)]}, S)[0], "type1 属性 ≥（61 = 名声）")
    check(h({"type": 3, "marks": [], "items": [], "attrs": [(65, 0)]}, S)[0] and not h({"type": 3, "marks": [], "items": [], "attrs": [(65, 26)]}, S)[0], "type3 属性 ==（65 = 门派）")
    check(h({"type": 4, "marks": [], "items": [], "attrs": [(65, 0)]}, S)[0] is False and h({"type": 4, "marks": [], "items": [], "attrs": [(65, 26)]}, S)[0], "type4 属性 !=")
    check(h({"type": 1, "marks": [], "items": [], "attrs": [(24, 3000)]}, S)[0] is False, "属性 24 = 当前血（2000 < 3000）")
    check(h({"type": 99}, S) == (True, True), "未知条件类型：按成立处理并标记为猜测")

    # ---- 引擎：2801 的 NPC
    def npc_of(name):
        return next(x for x in npc.get("2801") if x["name"] == name)

    def mk(state, name):
        return evtengine.Engine(rec, T, state, me_name="我", npc_name=name, rng=random.Random(1))
    guan = npc_of("李管家")
    check(guan["events"] == [188, 135, 54, 46, 43, 42, 53, 45, 44] and [rec["nodes"][e]["name"] for e in guan["events"]][:3] == ["黃蓉支線完成", "有三個標記", "戰過標記"],
          "李管家的事件列表 = 节点 188 135 54 46 43 42 …（0 起序号，名字对得上）")
    out = run(mk(evtengine.PlayerState([], F), "李管家"), guan["events"])
    check([s["t"] for s in out] == ["start", "say"] and out[0]["ev"] == 42 and out[1]["text"] == "現下正在進行群英會大宴，閒雜人等不得進入。" and out[1]["side"] == "npc",
          "没条件的玩家：走兜底主事件 42「一般人」，NPC 说「現下正在進行群英會大宴…」")
    out = run(mk(evtengine.PlayerState([40373], F), "李管家"), guan["events"])
    check(out[0]["ev"] == 43 and [s["t"] for s in out] == ["start", "effect", "say", "say", "fight"] and out[1]["ev"] == 43 and "英雄帖" in out[2]["text"] and bool(out[-1]["mobs"]) and out[-1]["mobs"][0]["mob"] > 0,
          "有英雄帖（40373）：事件 43：效果（发 0x6B 43）→ 两页话 → 战斗（对手 %s）" % (out[-1].get("mobs") if out else None))
    out = run(mk(evtengine.PlayerState([50527], F), "李管家"), guan["events"])
    check(out[0]["ev"] == 188, "有标记 50527：最先匹配事件 188（列表顺序 = 优先级）")
    # 商店：装备店老闆 -> 选单 -> 开店 merchant 50（京城装备店）
    da = npc_of("裝備店老闆")
    out = run(mk(evtengine.PlayerState([], F), "裝備店老闆"), da["events"], picks=[0])
    check([s["t"] for s in out] == ["start", "menu", "say", "shop"] and out[-1]["merchant"] == 50 and "裝備" in out[1]["prompt"], "装备店老闆：选单 → 「想看看」→ 一页话 → 开店 50")
    out = run(mk(evtengine.PlayerState([], F), "裝備店老闆"), da["events"], picks=[1])
    check([s["t"] for s in out] == ["start", "menu", "say"] and "謝謝" not in out[2]["text"] and "再來" in out[2]["text"] or "隨時" in out[2]["text"], "选「不需要」：一页告别话，不开店")
    out = run(mk(evtengine.PlayerState([], F), "裝備店老闆"), da["events"], picks=[None])
    check([s["t"] for s in out] == ["start", "menu"], "选单没回答（None）：对话结束")
    # 说话者交替：地图 14 的动作 17 = [-1, 26075, 26076, 26077, -1]
    rec14 = ev.get("14")
    e14 = evtengine.Engine(rec14, T, evtengine.PlayerState([], {"school": 26}), me_name="我", npc_name="乞丐")
    pg = list(e14.pages([-1, 26075, 26076, 26077, -1]))
    check([p["side"] for p in pg] == ["npc", "me", "npc"] and pg[1]["text"].startswith("真的嗎"), "对话页：-1 开头 = NPC 先说，然后轮流（NPC / 我 / NPC）")
    pg = list(e14.pages([26070, 26071, -1]))
    check([p["side"] for p in pg] == ["me", "npc"], "没有 -1 开头：玩家先说")
    # 多人对话（动作 28）说话者 = 型号 -> 名字
    sp = {}
    for m in npc.index:
        for n in npc.get(m):
            sp.setdefault(n["model"], n["name"])
    check(sp.get(39115) == "陳忠仁" and len(sp) > 1500, "说话者表：型号 39115 = 陳忠仁（%d 个型号）" % len(sp))
    # 随机子事件：同一种子结果固定、候选不含条件不满足的
    ng = npc_of("樵夫吳名")
    o1 = run(mk(evtengine.PlayerState([], F), "樵夫吳名"), ng["events"])
    o2 = run(mk(evtengine.PlayerState([], F), "樵夫吳名"), ng["events"])
    check(o1 == o2 and any(s["t"] == "say" for s in o1), "「亂說話」随机挑子事件：同一种子结果一致")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
