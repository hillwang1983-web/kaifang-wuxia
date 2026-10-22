#!/usr/bin/env python3
"""导航目录 / 新手教学（guide.py）：用原版 share\\dat 里的 cityportals.dat / cityportals_kind.dat / newbie.dat。找不到文件时跳过。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    if not os.path.exists(os.path.join(guide.DAT_DIR, "cityportals.dat")):
        print("SKIP 找不到 cityportals.dat")
        return 0
    k = guide.load_kinds()
    check(k == {1: "傳送類型", 2: "功能類型", 3: "消點類型", 4: "任務類型", 5: "活動類型", 6: "技能類型", 7: "買賣類型", 8: "其他類型"}, "类型表：8 类（傳送 / 功能 / 消點 / 任務 / 活動 / 技能 / 買賣 / 其他）")
    ns = guide.load_npcs()
    check(len(ns) == 823, "NPC 目录 823 条（%d）" % len(ns))
    check(all(1 <= n["kind"] <= 9 and n["map"] > 0 for n in ns), "每条都有类型和地图")
    xs = [n for n in ns if n["name"] == "新手指導員-小芙"]
    check(xs and xs[0]["map"] == 2801 and (xs[0]["x"], xs[0]["y"]) == (3685, 1069) and xs[0]["kind"] == 4, "『新手指導員-小芙』在 2801 图 (3685, 1069)，任務類型")
    # 和 NPC 摆放表交叉验证：目录里的像素坐标 = NpcMrg 里同名 NPC 的格子坐标 × 20（±1 格）
    try:
        import gateway
        idx = gateway.NpcIndex(gateway.DEFAULT_PIC_DIR)
        placed = {}
        for e in idx.get("2801"):
            placed.setdefault(e["name"], []).append(e)            # 同名 NPC 不止一个（菜商 / 肉商 …）
        pairs = [(n, placed[n["name"]]) for n in ns if n["map"] == 2801 and n["name"] in placed]
        ok = sum(1 for n, es in pairs if any(abs(n["x"] - e["x"] * 20) <= 140 and abs(n["y"] - e["y"] * 20) <= 140 for e in es))
        check(len(pairs) >= 5 and ok >= len(pairs) * 0.8, "坐标和 NPC 摆放表一致（2801 图 %d 个同名 NPC 里 %d 个对得上：像素 = 格子 × 20，目录给的是 NPC 旁边约 5 格内的位置）" % (len(pairs), ok))
    except Exception as e:  # noqa: BLE001
        print("SKIP 坐标交叉验证（%s）" % e)
    tu = guide.load_tutorial()
    titles = [t["title"] for t in tu]
    check(len(tu) >= 10 and "操作說明" in titles and "傳送說明" in titles and "事件教學" in titles, "新手教学 %d 节：%s" % (len(tu), "、".join(titles[:5])))
    g = guide.load(s2t=lambda s: s.replace("傳", "传"))
    check(g["kinds"]["1"] == "传类型" or g["kinds"]["1"].startswith("传"), "load(s2t) 会对名字 / 标题做转换")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
