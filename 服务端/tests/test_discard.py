"""丢弃(C2S 0x0D)：期望值全部来自对原版服务端的实测（2026-10，8617293 号丢 58182 / 28026 / 一批表内外物品）。"""

import struct
import unittest
from pathlib import Path

from jyserver import items as itemlogic
from jyserver.state import ItemTable

from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)
JYID = 8617293
JYID_LE = JYID.to_bytes(4, "little")


def hexs(frames):
    return [(op, p.hex(" "), w) for op, p, w in frames]


def req(item, dur=0xC8, qty=1):
    return struct.pack("<I", item) + bytes([dur]) + struct.pack("<I", qty)


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Discard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    @staticmethod
    def rows(bag=((58182, 10), (28026, 1))):
        return {
            "renwu": [{"jyid": str(JYID)}],
            "item": [{"item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in bag],
        }

    def test_drop_takes_exactly_one_and_tells_the_map(self):
        rows = self.rows()
        r = itemlogic.discard(rows, self.table, req(58182))
        self.assertEqual(r.to_self, [])  # 丢的人什么都收不到
        self.assertEqual(hexs(r.to_map), [(0x0D, "4d 7d 83 00 46 e3 00 00 c8 01 00 00 00", False)])
        self.assertEqual(rows["item"][0]["shuliang"], "9")
        self.assertEqual(r.dropped, {"item": 58182, "dur": 0xC8, "qty": 1})

    def test_the_quantity_in_the_request_is_only_echoed(self):
        for qty in (0, 5, 0xFFFF):
            rows = self.rows()
            r = itemlogic.discard(rows, self.table, req(58182, dur=0x55, qty=qty))
            self.assertEqual(rows["item"][0]["shuliang"], "9")  # 实测：不管填多少都只扣 1
            self.assertEqual(r.to_map[0][1], JYID_LE + struct.pack("<I", 58182) + b"\x55" + struct.pack("<I", qty))

    def test_last_one_removes_the_row(self):
        rows = self.rows()
        itemlogic.discard(rows, self.table, req(28026))
        self.assertEqual([r["item_id"] for r in rows["item"]], ["58182"])

    def test_not_in_bag(self):
        for item in (31011, 99999, 27003):
            rows = self.rows()
            r = itemlogic.discard(rows, self.table, req(item))
            self.assertEqual(
                hexs(r.to_self),
                [(0x1A, "64 aa ab ab 7e a4 a3 a8 ac", False), (0x05, "4d 7d 83 00 01", False)],
            )
            self.assertEqual((r.to_map, r.dropped), ([], None))

    def test_items_with_trade_flag_zero_cannot_be_dropped_even_when_unowned(self):
        self.assertEqual(len(self.table.no_trade), 34)
        for item in (28280, 11025, 12021):
            rows = self.rows(bag=[(item, 2)])
            r = itemlogic.discard(rows, self.table, req(item))
            self.assertEqual(hexs(r.to_self), [(0x1A, "64 a6 b9 aa ab ab 7e a4 a3 af e0 a5 e1 b1 f3", False)])
            self.assertEqual((rows["item"][0]["shuliang"], r.to_map), ("2", []))
        r = itemlogic.discard(self.rows(), self.table, req(28280))  # 没有也一样先说「不能丟棄」
        self.assertEqual(r.to_self[0][1].hex(" ")[:8], "64 a6 b9")

    def test_short_requests_are_ignored(self):
        rows = self.rows()
        for payload in (b"", req(58182)[:8], struct.pack("<I", 58182) + b"\xc8\x01"):
            r = itemlogic.discard(rows, self.table, payload)
            self.assertEqual((r.to_self, r.to_map, r.dropped), ([], [], None))
        self.assertEqual(rows["item"][0]["shuliang"], "10")


def rec(item, qty, dur=0xC8, sub=0x23):
    return bytes([sub]) + struct.pack("<I", item) + bytes([dur, qty])


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Recycle(unittest.TestCase):
    """C2S 0x99 子指令 0x23：期望值来自原版实测（8617293 号回收 12003 / 58182 / 28290）。"""

    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    @staticmethod
    def rows(bag=((12003, 2), (58182, 5)), money=100191):
        return {
            "renwu": [{"jyid": str(JYID), "jy_money": str(money)}],
            "item": [{"item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in bag],
        }

    def test_recycle_pays_price_times_quantity(self):
        rows = self.rows()
        r = itemlogic.recycle(rows, self.table, rec(12003, 1))
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x7B, "3c 01 ef 88 01 00", True),
                (0x1A, "64 56 49 50 aa b1 ae 61 a6 5e a6 ac a6 db b0 ca a7 e9 ba e2 aa f7 bf fa 3a 34 30 30 a8 e2 a1 54", False),
                (0x0B, "e3 2e 00 00 14 01", False),  # 耐久取自物品表（铁剑 0x14）
            ],
        )
        self.assertEqual((rows["renwu"][0]["jy_money"], rows["item"][0]["shuliang"]), ("100591", "1"))

    def test_price_one_items_and_removal_of_the_last_one(self):
        rows = self.rows(bag=[(58182, 2)], money=100595)
        r = itemlogic.recycle(rows, self.table, rec(58182, 2))
        self.assertEqual(r.to_self[0][1].hex(" "), "3c 01 f5 88 01 00")
        self.assertTrue(r.to_self[1][1].endswith(b":2" + bytes.fromhex("a8 e2 a1 54")))
        self.assertEqual((r.to_self[2][1].hex(" "), rows["item"]), ("46 e3 00 00 c8 01", []))

    def test_zero_quantity_only_acks(self):
        rows = self.rows()
        r = itemlogic.recycle(rows, self.table, rec(58182, 0))
        self.assertEqual(hexs(r.to_self), [(0x0B, "46 e3 00 00 c8 01", False)])
        self.assertEqual(rows["item"][1]["shuliang"], "5")

    def test_not_enough_or_not_owned(self):
        for item, qty in ((58182, 0xFF), (99999, 1), (31011, 1)):
            rows = self.rows()
            r = itemlogic.recycle(rows, self.table, rec(item, qty))
            self.assertEqual(
                hexs(r.to_self),
                [(0x1A, "64 aa ab ab 7e a4 a3 a8 ac", False), (0x05, "4d 7d 83 00 01", False)],
            )
            self.assertEqual(rows["renwu"][0]["jy_money"], "100191")

    def test_money_is_capped_but_message_reports_the_full_amount(self):
        rows = self.rows(money=999_999_900)
        r = itemlogic.recycle(rows, self.table, rec(12003, 1))
        self.assertEqual(rows["renwu"][0]["jy_money"], "1000000000")
        self.assertTrue(r.to_self[1][1].endswith(b":400" + bytes.fromhex("a8 e2 a1 54")))

    def test_other_subcommands_and_short_payloads_are_ignored(self):
        rows = self.rows()
        for payload in (rec(12003, 1, sub=0x22), rec(12003, 1)[:6], b""):
            self.assertEqual(itemlogic.recycle(rows, self.table, payload).to_self, [])
        self.assertEqual(rows["item"][0]["shuliang"], "2")


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Pickup(unittest.TestCase):
    """C2S 0x0F：期望值来自原版实测（W=1234567 捡 A=8617293 丢的 18072 / 58182）。"""

    @staticmethod
    def rows(bag=((58182, 3),)):
        return {
            "renwu": [{"jyid": "1234567"}],
            "item": [{"item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in bag],
        }

    @staticmethod
    def drop(item=18072, dur=0xC8, qty=1, map_id=2200):
        return {"item": item, "dur": dur, "qty": qty, "map": map_id, "x": 1, "y": 1, "owner": JYID}

    def test_pickup_gives_one_piece_and_tells_map(self):
        rows, ground = self.rows(), [self.drop()]
        r = itemlogic.pickup(rows, ground, 2200, req(18072))
        self.assertEqual(hexs(r.to_self), [(0x10, "98 46 00 00 c8 01 00 00 00", False)])
        self.assertEqual(hexs(r.to_map), [(0x11, "87 d6 12 00 98 46 00 00 c8 01 00 00 00", False)])
        self.assertEqual((ground, [(x["item_id"], x["shuliang"]) for x in rows["item"]]), ([], [("58182", "3"), ("18072", "1")]))

    def test_durability_not_compared_reply_uses_dropped_values_and_adds_exactly_one(self):
        rows, ground = self.rows(), [self.drop(58182, dur=0x55, qty=5)]
        r = itemlogic.pickup(rows, ground, 2200, req(58182, dur=0x00, qty=5))
        self.assertEqual(r.to_self[0][1].hex(" "), "46 e3 00 00 55 05 00 00 00")
        self.assertEqual(rows["item"][0]["shuliang"], "4")  # 数量 5 的那件也只 +1

    def test_quantity_mismatch_other_map_or_short_request_does_nothing(self):
        rows, ground = self.rows(), [self.drop(58182, dur=0x55, qty=5)]
        for payload, map_id in ((req(58182, qty=1), 2200), (req(58182, qty=5), 2801), (req(58182, qty=5)[:8], 2200), (req(99, qty=5), 2200)):
            r = itemlogic.pickup(rows, ground, map_id, payload)
            self.assertEqual((r.to_self, r.to_map), ([], []))
        self.assertEqual(len(ground), 1)

    def test_oldest_matching_drop_goes_first(self):
        ground = [self.drop(dur=0x11), self.drop(dur=0x22)]
        r = itemlogic.pickup(self.rows(), ground, 2200, req(18072))
        self.assertEqual(r.to_self[0][1][4], 0x11)
        self.assertEqual([g["dur"] for g in ground], [0x22])


if __name__ == "__main__":
    unittest.main()
