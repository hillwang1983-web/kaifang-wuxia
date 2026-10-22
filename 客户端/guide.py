#!/usr/bin/env python3
"""游戏自带的『导航 / 新手教学』数据：share\\dat\\cityportals.dat、cityportals_kind.dat、newbie.dat。

cityportals.dat（2026-10-21 解出，用 NPC 摆放表 NpcMrg 里的同名 NPC 交叉验证过：像素坐标 = 格子坐标 × 20）：
    头 4 字节：u16 1 | u16 条数（823）；之后每条 31 字节：
        id u16 | 分组 u8（1–4 = 新手区 / 城镇一类，10 / 11 / 12 / … = 门派号，和 师傅.csv 的「门派」同一套）| 类型 u8（见 cityportals_kind）|
        名字 21 字节 Big5（00 补满）| 地图 u16 | x u16 | y u16（像素）
cityportals_kind.dat：头 4 字节（u16 1 | u16 8），每条 22 字节：序号 u8 | 名字 21 字节 Big5。
    1 傳送類型 2 功能類型 3 消點類型 4 任務類型 5 活動類型 6 技能類型 7 買賣類型 8 其他類型
    它是客户端的"去哪找 NPC"目录：有任务的 NPC（4）、教武功消点的师傅（3）、卖东西的（7）……各在哪张图的什么位置。
    原版服务端对传送（C2S 0x5D）不校验，所以点目录里的条目就能直接过去。
newbie.dat：Big5 文本，按行 `#标题` 分节（操作说明 / 買賣教學 / 武器防具合成… / 生活技能教學 …）。
"""
import os
import struct

_HERE = os.path.dirname(os.path.abspath(__file__))
DAT_DIR = os.environ.get("JY_DAT") or (os.path.join(_HERE, "share", "dat") if os.path.isdir(os.path.join(_HERE, "share", "dat")) else os.path.normpath(os.path.join(_HERE, "..", "share", "dat")))

KIND_NAMES_FALLBACK = {1: "傳送類型", 2: "功能類型", 3: "消點類型", 4: "任務類型", 5: "活動類型", 6: "技能類型", 7: "買賣類型", 8: "其他類型"}


def _big5(b: bytes) -> str:
    return b.split(b"\0")[0].decode("big5", "replace")


def load_kinds(path=None):
    """{类型号: 名字}；读不到用写死的 8 类"""
    try:
        d = open(path or os.path.join(DAT_DIR, "cityportals_kind.dat"), "rb").read()
        n = struct.unpack_from("<HH", d, 0)[1]
        return {d[4 + 22 * i]: _big5(d[5 + 22 * i:4 + 22 * (i + 1)]) for i in range(n) if len(d) >= 4 + 22 * (i + 1)}
    except (OSError, struct.error):
        return dict(KIND_NAMES_FALLBACK)


def load_npcs(path=None):
    """[{id, group, kind, name, map, x, y}]；x y 是像素。读不到返回 []"""
    try:
        d = open(path or os.path.join(DAT_DIR, "cityportals.dat"), "rb").read()
    except OSError:
        return []
    if len(d) < 4:
        return []
    n = struct.unpack_from("<HH", d, 0)[1]
    out = []
    for i in range(n):
        o = 4 + 31 * i
        if o + 31 > len(d):
            break
        r = d[o:o + 31]
        out.append({"id": struct.unpack_from("<H", r, 0)[0], "group": r[2], "kind": r[3], "name": _big5(r[4:25]),
                    "map": struct.unpack_from("<H", r, 25)[0], "x": struct.unpack_from("<H", r, 27)[0], "y": struct.unpack_from("<H", r, 29)[0]})
    return out


def load_tutorial(path=None):
    """[{title, text}]：newbie.dat 按『#标题』分节（行内的硬换行合并成段落）"""
    try:
        t = open(path or os.path.join(DAT_DIR, "newbie.dat"), "rb").read().decode("big5", "replace")
    except OSError:
        return []
    out = []
    for part in t.split("#")[1:]:
        lines = part.replace("\r", "").split("\n")
        title = lines[0].strip()
        body = "\n".join(l for l in lines[1:]).strip("\n")
        if title and body.strip():
            out.append({"title": title, "text": body})
    return out


MAP_CSV = os.environ.get("JY_MAPCSV") or next((p for p in (os.path.join(_HERE, "data", "MAP.csv"), os.path.join(_HERE, "..", "maina", "MAP.csv")) if os.path.isfile(p)), "")


def load_places(path=None):
    """maina\\MAP.csv（客户端自带的地点表，GBK 简体）：`地图,x,y,名字` 一行一个地点，`1类别名` 开头的行是分组标题。
    -> [{cat, name, map, x, y}]；x y 是像素（城市图 = 格 × 20）。含 新手任务 / 常用地点 / 各大门派 / 京城城区 / 扬州城区 / 初阶技能师 …"""
    p = path or MAP_CSV
    out, cat = [], ""
    try:
        lines = open(p, "rb").read().decode("gbk", "replace").splitlines()
    except OSError:
        return []
    for ln in lines:
        c = ln.split(",")
        if len(c) >= 4 and c[0].isdigit() and c[1].isdigit() and c[2].isdigit() and c[3].strip():
            out.append({"cat": cat, "name": c[3].strip(), "map": int(c[0]), "x": int(c[1]), "y": int(c[2])})
        elif c and c[0].strip() and not c[0].strip().isdigit():
            cat = c[0].strip().lstrip("1") if c[0].startswith("1") and len(c[0]) > 1 and not c[0][1].isdigit() else c[0].strip()
    return out


def load(s2t=None, has_map=None):
    """网关 /guide.json 的内容：{kinds: {号: 名}, npcs: […], tutorial: […]}；s2t(str) 可选，把繁体转简体"""
    f = s2t or (lambda s: s)
    kinds = load_kinds()
    npcs = [dict(n, name=f(n["name"])) for n in load_npcs()]
    # MAP.csv 的地点（kind 9）：只留网页版画得出来的图（has_map(地图号) 为真）；名字已经是简体
    seen, places = set(), []
    for p in load_places():
        k = (p["name"], p["map"], p["x"], p["y"])
        if k in seen or (has_map is not None and not has_map(p["map"])):
            continue
        seen.add(k)
        places.append({"id": 10000 + len(places), "group": 0, "kind": 9, "name": p["name"], "cat": p["cat"], "map": p["map"], "x": p["x"], "y": p["y"]})
    return {"kinds": {str(k): f(v) for k, v in kinds.items()},
            "npcs": npcs + places,
            "tutorial": [{"title": f(t["title"]), "text": f(t["text"])} for t in load_tutorial()]}
