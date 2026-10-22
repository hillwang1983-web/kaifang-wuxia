#!/usr/bin/env python3
"""地图前景物件贴图（建筑 / 树等的抠图）：从 pic\\Scene*.mrg 里按物件名取 rle6 图，转成带透明的 PNG，缓存在 web\\objects\\。

物件列表（名字、位置、大小）在 dat\\WSG*.dat 每张图记录的碰撞位图后面，见 gateway.WalkIndex.objects；
物件图叠在背景上的位置 = (x, y) 左上角，已用像素差验证（偏 1 像素误差就明显变大）。

库用法:   ensure_object("280135", 160, 119) -> PNG 路径 | None
命令行:   python build_objects.py --map 2801        # 这张图的全部物件
          python build_objects.py --all             # 所有地图（4231 张不同的图，几分钟到十几分钟，打包用）
"""
import argparse
import glob
import math
import os
import re
import struct
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "资源解析"))
import wjres  # noqa: E402

PIC_DIR = os.path.normpath(os.path.join(HERE, "share", "pic") if os.path.isdir(os.path.join(HERE, "share", "pic")) else os.path.join(HERE, "..", "share", "pic"))
OUT_DIR = os.path.join(HERE, "web", "objects")
_lock = threading.Lock()
_mrgs = {}          # 文件 -> wjres.Mrg（整个文件读进内存，只留用到的）
_index = None       # 物件名 -> [(文件, 记录号)]


def _build_index(pic_dir):
    idx = {}
    files = sorted(glob.glob(os.path.join(pic_dir, "[sS]cene*.[mM][rR][gG]")) + glob.glob(os.path.join(pic_dir, "ScenePic.mrg")))
    seen = set()
    for fn in files:
        if os.path.basename(fn).lower().startswith("scenebg") or fn.lower() in seen:
            continue
        seen.add(fn.lower())
        try:
            with open(fn, "rb") as f:
                head = f.read(8)
                if len(head) < 8:
                    continue
                n, nl = struct.unpack("<II", head)
                f.read(13 * n)
                names = f.read(nl).decode("gbk", "replace").split("\r\n")[:n]
        except OSError:
            continue
        for i, nm in enumerate(names):
            if nm.isdigit():
                idx.setdefault(nm, []).append((fn, i))
    return idx


def _mrg(fn):
    if fn not in _mrgs:
        _mrgs[fn] = wjres.Mrg(fn)
    return _mrgs[fn]


def ensure_object(name, w, h, pic_dir=PIC_DIR, out_dir=OUT_DIR):
    """物件图 PNG 的路径（没有就生成）；同名图在多个 Scene*.mrg 里时选尺寸等于 (w,h) 的那个。找不到返回 None。"""
    global _index
    if not re.fullmatch(r"\d{5,9}", name):
        return None
    out = os.path.join(out_dir, "%s_%dx%d.png" % (name, w, h))
    if os.path.isfile(out):
        return out
    with _lock:
        if _index is None:
            _index = _build_index(pic_dir)
        for fn, i in _index.get(name, []):
            rec = _mrg(fn).get(i)
            t = wjres.parse_rle6(rec)
            if not t or (t[0], t[1]) != (w, h):
                continue
            try:
                iw, ih, cw, ch, idx, pal = wjres.decode_rle6(rec)
            except ValueError:
                continue
            os.makedirs(out_dir, exist_ok=True)
            tmp = out + ".tmp"
            wjres.idx_to_rgba(idx, iw, ih, pal).save(tmp, format="PNG", optimize=False)
            os.replace(tmp, out)
            return out
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", help="只生成这张地图的物件")
    ap.add_argument("--all", action="store_true", help="所有地图的所有物件")
    ap.add_argument("--dat", default=os.path.normpath(os.path.join(HERE, "..", "share", "dat")))
    a = ap.parse_args()
    import gateway
    walk = gateway.WalkIndex(a.dat)
    maps = [a.map] if a.map else sorted(walk.index) if a.all else []
    if not maps:
        ap.error("给 --map <编号> 或 --all")
    done = missing = 0
    seen = set()
    for mid in maps:
        for o in walk.objects(mid):
            key = (o["n"], o["w"], o["h"])
            if key in seen:
                continue
            seen.add(key)
            if ensure_object(o["n"], o["w"], o["h"], os.path.normpath(os.path.join(a.dat, "..", "pic"))):
                done += 1
            else:
                missing += 1
    print("物件图 %d 张已就绪，%d 张在 Scene*.mrg 里找不到" % (done, missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
