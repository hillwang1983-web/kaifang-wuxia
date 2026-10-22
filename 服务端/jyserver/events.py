"""事件引擎：C2S 0x6B（事件）。依据见 docs/事件引擎.md（反编译 0x63be2f + 对本机原版的逐包实测）。

纯函数：`handle()` 改角色 rows，返回要发的帧；网络层（server.py）负责发送。

数据：data/事件.csv（地图ID, NPCID, 事件id, 事件名称, type, 需要条件, 排斥条件, 结果, 开关）、data/标记.csv（ID, "标记ID:名字", 类型）。
「需要条件」「排斥条件」两列在原版数据里全是空的，条件都写在「结果」里（`验证:` 开头的语句）。

C2S 0x6B 载荷（至少 8 字节）：`[4 字节：原版不看，但 type>=3 时会原样回显] [地图 LE16] [事件id LE16]`。
结果列用 `;` 分成语句，语句用 `:` 分成字段；按顺序执行，**执行过的语句不回滚**，遇到失败就中止（中止时多数情况只回 `7D 事件id`）。
"""

from __future__ import annotations

import csv
import io
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from .kungfu import Kungfu, forget, learn
from .state import ItemTable, to_big5

log = logging.getLogger("jyserver.events")

Frame = tuple[int, bytes, bool]

U32 = 0xFFFFFFFF
TIME_UNITS_PER_HOUR = 48  # 验证:时间:H —— renwu.online_time >= H*48 才通过（实测：38400 过、38399 不过，H=800）
EVIL_BASE = 2000  # 善恶：库里存 evil_val = 显示值 + 2000

# 已知有专门代码（战役、杀龟大会等）的 (事件id, 地图)。它们在读 事件.csv 之前就被拦走，新服务端没有实现。
SPECIAL_EVENTS = {
    (191, 7000), (550, 5000), (457, 9351), (5, 9351), (350, 4000), (863, 5000), (3, 3501),
    (5, 10852), (252, 1000), (427, 2000), (150, 3000), (137, 5000), (866, 5000),
}

# ---- 固定文字（BIG5，全部是对原版回包逐字节抄下来的；原版的全角标点是 ﹕ ﹗ 而不是 ： ！）
_GOT_MARKER = bytes.fromhex("b1 6f a8 ec bc d0 b0 4f a1 52")  # 得到標記﹕
_LOST_MARKER = bytes.fromhex("a5 a2 a5 68 bc d0 b0 4f a1 52")  # 失去標記﹕
_LACK_MARKER = bytes.fromhex("af ca a4 d6 bc d0 b0 4f a1 52")  # 缺少標記﹕
_GOT_ITEM = bytes.fromhex("b1 6f a8 ec aa ab ab 7e a1 52")  # 得到物品﹕
_LOST_ITEM = bytes.fromhex("a5 a2 a5 68 aa ab ab 7e a1 52")  # 失去物品﹕
_LACK_ITEM = bytes.fromhex("af ca a4 d6 aa ab ab 7e a1 52")  # 缺少物品﹕
_HAS_MARKER = bytes.fromhex("a8 ad a4 57 a6 b3 bc d0 b0 4f a1 52")  # 身上有標記﹕
_HAS_ITEM = bytes.fromhex("a8 ad a4 57 a6 b3 aa ab ab 7e a1 52")  # 身上有物品﹕（推断：没有实测，文字来自 exe 里的「身上有物品：」）
_NO_ITEM = bytes.fromhex("aa ab ab 7e a4 a3 a8 ac")  # 物品不足
_BAG_HAS_NO_ITEM = bytes.fromhex("ad 49 a5 5d a8 53 a6 b3 a6 b9 aa ab ab 7e")  # 背包沒有此物品
_CANT_TAKE = bytes.fromhex("2c b5 4c aa 6b b1 b5 a6 b9 a5 f4 b0 c8 a1 54")  # ,無法接此任務﹗
_COMBAT_LACK = bytes.fromhex("b9 ea be d4 a4 a3 a8 ac a1 41 bb dd")  # 實戰不足，需
_TIME_LACK = bytes.fromhex("a4 57 bd 75 ae c9 b6 a1 a4 a3 a8 ac")  # 上線時間不足
_HOURS = bytes.fromhex("a4 70 ae c9")  # 小時
_SCHOOL_MISMATCH = bytes.fromhex("aa f9 ac a3 a4 a3 b2 c5 a1 52")  # 門派不符﹕
_LOGGED = bytes.fromhex("a6 e6 ac b0 a4 77 b0 4f bf fd a1 54")  # 行為已記錄﹗
_CHANGED = bytes.fromhex("a7 ef c5 dc a1 54")  # 改變﹗
_SCHOOL_SKILL_ADDED = bytes.fromhex("bc 57 a5 5b aa f9 a7 de")  # 增加門技
_NOT_OPEN = to_big5("此事件暂未开放")  # 没有数据能触发（事件.csv 的「开关」列全是 1）；文字未经实测
_CHEAT_PREFIX = bytes.fromhex("aa b1 ae 61 3a")  # 玩家:
_CHEAT_MID = bytes.fromhex("a1 41 a9 6d a6 57 3a")  # ，姓名:
_CHEAT_SUFFIX = bytes.fromhex("a8 ea a8 c6 a5 f3 a1 41 aa 5a a5 5c c0 48 c9 f3 b1 bc a4 40 af c5")  # 刷事件，武功隨机掉一級

# 属:<名> → (renwu 列, 0x7B 子类型, 「xx改變﹗」前缀)。顺序无关；前缀都是 0x14 子类型 08 的文字。
ATTRS: dict[str, tuple[str, int, bytes | None]] = {
    "金钱": ("jy_money", 0x3C, bytes.fromhex("aa f7 bf fa")),
    "名声": ("fame_val", 0x3D, bytes.fromhex("a6 57 c1 6e")),
    "历练": ("exp_val", 0x44, bytes.fromhex("be fa bd 6d")),
    "实战": ("combat_exp", 0x2B, bytes.fromhex("b9 ea be d4")),
    "善恶": ("evil_val", 0x45, bytes.fromhex("b5 bd b4 63")),
    "杀气": ("kill_val", 0x37, bytes.fromhex("b1 fe c9 61")),
    "PK值": ("pk_val", 0x38, bytes.fromhex("50 4b ad c8")),
    "学点": ("study_count", 0x28, bytes.fromhex("be c7 c2 49")),  # 學點
}
# 加减后的上限（实测，见 docs/事件引擎.md「数值夹取」）：N>0 只卡上限，N<0 只卡下限（善恶 1000、其余 0），N=0 不动；
# PK值 例外：不论方向都夹到 [0,100]。金钱 N<0 且结果 <=0 时整个事件中止（在 attr() 里）。实战没有上限，按 2^32 回绕。
ATTR_CAP = {"金钱": 1_000_000_000, "名声": 1_000_000, "历练": 1_000_000, "杀气": 1_000_000, "学点": 65200, "善恶": EVIL_BASE + 1000}
ATTR_FLOOR = {"善恶": EVIL_BASE - 1000}
PK_CAP = 100
SCHOOL_SKILL_MAX = 100  # 门技等级
# 基本:<名> → (武功 ID, renwu 等级列, 升一级要 floor(系数×等级³) 的系数×2)；经验列是 <列>exp（枪法的经验原版读成 0）。交易之道原版什么都不做。
BASIC_SKILLS: dict[str, tuple[int, str, int]] = {
    "基本刀法": (8001, "daofa", 2), "基本枪法": (8002, "qiangfa", 2), "基本剑法": (8003, "jianfa", 2), "基本鞭法": (8004, "bianfa", 2),
    "基本棍法": (8005, "gunfa", 2), "基本内功": (8006, "neigong", 2), "基本刺术": (8007, "cishu", 2), "基本身法": (8008, "shenfa", 2),
    "基本毒术": (8009, "dushu", 2), "基本医术": (8010, "yishu", 2), "基本阵法": (8011, "zhenfa", 2), "搏击格斗": (8012, "boji", 2),
    "闪躲纵跃": (8013, "shanduo", 2), "基本暗器": (8014, "anqi", 2), "拆招卸力": (8015, "chaizhao", 2), "读书识字": (8017, "dushushizi", 3),
}
_NO_SUCH_KF = bytes.fromhex("b5 4c a6 b9 aa 5a a5 5c")  # 無此武功
SET_ATTRS = {"门派": ("school", 0x41), "师承": ("master", 0x42)}  # 直接赋值，只回一条短帧 0x7B，没有 0x14


@dataclass
class Event:
    map_id: str
    event_id: str
    type: str
    result: str
    enabled: str


@dataclass
class Tables:
    events: dict[tuple[str, str], Event] = field(default_factory=dict)  # (地图, 事件id) -> Event，重复时取**第一条**（原版线性扫描）
    markers: dict[int, tuple[str, int]] = field(default_factory=dict)  # 标记ID -> (名字, 类型)，重复时取第一条
    kungfu: Kungfu = field(default_factory=Kungfu)  # 武功名字和学习条件（武功:ID:等级 语句用）

    @classmethod
    def load(cls, data_dir: str | Path) -> "Tables":
        t = cls()
        p = Path(data_dir) / "事件.csv"
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) < 9 or row[0].startswith("//"):
                    continue
                t.events.setdefault((row[0], row[2]), Event(row[0], row[2], row[4], row[7], row[8]))
        p = Path(data_dir) / "标记.csv"
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) >= 3 and row[0].strip().isdigit():
                    mid, _, name = row[1].partition(":")
                    if mid.strip().isdigit():
                        t.markers.setdefault(int(mid), (name, val(row[2])))
        t.kungfu = Kungfu.load(data_dir)
        return t


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_all: list[Frame] = field(default_factory=list)  # 发给所有在线玩家（含自己）
    inline: list[tuple[int, Frame]] = field(default_factory=list)  # 事件中途的全服广播：(广播时 to_self 已有几帧, 帧)；网络层按这个位置穿插
    skipped: list[str] = field(default_factory=list)  # 没实现、被跳过的语句（给日志和测试看）


NOOP_KINDS = {"熟练", "技能", "反向"}  # 实测无任何效果（熟练:/技能: 即使有对应武功 / 技能等级也一样）


def _wrap32(v: int) -> int:
    """VB 的 32 位整数转换：超出范围按 2^32 回绕（实测门技）。"""
    v = int(v) & U32
    return v - (1 << 32) if v >= (1 << 31) else v


_VAL = re.compile(r"\s*([+-]?\d+)")


def val(text) -> int:
    """易语言「到整数」：取开头的整数，取不到（空、`-`、字母）就是 0。"""
    m = _VAL.match(str(text or ""))
    return int(m.group(1)) if m else 0


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _notice(text: bytes) -> Frame:
    return (0x14, b"\x08" + text, True)


def _system_text(text: bytes) -> Frame:
    return (0x1A, b"\x64" + text, False)


def _sub(sub: int, value: int, *, wide: bool = True) -> Frame:
    return (0x7B, bytes([sub, 0x01]) + (value & 0xFFFFFFFF).to_bytes(4, "little"), wide)


class _Abort(Exception):
    """语句执行失败：后面的语句不再执行。frames 已经按原版顺序写进 Result。"""

    def __init__(self, reply: bool = True):
        self.reply = reply  # True：回 `7D 事件id`；False：什么都不回（金钱不够等）


# ---- 标记 / 物品的存取
def _marker_rows(rows: dict) -> list[dict]:
    return rows.setdefault("biaoji", [])


def _has_marker(rows: dict, mid: int) -> bool:
    return mid > 0 and any(_i(r.get("biaoji")) == mid for r in rows.get("biaoji") or [])


def _marker_type(tables: Tables, mid: int) -> int:
    return tables.markers[mid][1] if mid in tables.markers else 0


def _marker_name(tables: Tables, mid: int) -> bytes:
    return to_big5(tables.markers[mid][0]) if mid in tables.markers else b""


def _entry(entry_id: int, kind: int) -> bytes:
    """0x77（得到）/ 0x6B（失去）的载荷：ID(LE32) + (0x100 + 类型)(LE16)。"""
    return entry_id.to_bytes(4, "little") + (0x100 + kind).to_bytes(2, "little")


def _bag_qty(rows: dict, item_id: int) -> int:
    return sum(_i(r.get("shuliang")) for r in rows.get("item") or [] if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200)


def _bag_add(rows: dict, jyid: str, item_id: int, qty: int) -> None:
    for r in rows.setdefault("item", []):
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200:
            r["shuliang"] = str(_i(r.get("shuliang")) + qty)
            return
    rows["item"].append({"jyid": jyid, "item_id": str(item_id), "shuliang": str(qty), "state": "200"})


def _bag_take(rows: dict, item_id: int) -> None:
    for r in rows.get("item") or []:
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200 and _i(r.get("shuliang")) > 0:
            left = _i(r.get("shuliang")) - 1
            if left > 0:
                r["shuliang"] = str(left)
            else:
                rows["item"].remove(r)
            return


class _Run:
    """一次事件的执行上下文。"""

    def __init__(self, rows: dict, tables: Tables, items: ItemTable, res: Result, event_id: bytes):
        self.rows, self.tables, self.items, self.res, self.event_id = rows, tables, items, res, event_id
        self.renwu = rows["renwu"][0]
        self.jyid = str(self.renwu.get("jyid"))

    def out(self, *frames: Frame) -> None:
        self.res.to_self.extend(frames)

    # -- 标记
    def marker(self, token: str, n: int, forced: bool) -> None:
        mid = val(token)
        kind = _marker_type(self.tables, mid)
        name = _marker_name(self.tables, mid)
        if n > 0:
            for _ in range(n):
                self.out((0x77, _entry(mid, kind), True), _notice(_GOT_MARKER + name))
                if mid in self.tables.markers:  # 不在 标记.csv 里的标记只发帧，不入库（实测）
                    _marker_rows(self.rows).append({"jyid": self.jyid, "biaoji": str(mid), "zhuangtai": str(kind)})
        elif n < 0:
            for _ in range(-n):
                self.out((0x6B, _entry(mid, kind), True))  # 失去的帧先发，缺不缺都发（实测）
                if _has_marker(self.rows, mid):
                    for r in self.rows["biaoji"]:
                        if _i(r.get("biaoji")) == mid:
                            self.rows["biaoji"].remove(r)
                            break
                    self.out(_notice(_LOST_MARKER + name))
                elif forced:  # 标记2：没有也不算错，照样报「失去」
                    self.out(_notice(_LOST_MARKER + name))
                else:
                    self.res.to_self.append((0x7D, self.event_id, True))
                    self.out(_notice(_LACK_MARKER + to_big5(token)))
                    raise _Abort(False)

    # -- 物品
    def item(self, token: str, n: int, forced: bool) -> None:
        iid = val(token)
        dur = self.items.of(iid)
        name = to_big5(self.items.names.get(iid, ""))
        if n > 0:
            for _ in range(n):
                self.out((0x77, _entry(iid, dur), True), _notice(_GOT_ITEM + name))
            _bag_add(self.rows, self.jyid, iid, n)
        elif n < 0:
            for _ in range(-n):
                self.out((0x6B, _entry(iid, dur), True))
                if _bag_qty(self.rows, iid) >= 1:
                    _bag_take(self.rows, iid)
                    self.out(_notice(_LOST_ITEM + (to_big5(str(iid)) if forced else name)))
                elif forced:  # 物品2：没有也不算错
                    self.out(_system_text(_BAG_HAS_NO_ITEM), _notice(_LOST_ITEM + to_big5(str(iid))))
                else:
                    self.out(_system_text(_NO_ITEM), (0x7D, self.event_id, True), _notice(_LACK_ITEM + name))
                    raise _Abort(False)

    # -- 属
    def attr(self, name: str, n: int) -> bool:
        if name in SET_ATTRS:
            col, sub = SET_ATTRS[name]
            self.renwu[col] = str(n)
            self.out(_sub(sub, n, wide=False))
            return True
        if name == "门技":
            self.school_skill(n)
            return True
        if name not in ATTRS:
            return False
        col, sub, label = ATTRS[name]
        old = _i(self.renwu.get(col))
        new = old + n
        if name == "金钱" and n < 0 and new <= 0:
            raise _Abort(False)  # 钱不够（连正好花光都不行）：什么都不回（实测）
        if name == "PK值":
            new = max(0, min(PK_CAP, new))
        elif name == "实战":
            new = new & U32 if n > 0 else (max(0, new) if n < 0 else new)
        elif n > 0:
            new = min(new, ATTR_CAP[name])
        elif n < 0:
            new = max(new, ATTR_FLOOR.get(name, 0))
        self.renwu[col] = str(new)
        shown = new - EVIL_BASE if name == "善恶" else new
        self.out(_sub(sub, shown), _notice(label + _CHANGED))
        return True

    # -- 门技（原版 0x6a49fb）
    def school_skill(self, n: int) -> None:
        lv, exp = _i(self.renwu.get("school_skill_lv")), _i(self.renwu.get("school_skill_exp"))
        total = _wrap32((exp + n) * 10000)  # 原版把乘积转成 32 位整数，大数回绕（实测）
        if total < 1:
            new_lv, new_exp = lv, 0
        elif lv < SCHOOL_SKILL_MAX:
            new_lv = lv
            while total > (new_lv + 1) ** 2:
                new_lv += 1
                total -= new_lv ** 2
            new_lv, new_exp = (SCHOOL_SKILL_MAX, 0) if new_lv > SCHOOL_SKILL_MAX else (new_lv, total)
        else:
            self.out(_notice(_SCHOOL_SKILL_ADDED))  # 已经 100 级：不改、不发 0x7B
            return
        self.renwu["school_skill_lv"], self.renwu["school_skill_exp"] = str(new_lv), str(new_exp)
        self.out(_sub(0x49, new_lv), _sub(0x4A, new_exp), _notice(_SCHOOL_SKILL_ADDED))

    # -- 基本:<名>:N（原版 0x63be2f 里，只发 0x68，不落库）
    def basic(self, name: str, n: int) -> None:
        if name not in BASIC_SKILLS:
            self.res.skipped.append(f"基本:{name}")
            return
        kid, col, coef2 = BASIC_SKILLS[name]
        lv = _i(self.renwu.get(col))
        total = (0 if col == "qiangfa" else _i(self.renwu.get(col + "exp"))) + n
        if -(1 << 31) <= total < (1 << 31):  # 超出 32 位有符号数时原版不升级，直接把低 32 位发出去
            while total > (coef2 * (lv + 1) ** 3) // 2:
                lv += 1
                total -= (coef2 * lv ** 3) // 2
        body = (kid & 0xFFFF).to_bytes(2, "little") + (lv & 0xFFFF).to_bytes(2, "little") + (total & U32).to_bytes(4, "little")
        body += (_i(self.renwu.get("study_count")) & 0xFFFF).to_bytes(2, "little") + (_i(self.renwu.get("dangqianjing")) & 0xFFFF).to_bytes(2, "little")
        self.out((0x68, body, True))

    # -- 武功熟练度:ID:N —— 直接加到 kf_exp 上（不升级），回 0x70
    def kf_exp(self, token: str, n: int) -> None:
        if n == 0:
            return
        row = next((r for r in self.rows.get("kf") or [] if _i(r.get("kf_id")) == val(token)), None)
        if row is None:
            self.out(_system_text(_NO_SUCH_KF))
            return
        total = (_i(row.get("kf_exp")) + n) & U32
        row["kf_exp"] = str(total - (1 << 32) if total >= (1 << 31) else total)
        body = (_i(self.renwu.get("study_count")) & 0xFFFF).to_bytes(2, "little") + (_i(self.renwu.get("dangqianjing")) & 0xFFFF).to_bytes(2, "little")
        body += (val(token) & 0xFFFF).to_bytes(2, "little") + (_i(row.get("kf_lvl")) & 0xFFFF).to_bytes(2, "little") + total.to_bytes(4, "little")
        self.out((0x70, body, True))

    # -- 武功
    def kf(self, token: str, n: int) -> None:
        kid = val(token)
        res = learn(self.rows, self.tables.kungfu, kid, n) if n >= 1 else forget(self.rows, kid) if n < 0 else None
        if res is not None:
            self.res.inline.extend((len(self.res.to_self), f) for f in res.to_all)
            self.res.to_self.extend(res.to_self)

    # -- 验证
    def verify(self, what: str, token: str) -> None:
        if what == "标记":
            mid = val(token)
            if _has_marker(self.rows, mid):
                self.out(_system_text(_HAS_MARKER + str(mid).encode() + _CANT_TAKE))
                raise _Abort(True)
        elif what == "物品":
            iid = val(token)
            if _bag_qty(self.rows, iid) >= 1:
                self.out(_system_text(_HAS_ITEM + str(iid).encode() + _CANT_TAKE))
                raise _Abort(True)
        elif what == "实战":
            need = val(token)
            if _i(self.renwu.get("combat_exp")) < need:
                self.out(_system_text(_COMBAT_LACK + str(need).encode() + _CANT_TAKE))
                raise _Abort(True)
        elif what == "时间":
            hours = val(token)
            if _i(self.renwu.get("online_time")) < hours * TIME_UNITS_PER_HOUR:
                self.out(_system_text(_TIME_LACK + str(hours).encode() + _HOURS + _CANT_TAKE))
                raise _Abort(True)
        elif what == "门派":
            need = val(token)
            if _i(self.renwu.get("school")) != need:
                self.out(_system_text(_SCHOOL_MISMATCH + str(need).encode() + _CANT_TAKE + _LOGGED))
                raise _Abort(True)
        else:
            self.res.skipped.append(f"验证:{what}")

    def statement(self, text: str) -> None:
        parts = text.split(":")
        if len(parts) < 3:
            raise _Abort(None)  # 字段不足 3 个：记错误日志后放弃，不回包（实测）
        if len(parts) > 3:
            self.res.skipped.append(text)  # 多于 3 个字段：原版整条跳过（实测：物品:x:-1:物品:y:3 什么都没发生）
            return
        kind, a, b = parts
        if kind in ("标记", "标记2"):
            self.marker(a, val(b), kind == "标记2")
        elif kind in ("物品", "物品2"):
            self.item(a, val(b), kind == "物品2")
        elif kind == "属":
            if not self.attr(a, val(b)):
                self.res.skipped.append(text)
        elif kind == "验证":
            self.verify(a, b)
        elif kind == "武功":
            self.kf(a, val(b))
        elif kind == "基本":
            self.basic(a, val(b))
        elif kind == "武功熟练度":
            self.kf_exp(a, val(b))
        elif kind in NOOP_KINDS:
            pass  # 原版实测：什么都不做（只有事件末尾的 7D）
        else:  # 未知前缀（`属性:`、`输:` …）：原版也什么都不做，只记日志
            self.res.skipped.append(text)


def _tail(tokens: bytes, n: int, count: int) -> bytes | None:
    """回包 `7D` 里跟在事件id 后面的部分：从帧尾往前数，每个 type 单位取 2 个字节（地图、再往前…）。

    原版把整帧当十六进制文本按空格拆成 token（F4 44 <长度> 6B <载荷…>），取 token[n-2k-2], token[n-2k-1]，
    k=1..count，**越靠前的越先**。不够取（n < 2k+1）时原版什么都不回。
    """
    out = b""
    for k in range(1, count + 1):
        if n < 2 * k + 1:
            return None
        out = tokens[n - 2 * k - 2 : n - 2 * k] + out
    return out


def handle(
    rows: dict,
    tables: Tables,
    items: ItemTable,
    payload: bytes,
    *,
    wide: bool = False,
    rng: random.Random | None = None,
) -> Result:
    """C2S 0x6B。rows 是角色库格式；返回 Result（自己收的帧、要全服广播的帧）。"""
    res = Result()
    if wide or len(payload) < 8 or not rows.get("renwu"):
        return res
    renwu = rows["renwu"][0]
    n = len(payload) + 4
    tokens = bytes([0xF4, 0x44, n & 0xFF, 0x6B]) + payload  # 原版拿到的是解密后的整帧文本
    map_id = int.from_bytes(payload[4:6], "little")
    ev_id = int.from_bytes(payload[6:8], "little")
    event_id = payload[6:8]

    if str(map_id) != str(_i(renwu.get("map"))):
        # 「刷事件」：事件所在地图和玩家当前地图不一致。先回 7D，再全服广播警告；原版还会让玩家随机掉一级武功（没实现，见文档）
        log.warning("%s 刷事件：地图不符 map=%s event=%s", renwu.get("jyid"), map_id, ev_id)
        res.to_self.append((0x7D, event_id, True))
        res.to_all.append(
            _notice_kind(0x0E, _CHEAT_PREFIX + str(renwu.get("jyid")).encode() + _CHEAT_MID + to_big5(renwu.get("name") or "") + _CHEAT_SUFFIX)
        )
        return res

    if (ev_id, map_id) in SPECIAL_EVENTS:
        log.warning("%s 事件 %d/%d 在原版里是专门写的代码（战役等），未实现", renwu.get("jyid"), map_id, ev_id)
        return res

    ev = tables.events.get((str(map_id), str(ev_id)))
    if ev is None:
        # 「请增加地图事件」：回 7D 事件id + 地图（type 为空的那个分支）
        log.warning("%s 请增加地图事件：地图%d 事件%d", renwu.get("jyid"), map_id, ev_id)
        tail = _tail(tokens, n, 1)
        if tail is not None:
            res.to_self.append((0x7D, event_id + tail, True))
        return res
    if ev.enabled.strip() != "1":
        res.to_self.append(_system_text(_NOT_OPEN))
        res.to_self.append((0x7D, event_id, True))
        return res

    run = _Run(rows, tables, items, res, event_id)
    if ev.result != " ":
        try:
            for stmt in ev.result.split(";"):
                if stmt != "":
                    run.statement(stmt)
        except _Abort as stop:
            if stop.reply is True:
                res.to_self.append((0x7D, event_id, True))
            elif stop.reply is None:
                log.warning("%s 事件 %d/%d 语句字段不足，放弃", renwu.get("jyid"), map_id, ev_id)
            return res
    for s in res.skipped:
        log.warning("%s 事件 %d/%d：未实现的语句 %r", renwu.get("jyid"), map_id, ev_id, s)

    count = val(ev.type) if ev.type != "" else 1
    tail = _tail(tokens, n, count)
    if tail is not None:
        res.to_self.append((0x7D, event_id + tail, True))
    return res


def _notice_kind(sub: int, text: bytes) -> Frame:
    return (0x14, bytes([sub]) + text, True)
