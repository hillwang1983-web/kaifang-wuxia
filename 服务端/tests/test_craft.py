"""合成 / 烹調（C2S 0x1B）：期望值来自对原版 8617293 号的实测（2026-10-21，tools/craft_compare.py）。"""

import unittest

from jyserver import craft as C
from jyserver import life as L
from jyserver.state import ItemTable

JY = 8617293
ITEMS = ItemTable({44267: 40, 44102: 200, 44104: 200, 31001: 6})


class FixedRng:
    def __init__(self, *values):
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0) if self.values else a


def rows(chushi=0, luk=10, shen=50, bag=None):
    ren = {"jyid": str(JY), "dangqianshen": str(shen), "wint": "33", "luk": str(luk)}
    bag = {44267: 3, 44102: 3, 44104: 3} if bag is None else bag
    return {
        "renwu": [ren],
        "jineng": [{"chushi": str(chushi), "chushiexp": "0"}],
        "item": [{"jyid": str(JY), "item_id": str(i), "shuliang": str(n), "state": "200"} for i, n in bag.items()],
        "qianzhuang": [],
    }


def hexs(res):
    return [(op, p.hex(" ")) for op, p, _ in res.to_self]


def have(r, iid):
    return sum(int(x["shuliang"]) for x in r["item"] if int(x["item_id"]) == iid)


class Recipes(unittest.TestCase):
    def test_table_holds_the_cooking_recipes_that_were_read_from_the_original(self):
        c = C.Craft.load()
        self.assertEqual(c.recipes["F0 02"], {"needs": [[44267, 1], [44102, 1], [44104, 1]], "takes": [[44267, 1], [44102, 1], [44104, 1]], "skill": "厨师", "product": 31001, "win": "luk", "lvl_off": 508})
        self.assertGreater(len(c.recipes), 1300)
        self.assertIn("0A 00", c.unsupported)


class Cook(unittest.TestCase):
    def setUp(self):
        self.c = C.Craft.load()
        self.lf = L.Life({})

    def cook(self, r, roll=1, payload=b"\xf0\x02"):
        return self.c.craft(r, ITEMS, self.lf, FixedRng(roll), payload)

    def test_success_matches_the_original_frame_by_frame(self):
        r = rows(chushi=0, luk=10)
        res = self.cook(r, roll=1)  # (1+2)//5 = 0 < 10
        self.assertEqual(
            hexs(res),
            [
                (0x7B, "1a 01 31 00 00 00"),
                (0x6B, "eb ac 00 00 28 01"),
                (0x6B, "46 ac 00 00 c8 01"),
                (0x6B, "48 ac 00 00 c8 01"),
                (0x76, "be 0a 01 01 09 00 00 00"),  # 技能经验 悟性 33 × 10 = 330：0 级升到 9 级剩 45
                (0x76, "be 0a 02 01 2d 00 00 00"),
                (0x64, "19 79 01 0a 09 2d 00 00 00"),
            ],
        )
        self.assertEqual((have(r, 31001), have(r, 44267), have(r, 44102), have(r, 44104)), (1, 2, 2, 2))
        self.assertEqual(r["renwu"][0]["dangqianshen"], "49")

    def test_failure_sends_item_zero_and_keeps_the_materials_gone(self):
        r = rows(chushi=40, luk=0)
        res = self.cook(r, roll=50)
        self.assertEqual(hexs(res)[-1], (0x64, "00 00 00 0a 28 4a 01 00 00"))
        self.assertEqual((have(r, 31001), have(r, 44267)), (0, 2))

    def test_roll_is_the_original_rounding_of_a_1_to_110_draw_over_five(self):
        # 随机 r -> round(r / 5)：1、2 -> 0；3..7 -> 1；108..110 -> 22；luk 10 时 r <= 47 成功（四舍五入后 < 10）
        wins = [r for r in range(1, 111) if (r + 2) // 5 < 10]
        self.assertEqual(max(wins), 47)
        r = rows(luk=10)
        self.assertEqual(hexs(self.cook(r, roll=47))[-1][1][:8], "19 79 01")
        r = rows(luk=10)
        self.assertEqual(hexs(self.cook(r, roll=48))[-1][1][:8], "00 00 00")

    def test_missing_material_is_silent_but_the_shen_is_spent(self):
        r = rows(chushi=40, bag={44267: 1, 44104: 1})
        self.assertEqual(hexs(self.cook(r)), [(0x7B, "1a 01 31 00 00 00")])
        self.assertEqual(have(r, 44267), 1)

    def test_needs_two_shen(self):
        r = rows(shen=1)
        self.assertEqual(self.cook(r).to_self, [])
        self.assertEqual(r["renwu"][0]["dangqianshen"], "1")

    def test_short_payload_is_ignored_and_extra_bytes_do_not_matter(self):
        r = rows()
        self.assertEqual(self.cook(r, payload=b"").to_self, [])
        self.assertEqual(self.cook(r, payload=b"\xf0").to_self, [])
        self.assertEqual(hexs(self.cook(r, payload=b"\xf0\x02\x00\x00"))[0][0], 0x7B)

    def test_unknown_key_gets_the_admin_notice(self):
        res = self.cook(rows(), payload=b"\xf0\x03")
        self.assertEqual([op for op, _, _ in res.to_self], [0x7B, 0x1A])
        self.assertEqual(res.to_self[1][1][:9].hex(" "), "64 bd d0 b0 4f bf fd a1 52")
        self.assertIn(b"F0 03", res.to_self[1][1])

    def test_unsupported_special_recipe_only_costs_the_shen(self):
        self.assertEqual(hexs(self.cook(rows(), payload=b"\x0a\x00")), [(0x7B, "1a 01 31 00 00 00")])

    def test_each_unit_taken_is_its_own_0x6b_frame(self):
        # 木炭要 5 个 -> 5 条 0x6B（原版 7800 铁剑实测：绿晶铁 1、青铜 1、木炭 5 条）
        c = C.Craft.load()
        rec = c.recipes["7A 00"]
        r = rows(luk=30, bag={i: n * 2 for i, n in rec["needs"]})
        res = c.craft(r, ITEMS, self.lf, FixedRng(1), b"\x7a\x00")
        self.assertEqual([op for op, _, _ in res.to_self].count(0x6B), sum(n for _, n in rec["takes"]))
        self.assertTrue(all(p[-1] == 1 for op, p, _ in res.to_self if op == 0x6B))

    def test_take_list_can_differ_from_the_check_list_like_the_original_typo(self):
        # B6 04：检查 25006，扣的却是 24006（原版笔误）。背包没有 24006 -> 「物品不足」，配方照样做完，25006 不扣
        c = C.Craft.load()
        rec = c.recipes["B6 04"]
        self.assertNotEqual(rec["needs"], rec["takes"])
        r = rows(luk=30, bag={i: n for i, n in rec["needs"]})
        res = c.craft(r, ITEMS, self.lf, FixedRng(60), b"\xb6\x04")
        ops = [op for op, _, _ in res.to_self]
        self.assertEqual(ops[:2], [0x7B, 0x1A])
        self.assertEqual(res.to_self[1][1].hex(" "), "64 aa ab ab 7e a4 a3 a8 ac")
        self.assertEqual(ops[-1], 0x64)
        self.assertEqual(have(r, 25006), 1)
        self.assertEqual(have(r, rec["product"]), 1)

    def test_bag_total_over_498_blocks_the_craft(self):
        for total, blocked in ((498, False), (499, True), (500, True)):
            r = rows(bag={44267: 1, 44102: 1, 44104: 1, 40500: total - 3})
            res = self.cook(r, roll=1)
            self.assertEqual([op for op, _, _ in res.to_self][:2], [0x7B, 0x1A] if blocked else [0x7B, 0x6B], total)
        self.assertEqual(hexs(self.cook(rows(bag={40500: 500})))[1], (0x1A, "64 a8 ad a4 57 c1 60 bc c6 b6 57 b9 4c 34 39 39"))  # 身上總數超過499

    def test_announcement_for_broadcast_products_when_the_roll_is_under_six(self):
        # 原版实测（8617293 号，名字 123456）：合成 (精六)杀神盔 25801，随机数 < 6 时全服 0x04 子类型 09
        items = ItemTable({}, names={25801: "(精六)杀神盔", 31001: "熟牛肉"}, broadcast={25801})
        rec = dict(C.Craft.load().recipes["47 07"])
        c = C.Craft({"47 07": rec})
        r = rows(luk=30, bag={i: n for i, n in rec["needs"]})
        r["renwu"][0]["name"] = "123456"
        res = c.craft(r, items, self.lf, FixedRng(1), b"\x47\x07")  # (1+2)//5 = 0 < 6
        self.assertEqual(
            [(op, p.hex(" "), w) for op, p, w in res.to_all],
            [(0x04, "09 4d 7d 83 00 aa b1 ae 61 31 32 33 34 35 36 a1 41 a6 58 a6 a8 b1 6f a8 ec a1 52 28 ba eb a4 bb 29 b1 fe af ab b2 af", True)],
        )
        r = rows(luk=30, bag={i: n for i, n in rec["needs"]})
        self.assertEqual(c.craft(r, items, self.lf, FixedRng(60), b"\x47\x07").to_all, [])  # (60+2)//5 = 12 >= 6：不广播
        self.assertEqual(self.cook(rows(), roll=1).to_all, [])  # 熟牛肉没标「是否广播」

    def test_announcement_does_not_look_at_success(self):
        rec = dict(C.Craft.load().recipes["7A 00"])  # 阈值是幸运的配方；把成品当成标了广播的（读原版表时是 装备数据.csv「是否广播」）
        self.assertEqual(rec["win"], "luk")
        items = ItemTable({}, names={rec["product"]: "铁剑"}, broadcast={rec["product"]})
        c = C.Craft({"7A 00": rec})
        r = rows(luk=0, bag={i: n for i, n in rec["needs"]})  # luk 0：必败；随机数 < 6 照样广播
        res = c.craft(r, items, self.lf, FixedRng(1), b"\x7a\x00")
        self.assertEqual(len(res.to_all), 1)
        self.assertEqual(hexs(res)[-1][1][:8], "00 00 00")

    def test_level_100_gets_no_exp_frames(self):
        r = rows(chushi=100, luk=30)
        self.assertEqual([op for op, _, _ in self.cook(r).to_self], [0x7B, 0x6B, 0x6B, 0x6B, 0x64])


if __name__ == "__main__":
    unittest.main()
