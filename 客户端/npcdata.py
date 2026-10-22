#!/usr/bin/env python3
"""地图 NPC 列表：pic\\NpcMrg*.Mrg 里每张地图一个 LZSS 压缩的记录。只用标准库（网关运行时用）。

记录解码后（逆向笔记 §NPC）：
  开头是 Pascal 地图文件名（"2801.wsg"）+ 若干头字段 + u32 个数，然后是变长的 NPC 条目，每条：
    u8 01 + u32 n + n×u32（事件号列表）+ u16 NPC 编号 + u32 x + u32 y（单位：20 像素的格）
    + u8 朝向(0..7，4 = 面向镜头) + u16 型号（= 服务端 MOB数据.csv 的 mob_id，如 39015 肉商）
    + Pascal 名字（BIG5）+ 零填充 + u16 NPC 编号（同上一个）+ u8 02 + 8×FF + ……
  条目之间没有长度字段，所以按"NPC 编号 u16 在名字后面重复一次 + 02 + 8×FF"这个特征逐条找。
同一张图在多个 NpcMrg 文件里时取文件号最大的（NpcMrg5 > 4 > 3 > 2）。
"""
import os
import re
import struct

MAGIC = b"\x56\x8d\x0f\x20"


def lzss(src, outlen):
    """Okumura LZSS：4096 环形缓冲，初始 0x20，起点 0xFEE（和 资源解析\\wjres.py 一样，这里不依赖 Pillow）。"""
    ring = bytearray(b"\x20" * 4096)
    r = 0xFEE
    out = bytearray()
    i, n, flags = 0, len(src), 0
    while len(out) < outlen:
        flags >>= 1
        if not flags & 0x100:
            if i >= n:
                break
            flags = src[i] | 0xFF00
            i += 1
        if flags & 1:
            if i >= n:
                break
            c = src[i]
            i += 1
            out.append(c)
            ring[r] = c
            r = (r + 1) & 0xFFF
        else:
            if i + 1 >= n:
                break
            b1, b2 = src[i], src[i + 1]
            i += 2
            pos = b1 | ((b2 & 0xF0) << 4)
            for k in range((b2 & 0x0F) + 3):
                c = ring[(pos + k) & 0xFFF]
                out.append(c)
                ring[r] = c
                r = (r + 1) & 0xFFF
    return bytes(out)


def _events_after(b, p):
    """记录结尾 p 之后：24 字节填充（10 个 0 + 14 个 ff）+ `flag u8(0/1) | 个数 u32 | 事件号 u32…`。
    2026-10-21 更正：事件表属于它**前面**的那条记录（以前当成后面那条，整张图错位一条：8122 图 4 条记录 + 最后一个没有后继的表，
    才看出来；统计『名字含指導員的 NPC 事件里有新手节点』前后版本 16/71 → 68/71）"""
    s = p + 24
    if s + 5 <= len(b) and b[s] in (0, 1):
        c = struct.unpack_from("<I", b, s + 1)[0]
        if c <= 64 and s + 5 + 4 * c <= len(b):
            return list(struct.unpack_from("<%dI" % c, b, s + 5))
    return []


SLOT_RE = re.compile(r"(首領|小隊長|嘍嘍)\d+")


def parse_npcs(b):
    """-> [{"id","x","y","dir","model","name","events","slot"}]，x / y 是格坐标。
    名字只取长度字节说的那么长：名字后面到终结符之间常有上一次写入留下的残字（『首領1茪H』『嘍嘍1·8v技能師』『銀票兌換員利言』），不是名字的一部分。
    slot = 怪物攻城的刷怪位（名字『首領N / 小隊長N / 嘍嘍N』、型号 60028–60063 一类、没有事件；21 张城市图共 1558 个，活动时服务端才刷出来），NpcIndex.get 不收。"""
    out = []
    i = 0
    n = len(b)
    while i < n - 40:
        idv = b[i] | b[i + 1] << 8
        x, y = struct.unpack_from("<II", b, i + 2)
        ln = b[i + 13]
        if 0 < x < 2000 and 0 < y < 2000 and 1 <= ln <= 30 and i + 14 + ln + 8 < n:
            j = i + 14 + ln
            k = b.find(struct.pack("<H", idv) + b"\x02" + b"\xff" * 8, j, j + 40)
            if k >= 0:
                evs = _events_after(b, k + 11)
                name = b[i + 14:j].decode("big5", "replace")
                out.append({"id": idv, "x": x, "y": y, "dir": b[i + 10], "model": b[i + 11] | b[i + 12] << 8,
                            "name": name, "events": evs, "slot": bool(SLOT_RE.fullmatch(name)) and not evs})
                i = k + 11
                continue
        i += 1
    return out


ZONE_NAMES = {"進入點": "door", "地雷": "mine"}


def parse_zones(b):
    """NpcMrg 记录里不可见的触发区（模型 0）：-> [{"id","x","y","w","h","kind","name","events"}]。

    2026-10-21 解出（8105 / 2801 图叠加背景图验证）：和 NPC 同一种记录，`id u16 | x u32 | y u32（格）| 朝向 | 模型 u16 = 0 | 名字长度 | 名字`，
    名字是『進入點』（门 / 出入口，kind = door）或『地雷』（踩到才触发的隐藏事件，kind = mine）；名字后 13 个 0，再 `id u16 | 1 字节 | w u32 | h u32`
    （像素）。区域 = 左上角 (x×20, y×20)、宽 w、高 h 的矩形，人走进去就触发；events 和 NPC 一样是记录后面（填充 24 字节之后）的 `flag(0/1) | 个数 u32 | 事件号…`
    （2026-10-21 更正：以前当成记录前面的，错位一条，见 _events_after）。事件节点里的动作 3 = 传送，所以门就是『走进去 → 事件 → 传送』。parse_npcs 看不到这些记录（模型 0 / 没有终结符）。"""
    out = []
    n = len(b)
    for i in range(n - 60):
        if b[i + 11] or b[i + 12]:
            continue
        ln = b[i + 13]
        kind = ZONE_NAMES.get(b[i + 14:i + 14 + ln].decode("big5", "ignore")) if 2 <= ln <= 8 else None
        if kind is None:
            continue
        idv = b[i] | b[i + 1] << 8
        x, y = struct.unpack_from("<II", b, i + 2)
        s = i + 14 + ln + 13
        if x > 5000 or y > 5000 or s + 11 > n:
            continue
        w, h = struct.unpack_from("<II", b, s + 3)
        if not (0 < w < 2000 and 0 < h < 2000):
            continue
        evs = _events_after(b, s + 11)
        out.append({"id": idv, "x": x, "y": y, "w": w, "h": h, "kind": kind, "name": b[i + 14:i + 14 + ln].decode("big5", "replace"), "events": evs})
    return out


class NpcIndex:
    def __init__(self, pic_dir):
        self.index = {}          # 地图编号 -> (文件, 绝对偏移, 字节数)
        self.cache = {}
        self.zcache = {}
        try:
            files = [f for f in os.listdir(pic_dir) if re.fullmatch(r"(?i)npcmrg\d*\.mrg", f)]
        except OSError:
            files = []

        def order(f):
            m = re.search(r"(\d+)", f)
            n = int(m.group(1)) if m else 1
            return 100 if n == 3 else n         # NpcMrg3 / EvtMrg3 是现行版本，见 evtdata.EventIndex.order
        for fn in sorted(files, key=order):
            path = os.path.join(pic_dir, fn)
            try:
                with open(path, "rb") as f:
                    head = f.read(8)
                    if len(head) < 8:
                        continue
                    cnt, nl = struct.unpack("<II", head)
                    if cnt == 0 or cnt > 100000:
                        continue
                    tab, names = f.read(13 * cnt), f.read(nl).decode("gbk", "replace").split("\r\n")
            except OSError:
                continue
            base = 8 + 13 * cnt + nl
            for i, nm in enumerate(names[:cnt]):
                size, off = struct.unpack_from("<II", tab, 13 * i)
                if nm.isdigit() and size > 8:
                    self.index[nm] = (path, base + off, size)          # 文件号大的覆盖小的

    def _raw(self, map_id):
        ent = self.index.get(map_id) or self.index.get(map_id.zfill(4))      # 小编号的地图记录名是 4 位补零（0014）
        if not ent:
            return None
        try:
            with open(ent[0], "rb") as f:
                f.seek(ent[1])
                r = f.read(ent[2])
            if r[:4] == MAGIC:
                r = lzss(r[8:], struct.unpack_from("<I", r, 4)[0])
            return r
        except (OSError, struct.error):
            return None

    def get(self, map_id):
        if map_id in self.cache:
            return self.cache[map_id]
        r = self._raw(map_id)
        res = []
        seen = {}
        for n in (parse_npcs(r) if r else []):
            if n["slot"]:                         # 怪物攻城的刷怪位：平时不在
                continue
            # 同一个 id 在记录里可能出现好几次（会走动的 NPC 带路径点记录，位置相同、事件表有的为空）：留第一条，事件表取第一个非空的
            k = seen.get(n["id"])
            if k is None:
                seen[n["id"]] = n
                res.append(n)
            elif not k["events"] and n["events"]:
                k["events"] = n["events"]
        self.cache[map_id] = res
        return res

    def zones(self, map_id):
        """这张图的触发区（门 / 地雷），见 parse_zones"""
        if map_id not in self.zcache:
            r = self._raw(map_id)
            self.zcache[map_id] = parse_zones(r) if r else []
        return self.zcache[map_id]


if __name__ == "__main__":
    import sys
    pic = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "pic")
    ix = NpcIndex(pic)
    mid = sys.argv[2] if len(sys.argv) > 2 else "2801"
    ns = ix.get(mid)
    print("地图 %s：%d 个 NPC（共 %d 张图有 NPC 数据）" % (mid, len(ns), len(ix.index)))
    for n in ns[:25]:
        print(n["id"], n["name"], (n["x"] * 20, n["y"] * 20), "dir", n["dir"], "model", n["model"], "events", len(n["events"]))
