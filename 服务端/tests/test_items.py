"""穿/脱装备、使用物品：期望值全部来自对原版服务端的实测（tools/equip_probe.py、use_probe.py）。

物品表要读原版服务端的 data 目录，找不到就跳过。
"""

import copy
import json
import struct
import unittest
from pathlib import Path

from jyserver import items
from jyserver.state import ItemTable

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "data" / "fixtures"
from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)


def rows_of(jyid):
    return copy.deepcopy(json.loads((FIX / f"char-{jyid}.json").read_text(encoding="utf-8"))["rows"])


def hexs(frames):
    return [(op, p.hex(" "), w) for op, p, w in frames]


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Equipment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    def test_unequip_weapon_reports_weapon_strength_only(self):
        rows = rows_of(123456)
        r = items.unequip(rows, self.table, b"\x06")
        self.assertEqual(hexs(r.to_self), [(0x18, "40 e2 01 00 06", False), (0x7B, "2f 01 be 00 00 00", True)])
        self.assertEqual(rows["renwu"][0]["wuqi"], "0")

    def test_equip_weapon_back(self):
        rows = rows_of(123456)
        items.unequip(rows, self.table, b"\x06")
        r = items.equip(rows, self.table, b"\x06" + struct.pack("<I", 12498) + b"\x32")
        self.assertEqual(hexs(r.to_self), [(0x17, "40 e2 01 00 06 d2 30 00 00 32", False), (0x7B, "2f 01 4a 06 00 00", True)])
        self.assertEqual((rows["renwu"][0]["wuqi"], rows["renwu"][0]["wuqizhuangtai"]), ("12498", "50"))

    def test_body_armor_changes_both_strengths_weapon_first(self):
        rows = rows_of(123456)
        r = items.unequip(rows, self.table, b"\x03")
        self.assertEqual([p.hex(" ") for _, p, _ in r.to_self][1:], ["2f 01 8c 05 00 00", "30 01 86 1a 00 00"])

    def test_unequip_armor_only_reports_armor_strength(self):
        rows = rows_of(123456)
        r = items.unequip(rows, self.table, b"\x04")
        self.assertEqual([op for op, _, _ in r.to_self], [0x18, 0x7B])
        self.assertEqual(r.to_self[1][1][0], 0x30)

    def test_unequip_empty_slot_still_replies_without_strength(self):
        rows = rows_of(8617293)
        r = items.unequip(rows, self.table, b"\x01")
        self.assertEqual(hexs(r.to_self), [(0x18, "4d 7d 83 00 01", False)])

    def test_invalid_slots_are_silent(self):
        rows = rows_of(123456)
        for slot in (0, 5, 10, 200):
            self.assertEqual(items.unequip(rows, self.table, bytes([slot])).to_self, [])
            self.assertEqual(items.equip(rows, self.table, bytes([slot]) + struct.pack("<I", 12498) + b"\x32").to_self, [])

    def test_occupied_slot_is_silent_and_item_type_is_not_checked(self):
        rows = rows_of(123456)
        self.assertEqual(items.equip(rows, self.table, b"\x09" + struct.pack("<I", 12498) + b"\x32").to_self, [])
        items.unequip(rows, self.table, b"\x09")
        r = items.equip(rows, self.table, b"\x09" + struct.pack("<I", 12498) + b"\x32")  # 把剑穿在鞋子位上
        self.assertEqual(r.to_self[0][1].hex(" "), "40 e2 01 00 09 d2 30 00 00 32")

    def test_state_byte_is_echoed(self):
        rows = rows_of(123456)
        items.unequip(rows, self.table, b"\x09")
        r = items.equip(rows, self.table, b"\x09" + struct.pack("<I", 26108) + b"\x07")
        self.assertEqual(r.to_self[0][1][-1], 0x07)

    def test_equipping_unowned_item_broadcasts_cheat_notice(self):
        rows = rows_of(8617293)  # 名字 123456，背包里没有 神威麒麟盔
        r = items.equip(rows, self.table, b"\x01" + struct.pack("<I", 25091) + b"\x32")
        self.assertEqual(r.to_self, [])
        self.assertEqual(
            hexs(r.to_all),
            [(0x14, "0e 31 32 33 34 35 36 b9 c1 b8 d5 a8 ea b8 cb b3 c6 a1 54 af ab ab c2 c4 51 c5 ef b2 af", True)],
        )
        self.assertEqual(rows["renwu"][0]["toukui"], "0")

    def test_cheat_notice_uses_traditional_item_names(self):
        rows = rows_of(8617293)
        r = items.equip(rows, self.table, b"\x02" + struct.pack("<I", 24075) + b"\x32")  # 神威麒麟项炼
        self.assertTrue(r.to_all[0][1].endswith(bytes.fromhex("af ab ab c2 c4 51 c5 ef b6 b5 b7 d2")))

    def test_unknown_item_id_gives_notice_without_item_name(self):
        rows = rows_of(8617293)
        r = items.equip(rows, self.table, b"\x03" + struct.pack("<I", 99999999) + b"\x32")
        self.assertEqual(r.to_all[0][1].hex(" "), "0e 31 32 33 34 35 36 b9 c1 b8 d5 a8 ea b8 cb b3 c6 a1 54")


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class UseItem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    @staticmethod
    def char(**stats):
        renwu = {"jyid": "9999001", "dangqianxue": "2000", "zuidaxue": "2000", "dangqianjing": "210", "zuidajing": "210",
                 "dangqianshen": "210", "zuidashen": "210", "dangqiannei": "1", "zuidanei": "1", "diet_val": "60",
                 "water_val": "60", "study_count": "0", "fame_val": "0", "wint": "21", "str": "23"}
        renwu.update({k: str(v) for k, v in stats.items()})
        return {"renwu": [renwu], "item": []}

    def stock(self, rows, item_id, qty=3):
        rows["item"].append({"item_id": str(item_id), "shuliang": str(qty), "state": "200"})

    def test_food_heals_and_feeds_then_acks(self):
        rows = self.char()
        self.stock(rows, 31011)  # 鸳鸯五珍烩：气 1000、饱食 100
        r = items.use_item(rows, self.table, struct.pack("<I", 31011) + b"\x00")
        self.assertEqual(
            hexs(r.to_self),
            [(0x7B, "18 01 d0 07 00 00", True), (0x7B, "34 01 64 00 00 00", True), (0x0B, "23 79 00 00 32 01", False)],
        )
        self.assertEqual((rows["item"][0]["shuliang"], rows["renwu"][0]["diet_val"]), ("2", "100"))

    def test_effect_order_is_jing_shen_qi(self):
        rows = self.char()
        self.stock(rows, 31508)  # 佛光谱照：精 神 气 各 1500
        r = items.use_item(rows, self.table, struct.pack("<I", 31508))
        self.assertEqual([p[0] for op, p, _ in r.to_self if op == 0x7B], [0x16, 0x1A, 0x18])

    def test_water_before_food_and_study_points(self):
        rows = self.char()
        self.stock(rows, 31170)  # 饮水 100、饱食 100
        self.stock(rows, 31601)  # 饱食 10、学点 500
        r = items.use_item(rows, self.table, struct.pack("<I", 31170))
        self.assertEqual([p[0] for op, p, _ in r.to_self if op == 0x7B], [0x36, 0x34])
        r = items.use_item(rows, self.table, struct.pack("<I", 31601))
        self.assertEqual([p.hex(" ") for op, p, _ in r.to_self if op == 0x7B], ["34 01 64 00 00 00", "28 01 f4 01 00 00"])

    def test_attribute_and_fame_pills(self):
        rows = self.char()
        self.stock(rows, 28178)  # 悟性丹 +1
        self.stock(rows, 28280)  # 声望散 +1 名声
        r = items.use_item(rows, self.table, struct.pack("<I", 28178))
        self.assertEqual(r.to_self[0][1].hex(" "), "20 01 16 00 00 00")
        r = items.use_item(rows, self.table, struct.pack("<I", 28280))
        self.assertEqual(r.to_self[0][1].hex(" "), "3d 01 01 00 00 00")

    def test_unimplemented_effect_still_consumes_and_acks(self):
        rows = self.char()
        self.stock(rows, 28320)  # 霹雳丹：永久攻 +50，效果这里还没做
        r = items.use_item(rows, self.table, struct.pack("<I", 28320))
        self.assertEqual(hexs(r.to_self), [(0x0B, "a0 6e 00 00 c8 01", False)])
        self.assertEqual(rows["item"][0]["shuliang"], "2")

    def test_max_stat_pills_are_silent_and_not_consumed(self):
        rows = self.char()
        self.stock(rows, 28276)
        r = items.use_item(rows, self.table, struct.pack("<I", 28276))
        self.assertEqual(r.to_self, [])
        self.assertEqual(rows["item"][0]["shuliang"], "3")

    def test_permanent_attack_and_defence_accumulate_into_strength(self):
        rows = self.char()
        self.stock(rows, 28320)  # 霹雳丹 永久攻 +50
        self.stock(rows, 28321)  # 金钟丹 永久防 +100
        items.use_item(rows, self.table, struct.pack("<I", 28320))
        r = items.use_item(rows, self.table, struct.pack("<I", 28321))
        self.assertEqual(hexs(r.to_self), [(0x0B, "a1 6e 00 00 c8 01", False)])  # 只有确认，没有 0x7B
        self.assertEqual(self.table.strengths(rows["renwu"][0]), (50, 100))  # 实测：没装备时登录包里就是 50 / 100

    def test_max_qi_pill_acks_first_then_reports_new_max(self):
        rows = self.char()
        self.stock(rows, 28278)  # 气血涌现丹 max气 +5000
        r = items.use_item(rows, self.table, struct.pack("<I", 28278))
        self.assertEqual(hexs(r.to_self), [(0x0B, "76 6e 00 00 c8 01", False), (0x7B, "17 01 58 1b 00 00", True)])
        self.assertEqual(rows["renwu"][0]["zuidaxue"], "7000")

    def test_max_jing_shen_nei_pills_are_silent(self):
        rows = self.char()
        for iid in (31171, 31219, 28053):
            self.stock(rows, iid)
            self.assertEqual(items.use_item(rows, self.table, struct.pack("<I", iid)).to_self, [])
        self.assertEqual([r["shuliang"] for r in rows["item"]], ["3", "3", "3"])

    def test_status_only_medicine_is_silent(self):
        rows = self.char()
        self.stock(rows, 29001)  # 刀伤药：只有「流血 −20」
        self.assertEqual(items.use_item(rows, self.table, struct.pack("<I", 29001)).to_self, [])
        self.assertEqual(rows["item"][0]["shuliang"], "3")

    def test_status_columns_alongside_stats_only_show_the_stats(self):
        rows = self.char()
        self.stock(rows, 28074)  # 定脉完：气 +1、毒 +10
        r = items.use_item(rows, self.table, struct.pack("<I", 28074))
        self.assertEqual(hexs(r.to_self), [(0x7B, "18 01 d0 07 00 00", True), (0x0B, "aa 6d 00 00 c8 01", False)])

    def test_temporary_attack_pill_only_acks(self):
        rows = self.char()
        self.stock(rows, 28317)  # 气力倍增丸：攻击 +200（临时）
        r = items.use_item(rows, self.table, struct.pack("<I", 28317))
        self.assertEqual(hexs(r.to_self), [(0x0B, "9d 6e 00 00 c8 01", False)])
        self.assertEqual(rows["item"][0]["shuliang"], "2")

    def test_special_buff_items(self):
        for iid, want in (
            (28170, ["0b", "1a"]),
            (28172, ["0b"]),
            (28255, ["0b", "99", "1a"]),
            (28388, ["0b", "1a"]),
        ):
            rows = self.char()
            self.stock(rows, iid)
            r = items.use_item(rows, self.table, struct.pack("<I", iid))
            self.assertEqual([f"{op:02x}" for op, _, _ in r.to_self], want, iid)
            self.assertEqual(rows["item"][0]["shuliang"], "2")
        rows = self.char()
        self.stock(rows, 28255)
        r = items.use_item(rows, self.table, struct.pack("<I", 28255))
        self.assertEqual(r.to_self[1][1].hex(" "), "05 99 92 98 00 ff")  # 99 05 + jyid(LE32) + ff

    def test_effectless_unknown_item_is_silent(self):
        rows = self.char()
        self.stock(rows, 28197)  # 金娃娃鱼：药品表里没有效果列、也不是已知特殊药
        self.assertEqual(items.use_item(rows, self.table, struct.pack("<I", 28197)).to_self, [])

    def test_missing_item(self):
        rows = self.char()
        r = items.use_item(rows, self.table, struct.pack("<I", 31011))
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x1A, "64 aa ab ab 7e a4 a3 a8 ac", False),
                (0x05, "99 92 98 00 01", False),
                (0x14, "08 ad 49 a5 5d a8 53 a6 b3 a6 b9 aa ab ab 7e", True),
            ],
        )

    def test_running_out(self):
        rows = self.char()
        self.stock(rows, 31011, qty=1)
        self.assertEqual(items.use_item(rows, self.table, struct.pack("<I", 31011)).to_self[-1][0], 0x0B)
        self.assertEqual(items.use_item(rows, self.table, struct.pack("<I", 31011)).to_self[0][0], 0x1A)


if __name__ == "__main__":
    unittest.main()
