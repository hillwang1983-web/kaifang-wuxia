"""登录序列生成器：由角色的数据库行生成 C2S 0x19（启动登录）的 S2C 回包。

布局来自对原版服务端的差分实测（tools/layout_probe.py 等），详见 docs/登录序列布局.md。要点：

  0x1E 角色完整状态包（长帧）的载荷 =
      [0:4]     服务端运行分钟数（LE32，每分钟 +1，实测 675→676；不是校验和）
      [4:6]     背包记录条数 N（LE16，含末尾一条 (0,0) 结束记录）
      [6:6+5N]  背包记录：每条 = 物品ID(LE32) + 耐久(1 字节)；物品按数量展开
      [..]      尾部，布局固定（偏移以 N=23 的模板为基准，实际偏移 += 5*(N-23)）
  模板 = 原版服务端对测试号 8617293 的真实回包（data/fixtures/char-8617293.json）；
  尾部里凡是没有被下面字段表覆盖的字节，都原样取自模板（常量或尚未弄清的字段）。

不确定/未覆盖的地方都在 docs/登录序列布局.md 的「未解」一节。
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

TEMPLATE_N = 23  # 模板里的背包记录条数
TAIL_BASE = 6 + 5 * TEMPLATE_N  # = 121：模板里尾部开始的偏移

# ---- 字段表：(表, 列, 模板偏移, 宽度)；全部小端无符号整数，宽度单位字节 -----------------------------

RENWU_FIELDS: list[tuple[str, int, int]] = [
    ("map", 204, 4), ("x", 208, 4), ("y", 212, 4),
    ("zuidajing", 216, 2), ("dangqianjing", 218, 2),
    ("zuidaxue", 220, 3), ("dangqianxue", 224, 3),
    ("zuidashen", 228, 2), ("dangqianshen", 230, 2),
    ("dangqiannei", 232, 4), ("zuidanei", 236, 4),
    ("str", 240, 1), ("crg", 241, 1), ("wint", 242, 1), ("luk", 243, 1),
    ("dex", 244, 1), ("agi", 245, 1), ("vit", 246, 1), ("zigong", 247, 1),
    ("study_count", 248, 2), ("combat_exp", 258, 4),
    ("wuqiqiangdu", 274, 2), ("fangjuqiangdu", 276, 2),
    ("diet_val", 282, 1), ("water_val", 285, 1), ("kill_val", 286, 4), ("pk_val", 290, 1),
    ("jy_money", 299, 4), ("fame_val", 303, 4),
    ("online_time", 349, 4), ("b_month", 353, 1), ("b_day", 354, 1),
    ("sex", 357, 1), ("school", 358, 1), ("master", 360, 2),
    ("exp_val", 368, 4), ("evil_val", 372, 2),
    ("school_skill_lv", 378, 1), ("school_skill_exp", 379, 4),
    ("head_image", 728, 1), ("mode", 729, 1),
]

# 装备栏：5 字节记录 = 物品ID(LE32) + 状态(1)。wuqi 出现两次（两个记录都取同一列）
EQUIP_RECORDS: list[tuple[str, str, int]] = [
    ("toukui", "toukuizhuangtai", 121), ("xianglian", "xianglianzhuangtai", 126),
    ("yifu", "yifuzhuangtai", 131), ("pifeng", "pifengzhuangtai", 136),
    ("wuqi", "wuqizhuangtai", 141), ("wuqi", "wuqizhuangtai", 146),
    ("huwan", "huwanzhuangtai", 151), ("jiezhi", "jiezhizhuangtai", 156),
    ("xiezi", "xiezizhuangtai", 161),
]

# 17 个武学类别：6 字节记录 = 等级(LE16) + 经验(LE32)，从 425 起步长 6
MARTIAL_SKILLS: list[str] = [
    "daofa", "qiangfa", "jianfa", "bianfa", "gunfa", "neigong", "cishu", "shenfa",
    "dushu", "yishu", "zhenfa", "boji", "shanduo", "anqi", "chaizhao", "dushushizi", "jiaoyi",
]
MARTIAL_BASE = 425

# char_equip：15 个槽位，每个 LE16，从 395 起
CHAR_EQUIP_COLS = ["dao", "qiang", "jian", "bian", "gun", "xin", "ci", "qing", "du", "yi", "zhen", "quan", "shan", "ge", "no"]
CHAR_EQUIP_BASE = 395

# jineng：生活技能，5 字节记录 = 等级(1) + 经验(LE32)，从 673 起；lirenexp 原版不写入包里
LIFE_SKILLS: list[tuple[str, str]] = [
    ("famu", "famuexp"), ("gongjiang", "gongjiangexp"), ("zhibu", "zhibuexp"), ("caifeng", "caifengexp"),
    ("lieren", "lirenexp"), ("caikuang", "caikuangexp"), ("datie", "datieexp"), ("zhujian", "zhujianexp"),
    ("nongfu", "nongfuexp"), ("buyu", "buyuexp"), ("chushi", "chushiexp"),
]
LIFE_BASE = 673
LIFE_EXP_NOT_SENT = {"lirenexp"}

# kf：武功列表。偏移 528 是条数(LE16)，记录从 529 起，每条 **9** 字节：+1 等级(LE16) +3 经验(LE32) +7 武功ID(LE16)，最多 16 条（到 673 = 生活技能区为止）。
# 原版实测（8617293 写入 4 条：行距 9，不是 11；见 docs/0x1E字段表.md）
KF_COUNT_OFF, KF_BASE, KF_STRIDE, KF_CAPACITY = 528, 529, 9, 16

JYID_OFF = 166  # LE32
NAME_OFF = 170  # 长度前缀字符串，字段总宽 17
TITLE_OFF = 187  # 同上，内容 = "V7Z0-" + 昵称
STR_FIELD_WIDTH = 17
TITLE_PREFIX = b"V7Z0-"

# 0x14 系统公告里的点数文本（BIG5）
_PTS_SUFFIX = bytes.fromhex("c2 49 a1 54")  # 「點﹗」
_PTS_CHARGE = bytes.fromhex("c0 78 ad c8 c2 49 bc c6 a1 52")  # 「儲值點數﹕」
_PTS_TOTAL = bytes.fromhex("c1 60 c3 d9 a7 55 c2 49 bc c6 a1 52")  # 「總贊助點數﹕」


# 「本服贊助王﹕<名字>上線啦﹗，贊助點數為﹕<总消费点数>」，subtype 0x0e；实测来自测试号 123456
_KING_PREFIX = bytes.fromhex("0e a5 bb aa 41 c3 d9 a7 55 a4 fd a1 52")
_KING_MIDDLE = bytes.fromhex("a4 57 bd 75 b0 d5 a1 54 a1 41 c3 d9 a7 55 c2 49 bc c6 ac b0 a1 52")


def _load_s2t() -> dict[str, str]:
    p = Path(__file__).resolve().parent.parent / "data" / "s2t.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


S2T: dict[str, str] = _load_s2t()

# 参与「武器强度 / 防具强度」求和的装备列
STRENGTH_SLOTS = ("toukui", "xianglian", "wuqi", "yifu", "pifeng", "jiezhi", "xiezi", "huwan")


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def to_big5(text: str, extra: dict[str, bytes] | None = None) -> bytes:
    """GBK 简体 → BIG5 繁体字节（原版的真实转换，用 tools/name_map_probe.py 对 846 个武功名共 3521 个字逐字核对过，只有 1 个特例）。

    规则：先看这个字能不能直接编成 CP950（Windows 的 BIG5，含 ETEN 扩展）——能就原样用，所以 万 体 气 极 网 儿 蚕 恒 都**不**转繁体
    （c945 ca5e c961 cce5 ca49 a449 d3c9 f9da）；编不了的再过 S2T 简繁表（tools/build_s2t_nls.py 用 Windows NLS 的 LCMAP_TRADITIONAL_CHINESE
    生成，如 戏→戲 项→項 炼→煉 钢→鋼 连→連）；还编不了的变全角空格 a1 40（如 噼 勐）。特例：全角句点 ． (U+FF0E) 是 a1 4f。
    查找顺序：extra（调用方给的字节）→ 上面的规则。
    旧版先过 S2T 再编码，对 万 体 气 之类会多转一次；MOB 表 BIG5_NAME 列是人工校对的词义用字，不是转换结果，不能拿来校验。
    """
    out = bytearray()
    for ch in text:
        if extra and ch in extra:
            out += extra[ch]
            continue
        if ch == "．":
            out += b"\xa1\x4f"
            continue
        try:
            out += ch.encode("cp950")
            continue
        except UnicodeEncodeError:
            pass
        try:
            out += S2T.get(ch, ch).encode("cp950")
        except UnicodeEncodeError:
            try:
                ch.encode("gbk")
                out += b"\xa1\x40"  # 简体里有、BIG5 里没有（噼 勐）：原版给全角空格
            except UnicodeEncodeError:
                out += b"?"  # 连 GBK 都没有的字（表情之类）：没样本，沿用 ?
    return bytes(out)


_T2S: dict[str, str] = {}
for _s, _t in S2T.items():
    _T2S.setdefault(_t, _s)


def from_big5(raw: bytes) -> str:
    """客户端发来的 BIG5 字节 → 库里用的简体字符串（BIG5 解码后过繁转简；原版存库的就是简体，如 斕 → 斓）。"""
    return "".join(_T2S.get(ch, ch) for ch in raw.decode("big5", errors="replace"))

class ItemTable:
    """物品表。耐久（背包记录的第 5 个字节）来自 装备数据.csv 第 10 列和 药品.csv 第 3 列；
    攻击 / 防御（算武器强度、防具强度用）来自 装备数据.csv 第 8 / 9 列。"""

    def __init__(
        self,
        durability: dict[int, int],
        attack: dict[int, int] | None = None,
        defense: dict[int, int] | None = None,
        names: dict[int, str] | None = None,
        effects: dict[int, dict[str, int]] | None = None,
        sellable: set[int] | None = None,
        no_trade: set[int] | None = None,
        price: dict[int, int] | None = None,
        broadcast: set[int] | None = None,
    ):
        self.durability = durability
        self.attack = attack or {}
        self.defense = defense or {}
        self.names = names or {}  # 物品ID -> 简体名称（装备数据.csv 第 4 列、药品.csv 第 2 列）
        self.effects = effects or {}  # 药品ID -> {效果列名: 数值}，只含非 0 的列（药品.csv）
        self.sellable = sellable or set()  # 装备数据.csv「商品」列 = 1 的物品：商店里可以买（实测）
        self.price = price or {}  # 装备数据.csv「价格」列（第 11 列）：VIP 回收按它折算
        self.no_trade = no_trade or set()  # 装备数据.csv「交易」列 = 0 的物品（34 件）：不能丢弃（实测，其余交易规则见 docs/丢弃回收交易.md）
        self.broadcast = broadcast or set()  # 装备数据.csv「是否广播」列 = 1：合成出来时全服公告（实测，见 docs/合成.md）

    @classmethod
    def load(cls, data_dir: str | Path) -> "ItemTable":
        d = Path(data_dir)
        dur: dict[int, int] = {}
        atk: dict[int, int] = {}
        dfn: dict[int, int] = {}
        names: dict[int, str] = {}
        effects: dict[int, dict[str, int]] = {}
        sellable: set[int] = set()
        no_trade: set[int] = set()
        price: dict[int, int] = {}
        broadcast: set[int] = set()

        def num(row, col):
            return int(row[col]) if len(row) > col and row[col].strip().lstrip("-").isdigit() else None

        for name, col, name_col in (("药品.csv", 2, 1), ("装备数据.csv", 9, 3)):
            p = d / name
            if not p.exists():
                continue
            text = p.read_bytes().decode("gbk", errors="replace")
            header: list[str] = []
            for row in csv.reader(io.StringIO(text)):
                if row and not row[0].strip().isdigit() and not header:
                    header = row
                if not (row and row[0].strip().isdigit()):
                    continue
                iid = int(row[0])
                v = num(row, col)
                if v is not None:
                    dur[iid] = v & 0xFF
                if len(row) > name_col:
                    names[iid] = row[name_col]
                if name == "装备数据.csv":
                    atk[iid], dfn[iid] = num(row, 7) or 0, num(row, 8) or 0
                    if num(row, 19) == 1:
                        sellable.add(iid)
                    price[iid] = num(row, 10) or 0
                    if num(row, 20) == 1:
                        broadcast.add(iid)
                    if len(row) > 21 and row[21] == "0":
                        no_trade.add(iid)
                else:
                    eff = {h: int(x) for h, x in zip(header[5:], row[5:]) if x.strip().lstrip("-").isdigit() and int(x) != 0}
                    effects[iid] = eff
        return cls(dur, atk, dfn, names, effects, sellable, no_trade, price, broadcast)

    def of(self, item_id: int) -> int:
        """耐久 / 类型字节。物品不在两张表里时原版给 200（实测：事件给了表外物品 33757，登录包和 0x77 帧里都是 0xC8）。"""
        return self.durability.get(item_id, 200)

    def strengths(self, renwu: dict) -> tuple[int, int]:
        """(武器强度, 防具强度) = 身上各装备 攻击 / 防御 之和 + 永久加成（renwu.wuqiqiangdu / fangjuqiangdu，吃永久攻 / 永久防药累加）。

        实测：测试号 123456 为 1610 / 8890（加成列为 0）；吃了霹雳丹(+50)、金钟丹(+100) 的号，没装备时登录包里是 50 / 100。"""
        ids = [_i(renwu.get(s)) for s in STRENGTH_SLOTS]
        return (
            sum(self.attack.get(i, 0) for i in ids) + _i(renwu.get("wuqiqiangdu")),
            sum(self.defense.get(i, 0) for i in ids) + _i(renwu.get("fangjuqiangdu")),
        )


@dataclass
class Template:
    """原版对一个测试号的登录回包（帧 0 是握手响应，其余是 0x19 之后的序列）。"""

    frames: list[tuple[int, bytes, bool]]

    @classmethod
    def load(cls, path: str | Path) -> "Template":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([(f["opcode"], bytes.fromhex(f["payload"]), f["wide"]) for f in data["frames"]])

    @property
    def state_payload(self) -> bytes:
        return self.frames[1][1]


def _put(buf: bytearray, base: int, off: int, width: int, value: int) -> None:
    o = off - base
    buf[o : o + width] = (value & ((1 << (8 * width)) - 1)).to_bytes(width, "little")


def _put_str(buf: bytearray, base: int, off: int, data: bytes) -> None:
    o = off - base
    data = data[: STR_FIELD_WIDTH - 1]
    buf[o : o + STR_FIELD_WIDTH] = bytes([len(data)]) + data + bytes(STR_FIELD_WIDTH - 1 - len(data))


def inventory_records(items: list[dict], table: ItemTable, markers: list[dict] | None = None) -> list[tuple[int, int]]:
    """背包行 → 记录列表：item_id>0 且数量>0 的行，按数量展开，加一条 (0, 0)，再接 biaoji 表里 标记ID>0 的行
    （标记ID, zhuangtai 低字节），按行顺序。实测（2026-10）：每多一个标记，0x1E 里多一条 5 字节记录；建号时插的 (0, 0) 标记行不产生记录。"""
    recs: list[tuple[int, int]] = []
    for r in items:
        iid, qty = _i(r.get("item_id")), _i(r.get("shuliang"))
        if iid > 0 and qty > 0:
            recs += [(iid, table.of(iid))] * qty
    recs.append((0, 0))
    for m in markers or []:
        if _i(m.get("biaoji")) > 0:
            recs.append((_i(m.get("biaoji")), _i(m.get("zhuangtai")) & 0xFF))
    return recs


def build_state_payload(
    template: bytes,
    rows: dict,
    table: ItemTable,
    uptime_minutes: int = 0,
    big5_extra: dict[str, bytes] | None = None,
) -> bytes:
    """生成 0x1E 载荷。rows 的格式同 tools/snapshot_char.py：{'renwu':[{...}], 'char_equip':[...], ...}。"""
    renwu = (rows.get("renwu") or [{}])[0]
    ce = (rows.get("char_equip") or [{}])[0]
    jn = (rows.get("jineng") or [{}])[0]
    kf = rows.get("kf") or []

    recs = inventory_records(rows.get("item") or [], table, rows.get("biaoji"))
    head = bytearray(template[:6])
    head[0:4] = (uptime_minutes & 0xFFFFFFFF).to_bytes(4, "little")
    head[4:6] = len(recs).to_bytes(2, "little")
    body = b"".join(iid.to_bytes(4, "little") + bytes([dur & 0xFF]) for iid, dur in recs)

    tail = bytearray(template[TAIL_BASE:])
    put = lambda off, w, v: _put(tail, TAIL_BASE, off, w, v)  # noqa: E731

    put(JYID_OFF, 4, _i(renwu.get("jyid")))
    _put_str(tail, TAIL_BASE, NAME_OFF, to_big5(renwu.get("name", "") or "", big5_extra))
    _put_str(tail, TAIL_BASE, TITLE_OFF, TITLE_PREFIX + to_big5(renwu.get("nickname", "") or "", big5_extra))
    for col, off, w in RENWU_FIELDS:
        put(off, w, _i(renwu.get(col)))
    weapon, armor = table.strengths(renwu)  # 装备之和 + 数据库里的永久加成列，包里的值是现算的
    put(274, 2, weapon)
    put(276, 2, armor)
    for id_col, st_col, off in EQUIP_RECORDS:
        put(off, 4, _i(renwu.get(id_col)))
        put(off + 4, 1, _i(renwu.get(st_col)))
    for k, name in enumerate(MARTIAL_SKILLS):
        o = MARTIAL_BASE + 6 * k
        put(o, 2, _i(renwu.get(name)))
        put(o + 2, 4, _i(renwu.get(name + "exp")))
    for k, col in enumerate(CHAR_EQUIP_COLS):
        put(CHAR_EQUIP_BASE + 2 * k, 2, _i(ce.get(col)))
    for k, (lv, exp) in enumerate(LIFE_SKILLS):
        o = LIFE_BASE + 5 * k
        put(o, 1, _i(jn.get(lv)))
        if exp not in LIFE_EXP_NOT_SENT:
            put(o + 1, 4, _i(jn.get(exp)))
    kf = kf[:KF_CAPACITY]
    put(KF_COUNT_OFF, 1, len(kf))
    for i, r in enumerate(kf):
        o = KF_BASE + KF_STRIDE * i
        put(o + 1, 2, _i(r.get("kf_lvl")))
        put(o + 3, 4, _i(r.get("kf_exp")))
        put(o + 7, 2, _i(r.get("kf_id")))
    return bytes(head) + body + bytes(tail)


def build_login_stream(
    template: Template,
    rows: dict,
    table: ItemTable,
    uptime_minutes: int = 0,
    big5_extra: dict[str, bytes] | None = None,
    sponsor_king: bool = False,
    neighbours: list[dict] | None = None,
) -> list[tuple[int, bytes, bool]]:
    """生成握手响应之后的整条序列（对应 C2S 0x19）。

    sponsor_king=True 时，在 0x2F 帧之后多发一条「本服贊助王」广播（实测：总消费点数全服第一的号会有）。
    neighbours：同一张地图上已在线的其他玩家的 rows；每人在 0x31 帧之后、0x2F 帧之前多出 0x02 + 0x82 两帧。
    """
    frames = [list(f) for f in template.frames[1:]]  # 去掉握手响应
    renwu = (rows.get("renwu") or [{}])[0]
    account = (rows.get("account") or [{}])[0]

    frames[0][1] = build_state_payload(template.state_payload, rows, table, uptime_minutes, big5_extra)
    # 0x32：`6f` + 商城点数 LE32（去掉握手后的第 6 帧）
    frames[6][1] = b"\x6f" + (_i(account.get("shangchengdianshu")) & 0xFFFFFFFF).to_bytes(4, "little")
    # 储值点数 / 总赞助点数 两条公告（去掉握手后是第 7、8 帧）
    frames[7][1] = b"\x03" + _PTS_CHARGE + str(_i(account.get("shangchengdianshu"))).encode("ascii") + _PTS_SUFFIX
    frames[8][1] = b"\x03" + _PTS_TOTAL + str(_i(renwu.get("zongxiaofei"))).encode("ascii") + _PTS_SUFFIX
    # 0x08 设定位置：map/x/y 各 LE16，最后 1 字节保持模板值
    pos = bytearray(frames[9][1])
    pos[0:2] = (_i(renwu.get("map")) & 0xFFFF).to_bytes(2, "little")
    pos[2:4] = (_i(renwu.get("x")) & 0xFFFF).to_bytes(2, "little")
    pos[4:6] = (_i(renwu.get("y")) & 0xFFFF).to_bytes(2, "little")
    frames[9][1] = bytes(pos)
    # 0xA9：声望 LE32 @1，学点 LE32 @6
    tail = bytearray(frames[17][1])
    tail[1:5] = _i(renwu.get("shengwang")).to_bytes(4, "little")
    tail[6:10] = _i(renwu.get("xueshidian")).to_bytes(4, "little")
    frames[17][1] = bytes(tail)
    at = next(i for i, f in enumerate(frames) if f[0] == 0x2F)  # 0x31 之后的 0x2F 帧
    for other in neighbours or []:
        for op, p, w in neighbour_frames(other, big5_extra):
            frames.insert(at, [op, p, w])
            at += 1
    if sponsor_king:
        frames.insert(at + 1, [0x14, king_payload(renwu, big5_extra), True])
    return [(op, bytes(p), bool(w)) for op, p, w in frames]


def king_payload(renwu: dict, big5_extra: dict[str, bytes] | None = None) -> bytes:
    name = to_big5(renwu.get("name", "") or "", big5_extra)
    return _KING_PREFIX + name + _KING_MIDDLE + str(_i(renwu.get("zongxiaofei"))).encode("ascii")


# ---- 玩家出现 / 离开：别的玩家上线、下线时，在线的其他人收到的广播（实测，tools/enter_probe.py）-------------

_NOTICE_PREFIX = bytes.fromhex("08 aa b1 ae 61 a1 52")  # 0x14 子类型 08 +「玩家﹕」
_ONLINE_SUFFIX = bytes.fromhex("a4 57 bd 75 a4 46")  # 「上線了」
_OFFLINE_SUFFIX = bytes.fromhex("d6 c3 b6 7d b4 e5 c0 b8")  # 「离開游戲」


def _str17(data: bytes) -> bytes:
    data = data[: STR_FIELD_WIDTH - 1]
    return bytes([len(data)]) + data + bytes(STR_FIELD_WIDTH - 1 - len(data))


def appear_frames(
    rows: dict,
    position: tuple[int, int, int] | None = None,
    big5_extra: dict[str, bytes] | None = None,
    sponsor_king: bool = False,
) -> list[tuple[int, bytes, bool]]:
    """某玩家上线时，发给其他在线玩家的帧：0x60 名字牌、0x14 上线公告、0x02 外观/位置（、赞助王广播）。

    0x60 = jyid + 名字(17) + 称号(17) + 8 字节未解（样本全 0）。
    0x02 (96 字节) = jyid + 地图/x/y(LE16×3) + 01 + 名字(17) + 称号(17) + 6 字节 0 + 01 01 + 头盔/衣服/武器(LE16×3)，
    + 善恶值（evil_val−2000，有符号 LE16），其余补 0，末字节 0x32。
    """
    renwu = (rows.get("renwu") or [{}])[0]
    jyid = _i(renwu.get("jyid")).to_bytes(4, "little")
    name = to_big5(renwu.get("name", "") or "", big5_extra)
    title = TITLE_PREFIX + to_big5(renwu.get("nickname", "") or "", big5_extra)
    p60 = jyid + _str17(name) + _str17(title) + bytes(8)
    out = [
        (0x60, p60, False),
        (0x14, _NOTICE_PREFIX + name + _ONLINE_SUFFIX, True),
        (0x02, sight_payload(rows, position, big5_extra), False),
    ]
    if sponsor_king:
        out.append((0x14, king_payload(renwu, big5_extra), True))
    return out


def _appearance(renwu: dict) -> bytes:
    """外观：头盔、衣服、武器各 LE16，再接善恶值 `evil_val - 2000`（有符号 LE16；2000 是中性）。

    实测（克隆 123456 逐项清零）：evil_val 2400 → `90 01`(+400)，evil_val 0 → `30 f8`(−2000)，2000 → `00 00`。"""
    out = b"".join((_i(renwu.get(col)) & 0xFFFF).to_bytes(2, "little") for col in ("toukui", "yifu", "wuqi"))
    return out + ((_i(renwu.get("evil_val")) - 2000) & 0xFFFF).to_bytes(2, "little")


def sight_payload(rows: dict, position=None, big5_extra=None) -> bytes:
    """S2C 0x02（96 字节）：别人出现在我视野里时收到的角色包，里面带着他当前的位置。"""
    renwu = (rows.get("renwu") or [{}])[0]
    jyid = _i(renwu.get("jyid")).to_bytes(4, "little")
    name = to_big5(renwu.get("name", "") or "", big5_extra)
    title = TITLE_PREFIX + to_big5(renwu.get("nickname", "") or "", big5_extra)
    m, x, y = position or (_i(renwu.get("map")), _i(renwu.get("x")), _i(renwu.get("y")))
    p = bytearray(jyid + b"".join((v & 0xFFFF).to_bytes(2, "little") for v in (m, x, y)) + b"\x01")
    p += _str17(name) + _str17(title) + bytes(6) + b"\x01\x01" + _appearance(renwu)
    return bytes(p + bytes(95 - len(p)) + b"\x32")


def map_enter_frame(rows: dict, position=None) -> tuple[int, bytes, bool]:
    """S2C 0x61（54 字节）：有人进入我所在的地图。jyid + 地图/x/y + 01 + 外观，补 0，末字节 0x14。"""
    renwu = (rows.get("renwu") or [{}])[0]
    m, x, y = position or (_i(renwu.get("map")), _i(renwu.get("x")), _i(renwu.get("y")))
    p = _i(renwu.get("jyid")).to_bytes(4, "little") + b"".join((v & 0xFFFF).to_bytes(2, "little") for v in (m, x, y))
    p += b"\x01" + _appearance(renwu)
    return (0x61, p + bytes(53 - len(p)) + b"\x14", False)


def map_leave_frame(jyid: int) -> tuple[int, bytes, bool]:
    """S2C 0x62：有人离开我所在的地图。"""
    return (0x62, jyid.to_bytes(4, "little"), False)


def neighbour_frames(rows: dict, big5_extra=None) -> list[tuple[int, bytes, bool]]:
    """我进入一张地图（传送过去，或登录时就在这张图）时，对图上每个已有的人收到：0x02 角色包 + 0x82。"""
    renwu = (rows.get("renwu") or [{}])[0]
    return [(0x02, sight_payload(rows, None, big5_extra), False), (0x82, _i(renwu.get("jyid")).to_bytes(4, "little") + bytes(2), False)]


def disappear_frames(rows: dict, big5_extra: dict[str, bytes] | None = None) -> list[tuple[int, bytes, bool]]:
    """某玩家下线时发给其他在线玩家：0x05 移除实体、0x14 下线公告。"""
    renwu = (rows.get("renwu") or [{}])[0]
    name = to_big5(renwu.get("name", "") or "", big5_extra)
    return [
        (0x05, _i(renwu.get("jyid")).to_bytes(4, "little") + b"\x00", False),
        (0x14, _NOTICE_PREFIX + name + _OFFLINE_SUFFIX, True),
    ]
