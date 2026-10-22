#!/usr/bin/env python3
"""预生成武功动画：web/sprites/fx/<图片名>.png（调色板 PNG，0 色透明）+ web/sprites/fx/index.json（技能 id -> 帧表）。

    python build_fx.py            # 全部（381 张图，2147 个技能）
    python build_fx.py --skills 800301,100601   # 只生成这些技能用到的图（调试）

index.json：{"版本":2,"skills":{"800301":{"v":2,"f":6,"sp":15,"fr":[["151",x0,y0,x1,y1,d,a,b],...]}, ...}}
  sp = 帧速度参数（见 kkfdata.py 说明），fr 每项 = [图片名, 矩形x0,y0,x1,y1, 图片槽位序号d, 偏移a, 偏移b]。
  v = 段数（d 的最大值+1），f = 总帧数/段数（仅供参考，各段帧数常不等），fr = 全部帧 [图片名,x0,y0,x1,y1,d]（按 KKF 顺序，时间线）。
图片来自 share\\pic\\KongFu*.mrg，每张是一列竖排帧序列（RLE6，调色板 565，0 号色 = 透明）。
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "资源解析"))
import evtdata  # noqa: E402
import kkfdata  # noqa: E402
import wjres  # noqa: E402
from PIL import Image  # noqa: E402

OUT = os.path.join(HERE, "web", "sprites", "fx")


def mrg_images(share):
    """图片名 -> (mrg 文件, 记录字节)，按 KongFu*.mrg 的顺序，先到先得。"""
    found = {}
    for f in sorted(glob.glob(os.path.join(share, "pic", "[Kk]ong[Ff]u*.mrg"))):
        m = evtdata.mrg_open(f)
        for k in m.keys():
            if k not in found:
                v = m[k]
                found[k] = (os.path.basename(f), v[0] if isinstance(v, (tuple, list)) else v)
    return found


def save_png(rec, path):
    w, h, cw, ch, idx, pal = wjres.decode_rle6(rec)
    im = Image.frombytes("P", (w, h), bytes(idx))
    flat, alpha = [], bytearray(256)
    for i in range(256):
        v = pal[i] if i < len(pal) else 0
        r, g, b = wjres.RGB[v]
        flat += [r, g, b]
        alpha[i] = 0 if v == 0 else 255
    im.putpalette(flat)
    im.save(path, optimize=True, transparency=bytes(alpha))
    return w, h


def frame_table(rec):
    """KKF 记录 -> {"v","f","fr"}：每帧取第一个 A 项（原版一帧一图；有多项时取第一项并记下其余的数量）。"""
    fr, var = [], []
    for f in rec["frames"]:
        a = f["A"][0] if f["A"] else None
        if a is None:
            fr.append(None)
            continue
        x0, y0, x1, y1 = a["rect"]
        sx = a["a"] - 65536 if a["a"] >= 32768 else a["a"]          # a / b 是有符号 16 位像素偏移
        sy = a["b"] - 65536 if a["b"] >= 32768 else a["b"]
        fr.append([a["name"], x0, y0, x1, y1, a["d"], sx, sy])
        var.append(a["d"])
    nv = (max(var) + 1) if var else 1
    return {"v": nv, "f": max(1, len(fr) // nv), "sp": rec.get("speed", 15), "fr": [x for x in fr if x]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills", default="")
    ap.add_argument("--share", default=kkfdata.SHARE)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    idx = kkfdata.kkf_index()
    want = [s for s in a.skills.split(",") if s] or sorted(idx)
    skills, need = {}, set()
    for s in want:
        r = kkfdata.skill_anim(s)
        if not r:
            continue
        t = frame_table(r)
        skills[s] = t
        need.update(x[0] for x in t["fr"])
    imgs = mrg_images(a.share)
    t0, done, miss = time.time(), 0, []
    for n in sorted(need):
        p = os.path.join(OUT, n + ".png")
        if os.path.isfile(p) and not a.force:
            continue
        if n not in imgs:
            miss.append(n)
            continue
        try:
            save_png(imgs[n][1], p)
            done += 1
        except Exception as e:      # noqa: BLE001
            miss.append("%s(%s)" % (n, e))
    # 只留图片存在的技能
    have = {s: t for s, t in skills.items() if all(os.path.isfile(os.path.join(OUT, x[0] + ".png")) for x in t["fr"])}
    ip = os.path.join(OUT, "index.json")
    old = {}
    if a.skills and os.path.isfile(ip):
        with open(ip, encoding="utf8") as f:
            old = json.load(f).get("skills", {})
    old.update(have)
    with open(ip, "w", encoding="utf8") as f:
        json.dump({"版本": 2, "skills": old}, f, ensure_ascii=False, separators=(",", ":"))
    print("技能 %d（有图 %d）| 新生成图 %d | 缺 %d %s | %.1fs" % (len(skills), len(have), done, len(miss), miss[:6], time.time() - t0))


if __name__ == "__main__":
    main()
