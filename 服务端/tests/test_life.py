"""生活技能（伐木 / 捕魚 / 採礦）和農夫：期望值来自对原版 8617293 号的实测（2026-10-20，tools/life_probe.py / life_sample.py / farm_sample.py）。"""

import unittest

from jyserver import life as L
from jyserver.state import ItemTable

JY = 8617293


class FixedRng:
    def __init__(self, *values):
        self.values = list(values)

    def randint(self, a, b):
        return self.values.pop(0) if self.values else a

    def choice(self, seq):
        return seq[0]


def rows(**kw):
    ren = {"jyid": str(JY), "dangqianjing": "500", "wint": "33", "jy_money": "100000"}
    ren.update({k: str(v) for k, v in kw.items()})
    return {"renwu": [ren], "jineng": [{"famu": "5", "famuexp": "0", "buyu": "0", "buyuexp": "0", "caikuang": "0", "caikuangexp": "0", "nongfu": "1", "nongfuexp": "0"}], "item": [], "qianzhuang": []}


ITEMS = ItemTable({44156: 200, 44051: 200, 44206: 200, 44201: 200, 55710: 200})


def pay_work(a, b):
    return bytes([1, 0, 0, 0, a, b, 0, 0, 0, 0, 0, 0, 0])


def pay_farm(plot, action):
    return bytes([9, 0, 0, 0, plot, action, 0, 0, 0, 0, 0, 0])


def hexs(frames):
    return [(op, p.hex(" ")) for op, p, _ in frames]


class Tables(unittest.TestCase):
    def test_extracted_ladders_match_what_the_original_gave_when_sampled(self):
        lf = L.Life.load()
        self.assertEqual({lf.pick("famu", lv, r) for lv in (0, 15, 30) for r in (1, 50, 100)}, {44156})  # 伐木 30 级以下固定相思木
        self.assertEqual(lf.pick("famu", 100, 90), 44169)  # 满级才有
        self.assertEqual(lf.pick("buyu", 85, 35), 0)  # 捕魚 61–90 级有 10% 什么也没有（原版发物品 0）
        self.assertEqual([lf.pick("buyu", 85, r) for r in (5, 15, 25, 45, 55, 65, 75, 85, 95)], [44051, 44052, 44053, 44054, 44055, 44056, 44057, 44058, 44059])
        self.assertEqual(lf.pick("caikuang", 5, 50), 44021)


class Work(unittest.TestCase):
    def setUp(self):
        self.lf = L.Life({"famu": {str(n): [[1, 100, "44156"]] for n in range(101)}})
        self.st = L.State()

    def run_round(self, r, now, rng=None):
        return self.lf.work(r, ITEMS, self.st, rng or FixedRng(50), JY, pay_work(2, 1), now=now)

    def test_start_and_stop_tell_the_map(self):
        r = rows()
        res = self.lf.work(r, ITEMS, self.st, FixedRng(), JY, pay_work(1, 1), now=100)
        self.assertEqual((hexs(res.to_self), hexs(res.to_map)), ([(0x82, "4d 7d 83 00 03 00")], [(0x82, "4d 7d 83 00 03 00")]))
        self.assertEqual(hexs(self.lf.work(r, ITEMS, self.st, FixedRng(), JY, pay_work(1, 2), now=100).to_self), [(0x82, "4d 7d 83 00 04 00")])
        self.assertEqual(hexs(self.lf.work(r, ITEMS, self.st, FixedRng(), JY, pay_work(1, 3), now=100).to_self), [(0x82, "4d 7d 83 00 05 00")])
        self.assertEqual(self.lf.work(r, ITEMS, self.st, FixedRng(), JY, pay_work(0, 0), now=100).to_self, [])  # A=0 原版什么都不回
        stop = self.lf.work(r, ITEMS, self.st, FixedRng(), JY, pay_work(3, 1), now=100)
        self.assertEqual((hexs(stop.to_self), stop.to_map), ([(0x82, "4d 7d 83 00 00 00")], []))

    def test_the_first_catch_of_a_kind_stays_in_the_bag_silently(self):
        r = rows()
        res = self.run_round(r, 1000)
        self.assertEqual([op for op, _, _ in res.to_self], [0x7B, 0x76, 0x76, 0x64])
        self.assertEqual([(i["item_id"], i["shuliang"]) for i in r["item"]], [("44156", "1")])
        self.assertEqual(r["qianzhuang"], [])
        res = self.run_round(r, 1010)  # 背包里已经有了：这回走钱庄，背包不变
        self.assertEqual([op for op, _, _ in res.to_self][-4:], [0x0B, 0x77, 0x27, 0x1A])
        self.assertEqual(([i["shuliang"] for i in r["item"]], [(b["wupin"], b["shuliang"]) for b in r["qianzhuang"]]), (["1"], [("44156", "1")]))

    def test_a_round_spends_one_jing_grows_the_skill_and_stores_the_catch_in_the_bank(self):
        r = rows(dangqianjing=3)
        r["item"] = [{"jyid": str(JY), "item_id": "44156", "shuliang": "1", "state": "200"}]
        res = self.run_round(r, 1000)
        self.assertEqual(
            hexs(res.to_self),
            [
                (0x7B, "16 01 02 00 00 00"),
                (0x76, "be 00 01 01 09 00 00 00"),  # 5 级 + 33×10 经验：36+49+64+81 之后剩 100，到 9 级
                (0x76, "be 00 02 01 64 00 00 00"),
                (0x64, "7c ac 01 00 09 64 00 00"),
                (0x0B, "8f bb 00 00 c8 01"),
                (0x77, "8f bb 00 00 c8 01"),
                (0x27, "00 7c ac 00 00 01 00 a0 86 01 00 c8"),
                (0x1A, "64 56 49 50 a5 5c af e0 aa f6 b6 b0 aa ab ab 7e a6 db b0 ca a6 73 a4 4a bf fa c9 dc a1 54"),
            ],
        )
        self.assertEqual((r["jineng"][0]["famu"], r["jineng"][0]["famuexp"], r["renwu"][0]["dangqianjing"]), ("9", "100", "2"))
        self.assertEqual([(b["wupin"], b["shuliang"]) for b in r["qianzhuang"]], [("44156", "1")])

    def test_rounds_less_than_four_seconds_apart_are_refused_but_still_pay_exp_and_jing(self):
        r = rows()
        self.run_round(r, 1000)
        res = self.run_round(r, 1003)
        self.assertEqual([op for op, _, _ in res.to_self], [0x7B, 0x76, 0x76, 0x1A])
        self.assertEqual(hexs(res.to_self)[-1], (0x1A, "64 b8 54 a4 ee a5 5b b3 74 aa f6 b6 b0"))
        self.assertEqual(r["renwu"][0]["dangqianjing"], "498")
        self.assertEqual([op for op, _, _ in self.run_round(r, 1004).to_self][3], 0x64)  # 4 秒够了（从上一次**成功**的算起）

    def test_needs_more_than_one_jing(self):
        r = rows(dangqianjing=1)
        self.assertEqual(self.run_round(r, 1000).to_self, [])
        self.assertEqual(r["renwu"][0]["dangqianjing"], "1")

    def test_level_100_is_the_cap_and_stops_the_counters(self):
        r = rows()
        r["jineng"][0].update(famu="99", famuexp="9900")
        res = self.run_round(r, 1000)
        self.assertEqual((r["jineng"][0]["famu"], r["jineng"][0]["famuexp"]), ("100", "0"))
        self.assertEqual(hexs(res.to_self)[1:3], [(0x76, "be 00 01 01 64 00 00 00"), (0x76, "be 00 02 01 00 00 00 00")])
        res = self.run_round(r, 1010)
        self.assertEqual([op for op, _, _ in res.to_self][:2], [0x7B, 0x64])  # 满级以后不再发 0x76
        self.assertEqual(hexs(res.to_self)[1], (0x64, "7c ac 01 00 64 00 00 00"))

    def test_item_zero_is_deposited_on_the_wupin_zero_row(self):
        r = rows()
        res = L.Life({"famu": {str(n): [[1, 100, None]] for n in range(101)}}).work(r, ITEMS, L.State(), FixedRng(1), JY, pay_work(2, 1), now=5)
        self.assertEqual(hexs(res.to_self)[3], (0x64, "00 00 01 00 05 00 00 00".replace("05 00 00 00", "09 64 00 00")))
        self.assertEqual([(b["wupin"], b["shuliang"]) for b in r["qianzhuang"]], [("0", "1")])


class Zixiu(unittest.TestCase):
    def test_penalty_text_and_one_level_off_a_kungfu_when_there_are_two_or_more(self):
        r = rows()
        r["renwu"][0]["name"] = "123456"
        r["kf"] = [{"kf_id": "1000", "kf_lvl": "10", "kf_exp": "0"}, {"kf_id": "1002", "kf_lvl": "10", "kf_exp": "0"}]
        res = L.Life({}).zixiu_penalty(r, FixedRng(), JY)
        self.assertEqual(res.to_all[0][1], bytes.fromhex("0e aa b1 ae 61 3a") + b"8617293" + bytes.fromhex("a1 41 a9 6d a6 57 3a") + b"123456" + bytes.fromhex("a6 62 a6 db ad d7 ac 7d bd 6d a7 de af e0 a1 41 aa 5a a5 5c c0 48 c9 f3 b1 bc a4 40 af c5"))
        self.assertEqual(hexs(res.to_self), [(0x70, "00 00 f4 01 e8 03 09 00 00 00 00 00".replace("00 00 f4 01", "00 00 f4 01"))])
        r["kf"] = r["kf"][:1]
        self.assertEqual(L.Life({}).zixiu_penalty(r, FixedRng(), JY).to_self, [])  # 只有一门：只有公告


class Farm(unittest.TestCase):
    def setUp(self):
        self.lf = L.Life({})
        self.st = L.State()

    def test_plant_till_harvest(self):
        r = rows()
        r["item"] = [{"jyid": str(JY), "item_id": "44201", "shuliang": "2", "state": "200"}]
        res = self.lf.plant(r, self.st, JY, bytes([3, 0xA9, 0xAC]))
        self.assertEqual((hexs(res.to_self), hexs(res.to_map)), ([(0x66, "4d 7d 83 00 03 a9 ac 01")], [(0x67, "03 01")]))
        self.assertEqual(r["item"][0]["shuliang"], "1")
        res = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100), JY, pay_farm(3, 1))
        self.assertEqual((hexs(res.to_self), hexs(res.to_map)), ([(0x66, "4d 7d 83 00 03 a9 ac 03"), (0x82, "4d 7d 83 00 06 00")], [(0x82, "4d 7d 83 00 06 00")]))
        res = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(1, 100), JY, pay_farm(3, 2), now=1000)
        self.assertEqual(
            hexs(res.to_self),
            [(0x64, "ae ac 01 08 01 00 00 00 00"), (0x76, "be 08 01 01 09 00 00 00"), (0x76, "be 08 02 01 2e 00 00 00")],  # 64 里是升级前的等级 / 经验
        )
        self.assertEqual(hexs(res.to_map), [(0x67, "03 00")])
        self.assertEqual([(b["item_id"], b["shuliang"]) for b in r["item"]], [("44201", "1"), ("44206", "1")])  # 稻米进背包，不走钱庄
        self.assertEqual((r["jineng"][0]["nongfu"], r["jineng"][0]["nongfuexp"], self.st.seed), ("9", "46", 0))
        again = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100), JY, pay_farm(3, 1))
        self.assertEqual(hexs(again.to_self)[0], (0x66, "4d 7d 83 00 03 00 00 03"))  # 收完以后田块上没有种子了

    def test_harvest_without_a_seed_sends_no_0x64_and_a_one_percent_failure_frame_otherwise(self):
        r = rows()
        res = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100), JY, pay_farm(3, 2), now=1000)
        self.assertEqual([op for op, _, _ in res.to_self], [0x76, 0x76])  # 没种子：只有经验
        self.st.seed = 44201
        res = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100, 100), JY, pay_farm(3, 2), now=1010)
        self.assertEqual(hexs(res.to_self)[0][1][:11], "00 00 00 08")  # 掷到 100：失败帧，作物不进背包
        self.assertEqual(r["item"], [])

    def test_planting_without_the_seed_still_answers_then_complains(self):
        r = rows()
        res = self.lf.plant(r, self.st, JY, bytes([0, 0xA9, 0xAC]))
        self.assertEqual(hexs(res.to_self), [(0x66, "4d 7d 83 00 00 a9 ac 01"), (0x1A, "64 aa ab ab 7e a4 a3 a8 ac")])
        self.assertEqual(self.lf.plant(r, self.st, JY, bytes([0, 0xA9, 0xAC, 0])).to_self, [])  # 载荷不是 3 字节：不理

    def test_harvests_are_rate_limited_like_the_work_rounds(self):
        r = rows()
        self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100), JY, pay_farm(3, 2), now=1000)
        res = self.lf.till_or_harvest(r, ITEMS, self.st, FixedRng(100), JY, pay_farm(3, 2), now=1002)
        self.assertEqual([op for op, _, _ in res.to_self], [0x1A, 0x76, 0x76])  # 被拒的收成照样涨经验
        self.assertEqual(hexs(res.to_self)[0], (0x1A, "64 b8 54 a4 ee a5 5b b3 74 aa f6 b6 b0"))
        self.assertEqual(hexs(res.to_map), [(0x67, "03 00")])


if __name__ == "__main__":
    unittest.main()
