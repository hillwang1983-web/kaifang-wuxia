"""装备与物品：穿装备(C2S 0x15)、脱装备(0x16)、使用物品(0x0B)。

全部是纯函数：入参是角色的数据库行（rows，会被原地修改）、物品表，返回要发的帧；网络层在 server.py。
行为依据 2026-10 对本机原版服务端的实测（tools/equip_probe.py、use_probe.py、multi_probe.py）和
0x72e01f 之外的处理函数输出对照，细节与未解项见 docs/装备与物品.md。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import ItemTable, to_big5

Frame = tuple[int, bytes, bool]  # (opcode, 载荷, 是否长帧)

# 装备槽位号 -> renwu 列。槽位 5 不用（原版对它不回包）。
EQUIP_SLOTS: dict[int, str] = {
    1: "toukui", 2: "xianglian", 3: "yifu", 4: "pifeng", 6: "wuqi", 7: "huwan", 8: "jiezhi", 9: "xiezi",
}

# 0x7B 属性更新的子类型 -> 含义（实测）
SUB_JING, SUB_XUE, SUB_SHEN, SUB_NEI = 0x16, 0x18, 0x1A, 0x1B
SUB_WEAPON_STRENGTH, SUB_ARMOR_STRENGTH = 0x2F, 0x30

# 药品效果列 -> (renwu 当前值列, 上限列或固定上限, 0x7B 子类型)。
# 顺序就是原版发 0x7B 的顺序（实测：精 神 气 内 → 饮水 饱食 → 学点）；表外的列（毒、酒醉、永久攻、
# 临时攻防等）原版会消耗物品并回 0x0B 确认，但这里还没实现它们的效果。
EFFECTS: list[tuple[str, str, str | int | None, int]] = [
    ("精", "dangqianjing", "zuidajing", SUB_JING),
    ("神", "dangqianshen", "zuidashen", SUB_SHEN),
    ("气", "dangqianxue", "zuidaxue", SUB_XUE),
    ("内", "dangqiannei", "zuidanei", SUB_NEI),
    ("饮水", "water_val", 100, 0x36),
    ("饱食", "diet_val", 100, 0x34),
    ("学点", "study_count", None, 0x28),
    ("臂力", "str", None, 0x1E),
    ("胆识", "crg", None, 0x1F),
    ("悟性", "wint", None, 0x20),
    ("富源", "luk", None, 0x21),
    ("定力", "dex", None, 0x22),
    ("机敏", "agi", None, 0x23),
    ("根骨", "vit", None, 0x24),
    ("名声", "fame_val", None, 0x3D),
    ("实战", "combat_exp", None, 0x2B),
    ("历练", "exp_val", None, 0x44),
]
# 带这些列的药（加最大精 / 神 / 内）原版会静默不处理：不回包、不消耗。实测：即使把对应上限调低也一样。
# 只有「max气」被实现：zuidaxue += 值，先回 0x0B 确认，再回 0x7B 17 = 新的最大气血。
SILENT_COLUMNS = ("max精", "max神", "max内")
SUB_MAX_XUE = 0x17

# 永久攻 / 永久防：累加进 renwu.wuqiqiangdu / fangjuqiangdu（下线才落库），登录包里的武器 / 防具强度 = 装备之和 + 这两列。
# 只回 0x0B 确认，没有 0x7B。
PERMANENT = {"永久攻": "wuqiqiangdu", "永久防": "fangjuqiangdu"}

# 只含这些「状态」列的药（实测：刀伤药 = 流血 −20）原版静默不处理。带精气神等可见效果的药，状态列本身不产生任何包——
# 状态（毒、酒醉、流血…）只存在服务端内存里，没有 0x7B，目前也没有战斗逻辑去用它，所以这里不记录。
INERT_COLUMNS = {"毒", "酒醉", "流血", "内伤", "麻痹", "混乱", "走火入魔", "情花毒", "赤练毒", "气血失调", "杀气"}

# 没有效果列的特殊药（有专门逻辑）：物品ID -> 确认之后追加的帧。数量照常 −1。其余没有效果列的药（金娃娃鱼、新药1…）原版静默不处理。
_BUFF_TEXT_28170 = bytes.fromhex("64 a4 ba a4 4f a4 a3 b4 ee a4 a6 ae c4 aa 47 b6 7d a9 6c a1 41 a4 55 bd 75 a5 a2 ae c4 a1 54")  # 內力不減丹效果開始，下線失效﹗
_BUFF_TEXT_28255 = bytes.fromhex("64 af ab a6 e6 a4 a6 ae c4 aa 47 b6 7d a9 6c a1 41 a4 55 bd 75 a5 a2 ae c4 a1 54")  # 神行丹效果開始，下線失效﹗
_BUFF_TEXT_28388 = bytes.fromhex("64 c5 71 ae 70 a6 db ad d7 a5 5b ad bf a4 f4 ae c4 aa 47 b6 7d a9 6c a1 41 ad ab b5 6e a5 a2 ae c4 a1 54")  # 巔峰自修加倍水效果開始，重登失效﹗
SPECIAL_ITEMS = {28170: "text:28170", 28172: None, 28255: "shenxing", 28388: "text:28388"}

_CHEAT_MID = bytes.fromhex("b9 c1 b8 d5 a8 ea b8 cb b3 c6 a1 54")  # 「嘗試刷裝備﹗」
_NO_ITEM_MSG = bytes.fromhex("64 aa ab ab 7e a4 a3 a8 ac")  # 0x1A: 子类型 64 +「物品不足」
_NO_ITEM_NOTICE = bytes.fromhex("08 ad 49 a5 5d a8 53 a6 b3 a6 b9 aa ab ab 7e")  # 0x14: 08 +「背包沒有此物品」
_RECYCLE_PREFIX = to_big5("VIP玩家回收自动折算金钱:")  # 0x1A 子类型 64 之后的文字（「VIP玩家回收自動折算金錢:」）
_RECYCLE_SUFFIX = bytes.fromhex("a8 e2 a1 54")  # 「兩﹗」
_NO_DISCARD_MSG = bytes.fromhex("64 a6 b9 aa ab ab 7e a4 a3 af e0 a5 e1 b1 f3")  # 0x1A: 64 +「此物品不能丟棄」


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_all: list[Frame] = field(default_factory=list)  # 发给所有在线玩家（含自己）
    to_map: list[Frame] = field(default_factory=list)  # 发给同一张地图上的其他玩家（不含自己）
    dropped: dict | None = None  # 丢弃成功时掉在地上的东西：{"item", "dur", "qty"}（位置由网络层补）


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _sub(sub: int, value: int) -> Frame:
    return (0x7B, bytes([sub, 0x01]) + (value & 0xFFFFFFFF).to_bytes(4, "little"), True)


def _strength_frames(renwu: dict, table: ItemTable, before: tuple[int, int]) -> list[Frame]:
    """装备变化后，武器强度、防具强度哪个变了就发哪个（实测：先 0x2F 后 0x30，没变的不发）。"""
    after = table.strengths(renwu)
    out = []
    if after[0] != before[0]:
        out.append(_sub(SUB_WEAPON_STRENGTH, after[0]))
    if after[1] != before[1]:
        out.append(_sub(SUB_ARMOR_STRENGTH, after[1]))
    return out


def owned_row(rows: dict, item_id: int) -> dict | None:
    for r in rows.get("item") or []:
        if _i(r.get("item_id")) == item_id and _i(r.get("shuliang")) > 0:
            return r
    return None


def equip(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x15：槽位(1) 物品ID(LE32) 状态(1)。

    实测规则：背包里没有这件物品 → 向全服广播 0x14(0e)「<名字>嘗試刷裝備﹗<物品名>」，不穿；
    槽位不是 1/2/3/4/6/7/8/9、或槽位上已有装备 → 静默忽略；不检查物品类型和槽位是否匹配。
    成功：回 0x17 = jyid + 槽位 + 物品ID + 状态，再按需回 0x7B 武器/防具强度。装备不会从背包扣掉。
    """
    res = Result()
    if len(payload) < 6:
        return res
    slot, item_id, state = payload[0], int.from_bytes(payload[1:5], "little"), payload[5]
    renwu = rows["renwu"][0]
    if owned_row(rows, item_id) is None:
        name = to_big5(renwu.get("name", "") or "")
        item_name = to_big5(table.names.get(item_id, ""))
        res.to_all.append((0x14, b"\x0e" + name + _CHEAT_MID + item_name, True))
        return res
    col = EQUIP_SLOTS.get(slot)
    if col is None or _i(renwu.get(col)) != 0:
        return res
    before = table.strengths(renwu)
    renwu[col] = str(item_id)
    renwu[col + "zhuangtai"] = str(state)
    jyid = _i(renwu.get("jyid")).to_bytes(4, "little")
    res.to_self.append((0x17, jyid + bytes([slot]) + item_id.to_bytes(4, "little") + bytes([state]), False))
    res.to_self += _strength_frames(renwu, table, before)
    return res


def unequip(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x16：槽位(1)。有效槽位一律回 0x18 = jyid + 槽位（槽位本来是空的也回），再按需回 0x7B 强度。"""
    res = Result()
    if len(payload) < 1:
        return res
    slot = payload[0]
    col = EQUIP_SLOTS.get(slot)
    if col is None:
        return res
    renwu = rows["renwu"][0]
    before = table.strengths(renwu)
    renwu[col] = "0"
    renwu[col + "zhuangtai"] = "0"
    res.to_self.append((0x18, _i(renwu.get("jyid")).to_bytes(4, "little") + bytes([slot]), False))
    res.to_self += _strength_frames(renwu, table, before)
    return res


def use_item(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x0B：物品ID(LE32)（后面的字节原版不看）。

    背包里没有：回 0x1A「物品不足」、0x05(jyid+01)、0x14(08)「背包沒有此物品」。
    有：数量 −1；按 药品.csv 的效果列改角色并发 0x7B（顺序见 EFFECTS，取值被上限截断，列不为 0 就发，
    哪怕值没变）；最后回 0x0B = 物品ID + 耐久字节 + 01。
    其余列：永久攻 / 永久防 累加进 wuqiqiangdu / fangjuqiangdu；max气 累加进 zuidaxue，确认之后再发 0x7B 17；
    临时攻 / 防只回确认；毒、酒醉等状态列不产生任何包。静默不处理（不回包、不消耗）的情况：带 max精/max神/max内、
    只含状态列、不在药品表里、表里没有效果列又不是已知特殊药。详见 docs/药品效果.md。
    """
    res = Result()
    if len(payload) < 4:
        return res
    item_id = int.from_bytes(payload[:4], "little")
    renwu = rows["renwu"][0]
    row = owned_row(rows, item_id)
    if row is None:
        res.to_self.append((0x1A, _NO_ITEM_MSG, False))
        res.to_self.append((0x05, _i(renwu.get("jyid")).to_bytes(4, "little") + b"\x01", False))
        res.to_self.append((0x14, _NO_ITEM_NOTICE, True))
        return res
    effects = table.effects.get(item_id)
    if effects is None and item_id in SPECIAL_ITEMS:
        effects = {}  # 28388 之类不在药品表里的特殊物品
    if effects is None or any(effects.get(c) for c in SILENT_COLUMNS):
        return res
    if not effects and item_id not in SPECIAL_ITEMS:
        return res
    if effects and all(c in INERT_COLUMNS for c in effects):
        return res
    row["shuliang"] = str(_i(row["shuliang"]) - 1)
    for col, cur_col, cap, sub in EFFECTS:
        delta = effects.get(col)
        if not delta:
            continue
        limit = _i(renwu.get(cap)) if isinstance(cap, str) else cap
        value = _i(renwu.get(cur_col)) + delta
        if limit is not None:
            value = min(value, limit)
        value = max(value, 0)
        renwu[cur_col] = str(value)
        res.to_self.append(_sub(sub, value))
    for col, target in PERMANENT.items():
        if effects.get(col):
            renwu[target] = str(_i(renwu.get(target)) + effects[col])
    res.to_self.append((0x0B, item_id.to_bytes(4, "little") + bytes([table.of(item_id), 0x01]), False))
    if effects.get("max气"):
        renwu["zuidaxue"] = str(_i(renwu.get("zuidaxue")) + effects["max气"])
        res.to_self.append(_sub(SUB_MAX_XUE, _i(renwu["zuidaxue"])))
    special = SPECIAL_ITEMS.get(item_id)
    if special == "shenxing":
        res.to_self.append((0x99, b"\x05" + _i(renwu.get("jyid")).to_bytes(4, "little") + b"\xff", False))
    if special in ("text:28170", "shenxing", "text:28388"):
        text = {"text:28170": _BUFF_TEXT_28170, "shenxing": _BUFF_TEXT_28255, "text:28388": _BUFF_TEXT_28388}[special]
        res.to_self.append((0x1A, text, False))
    return res


def discard(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x0D 丢弃：物品ID(LE32) 耐久(1) 数量(LE32)，载荷至少 9 字节（短了原版静默忽略）。

    实测（2026-10，8617293 号，tools/raw_probe.py）：
    - 物品的「交易」列 = 0（装备数据.csv，34 件，如 11025 / 12021 / 28280）→ 回 0x1A「此物品不能丟棄」，什么都不动；
    - 背包里一件都没有 → 回 0x1A「物品不足」+ 0x05(jyid+01)，没有 0x14；
    - 否则**背包只扣 1 件，不管载荷里的数量**（发 0 / 5 / 65535 都是扣 1），掉在地上的东西记下载荷里的耐久字节和 4 字节数量；
      丢的人自己什么都收不到，同一张地图上的其他玩家收到 0x0D（短帧）= 丢的人 jyid + 物品ID + 耐久字节 + 数量(LE32)（照抄载荷）。
    原版先查「交易」列再查背包；不在物品表里的物品不受「交易」列限制。
    """
    res = Result()
    if len(payload) < 9:
        return res
    item_id = int.from_bytes(payload[:4], "little")
    renwu = rows["renwu"][0]
    jyid = _i(renwu.get("jyid")).to_bytes(4, "little")
    if item_id in table.no_trade:
        res.to_self.append((0x1A, _NO_DISCARD_MSG, False))
        return res
    row = owned_row(rows, item_id)
    if row is None:
        res.to_self.append((0x1A, _NO_ITEM_MSG, False))
        res.to_self.append((0x05, jyid + b"\x01", False))
        return res
    left = _i(row["shuliang"]) - 1
    if left > 0:
        row["shuliang"] = str(left)
    else:
        rows["item"].remove(row)  # 用光整行删掉（和钱庄一样）
    res.dropped = {"item": item_id, "dur": payload[4], "qty": int.from_bytes(payload[5:9], "little")}
    res.to_map.append((0x0D, jyid + payload[:9], False))
    return res


MONEY_CAP = 1_000_000_000


def recycle(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x99 子指令 0x23「VIP 玩家回收」：子类型 23(1) 物品ID(LE32) 耐久(1，不看) 数量(1)，载荷至少 7 字节。

    实测（2026-10，8617293 号）：背包里那一格的数量 < 请求数量（含没有该物品）→ 回 0x1A「物品不足」+ 0x05(jyid+01)，不动；
    否则背包扣掉这个数量（用光整行删掉），并按 装备数据.csv「价格」× 数量 给钱（上限 10 亿，表里没有的物品价格 0）：
    价格 > 0 时先回 0x7B 3C = 新的金钱，再回 0x1A 64 +「VIP玩家回收自動折算金錢:<价格×数量>兩﹗」（文字里是折算额，不是封顶后的实际增加）；
    不管价格是否为 0，最后回 0x0B = 物品ID + 耐久（取物品表）+ 01。数量 0 只回 0x0B。
    原版还有个条件 `玩家+0x484 > 4`（只在给钱时检查）：+0x484 是 VIP 等级，恒为 7，所以恒成立。
    """
    res = Result()
    if len(payload) < 7 or payload[0] != 0x23:
        return res
    item_id = int.from_bytes(payload[1:5], "little")
    qty = payload[6]
    renwu = rows["renwu"][0]
    row = next((r for r in rows.get("item") or [] if _i(r.get("item_id")) == item_id), None)
    if row is None or _i(row.get("shuliang")) < qty:
        res.to_self.append((0x1A, _NO_ITEM_MSG, False))
        res.to_self.append((0x05, _i(renwu.get("jyid")).to_bytes(4, "little") + b"\x01", False))
        return res
    gain = table.price.get(item_id, 0) * qty
    if gain > 0:
        money = min(_i(renwu.get("jy_money")) + gain, MONEY_CAP)
        renwu["jy_money"] = str(money)
        res.to_self.append(_sub(0x3C, money))
        res.to_self.append((0x1A, b"\x64" + _RECYCLE_PREFIX + str(gain).encode() + _RECYCLE_SUFFIX, False))
    left = _i(row["shuliang"]) - qty
    if left > 0:
        row["shuliang"] = str(left)
    else:
        rows["item"].remove(row)
    res.to_self.append((0x0B, item_id.to_bytes(4, "little") + bytes([table.of(item_id), 0x01]), False))
    return res


def pickup(rows: dict, ground: list[dict], map_id: int, payload: bytes) -> Result:
    """C2S 0x0F 拾取：物品ID(LE32) 耐久(1，不比较) 数量(LE32)，至少 9 字节。

    在**同一张地图**的地上物品里找第一件（丢得最早的）物品ID 和数量都相等的——位置、谁丢的都不看，丢的人自己也能捡；耐久字节不参与匹配。
    找到：地上记录删掉，背包 +1 件（不管那件的数量是几），自己收 0x10 = 物品ID + 耐久 + 数量（耐久、数量取地上记录里丢弃时记下的），
    同图其他玩家收 0x11 = 捡的人 jyid + 同样 9 字节。找不到：什么都不回。
    原版另有一份「2800 号地图专用」的掉落表（DAT_00dd85ac），玩家在 2800 图上捡东西时也会查，这里没做。
    """
    res = Result()
    if len(payload) < 9:
        return res
    item_id = int.from_bytes(payload[:4], "little")
    qty = int.from_bytes(payload[5:9], "little")
    hit = next((g for g in ground if g["map"] == map_id and g["item"] == item_id and g["qty"] == qty), None)
    if hit is None:
        return res
    ground.remove(hit)
    renwu = rows["renwu"][0]
    for r in rows.setdefault("item", []):
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200:
            r["shuliang"] = str(_i(r.get("shuliang")) + 1)
            break
    else:
        rows["item"].append({"jyid": str(renwu.get("jyid")), "item_id": str(item_id), "shuliang": "1", "state": "200"})
    body = item_id.to_bytes(4, "little") + bytes([hit["dur"]]) + hit["qty"].to_bytes(4, "little")
    res.to_self.append((0x10, body, False))
    res.to_map.append((0x11, _i(renwu.get("jyid")).to_bytes(4, "little") + body, False))
    return res
