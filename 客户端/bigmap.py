#!/usr/bin/env python3
"""大地图（野外 / 世界地图，1000 / 2000 … 8000 等）渲染：pic\\MapMrg*.Mrg 的地块表 + pic\\Pan_J*.mrg 的地面贴图。

2026-10-21 从 loginp.exe 的地图绘制代码读出来（0x92760a 画格子、0x9271f8 地面类型 → 贴图、0x927568 贴图取点、0x927d3c / 0x927b64 邻格过渡）：

MapMrg 记录（LZSS 解压后）：`宽 u16 | 高 u16 | 01 01 |` 然后 宽×高 个 5 字节的格子（行优先），之后是别的层（建筑 / 树等，本模块没处理）。
  格子 = 地面类型 b0 | 变体 b1（0..13，过渡遮罩的列号）| 标记 b2（非 0 的格子原版不画地面）| b3 b4（上层物件，没解）
  一格 48 × 48 像素；267 × 200 格 = 12816 × 9600 像素。
地面类型 → 贴图：类型码经 0x927388（一张 101 项的跳转表）得到优先级 F（0..34），贴图名 = NAMES[TBL[F]]（见下）；贴图是 Pan_J*.mrg 里的 480 × 384 JPEG
  （10 × 8 格），格 (x, y) 取贴图里 ((x % 10) × 48, (y % 8) × 48) 起的 48 × 48；类型 1 / 2 / 3 / 10（毒 / 血 / 火石 / 绿水）是会滚动的液体，这里取静态：% 9 / % 7。
邻格过渡：对格子周围 8 个邻格，邻格的 F 比自己大的，把邻格的贴图（取点和自己一样）用遮罩叠到自己上：遮罩在 Pan_Com.mrg 的 `mask3`（720 × 384 的 2 色图，
  15 列 × 8 行，每格 48 × 48），列 = 邻格的变体 b1，行 = 7 − 邻格序号（序号按 (x−1,y−1) (x−1,y) (x−1,y+1) (x,y−1) (x,y+1) (x+1,y−1) (x+1,y) (x+1,y+1)）；
  遮罩里调色板索引 0（白）= 显示邻格的贴图。水（类型 80..94）对水不画过渡。
同一张图在好几个 MapMrg 文件里都有（旧版本），取文件号最大的。

载入函数 0x92819c 的读法：宽 / 高 u16、两个字节（各减 0x80）、格子（按列，每列 0x960 字节）、4 节物件 `个数 i32 | 个数 × 12 字节`、
  8 字节、0x54C91 字节的碰撞位图（见 collision()）。

物件层（2026-10-22 从数据看出来，叠到地面上目测对）：格子数据后面是 3 节 `个数 i32 | 个数 × (精灵号 i32, x i32, y i32)`（x / y 是格，
  可为负，按 y 排好序），第 4 节一般是空的（0），然后是碰撞位图。
  第 0 节 = 大块拼图（城墙 / 城内建筑 / 成片树林，切成矩形块）、第 1 节 = 单个立物（树 / 灌木 / 箭楼 / 草）、第 2 节 = 少量上层。
  精灵画在 (x × 48, y × 48)（左上角对齐，相邻拼块正好接上），先画第 0 节、再第 1 节、再第 2 节，节内按 (y, x)。
  精灵来源（按顺序找）：Pan_Com*.mrg（记录名 = 精灵号）、ScenePic.mrg（%03d）、KcomMrg*.mrg（t%05d，石碑 / 桌子一类）。都是 rle6：
  `w h cw ch 调色板字节数 p | 调色板 RGB565（偏移 20）| 数据（偏移 24 + p）`，颜色 0 = 透明。号码同样对得上的 smlanti.mrg（漫画头像）
  和 FlashPic*.mrg（武功特效）不是地图物件。找不到的（2600–2603、3428–3457、1136、200、1010–1023、2000–2048 …）随客户端带的资源里没有，跳过。
"""
import io
import os
import re
import struct

import numpy as np
from PIL import Image

CELL = 48
SUB = 16                     # 碰撞小格边长（一格 = 3 × 3 小格）
COLL_STRIDE = 0x5A1          # 碰撞位图：每 8 列小格一组，组内按行 1441 字节
COLL_BYTES = 0x54C91         # 碰撞位图固定长度（loginp.exe 0x928b38）
# 0x927388：地面类型 -> 优先级 F；TBL（0xa25bd4，8 字节一项）：F -> 贴图名序号；NAMES（0xa258f0，21 字节一项）
F = {0: 0, 1: 1, 2: 2, 3: 3, 4: 5, 8: 6, 10: 4, 12: 7, 20: 8, 24: 9, 30: 10, 34: 11, 35: 12, 36: 13, 37: 14, 38: 15, 40: 16, 44: 17, 48: 18, 52: 19, 54: 20,
     56: 21, 60: 22, 62: 23, 64: 24, 80: 25, 84: 26, 88: 27, 90: 28, 92: 29, 94: 30, 96: 31, 98: 32, 99: 33, 100: 34}
TBL = [0, 1, 2, 3, 4, 5, 21, 6, 7, 14, 15, 13, 29, 30, 31, 8, 9, 10, 11, 12, 26, 27, 22, 16, 17, 18, 19, 20, 23, 24, 25, 28, 32, 33, 34]
NAMES = ["Dirt1", "Poison", "Blood", "FireSt", "GWater2", "Dirt2", "Dirt3", "Road1", "Desert1", "Leave", "Grass1", "Grass2", "Grass3", "Desert2", "StonePlace1",
         "MudPlace1", "Ice1", "Snow1", "Water1", "Water2", "Water3", "Dirt4", "SnowGround", "Water4", "Water5", "Water6", "Grass4", "Grass5", "GWater1",
         "Desert3", "Desert4", "DRoad", "water13", "water14", "water15"]
LIQUID = {1, 2, 3, 10}          # 会滚动的液体类型
WATER = range(0x50, 0x5F)       # 水：水对水不画过渡
NEIGH = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]     # 邻格序号 -> (dx, dy)

_MAGIC = b"\x56\x8d\x0f\x20"


def _lzss(src, outlen):
    """LZSS（loginp.exe FUN_004a7f50，和 npcdata.lzss 一样）"""
    import npcdata
    return npcdata.lzss(src, outlen)


class Mrg:
    """.mrg 容器（记录名 -> 字节）"""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        cnt, nl = struct.unpack_from("<II", self.data, 0)
        names = self.data[8 + 13 * cnt:8 + 13 * cnt + nl].decode("gbk", "replace").split("\r\n")
        self.base = 8 + 13 * cnt + nl
        self.recs = {}
        for i in range(cnt):
            size, off = struct.unpack_from("<II", self.data, 8 + 13 * i)
            self.recs[names[i].lower()] = (self.base + off, size)

    def get(self, name):
        e = self.recs.get(name.lower())
        return None if e is None else self.data[e[0]:e[0] + e[1]]


def _rle6(rec):
    """rle6 带调色板位图 -> (w, h, 索引 numpy 数组 (h, w), 调色板列表)"""
    w, h, cw, ch, p = struct.unpack_from("<5I", rec, 0)
    pal = list(struct.unpack_from("<%dH" % (p // 2), rec, 20))
    data = rec[24 + p:]
    out = bytearray()
    i = 0
    for _ in range(h):
        x = 0
        while x < w:
            c = data[i]
            if c == 0:
                k = w - x
                out += data[i + 1:i + 1 + k]
                i += 1 + k
                x = w
            else:
                out += data[i + 1:i + 2] * c
                i += 2
                x += c
    return w, h, np.frombuffer(bytes(out), dtype=np.uint8).reshape(h, w), pal


def sprite_rgba(rec):
    """物件精灵记录 -> numpy RGBA (h, w, 4)：rle6（颜色 0 透明）或 JPEG（近黑透明）"""
    if rec[:2] == b"\xff\xd8":
        a = np.asarray(Image.open(io.BytesIO(rec)).convert("RGB"))
        alpha = np.where(a.astype(np.int32).sum(2) < 40, 0, 255).astype(np.uint8)
        return np.dstack([a, alpha])
    w, h, idx, pal = _rle6(rec)
    p = np.array(pal[:256] + [0] * (256 - min(len(pal), 256)), dtype=np.uint32)
    lut = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31,
                    np.where(p == 0, 0, 255)], 1).astype(np.uint8)
    return lut[idx]


class Sprites:
    """大地图物件精灵：Pan_Com*.mrg（精灵号）/ ScenePic.mrg（%03d）/ KcomMrg*.mrg（t%05d）；按需解码并缓存。
    smlanti.mrg（T%04d+帧，是漫画头像）和 FlashPic*.mrg（408–647，是武功特效）号码对得上但不是地图物件，不要用"""

    def __init__(self, pic_dir):
        def mrgs(prefix):
            out = []
            for f in sorted(os.listdir(pic_dir)):
                if f.lower().startswith(prefix) and f.lower().endswith(".mrg"):
                    try:
                        out.append(Mrg(os.path.join(pic_dir, f)))
                    except (OSError, struct.error):
                        pass
            return out
        self.pan = mrgs("pan_com")
        self.scene = mrgs("scenepic")
        self.kcom = mrgs("kcommrg")
        self.cache = {}

    def record(self, sid):
        for m in self.pan:
            r = m.get(str(sid))
            if r:
                return r
        for m in self.scene:
            r = m.get("%03d" % sid)
            if r:
                return r
        for m in self.kcom:
            r = m.get("t%05d" % sid)
            if r:
                return r
        return None

    def get(self, sid):
        """-> numpy RGBA 或 None（资源里没有 / 解不开）"""
        if sid not in self.cache:
            r = self.record(sid) if sid > 0 else None
            try:
                self.cache[sid] = sprite_rgba(r) if r else None
            except (IndexError, ValueError, OSError, struct.error):
                self.cache[sid] = None
        return self.cache[sid]


class BigMaps:
    def __init__(self, pic_dir):
        self.pic = pic_dir
        self.index = {}                  # 地图编号 -> (文件, 文件号)
        files = [f for f in os.listdir(pic_dir) if re.fullmatch(r"(?i)mapmrg\d*\.mrg", f)]

        def order(f):
            m = re.search(r"(\d+)", f)
            return int(m.group(1)) if m else 1
        self._mrgs = {}
        for fn in sorted(files, key=order):
            try:
                with open(os.path.join(pic_dir, fn), "rb") as f:
                    cnt, nl = struct.unpack("<II", f.read(8))
                    f.seek(8 + 13 * cnt)
                    names = f.read(nl).decode("gbk", "replace").split("\r\n")
            except (OSError, struct.error):
                continue
            for nm in names[:cnt]:
                if nm.isdigit():
                    self.index[nm] = fn                     # 文件号大的覆盖小的
        self.cells = {}
        self._objs = {}
        self._spr = None
        self._tex = None
        self._mask = None
        self._tiles = {}
        self._walk = {}
        import threading
        self._lock = threading.RLock()

    def _mrg(self, fn):
        if fn not in self._mrgs:
            self._mrgs[fn] = Mrg(os.path.join(self.pic, fn))
        return self._mrgs[fn]

    def has(self, map_id):
        return str(map_id) in self.index

    def _record(self, k):
        fn = self.index.get(k)
        rec = self._mrg(fn).get(k) if fn else None
        if rec is not None and rec[:4] == _MAGIC:
            rec = _lzss(rec[8:], struct.unpack_from("<I", rec, 4)[0])
        return rec

    def sprites(self):
        with self._lock:
            if self._spr is None:
                self._spr = Sprites(self.pic)
            return self._spr

    def objects(self, map_id):
        """物件层 -> [(节, 精灵号, 像素 x, 像素 y, 宽, 高)]，按画的先后排好；资源里没有的精灵不收"""
        k = str(map_id)
        if k in self._objs:
            return self._objs[k]
        with self._lock:
            if k in self._objs:
                return self._objs[k]
            out = []
            rec = self._record(k)
            if rec is not None and len(rec) >= 6:
                w, h = struct.unpack_from("<HH", rec, 0)
                p = 6 + 5 * w * h
                spr = self.sprites()
                raw = []
                for sec in range(3):
                    if p + 4 > len(rec):
                        break
                    n = struct.unpack_from("<i", rec, p)[0]
                    if not 0 <= n <= 100000 or p + 4 + 12 * n > len(rec):
                        break
                    raw += [(sec,) + struct.unpack_from("<iii", rec, p + 4 + 12 * i) for i in range(n)]
                    p += 4 + 12 * n
                for sec, sid, x, y in sorted(raw, key=lambda o: (o[0], o[3], o[2])):
                    a = spr.get(sid)
                    if a is not None:
                        out.append((sec, sid, x * CELL, y * CELL, a.shape[1], a.shape[0]))
            self._objs[k] = out
            return out

    def grid(self, map_id):
        """-> (宽, 高, numpy (高, 宽, 5) uint8)；没有返回 None"""
        k = str(map_id)
        if k in self.cells:
            return self.cells[k]
        res = None
        if k in self.index:
            rec = self._record(k)
            if rec is not None:
                w, h = struct.unpack_from("<HH", rec, 0)
                if 0 < w <= 2000 and 0 < h <= 2000 and len(rec) >= 6 + 5 * w * h:
                    # 数据是列优先的（先 x 再 y：下标 = x × 高 + y）：自相关 W = 200（= 高）时 79%，W = 267 时只有 33%；客户端里外层下标 = 横坐标
                    res = (w, h, np.frombuffer(rec, dtype=np.uint8, count=5 * w * h, offset=6).reshape(w, h, 5).transpose(1, 0, 2))
        self.cells[k] = res
        return res

    def size(self, map_id):
        g = self.grid(map_id)
        return None if g is None else (g[0] * CELL, g[1] * CELL)

    # ---- 贴图 / 遮罩
    def _textures(self):
        with self._lock:                         # 网关用线程池渲染切片：先在局部变量里建好再赋值，别让别的线程看到半成品
            if self._tex is None:
                mrgs = []
                for fn in ("Pan_J.mrg", "Pan_J2.mrg", "Pan_J3.mrg", "Pan_J4.mrg", "Pan_J5.mrg", "Pan_J6.mrg"):
                    p = os.path.join(self.pic, fn)
                    if os.path.exists(p):
                        mrgs.append(Mrg(p))
                tex = {}
                for i, nm in enumerate(NAMES):
                    for m in mrgs:
                        rec = m.get(nm)
                        if rec:
                            tex[i] = np.asarray(Image.open(io.BytesIO(rec)).convert("RGB"))
                            break
                self._tex = tex
            return self._tex

    def _masks(self):
        """mask3 -> numpy bool (8 行 × 15 列, 48, 48)：True = 显示邻格的贴图"""
        with self._lock:
            if self._mask is None:
                rec = Mrg(os.path.join(self.pic, "Pan_Com.mrg")).get("mask3")
                w, h, idx, pal = _rle6(rec)
                m = (idx == 0)
                self._mask = m.reshape(h // CELL, CELL, w // CELL, CELL).transpose(0, 2, 1, 3)
            return self._mask

    def _chunk(self, tex, t, x, y):
        """格 (x, y) 在类型 t 的贴图里的 48 × 48 取点"""
        a = self._textures().get(TBL[F[t]] if t in F else 0)
        if a is None:
            return None
        th, tw = a.shape[0], a.shape[1]
        if t in LIQUID:
            ox, oy = (x % 9) * CELL, (y % 7) * CELL
        else:
            ox, oy = (x % (tw // CELL)) * CELL, (y % (th // CELL)) * CELL
        return a[oy:oy + CELL, ox:ox + CELL]

    def render(self, map_id, x0, y0, w, h, objects=True):
        """渲染像素区域 [x0, x0 + w) × [y0, y0 + h)（超出地图的部分是黑的），返回 PIL RGB 图；objects=False 只画地面"""
        g = self.grid(map_id)
        out = np.zeros((h, w, 3), dtype=np.uint8)
        if g is None:
            return Image.fromarray(out)
        gw, gh, cells = g
        masks = self._masks()
        cx0, cy0 = max(0, x0 // CELL), max(0, y0 // CELL)
        cx1, cy1 = min(gw - 1, (x0 + w - 1) // CELL), min(gh - 1, (y0 + h - 1) // CELL)
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                t = int(cells[cy, cx, 0])
                if t not in F:
                    continue
                tile = self._chunk(None, t, cx, cy)
                if tile is None:
                    continue
                tile = tile.copy()
                own = F[t]
                # 邻格过渡：F 比自己大的邻格，按 F 从小到大叠
                ns = []
                for k, (dx, dy) in enumerate(NEIGH):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < gw and 0 <= ny < gh:
                        nt = int(cells[ny, nx, 0])
                        if nt in F and F[nt] > own and not (t in WATER and nt in WATER):
                            ns.append((F[nt], k, nt, int(cells[ny, nx, 1])))
                ns.sort()
                for _, k, nt, var in ns:
                    src = self._chunk(None, nt, cx, cy)
                    if src is None or var >= masks.shape[1]:
                        continue
                    m = masks[7 - k, var]
                    tile[m] = src[m]
                px, py = cx * CELL - x0, cy * CELL - y0
                sx0, sy0 = max(0, -px), max(0, -py)
                sx1, sy1 = min(CELL, w - px), min(CELL, h - py)
                out[py + sy0:py + sy1, px + sx0:px + sx1] = tile[sy0:sy1, sx0:sx1]
        if objects:
            self._draw_objects(map_id, out, x0, y0)
        return Image.fromarray(out)

    def occluders(self, map_id):
        """给页面做遮挡用的物件（第 1 节的单个立物：树 / 箭楼 / 灌木）：[{n,x,y,w,h,d,u}]，d = 脚下基线（底边往上 12 像素），格式同城市图的 /objects"""
        return [{"n": sid, "x": px, "y": py, "w": sw, "h": sh, "d": py + sh - 12, "u": "/bigobj/%d.png" % sid}
                for sec, sid, px, py, sw, sh in self.objects(map_id) if sec == 1 and sh > CELL]

    def sprite_png(self, sid):
        """物件精灵 -> PNG 字节（透明背景）；没有返回 None"""
        a = self.sprites().get(int(sid))
        if a is None:
            return None
        buf = io.BytesIO()
        Image.fromarray(a, "RGBA").save(buf, "PNG")
        return buf.getvalue()

    def _draw_objects(self, map_id, out, x0, y0):
        """把物件层里和这块区域相交的精灵叠上去（alpha 只有 0 / 255）"""
        h, w = out.shape[:2]
        spr = self.sprites()
        for sec, sid, px, py, sw, sh in self.objects(map_id):
            if px >= x0 + w or py >= y0 + h or px + sw <= x0 or py + sh <= y0:
                continue
            a = spr.get(sid)
            ox, oy = px - x0, py - y0
            sx0, sy0 = max(0, -ox), max(0, -oy)
            sx1, sy1 = min(sw, w - ox), min(sh, h - oy)
            src = a[sy0:sy1, sx0:sx1]
            dst = out[oy + sy0:oy + sy1, ox + sx0:ox + sx1]
            m = src[:, :, 3] > 0
            dst[m] = src[:, :, :3][m]


    # ---- 给网关用的几样东西
    TILE = 768                                    # 切片边长（16 格）
    BLOCKED = (80, 84, 88, 90, 92, 94, 96, 98, 99, 100)      # 水：记录里没有碰撞位图时退回按地面类型挡

    def walk_grid(self, map_id):
        """碰撞格 {"w","h","rows","cols","cell","stride","data"}（格式同 gateway.WalkIndex.get）：原版位图，一小格 16 像素；没有位图时按地面类型（水挡），一格 48"""
        k = str(map_id)
        if k in self._walk:
            return self._walk[k]
        g = self.grid(map_id)
        if g is None:
            return None
        gw, gh, cells = g
        blocked = self.collision(k)
        cell = SUB
        if blocked is None:                       # 记录太短（没有碰撞位图）：退回按地面类型（水挡）
            blocked, cell = np.isin(cells[:, :, 0], self.BLOCKED), CELL
        rows, cols = blocked.shape
        stride = cols // 8 + 1
        pad = np.zeros((rows, stride * 8), dtype=bool)
        pad[:, :cols] = blocked
        data = np.packbits(pad, axis=1, bitorder="little").tobytes()
        self._walk[k] = {"w": gw * CELL, "h": gh * CELL, "rows": rows, "cols": cols, "cell": cell, "stride": stride, "data": data}
        return self._walk[k]

    def collision(self, map_id):
        """原版碰撞位图 -> numpy bool (高×3, 宽×3)，True = 挡；一格 16 像素（大地图一格 48 = 3 × 3 小格）。没有返回 None。
        loginp.exe 载入（0x92819c）：物件 4 节之后读 8 字节（+0x203f54）再读 0x54C91 字节（+0x1ae1a4）；查询（0x927eb0 / 0x92ae69）：
        像素 (x, y) -> 小格 (x >> 4, y >> 4)，字节 = (小格x >> 3) × 0x5A1 + 小格y，位 = 0x80 >> (小格x & 7)，置位 = 挡；出界算挡。
        水、山、成片树林、城墙（整座城）都在里面，桥是河上的缺口。"""
        rec = self._record(str(map_id))
        if rec is None or len(rec) < 6:
            return None
        w, h = struct.unpack_from("<HH", rec, 0)
        p = 6 + 5 * w * h
        for _ in range(4):
            if p + 4 > len(rec):
                return None
            n = struct.unpack_from("<i", rec, p)[0]
            if not 0 <= n <= 100000:
                return None
            p += 4 + 12 * n
        p += 8
        bits = np.frombuffer(rec[p:p + COLL_BYTES], dtype=np.uint8)
        sw, sh = w * 3, h * 3
        if (sw - 1 >> 3) * COLL_STRIDE + sh > len(bits) or sh > COLL_STRIDE:
            return None
        ng = (sw + 7) >> 3
        buf = np.zeros(ng * COLL_STRIDE, dtype=np.uint8)
        buf[:min(len(bits), len(buf))] = bits[:len(buf)]
        groups = buf.reshape(ng, COLL_STRIDE)[:, :sh]                     # (8 列一组, 行)
        cols = np.unpackbits(groups[:, :, None], axis=2)                  # (组, 行, 8)：高位 0x80 = 组内第 0 列
        return cols.transpose(1, 0, 2).reshape(sh, ng * 8)[:, :sw].astype(bool)

    def tile_jpeg(self, map_id, tx, ty, quality=82):
        """第 (tx, ty) 块切片（TILE × TILE 像素，边上的块小一点）的 JPEG 字节；超出地图返回 None"""
        size = self.size(map_id)
        if size is None or tx < 0 or ty < 0 or tx * self.TILE >= size[0] or ty * self.TILE >= size[1]:
            return None
        key = (str(map_id), tx, ty)
        c = self._tiles.get(key)
        if c is None:
            w = min(self.TILE, size[0] - tx * self.TILE)
            h = min(self.TILE, size[1] - ty * self.TILE)
            buf = io.BytesIO()
            self.render(map_id, tx * self.TILE, ty * self.TILE, w, h).save(buf, "JPEG", quality=quality)
            c = buf.getvalue()
            if len(self._tiles) > 600:
                self._tiles.pop(next(iter(self._tiles)))
            self._tiles[key] = c
        return c

    def overview_png(self, map_id, scale=4):
        """整张图的缩略图（每格一个色块，色 = 贴图平均色，× scale），给小地图用"""
        g = self.grid(map_id)
        if g is None:
            return None
        gw, gh, cells = g
        tex = self._textures()
        img = np.zeros((gh, gw, 3), dtype=np.uint8)
        for t in np.unique(cells[:, :, 0]):
            a = tex.get(TBL[F[int(t)]]) if int(t) in F else None
            if a is not None:
                img[cells[:, :, 0] == t] = a.reshape(-1, 3).mean(0).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(img).resize((gw * scale, gh * scale), Image.NEAREST).save(buf, "PNG")
        return buf.getvalue()


if __name__ == "__main__":
    import sys
    pic = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "pic")
    bm = BigMaps(pic)
    mid = sys.argv[1] if len(sys.argv) > 1 else "5000"
    x0, y0, w, h = (int(v) for v in sys.argv[2:6]) if len(sys.argv) >= 6 else (0, 0, 1600, 1000)
    im = bm.render(mid, x0, y0, w, h)
    im.save(sys.argv[6] if len(sys.argv) > 6 else "bigmap_test.jpg", quality=85)
    print(mid, bm.size(mid), "->", im.size)
