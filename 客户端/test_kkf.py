#!/usr/bin/env python3
"""武功动画解析（kkfdata.py）和预生成产物（build_fx.py -> web/sprites/fx）的回归测试。需要 share\\dat\\KKF*.dat（没有就跳过解析部分）。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kkfdata  # noqa: E402

ok = bad = 0


def check(c, msg):
    global ok, bad
    if c:
        ok += 1
        print("PASS", msg)
    else:
        bad += 1
        print("FAIL", msg)


if os.path.isfile(os.path.join(kkfdata.SHARE, "dat", "KKF.dat")):
    r = kkfdata.skill_anim(800301)
    check(r is not None and r["nseg"] == 12 and r["head"][4] == 6, "基本剑法 800301：12 帧、每变体 6 帧")
    fr = r["frames"]
    check([f["A"][0]["name"] for f in fr] == ["151"] * 6 + ["152"] * 6, "800301：前 6 帧图 151，后 6 帧图 152")
    check(fr[0]["A"][0]["rect"] == (0, 0, 150, 149) and fr[1]["A"][0]["rect"] == (0, 150, 150, 299), "800301：矩形 = 150×150 竖排")
    check([f["A"][0]["d"] for f in fr] == [0] * 6 + [1] * 6, "800301：段编号 d = 0 / 1（d 是第几段，不是朝向：多数技能各段帧数不等）")
    check(kkfdata.skill_anim(900001)["nseg"] == 15, "900001：15 帧（KKF2）")
    check(r["speed"] == 15 and kkfdata.skill_anim(801401)["speed"] == 33 and kkfdata.skill_anim(900001)["speed"] == 142, "速度参数（记录尾部 i16）：800301=15、801401=33、900001=142")
    check(all(f["A"][0]["a"] in (1, 2) and f["A"][0]["b"] in (1, 2, 4) for f in kkfdata.skill_anim(800301)["frames"]) , "800301：每帧偏移 a,b 是 1–4 像素的小数")
    check(kkfdata.skill_anim(1) is None or True, "未收录的 id 不抛异常")
    idx = kkfdata.kkf_index()
    allok = True
    for k, (fn, d) in list(idx.items())[:400]:
        try:
            kkfdata.parse_record(d)
        except Exception:
            allok = False
    check(allok, "前 400 条记录全部能解析")
    check(kkfdata.skill_anim(0x1b0d0)["key"] == str(0x1b071), "键重映射（FUN_00984420）：0x1b0d0 -> 0x1b071") if kkfdata.skill_anim(0x1b0d0) else check(True, "重映射目标不在表里，跳过")

ip = os.path.join(HERE, "web", "sprites", "fx", "index.json")
if os.path.isfile(ip):
    j = json.load(open(ip, encoding="utf8"))["skills"]
    check("800301" in j and j["800301"]["v"] == 2 and j["800301"]["f"] == 6 and len(j["800301"]["fr"]) == 12, "index.json：800301 = 2 张图 × 6 帧")
    check(j["800301"]["sp"] == 15 and len(j["800301"]["fr"][0]) == 8, "index.json：带速度参数 sp 和每帧偏移 a,b（版本 2）")
    miss = [x[0] for s in list(j.values())[:300] for x in s["fr"] if not os.path.isfile(os.path.join(HERE, "web", "sprites", "fx", x[0] + ".png"))]
    check(not miss, "index.json 引用的图片都存在（抽查前 300 个技能）")
    check(len(j) > 2000, "index.json 收录 2000+ 个技能（现 %d）" % len(j))
else:
    print("SKIP 没有 web/sprites/fx/index.json（先跑 build_fx.py）")

print("\n%d/%d 通过" % (ok, ok + bad))
sys.exit(1 if bad else 0)
