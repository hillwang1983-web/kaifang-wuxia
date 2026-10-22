"""武功：C2S 0x61 装备武功、0x6A 删除武功；存档时 kf 表的取舍。

行为依据 2026-10 对原版的实测（tools/kf_compare.py、kf_matrix.py），详见 docs/武功装备与删除.md。
原版里「拥有的武功」是内存里的一个列表（登录时从 kf 表读），等级 / 经验两个并行数组；删除只是把等级、经验写成 0，
武功还留在列表里，所以删完还能再「删」（照样回包）、也还能「装备」；下线存档时等级为 0 的行不写，下次登录才真没了。
装备本身服务端不做类型 / 门派 / 槽位种类检查（槽位 0–14 都收，客户端自己管），也没有任何别处看得到的状态——只回显。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from .state import to_big5

Frame = tuple[int, bytes, bool]

REBIRTH_KF = 3860  # 转生武功：不能删
MAX_SLOT = 0x0E  # 装备槽位 0..14
_TRIED = bytes.fromhex("b9 c1 b8 d5 a8 ea aa 5a a5 5c a1 54")  # 嘗試刷武功﹗
_NO_DELETE = b"\x64" + bytes.fromhex("c2 e0 a5 cd aa 5a a5 5c b5 4c aa 6b a7 52 b0 a3 a1 54")  # 轉生武功無法刪除﹗
_BAD_PASSWORD = b"\x64" + bytes.fromhex("b1 4b bd 58 bf f9 bb 7e")  # 密碼錯誤


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_all: list[Frame] = field(default_factory=list)
    inline: list[tuple[int, Frame]] = field(default_factory=list)  # (插在 to_self 第几帧之前, 全服帧)：读书时「刷武功」公告在书被扣的帧之前


@dataclass
class Req:
    """防挂验证.csv 的一行：学这门武功的条件（全是「不低于」，0 = 不查）。"""

    skills: list[tuple[int, int]]  # (前置武功 ID, 等级)，ID 为 0 的不查
    stats: dict[str, int]  # 人物表列名 -> 要求（臂力 str、胆识 crg、悟性 wint、福源 luk、定力 dex、机敏 agi、根骨 vit、名声 fame_val、历练 exp_val）
    combat: int  # 实战
    hours: int  # 上线时间（小时；online_time / 48 要不低于它）
    school: int  # 门派编号，0 = 不查（必须恰好等于）


# 防挂验证.csv 第 8–16 列对应的人物表列（原版按偏移 +0xc0 +0xd8 +0xdc +0xe0 +0xe4 +0xe8 +0xec +0xf0 +0xfc 比较）
REQ_STAT_COLS = ("str", "crg", "wint", "luk", "dex", "agi", "vit", "fame_val", "exp_val")
ONLINE_UNITS_PER_HOUR = 48


@dataclass
class Master:
    """师傅.csv 的一行：一位师傅教的一门武功（消点用，见 jyserver/study.py）。"""

    rank: int  # 「级数」：消点能升到的最高等级
    school: int  # 「门派」，0 = 谁都能学
    kind: int
    map: int  # 「地图」：玩家要在这张图上


class Kungfu:
    """武学系数.csv：武功 ID → 简体名称（第 5 列「GBK」）；防挂验证.csv：武功 ID → 学习条件；师傅.csv：(师傅, 武功) → 级数 / 门派 / 地图。"""

    def __init__(self, names: dict[int, str] | None = None, reqs: dict[int, Req] | None = None, attack: dict[int, int] | None = None,
                 coef: dict[int, float] | None = None, masters: dict[tuple[int, int], Master] | None = None) -> None:
        self.names = names or {}
        self.reqs = reqs or {}
        self.attack = attack or {}  # 武功 ID -> 「攻」列（战斗伤害用）
        self.coef = coef or {}  # 武功 ID -> 升级系数（武学系数.csv 第 11 列）：升级要 系数 × (等级+1)^3 点经验
        self.masters = masters or {}

    @classmethod
    def load(cls, data_dir: str | Path) -> "Kungfu":
        names: dict[int, str] = {}
        reqs: dict[int, Req] = {}
        attack: dict[int, int] = {}
        coef: dict[int, float] = {}
        masters: dict[tuple[int, int], Master] = {}
        p = Path(data_dir) / "武学系数.csv"
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) > 4 and row[0].strip().isdigit():
                    names[int(row[0])] = row[4]
                    attack[int(row[0])] = _i(row[11]) if len(row) > 11 else 0
                    coef[int(row[0])] = _float(row[10]) if len(row) > 10 else 1.0
        p = Path(data_dir) / "防挂验证.csv"
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) < 19 or not row[0].strip().isdigit():
                    continue
                kid = int(row[0])
                if kid in reqs:  # 重复行取第一条（原版线性扫描）
                    continue
                reqs[kid] = Req(
                    skills=[(_i(row[a]), _i(row[a + 1])) for a in (1, 3, 5)],
                    stats={col: _i(row[7 + k]) for k, col in enumerate(REQ_STAT_COLS)},
                    combat=_i(row[16]),
                    hours=_i(row[17]),
                    school=_i(row[18]),
                )
        p = Path(data_dir) / "师傅.csv"
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) > 8 and row[0].strip().isdigit() and row[3].strip().isdigit():
                    masters.setdefault((int(row[0]), int(row[3])), Master(_i(row[5]), _i(row[6]), _i(row[7]), _i(row[8])))  # 重复行取第一条（原版线性扫描）
        return cls(names, reqs, attack, coef, masters)

def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def _owned(rows: dict, kid: int) -> dict | None:
    return next((r for r in rows.get("kf") or [] if _i(r.get("kf_id")) == kid), None)


def equip(rows: dict, table: Kungfu, payload: bytes) -> Result:
    """C2S 0x61：载荷 = 槽位(1) + 武功 ID(LE16)，至少 3 字节（后面的不看）。
    自己没有这门武功（kf 列表里没有；等级 0 的删除残留算有）→ **全服**收 0x14（长帧）= 0e + <名字> + 「嘗試刷武功﹗」 + 武功名（表里有才带，
    不管槽位对不对）；有，且槽位 0–14 → 自己收 0x6E = 槽位 + 武功 ID（回显）；槽位 > 14 → 静默。"""
    res = Result()
    if len(payload) < 3:
        return res
    slot, kid = payload[0], int.from_bytes(payload[1:3], "little")
    if kid == 0:  # 表里查不到 ID 0：回显，不管槽位、也不查拥有
        res.to_self.append((0x6E, payload[:3], False))
    elif _owned(rows, kid) is None:
        name = to_big5(table.names[kid]) if kid in table.names else b""
        res.to_all.append((0x14, b"\x0e" + to_big5(rows["renwu"][0].get("name", "") or "") + _TRIED + name, True))
    elif slot <= MAX_SLOT:
        res.to_self.append((0x6E, payload[:3], False))
    return res


def delete(rows: dict, password: str, payload: bytes) -> Result:
    """C2S 0x6A：载荷 = 1 字节（不看）+ 密码长度 N(1) + 密码 N 字节 + 1 字节（不看）+ K×武功 ID(LE16)，至少 4 字节。
    原版数「字节数」：m = 载荷长 − N − 2，条目数 K = CInt((m − 1) / 2)（四舍六入五成双）；K ≤ 0 → 整条指令静默。条目 i（1 起）占密码后第 2+2(i−1) 起的
    2 字节；条目的字节超出载荷（m 是 4 的倍数时最后一条会）不报错，只是那个 ID 谁也匹配不上。解析中遇到 3860（转生武功）→ 0x1A「轉生武功無法刪除﹗」并结束
    （**先于**密码检查，已解析的条目也不删）。然后核对账号密码：不对 → 0x1A「密碼錯誤」。最后按顺序处理条目：在 kf 列表里找第一个相同的 ID，
    找到就把等级、经验写成 0，自己收 0x7A = `02` + ID(LE16)；没有就跳过。已经删过（等级 0）的再删照样回包。"""
    res = Result()
    if len(payload) < 4:
        return res
    n = payload[1]
    m = len(payload) - n - 2  # 原版的「token 数 − N − 6」
    k = round((m - 1) / 2)  # VB 的 CInt：五成双
    if k <= 0:
        return res
    ids: list[int] = []
    for i in range(1, k + 1):
        at = n + 3 + 2 * (i - 1)  # 条目在载荷里的起点
        if at + 1 >= len(payload):
            continue
        kid = int.from_bytes(payload[at : at + 2], "little")
        if kid == REBIRTH_KF:
            res.to_self.append((0x1A, _NO_DELETE, False))
            return res
        ids.append(kid)
    if payload[2 : 2 + n].decode("latin1") != password:
        res.to_self.append((0x1A, _BAD_PASSWORD, False))
        return res
    for kid in ids:
        row = _owned(rows, kid)
        if row is not None:
            row["kf_lvl"] = "0"
            row["kf_exp"] = "0"
            res.to_self.append((0x7A, b"\x02" + kid.to_bytes(2, "little"), False))
    return res

def persistable(rows: dict) -> dict:
    """下线 / 存档时写进库的行：kf 表里等级为 0 的行不写（原版实测），别的原样。内存里的不动。"""
    if not any(_i(r.get("kf_lvl")) == 0 for r in rows.get("kf") or []):
        return rows
    out = dict(rows)
    out["kf"] = [r for r in rows["kf"] if _i(r.get("kf_lvl")) != 0]
    return out


# ---- 事件语句 武功:ID:等级（events.py 调用）
_NOTICE_PREFIX = bytes.fromhex("aa b1 ae 61 a1 52")  # 玩家﹕
_NOTICE_MID = bytes.fromhex("a5 bf a6 62 a8 ea aa 5a a5 5c a8 c6 a5 f3 a1 52")  # 正在刷武功事件﹕
_NOTICE_SUFFIX = bytes.fromhex("b8 d3 a6 e6 ac b0 a4 77 b8 67 b0 4f bf fd a1 54")  # 該行為已經記錄﹗
_ALREADY = b"\x64" + bytes.fromhex("a4 77 b8 67 a6 b3 a6 b9 aa 5a a5 5c a4 46 a1 54")  # 已經有此武功了﹗


def level_of(rows: dict, kid: int) -> int:
    """玩家在 kid 这门武功上的等级；没有 = 0。"""
    row = _owned(rows, kid)
    return _i(row.get("kf_lvl")) if row is not None else 0


def meets(rows: dict, req: Req | None) -> bool:
    """学习条件（原版 0x6a64bf）：没有这一行 = 随便学；有就逐项「不低于」，门派要相等。"""
    if req is None:
        return True
    renwu = rows["renwu"][0]
    for kid, lvl in req.skills:
        if kid != 0 and level_of(rows, kid) < lvl:
            return False
    for col, need in req.stats.items():
        if need != 0 and _i(renwu.get(col)) < need:
            return False
    if req.combat != 0 and _i(renwu.get("combat_exp")) < req.combat:
        return False
    if req.hours != 0 and _i(renwu.get("online_time")) / ONLINE_UNITS_PER_HOUR < req.hours:
        return False
    if req.school != 0 and _i(renwu.get("school")) != req.school:
        return False
    return True


def learn(rows: dict, table: Kungfu, kid: int, level: int) -> Result:
    """事件语句 武功:ID:等级（等级 ≥ 1）。条件不满足 → **全服**收 0x14（长帧）03 = 「玩家﹕<名字>正在刷武功事件﹕<武功名>該行為已經記錄﹗」（原版还写日志）；
    满足且还没有这门武功 → 追加一行（等级 = 语句里的等级，经验 0），自己收 0x68 = ID(LE16) 等级(LE16) 00000000 学点(LE16) 当前精(LE16)；
    已经有（含删除残留的等级 0）→ 自己收 0x1A「已經有此武功了﹗」，等级不变。"""
    res = Result()
    renwu = rows["renwu"][0]
    if not meets(rows, table.reqs.get(kid)):
        name = to_big5(table.names[kid]) if kid in table.names else b""
        res.to_all.append((0x14, b"\x03" + _NOTICE_PREFIX + to_big5(renwu.get("name", "") or "") + _NOTICE_MID + name + _NOTICE_SUFFIX, True))
        return res
    if _owned(rows, kid) is not None:
        res.to_self.append((0x1A, _ALREADY, False))
        return res
    rows.setdefault("kf", []).append({"jyid": str(renwu.get("jyid")), "kf_id": str(kid), "kf_lvl": str(level), "kf_exp": "0"})
    body = (kid & 0xFFFF).to_bytes(2, "little") + (level & 0xFFFF).to_bytes(2, "little") + bytes(4)
    body += (_i(renwu.get("study_count")) & 0xFFFF).to_bytes(2, "little") + (_i(renwu.get("dangqianjing")) & 0xFFFF).to_bytes(2, "little")
    res.to_self.append((0x68, body, False))
    return res


def forget(rows: dict, kid: int) -> Result:
    """事件语句 武功:ID:负数：列表里有就把等级、经验写成 0，自己收 0x7A = `02` + ID(LE16)；没有就什么都不发。"""
    res = Result()
    row = _owned(rows, kid)
    if row is not None:
        row["kf_lvl"] = "0"
        row["kf_exp"] = "0"
        res.to_self.append((0x7A, b"\x02" + (kid & 0xFFFF).to_bytes(2, "little"), False))
    return res


# ---- C2S 0x60 读秘笈（2026-10-20，tools/kf_compare.py book-* 与原版逐帧、逐库对照）
BOOKS = {35022: (2203, False), 35031: (3004, True), 40177: (4023, True)}  # 物品 -> (学到的武功, 是否要求已自宫)
BOOK_ATTRS = ("str", "crg", "wint", "luk", "dex", "agi", "vit")
BOOK_MIN = 50
_NO_ITEM = b"\x64" + bytes.fromhex("aa ab ab 7e a4 a3 a8 ac")  # 物品不足
_NEED_ATTRS = b"\x64" + bytes.fromhex("bb dd ad 6e a5 fe c4 dd a9 ca") + b"50"  # 需要全屬性50
_NEED_ZIGONG = bytes.fromhex("bb dd ad 6e a6 db ae 63 a1 54")  # 需要自宮﹗


def read_book(rows: dict, table: Kungfu, items, payload: bytes) -> Result:
    """C2S 0x60：载荷 = 物品 ID(LE32，前 4 字节) + 耐久(1，不看)，至少 5 字节（更短静默）。
    背包里没有这件物品（不管是不是秘笈）→ 0x1A「物品不足」+ 0x05 自己下线帧；有，但不是三本秘笈之一 → 静默。
    三本：35022 乾坤大挪移 → 2203，35031 葵花宝典 → 3004，40177 太玄经 → 4023。七项属性都要 ≥ 50（葵花、太玄另要已自宫），
    不够 → 0x1A「需要全屬性50」/「需要全屬性50,需要自宮﹗」，书不扣。够了就走**事件语句 武功:ID:1 的同一套学武功流程**（防挂验证 / 已经有 / 学到），
    不管结果如何**书都扣一本**，随后自己收 0x0B 和 0x6B（物品 ID + 耐久 + 01）；防挂验证不过时「刷武功」公告（全服）在这两帧之前。"""
    res = Result()
    if len(payload) < 5:
        return res
    iid = int.from_bytes(payload[:4], "little")
    renwu = rows["renwu"][0]
    row = next((r for r in rows.get("item") or [] if _i(r.get("item_id")) == iid and _i(r.get("shuliang")) > 0), None)
    if row is None:
        res.to_self.append((0x1A, _NO_ITEM, False))
        res.to_self.append((0x05, _i(renwu.get("jyid")).to_bytes(4, "little") + b"\x01", False))
        return res
    if iid not in BOOKS:
        return res
    kid, need_zigong = BOOKS[iid]
    lacks_attrs = any(_i(renwu.get(a)) < BOOK_MIN for a in BOOK_ATTRS)
    lacks_zigong = need_zigong and _i(renwu.get("zigong")) != 1
    if lacks_attrs or lacks_zigong:
        res.to_self.append((0x1A, _NEED_ATTRS + (b"," + _NEED_ZIGONG if need_zigong else b""), False))
        return res
    learned = learn(rows, table, kid, 1)
    res.to_self += learned.to_self
    res.inline += [(len(res.to_self) - len(learned.to_self), fr) for fr in learned.to_all]  # 公告插在最前
    left = _i(row["shuliang"]) - 1
    if left > 0:
        row["shuliang"] = str(left)
    else:
        rows["item"].remove(row)
    entry = iid.to_bytes(4, "little") + bytes([items.of(iid), 0x01])
    res.to_self.append((0x0B, entry, False))
    res.to_self.append((0x6B, entry, True))
    return res
