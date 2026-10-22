#!/usr/bin/env python3
"""WebSocket 网关：浏览器页面 <-WebSocket/JSON-> 本程序（jyclient）<-TCP 原版协议-> 游戏服务端。

只用标准库（自带最小 HTTP + RFC 6455 WebSocket 实现）。默认只监听 127.0.0.1；
同一个端口既提供页面（web/ 目录，只读白名单）又提供 /ws。

    python gateway.py                                  # 页面 http://127.0.0.1:8088/ ，上游 127.0.0.1:6732
    python gateway.py --server 127.0.0.1:6731          # 连原版服务端（小心：原版强制单点登录、会写库）

注意：游戏协议的登录包里没有密码，服务端只信 jyid。所以别把网关监听到公网 / 局域网上，
需要远程用时放在带认证的反向代理后面，或者以后在网关里加登录校验。

浏览器 -> 网关（JSON 文本帧）
  {"op":"login","jyid":123456}    登录并走完登录序列
  {"op":"say","text":"..."}       公共聊天
  {"op":"move","x":..,"y":..}     从当前位置走到 (x,y)
  {"op":"teleport","map":..,"x":..,"y":..}
  {"op":"equip","slot":1..9,"item":id} / {"op":"unequip","slot":1..9} / {"op":"use","item":id}
  {"op":"shop_open","merchant":id} / {"op":"buy","items":[{"item":id,"n":数量},..]}
  {"op":"debug","on":true}        推送每个收到的帧的类型和长度
  {"op":"logout"}
网关 -> 浏览器
  {"ev":"status","text":..}  {"ev":"error","msg":..}  {"ev":"me",...}  {"ev":"patch",...}
  {"ev":"pos","map":..,"x":..,"y":..}  {"ev":"players","list":[..]}
  {"ev":"chat","jyid":..,"name":..,"text":..,"self":bool}  {"ev":"notice","kind":..,"text":..}
  {"ev":"shop","items":[{"id","name","ok"}]}   （装备/背包/属性变化后会重发完整的 me）
  {"ev":"frame","type":..,"n":..}  {"ev":"closed"}
"""
import argparse
import asyncio
import base64
import csv
import hashlib
import json
import os
import re
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient, SLOT_NAME, from_big5  # noqa: E402
import jyfight  # noqa: E402
import notices  # noqa: E402
import biaoju  # noqa: E402
import lifeskill  # noqa: E402
import masters  # noqa: E402
import books  # noqa: E402
import dutydata  # noqa: E402
import guide  # noqa: E402
try:
    import bigmap  # noqa: E402
except ImportError:      # 没装 numpy / Pillow：没有大地图
    bigmap = None
from npcdata import NpcIndex  # noqa: E402
import evtengine  # noqa: E402
from evtdata import EventIndex, TextStore  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
OBJ_DIR = os.path.join(WEB_DIR, "objects")          # 前景物件贴图缓存（build_objects.py 生成）
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_WS_MSG = 64 * 1024
MAX_SESSIONS = 8
WORK_MIN_JING = 10        # 生活技能：精低于这个值就停（原版每轮 −1，客户端有"精力不足"检查）
FARM_GROW_SECS = 20.0     # 農夫：耕種到收成之间等多久（原版服务端对间隔不设限，实测 0 秒也能收；客户端按作物 4 秒一格自己数）
ZIXIU_MAP = 3511          # 自修洞：这张图上发 0x5B / 0x5C，原版全服公告并随机降一级武功（生活技能与农夫.md）
FARM_PLOTS = 20          # 客户端的田块表 20 项（0x91b29b 的循环 0x14）
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".png": "image/png", ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8"}
_PKG_DATA = os.path.join(HERE, "data")
# 物品表目录：打包后在 <网关目录>\data（装备数据.csv 等），开发机上读原版服务端的 data
DEFAULT_ITEM_DIR = _PKG_DATA if os.path.isfile(os.path.join(_PKG_DATA, "装备数据.csv")) else r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"
# 客户端 share\pic（地图背景）目录：打包后在 <网关目录>\share\pic，开发机上在 ..\share\pic
DEFAULT_PIC_DIR = os.path.normpath(os.path.join(HERE, "share", "pic") if os.path.isdir(os.path.join(HERE, "share", "pic")) else os.path.join(HERE, "..", "share", "pic"))


# ---------------------------------------------------------------- 物品名字
class Items:
    def __init__(self, data_dir):
        self.names = {}
        self.equips, self.meds, self.buyable = set(), set(), set()   # 装备数据里的物品 / 药品表里的物品 / 「商品」列=1（能买）
        self.merchants = []                                          # [{"id","name"}]
        self.type2 = {}                                              # 装备数据.csv 的 itemtype2
        self.notrade = set()                                         # 「交易」列（第 22 列）= 0：不能丢弃 / 交易
        self.kf_names = {}                                           # 武学系数.csv：武功 ID -> 名字（GBK 简体列）
        try:
            with open(os.path.join(data_dir or "", "武学系数.csv"), encoding="gbk", errors="replace", newline="") as f:
                rd = csv.reader(f)
                next(rd, None)
                for row in rd:
                    if len(row) > 4 and row[0].isdigit():
                        self.kf_names[int(row[0])] = row[4] or row[3]
        except OSError:
            pass
        self.masters = masters.Masters(os.path.join(data_dir or "", "师傅.csv"))     # 师傅.csv：消点（C2S 0x5E）用
        for fn, idc, namec in (("装备数据.csv", 0, 3), ("药品.csv", 0, 1)):
            p = os.path.join(data_dir or "", fn)
            try:
                with open(p, encoding="gbk", errors="replace", newline="") as f:
                    rd = csv.reader(f)
                    next(rd, None)
                    for row in rd:
                        if len(row) > namec and row[idc].isdigit():
                            i = int(row[idc])
                            self.names.setdefault(i, row[namec])
                            if fn == "装备数据.csv":
                                self.equips.add(i)
                                if len(row) > 2 and row[2].isdigit():
                                    self.type2[i] = int(row[2])
                                if len(row) > 19 and row[19] == "1":
                                    self.buyable.add(i)
                                if len(row) > 21 and row[21] == "0":
                                    self.notrade.add(i)
                            else:
                                self.meds.add(i)
            except OSError:
                pass
        self.mobs = {}                                               # MOB数据.csv：mob_id -> {name, hp, speed(聚气速度)}
        try:
            with open(os.path.join(data_dir or "", "MOB数据.csv"), encoding="gbk", errors="replace", newline="") as f:
                rd = csv.reader(f)
                next(rd, None)
                for row in rd:
                    if len(row) > 10 and row[0].isdigit():
                        self.mobs[int(row[0])] = {"name": row[2] or row[1], "hp": int(row[4] or 0) if row[4].isdigit() else 0,
                                                  "speed": int(row[10]) if row[10].isdigit() and int(row[10]) > 0 else 50}
        except OSError:
            pass
        try:
            with open(os.path.join(data_dir or "", "商人.csv"), encoding="gbk", errors="replace", newline="") as f:
                rd = csv.reader(f)
                next(rd, None)
                for row in rd:
                    if len(row) >= 2 and row[0].isdigit():
                        self.merchants.append({"id": int(row[0]), "name": row[1]})
        except OSError:
            pass
        # 任务标记：服务端 标记.csv（ID, "标记ID:名字", 类型）。任务进度 = 身上有哪些标记（事件结果 `标记:ID:N` 由服务端写库并用 0x77 发下来，
        # 客户端把它当背包条目存）。名字没有统一格式，常见的是「任务名 + 序号（一 / 二 …）+ 字母 + 动作」，如 风月夷光一A退青。
        self.markers = {}                                            # id -> {name, quest, step, what, type}
        try:
            with open(os.path.join(data_dir or "", "标记.csv"), encoding="gbk", errors="replace", newline="") as f:
                rd = csv.reader(f)
                next(rd, None)
                for row in rd:
                    if len(row) >= 2 and ":" in row[1] and row[1].split(":", 1)[0].isdigit():
                        mid, nm = row[1].split(":", 1)
                        quest, step, what = self.split_marker(nm)
                        self.markers[int(mid)] = {"name": nm, "quest": quest, "step": step, "what": what, "type": int(row[2]) if len(row) > 2 and row[2].isdigit() else 0}
        except OSError:
            pass

    _NUMS = "一二三四五六七八九十"

    @classmethod
    def split_marker(cls, name):
        """标记名 -> (任务名, 步骤, 说明)。规则：第一个 ASCII 字母 / 数字之前是"任务名（+ 汉字序号）"，那个字符是步骤号，其后是说明
        （风月夷光一A退青 → 风月夷光 / 一A / 退青；五行掌A触发 → 五行掌 / A / 触发）；没有 ASCII 字符时，结尾带汉字序号的才拆
        （某某任务二完成 → 不拆），其余整个名字放进"其它"。"""
        name = name.strip()
        m = re.search(r"[A-Za-z0-9]", name)
        if not m or m.start() < 2:
            return "其它", "", name
        head, k = name[:m.start()], m.start()
        run = re.match(r"[A-Za-z0-9]{1,4}", name[k:]).group(0)        # 步骤号：连续的字母 / 数字（A、1A、A01、一199 里的 199）
        step = run
        mm = re.match(r"^(.{2,}?)([%s]{1,3})$" % cls._NUMS, head)
        if mm:
            head, step = mm.group(1), mm.group(2) + run
        what = name[k + len(run):].lstrip("-－— ").strip()
        return head, step, what or name

    def is_marker(self, i):
        """背包里的这个 id 是任务标记：在 标记.csv 里，并且不是装备 / 药品（两张表的 id 段不重合，这里只是保险）。"""
        return i in self.markers and i not in self.names

    def quest_view(self, counts):
        """{标记 id: 数量} -> [{quest, steps:[{id, step, what, n}]}]，按任务名排序，步骤按 id 排。"""
        groups = {}
        for i, n in counts.items():
            mk = self.markers.get(i)
            if mk is None:
                continue
            groups.setdefault(mk["quest"], []).append({"id": i, "step": mk["step"], "what": mk["what"], "n": n, "name": mk["name"]})
        out = [{"quest": q, "steps": sorted(st, key=lambda s: s["id"])} for q, st in groups.items()]
        out.sort(key=lambda g: (g["quest"] == "其它", g["quest"]))
        return out

    def name(self, i):
        mk = self.markers.get(i) if i not in self.names else None
        return self.names.get(i) or (("標記·" + mk["name"]) if mk else "物品#%d" % i)

    # 武器 itemtype2 -> 武器层（WA 刀 / WB 棍 / WC 枪 / WD 剑 / WE 鞭）。类型来自服务端 装备数据.csv（传家宝刀 / 剑 / 棍 / 枪 / 鞭 分别是 20 / 23 / 22 / 25 / 24），
    # 层是在渲染图里肉眼对过的（攻击帧）。**这个对应不是原版客户端的做法**：原版按 Item*.dat 里的外观码，缺记录就不画。只给 --look-fallback 用。
    WEAPON_LETTER = {20: "WA", 23: "WD", 22: "WB", 25: "WC", 24: "WE"}

    def weapon_letter(self, i):
        return self.WEAPON_LETTER.get(self.type2.get(i & 0xFFFF))

    @staticmethod
    def guess_slot(i):
        """按物品编号前缀猜装备槽（盔 25 / 项链 24 / 衣 27 / 披风 20 / 武器 11..18 / 护腕 22 / 戒指 23 / 鞋 26）。
        只是界面默认值：服务端并不检查物品类型和槽位是否匹配。"""
        g = i // 1000
        return {25: 1, 24: 2, 27: 3, 20: 4, 22: 7, 23: 8, 26: 9}.get(g, 6 if 11 <= g <= 18 else 0)


# ---------------------------------------------------------------- NPC / 怪物形象
class NpcSprites:
    """型号（NpcMrg 的 model = MOB id）-> 精灵号：share\\dat\\Npc*.Dat 记录 +0x19（npcdat.py，loginp.exe 0x51b5bc）；
    精灵 = role\\npc*.mrg 里 ROLE\\<精灵号>{S,A}.CP，由 build_npc_sprites.py --all 预生成 web\\sprites\\npc\\<精灵号>.json/.png
    （打包进 Mac 包；没有预生成的型号就画名牌 / 占位）。"""

    def __init__(self):
        self.dir = os.path.join(WEB_DIR, "sprites", "npc")
        self.cache = {}

    def have(self, sid):
        return os.path.isfile(os.path.join(self.dir, "%d.json" % sid))

    def of(self, model):
        if model not in self.cache:
            sid = None
            try:
                import npcdat
                import struct as _st
                for t in self.tables():
                    r = t.get(model)
                    if r is not None:
                        s = _st.unpack_from("<H", r, 0x19)[0]
                        if s and self.have(s):
                            sid = s
                            break
            except OSError:
                pass
            self.cache[model] = sid
        return self.cache[model]

    def tables(self):
        if not hasattr(self, "_tables"):
            import npcdat
            self._tables = []
            for fn in ("Npc3.Dat", "Npc1.Dat", "Npc.Dat"):
                p = os.path.join(npcdat.DAT_DIR, fn)
                if os.path.isfile(p):
                    self._tables.append(npcdat.load(p))
        return self._tables

    def ensure(self, sid):
        """某个精灵号的 json 路径，没有预生成返回 None（只用 python build_npc_sprites.py --all 预生成的；不在网关里现生成，免得把 1GB 的 npc*.mrg 读进内存）。"""
        p = os.path.join(self.dir, "%d.json" % sid)
        return p if os.path.isfile(p) else None

# ---------------------------------------------------------------- 外观
class RoleMeta:
    """roles.json 里的一个模型（接口和 build_sprites.RoleFile 里用到的部分一致）。"""

    def __init__(self, d):
        self.prefix, self.body, self.shadow, self.layers = d["prefix"], d["body"], d.get("shadow"), list(d["layers"])
        self._set = {l.upper() for l in self.layers}

    def has_layer(self, layer):
        return layer.upper() in self._set


class Looks:
    """装备物品 ID -> 外观层。照 loginp.exe 的做法（逆向笔记 §外观）：

    * 表在内存 this+0x281058，每个 ID 14 字节 = 两个 Delphi shortstring[6]（前一个女、后一个男），由 0x51cbac 从 dat\\item3.dat 读入：
      文件 320 字节头 + 每条 299 字节；ID = 记录首 u16，女外观码在记录 +0x38，男外观码在 +0xaf；表里 0xFFFF 的两个串都是 "ma0101"（默认头发）。
    * 外观码 6 个字符 "ma0101" = 层名后 4 位 "MA01" + 调色板套号 "01"；层名 = 模型前缀（boy01 是 M1）+ 前 4 位大写。（0x521be4 + 0x5253c8）
    * 男模型（1..9、0x14..0x19）取男码，女模型取女码，选中的为空就用另一个；两个都空 = 这个槽不画。
    * 玩家对象里有 3 个装备槽（头 / 衣 / 武器，来自 0x02、0x61 包的三个 LE16 物品 ID）；头槽为 0 时按 0xFFFF 查（默认头发），其余槽为 0 就不画。
    * 叠放顺序：阴影、身体、再按槽：模型 3..9 是 衣、头、武器，其余是 头、衣、武器（0x5252f8）。
    * 某个层在这个模型的 mrg 里不存在（例如 WF01 只有 6 号以上的模型才有）就不画——和原版一样。
    """
    H, S = 0x140, 299
    CODE = re.compile(r"[a-z]{2}\d{4}")

    def __init__(self, item3_path):
        self.table = {}                 # id -> (女码, 男码)
        try:
            d = open(item3_path, "rb").read()
        except OSError:
            d = b""

        def ss(r, o):
            n = r[o]
            s = r[o + 1:o + 1 + n].decode("latin1") if n == 6 else ""
            return s if self.CODE.fullmatch(s) else ""

        for k in range(max(0, (len(d) - self.H) // self.S)):
            r = d[self.H + k * self.S:self.H + (k + 1) * self.S]
            i = r[0] | r[1] << 8
            if i:
                a, b = ss(r, 0x38), ss(r, 0xAF)
                if a or b:
                    self.table[i] = (a, b)
        self.table[0xFFFF] = ("ma0101", "ma0101")
        self.roles = {}
        self.fallback = None            # 可选 fn(item_id) -> "WA".."WE" | None，见 Gateway(look_fallback=True)

    def role(self, model):
        """模型的 {前缀, 身体层, 阴影层, 层名表}。优先读 web/sprites/roles.json（打包到没有 role\\*.mrg / Pillow 的机器上用），
        没有再从 role\\*.mrg 现读（需要 Pillow 和客户端的 share\\role）。"""
        if model not in self.roles:
            meta = None
            try:
                with open(os.path.join(WEB_DIR, "sprites", "roles.json"), encoding="utf8") as f:
                    m = json.load(f).get(str(model))
                if m:
                    meta = RoleMeta(m)
            except (OSError, ValueError):
                pass
            if meta is None:
                try:
                    import build_sprites
                    meta = build_sprites.get_role(model)
                except BaseException:       # wjres 没有 Pillow 时会 sys.exit
                    meta = None
            self.roles[model] = meta
        return self.roles[model]

    def layers(self, model, ids):
        """ids = [头, 衣, 武器] 物品 ID -> {"model","layers":[{"l","s"}...],"info":[...]}；没有这个模型的资源时 layers 为空。"""
        rf = self.role(model)
        if rf is None:
            return {"model": model, "layers": [], "info": []}
        male = 1 <= model <= 9 or 0x14 <= model <= 0x19
        ids = [i & 0xFFFF for i in ids]       # 表按 16 位 ID 索引
        if ids[0] == 0:
            ids[0] = 0xFFFF
        out, info = [], []
        if rf.shadow:
            out.append({"l": rf.shadow, "s": 0, "alpha": 0.5})      # 阴影层只有一种灰色，半透明叠加
        out.append({"l": rf.body, "s": 0})
        for k in ([1, 0, 2] if 3 <= model <= 9 else [0, 1, 2]):
            a, b = self.table.get(ids[k], ("", ""))
            code = (b or a) if male else (a or b)
            ent = {"slot": ("头", "衣", "武器")[k], "id": ids[k], "code": code}
            if not code and k == 2 and ids[2] and self.fallback:
                letter = self.fallback(ids[2])      # 非原版：表里没有的武器按 itemtype2 套 WA..WE，款式 01、调色板第 0 套
                if letter:
                    code = letter.lower() + "0100"
                    ent.update(code=code, fallback=True)
            if code:
                layer = rf.prefix + code[:4].upper()
                ent["layer"] = layer
                if rf.has_layer(layer):
                    out.append({"l": layer, "s": int(code[4:6])})
                else:
                    ent["missing"] = True
            info.append(ent)
        return {"model": model, "layers": out, "info": info}


# ---------------------------------------------------------------- 地图背景
class MapIndex:
    """pic\\SceneBG*.mrg 里以地图编号命名的记录就是该地图的整张 JPEG 背景（见 资源格式说明.md §2.1）。
    只读 .mrg 的记录表和名字表建索引，按需从原文件里切出 JPEG 返回，不转换、不复制。"""

    def __init__(self, pic_dir):
        self.pic_dir = pic_dir
        self.index = {}          # 地图编号 -> (文件, 绝对偏移, 字节数)
        try:
            files = sorted(f for f in os.listdir(pic_dir) if f.lower().startswith("scenebg") and f.lower().endswith(".mrg"))
        except OSError:
            files = []
        for fn in files:
            path = os.path.join(pic_dir, fn)
            try:
                with open(path, "rb") as f:
                    head = f.read(8)
                    if len(head) < 8:
                        continue
                    n, nl = struct.unpack("<II", head)
                    if n == 0 or n > 100000:
                        continue
                    tab, names = f.read(13 * n), f.read(nl).decode("gbk", "replace").split("\r\n")
            except OSError:
                continue
            base = 8 + 13 * n + nl
            for i, nm in enumerate(names[:n]):
                size, off = struct.unpack_from("<II", tab, 13 * i)
                if nm.isdigit() and size > 4 and nm not in self.index:
                    self.index[nm] = (path, base + off, size)

    def get(self, map_id: str):
        ent = self.index.get(map_id)
        if not ent:
            return None
        path, off, size = ent
        try:
            with open(path, "rb") as f:
                f.seek(off)
                data = f.read(size)
        except OSError:
            return None
        return data if data[:2] == b"\xff\xd8" else None


# ---------------------------------------------------------------- 地图碰撞（可走格）
class WalkIndex:
    """dat\\WSG*.dat 是 .mrg 容器，里面以地图编号命名的记录带这张地图的碰撞位图（逆向笔记 §地图碰撞）：

        记录 = Pascal 地图名 ... 偏移 51 起 u16 宽、高(像素)、行数、列数，偏移 59 起位图；
        格子 20×20 像素，行数 = ceil(高/20)，列数 = ceil(宽/20)，每行 (列数//8 + 1) 字节，低位在前，1 = 不能走。

    判定依据：8105 / 2200 号图叠在背景上，街道和楼梯是空的、房子是满的；2801 号图要用"每行 列数//8+1 字节"才能对齐
    （MAP.csv 里 79 个到达点 74 个落在可走格，按 列数//8 切只有 46%）。
    同一张图可能出现在多个 WSG 文件里（104 张，内容略有不同，是版本更新），按文件号从小到大后者覆盖前者。"""
    CELL = 20

    def __init__(self, dat_dir):
        self.index = {}          # 地图编号 -> (文件, 绝对偏移, 字节数)
        self.cache = {}
        try:
            files = [f for f in os.listdir(dat_dir) if re.fullmatch(r"(?i)wsg\d*\.dat", f)]
        except OSError:
            files = []

        def order(f):
            m = re.search(r"(\d+)", f)
            return int(m.group(1)) if m else 1
        for fn in sorted(files, key=order):
            path = os.path.join(dat_dir, fn)
            try:
                with open(path, "rb") as f:
                    head = f.read(8)
                    if len(head) < 8:
                        continue
                    n, nl = struct.unpack("<II", head)
                    if n == 0 or n > 100000:
                        continue
                    tab, names = f.read(13 * n), f.read(nl).decode("gbk", "replace").split("\r\n")
            except OSError:
                continue
            base = 8 + 13 * n + nl
            for i, nm in enumerate(names[:n]):
                size, off = struct.unpack_from("<II", tab, 13 * i)
                if nm.isdigit() and size > 60:
                    self.index[nm] = (path, base + off, size)       # 后面的文件覆盖前面的

    @staticmethod
    def blocked(g, x, y):
        cx, cy = int(x) // g["cell"], int(y) // g["cell"]
        if cx < 0 or cy < 0 or cx >= g["cols"] or cy >= g["rows"]:
            return True
        return bool((g["data"][cy * g["stride"] + (cx >> 3)] >> (cx & 7)) & 1)

    def segment_clear(self, map_id, x1, y1, x2, y2):
        """(x1,y1)->(x2,y2) 一路上是否都在可走格里（起点所在格不检查：站在阻挡格上也要能走出来）。没有这张图的碰撞数据时返回 True。"""
        g = self.get(str(map_id))
        if g is None:
            return True
        if self.blocked(g, x1, y1):            # 站在阻挡格上（传送 / 登录落在这里）：只要求落脚点能走，好让人走出来
            return not self.blocked(g, x2, y2)
        n = max(1, int(max(abs(x2 - x1), abs(y2 - y1)) // 4))
        for k in range(1, n + 1):
            if self.blocked(g, x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n):
                return False
        return True

    OBJ = re.compile(rb"\x32\x00([\x05-\x09])([0-9]{5,9})", re.S)

    def objects(self, map_id: str):
        """这张图的前景物件 [{"n","x","y","w","h","d"}]（d = 深度线 = y + h）。

        碰撞位图后面是物件列表，每条 = u16 50 + Pascal 名(51 字节) + u16 宽 高 x y + 3 个 u16 + u8 足迹列数 行数 + 足迹(列数*行数 字节 0/1)。
        不同地图的列表头不一样（8105 是 u32 0 + u32 个数，2801 是 u16 2 + u16 69 + u32 个数），个别图里夹着别的记录类型，
        所以不顺着列表走，而是按「u16 50 + 名字」的特征逐条找、再用尺寸一致性（足迹列数 = ceil(宽/20)、行数 = ceil(高/20)）过滤。"""
        key = "obj:" + map_id
        if key in self.cache:
            return self.cache[key]
        out = []
        ent = self.index.get(map_id)
        g = self.get(map_id)
        if ent and g:
            with open(ent[0], "rb") as f:
                f.seek(ent[1])
                r = f.read(ent[2])
            for m in self.OBJ.finditer(r):
                nm = m.group(2).decode()
                if len(nm) != m.group(1)[0]:
                    continue
                q = m.start() + 53
                if q + 16 > len(r):
                    continue
                w, h, x, y = struct.unpack_from("<4H", r, q)
                fc, fr = r[q + 14], r[q + 15]
                if 0 < w <= g["w"] and 0 < h <= g["h"] and fc == -(-w // 20) and fr == -(-h // 20) and q + 16 + fc * fr <= len(r):
                    out.append({"n": nm, "x": x, "y": y, "w": w, "h": h, "d": y + h})
        self.cache[key] = out
        return out

    def get(self, map_id: str):
        """-> {"w","h","rows","cols","cell","stride","data": bytes} 或 None（没有这张图 / 记录不是碰撞格式）"""
        if map_id in self.cache:
            return self.cache[map_id]
        ent = self.index.get(map_id)
        res = None
        if ent:
            try:
                with open(ent[0], "rb") as f:
                    f.seek(ent[1])
                    r = f.read(ent[2])
                n = r[0]
                if r[1:1 + n].decode("latin1") == map_id and len(r) >= 60:
                    w, h, rows, cols = struct.unpack_from("<HHHH", r, 51)
                    stride = cols // 8 + 1
                    if rows == -(-h // self.CELL) and cols == -(-w // self.CELL) and 59 + rows * stride <= len(r):
                        res = {"w": w, "h": h, "rows": rows, "cols": cols, "cell": self.CELL, "stride": stride, "data": r[59:59 + rows * stride]}
            except (OSError, struct.error):
                res = None
        self.cache[map_id] = res
        return res


# ---------------------------------------------------------------- 最小 WebSocket
class WS:
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer
        self.open = True

    async def recv(self):
        """返回一条文本消息；对端关闭返回 None。"""
        buf, started = b"", False
        while True:
            h = await self.r.readexactly(2)
            fin, op = h[0] & 0x80, h[0] & 0x0F
            masked, n = h[1] & 0x80, h[1] & 0x7F
            if n == 126:
                n = struct.unpack(">H", await self.r.readexactly(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", await self.r.readexactly(8))[0]
            if n > MAX_WS_MSG or len(buf) + n > MAX_WS_MSG:
                await self.close(1009)
                return None
            mask = await self.r.readexactly(4) if masked else b"\0\0\0\0"
            data = bytearray(await self.r.readexactly(n))
            if masked:
                for i in range(n):
                    data[i] ^= mask[i & 3]
            if op == 8:
                await self.close(1000)
                return None
            if op == 9:
                await self._send(10, bytes(data))
                continue
            if op == 10:
                continue
            if op in (1, 2):
                started = op == 1
                buf = bytes(data)
            elif op == 0 and started:
                buf += bytes(data)
            if fin and started:
                return buf.decode("utf8", errors="replace")

    async def _send(self, op, data: bytes):
        if not self.open:
            return
        n = len(data)
        head = bytes([0x80 | op])
        if n < 126:
            head += bytes([n])
        elif n < 65536:
            head += b"\x7e" + struct.pack(">H", n)
        else:
            head += b"\x7f" + struct.pack(">Q", n)
        try:
            self.w.write(head + data)
            await self.w.drain()
        except (ConnectionError, OSError):
            self.open = False

    async def send_json(self, obj):
        await self._send(1, json.dumps(obj, ensure_ascii=False).encode("utf8"))

    async def close(self, code=1000):
        if self.open:
            await self._send(8, struct.pack(">H", code))
            self.open = False
        try:
            self.w.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 会话
SOCIAL_OPS = ("party", "org", "trade", "kf", "nick", "pw", "item_info", "recycle", "biaoju_send", "biaoju_query", "biaoju_jobs", "biaoju_claim", "work_start", "work_stop", "farm_start", "masters", "study", "read_book")
SOCIAL_FRAMES = {0x2A, 0x2B, 0x2D, 0x2E, 0x2F, 0x4F, 0x54, 0x55, 0x56, 0x57, 0xAD, 0x39, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x82, 0x32}


class Session:
    def __init__(self, gw, ws):
        self.gw, self.ws = gw, ws
        self.c: JyClient | None = None
        self.debug = False
        self.loop = asyncio.get_running_loop()
        self.out = asyncio.Queue()
        self.busy = False
        self.creating = False         # 新账号：握手之后、进入世界之前（摇点 / 起名 / 进入）
        self.jyid = self.pw = None    # 登录用的账号 / 密码（重新同步时用）
        self._social_h = None
        self._fight_task = None
        self._work_task = None
        self._farming = False
        self._zone_in = None                 # 当前站在哪个门里（去重用）
        self._fight_enter_h = None
        self._last_act = 0.0
        self._last_move = 0.0
        self.dlg = None
        self.last_say = 0.0
        self._refresh_h = None

    def emit(self, obj):
        self.out.put_nowait(obj)

    # --- 浏览器 -> 游戏
    async def handle(self, msg: dict):
        op = msg.get("op")
        if op == "login":
            pw = msg.get("password")
            await self.login(msg.get("jyid"), pw if isinstance(pw, str) and 0 < len(pw) <= 32 and pw.isascii() else None)
        elif op == "debug":
            self.debug = bool(msg.get("on"))
        elif op == "logout":
            await self.logout()
            self.emit({"ev": "closed"})
        elif op == "delete_role":
            await self.delete_role(msg)
        elif op in ("roll", "create_name", "create_enter"):
            await self.create_op(op, msg)
        elif not self.c or not self.me_ready():
            self.emit({"ev": "error", "msg": "还没有登录"})
        elif op == "say":
            text = re.sub(r"[\x00-\x1f\x7f]", "", str(msg.get("text", "")))[:60].strip()
            now = time.time()
            if not text:
                return
            if now - self.last_say < 0.5:
                self.emit({"ev": "error", "msg": "说话太快了"})
                return
            self.last_say = now
            if text.startswith("@"):          # 文字指令（@where @cpw @scb …，只发 ASCII）：回复来自服务端，不在本地回显
                await self.c.command(text)
                return
            ch = msg.get("ch", "public")
            me = self.c.me["fields"]["jyid"]
            if ch == "whisper":
                v = self._ints(msg, "to", hi=0xFFFFFFFF)
                if not v:
                    return
                await self.c.whisper(v[0], text)
                self.emit({"ev": "chat", "ch": "whisper", "jyid": me, "name": "对 " + (self.c.names.get(v[0]) or str(v[0])), "text": text, "self": True})
            elif ch == "party":
                await self.c.party_chat(text)       # 队伍聊天发送者自己也会收到 0x1C，不在这里回显
            elif ch == "org":
                await self.c.org_chat(text)
                self.emit({"ev": "chat", "ch": "org", "jyid": me, "name": self.c.me["name"], "text": text, "self": True})
            else:
                await self.c.say(text)
                self.emit({"ev": "chat", "jyid": me, "name": self.c.me["name"], "text": text, "self": True})
        elif op == "move":
            try:
                x, y = int(msg["x"]), int(msg["y"])
            except (KeyError, TypeError, ValueError):
                return
            if not (0 <= x < 65536 and 0 <= y < 65536):
                return
            sx, sy = self.c.pos
            if not self.gw.walk.segment_clear(self.c.map_id, sx, sy, x, y):
                self.emit({"ev": "error", "msg": "这条路被地形挡住了"})      # 原版服务端不校验，网关替客户端把关
                return
            await self.c.move(sx, sy, x, y)
        elif op == "teleport":
            v = self._ints(msg, "map", "x", "y")
            if v:
                await self.c.teleport(*v)
        elif op == "equip":
            v = self._ints(msg, "slot", "item", hi=0xFFFFFFFF)
            if not v or v[0] not in SLOT_NAME:
                self.emit({"ev": "error", "msg": "槽位无效"})
                return
            slot = next((s for s in self.c.me["bag"] if s["item_id"] == v[1]), None)
            if slot is None:      # 网关先拦住：背包没有的物品发给服务端会触发全服「嘗試刷裝備」广播
                self.emit({"ev": "error", "msg": "背包里没有这件物品"})
                return
            await self.c.equip(v[0], v[1], slot["byte5"])
        elif op == "unequip":
            v = self._ints(msg, "slot", hi=255)
            if not v or v[0] not in SLOT_NAME:
                self.emit({"ev": "error", "msg": "槽位无效"})
                return
            await self.c.unequip(v[0])
        elif op == "use":
            v = self._ints(msg, "item", hi=0xFFFFFFFF)
            if v:
                await self.c.use_item(v[0])
        elif op == "bank_open":
            await self.c.bank_open()
        elif op in ("bank_put", "bank_get"):
            v = self._ints(msg, "item", "n", hi=0xFFFFFFFF)
            if not v or not 1 <= v[1] <= 65535:
                self.emit({"ev": "error", "msg": "数量无效"})
                return
            if op == "bank_put" and not any(b["item_id"] == v[0] for b in self.c.me["bag"]):
                self.emit({"ev": "error", "msg": "背包里没有这件物品"})
                return
            if self.c.bank is None:           # 没打开过钱庄：先取清单，之后的存取才能在本地状态里对上
                await self.c.bank_open()
                await asyncio.sleep(0.3)
            await (self.c.bank_put if op == "bank_put" else self.c.bank_get)(v[0], v[1])
        elif op == "discard":
            v = self._ints(msg, "item", hi=0xFFFFFFFF)
            if not v:
                return
            if not any(b["item_id"] == v[0] for b in self.c.me["bag"]):
                self.emit({"ev": "error", "msg": "背包里没有这件物品"})
            elif v[0] in self.gw.items.notrade:
                self.emit({"ev": "error", "msg": "此物品不能丟棄"})
            else:
                await self.c.discard(v[0], 1)
                self.emit(self.gw.view_ground(self.c))
                self.refresh_soon()
        elif op == "pickup":
            v = self._ints(msg, "i", hi=100000)
            if not v or v[0] >= len(self.c.ground):
                self.emit({"ev": "error", "msg": "地上没有这件东西"})
                return
            g = self.c.ground[v[0]]
            await self.c.pickup(g["id"], g["n"], g["dur"])
        elif op in SOCIAL_OPS:
            await self.social_op(op, msg)
        elif op in ("fight_start", "fight_act", "fight_move", "fight_pose", "fight_escape"):
            await self.fight_op(op, msg)
        elif op == "talk":
            await self.talk(msg)
        elif op == "dlg":
            await self.dlg_answer(msg)
        elif op == "dlg_close":
            self.dlg_end()
        elif op == "shop_open":
            v = self._ints(msg, "merchant")
            if v:
                await self.c.shop_open(v[0])
        elif op == "buy":
            lst = msg.get("items")
            if not isinstance(lst, list) or not 1 <= len(lst) <= 20:
                self.emit({"ev": "error", "msg": "购买列表无效"})
                return
            buy = []
            for it in lst:
                v = self._ints(it if isinstance(it, dict) else {}, "item", "n", hi=0xFFFFFFFF)
                if not v or not 1 <= v[1] <= 9999:
                    self.emit({"ev": "error", "msg": "购买数量无效"})
                    return
                buy.append((v[0], v[1]))
            await self.c.buy(buy)
        else:
            self.emit({"ev": "error", "msg": "未知操作 %r" % op})

    # --- 战斗（协议见 战斗协议_客户端侧.md；怪物 AI 与胜负判定按原版放在客户端 = 这里）
    async def fight_op(self, op, msg):
        c = self.c
        f = c.fight
        if op == "fight_start":
            if self._fight_task and not self._fight_task.done():
                self.emit({"ev": "error", "msg": "已经在战斗中"})
                return
            v = self._ints(msg, "mob", hi=99999)
            if not v or v[0] < 1:
                self.emit({"ev": "error", "msg": "怪物编号无效"})
                return
            if int(c.me["fields"].get("dangqianxue") or 0) <= 0:
                self.emit({"ev": "error", "msg": "气血为 0，先用药恢复再战斗"})
                return
            self._fight_enter_h = None
            self.fight_npc = msg.get("npc") if isinstance(msg.get("npc"), int) and not isinstance(msg.get("npc"), bool) else None
            n = msg.get("n")
            n = n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 5 else 1       # 同种怪的数量（事件战斗动作里的数量；新服务端扩展，原版填零 = 1 只）
            await c.fight_encounter(100000000 + v[0], n)
            self._fight_task = asyncio.create_task(self.fight_loop())
            self.emit({"ev": "status", "text": "遭遇 %s …" % ((self.gw.items.mobs.get(v[0]) or {}).get("name") or "怪#%d" % v[0])})
            return
        if op == "fight_move":                                # 战斗内走到某格（C2S 0xD4）；格子范围由页面按场地限制，这里只防乱发
            if not f.entered or f.end_sent or f.ended_by_server or f.result:
                self.emit({"ev": "error", "msg": "现在不能移动"})
                return
            v = self._ints(msg, "col", "row", hi=255)
            if not v:
                return
            now = time.time()
            if now - self._last_move < 0.25:
                return
            me = c.me["fields"]["jyid"]
            cur = f.ents.get(me)
            if cur is not None and cur.col is not None and max(abs(v[0] - cur.col), abs(v[1] - cur.row)) > 8:
                self.emit({"ev": "error", "msg": "太远了"})
                return
            if any(e.alive and e.col == v[0] and e.row == v[1] for e in f.ents.values() if e.id != me):
                return
            self._last_move = now
            await c.fight_move(v[0], v[1], tick=int(now * 10) & 0xFFFF)
            return
        if op in ("fight_pose", "fight_escape"):              # 命令栏：防禦 / 閃躲 / 養精蓄銳 / 自動（C2S 0xDE）、逃跑（C2S 0xF9）
            if not f.entered or f.end_sent or f.ended_by_server or f.result:
                self.emit({"ev": "error", "msg": "现在不能下这个命令"})
                return
            now = time.time()
            if now - self._last_act < 1.3:                   # 和出招共用间隔（原版同一个"攻击间隔"计数器）
                self.emit({"ev": "error", "msg": "命令太快了"})
                return
            if op == "fight_escape":
                self._last_act = now
                await c.fight_escape()
                self.emit({"ev": "status", "text": "已请求逃跑（原版只在逃离点有效，成败由服务端决定）"})
                return
            v = self._ints(msg, "cmd", hi=255)
            if not v or v[0] not in jyfight.POSE_CMDS:
                self.emit({"ev": "error", "msg": "命令无效"})
                return
            self._last_act = now
            await c.fight_pose(v[0])
            return
        # fight_act：对某个活着的怪出一招
        if not f.entered or f.end_sent or f.ended_by_server or f.result:
            self.emit({"ev": "error", "msg": "现在不能出招"})
            return
        now = time.time()
        if now - self._last_act < 1.3:                       # 原版：攻击间隔 < 0x514(1300ms) 会被踢
            self.emit({"ev": "error", "msg": "出招太快了"})
            return
        v = self._ints(msg, "target", hi=0xFFFFFFFF)
        me = c.me["fields"]["jyid"]
        t = f.ents.get(v[0]) if v else None
        if t is None:
            t = next((e for e in f.ents.values() if e.team == 2 and e.alive and not e.left), None)
        if t is None or t.team != 2 or not t.alive or t.col is None:
            self.emit({"ev": "error", "msg": "没有可以攻击的目标"})
            return
        kf = None
        lv = 0
        kv = self._ints(msg, "kf", hi=65535)
        if kv:
            row = next((r for r in self.gw.kf_rows(c.me) if r["id"] == kv[0] and r["lv"] > 0), None)
            if not row:
                self.emit({"ev": "error", "msg": "没有这门武功"})
                return
            kf, lv = row["id"], row["lv"]
        self._last_act = now
        skill = (kf * 100 + 1) if kf else jyfight.BASIC_SKILL
        await c.fight_act(me, (t.col, t.row), skill=skill, cmd=3 if kf else 2, level=lv, tick=int(now * 10) & 0xFFFF)

    async def fight_loop(self):
        """遭遇后的客户端侧逻辑：D1 到了就发 E3 进战；之后每 0.5 秒替怪出招、判胜负、等够时间发 E5。"""
        c = self.c
        f = c.fight
        t0 = t_enter = time.time()
        last = None
        try:
            while c and not c.closed and self.c is c:
                if not f.entered:
                    if f.d1 is not None:
                        await c.fight_enter()
                        t_enter = time.time()
                    elif time.time() - t0 > 5:
                        self.emit({"ev": "error", "msg": "服务端没有开战（遭遇无回应）"})
                        return
                else:
                    if not f.ready and not f.end_sent and time.time() - t_enter > 6:
                        # 进战包（E3）之后服务端没有任何推送：原版单人时对 E3 本来就不回包（服务端程序里 E3 只转发给队友），也不发战场名单；
                        # 新服务端会回 D5 / C6。不收尾的话原版会一直留着这场遭遇，下一次 0x30 不回 D1，所以主动发 E5 离场。
                        self.emit({"ev": "error", "msg": "服务端没有推送战场（原版单人时对 E3 不回包、也不发战场名单，客户端目前没法在原版上渲染战斗）；已离场"})
                        await c.fight_end()
                        f.ended_by_server = True          # 让页面把战斗标成已结束（下面照常推一次视图再退出循环）
                    else:
                        await c.fight_tick(delay=self.gw.end_delay, interval=self.fight_interval())
                sig = (f._n, f.result, f.end_sent, f.entered)
                if sig != last:
                    last = sig
                    vf = self.gw.view_fight(c)
                    vf["npc"] = getattr(self, "fight_npc", None)
                    vf["itv"] = self.fight_interval()
                    self.emit(vf)
                if f.ended_by_server:
                    break
                await asyncio.sleep(0.5)
            vf = self.gw.view_fight(c)
            vf["npc"] = getattr(self, "fight_npc", None)
            vf["itv"] = self.fight_interval()
            self.emit(vf)
            self.refresh_soon()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.emit({"ev": "error", "msg": "战斗循环出错 %r" % e})

    def fight_interval(self):
        """怪物出招间隔：MOB数据.csv 的"聚气速度"(缺省 50) → 200/速度 秒（猜测的换算，反编译里的集气公式没解出来）。"""
        sp = [(self.gw.items.mobs.get(jyfight.mob_id(e.id)) or {}).get("speed", 50) for e in self.c.fight.ents.values() if e.team == 2 and e.alive]
        return 200.0 / max(sp) if sp else 4.0

    # --- 组队 / 组织 / 交易 / 武功 / 账号类
    def _text(self, msg, key="text", n=60):
        return re.sub(r"[\x00-\x1f\x7f]", "", str(msg.get(key, "")))[:n].strip()

    async def social_op(self, op, msg):
        c = self.c
        a = msg.get("a")
        if op == "party":
            if a == "create":
                await c.party_create()
            elif a in ("invite", "answer"):
                v = self._ints(msg, "jyid", hi=0xFFFFFFFF)
                if not v:
                    return
                if a == "invite":
                    await c.party_invite(v[0])
                else:
                    await c.party_answer(v[0], bool(msg.get("accept")))
                    c.team_invites = [i for i in c.team_invites if i != v[0]]
            elif a == "leave":
                await c.party_leave()
            elif a == "disband":
                await c.party_disband()
            else:
                self.emit({"ev": "error", "msg": "未知队伍操作"})
        elif op == "org":
            if a == "create":
                name = self._text(msg, "name", 24)
                if not name:
                    self.emit({"ev": "error", "msg": "组织名不能为空"})
                    return
                await c.org_create(name)
            elif a in ("recruit", "join"):
                v = self._ints(msg, "jyid", hi=0xFFFFFFFF)
                if v:
                    await (c.org_recruit if a == "recruit" else c.org_join)(v[0])
                    if a == "join":
                        c.org_invites = [i for i in c.org_invites if i["creator"] != v[0]]
            elif a == "list":
                await c.org_list()
            elif a == "kick":
                name = self._text(msg, "name", 20)
                if name:
                    await c.org_kick(name)
            elif a == "quit":
                await c.org_quit()
            elif a == "query":
                v = self._ints(msg, "sub", hi=255)
                if v:
                    await c.org_query_status(v[0])
            else:
                self.emit({"ev": "error", "msg": "未知组织操作"})
        elif op == "trade":
            if a == "request":
                v = self._ints(msg, "jyid", hi=0xFFFFFFFF)
                if v and v[0] != c.me["fields"]["jyid"]:
                    await c.trade_request(v[0])
            elif not c.trade:
                self.emit({"ev": "error", "msg": "没有进行中的交易"})
            elif a == "item":
                v = self._ints(msg, "item", hi=0xFFFFFFFF)
                if not v:
                    return
                have = sum(1 for b in c.me["bag"] if b["item_id"] == v[0])
                used = sum(1 for o in c.trade["offers"].get(c.me["fields"]["jyid"], []) if o["id"] == v[0])
                if used >= have:
                    self.emit({"ev": "error", "msg": "背包里没有更多这件物品了"})       # 原版不检查，网关替客户端把关（成交时放多了会整笔作废）
                elif v[0] in self.gw.items.notrade:
                    self.emit({"ev": "error", "msg": "此物品不能交易"})
                else:
                    await c.trade_put_item(v[0])
            elif a == "money":
                v = self._ints(msg, "money", hi=0xFFFFFFFF)
                if v:
                    if v[0] > c.me["fields"]["jy_money"]:
                        self.emit({"ev": "error", "msg": "钱不够"})
                        return
                    await c.trade_put_money(v[0])
            elif a == "lock":
                await c.trade_lock()
            elif a == "confirm":
                await c.trade_confirm()
            elif a == "cancel":
                await c.trade_cancel()
            else:
                self.emit({"ev": "error", "msg": "未知交易操作"})
        elif op == "kf":
            if a == "equip":
                v = self._ints(msg, "slot", "id", hi=65535)
                if v and v[0] <= 14:
                    await c.kf_equip(v[0], v[1])
                elif v:
                    self.emit({"ev": "error", "msg": "武功槽位是 0–14"})
            elif a == "delete":
                ids = msg.get("ids")
                pw = str(msg.get("password", ""))[:32]
                if not isinstance(ids, list) or not 1 <= len(ids) <= 16 or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 65535 for i in ids):
                    self.emit({"ev": "error", "msg": "武功编号无效"})
                    return
                await c.kf_delete(pw, ids)
            else:
                self.emit({"ev": "error", "msg": "未知武功操作"})
        elif op == "nick":
            await c.set_nickname(self._text(msg, "text", 20))
        elif op == "pw":
            if a == "zigong":                              # 自宫（不可逆）：C2S 0x98 0D；要 confirm = true 才发
                if msg.get("confirm") is not True:
                    self.emit({"ev": "error", "msg": "自宫不可逆，需要确认"})
                elif c.me["fields"].get("zigong"):
                    self.emit({"ev": "error", "msg": "已经自宫了"})
                else:
                    await c.zigong(str(msg.get("password", ""))[:32])
            else:
                v = self._ints(msg, "sub", hi=255)
                if v and v[0] in (0x0E, 0x0F):
                    await c.password_echo(v[0])
        elif op == "item_info":
            v = self._ints(msg, "item", hi=0xFFFFFFFF)
            if v:
                await c.item_info(v[0])
                await asyncio.sleep(0.3)
                raw = c.item_infos.get(v[0])
                self.emit({"ev": "notice", "kind": 0x40, "text": "%s（%d）：服务端物品信息 %s" % (self.gw.items.name(v[0]), v[0], raw.hex() if raw is not None else "无回应")})
        elif op == "recycle":
            v = self._ints(msg, "item", "n", hi=0xFFFFFFFF)
            if not v or not 1 <= v[1] <= 255:
                self.emit({"ev": "error", "msg": "数量无效"})
            elif not any(b["item_id"] == v[0] for b in c.me["bag"]):
                self.emit({"ev": "error", "msg": "背包里没有这件物品"})
            else:
                await c.recycle(v[0], v[1])
        elif op == "biaoju_send":                          # 託鏢：{"name": 收件人名字, "item": 打工物品 id, "n": 件数}
            v = self._ints(msg, "item", "n", hi=0xFFFFFFFF)
            nm = msg.get("name")
            if not v or not 1 <= v[1] <= 255:
                self.emit({"ev": "error", "msg": "数量无效"})
            elif not isinstance(nm, str) or not 1 <= len(nm.strip()) <= 12:
                self.emit({"ev": "error", "msg": "请填收件人的名字"})
            elif not biaoju.is_job_item(v[0]):
                self.emit({"ev": "error", "msg": "只有打工物品（镖局的包裹 / 运镖车）能託鏢"})
            elif sum(1 for b in c.me["bag"] if b["item_id"] == v[0]) < v[1]:
                self.emit({"ev": "error", "msg": "背包里没有这么多件"})
            else:
                try:
                    await c.biaoju_send(nm.strip(), v[0], v[1])
                except (ValueError, UnicodeEncodeError) as e:
                    self.emit({"ev": "error", "msg": "託鏢失败：%s" % e})
        elif op == "work_start":                           # 生活技能：{"job": 1 伐木 / 2 捕魚 / 3 採礦}；每 8 秒一轮由网关自己发，直到停止 / 精力不足
            v = self._ints(msg, "job", hi=3)
            if v:
                await self.work_start(v[0])
        elif op == "farm_start":                           # 農夫：{"seed": 种子物品 id（可省，默认背包里第一种）, "plot": 田块号 0..19（可省）}；播種 → 耕種 → 收成循环
            seed = msg.get("seed")
            if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 65535):
                self.emit({"ev": "error", "msg": "参数 seed 无效"})
            else:
                v = self._ints({"plot": msg.get("plot", 0)}, "plot", hi=FARM_PLOTS - 1)
                if v:
                    await self.farm_start(seed, v[0])
        elif op == "read_book":                            # 读秘笈学特殊武功（C2S 0x60）：{"item": 35022 / 35031 / 40177}；原版会扣书的情况网关先拦下
            v = self._ints(msg, "item", hi=0xFFFF)
            if v:
                err = books.check(v[0], c.me["fields"], {k["id"] for k in self.gw.kf_rows(c.me)})
                if err is None and not any(b["item_id"] == v[0] for b in c.me["bag"]):
                    err = "背包里没有这件物品"
                if err:
                    self.emit({"ev": "error", "msg": "读秘笈：%s" % err})
                else:
                    await c.read_book(v[0])
        elif op == "masters":                              # 这张图上的师傅和他们教的武功（师傅.csv）→ 事件 masters
            self.emit(self.gw.view_masters(c))
        elif op == "study":                                # 消点：{"master": 师傅 ID, "kf": 武功 ID, "points": 点数}（要会话校验字节）
            v = self._ints(msg, "master", "kf", "points")
            if v:
                await self.study(*v)
        elif op == "work_stop":
            await self.work_stop("已停止")
        elif op == "biaoju_query":
            await c.biaoju_query()
        elif op == "biaoju_claim":                         # 取鏢：{"rows": [清单里的行号，1 起]}（要会话校验字节，只有 Windows + loginp.exe + unicorn 才算得出）
            rows = msg.get("rows")
            if not isinstance(rows, list) or not rows or not all(isinstance(r, int) and not isinstance(r, bool) and 1 <= r <= 254 for r in rows) or len(rows) > 50:
                self.emit({"ev": "error", "msg": "行号无效"})
            elif len(rows) > len(c.biaoju_list):
                self.emit({"ev": "error", "msg": "先点「查看我的鏢局存放」再取"})
            else:
                try:
                    await c.biaoju_claim(rows)
                except RuntimeError as e:
                    self.emit({"ev": "error", "msg": "取鏢失败：%s" % e})
                else:
                    if c.last_claim_padded:           # 补位的包服务端不回 0x4B：等一下重登取真实背包
                        self.loop.call_later(2.0, lambda: self.loop.create_task(self.resync("取鏢（补位）")))
        elif op == "biaoju_jobs":
            v = self._ints(msg, "sub", hi=255)
            if v:
                await c.biaoju_jobs(v[0])
        self.social_soon()

    def social_soon(self):
        if self._social_h is None:
            self._social_h = self.loop.call_later(0.2, self._social)

    def _social(self):
        self._social_h = None
        if self.c and self.c.me:
            self.emit(self.gw.view_social(self.c))

    async def delete_role(self, msg):
        """删除角色（0x33）只能在选角色界面用：单开一条连接，握手成功后只发 0x33，不进入世界。"""
        v = self._ints(msg, "jyid", hi=0x7FFFFFFF)
        pw = str(msg.get("password", ""))[:32]
        if not v or v[0] < 1 or not pw:
            self.emit({"ev": "error", "msg": "要账号和密码"})
            return
        if self.c or self.busy:
            self.emit({"ev": "error", "msg": "先退出再删除角色"})
            return
        self.busy = True
        c = JyClient(self.gw.up_host, self.gw.up_port, name="del%d" % v[0])
        try:
            try:
                await asyncio.wait_for(c.connect(), 5)
            except (OSError, asyncio.TimeoutError):
                self.emit({"ev": "error", "msg": "连不上游戏服务端"})
                return
            if await c.login(v[0], timeout=6, password=pw) is None:
                self.emit({"ev": "error", "msg": "服务端没有回应登录（账号不存在 / 密码不对 / 已在别处登录）"})
                return
            await c.delete_role(pw)
            fr = await c.drain(0.8)
            if c.deleted:
                self.emit({"ev": "status", "text": "账号 %d 的角色已删除，再登录会进入新建角色流程" % v[0]})
            else:
                self.emit({"ev": "error", "msg": "删除失败：%s" % ("".join(from_big5(f.payload[1:]) for f in fr if f.type == 0x1A) or "服务端没有回应")})
        finally:
            await c.close()
            self.busy = False

    async def create_op(self, op, msg):
        c = self.c
        if not (self.creating and c):
            self.emit({"ev": "error", "msg": "现在不在新建角色流程里"})
            return
        if op == "roll":
            await c.roll()
            await asyncio.sleep(0.5)
            self.emit({"ev": "roll", "attrs": c.roll_result})
        elif op == "create_name":
            name = self._text(msg, "name", 8)
            if not name:
                self.emit({"ev": "error", "msg": "名字不能为空"})
                return
            c.name_result = None
            await c.create_name(name)
            await asyncio.sleep(0.5)
            self.emit({"ev": "name_result", "name": name, "ok": c.name_result == 0})
        else:
            name = self._text(msg, "name", 8)
            attrs = msg.get("attrs")
            if not name or not isinstance(attrs, list) or len(attrs) != 7 or not all(isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 99 for x in attrs) or sum(attrs) > 145:
                self.emit({"ev": "error", "msg": "名字或属性无效（7 项属性总和不能超过 145）"})
                return
            v = self._ints(msg, "map", "head", "mode", "month", "day", hi=65535)
            if not v:
                return
            await c.create_enter(name, v[0], attrs, head=v[1] & 255, mode=v[2] & 255, month=v[3] & 255, day=v[4] & 255, nick=self._text(msg, "nick", 8))

    async def resync(self, why):
        """交易成交 / 作废都没有明确的背包刷新帧：重新登录取一份真实状态（会让同图的人看到一次下线 / 上线）。"""
        if self.busy or not self.c or not self.jyid:
            return
        self.emit({"ev": "status", "text": why + "：重新同步角色状态 …"})
        await self.logout()
        for _ in range(4):
            await asyncio.sleep(0.6)
            await self.login(self.jyid, self.pw)
            if self.c:
                return
        self.emit({"ev": "closed"})

    # --- NPC 对话（事件脚本，见 evtengine.py）
    def dlg_end(self):
        g, self.dlg = self.dlg, None
        if g:
            g.close()

    async def talk(self, msg):
        v = self._ints(msg, "npc")
        if not v:
            return
        c = self.c
        mp = str(c.map_id)
        npc = next((n for n in self.gw.npc.get(mp) if n["id"] == v[0]), None)
        if npc and npc["model"] >= 50000 and not npc["events"]:        # 普通怪物刷新点（没有事件）：走近了直接开战，怪 = 型号（MOB id）
            sx, sy = c.pos
            cs = self.gw.cell_of(mp)
            if abs(npc["x"] * cs + cs // 2 - sx) > 400 or abs(npc["y"] * cs + cs // 2 - sy) > 400:
                self.emit({"ev": "error", "msg": "离 %s 太远了，走近一点" % npc["name"]})
                return
            self.dlg_end()
            await self.fight_op("fight_start", {"mob": npc["model"], "npc": npc["id"]})
            return
        rec = self.gw.events.get(mp)
        if not npc or not rec:
            self.emit({"ev": "error", "msg": "这个 NPC 没有事件数据"})
            return
        sx, sy = c.pos
        cs = self.gw.cell_of(mp)
        if abs(npc["x"] * cs + cs // 2 - sx) > 400 or abs(npc["y"] * cs + cs // 2 - sy) > 400:
            self.emit({"ev": "error", "msg": "离 %s 太远了，走近一点" % npc["name"]})
            return
        self.dlg_end()
        fields = c.me["fields"]
        state = evtengine.PlayerState([s["item_id"] for s in c.me["bag"]], fields, kf={r["id"]: r["lv"] for r in self.gw.kf_rows(c.me)}, clock=c.game_time())
        eng = evtengine.Engine(rec, self.gw.texts, state, me_name=c.me["name"], npc_name=npc["name"], speakers=self.gw.speakers())
        self.dlg = eng.talk(npc["events"])
        self.dlg_npc = npc["id"]
        self.dlg_n = 0
        await self.dlg_step(None, first=True)

    # --- 触发区（门 / 出入口）：人走进矩形就跑区域的事件（多半是传送）
    def zone_at(self, map_id, x, y):
        """(x, y) 像素落在哪个『門』触发区里（有事件的），没有返回 None；返回 (地图, 区号, 序号) 用来去重"""
        cs = self.gw.cell_of(map_id)
        for k, z in enumerate(self.gw.npc.zones(str(map_id))):
            if z["kind"] == "door" and z["events"] and z["x"] * cs <= x <= z["x"] * cs + z["w"] and z["y"] * cs <= y <= z["y"] * cs + z["h"]:
                return (map_id, z["id"], k)
        return None

    async def check_zone(self):
        c = self.c
        if not c or c.closed or not c.pos or c.map_id is None or self.dlg or self._fight_task:
            return
        key = self.zone_at(c.map_id, *c.pos)
        if key is None:
            self._zone_in = None
            return
        if key == self._zone_in:
            return
        self._zone_in = key
        z = self.gw.npc.zones(str(c.map_id))[key[2]]
        rec = self.gw.events.get(str(c.map_id))
        if not rec:
            return
        fields = c.me["fields"]
        state = evtengine.PlayerState([s["item_id"] for s in c.me["bag"]], fields, kf={r["id"]: r["lv"] for r in self.gw.kf_rows(c.me)}, clock=c.game_time())
        eng = evtengine.Engine(rec, self.gw.texts, state, me_name=c.me["name"], npc_name="", speakers=self.gw.speakers())
        if not any(0 <= e < len(rec["nodes"]) and rec["nodes"][e]["main"] and eng.node_ok(e) for e in z["events"]):
            return                                    # 条件都不满足：门不动，不提示
        self.dlg = eng.talk(z["events"])
        self.dlg_npc = None
        self.dlg_n = 0
        await self.dlg_step(None, first=True)

    async def dlg_answer(self, msg):
        if not self.dlg:
            return
        i = msg.get("i")
        await self.dlg_step(i if isinstance(i, int) and not isinstance(i, bool) else None)

    async def dlg_step(self, answer, first=False):
        """推进对话生成器直到下一个要用户操作的步骤（一页话 / 一个选单）；效果事件在中途直接发给服务端。"""
        g = self.dlg
        try:
            while True:
                self.dlg_n += 1
                if self.dlg_n > 400:
                    raise StopIteration
                st = next(g) if first or answer is None else g.send(answer)
                first = False
                answer = None
                t = st["t"]
                if t == "say":
                    self.emit({"ev": "dialog", "kind": "say", "side": st["side"], "who": st["who"], "text": st["text"]})
                    return
                if t == "menu":
                    self.emit({"ev": "dialog", "kind": "menu", "who": st["who"], "text": st["prompt"], "options": st["options"]})
                    return
                if t == "effect":
                    await self.c.event(st["ev"])
                elif t == "shop":
                    self.emit({"ev": "dialog", "kind": "end"})
                    self.dlg = None
                    await self.c.shop_open(st["merchant"])
                    return
                elif t == "teleport":                    # 事件里的传送动作（传送員 / 羽士 / 各门派入口）：结束对话，C2S 0x5D 过去
                    self.emit({"ev": "dialog", "kind": "end"})
                    self.dlg = None
                    mp = str(st["map"])
                    if not self.gw.has_map(mp):
                        self.emit({"ev": "notice", "kind": 0x40, "text": "（目的地是地图 %s，这张图的画面网页版还画不出来，已取消传送；可以用「导航」页去能显示的地方）" % mp})
                        return
                    cs = self.gw.cell_of(mp)
                    await self.c.teleport(st["map"], st["x"] * cs + cs // 2, st["y"] * cs + cs // 2)
                    return
                elif t == "fight":                       # 事件里的战斗动作：结束对话，和第一个有资料的对手开战（服务端一次遭遇只有一只怪）
                    self.emit({"ev": "dialog", "kind": "end"})
                    self.dlg = None
                    tab = self.gw.items.mobs
                    mob = next((m for m in st["mobs"] if not tab or m["mob"] in tab), None)
                    if mob:
                        await self.fight_op("fight_start", {"mob": mob["mob"], "npc": getattr(self, "dlg_npc", None), "n": mob.get("n", 1)})
                    else:
                        self.emit({"ev": "notice", "kind": 0x40, "text": "（這場戰鬥的對手沒有資料）"})
                    return
                elif t in ("note", "todo"):
                    self.emit({"ev": "notice", "kind": 0x40, "text": st["text"]})
        except StopIteration:
            pass
        self.dlg = None
        self.emit({"ev": "dialog", "kind": "end"})

    def _ints(self, msg, *names, hi=65535):
        """取整数字段并检查范围 0..hi；不合格时给浏览器报错并返回 None。"""
        out = []
        for n in names:
            v = msg.get(n)
            if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= hi:
                self.emit({"ev": "error", "msg": "参数 %s 无效" % n})
                return None
            out.append(v)
        return out

    def me_ready(self):
        return bool(self.c and self.c.me and not self.c.closed)

    async def login(self, jyid, password=None):
        if self.c and self.c.closed and not self.busy:      # 服务端把连接断了（被顶号 / 重启）：清掉旧连接，允许重新登录
            await self.logout()
        if self.busy or self.c:
            self.emit({"ev": "error", "msg": "已经在登录 / 已登录"})
            return
        if not isinstance(jyid, int) or isinstance(jyid, bool) or not 1 <= jyid <= 0x7FFFFFFF:
            self.emit({"ev": "error", "msg": "账号必须是正整数"})
            return
        self.busy = True
        c = JyClient(self.gw.up_host, self.gw.up_port, name="web%d" % jyid)   # login()/start() 要用队列等帧，结束后 stop_queue()
        try:
            self.emit({"ev": "status", "text": "正在连接 %s:%d …" % (self.gw.up_host, self.gw.up_port)})
            try:
                await asyncio.wait_for(c.connect(), 5)
            except (OSError, asyncio.TimeoutError):
                self.emit({"ev": "error", "msg": "连不上游戏服务端 %s:%d" % (self.gw.up_host, self.gw.up_port)})
                return
            c.listeners.append(self.on_frame)
            hs = await c.login(jyid, timeout=6, password=password)
            if hs is None:
                c.stop_queue()
                self.emit({"ev": "error", "msg": "服务端没有回应登录（账号不存在 / 密码不对 / 被封 / 已在别处登录）"})
                await c.close()
                return
            self.c = c
            self.jyid, self.pw = jyid, password
            if c.base == 0x34:          # 新账号（还没有角色）的握手种子 a2 bc 08 5f -> 密钥 0x34：进入摇点 / 起名流程
                self.creating = True
                self.emit({"ev": "need_create", "jyid": jyid, "births": [3304, 8105, 1305, 2802]})
                self.emit({"ev": "status", "text": "这个账号还没有角色：请摇点、起名字、选出生地"})
                return
            self.emit({"ev": "status", "text": "握手成功，正在载入角色 …"})
            await c.start(timeout=10)
            c.stop_queue()
            if not c.me:
                self.emit({"ev": "error", "msg": "登录序列里没有角色数据"})
                await self.logout()
                return
            self.emit({"ev": "status", "text": "已登录"})
        finally:
            self.busy = False

    # --- 生活技能（伐木 / 捕魚 / 採礦）
    async def work_start(self, job):
        c = self.c
        if job not in lifeskill.JOB_NAMES:
            self.emit({"ev": "error", "msg": "这种工作还没做（農夫走另一套包）"})
            return
        if self._farming:
            self.emit({"ev": "error", "msg": "已经在農夫了，先停止"})
            return
        if c.work:
            self.emit({"ev": "error", "msg": "已经在%s了，先停止" % lifeskill.JOB_NAMES[c.work["job"]]})
            return
        have = {b["item_id"] for b in c.me["bag"]}
        tools = [i for i in lifeskill.tool_ids(self.gw.items.names, job) if i in have]
        if not tools:
            self.emit({"ev": "error", "msg": "背包里没有%s用的工具（%s）" % (lifeskill.JOB_NAMES[job], "斧头" if job == 1 else "钓竿" if job == 2 else "十字镐")})
            return
        if c.me["fields"]["dangqianjing"] <= WORK_MIN_JING:
            self.emit({"ev": "error", "msg": "(精力不足)好..累..喔...."})
            return
        try:
            await c.work_start(job, tools[0])
        except (RuntimeError, ValueError) as e:
            self.emit({"ev": "error", "msg": "开始失败：%s" % e})
            return
        self.emit({"ev": "work", "on": True, "job": job, "name": lifeskill.JOB_NAMES[job], "tool": self.gw.items.name(tools[0])})
        self._work_task = asyncio.create_task(self.work_loop(c))

    async def work_loop(self, c):
        try:
            while c.work and not c.closed:
                await asyncio.sleep(lifeskill.TICK_SECS + 0.2)
                if not c.work or c.closed:
                    return
                if c.me["fields"]["dangqianjing"] <= WORK_MIN_JING:
                    await self.work_stop("(精力不足)好..累..喔....")
                    return
                await c.work_tick()
        except RuntimeError as e:
            await self.work_stop("工作中断：%s" % e)
        except asyncio.CancelledError:
            raise

    # --- 消点（学习点 → 武功经验，C2S 0x5E）
    async def study(self, master, kf, points):
        c = self.c
        f = c.me["fields"]
        # 先按服务端的规则预检：师傅 / 地图 / 门派对不上，原版会随机掉一级武功
        err = self.gw.items.masters.check(master, kf, c.map_id, f.get("school", 0))
        row = self.gw.items.masters.by_pair.get((master, kf))
        mine = {k["id"]: k["lv"] for k in self.gw.kf_rows(c.me)}
        if err is None and kf not in mine:
            err = "还没有这门武功"
        elif err is None and points < 1:
            err = "請輸入大於1的正整數"
        elif err is None and points > f.get("study_count", 0):
            err = "數字已超過上限"
        elif err is None and row and mine[kf] >= row["cap"]:
            err = "學習的技能等級已達極限"
        if err:
            self.emit({"ev": "error", "msg": "消点：%s" % err})
            return
        try:
            await c.study(master, kf, points)
        except RuntimeError as e:
            self.emit({"ev": "error", "msg": "消点失败：%s" % e})

    # --- 農夫（播種 0x5B → 耕種 0x5C/1 → 过一阵 → 收成 0x5C/2，循环到种子用完 / 精力不足 / 停止）
    def farm_seeds(self):
        """背包里的种子：物品名以"种子"结尾的 id（保持背包顺序、去重）。"""
        out = []
        for b in self.c.me["bag"]:
            i = b["item_id"]
            if i not in out and self.gw.items.name(i).endswith("种子"):
                out.append(i)
        return out

    async def farm_start(self, seed, plot):
        c = self.c
        if c.work or self._farming:
            self.emit({"ev": "error", "msg": "已经在工作了，先停止"})
            return
        if c.map_id == ZIXIU_MAP:
            self.emit({"ev": "error", "msg": "自修洞里不能种地（原版会随机降你一级武功）"})
            return
        have = {b["item_id"] for b in c.me["bag"]}
        if not [i for i in lifeskill.tool_ids(self.gw.items.names, 4) if i in have]:
            self.emit({"ev": "error", "msg": "背包里没有農夫用的工具（锄头）"})
            return
        seeds = self.farm_seeds()
        if seed is None:
            seed = seeds[0] if seeds else None
        if seed is None or seed not in seeds:
            self.emit({"ev": "error", "msg": "背包里没有这种种子" if seed is not None else "背包里没有种子"})
            return
        if c.me["fields"]["dangqianjing"] <= WORK_MIN_JING:
            self.emit({"ev": "error", "msg": "(精力不足)好..累..喔...."})
            return
        self._farming = True
        self.emit({"ev": "work", "on": True, "job": 4, "name": "農夫", "tool": "锄头", "seed": self.gw.items.name(seed)})
        self._work_task = asyncio.create_task(self.farm_loop(c, seed, plot))

    async def farm_loop(self, c, seed, plot):
        try:
            while self._farming and not c.closed:
                if not any(b["item_id"] == seed for b in c.me["bag"]):
                    await self.work_stop("种子用完了")
                    return
                if c.me["fields"]["dangqianjing"] <= WORK_MIN_JING:
                    await self.work_stop("(精力不足)好..累..喔....")
                    return
                await c.farm_plant(plot, seed)
                await asyncio.sleep(1.0)
                await c.farm_till(plot)
                await asyncio.sleep(FARM_GROW_SECS)
                await c.farm_harvest(plot)
                await asyncio.sleep(1.5)
        except (RuntimeError, ValueError) as e:
            await self.work_stop("工作中断：%s" % e)
        except asyncio.CancelledError:
            raise

    async def work_stop(self, why):
        c = self.c
        t, self._work_task = self._work_task, None
        if t and t is not asyncio.current_task():
            t.cancel()
        if self._farming:
            self._farming = False
            if c and not c.closed:
                self.emit({"ev": "work", "on": False, "text": why})
            return
        if c and c.work and not c.closed:
            try:
                await c.work_stop()
            except RuntimeError:
                c.work = None
            self.emit({"ev": "work", "on": False, "text": why})
        elif c:
            c.work = None

    async def logout(self):
        self.dlg_end()
        if self._fight_task:
            self._fight_task.cancel()
            self._fight_task = None
        if self._work_task:
            self._work_task.cancel()
            self._work_task = None
        self._farming = False
        c, self.c = self.c, None
        if c:
            c.listeners.clear()
            await c.close()

    # --- 游戏 -> 浏览器
    def on_frame(self, f):
        c = self.c
        if f is None:
            if not self.busy:      # 登录阶段被服务端断开由 login() 报错，不重复提示
                self.emit({"ev": "closed"})
            return
        if self.debug:
            self.emit({"ev": "frame", "type": f.type, "n": len(f.payload)})
        p, t = f.payload, f.type
        if c is None:      # login() 还没返回时 self.c 为空，状态在 JyClient 内部，先忽略
            return
        if t == 0x1E:
            if self.creating:                        # 新角色建好了：登录序列开始，之后和普通登录一样
                self.creating = False
                c.stop_queue()
                self.emit({"ev": "status", "text": "角色已创建，已登录"})
            self.emit(self.gw.view_me(c))
        elif t == 0x04 and len(p) >= 6 and p[0] in (3, 5):
            jy = struct.unpack_from("<I", p, 1)[0]
            self.emit({"ev": "chat", "ch": "whisper" if p[0] == 3 else "org", "jyid": jy, "name": c.names.get(jy) or str(jy), "text": from_big5(p[5:]), "self": False})
        elif t == 0x1C:
            self.emit({"ev": "chat", "ch": "party", "jyid": 0, "name": "队伍", "text": from_big5(p), "self": False})
        elif t == 0x04 and len(p) >= 6 and p[0] == 1:
            jy = struct.unpack_from("<I", p, 1)[0]
            self.emit({"ev": "chat", "jyid": jy, "name": c.names.get(jy) or str(jy), "text": from_big5(p[5:]), "self": False})
        elif t == 0x04 and len(p) >= 6 and p[0] == 2:      # 系统回复（@where / @cpw 的结果）：02 + jyid + 文字
            self.emit({"ev": "notice", "kind": 2, "text": from_big5(p[5:])})
        elif t in (0x68, 0x70) and len(p) >= 12 and c.study_log:         # 学武功 / 消点 / 掉级：jyclient 已改了 kf 行和学习点
            r = c.study_log[-1]
            nm = self.gw.items.kf_names.get(r["kf"]) or "武功#%d" % r["kf"]
            self.emit({"ev": "notice", "kind": t, "text": ("%s 掉了一级，现在 %d 级" if r["lost"] else "%s 现在 %d 级（经验 %d）") % ((nm, r["lv"]) if r["lost"] else (nm, r["lv"], r["exp"]))})
            self.refresh_soon()
            if self.me_ready():
                self.emit(self.gw.view_masters(c))
        elif t == 0xB8 and len(p) >= 1 and p[0] == 0x10:                 # 自宫成功
            self.emit({"ev": "notice", "kind": 0xB8, "text": "自宮成功"})
            self.refresh_soon()
        elif t == 0x14 and len(p) >= 2:
            self.emit({"ev": "notice", "kind": p[0], "text": from_big5(p[1:])})
        elif t in (0x28, 0x27):
            self.emit(self.gw.view_bank(c))
        elif t in (0x0D, 0x10, 0x11):
            self.emit(self.gw.view_ground(c))
        elif t == 0x7B and len(p) >= 6 and p[0] in (0x34, 0x36):
            key = "diet_val" if p[0] == 0x34 else "water_val"
            self.emit({"ev": "patch", key: struct.unpack_from("<I", p, 2)[0]})
        elif t == 0x33 and len(p) >= 8:
            self.emit({"ev": "clock", "t": c.game_time()})              # 心跳 = 游戏时钟校时
        elif t == 0xBC and len(p) >= 2 and p[0] == 0x42:                 # 扩展窗口消息的 0x42 = 公告文字（原版登录时发一条，0x67d208）
            self.emit({"ev": "notice", "kind": 0x42, "text": from_big5(p[1:])})
        elif t == 0x64 and len(p) >= 6:                                  # 生活技能每一轮的结果
            r = lifeskill.parse_64(p)
            job = 4 if self._farming else (c.work or {}).get("job", 1)
            if r:
                if r["ok"] and not r["item_id"]:                       # 掷到"什么也没有"的格子：物品 0 也照发
                    text = "什么也没有得到"
                else:
                    text = ("得到 %s" % self.gw.items.name(r["item_id"])) if r["ok"] else lifeskill.FAIL_TEXT.get(job, "工作失敗")
                self.emit({"ev": "notice", "kind": 0x64, "text": text})
                self.refresh_soon()
        elif t == 0x66 and len(p) >= 8 and self._farming and struct.unpack_from("<I", p, 0)[0] == c.me["fields"]["jyid"]:     # 農夫田块回显（播種 / 耕種）
            if p[7] == 1:
                self.emit({"ev": "notice", "kind": 0x66, "text": "種下 %s" % self.gw.items.name(struct.unpack_from("<H", p, 5)[0])})
                self.refresh_soon()
        elif t == 0x49:                                                  # 鏢局存放清单
            self.emit({"ev": "biaoju", "list": [{"from": r["from"], "id": r["item_id"], "name": self.gw.items.name(r["item_id"]), "dur": r["dur"]} for r in c.biaoju_list]})
        elif t == 0x3F and (c.mail_notice or {}).get("kind") in ("system", "player"):
            who = "系统" if c.mail_notice["kind"] == "system" else (c.names.get(c.mail_notice["sender"]) or str(c.mail_notice["sender"]))
            self.emit({"ev": "notice", "kind": 0x3F, "text": "%s寄信给你（驿站里有新信件）" % who})
        elif t == 0x1A and len(p) >= 1:
            txt = notices.decode_1a(p, from_big5)
            if txt:
                self.emit({"ev": "notice", "kind": 0x1A, "text": txt})
        elif t == 0x09 and len(p) >= 1:
            self.emit({"ev": "shop", "items": [{"id": i["id"], "name": self.gw.items.name(i["id"]), "ok": i["id"] in self.gw.items.buyable}
                                               for i in (c.shop or {}).get("items", [])]})
        elif t in (0x08, 0x06):
            # 0x08 = 自己被传送 / 登录；0x06 = 某人的移动回显，只有自己的才报给页面（页面靠它判断"这一步走完了"）
            mine = t == 0x08 or (len(p) >= 4 and c.me and struct.unpack_from("<I", p, 0)[0] == c.me["fields"]["jyid"])
            if mine and c.pos and c.map_id is not None:
                self.emit({"ev": "pos", "map": c.map_id, "x": c.pos[0], "y": c.pos[1], "tp": t == 0x08})
                if t == 0x08:
                    self._zone_in = self.zone_at(c.map_id, *c.pos)      # 传送到的地方恰好站在门里：不触发，走出去再进来才算
                else:
                    self.loop.create_task(self.check_zone())
        if t in (0x17, 0x18, 0x0B, 0x0A, 0x7B, 0x77, 0x6B, 0x27, 0x10, 0x4B) and t != 0x1E:
            self.refresh_soon()
        if t in (0x02, 0x61, 0x62, 0x05, 0x06):
            self.emit({"ev": "players", "list": self.gw.view_players(c)})
        if t in SOCIAL_FRAMES:
            self.social_soon()
        if t in (0x15, 0x32, 0x7A, 0x6E):
            self.refresh_soon()
        if t == 0x22:                                # 交易结束（成交或整笔作废）：没有背包刷新帧，重新登录取真实状态
            self.loop.create_task(self.resync("交易结束"))

    def refresh_soon(self):
        """装备 / 背包 / 属性变化后，合并 0.15 秒内的多个更新，重发一次完整角色状态。"""
        if self._refresh_h is None:
            self._refresh_h = self.loop.call_later(0.15, self._refresh)

    def _refresh(self):
        self._refresh_h = None
        if self.me_ready():
            self.emit(self.gw.view_me(self.c))

    async def pump(self):
        while True:
            obj = await self.out.get()
            if obj is None:
                return
            await self.ws.send_json(obj)


# ---------------------------------------------------------------- 网关
class Gateway:
    def __init__(self, up_host, up_port, items, maps=None, looks=None, look_fallback=False, walk=None, pic_dir=None, npc=None, events=None, texts=None):
        self.up_host, self.up_port = up_host, up_port
        self.items = items
        self.npc = npc or NpcIndex("")
        self.events = events or EventIndex("")
        self.texts = texts or TextStore("")
        self._speakers = None
        self.maps = maps or MapIndex("")
        self.walk = walk or WalkIndex("")
        self.looks = looks or Looks("")
        self.look_fallback = look_fallback
        self.nspr = NpcSprites()
        self.duty = dutydata.load()                # 任务手册（MyDuty.dat，只有说明文字）
        self.big = None                            # 大地图（野外，pic\MapMrg*.Mrg，一格 48 像素）：地面渲染见 bigmap.py；没有 numpy / PIL 就没有
        if bigmap is not None:
            try:
                self.big = bigmap.BigMaps(pic_dir or DEFAULT_PIC_DIR)
            except Exception:  # noqa: BLE001
                self.big = None
        if self.big is not None:
            _walk_get = self.walk.get

            def _get(mid, _o=_walk_get):          # 大地图没有碰撞数据：按地面类型合成（水不能走）
                g = _o(mid)
                return g if g is not None else (self.big.walk_grid(mid) if self.big.has(mid) else None)
            self.walk.get = _get
        self.guide = guide.load(has_map=self.has_map)      # 游戏自带的 NPC 导航目录 + 新手教学 + MAP.csv 地点（只留画得出来的图）
        self.end_delay = float(os.environ.get("JY_FIGHT_END_DELAY") or jyfight.END_DELAY)    # 判定结果后等多久再发 E5（原版 ~15 秒）；测试可调小
        self.pic_dir = pic_dir or DEFAULT_PIC_DIR
        if look_fallback:
            self.looks.fallback = items.weapon_letter
        self.sessions = 0

    def has_art(self, m):
        """这张图有真背景图（城市图 SceneBG 或大地图 MapMrg）"""
        k = str(m)
        return k in self.maps.index or k.zfill(4) in self.maps.index or (self.big is not None and self.big.has(k))

    def has_map(self, m):
        """这张图网页版能去：有真背景图，或者至少有 NPC / 门的摆放数据（缺背景的图画占位房间，见 room_of）。
        随客户端带的资源里大约 2800 张图（钱庄 / 农田 / 各种室内）没有背景图，也没有碰撞数据，但 NPC 和事件都在——
        新手任务链要走进其中好几张（8122 钱庄、农田 9522 …）"""
        k = str(m)
        return self.has_art(k) or k in self.npc.index or k.zfill(4) in self.npc.index

    def cell_of(self, m):
        """这张图一格多少像素：大地图 48，城市图 20（NPC / 门 / 传送的坐标都是格子坐标）；缺背景的 95xx（农田一类，其它几张 95xx 是 30 × 30 格的大地图）按 48"""
        k = str(m)
        if self.big is not None and self.big.has(k):
            return bigmap.CELL
        if not self.has_art(k) and k.isdigit() and 9500 <= int(k) < 9600:
            return 48
        return 20

    def room_of(self, m):
        """缺背景图的地图的占位房间：{w, h（像素）, cell}。大小 = 摆放的 NPC / 门 往外留一圈，至少 40 × 30 格（95xx 30 × 30 格）。没有数据返回 None"""
        k = str(m)
        if self.has_art(k) or not (k in self.npc.index or k.zfill(4) in self.npc.index):
            return None
        cs = self.cell_of(k)
        xs, ys = [30 if cs == 48 else 40], [30]
        for n in self.npc.get(k):
            xs.append(n["x"] + 8), ys.append(n["y"] + 8)
        for z in self.npc.zones(k):
            xs.append(z["x"] + -(-z["w"] // cs) + 8), ys.append(z["y"] + -(-z["h"] // cs) + 8)
        gw, gh = max(xs), max(ys)
        return {"w": gw * cs, "h": gh * cs, "cell": cs}

    def speakers(self):
        """NPC 型号（= MOB 号）-> 名字，从全部地图的 NPC 摆放里收集（多人对话里的说话者要用）。"""
        if self._speakers is None:
            sp = {}
            for m in self.npc.index:
                for n in self.npc.get(m):
                    sp.setdefault(n["model"], n["name"])
            self._speakers = sp
        return self._speakers

    def look_of(self, f, toukui, yifu, wuqi):
        """外观层列表。模型：renwu.mode / sex / head_image 三个字段在测试号上全是 1，没法验证哪个决定模型，先一律用 1（boy01，男）。"""
        # 自己：renwu.sex = 2（服务端：头像 5..8 建的号）用女模型 girl（128），否则男模型 boy01（1）。其他玩家：0x02 / 0x61 里没有性别 / 模型字节（`01 01` 是常量），只能一律男模型。
        model = 128 if f and f.get("sex") == 2 and self.looks.role(128) else 1
        return self.looks.layers(model, [toukui, yifu, wuqi])

    def view_me(self, c: JyClient):
        me = c.me
        f = me["fields"]
        sec = me["second_string"]
        counts, order = {}, []
        for s in me["bag"]:
            if s["item_id"] not in counts:
                order.append(s["item_id"])
            counts[s["item_id"]] = counts.get(s["item_id"], 0) + 1
        bag = [{"id": i, "name": self.items.name(i), "n": counts[i], "job": biaoju.is_job_item(i), "book": i in books.BOOKS, "use": i in self.items.meds,
                "equip": i in self.items.equips, "slot": self.items.guess_slot(i)} for i in order if not self.items.is_marker(i)]
        quests = self.items.quest_view({i: n for i, n in counts.items() if self.items.is_marker(i)})
        equip = []
        by_name = {v: k for k, v in SLOT_NAME.items()}
        for slot, lst in me["equip"].items():
            e = lst[0]
            equip.append({"slot": slot, "no": by_name[slot], "id": e["item_id"], "name": self.items.name(e["item_id"]) if e["item_id"] else ""})
        keep = ("map", "x", "y", "dangqianjing", "zuidajing", "dangqianxue", "zuidaxue", "dangqianshen", "zuidashen",
                "dangqiannei", "zuidanei", "str", "crg", "wint", "luk", "dex", "agi", "vit", "jy_money", "fame_val",
                "kill_val", "pk_val", "combat_exp", "exp_val", "evil_val", "diet_val", "water_val", "online_time",
                "sex", "school", "master", "study_count", "head_image")
        eq1 = {k: v[0]["item_id"] for k, v in me["equip"].items()}
        ff = {k: f[k] for k in keep}
        if c.map_id is not None and c.pos:          # fields 是上次 0x1E 的快照（登录时的位置）；走过 / 传送过之后用最新的，否则任何一次背包变化都会把页面拉回登录的地图
            ff["map"], ff["x"], ff["y"] = c.map_id, c.pos[0], c.pos[1]
        return {"ev": "me", "jyid": f["jyid"], "name": me["name"],
                "look": self.look_of(f, eq1["toukui"], eq1["yifu"], eq1["wuqi"]),
                "nickname": re.sub(r"^V7Z\d-", "", sec),
                "f": ff, "bag": bag, "quests": quests, "bag_cap": me["bag_capacity"], "equip": equip,
                "kf": self.kf_rows(me), "clock": c.game_time(),
                "wugong": {k: v["lv"] for k, v in me["wugong"].items() if v["lv"]},
                "jineng": {k: v["lv"] for k, v in me["jineng"].items() if v["lv"]}}

    def view_bank(self, c: JyClient):
        return {"ev": "bank", "items": [{"id": b["id"], "name": self.items.name(b["id"]), "n": b["n"]} for b in (c.bank or [])]}

    def view_ground(self, c: JyClient):
        out = []
        for i, g in enumerate(c.ground):
            pos = g.get("pos")
            out.append({"i": i, "id": g["id"], "name": self.items.name(g["id"]), "n": g["n"], "x": pos[0] if pos else None, "y": pos[1] if pos else None,
                        "mine": bool(c.me and g["by"] == c.me["fields"]["jyid"])})
        return {"ev": "ground", "list": out}

    def kf_rows(self, me):
        """kf 行（0x1E 里每行 11 字节：+1 等级 +3..5 经验 LE24 +7..8 武功 ID LE16；最多 16 行）。"""
        out = []
        for h in me.get("kf_rows", []):
            b = bytes.fromhex(h)
            if len(b) >= 9:
                kid = struct.unpack_from("<H", b, 7)[0]
                out.append({"id": kid, "name": self.items.kf_names.get(kid) or "武功#%d" % kid, "lv": b[1], "exp": int.from_bytes(b[3:6], "little")})
        return out

    def view_masters(self, c: JyClient):
        """这张图上的师傅和他们教的武功（师傅.csv），带上我已有的等级，页面「技能」页的消点区用。"""
        mine = {k["id"]: k["lv"] for k in self.kf_rows(c.me)}
        f = c.me["fields"]
        out = []
        for m in self.items.masters.on_map(c.map_id):
            out.append({"master": m["master"], "name": m["name"], "kfs": [
                {"kf": r["kf"], "name": self.items.kf_names.get(r["kf"]) or r["kf_name"], "cap": r["cap"], "school": r["school"], "cls": r["cls"],
                 "lv": mine.get(r["kf"]), "ok": not r["school"] or r["school"] == f.get("school", 0)} for r in m["kfs"]]})
        return {"ev": "masters", "map": c.map_id, "school": f.get("school", 0), "study": f.get("study_count", 0), "list": out}

    def view_fight(self, c: JyClient):
        v = c.fight.view()
        me = c.me["fields"]["jyid"] if c.me else None
        for e in v["ents"]:
            if e["mob"] is not None:
                e["name"] = (self.items.mobs.get(e["mob"]) or {}).get("name") or "怪#%d" % e["mob"]
                e["spr"] = self.nspr.of(e["mob"])
            else:
                e["name"] = (c.names.get(e["id"]) or str(e["id"])) + ("（我）" if e["id"] == me else "")
        for it in v["items"]:
            it["name"] = self.items.name(it["item"])
        v["me"] = me
        v["cell"] = list(c.fight_cell)
        for ev in v["events"]:
            if "item" in ev and ev["item"]:
                ev["item_name"] = self.items.name(ev["item"])
        v["ev"] = "fight"
        return v

    def view_social(self, c: JyClient):
        nm = lambda jy: c.names.get(jy) or str(jy)
        me = c.me["fields"]["jyid"] if c.me else None
        tr = None
        if c.trade:
            t = c.trade
            other = t["with"]
            tr = {"with": {"jyid": other, "name": nm(other)}, "stage": t["stage"],
                  "mine": [{"id": o["id"], "name": self.items.name(o["id"])} for o in t["offers"].get(me, [])],
                  "theirs": [{"id": o["id"], "name": self.items.name(o["id"])} for o in t["offers"].get(other, [])],
                  "money_mine": t["money"].get(me, 0), "money_theirs": t["money"].get(other, 0),
                  "i_locked": me in t["locked"], "they_locked": other in t["locked"]}
        return {"ev": "social",
                "party": {"members": [{"jyid": j, "name": nm(j)} for j in c.my_party()], "invites": [{"jyid": j, "name": nm(j)} for j in c.team_invites]},
                "org": ({"id": c.org["id"], "name": c.org["name"], "online": c.org_online} if c.org else None),
                "org_invites": [{"creator": i["creator"], "cname": nm(i["creator"]), "name": i["name"], "org": i["org"]} for i in c.org_invites],
                "trade": tr, "points": c.mall_points}

    def view_players(self, c: JyClient):
        out = []
        for jy, p in c.players.items():
            lk = p.get("look") or {}
            out.append({"jyid": jy, "name": p.get("name") or c.names.get(jy) or str(jy),
                        "x": p["pos"][0] if p.get("pos") else None, "y": p["pos"][1] if p.get("pos") else None,
                        "look": self.look_of(None, lk.get("toukui", 0), lk.get("yifu", 0), lk.get("wuqi", 0))})
        return out

    # --- HTTP / WS 入口
    async def on_conn(self, reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError, ConnectionError):
            writer.close()
            return
        try:
            lines = head.decode("latin-1").split("\r\n")
            method, target, _ = lines[0].split(" ", 2)
            hdr = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    hdr[k.strip().lower()] = v.strip()
        except ValueError:
            writer.close()
            return
        path = target.split("?", 1)[0]
        if path == "/ws" and hdr.get("upgrade", "").lower() == "websocket":
            await self.serve_ws(reader, writer, hdr)
        elif method == "GET":
            await self.serve_file(writer, path)
        else:
            await self._http(writer, 405, b"method not allowed", "text/plain")

    async def _http(self, writer, code, body: bytes, ctype, cache="no-store"):
        reason = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed", 503: "Service Unavailable"}.get(code, "")
        writer.write(("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: %s\r\n"
                      "X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n" % (code, reason, ctype, len(body), cache)).encode() + body)
        try:
            await writer.drain()
        finally:
            writer.close()

    async def _make_object(self, name, w, h):
        """物件图缓存里没有时现生成（需要 Pillow 和客户端 pic\\Scene*.mrg）；做不到返回 None。"""
        try:
            import build_objects
            return await asyncio.get_running_loop().run_in_executor(None, build_objects.ensure_object, name, w, h, self.pic_dir, OBJ_DIR)
        except BaseException:        # 没装 Pillow 时 wjres 会 sys.exit
            return None

    async def _have_object(self, o):
        return bool(await self._make_object(o["n"], o["w"], o["h"]))

    async def serve_file(self, writer, path):
        m = re.fullmatch(r"/maps/(\d{1,8})\.jpg", path)
        if m:      # 地图背景：从原版 SceneBG*.mrg 里现切
            data = await asyncio.get_running_loop().run_in_executor(None, self.maps.get, m.group(1))
            if data is None:
                return await self._http(writer, 404, b"no background for this map", "text/plain")
            return await self._http(writer, 200, data, "image/jpeg", cache="max-age=3600")
        m = re.fullmatch(r"/objects/(\d{1,8})\.json", path)
        if m:      # 这张图的前景物件（用来让建筑 / 树遮住走到它们后面的人）：[{n,x,y,w,h,d,u}]，u = 贴图地址；贴图缺的物件不列
            if self.big is not None and self.big.has(m.group(1)):      # 大地图：物件层第 1 节（树 / 箭楼…），贴图走 /bigobj/<精灵号>.png
                objs = await asyncio.get_running_loop().run_in_executor(None, self.big.occluders, m.group(1))
                if not objs:
                    return await self._http(writer, 404, b"no objects for this map", "text/plain")
                return await self._http(writer, 200, json.dumps(objs, separators=(",", ":")).encode(), "application/json; charset=utf-8", cache="max-age=3600")
            objs = []
            for o in self.walk.objects(m.group(1)):
                png = "%s_%dx%d.png" % (o["n"], o["w"], o["h"])
                if os.path.isfile(os.path.join(OBJ_DIR, png)) or await self._have_object(o):
                    objs.append(dict(o, u="/obj/" + png))
            if not objs:
                return await self._http(writer, 404, b"no objects for this map", "text/plain")
            return await self._http(writer, 200, json.dumps(objs, separators=(",", ":")).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/bigobj/(\d{1,6})\.png", path)
        if m and self.big is not None:      # 大地图物件精灵（遮挡用的透明 PNG）
            data = await asyncio.get_running_loop().run_in_executor(None, self.big.sprite_png, m.group(1))
            if data is None:
                return await self._http(writer, 404, b"no such sprite", "text/plain")
            return await self._http(writer, 200, data, "image/png", cache="max-age=3600")
        m = re.fullmatch(r"/obj/(\d{5,9})_(\d{1,4})x(\d{1,4})\.png", path)
        if m:
            full = os.path.join(OBJ_DIR, path[len("/obj/"):])
            if not os.path.isfile(full):
                full = await self._make_object(m.group(1), int(m.group(2)), int(m.group(3)))
            if not full:
                return await self._http(writer, 404, b"no such object image", "text/plain")
            return await self._http(writer, 200, open(full, "rb").read(), "image/png", cache="max-age=3600")
        if path == "/duty.json":      # 任务手册：[{name, entries:[{kind,title,level,desc}]}]
            if not self.duty:
                return await self._http(writer, 404, b"no duty data", "text/plain")
            return await self._http(writer, 200, json.dumps(self.duty, separators=(",", ":"), ensure_ascii=False).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        if path == "/guide.json":      # 导航目录：{kinds:{号:名}, npcs:[{id,group,kind,name,map,x,y}], tutorial:[{title,text}]}；x y 是像素
            if not self.guide["npcs"]:
                return await self._http(writer, 404, b"no guide data", "text/plain")
            return await self._http(writer, 200, json.dumps(self.guide, separators=(",", ":"), ensure_ascii=False).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/npcs/(\d{1,8})\.json", path)
        if m:      # 这张图的 NPC / 怪物摆放：[{id,name,x,y,dir,model,kind,ev}]；x y 是像素（所在 20 像素格的中心），ev = 事件数
            cs = self.cell_of(m.group(1))
            lst = [{"id": n["id"], "name": n["name"], "x": n["x"] * cs + cs // 2, "y": n["y"] * cs + cs // 2, "dir": n["dir"], "model": n["model"],
                    "kind": "mob" if n["model"] >= 50000 else "npc", "ev": len(n["events"]), "spr": self.nspr.of(n["model"])} for n in self.npc.get(m.group(1))]
            if not lst:
                return await self._http(writer, 404, b"no npcs for this map", "text/plain")
            return await self._http(writer, 200, json.dumps(lst, separators=(",", ":"), ensure_ascii=False).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/bigmap/(\d{1,8})/(info\.json|mini\.png|(\d{1,3})_(\d{1,3})\.jpg)", path)
        if m and self.big is not None and self.big.has(m.group(1)):      # 大地图：info.json（尺寸）/ 切片 <tx>_<ty>.jpg（768 像素一块）/ mini.png（小地图）
            mid, what = m.group(1), m.group(2)
            loop = asyncio.get_running_loop()
            if what == "info.json":
                w, h = self.big.size(mid)
                return await self._http(writer, 200, json.dumps({"w": w, "h": h, "cell": bigmap.CELL, "tile": self.big.TILE}).encode(), "application/json; charset=utf-8", cache="max-age=3600")
            if what == "mini.png":
                data = await loop.run_in_executor(None, self.big.overview_png, mid)
                return await self._http(writer, 200, data, "image/png", cache="max-age=3600")
            data = await loop.run_in_executor(None, self.big.tile_jpeg, mid, int(m.group(3)), int(m.group(4)))
            if data is None:
                return await self._http(writer, 404, b"no tile", "text/plain")
            return await self._http(writer, 200, data, "image/jpeg", cache="max-age=3600")
        m = re.fullmatch(r"/room/(\d{1,8})\.json", path)
        if m:      # 缺背景图的地图：占位房间的尺寸 {w,h,cell}（页面自己画地板），见 Gateway.room_of
            room = self.room_of(m.group(1))
            if room is None:
                return await self._http(writer, 404, b"no room for this map", "text/plain")
            return await self._http(writer, 200, json.dumps(room).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/zones/(\d{1,8})\.json", path)
        if m:      # 这张图的门 / 出入口（走进矩形触发事件，多半是传送）：[{id,x,y,w,h}]，像素，x y 是左上角
            cs = self.cell_of(m.group(1))
            lst = [{"id": z["id"], "x": z["x"] * cs, "y": z["y"] * cs, "w": z["w"], "h": z["h"]} for z in self.npc.zones(m.group(1)) if z["kind"] == "door" and z["events"]]
            if not lst:
                return await self._http(writer, 404, b"no doors for this map", "text/plain")
            return await self._http(writer, 200, json.dumps(lst, separators=(",", ":")).encode(), "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/walk/(\d{1,8})\.json", path)
        if m:      # 地图碰撞格：{w,h,rows,cols,cell,stride,data(base64)}，页面据此寻路、画碰撞层
            g = self.walk.get(m.group(1))
            if g is None:
                return await self._http(writer, 404, b"no walk grid for this map", "text/plain")
            body = json.dumps(dict(g, data=base64.b64encode(g["data"]).decode()), separators=(",", ":")).encode()
            return await self._http(writer, 200, body, "application/json; charset=utf-8", cache="max-age=3600")
        m = re.fullmatch(r"/sprites/fx/([0-9A-Za-z]{1,12})\.png|/sprites/fx/(index)\.json", path)
        if m:      # 武功动画图（build_fx.py 预生成）和技能 -> 帧表索引
            fn = (m.group(1) + ".png") if m.group(1) else "index.json"
            fp = os.path.join(WEB_DIR, "sprites", "fx", fn)
            if not os.path.isfile(fp):
                return await self._http(writer, 404, b"no fx", "text/plain")
            return await self._http(writer, 200, open(fp, "rb").read(), "image/png" if fn.endswith(".png") else MIME[".json"], cache="max-age=3600")
        if path == "/sprites/fight_cells.png":     # 原版战斗格子高亮图（FightN.mrg：6 色 × 6 状态，每格 96×33）
            fp = os.path.join(WEB_DIR, "sprites", "fight_cells.png")
            if not os.path.isfile(fp):
                return await self._http(writer, 404, b"no fight cell sprite", "text/plain")
            return await self._http(writer, 200, open(fp, "rb").read(), "image/png", cache="max-age=3600")
        m = re.fullmatch(r"/sprites/npc/(\d{1,6})(?:_(\d{1,2})\.png|\.json)", path)
        if m:      # NPC / 怪物精灵（站立 S / 攻击 A 的图集）：web\sprites\npc\；缺的现生成
            sid = int(m.group(1))
            jp = self.nspr.ensure(sid)
            if not jp:
                return await self._http(writer, 404, b"no such npc sprite", "text/plain")
            full = jp if m.group(2) is None else os.path.join(self.nspr.dir, "%d_%s.png" % (sid, m.group(2)))
            if not os.path.isfile(full):
                return await self._http(writer, 404, b"no such npc sprite page", "text/plain")
            return await self._http(writer, 200, open(full, "rb").read(), "image/png" if full.endswith(".png") else MIME[".json"], cache="max-age=3600")
        m = re.fullmatch(r"/sprites/(\d{1,3})/([A-Z0-9]{3,8})_([0-5])\.(png|json)", path)
        if m:      # 人物精灵层：缓存在 web\sprites\<模型>\；没有就由 build_sprites.py 从 role\*.mrg 现生成（需要 Pillow 和客户端资源）
            base = os.path.join(WEB_DIR, "sprites", m.group(1), "%s_%s" % (m.group(2), m.group(3)))
            res = (base + ".png", base + ".json") if os.path.isfile(base + ".json") and os.path.isfile(base + ".png") else None
            if res is None:
                try:
                    import build_sprites
                    res = await asyncio.get_running_loop().run_in_executor(None, build_sprites.ensure_layer, int(m.group(1)), m.group(2), int(m.group(3)))
                except BaseException:       # 没装 Pillow 时 wjres 会 sys.exit
                    res = None
            if not res:
                return await self._http(writer, 404, b"no such sprite layer", "text/plain")
            full = res[0] if m.group(4) == "png" else res[1]
            return await self._http(writer, 200, open(full, "rb").read(), MIME["." + m.group(4)], cache="max-age=600")
        name = "index.html" if path in ("/", "") else path.lstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or ".." in name:
            return await self._http(writer, 404, b"not found", "text/plain")
        full = os.path.join(WEB_DIR, name)
        ext = os.path.splitext(name)[1].lower()
        if ext not in MIME or not os.path.isfile(full):
            return await self._http(writer, 404, b"not found", "text/plain")
        await self._http(writer, 200, open(full, "rb").read(), MIME[ext])

    async def serve_ws(self, reader, writer, hdr):
        # 防跨站 WebSocket 劫持：浏览器带 Origin 时，主机部分必须等于 Host
        origin = hdr.get("origin")
        if origin and re.sub(r"^https?://", "", origin).rstrip("/") != hdr.get("host", ""):
            return await self._http(writer, 403, b"bad origin", "text/plain")
        key = hdr.get("sec-websocket-key")
        if not key or hdr.get("sec-websocket-version") != "13":
            return await self._http(writer, 400, b"bad request", "text/plain")
        if self.sessions >= MAX_SESSIONS:
            return await self._http(writer, 503, b"too many sessions", "text/plain")
        accept = base64.b64encode(hashlib.sha1(key.encode() + WS_GUID).digest()).decode()
        writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        await writer.drain()
        ws = WS(reader, writer)
        s = Session(self, ws)
        self.sessions += 1
        pump = asyncio.create_task(s.pump())
        try:
            await ws.send_json({"ev": "hello", "server": "%s:%d" % (self.up_host, self.up_port), "merchants": self.items.merchants,
                                  "look_fallback": self.look_fallback})
            while True:
                text = await ws.recv()
                if text is None:
                    break
                try:
                    msg = json.loads(text)
                    if not isinstance(msg, dict):
                        raise ValueError
                except ValueError:
                    s.emit({"ev": "error", "msg": "消息不是 JSON 对象"})
                    continue
                try:
                    await s.handle(msg)
                except Exception as e:  # 一个坏请求不能拖垮连接
                    s.emit({"ev": "error", "msg": "内部错误: %r" % e})
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self.sessions -= 1
            await s.logout()
            s.out.put_nowait(None)
            await pump
            await ws.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", default="127.0.0.1:8088")
    ap.add_argument("--server", default="127.0.0.1:6732", help="游戏服务端 host:port")
    ap.add_argument("--items", default=DEFAULT_ITEM_DIR, help="装备数据.csv / 药品.csv 所在目录（用来显示物品名）")
    ap.add_argument("--look-fallback", action="store_true",
                    help="外观兜底（默认关闭，**不是原版行为**）：Item3.Dat 里没有的武器，按装备数据.csv 的 itemtype2 画 WA..WE 层。"
                         "原版客户端对表里没有的装备什么也不画；服务端自己的武器编号（11xxx–15xxx）都不在表里")
    ap.add_argument("--pic", default=DEFAULT_PIC_DIR, help="客户端 share/pic 目录（地图背景 SceneBG*.mrg；外观表读它旁边的 share/dat/Item3.Dat）")
    a = ap.parse_args()
    lh, lp = a.listen.rsplit(":", 1)
    uh, up = a.server.rsplit(":", 1)
    if lh not in ("127.0.0.1", "localhost", "::1"):
        print("警告：网关监听在 %s，游戏协议没有密码，任何能访问的人都能以任意账号登录。" % lh, file=sys.stderr)
    gw = Gateway(uh, int(up), Items(a.items), MapIndex(a.pic), Looks(os.path.join(a.pic, "..", "dat", "Item3.Dat")), look_fallback=a.look_fallback,
                 walk=WalkIndex(os.path.join(a.pic, "..", "dat")), pic_dir=a.pic, npc=NpcIndex(a.pic), events=EventIndex(a.pic), texts=TextStore(a.pic))

    async def run():
        await asyncio.get_running_loop().run_in_executor(None, gw.speakers)      # 说话者表要扫全部地图的 NPC（约 3 秒），启动时先算好，免得第一次对话卡住
        srv = await asyncio.start_server(gw.on_conn, lh, int(lp))
        print("网关 http://%s:%s/  ->  游戏服务端 %s:%s  （物品名 %d 条，地图背景 %d 张，外观码 %d 条）" % (lh, lp, uh, up, len(gw.items.names), len(gw.maps.index), len(gw.looks.table)), flush=True)
        print("  物品表 %s | 地图 %s | 外观表 %s | 精灵缓存 %s" % (a.items, a.pic, os.path.normpath(os.path.join(a.pic, "..", "dat", "Item3.Dat")), os.path.join(WEB_DIR, "sprites")), flush=True)
        print("  碰撞格 %d 张地图（dat\\WSG*.dat）| NPC 摆放 %d 张地图（pic\\NpcMrg*.Mrg）| 事件脚本 %d 张 + 对话文本 %d 条" % (len(gw.walk.index), len(gw.npc.index), len(gw.events.index), len(gw.texts)), flush=True)
        if not gw.items.names or not gw.maps.index or not gw.looks.table or not gw.walk.index or not gw.npc.index or not gw.events.index or not len(gw.texts):
            print("  警告：有资源没读到（物品名 / 地图 / 外观码 / 碰撞格 / NPC 为 0），请检查上面的路径", flush=True)
        async with srv:
            await srv.serve_forever()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
