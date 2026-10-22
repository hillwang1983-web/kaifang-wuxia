#!/usr/bin/env python3
"""NPC / 怪物精灵图集：型号 -> 精灵号（share\\dat\\Npc*.Dat 记录 +0x19，见 npcdat.py）-> role\\npc*.mrg 里的 ROLE\\<精灵号>{S,W,A}.CP。

  S = 站立（8 方向 × 4 帧）  W = 行走（8 方向 × 8 帧）  A = 攻击（8 方向 × n 帧）。文件帧号 = 方向*每方向帧数 + 帧号，方向顺序同人物（上、左上、左、左下、下、右下、右、右上）。
输出：web/sprites/npc/<精灵号>.png + .json，JSON = {"page":..,"cps":{"S":{"fpd":4,"frames":[[x,y,w,h,ox,oy]|null..]}, "W":.., "A":..}}（ox/oy 相对脚下）。

    python build_npc_sprites.py --id 10111          # 单个
    python build_npc_sprites.py --models 38166 38268  # 按型号（先查 Npc*.Dat）
    python build_npc_sprites.py --all               # 全部精灵号（要几分钟）
"""
import argparse
import glob
import json
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "资源解析"))
sys.path.insert(0, HERE)
import npcdat  # noqa: E402

ROLE_DIR = os.path.normpath(os.path.join(HERE, "..", "share", "role"))
OUT_DIR = os.path.join(HERE, "web", "sprites", "npc")
KINDS = ("S", "A")            # 站立 / 攻击；行走 W 体积大且 NPC / 怪在战斗里用不上，不生成
_lock = threading.Lock()
_index = None            # 精灵号 -> {"S": (mrg 对象, 下标), ...}
_tables = None


def sprite_files():
    """role\\npc*.mrg 里全部 ROLE\\<数字>{S,W,A}.CP；同一个精灵号出现在多个 mrg 里时取文件名排序靠后的（和 NpcMrg 一样取最新）。"""
    global _index
    if _index is None:
        import wjres
        idx = {}
        for f in sorted(glob.glob(os.path.join(ROLE_DIR, "npc*.mrg"))):
            try:
                m = wjres.Mrg(f)
            except Exception:
                continue
            for i, n in enumerate(m.names[:m.count]):
                g = re.match(r"^ROLE\\(\d+)([SWA])\.CP$", n, re.I)
                if g:
                    idx.setdefault(int(g.group(1)), {})[g.group(2).upper()] = (m, i)
        _index = idx
    return _index


def tables():
    """[Npc3, Npc1, Npc] 三张表（解码后 {型号: 记录}），按这个顺序查。"""
    global _tables
    if _tables is None:
        _tables = [npcdat.load(os.path.join(npcdat.DAT_DIR, f)) for f in ("Npc3.Dat", "Npc1.Dat", "Npc.Dat")]
    return _tables


def sprite_of(model, exists=None):
    """型号 -> 精灵号（没有记录 / 精灵不存在返回 None）。exists(精灵号) 判断精灵是否存在，缺省看 role\\npc*.mrg。"""
    import struct
    exists = exists or (lambda s: s in sprite_files())
    for t in tables():
        r = t.get(model)
        if r is not None:
            s = struct.unpack_from("<H", r, 0x19)[0]
            if s and exists(s):
                return s
    return None


def build(sprite_id, out_dir=OUT_DIR):
    """生成一个精灵号的图集；返回 True / False（没有这个精灵）。"""
    import wjres
    files = sprite_files().get(sprite_id)
    if not files:
        return False
    atlas = wjres.Atlas(4096)
    n_items = 0
    for kind in KINDS:
        if kind not in files:
            continue
        m, i = files[kind]
        parsed = wjres.parse_cp(m.get(i))
        if not parsed:
            continue
        pal, frames = parsed
        for fi, (ox, oy, w, h, comp) in enumerate(frames):
            if not w or not h:
                continue
            idx = wjres.lzss(comp, w * h)
            if len(idx) < w * h:
                idx = idx + bytes(w * h - len(idx))
            atlas.add(wjres.idx_to_rgba(idx, w, h, pal), {"cp": kind, "frame": fi, "ox": ox, "oy": oy, "n": len(frames)})
            n_items += 1
    if not n_items:
        return False
    os.makedirs(out_dir, exist_ok=True)
    base = str(sprite_id)
    items = atlas.save(out_dir, prefix=base)
    pages = sorted({it["page"] for it in items})
    from PIL import Image
    for pg in pages:                      # 256 色 PNG（原图本来就是调色板色），体积约 1/3
        p = os.path.join(out_dir, pg)
        Image.open(p).convert("RGBA").quantize(colors=256, method=Image.FASTOCTREE, dither=Image.NONE).save(p, optimize=True)
    out = {"cps": {}, "pages": pages}
    for it in items:
        ent = out["cps"].setdefault(it["cp"], {"fpd": it["n"] // 8, "frames": [None] * it["n"]})
        ent["frames"][it["frame"]] = [it["x"], it["y"], it["w"], it["h"], it["ox"], it["oy"], pages.index(it["page"])]
    tmp = os.path.join(out_dir, base + ".json.tmp")
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(tmp, os.path.join(out_dir, base + ".json"))       # json 最后落盘：有 json 就说明 png 已经好了
    return True


def ensure(sprite_id, out_root=OUT_DIR):
    """返回 json 路径；没有就生成（线程安全）；精灵不存在返回 None。"""
    p = os.path.join(out_root, "%d.json" % sprite_id)
    with _lock:
        if not os.path.isfile(p) and not build(sprite_id, out_root):
            return None
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", type=int, nargs="*", default=[])
    ap.add_argument("--models", type=int, nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    ids = list(a.id) + [s for s in (sprite_of(m) for m in a.models) if s]
    if a.all:
        ids = sorted(sprite_files())
    total = 0
    for k, s in enumerate(ids):
        ok = build(s, a.out)
        total += bool(ok)
        if a.all and k % 50 == 0:
            print(k, len(ids), flush=True)
    print("生成 %d / %d 个精灵号 -> %s" % (total, len(ids), a.out))


if __name__ == "__main__":
    main()
