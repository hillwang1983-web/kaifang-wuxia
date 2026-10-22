"""商店：期望值全部来自对原版服务端的实测（tools/shop_probe.py）。物品表和商人表要读原版 data 目录，找不到就跳过。"""

import struct
import unittest
from pathlib import Path

from jyserver import shop
from jyserver.state import ItemTable

from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)


def hexs(frames):
    return [(op, p.hex(" "), w) for op, p, w in frames]


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Shop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)
        cls.merchants = shop.Merchants.load(DATA_DIR)

    @staticmethod
    def rows(money=100000, items=()):
        return {"renwu": [{"jyid": "9999031", "jy_money": str(money)}],
                "item": [{"item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in items]}

    def test_open_known_shop(self):
        r = shop.open_shop(self.merchants, struct.pack("<H", 53))  # 京城药店
        self.assertEqual([op for op, _, _ in r.to_self], [0x1A, 0x09, 0x1B, 0x1B])
        self.assertEqual(
            r.to_self[1][1].hex(" "),
            "00 7a 6d 00 00 e8 03 00 00 65 6d 00 00 e8 03 00 00 68 6d 00 00 e8 03 00 00 7b 6d 00 00 e8 03 00 00 90 6d 00 00 e8 03 00 00 4b 71 00 00 e8 03 00 00",
        )
        self.assertTrue(r.to_self[1][2])
        self.assertEqual(r.to_self[2][1].hex(" "), "1f 79 00 00 32 02 00 00 00")
        self.assertEqual(r.to_self[3][1].hex(" "), "c9 af 00 00 3c 0c 00 00 00")
        self.assertEqual(r.to_self[0][1].decode("big5").strip("d"), "批量購買，需重登后顯示﹗")

    def test_open_unknown_shop(self):
        r = shop.open_shop(self.merchants, struct.pack("<H", 9999))
        self.assertEqual(
            hexs(r.to_self),
            [(0x1A, "64 a6 b9 b0 d3 a4 48 a8 53 bf fd a4 4a a1 41 b3 71 aa be 47 4d a1 54 39 39 39 39", False), (0x1B, "", False)],
        )

    def test_batch_buy_charges_by_quantity_but_adds_one_of_each(self):
        rows = self.rows()
        payload = struct.pack("<IIII", 28026, 3, 28005, 2)
        r = shop.buy(rows, self.table, payload)
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x7B, "3c 01 9b 86 01 00", True),
                (0x0A, "01 7a 6d 00 00 9d 86 01 00 01 65 6d 00 00 9b 86 01 00", True),
                (0x1B, "7a 6d 00 c8 00 00 00 00 65 6d 00 c8 00 00 00 00", True),
                (0x1A, "64 c1 ca b6 52 a6 a8 a5 5c a1 54", False),
            ],
        )
        self.assertEqual(rows["renwu"][0]["jy_money"], "99995")
        self.assertEqual([(r_["item_id"], r_["shuliang"]) for r_ in rows["item"]], [("28026", "1"), ("28005", "1")])  # 原版实测：每种只加 1 件

    def test_buying_again_merges_into_the_existing_stack(self):
        rows = self.rows(items=[(28026, 1)])
        shop.buy(rows, self.table, struct.pack("<II", 28026, 1))
        self.assertEqual([(r["item_id"], r["shuliang"]) for r in rows["item"]], [("28026", "2")])

    def test_zero_quantity_is_free_but_still_adds_one(self):
        rows = self.rows()
        r = shop.buy(rows, self.table, struct.pack("<II", 12003, 0))
        self.assertEqual(r.to_self[0][1].hex(" "), "3c 01 a0 86 01 00")
        self.assertEqual(r.to_self[2][1].hex(" "), "e3 2e 00 14 00 00 00 00")  # 耐久字节 0x14
        self.assertEqual(rows["item"][0]["shuliang"], "1")

    def test_not_for_sale_item_is_refused_and_nothing_changes(self):
        rows = self.rows()
        r = shop.buy(rows, self.table, struct.pack("<IIII", 28026, 1, 25091, 1))  # 神威麒麟盔：商品列 = 0
        self.assertEqual(hexs(r.to_self), [(0x1A, "64 a6 b3 a4 a3 a4 b9 b3 5c c1 ca b6 52 b0 d3 ab 7e a1 41 b8 d3 a6 e6 ac b0 a4 77 b8 67 b0 4f bf fd a1 54", False)])
        self.assertEqual((rows["renwu"][0]["jy_money"], rows["item"]), ("100000", []))

    def test_listed_by_a_merchant_but_flag_zero_is_still_refused(self):
        rows = self.rows()
        r = shop.buy(rows, self.table, struct.pack("<II", 44107, 1))  # 商人表里有，但商品列 = 0
        self.assertEqual(r.to_self[0][0], 0x1A)
        self.assertEqual(len(r.to_self), 1)

    def test_not_enough_money(self):
        rows = self.rows(money=10)
        r = shop.buy(rows, self.table, struct.pack("<II", 12003, 11))
        self.assertEqual(hexs(r.to_self), [(0x1A, "64 bf fa a4 a3 b0 f7 a1 54", False), (0x1B, "", False)])
        self.assertEqual((rows["renwu"][0]["jy_money"], rows["item"]), ("10", []))

    def test_price_is_one_per_unit_whatever_the_tables_say(self):
        for item in (11007, 44101, 44051, 40304, 44035):  # 表里价格 3000 / 10 / 6 / 1 / 10000
            rows = self.rows()
            shop.buy(rows, self.table, struct.pack("<II", item, 5))
            self.assertEqual(rows["renwu"][0]["jy_money"], "99995", item)

    def test_bag_limit(self):
        rows = self.rows(items=[(58182, 499)])
        r = shop.buy(rows, self.table, struct.pack("<II", 28026, 1))
        self.assertEqual(r.to_self[0][0], 0x1A)
        self.assertEqual(rows["renwu"][0]["jy_money"], "100000")


if __name__ == "__main__":
    unittest.main()
