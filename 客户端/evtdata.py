#!/usr/bin/env python3
"""原版客户端的地图事件脚本（pic\\EvtMrg*.Mrg）和对话文本库（pic\\TextMrg*.mrg）解析。只用标准库。

来源：loginp.exe 的 FUN_0091d410（事件记录加载器）、FUN_0091ff30（取文本）、FUN_0092213c（文本解密），逐字节照抄。

事件记录（LZSS 解压后）三张表，依次排列：
  节点表  u32 N1，然后 N1 个节点：  名字 20 字节(Pascal，长度 + 19 字节，尾部可能是垃圾) + u8 t(1=主事件, 0=副事件/选项)
          + u32 nA + nA×u32（条件表达式编号，下标进"条件表"）+ u32 nM + nM×u32（动作编号，下标进"动作表"）
  条件表  u32 N2，每项 u8 类型 + 按类型的载荷（见 _COND_*）。类型 1-4/0xb-0xe：u8 + 若干"标签段"
          （u8 标签：0 = 标记 [u16 标记号, i32]×n；1 = 物品 [u16 物品号, i32, i32]×n；2 = 属性 [u16 属性号, i32]×n；0xff 结束）
  动作表  u32 N3，每项 u8 种类 + 按种类的载荷（见 _ACT_*）。种类 1 = 一串文本编号（对话，-1 是分隔符）
节点的编号 = 在节点表里的序号（从 1 起），NpcMrg 里 NPC 的"事件号"和服务端 0x6B 的事件 id 都指它（见逆向笔记）。

文本库 TextMrg*.mrg：一条记录 'TEXT'：u32 解压后长度、u32 压缩长度、u32 条目数 N，N×10 字节索引（u32 id, u16 长度, u32 偏移），
  然后 gzip 压缩的文本区；每条文本按 FUN_0092213c 解密（奇偶位置翻转 + XOR 0x6B），内容是 BIG5。
"""
import gzip
import os
import re
import struct

from npcdata import MAGIC, lzss


def mrg_open(path):
    """-> {记录名: (字节, 类型)}（只读索引，字节按需切片）"""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 8:
        return {}
    cnt, nl = struct.unpack_from("<II", data, 0)
    if cnt == 0 or cnt > 200000 or 8 + 13 * cnt + nl > len(data):
        return {}
    names = data[8 + 13 * cnt:8 + 13 * cnt + nl].decode("gbk", "replace").split("\r\n")
    base = 8 + 13 * cnt + nl
    out = {}
    for i in range(cnt):
        size, off, _hi, t = struct.unpack_from("<IIIB", data, 8 + 13 * i)
        out[names[i]] = (data[base + off:base + off + size], t)
    return out


def decode_text(s):
    """FUN_0092213c：偶数长度时前半段奇数位和后半段对应位互换并 XOR 0x6B；奇数长度时奇数位取镜像位 XOR 0x6B。"""
    n = len(s)
    o = bytearray(s)
    if n % 2 == 0:
        for i in range(1, n // 2 + 1):
            if i % 2 == 1:
                o[i - 1] = s[n - i] ^ 0x6B
                o[n - i] = s[i - 1] ^ 0x6B
    else:
        for i in range(1, n + 1):
            if i % 2 == 1:
                o[i - 1] = s[n - i] ^ 0x6B
    return bytes(o)


class TextStore:
    """pic\\TextMrg.mrg / TextMrg2 / 3 / 4：文本编号 -> BIG5 文本。同一个编号在几个文件里是不同版本：TextMrg2 是简体字版（愿 并），
    TextMrg / 3 / 4 是繁体字版；原版加载时先查 TextMrg2，网页版（繁体界面）优先繁体：4 > 3 > TextMrg > 最后才用 TextMrg2。"""

    def __init__(self, pic_dir, names=("TextMrg2.Mrg", "TextMrg.mrg", "TextMrg3.mrg", "TextMrg4.mrg")):
        self.pools = []
        for nm in names:
            p = os.path.join(pic_dir, nm)
            if not os.path.isfile(p):
                low = {f.lower(): f for f in os.listdir(pic_dir)} if os.path.isdir(pic_dir) else {}
                p = os.path.join(pic_dir, low[nm.lower()]) if nm.lower() in low else None
            if not p:
                continue
            try:
                recs = mrg_open(p)
                blob = next(iter(recs.values()))[0] if recs else b""
                if len(blob) < 12:
                    continue
                h0, h1, n = struct.unpack_from("<III", blob, 0)
                end = 12 + 10 * n
                idx = {}
                for k in range(n):
                    tid, ln, off = struct.unpack_from("<IHI", blob, 12 + 10 * k)
                    idx[tid] = (off, ln)
                text = gzip.decompress(blob[end:end + h1])
                if len(text) != h0:
                    continue
                self.pools.append((idx, text))
            except (OSError, struct.error, EOFError, ValueError):
                continue

    def get(self, tid):
        for idx, text in reversed(self.pools):
            e = idx.get(tid)
            if e:
                return decode_text(text[e[0]:e[0] + e[1]]).decode("big5", "replace")
        return None

    def __len__(self):
        return sum(len(i) for i, _ in self.pools)


# ---- 条件 / 动作载荷解析（FUN_0091d410）
class _R:
    def __init__(self, b, p=0):
        self.b, self.p = b, p

    def u8(self):
        v = self.b[self.p]
        self.p += 1
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        if len(v) != n:
            raise ValueError("eof")
        self.p += n
        return v

    def sized(self, n):
        c = self.u32()
        if c > 100000:
            raise ValueError("count %d" % c)
        return [self.raw(n) for _ in range(c)]


def _tagged(r):
    """标签段：0 = 标记 [u16 号, i32 值]；1 = 物品 [u16 号, i32, i32]；2 = 属性 [u16 号, i32 值]，0xff 结束"""
    out = {"marks": [], "items": [], "attrs": []}
    while True:
        tag = r.u8()
        if tag == 0xFF:
            return out
        if tag == 0:
            out["marks"] = [struct.unpack("<Hi", x) for x in r.sized(6)]
        elif tag == 1:
            out["items"] = [struct.unpack("<Hii", x) for x in r.sized(10)]
        elif tag == 2:
            out["attrs"] = [struct.unpack("<Hi", x) for x in r.sized(6)]


def _cond(r):
    t = r.u8()
    c = {"type": t}
    if t in (1, 2, 3, 4, 0xB, 0xC, 0xD, 0xE):
        c["flag"] = r.u8()
        c.update(_tagged(r))
    elif t == 6:
        c["a"], c["b"] = r.raw(5), r.raw(5)
    elif t == 7:
        c["raw"] = r.raw(0x18)
    elif t == 5:
        c["flag"] = r.u8()
        c["raw"] = r.raw(0x12)
    elif t == 9:
        c["flag"] = r.u8()
    elif t == 0xA:
        c["v"] = r.u32()
    elif t == 8:
        c["flag"] = r.u8()
        c["list"] = [struct.unpack("<Hi", x) for x in r.sized(6)]
    elif t == 0xF:
        c["v"] = [r.u32() for _ in range(3)]
    elif 0x10 <= t <= 0x13:
        c["v"] = [r.u32() for _ in range(2)]
    elif t == 0x14:
        c["v"] = [r.u32()]
    elif t == 0x15:
        c["v"] = [r.u32() for _ in range(2)]
    elif t == 0x16:
        c["v"] = [r.u32() for _ in range(3)]
    elif 0x17 <= t <= 0x1A:
        c["list"] = [struct.unpack("<Hi", x) for x in r.sized(6)]
    elif t in (0x1B, 0x1C):
        c["v"] = [r.u32() for _ in range(2)]
    elif t == 0x1F:
        c["v"] = [r.u32() for _ in range(3)]
    elif t == 0x20:
        c["v"] = [r.u32() for _ in range(5)]
    return c


def _act(r):
    k = r.u8()
    a = {"kind": k}
    if k in (4, 5):
        a["b1"], a["b2"] = r.u8(), r.u8()
        a.update(_tagged(r))
    elif k == 3:
        a["raw"] = r.raw(13)
    elif k in (0xE, 0xB, 0x12, 0xA, 0x13, 0x14, 0x16, 0x17, 0x24):
        a["v"] = [r.u32()]
    elif k == 9:
        a["v"] = [r.u32()]
        a["list"] = [struct.unpack("<II", x) for x in r.sized(8)]
    elif k == 1:
        a["ids"] = [struct.unpack("<i", x)[0] for x in r.sized(4)]
    elif k == 2:
        a["v"] = [r.u32(), r.u32(), r.u32()]
        a["b"] = [r.u8(), r.u8()]
        a["l26"] = r.sized(26)
        a["b3"] = r.u8()
        a["v4"] = r.u32()
        a["l15a"] = r.sized(15)
        a["l15b"] = r.sized(15)
    elif k == 0xD:
        a["v"] = [r.u32(), r.u32()]
        a["b"] = r.u8()
    elif k in (0x10, 0x15):
        a["ids"] = [struct.unpack("<i", x)[0] for x in r.sized(4)]
    elif k in (0x1A, 0x19):
        a["v"] = [r.u32() for _ in range(3)]
    elif k in (0x1B, 0x1D, 0x1E, 0x1F, 0x22, 0x23):
        a["v"] = [r.u32() for _ in range(2)]
    elif k == 0x1C:
        a["list"] = [struct.unpack("<Hi", x) for x in r.sized(6)]
    elif k == 0x20:
        a["v"] = [r.u32()]
        a["ids"] = [struct.unpack("<i", x)[0] for x in r.sized(4)]
    return a


def parse_record(d):
    """解压后的事件记录 -> {"nodes":[{id,name,main,A,M}], "conds":[...], "acts":[...], "tail": 多余字节数}；读不完抛 ValueError"""
    r = _R(d)
    n1 = r.u32()
    if n1 > 100000:
        raise ValueError("n1")
    nodes = []
    for i in range(n1):
        nm = r.raw(20)
        ln = min(nm[0], 19)
        name = nm[1:1 + ln].decode("big5", "replace")
        t = r.u8()
        na = r.u32()
        if na > 100000:
            raise ValueError("nA")
        A = [r.u32() for _ in range(na)]
        nm_ = r.u32()
        if nm_ > 100000:
            raise ValueError("nM")
        M = [r.u32() for _ in range(nm_)]
        nodes.append({"id": i + 1, "name": name, "main": t == 1, "A": A, "M": M})
    n2 = r.u32()
    if n2 > 1000000:
        raise ValueError("n2")
    conds = [_cond(r) for _ in range(n2)]
    n3 = r.u32()
    if n3 > 1000000:
        raise ValueError("n3")
    acts = [_act(r) for _ in range(n3)]
    # 记录后面可能有多余字节：编辑器改短记录时没截断文件留下的旧内容（有些是上一版文本编号的残片），原版加载器读完三张表就停，这里一样
    return {"nodes": nodes, "conds": conds, "acts": acts, "tail": len(d) - r.p}


class EventIndex:
    """pic\\EvtMrg*.Mrg：地图编号 -> 事件记录（EvtMrg3 优先，其余文件号大的覆盖小的）。"""

    def __init__(self, pic_dir):
        self.index = {}
        self.cache = {}
        try:
            files = [f for f in os.listdir(pic_dir) if re.fullmatch(r"(?i)evtmrg\d*\.mrg", f)]
        except OSError:
            files = []

        def order(f):
            # 同一张图在几个文件里都有时谁说了算：EvtMrg3 / NpcMrg3 才是现行版本（2026-10-21 用服务端 事件.csv 的结果标记逐图对：
            # 3 优先时 98.4% 的事件对得上，旧规则『文件号大的覆盖小的』只有 76%；游戏自带的 NPC 目录 cityportals.dat 也和 NpcMrg3 一致）
            m = re.search(r"(\d+)", f)
            n = int(m.group(1)) if m else 1
            return 100 if n == 3 else n
        for fn in sorted(files, key=order):
            path = os.path.join(pic_dir, fn)
            try:
                with open(path, "rb") as f:
                    head = f.read(8)
                    if len(head) < 8:
                        continue
                    cnt, nl = struct.unpack("<II", head)
                    if cnt == 0 or cnt > 200000:
                        continue
                    tab = f.read(13 * cnt)
                    names = f.read(nl).decode("gbk", "replace").split("\r\n")
            except OSError:
                continue
            base = 8 + 13 * cnt + nl
            for i, nm in enumerate(names[:cnt]):
                size, off = struct.unpack_from("<II", tab, 13 * i)
                if nm.isdigit() and size > 8:
                    self.index[nm] = (path, base + off, size)

    def raw(self, map_id):
        ent = self.index.get(map_id) or self.index.get(map_id.zfill(4))      # 小编号的地图记录名是 4 位补零（0014）
        if not ent:
            return None
        with open(ent[0], "rb") as f:
            f.seek(ent[1])
            r = f.read(ent[2])
        if r[:4] == MAGIC:
            r = lzss(r[8:], struct.unpack_from("<I", r, 4)[0])
        return r

    def get(self, map_id):
        if map_id not in self.cache:
            try:
                d = self.raw(map_id)
                self.cache[map_id] = parse_record(d) if d else None
            except (OSError, ValueError, struct.error, IndexError):
                self.cache[map_id] = None
        return self.cache[map_id]


if __name__ == "__main__":
    import sys
    pic = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "share", "pic")
    ix = EventIndex(pic)
    ok = bad = odd = 0
    badl = []
    for m in sorted(ix.index):
        try:
            rec = parse_record(ix.raw(m))
            ok += 1
            if any(a["kind"] > 0x24 for a in rec["acts"]) or any(c["type"] > 0x20 for c in rec["conds"]):
                odd += 1
                badl.append((m, "未知种类"))
        except (ValueError, struct.error, IndexError) as e:
            bad += 1
            badl.append((m, str(e)))
    print("事件记录 %d 条：解析成功 %d（其中含未知种类的 %d），失败 %d" % (len(ix.index), ok, odd, bad), badl[:10])
    ts = TextStore(pic)
    print("文本 %d 条" % len(ts), ts.get(10001))
