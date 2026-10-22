"""@文字指令（C2S 0xC7）：期望值来自对原版的实测（2026-10，8617293 号，tools/cmd_probe.py / cmd_compare.py）。"""

import unittest
from pathlib import Path

from jyserver import commands
from jyserver.events import Tables
from jyserver.state import ItemTable

from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)
JYID = 8617293


def hexs(frames):
    return [(op, p.hex(" ")) for op, p, _ in frames]


def cmd(text, **kw):
    return b"\x04\x40" + text.encode() + kw.get("tail", b"")


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class Commands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = ItemTable.load(DATA_DIR)
        cls.tables = Tables.load(DATA_DIR)

    @staticmethod
    def rows(money=100000, points=3000, gm=0, school=0, master=0, bag=()):
        return {
            "renwu": [{"jyid": str(JYID), "name": "123456", "map": "2200", "jy_money": str(money), "school": str(school), "master": str(master), "school_skill_lv": "7", "school_skill_exp": "555"}],
            "account": [{"jyid": str(JYID), "shangchengdianshu": str(points), "gm_lvl": str(gm)}],
            "item": [{"jyid": str(JYID), "item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in bag],
            "biaoji": [],
        }

    def run_cmd(self, rows, payload):
        return commands.handle(rows, self.items, self.tables, payload)

    def test_silent_switches_and_unknown_text(self):
        rows = self.rows()
        for p in (cmd("tw", tail=b"\x00"), cmd("tw", tail=b"\x01"), cmd("cxwg"), cmd("bj", tail=b"\x00"), cmd("nonsense"), b"\x05\x40where", cmd("tw")):
            r = self.run_cmd(rows, p)
            self.assertEqual((r.to_self, r.to_all, r.teleport, r.kick), ([], [], None, False))

    def test_where_and_kale(self):
        r = self.run_cmd(self.rows(), cmd("where"))
        self.assertEqual(hexs(r.to_self), [(0x04, "02 4d 7d 83 00 32 32 30 30")])
        self.assertEqual(self.run_cmd(self.rows(), cmd("kale")).teleport, (2822, 210, 450))

    def test_cpw_lists_bag_newest_first_with_traditional_names(self):
        r = self.run_cmd(self.rows(bag=[(28290, 1), (58182, 10)]), cmd("cpw"))
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x04, "02 4d 7d 83 00 35 38 31 38 32 a1 52 b0 4f be d0 a4 d1 ae d1 28 ba a1 29 a1 52 31 30"),
                (0x04, "02 4d 7d 83 00 32 38 32 39 30 a1 52 aa 5a a6 b1 af ac ba d6 a4 a6 a1 52 31"),
            ],
        )

    def test_vip_pause_and_level(self):
        rows = self.rows()
        self.assertEqual(hexs(self.run_cmd(rows, b"\x04\x40cxg\x88").to_self), [(0x1A, "64 bc c8 b0 b1 56 49 50 a5 5c af e0 a1 54")])
        self.assertEqual(hexs(self.run_cmd(rows, b"\x04\x40cxg\x89").to_self), [(0x14, self.STATUS_TAIL)])

    def test_rebirth_needs_all_attributes_at_100(self):
        msg = [(0x1A, "64 bb dd ad 6e a5 fe c4 dd a9 ca 31 30 30 a1 54")]
        rows = self.rows()
        for a in commands.ATTRS:
            rows["renwu"][0][a] = "100"
        self.assertEqual(self.run_cmd(rows, b"\x04\x40cxg\x87").to_self, [])  # 满足条件：原版会转生，这里没做
        rows["renwu"][0]["vit"] = "99"
        self.assertEqual(hexs(self.run_cmd(rows, b"\x04\x40cxg\x87").to_self), msg)
        self.assertEqual(hexs(self.run_cmd(self.rows(), b"\x04\x40cxg\x87").to_self), msg)  # 缺属性列当 0

    def test_se_and_sqsq_only_change_the_display(self):
        rows = self.rows()
        self.assertEqual(hexs(self.run_cmd(rows, cmd("se 100")).to_self), [(0x7B, "45 01 64 00 00 00")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("se -100")).to_self), [(0x7B, "45 01 9c ff ff ff")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("se 0")).to_self), [(0x7B, "45 01 00 00 00 00")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("se 5000")).to_self), [(0x1A, "64 b5 bd b4 63 a6 62 2d 31 30 30 30 a8 ec 31 30 30 30 a4 a7 b6 a1")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("sqsq")).to_self), [(0x7B, "37 01 40 42 0f 00")])
        self.assertNotIn("evil_val", rows["renwu"][0])  # 库里不动\n
    def test_wp_needs_gm_level_one_and_five_digit_known_id(self):
        rows = self.rows(gm=1)
        self.assertEqual(hexs(self.run_cmd(rows, cmd("wp 11005")).to_self), [(0x77, "fd 2a 00 00 14 01")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("wp 31011 3")).to_self), [(0x77, "23 79 00 00 32 01")])  # 药品表里的也行；后面的数量不看
        self.assertEqual([(r["item_id"], r["shuliang"]) for r in rows["item"]], [("11005", "1"), ("31011", "1")])
        self.run_cmd(rows, cmd("wp 11005"))
        self.assertEqual(rows["item"][0]["shuliang"], "2")
        for text in ("wp 99999", "wp 1100a", "wp 011005", "wp -1005"):
            self.assertEqual(hexs(self.run_cmd(rows, cmd(text)).to_self), [(0x1A, "64 b5 4c a6 b9 aa ab ab 7e")])
        for text in ("wp 1100", "wp", "WP 11005"):
            self.assertEqual(self.run_cmd(rows, cmd(text)).to_self, [])
        self.assertEqual(self.run_cmd(self.rows(gm=0), cmd("wp 11005")).to_self, [])  # 不是 GM：静默

    STATUS_TAIL = "03 56 49 50 b5 a5 af c5 a1 52 37 af c5 a1 54"

    def test_scb_status_and_exchange(self):
        r = self.run_cmd(self.rows(money=100000, points=100000), cmd("scb 0"))
        self.assertEqual(
            [(op, p) for op, p in hexs(r.to_self)],
            [
                (0x7B, "3c 01 a0 86 01 00"),
                (0x32, "6f a0 86 01 00"),
                (0x14, "03 c0 78 ad c8 c2 49 bc c6 a1 52 31 30 30 30 30 30 c2 49 a1 54"),
                (0x14, self.STATUS_TAIL),
            ],
        )
        rows = self.rows(money=1_000_000_000, points=5000)
        r = self.run_cmd(rows, cmd("scb 1"))
        self.assertEqual(hexs(r.to_self)[:2], [(0x7B, "3c 01 60 43 99 3b"), (0x32, "6f 89 13 00 00")])
        self.assertEqual((rows["renwu"][0]["jy_money"], rows["account"][0]["shangchengdianshu"]), ("999900000", "5001"))
        self.run_cmd(rows, cmd("scb 100"))
        self.assertEqual(rows["account"][0]["shangchengdianshu"], "5101")

    def test_scb_refusals(self):
        rows = self.rows(money=100000, points=10)
        self.assertEqual(hexs(self.run_cmd(rows, cmd("scb 100")).to_self), [(0x1A, "64 aa f7 bf fa a4 a3 a8 ac a1 54")])
        self.assertEqual(hexs(self.run_cmd(rows, cmd("scb 1001")).to_self)[0][1][:20], "64 b3 e6 a6 b8 a7 49")
        self.assertEqual(hexs(self.run_cmd(rows, cmd("scb -5")).to_self), [(0x1A, "64 a4 a3 af e0 ac b0 ad 74 bc c6")])
        self.assertEqual((rows["renwu"][0]["jy_money"], rows["account"][0]["shangchengdianshu"]), ("100000", "10"))

    def test_mp_changes_school_costs_points_announces_and_kicks(self):
        rows = self.rows(points=20000, school=12, master=5)
        r = self.run_cmd(rows, cmd("mp 3"))
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x32, "6f 11 27 00 00"),
                (0x14, "03 c0 78 ad c8 c2 49 bc c6 a1 52 31 30 30 30 31 c2 49 a1 54"),
                (0x7B, "41 01 0c 00 00 00"),
                (0x7B, "42 01 ed 2e 00 00"),
            ],
        )
        self.assertEqual(hexs(r.to_all), [(0x14, "0e a4 67 bb a8 a1 52 31 32 33 34 35 36 a7 f3 b4 ab a4 46 aa f9 ac a3 a1 54")])
        self.assertTrue(r.kick)
        self.assertEqual((rows["renwu"][0]["school"], rows["renwu"][0]["master"]), ("12", "12013"))
        self.assertEqual(rows["account"][0]["shangchengdianshu"], "10001")
        self.assertEqual(rows["renwu"][0]["school_skill_lv"], "7")  # 换门派不动门技

    def test_mp_digit_table(self):
        for digit, school, master in (("1", 10, 0), ("2", 11, 11005), ("5", 15, 15001), ("9", 23, 23002)):
            rows = self.rows(points=20000)
            r = self.run_cmd(rows, cmd(f"mp {digit}"))
            self.assertEqual((rows["renwu"][0]["school"], rows["renwu"][0]["master"]), (str(school), str(master)))
            self.assertEqual(hexs(r.to_self)[2:], [(0x7B, f"41 01 {school:02x} 00 00 00"), (0x7B, "42 01 " + master.to_bytes(4, "little").hex(" "))])
        rows = self.rows(points=20000)
        self.run_cmd(rows, cmd("mp 13"))  # 只看第一个字符
        self.assertEqual(rows["renwu"][0]["school"], "10")

    def test_mp_refusals(self):
        rows = self.rows(points=9998)
        msg = [(0x1A, "64 bb dd ad 6e b0 d3 ab b0 c2 49 bc c6 39 39 39 39 a4 7e af e0 a6 db a5 d1 bf ef be dc aa f9 ac a3")]
        self.assertEqual(hexs(self.run_cmd(rows, cmd("mp 2")).to_self), msg)
        self.assertEqual(hexs(self.run_cmd(rows, cmd("mp x")).to_self), msg)
        self.assertEqual(self.run_cmd(rows, cmd("mp")).to_self, [])
        rich = self.rows(points=9999)
        self.assertTrue(self.run_cmd(rich, cmd("mp 2")).kick)
        self.assertEqual(rich["account"][0]["shangchengdianshu"], "0")
        self.assertEqual(self.run_cmd(self.rows(points=50000), cmd("mp x")).to_self, [])  # 点数够但数字不认识：什么都不做

    def test_bpsm_with_school_adds_marker_and_clears_school(self):
        rows = self.rows(school=12, master=333)
        r = self.run_cmd(rows, cmd("bpsm"))
        self.assertEqual(
            hexs(r.to_self),
            [
                (0x77, "7d c3 00 00 c8 01"),
                (0x7B, "49 01 00 00 00 00"),
                (0x7B, "4a 01 00 00 00 00"),
                (0x1A, "64 a4 77 b8 67 ad 49 ab 71 ae 76 aa f9"),
                (0x7B, "42 01 00 00 00 00"),
                (0x7B, "41 01 00 00 00 00"),
            ],
        )
        rn = rows["renwu"][0]
        self.assertEqual((rn["school"], rn["master"], rn["school_skill_lv"], rn["school_skill_exp"]), ("0", "0", "0", "0"))
        self.assertEqual([m["biaoji"] for m in rows["biaoji"]], ["50045"])
        r = self.run_cmd(self.rows(school=12), cmd("bpsm"))
        rows2 = self.rows(school=12)
        rows2["biaoji"] = [{"biaoji": "50045"}]
        r = self.run_cmd(rows2, cmd("bpsm"))
        self.assertEqual(hexs(r.to_self)[0], (0x1A, "64 a4 77 b8 67 a6 b3 a6 b9 bc d0 b0 4f"))  # 已經有此標記
        self.assertEqual(len(rows2["biaoji"]), 1)

    def test_bpsm_halves_every_kungfu_level_and_reports_each_with_0x70(self):
        """对原版实测（tools/kf_compare.py bpsm-school / bpsm-odd，与原版逐帧、逐库一致）。"""
        rows = self.rows(school=10, master=0)
        rows["renwu"][0].update(study_count="55", dangqianjing="198")
        rows["kf"] = [{"kf_id": str(i), "kf_lvl": str(lv), "kf_exp": str(x)} for i, lv, x in [(1211, 1, 0), (1000, 21, 500), (3860, 12, 0), (1002, 2, 70), (1005, 0, 9)]]
        out = hexs(self.run_cmd(rows, cmd("bpsm")).to_self)
        self.assertEqual(
            [o for o in out if o[0] == 0x70],
            [
                (0x70, "37 00 c6 00 e8 03 0a 00 f4 01 00 00"),  # 1000: 21 → 10
                (0x70, "37 00 c6 00 ea 03 01 00 46 00 00 00"),  # 1002: 2 → 1
                (0x70, "37 00 c6 00 ed 03 00 00 09 00 00 00"),  # 1005: 0 → 0 也回
                (0x70, "37 00 c6 00 bb 04 00 00 00 00 00 00"),  # 1211: 1 → 0；3860 转生武功不动也不回
            ],
        )
        self.assertEqual([o[0] for o in out][:3] + [out[-3][0]], [0x77, 0x7B, 0x7B, 0x1A])  # 70 在 7B 4A 之后、1A 之前
        self.assertEqual({r["kf_id"]: r["kf_lvl"] for r in rows["kf"]}, {"1000": "10", "1002": "1", "1005": "0", "1211": "0", "3860": "12"})
        none = self.rows(school=0)
        none["kf"] = [{"kf_id": "1000", "kf_lvl": "20", "kf_exp": "0"}]
        self.run_cmd(none, cmd("bpsm"))
        self.assertEqual(none["kf"][0]["kf_lvl"], "20")  # 没有门派不减半

    def test_bpsm_without_school_only_clears_master(self):
        rows = self.rows(school=0, master=333)
        r = self.run_cmd(rows, cmd("bpsm"))
        self.assertEqual(hexs(r.to_self), [(0x7B, "42 01 00 00 00 00"), (0x7B, "41 01 00 00 00 00")])
        rn = rows["renwu"][0]
        self.assertEqual((rn["master"], rn["school_skill_lv"], rn["school_skill_exp"]), ("0", "7", "555"))


if __name__ == "__main__":
    unittest.main()
