"""C2S 0xC7 文本指令（客户端把聊天框里 `@xxx` 发上来）：原版 `0x6cab50`，整个函数 4.6 万字节、二十多条指令。

载荷 = `04 40` + ASCII 文本（`04` 是聊天子类型，`40` 是 `@`）。行为依据 2026-10 对原版的逐条实测（tools/cmd_probe.py），
见 docs/文字指令.md。这里只做实测清楚的那些，其余见文档里的「没做」表。

纯函数：入参是角色的数据库行（原地修改），返回要发的帧；网络层在 server.py（传送、踢线也由它做）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .events import Tables, _entry, _marker_rows, _marker_type, _bag_add
from .state import ItemTable, to_big5

Frame = tuple[int, bytes, bool]

POINT_PRICE = 100_000  # @scb：1 点商城点数 = 10 万金钱
SCB_MAX = 1000
MP_COST = 9999
VIP_LEVEL = 7  # 原版 VIP 等级对所有人恒为 7（「暂停VIP功能」），回收里那个神秘的 `玩家+0x484 > 4` 条件就是它
KALE_TARGET = (2822, 210, 450)

# @mp 数字 -> (门派 school, 师承 master)；数字 1–9，其余忽略。master 是门派对应的一件物品 ID（0 = 无）。
MP_TABLE = {
    "1": (10, 0), "2": (11, 11005), "3": (12, 12013), "4": (13, 0), "5": (15, 15001),
    "6": (19, 19064), "7": (21, 21001), "8": (22, 22001), "9": (23, 23002),
}
# @bpsm：背叛师门时补发的「师门标记」。门派 -> 标记 ID
SCHOOL_MARKER = {10: 50046, 11: 50044, 12: 50045, 13: 33721, 15: 50049, 19: 50050, 21: 50300, 22: 33558, 23: 50047}

_COLON = b"\xa1\x52"  # 原版文字里的「﹕」
_MSG_NO_ITEM = b"\x64" + bytes.fromhex("b5 4c a6 b9 aa ab ab 7e")  # 無此物品
_MSG_NEED_POINTS = b"\x64" + bytes.fromhex("bb dd ad 6e b0 d3 ab b0 c2 49 bc c6 39 39 39 39 a4 7e af e0 a6 db a5 d1 bf ef be dc aa f9 ac a3")  # 需要商城點數9999才能自由選擇門派
_MSG_SCB_MAX = b"\x64" + bytes.fromhex("b3 e6 a6 b8 a7 49 b4 ab a4 a3 b1 6f b6 57 b9 4c") + b"1000"  # 單次兌換不得超過1000
_MSG_NEGATIVE = b"\x64" + bytes.fromhex("a4 a3 af e0 ac b0 ad 74 bc c6")  # 不能為負數
_MSG_NO_MONEY = b"\x64" + bytes.fromhex("aa f7 bf fa a4 a3 a8 ac a1 54")  # 金錢不足﹗
_MSG_HAS_MARKER = b"\x64" + bytes.fromhex("a4 77 b8 67 a6 b3 a6 b9 bc d0 b0 4f")  # 已經有此標記
REBIRTH_KF = 3860  # 转生武功：背叛师门时不减半
_MSG_LEFT_SCHOOL = b"\x64" + bytes.fromhex("a4 77 b8 67 ad 49 ab 71 ae 76 aa f9")  # 已經背叛師門
ATTRS = ("str", "crg", "wint", "luk", "dex", "agi", "vit")
_MSG_NEED_ATTRS = b"\x64" + bytes.fromhex("bb dd ad 6e a5 fe c4 dd a9 ca") + b"100" + bytes.fromhex("a1 54")  # 需要全屬性100﹗
_MSG_VIP_PAUSED =b"\x64" + bytes.fromhex("bc c8 b0 b1") + b"VIP" + bytes.fromhex("a5 5c af e0 a1 54")  # 暫停VIP功能﹗
_PTS_PREFIX = bytes.fromhex("c0 78 ad c8 c2 49 bc c6") + _COLON  # 儲值點數﹕
_PTS_SUFFIX = bytes.fromhex("c2 49 a1 54")  # 點﹗
_VIP_TEXT = b"VIP" + bytes.fromhex("b5 a5 af c5") + _COLON + str(VIP_LEVEL).encode() + bytes.fromhex("af c5 a1 54")  # VIP等級﹕7級﹗
_TYCOON_PREFIX = bytes.fromhex("a4 67 bb a8") + _COLON  # 土豪﹕
_TYCOON_SUFFIX = bytes.fromhex("a7 f3 b4 ab a4 46 aa f9 ac a3 a1 54")  # 更換了門派﹗


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_all: list[Frame] = field(default_factory=list)  # 全服（含自己）
    teleport: tuple[int, int, int] | None = None  # 要传送到 (地图, x, y)，由网络层执行
    kick: bool = False  # 回完包之后断开连接（改门派要求重登）


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _sub(sub: int, value: int) -> Frame:
    return (0x7B, bytes([sub, 0x01]) + (value & 0xFFFFFFFF).to_bytes(4, "little"), True)


def _text(sub: int, text: bytes) -> Frame:
    return (0x14, bytes([sub]) + text, True)


def _chat_line(jyid: int, text: bytes) -> Frame:
    """0x04 子类型 02 + 自己的 jyid + 文字：显示在聊天框里的一行系统文字。"""
    return (0x04, b"\x02" + jyid.to_bytes(4, "little") + text, False)


def _num(s: str) -> int:
    m = re.match(r"\s*(-?\d+)", s)
    return int(m.group(1)) if m else 0


def _points(rows: dict) -> int:
    return _i((rows.get("account") or [{}])[0].get("shangchengdianshu"))


def _status_frames(renwu: dict, rows: dict) -> list[Frame]:
    """@scb 的回包：金钱、商城点数（0x32 6f）、两条公告。"""
    pts = _points(rows)
    return [
        _sub(0x3C, _i(renwu.get("jy_money"))),
        (0x32, b"\x6f" + (pts & 0xFFFFFFFF).to_bytes(4, "little"), True),
        _text(0x03, _PTS_PREFIX + str(pts).encode() + _PTS_SUFFIX),
        _text(0x03, _VIP_TEXT),
    ]


def handle(rows: dict, items: ItemTable, tables: Tables, payload: bytes) -> Result:
    res = Result()
    if len(payload) < 2 or payload[:2] != b"\x04\x40" or not rows.get("renwu"):
        return res
    raw = payload[2:]
    renwu = rows["renwu"][0]
    jyid = _i(renwu.get("jyid"))
    # ---- 整串必须完全相等的指令
    if raw in (b"tw\x00", b"tw\x01", b"cxwg", b"bj\x00"):
        return res  # 只改原版内存里的开关，没有回包，库里也不变
    if raw == b"where":
        res.to_self.append(_chat_line(jyid, str(_i(renwu.get("map"))).encode()))
        return res
    if raw == b"kale":
        res.teleport = KALE_TARGET  # 「卡了」：传到固定地点。原版另有 战斗中 / 押镖中 不许传，这里没有这些状态
        return res
    if raw == b"cpw":
        for r in reversed(rows.get("item") or []):  # 原版按内存里背包的倒序列出（最新的在前）
            iid, qty = _i(r.get("item_id")), _i(r.get("shuliang"))
            if iid and qty > 0:
                name = to_big5(items.names.get(iid, ""))
                res.to_self.append(_chat_line(jyid, str(iid).encode() + _COLON + name + _COLON + str(qty).encode()))
        return res
    if raw == b"cxg\x87":  # 转生：七项属性都要 ≥100。满足时原版会重置属性、加气血 / 强度、给新武功……这里没做（见 docs/文字指令.md）
        if any(_i(renwu.get(a)) < 100 for a in ATTRS):
            res.to_self.append((0x1A, _MSG_NEED_ATTRS, False))
        return res
    if raw == b"cxg\x88":  # 「暫停VIP功能﹗」
        res.to_self.append((0x1A, _MSG_VIP_PAUSED, False))
        return res
    if raw == b"cxg\x89":  # 查 VIP 等级
        res.to_self.append(_text(0x03, _VIP_TEXT))
        return res
    if raw == b"sqsq":
        res.to_self.append(_sub(0x37, 1_000_000))  # 只改客户端显示（杀气），库里不变
        return res
    if raw == b"bpsm":
        return _leave_school(rows, tables, res)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return res
    # ---- 带参数的指令
    if text.startswith("se "):  # 善恶：只改显示，-1000..1000
        v = _num(text[3:])
        if not -1000 <= v <= 1000:
            res.to_self.append((0x1A, b"\x64" + bytes.fromhex("b5 bd b4 63 a6 62 2d 31 30 30 30 a8 ec 31 30 30 30 a4 a7 b6 a1"), False))
        else:
            res.to_self.append(_sub(0x45, v))
        return res
    if text.startswith("wp ") and len(text) >= 8:  # GM 给物品：账号 gm_lvl 必须是 1，物品 ID 取 `wp ` 后面 5 个字符
        if _i((rows.get("account") or [{}])[0].get("gm_lvl")) != 1:
            return res
        token = text[3:8]
        iid = int(token) if token.isascii() and token.isdigit() and str(int(token)) == token else 0
        if iid not in items.durability:
            res.to_self.append((0x1A, _MSG_NO_ITEM, False))
            return res
        res.to_self.append((0x77, _entry(iid, items.of(iid)), True))
        _bag_add(rows, str(jyid), iid, 1)
        return res
    if text.startswith("scb "):
        return _exchange(rows, renwu, _num(text[4:]), res)
    if text.startswith("mp ") and len(text) >= 4:
        return _change_school(rows, renwu, text[3], res)
    return res


def _exchange(rows: dict, renwu: dict, n: int, res: Result) -> Result:
    """@scb N：花 N×10 万金钱换 N 点商城点数。N=0（或不是数字）只是查询状态。"""
    if n > SCB_MAX:
        res.to_self.append((0x1A, _MSG_SCB_MAX, False))
        return res
    if n < 0:
        res.to_self.append((0x1A, _MSG_NEGATIVE, False))
        return res
    if n > 0:
        if _i(renwu.get("jy_money")) < n * POINT_PRICE:
            res.to_self.append((0x1A, _MSG_NO_MONEY, False))
            return res
        renwu["jy_money"] = str(_i(renwu.get("jy_money")) - n * POINT_PRICE)
        rows["account"][0]["shangchengdianshu"] = str(_points(rows) + n)
    res.to_self += _status_frames(renwu, rows)
    return res


def _change_school(rows: dict, renwu: dict, digit: str, res: Result) -> Result:
    """@mp 数字：花 9999 商城点数换门派（数字 1–9 见 MP_TABLE；`0` = 不换，只是照样扣点、重发）。回完包踢下线要求重登。"""
    if _points(rows) < MP_COST:
        res.to_self.append((0x1A, _MSG_NEED_POINTS, False))
        return res
    if digit in MP_TABLE:
        renwu["school"], renwu["master"] = (str(v) for v in MP_TABLE[digit])
    elif digit != "0":
        return res
    rows["account"][0]["shangchengdianshu"] = str(_points(rows) - MP_COST)
    name = to_big5(renwu.get("name", "") or "")
    res.to_self += [
        (0x32, b"\x6f" + _points(rows).to_bytes(4, "little"), True),
        _text(0x03, _PTS_PREFIX + str(_points(rows)).encode() + _PTS_SUFFIX),
        _sub(0x41, _i(renwu.get("school"))),
        _sub(0x42, _i(renwu.get("master"))),
    ]
    res.to_all.append(_text(0x0E, _TYCOON_PREFIX + name + _TYCOON_SUFFIX))
    res.kick = True
    return res


def _leave_school(rows: dict, tables: Tables, res: Result) -> Result:
    """@bpsm：背叛师门，免费。有门派：补发师门标记（已有就提示）、门派 / 门技等级 / 门技熟练度 / 师承清零、每门武功等级减半；没门派：只清师承。"""
    renwu = rows["renwu"][0]
    school = _i(renwu.get("school"))
    if school:
        mid = SCHOOL_MARKER.get(school)
        if mid:
            have = any(_i(r.get("biaoji")) == mid for r in rows.get("biaoji") or [])
            if have:
                res.to_self.append((0x1A, _MSG_HAS_MARKER, False))
            else:
                kind = _marker_type(tables, mid)
                res.to_self.append((0x77, _entry(mid, kind), True))
                if mid in tables.markers:
                    _marker_rows(rows).append({"jyid": str(renwu.get("jyid")), "biaoji": str(mid), "zhuangtai": str(kind)})
        renwu["school_skill_lv"] = renwu["school_skill_exp"] = "0"
        renwu["school"] = "0"
        res.to_self += [_sub(0x49, 0), _sub(0x4A, 0)]
        # 原版实测（2026-10-20，kf_compare bpsm-*）：每门武功等级减半（整除）、每门回一条 0x70（按武功 ID 从小到大；等级 0 的行也回；转生武功 3860 不动也不回）；
        # 等级减到 0 的行下线时不会存回库里。没有门派的人不减半。
        for r in sorted(rows.get("kf") or [], key=lambda r: _i(r.get("kf_id"))):
            kid = _i(r.get("kf_id"))
            if kid == REBIRTH_KF:
                continue
            lvl = _i(r.get("kf_lvl")) // 2
            r["kf_lvl"] = str(lvl)
            res.to_self.append((0x70, (_i(renwu.get("study_count")) & 0xFFFF).to_bytes(2, "little") + (_i(renwu.get("dangqianjing")) & 0xFFFF).to_bytes(2, "little")
                                + kid.to_bytes(2, "little") + (lvl & 0xFFFF).to_bytes(2, "little") + (_i(r.get("kf_exp")) & 0xFFFFFFFF).to_bytes(4, "little"), True))
        res.to_self.append((0x1A, _MSG_LEFT_SCHOOL, False))
    renwu["master"] = "0"
    res.to_self += [_sub(0x42, 0), _sub(0x41, 0)]
    return res
