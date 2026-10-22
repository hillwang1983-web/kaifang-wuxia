"""钱庄：期望值全部来自对原版服务端的实测（2026-10，8617293 号存 / 取 28026、28005）。"""

import struct
import unittest
from pathlib import Path

from jyserver import bank
from jyserver.state import ItemTable

from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)


def hexs(frames):
    return [(op, p.hex(" "), w) for op, p, w in frames]


def dep(i, q, d=0xC8):
    return b"\x00" + struct.pack("<I", i) + bytes([d]) + struct.pack("<H", q)


def wd(i, q, d=0xC8):
    return b"\x01" + struct.pack("<I", i) + bytes([d]) + struct.pack("<H", q)


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Bank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    @staticmethod
    def rows(bag=((28026, 4), (28005, 1)), stored=()):
        return {
            "renwu": [{"jyid": "8617293", "jy_money": "99791"}],
            "item": [{"item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in bag],
            "qianzhuang": [{"wupin": str(i), "shuliang": str(q)} for i, q in stored],
        }

    ACK = [(0x0B, "8f bb 00 00 c8 01", False), (0x77, "8f bb 00 00 c8 01", False)]

    def test_empty_bank(self):
        self.assertEqual(hexs(bank.open_bank(self.rows(), self.table).to_self), [(0x28, "00 00 00 00", True)])

    def test_deposit_moves_items_and_lists_newest_first(self):
        rows = self.rows()
        r = bank.transfer(rows, self.table, dep(28026, 3))
        self.assertEqual(hexs(r.to_self), self.ACK + [(0x27, "00 7a 6d 00 00 03 00 cf 85 01 00 c8", False)])
        bank.transfer(rows, self.table, dep(28005, 1))
        self.assertEqual(
            hexs(bank.open_bank(rows, self.table).to_self),
            [(0x28, "00 00 00 00 65 6d 00 00 c8 01 00 7a 6d 00 00 c8 03 00", True)],
        )
        self.assertEqual([(r_["item_id"], r_["shuliang"]) for r_ in rows["item"]], [("28026", "1")])  # 28005 用光，整行删掉
        self.assertEqual([(r_["wupin"], r_["shuliang"]) for r_ in rows["qianzhuang"]], [("28026", "3"), ("28005", "1")])

    def test_withdraw_refreshes_listing(self):
        rows = self.rows(bag=[(28026, 1)], stored=[(28026, 3), (28005, 1)])
        r = bank.transfer(rows, self.table, wd(28026, 2))
        self.assertEqual(
            hexs(r.to_self),
            self.ACK
            + [
                (0x27, "01 7a 6d 00 00 02 00 ee dc 00 00", False),
                (0x28, "00 00 00 00 65 6d 00 00 c8 01 00 7a 6d 00 00 c8 01 00", True),
            ],
        )
        self.assertEqual(rows["item"][0]["shuliang"], "3")

    def test_withdraw_everything_removes_the_entry(self):
        rows = self.rows(bag=[], stored=[(28026, 1)])
        r = bank.transfer(rows, self.table, wd(28026, 1))
        self.assertEqual(r.to_self[-1][1].hex(" "), "00 00 00 00")
        self.assertEqual((rows["qianzhuang"], rows["item"][0]["item_id"]), ([], "28026"))

    def test_not_enough_to_deposit(self):
        for item, qty in ((28026, 99), (12345, 1), (0, 1)):
            rows = self.rows()
            r = bank.transfer(rows, self.table, dep(item, qty))
            self.assertEqual(
                hexs(r.to_self),
                [(0x1A, "64 aa ab ab 7e bc c6 b6 71 a4 a3 a8 ac a1 41 bd d0 ad ab b5 6e a1 54", False), (0x77, "8f bb 00 00 c8 01", False)],
            )
            self.assertEqual(rows["qianzhuang"], [])

    def test_not_enough_to_withdraw(self):
        for item, qty in ((28026, 5), (40000, 1), (0, 500)):
            rows = self.rows(stored=[(28026, 1)])
            r = bank.transfer(rows, self.table, wd(item, qty))
            self.assertEqual(
                hexs(r.to_self),
                [(0x0B, "8f bb 00 00 c8 01", False), (0x1A, "64 bc c6 b6 71 a4 a3 a8 ac", False), (0x77, "8f bb 00 00 c8 01", False)],
            )

    def test_zero_quantity_succeeds_without_changing_anything(self):
        rows = self.rows()
        r = bank.transfer(rows, self.table, dep(28026, 0))
        self.assertEqual(r.to_self[-1][1].hex(" "), "00 7a 6d 00 00 00 00 cf 85 01 00 c8")
        self.assertEqual((rows["qianzhuang"], rows["item"][0]["shuliang"]), ([], "4"))

    def test_durability_byte_in_the_request_is_ignored(self):
        rows = self.rows()
        r = bank.transfer(rows, self.table, dep(28026, 1, d=0x00))
        self.assertTrue(r.to_self[-1][1].endswith(b"\xc8"))  # 回包里取的是物品表的耐久

    def test_malformed_requests_are_ignored(self):
        rows = self.rows()
        self.assertEqual(bank.transfer(rows, self.table, b"\x00\x01\x02").to_self, [])
        self.assertEqual(bank.transfer(rows, self.table, b"\x02" + bytes(7)).to_self, [])

    def test_item_info(self):
        self.assertEqual(hexs(bank.item_info(struct.pack("<I", 28026) + bytes(6)).to_self), [(0x88, "7a 6d 00 00 c8 00 00 00 00", False)])
        self.assertEqual(hexs(bank.item_info(struct.pack("<I", 99999999) + bytes(1)).to_self)[0][1], "ff e0 f5 05 c8 00 00 00 00")
        self.assertEqual(bank.item_info(b"\x01\x02\x03\x04").to_self, [])


if __name__ == "__main__":
    unittest.main()
