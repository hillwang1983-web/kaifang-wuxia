#!/usr/bin/env python3
"""人物精灵图集生成器：每个"层 × 调色板套"一张小图集，只含站立(CP7)和行走(CP1)，8 个方向。

库用法（网关按需调用，生成后缓存在 web\\sprites\\<模型>\\ 下）:
    ensure_layer(model, "M1MA01", 1)  ->  web/sprites/1/M1MA01_1.png + .json
命令行:
    python build_sprites.py --model 1                 # 预生成身体、阴影、默认头发 (M1MA01 的第 1 套调色板)
    python build_sprites.py --model 1 --layer M1PA01 --set 2

依据（动作表\\动作表说明.md、资源格式说明.md，以及 loginp.exe 0x521be4 的反编译）：
  * 模型号 -> mrg / 身体层 / 阴影层：动作表\\action_table.web.json 的 models[]
  * ROLE\\<层>.CP<n>：n=动作号（7 站立，1 行走）；文件帧号 = 方向*每方向帧数 + 帧号
  * 调色板：.cp 记录自带的是第 0 套；<mrg 同名>.pal 里每个层名一个块，6 套 × 256 色 RGB565，第 k 套 = 换色版 k。
    外观码 "ma0101" 的最后两位 = 调色板套号（客户端 0x5253c8 里 调色板地址 = 基址 + 套号*0x200，即 256 色*2 字节）
输出 JSON：{"cps":{"7":{"fpd":8,"frames":[[x,y,w,h,ox,oy]|null,...]},"1":{...}}}，帧按文件帧号排列，null = 空帧。
"""
import argparse
import json
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "资源解析"))
import wjres  # noqa: E402

TABLE = os.path.join(HERE, "动作表", "action_table.web.json")
ROLE_DIR = os.path.normpath(os.path.join(HERE, "..", "share", "role"))
OUT_DIR = os.path.join(HERE, "web", "sprites")
CPS = (7, 1)          # 站立、行走


def model_info(model):
    table = json.load(open(TABLE, encoding="utf8"))
    return next((m for m in table["models"] if m["model"] == model), None)


class RoleFile:
    """一个 role\\*.mrg：层名表 + 解码。"""

    def __init__(self, model):
        self.model = model
        mod = model_info(model)
        if not mod:
            raise ValueError("动作表里没有模型 %d" % model)
        self.mod = mod
        self.path = os.path.join(ROLE_DIR, mod["mrg"])
        self.mrg = wjres.Mrg(self.path)
        self.body = mod["bodyLayer"].upper()
        self.shadow = (mod.get("shadowLayer") or "").upper() or None
        self.prefix = re.match(r"^([A-Za-z]\d+)0000$", self.body, re.I).group(1).upper()
        self.names = {n.upper(): i for i, n in enumerate(self.mrg.names[:self.mrg.count])}
        self.layers = sorted({m.group(1).upper() for n in self.names for m in [re.match(r"^ROLE\\(.+)\.CP\d+$", n)] if m})
        pal = wjres.find_pal(self.path)
        self.pals = wjres.load_pal(pal) if pal else {}

    def has_layer(self, layer):
        return layer.upper() in self.layers

    def palette(self, layer, pal_set, embedded):
        """第 pal_set 套调色板；0 或没有 .pal 记录时用 .cp 自带的。"""
        if pal_set == 0:
            return embedded
        blk = self.pals.get(layer.lower())
        if not blk or pal_set >= len(blk):
            return embedded
        return blk[pal_set]


def build_layer(rf: RoleFile, layer, pal_set, out_dir):
    from PIL import Image  # noqa: F401  （wjres 已经检查过）
    layer = layer.upper()
    atlas = wjres.Atlas(4096)
    for cp in CPS:
        i = rf.names.get(("ROLE\\%s.CP%d" % (layer, cp)).upper())
        if i is None:
            continue
        parsed = wjres.parse_cp(rf.mrg.get(i))
        if not parsed:
            continue
        pal, frames = parsed
        pal = rf.palette(layer, pal_set, pal)
        for fi, (ox, oy, w, h, comp) in enumerate(frames):
            if not w or not h:
                continue
            idx = wjres.lzss(comp, w * h)
            if len(idx) < w * h:
                idx = idx + bytes(w * h - len(idx))
            atlas.add(wjres.idx_to_rgba(idx, w, h, pal), {"cp": cp, "frame": fi, "ox": ox, "oy": oy, "n": len(frames)})
    if not atlas.items:
        return False
    os.makedirs(out_dir, exist_ok=True)
    base = "%s_%d" % (layer, pal_set)
    items = atlas.save(out_dir, prefix=base)
    if len({it["page"] for it in items}) != 1:
        raise RuntimeError("层 %s 的图集超过一页，调大页面" % layer)
    page = items[0]["page"]
    out = {"page": page, "cps": {}}
    for it in items:
        ent = out["cps"].setdefault(str(it["cp"]), {"fpd": it["n"] // 8, "frames": [None] * it["n"]})
        ent["frames"][it["frame"]] = [it["x"], it["y"], it["w"], it["h"], it["ox"], it["oy"]]
    os.replace(os.path.join(out_dir, page), os.path.join(out_dir, base + ".png"))
    out["page"] = base + ".png"
    tmp = os.path.join(out_dir, base + ".json.tmp")
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(tmp, os.path.join(out_dir, base + ".json"))      # json 最后落盘：有 json 就说明 png 已经好了
    return True


_roles = {}
_lock = threading.Lock()


def get_role(model):
    """RoleFile 缓存（整个 mrg 读进内存，boy01 约 15MB，所以每个模型只留一份）。模型不存在返回 None。"""
    with _lock:
        if model not in _roles:
            try:
                _roles[model] = RoleFile(model)
            except Exception:
                _roles[model] = None
        return _roles[model]


def ensure_layer(model, layer, pal_set, out_root=OUT_DIR):
    """返回 (png 路径, json 路径)；没有就生成。层不存在 / 模型不存在返回 None。线程安全（网关在线程池里调用）。"""
    rf = get_role(model)
    with _lock:
        layer = layer.upper()
        if rf is None or not rf.has_layer(layer) or not 0 <= pal_set <= 5:
            return None
        out_dir = os.path.join(out_root, str(model))
        base = os.path.join(out_dir, "%s_%d" % (layer, pal_set))
        if not os.path.isfile(base + ".json"):
            if not build_layer(rf, layer, pal_set, out_dir):
                return None
        return base + ".png", base + ".json"


def export_roles(models, out_root=OUT_DIR):
    """把每个模型的 {前缀, 身体层, 阴影层, 层名表} 写成 roles.json：打包到没有 role\\*.mrg / Pillow 的机器上时，网关靠它知道哪些层存在。"""
    meta = {}
    try:                                    # 合并已有的：一次只生成一个模型时别把别的模型从 roles.json 里弄丢
        with open(os.path.join(out_root, "roles.json"), encoding="utf8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        pass
    for m in models:
        rf = get_role(m)
        if rf:
            meta[str(m)] = {"prefix": rf.prefix, "body": rf.body, "shadow": rf.shadow, "layers": rf.layers}
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, "roles.json"), "w", encoding="utf8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return meta


def build_all(model, out_root=OUT_DIR):
    """某个模型的全部层 × 调色板套 0..5（阴影 / 身体只有第 0 套）。返回生成的 (层, 套) 数。"""
    rf = get_role(model)
    n = 0
    for layer in rf.layers:
        for s in ([0] if layer in (rf.body, rf.shadow) else range(6)):
            if ensure_layer(model, layer, s, out_root):
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", type=int, default=1)
    ap.add_argument("--layer", help="只生成这一层（如 M1PA01）；不给则预生成身体、阴影、默认头发")
    ap.add_argument("--set", type=int, default=0, help="调色板套号 0..5")
    ap.add_argument("--all", action="store_true", help="生成这个模型的全部层 × 调色板套，并写 roles.json（打包用）")
    a = ap.parse_args()
    rf = RoleFile(a.model)
    print("模型 %d：%s，层 %s" % (a.model, rf.mod["mrg"], " ".join(rf.layers)))
    if a.all:
        n = build_all(a.model)
        export_roles([a.model])
        print("生成 %d 个层图集，roles.json 已写入 %s" % (n, OUT_DIR))
        return
    todo = [(a.layer.upper(), a.set)] if a.layer else [(rf.body, 0), (rf.shadow, 0), (rf.prefix + "MA01", 1)]
    for layer, s in todo:
        if layer:
            r = ensure_layer(a.model, layer, s)
            print("  %s 套%d -> %s" % (layer, s, r[0] if r else "没有这一层"))


if __name__ == "__main__":
    main()
