"""商店：开店（C2S 0x09）、购买（C2S 0x0A）。

全部是纯函数，行为依据 2026-10 对本机原版服务端的实测（tools/shop_probe.py）和 0x5ff37d 的反编译。要点：

  * 开店 0x09：载荷 = 商人 ID（LE16，对应 data/商人.csv 的 ID 列）。认识的商人回
        0x1A「批量購買，需重登后顯示﹗」、0x09（长帧）= 00 + 每件商品 [物品ID LE32 + 商人表里的数 LE32]、
        再两条固定的 0x1B；不认识的回 0x1A「此商人沒錄入，通知GM﹗<商人ID十进制>」+ 空的 0x1B。
  * 购买 0x0A：载荷 = 若干条 8 字节记录 [物品ID LE32 + 数量 LE32]（批量购买）。**不检查开过哪家店**，也不检查商人卖不卖这件，
    只要这件物品在 装备数据.csv 里「商品」列 = 1 就能买。
  * 单价恒为 1，按「数量」扣金钱（实测 12 种物品，不管商人表和物品表里写多少都是 1）；**背包却只加 1 件**——不管记录里写几件
    （包括 0 件）。这是原版的行为（界面上也提示「批量购买，需重登后显示」），默认照做，见 FAITHFUL_SINGLE_UNIT。
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .state import ItemTable

log = logging.getLogger("jyserver.shop")

Frame = tuple[int, bytes, bool]

FAITHFUL_SINGLE_UNIT = True  # True：每条记录只往背包加 1 件（原版实测）；False：按数量加
UNIT_PRICE = 1  # 实测：每件 1，和商人表、物品表里的价格无关
BAG_LIMIT = 499  # 原版代码里的背包上限（0x5ff37d：身上总数超过 499）

_OPEN_NOTICE = bytes.fromhex("64 a7 e5 b6 71 c1 ca b6 52 a1 41 bb dd ad ab b5 6e a6 5a c5 e3 a5 dc a1 54")  # 批量購買，需重登后顯示﹗
_UNKNOWN_SHOP = bytes.fromhex("64 a6 b9 b0 d3 a4 48 a8 53 bf fd a4 4a a1 41 b3 71 aa be 47 4d a1 54")  # 此商人沒錄入，通知GM﹗
_OPEN_MARKERS = [
    (0x1B, bytes.fromhex("1f 79 00 00 32 02 00 00 00"), True),
    (0x1B, bytes.fromhex("c9 af 00 00 3c 0c 00 00 00"), True),
]
_NOT_ALLOWED = bytes.fromhex("64 a6 b3 a4 a3 a4 b9 b3 5c c1 ca b6 52 b0 d3 ab 7e a1 41 b8 d3 a6 e6 ac b0 a4 77 b8 67 b0 4f bf fd a1 54")  # 有不允許購買商品，該行為已經記錄﹗
_NO_MONEY = bytes.fromhex("64 bf fa a4 a3 b0 f7 a1 54")  # 錢不夠﹗
_BOUGHT = bytes.fromhex("64 c1 ca b6 52 a6 a8 a5 5c a1 54")  # 購買成功﹗
_BAG_FULL = "身上總數超過499".encode("big5", errors="replace")

SUB_MONEY = 0x3C


@dataclass
class Merchants:
    """data/商人.csv：商人 ID -> [(物品ID, 表里的数)]。"""

    shops: dict[int, list[tuple[int, int]]] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: str | Path) -> "Merchants":
        p = Path(data_dir) / "商人.csv"
        shops: dict[int, list[tuple[int, int]]] = {}
        if p.exists():
            text = p.read_bytes().decode("gbk", errors="replace")
            for row in csv.reader(io.StringIO(text)):
                if len(row) >= 3 and row[0].strip().isdigit():
                    goods = []
                    for part in row[2].split(";"):
                        a, _, b = part.partition(":")
                        if a.strip().isdigit():
                            goods.append((int(a), int(b) if b.strip().isdigit() else 0))
                    shops[int(row[0])] = goods
        return cls(shops)


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def open_shop(merchants: Merchants, payload: bytes) -> Result:
    """C2S 0x09：商人 ID LE16。"""
    res = Result()
    if len(payload) < 2:
        return res
    npc = int.from_bytes(payload[:2], "little")
    goods = merchants.shops.get(npc)
    if goods is None:
        res.to_self.append((0x1A, _UNKNOWN_SHOP + str(npc).encode("ascii"), False))
        res.to_self.append((0x1B, b"", False))
        return res
    res.to_self.append((0x1A, _OPEN_NOTICE, False))
    res.to_self.append((0x09, b"\x00" + b"".join(i.to_bytes(4, "little") + v.to_bytes(4, "little") for i, v in goods), True))
    res.to_self += _OPEN_MARKERS
    return res


def bag_count(rows: dict) -> int:
    """背包里的件数：每行 shuliang 件之和（和 0x1E 里按数量展开的记录数一致）。"""
    return sum(_i(r.get("shuliang")) for r in rows.get("item") or [] if _i(r.get("item_id")) > 0)


def _add_to_bag(rows: dict, jyid: str, item_id: int, qty: int) -> None:
    for r in rows.setdefault("item", []):
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200:
            r["shuliang"] = str(_i(r.get("shuliang")) + qty)
            return
    rows["item"].append({"jyid": jyid, "item_id": str(item_id), "shuliang": str(qty), "state": "200"})


def buy(rows: dict, table: ItemTable, payload: bytes, *, account_label: str = "") -> Result:
    """C2S 0x0A：若干条 [物品ID LE32 + 数量 LE32]。"""
    res = Result()
    records = [
        (int.from_bytes(payload[k : k + 4], "little"), int.from_bytes(payload[k + 4 : k + 8], "little"))
        for k in range(0, len(payload) - len(payload) % 8, 8)
    ]
    if not records:
        return res
    renwu = rows["renwu"][0]
    if any(i not in table.sellable for i, _ in records):
        bad = [i for i, _ in records if i not in table.sellable]
        log.warning("%s 刷购买：%s", account_label or renwu.get("jyid"), bad[0])
        res.to_self.append((0x1A, _NOT_ALLOWED, False))
        return res
    money = _i(renwu.get("jy_money"))
    cost = sum(q * UNIT_PRICE for _, q in records)
    if cost > money:
        res.to_self.append((0x1A, _NO_MONEY, False))
        res.to_self.append((0x1B, b"", False))
        return res
    if bag_count(rows) + len(records) > BAG_LIMIT:
        res.to_self.append((0x1A, b"\x64" + _BAG_FULL, False))
        return res
    jyid = str(renwu.get("jyid"))
    bought, listing, balance = [], [], money
    for item_id, qty in records:
        balance -= qty * UNIT_PRICE
        listing.append(b"\x01" + item_id.to_bytes(4, "little") + balance.to_bytes(4, "little"))
        bought.append(item_id.to_bytes(4, "little")[:3] + bytes([table.of(item_id)]) + bytes(4))
        _add_to_bag(rows, jyid, item_id, 1 if FAITHFUL_SINGLE_UNIT else qty)
    renwu["jy_money"] = str(balance)
    res.to_self.append((0x7B, bytes([SUB_MONEY, 0x01]) + balance.to_bytes(4, "little"), True))
    res.to_self.append((0x0A, b"".join(listing), True))
    res.to_self.append((0x1B, b"".join(bought), True))
    res.to_self.append((0x1A, _BOUGHT, False))
    return res
