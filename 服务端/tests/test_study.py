"""消点（C2S 0x5E）：期望值来自对原版 8617293 号的实测（2026-10，tools/kf_compare.py xd-*，与原版逐帧、逐库一致）。"""

import random
import unittest

from jyserver.kungfu import Kungfu, Master
from jyserver.study import need, study

TABLE = Kungfu(
    coef={1014: 2.0, 1005: 1.2, 8001: 1.0, 8006: 5.0, 8012: 1.0, 8013: 1.0, 8017: 1.5},
    masters={(10003, 1014): Master(80, 0, 1, 2411), (12003, 1201): Master(120, 12, 1, 4101), (10041, 1005): Master(60, 0, 1, 2416)},
)


def rows(**kw):
    ren = {"name": "123456", "jyid": "8617293", "study_count": "30000", "dangqianjing": "1000", "wint": "33", "school": "0", "map": "2411",
           "daofa": "3", "daofaexp": "0", "neigong": "3", "neigongexp": "0", "dushushizi": "3", "dushushiziexp": "0", "boji": "3", "bojiexp": "0",
           "zuidajing": "1000", "zuidashen": "2000", "zuidaxue": "3000", "zuidanei": "4000", "str": "31", "agi": "36"}
    ren.update({k: str(v) for k, v in kw.items()})
    return {"renwu": [ren], "kf": []}


def pay(master, kid, pts):
    return master.to_bytes(2, "little") + kid.to_bytes(2, "little") + pts.to_bytes(2, "little") + bytes(5)


def hexs(frames):
    return [(op, p.hex(" ")) for op, p, _ in frames]


class FirstRng:
    """随机挑选永远挑第一个，让掉级的测试可复现。"""

    def choice(self, seq):
        return seq[0]


def run(r, master, kid, pts, rng=None):
    return study(r, TABLE, rng or random.Random(1), pay(master, kid, pts))


class Levels(unittest.TestCase):
    def test_threshold_is_coef_times_next_level_cubed_truncated(self):
        self.assertEqual([need(2, l) for l in (3, 4, 5, 6)], [128, 250, 432, 686])  # 对原版 1014 实测
        self.assertEqual([need(1.5, l) for l in (3, 4, 5, 6, 7, 8, 9)], [96, 187, 324, 514, 768, 1093, 1500])  # 读书识字，每级取整数部分
        self.assertEqual(need(1.2, 3), 76)  # 单精度系数：1.2 × 64 = 76.8

    def test_basic_skill_gain_is_wisdom_times_one_and_a_half(self):
        r = rows()
        res = run(r, 10039, 8001, 1)
        self.assertEqual(hexs(res.to_self), [(0x68, "41 1f 03 00 31 00 00 00 2f 75 e8 03")])  # 33 × 1.5 = 49.5 → 49
        self.assertEqual((r["renwu"][0]["daofa"], r["renwu"][0]["daofaexp"], r["renwu"][0]["study_count"]), ("3", "49", "29999"))
        res = run(r, 10039, 8001, 100)
        self.assertEqual((r["renwu"][0]["daofa"], r["renwu"][0]["daofaexp"]), ("11", "679"))  # 49 + 4950 − Σ(4³…10³)
        self.assertEqual(hexs(res.to_self), [(0x68, "41 1f 0b 00 a7 02 00 00 cb 74 e8 03")])

    def test_basic_skills_ignore_master_and_map(self):
        r = rows(map=100)
        self.assertEqual(run(r, 60000, 8001, 1).to_self[0][0], 0x68)

    def test_neigong_raises_the_four_maxima_and_always_reports_them(self):
        r = rows()
        res = run(r, 10039, 8006, 100)
        self.assertEqual(
            hexs(res.to_self),
            [(0x68, "46 1f 07 00 ba 04 00 00 cc 74 e8 03"), (0x7B, "15 01 28 0a 00 00"), (0x7B, "17 01 f8 11 00 00"), (0x7B, "19 01 10 0e 00 00"), (0x7B, "1c 01 b4 0f 00 00")],
        )
        self.assertEqual([r["renwu"][0][c] for c in ("zuidajing", "zuidashen", "zuidaxue", "zuidanei")], ["2600", "3600", "4600", "4020"])
        self.assertEqual(len([f for f in run(rows(), 10039, 8006, 1).to_self if f[0] == 0x7B]), 4)  # 没升级也发

    def test_every_ten_levels_gives_an_attribute_point(self):
        r = rows()
        res = run(r, 39032, 8017, 100)
        self.assertEqual((r["renwu"][0]["dushushizi"], r["renwu"][0]["dushushiziexp"], r["renwu"][0]["wint"]), ("10", "468", "34"))
        self.assertEqual(hexs(res.to_self)[-1], (0x7B, "20 01 22 00 00 00"))
        r = rows()
        run(r, 10039, 8012, 100)
        self.assertEqual(r["renwu"][0]["str"], "32")
        self.assertEqual([f for f in run(rows(), 10039, 8012, 1).to_self if f[0] == 0x7B], [])  # 没跨十级不发

    def test_level_cap_clamps_and_warns_before_the_report(self):
        r = rows(study_count=3_000_000, wint=100, daofa=148)
        res = run(r, 10039, 8001, 2)  # 点数 2 = 全部学习点
        self.assertEqual(hexs(res.to_self), [(0x1A, "64 b6 57 b9 4c ae f8 c2 49 af c5 bc c6"), (0x68, "41 1f 96 00 34 f2 37 1a 00 00 e8 03")])
        self.assertEqual((r["renwu"][0]["daofa"], r["renwu"][0]["daofaexp"], r["renwu"][0]["study_count"]), ("150", "439874100", "0"))


class NormalKungfu(unittest.TestCase):
    def kf_rows(self, **kw):
        r = rows(wint=60, **kw)
        r["kf"] = [{"kf_id": "1014", "kf_lvl": "3", "kf_exp": "110"}]
        return r

    def test_gain_and_level_up(self):
        r = self.kf_rows()
        res = run(r, 10003, 1014, 1)  # 60 × 1.5 = 90；110 + 90 − 128 = 72
        self.assertEqual(hexs(res.to_self), [(0x68, "f6 03 04 00 48 00 00 00 2f 75 e8 03")])
        self.assertEqual((r["kf"][0]["kf_lvl"], r["kf"][0]["kf_exp"]), ("4", "72"))

    def test_not_owned_just_announces_even_when_map_and_school_are_right(self):
        r = rows()
        res = run(r, 10003, 1014, 1)
        self.assertEqual((res.to_self, [(pos, f[1]) for pos, f in res.inline]), ([], [(0, b"\x0e123456\xb9\xc1\xb8\xd5\xa8\xea\xaa\x5a\xa5\x5c:1014")]))
        self.assertEqual(r["renwu"][0]["study_count"], "30000")

    def test_unknown_pair_announces_to_self_then_to_everyone(self):
        r = self.kf_rows()
        res = run(r, 60000, 1014, 1)
        self.assertEqual(res.to_self[0][1][:1], b"\x03")
        self.assertEqual([(pos, f[1][:7]) for pos, f in res.inline], [(1, b"\x0e123456")])
        self.assertTrue(res.to_self[0][1].endswith(b"60000\xa1\x511014"))

    def test_wrong_map_text_first_then_one_level_off_a_random_kungfu(self):
        r = self.kf_rows(map=100, school=0)
        r["kf"].append({"kf_id": "1018", "kf_lvl": "9", "kf_exp": "0"})
        res = run(r, 10003, 1014, 3, FirstRng())
        self.assertEqual([(pos, f[1][:1]) for pos, f in res.inline], [(0, b"\x0e")])
        self.assertEqual(hexs(res.to_self), [(0x70, "30 75 e8 03 f6 03 02 00 6e 00 00 00")])  # 3 → 2，经验不动，学点没扣
        self.assertEqual((r["kf"][0]["kf_lvl"], r["kf"][1]["kf_lvl"], r["renwu"][0]["study_count"]), ("2", "9", "30000"))
        single = self.kf_rows(map=100, school=0)  # 只有一门武功：从不掉级
        self.assertEqual(run(single, 10003, 1014, 3, FirstRng()).to_self, [])
        self.assertEqual(single["kf"][0]["kf_lvl"], "3")

    def test_wrong_school_reports_the_drop_first_and_unowned_just_announces(self):
        r = rows(map=4101, school=0)
        r["kf"] = [{"kf_id": "1201", "kf_lvl": "6", "kf_exp": "0"}, {"kf_id": "1018", "kf_lvl": "4", "kf_exp": "0"}]
        res = run(r, 12003, 1201, 3, FirstRng())
        self.assertEqual([op for op, _, _ in res.to_self], [0x70])
        self.assertEqual([pos for pos, _ in res.inline], [1])  # 70 在前、文字在后
        r2 = rows(map=4101, school=0)
        res2 = run(r2, 12003, 1201, 3)
        self.assertEqual((res2.to_self, [pos for pos, _ in res2.inline]), ([], [0]))  # 没有这门武功：只有「嘗試刷武功」
        r["renwu"][0]["school"] = "12"  # 门派对了
        self.assertEqual(run(r, 12003, 1201, 3).to_self[0][0], 0x68)

    def test_silent_cases_zero_points_and_all_points(self):
        r = self.kf_rows(study_count=10)
        self.assertEqual(run(r, 10003, 1014, 50).to_self, [])  # 点数比学习点多：在所有检查之前就静默
        self.assertEqual(run(self.kf_rows(map=100, study_count=10), 60000, 1014, 50).inline, [])
        self.assertEqual(study(r, TABLE, random.Random(1), b"\x13\x27\xf6\x03\x01").to_self, [])  # 载荷不够 6 字节
        echo = run(r, 10003, 1014, 0)
        self.assertEqual(hexs(echo.to_self), [(0x68, "f6 03 03 00 6e 00 00 00 0a 00 e8 03")])
        self.assertEqual(r["renwu"][0]["study_count"], "10")
        run(r, 10003, 1014, 2)
        self.assertEqual(r["renwu"][0]["study_count"], "0")  # 2 = 全部


if __name__ == "__main__":
    unittest.main()
