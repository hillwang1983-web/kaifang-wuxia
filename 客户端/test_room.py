#!/usr/bin/env python3
"""缺背景图的地图（占位房间）：Gateway.has_art / has_map / cell_of / room_of。随客户端带的资源里约 2800 张图（钱庄 8122、农田 9522 …）
没有背景图和碰撞数据，但 NPC / 门 / 事件都在，新手任务链要走进其中好几张。用原版 share\\pic；找不到就跳过。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gateway as G  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    pic = os.path.join(HERE, "share", "pic") if os.path.isdir(os.path.join(HERE, "share", "pic")) else os.path.join(HERE, "..", "share", "pic")
    if not os.path.exists(os.path.join(pic, "NpcMrg3.Mrg")):
        print("SKIP 找不到 NpcMrg3.Mrg")
        return 0
    gw = G.Gateway("127.0.0.1", 1, G.Items(""), maps=G.MapIndex(pic), npc=G.NpcIndex(pic), pic_dir=pic)
    check(gw.has_art("8105") and not gw.has_art("8122") and not gw.has_art("9522"), "8105 有真背景图；8122（钱庄）/ 9522（扬州农田）没有")
    check(gw.has_map("8105") and gw.has_map("8122") and gw.has_map("9522"), "三张图网页版都能去（缺图的画占位房间）")
    check(not gw.has_map("99999999"), "什么数据都没有的图仍然去不了")
    check(gw.cell_of("8105") == 20 and gw.cell_of("8122") == 20, "城市 / 室内图一格 20 像素")
    check(gw.cell_of("9522") == 48, "缺背景的 95xx（农田）按 48")
    if gw.big is not None:
        check(gw.cell_of("5000") == 48 and gw.cell_of("9501") == 48, "大地图一格 48 像素")
    check(gw.room_of("8105") is None, "有背景图的图没有占位房间")
    r = gw.room_of("8122")
    npcs = gw.npc.get("8122")
    check(r and r["cell"] == 20 and r["w"] >= 800 and r["h"] >= 600 and r["w"] >= max(n["x"] for n in npcs) * 20 and r["h"] >= max(n["y"] for n in npcs) * 20,
          "8122 占位房间 %s：至少 40 × 30 格、装得下全部 NPC" % (r,))
    r = gw.room_of("9522")
    check(r and r["cell"] == 48 and r["w"] >= 1440 and r["h"] >= 1440 and r["w"] % 48 == 0, "9522 占位房间 %s：至少 30 × 30 格（1440 px）" % (r,))
    z = gw.npc.zones("8122")
    check(r is not None and z and gw.room_of("8122")["w"] >= (z[0]["x"] + 1) * 20, "門也在房间里")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
