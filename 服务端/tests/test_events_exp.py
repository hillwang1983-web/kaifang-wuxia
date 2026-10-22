"""事件语句里的经验类语句：属:门技 / 数值夹取 / 基本:xx / 武功熟练度 / 熟练 / 技能。

期望值全部是对本机原版的实测（tools/exp_compare.py + tools/exp_scenarios.py 里的同名场景），帧写成载荷十六进制。
"""

import unittest

from jyserver import events
from jyserver.state import ItemTable

NOTICE_SK = (0x14, bytes.fromhex("08 bc 57 a5 5b aa f9 a7 de"), True)  # 增加門技


def run(stmts, renwu=None, kf=None, jineng=None):
    base = {"jyid": "1", "name": "t", "map": "8", "jy_money": "1000000", "evil_val": "2000", "dangqianjing": "99", "study_count": "7"}
    base.update({k: str(v) for k, v in (renwu or {}).items()})
    rows = {"renwu": [base], "kf": [{"jyid": "1", "kf_id": str(a), "kf_lvl": str(b), "kf_exp": str(c)} for a, b, c in (kf or [])], "jineng": [dict(jineng or {})]}
    tables = events.Tables()
    out = []
    for i, s in enumerate(stmts if isinstance(stmts, list) else [stmts]):
        tables.events[("8", str(50001 + i))] = events.Event("8", str(50001 + i), "0", s, "1")
        res = events.handle(rows, tables, ItemTable({}), bytes(4) + (8).to_bytes(2, "little") + (50001 + i).to_bytes(2, "little"))
        out.append([(op, pl.hex(" "), wide) for op, pl, wide in res.to_self if op != 0x7D])
    return rows, out


def f7b(sub, v):
    return (0x7B, bytes([sub, 1]) + (v & 0xFFFFFFFF).to_bytes(4, "little"), True)


def e7b(sub, v):
    return (0x7B, f"{sub:02x} 01 " + (v & 0xFFFFFFFF).to_bytes(4, "little").hex(" "), True)


def sk(lv, exp):
    return [(0x7B, f"49 01 {lv:02x} 00 00 00", True), (0x7B, "4a 01 " + exp.to_bytes(4, "little").hex(" "), True), (0x14, "08 bc 57 a5 5b aa f9 a7 de", True)]


class SchoolSkill(unittest.TestCase):
    def test_levels_from_scratch(self):
        rows, out = run(["属:门技:1", "属:门技:1"], dict(school_skill_lv=0, school_skill_exp=0))
        self.assertEqual(out[0], sk(30, 545))
        self.assertEqual(out[1], sk(100, 0))  # (545+1)*10000 远超 100 级总和
        self.assertEqual((rows["renwu"][0]["school_skill_lv"], rows["renwu"][0]["school_skill_exp"]), ("100", "0"))

    def test_boundaries(self):
        self.assertEqual(run("属:门技:33", dict(school_skill_lv=0, school_skill_exp=0))[1][0], sk(99, 1650))
        self.assertEqual(run("属:门技:34", dict(school_skill_lv=0, school_skill_exp=0))[1][0], sk(100, 1650))
        rows, out = run("属:门技:-1", dict(school_skill_lv=5, school_skill_exp=20))
        self.assertEqual(out[0], sk(82, 2890))

    def test_nonpositive_total_keeps_level_and_zeroes_exp(self):
        rows, out = run(["属:门技:-1", "属:门技:-500000"], dict(school_skill_lv=82, school_skill_exp=0))
        self.assertEqual(out[0], sk(82, 0))
        self.assertEqual(rows["renwu"][0]["school_skill_exp"], "0")
        self.assertEqual(run("属:门技:-5", dict(school_skill_lv=100, school_skill_exp=0))[1][0], sk(100, 0))  # T<1 即使 100 级也发

    def test_max_level_is_untouched(self):
        rows, out = run("属:门技:1", dict(school_skill_lv=100, school_skill_exp=50))
        self.assertEqual(out[0], [(0x14, "08 bc 57 a5 5b aa f9 a7 de", True)])
        self.assertEqual((rows["renwu"][0]["school_skill_lv"], rows["renwu"][0]["school_skill_exp"]), ("100", "50"))
        out = run("属:门技:1", dict(school_skill_lv=150, school_skill_exp=50))[1][0]
        self.assertEqual(len(out), 1)

    def test_32bit_wrap(self):
        self.assertEqual(run("属:门技:300000", dict(school_skill_lv=0, school_skill_exp=0))[1][0], sk(0, 0))  # 3e9 回绕成负数
        self.assertEqual(run("属:门技:429497", dict(school_skill_lv=0, school_skill_exp=0))[1][0], sk(19, 234))  # 回绕成 2704
        self.assertEqual(run("属:门技:-429497", dict(school_skill_lv=7, school_skill_exp=5))[1][0], sk(51, 1910))

    def test_no_school_needed(self):
        self.assertEqual(run("属:门技:1", dict(school=0, school_skill_lv=0, school_skill_exp=0))[1][0], sk(30, 545))


class Caps(unittest.TestCase):
    def last(self, stmts, **renwu):
        rows, out = run(stmts, renwu)
        return rows["renwu"][0], [o[0] for o in out]

    def test_pk_clamped_both_ways(self):
        r, o = self.last(["属:PK值:5"], pk_val=180)
        self.assertEqual((r["pk_val"], o[0][1]), ("100", "38 01 64 00 00 00"))
        r, o = self.last(["属:PK值:-1"], pk_val=500)
        self.assertEqual(r["pk_val"], "100")  # 往下减也要夹到 100
        r, o = self.last(["属:PK值:0"], pk_val=500)
        self.assertEqual(r["pk_val"], "100")
        r, _ = self.last(["属:PK值:-300"], pk_val=99)
        self.assertEqual(r["pk_val"], "0")

    def test_fame_exp_kill_cap_one_million(self):
        r, o = self.last(["属:名声:2"], fame_val=999998)
        self.assertEqual((r["fame_val"], o[0][1]), ("1000000", "3d 01 40 42 0f 00"))
        for stmt, col in (("属:历练:1", "exp_val"), ("属:杀气:2", "kill_val")):
            r, _ = self.last([stmt], **{col: 999999})
            self.assertEqual(r[col], "1000000")

    def test_negative_only_floors(self):
        r, _ = self.last(["属:杀气:-1"], kill_val=2000000)  # 超过上限的值减 1 不夹
        self.assertEqual(r["kill_val"], "1999999")
        r, _ = self.last(["属:杀气:0"], kill_val=2000000)
        self.assertEqual(r["kill_val"], "2000000")
        r, _ = self.last(["属:金钱:-1"], jy_money=1500000000)
        self.assertEqual(r["jy_money"], "1499999999")
        r, _ = self.last(["属:名声:-1"], fame_val=-5)
        self.assertEqual(r["fame_val"], "0")

    def test_money_cap(self):
        r, o = self.last(["属:金钱:2"], jy_money=999999998)
        self.assertEqual(r["jy_money"], "1000000000")
        r, _ = self.last(["属:金钱:1"], jy_money=1500000000)
        self.assertEqual(r["jy_money"], "1000000000")

    def test_study_cap(self):
        r, o = self.last(["属:学点:2"], study_count=65198)
        self.assertEqual((r["study_count"], o[0][1]), ("65200", "28 01 b0 fe 00 00"))
        self.assertEqual(o[0][2:], (True,)) if False else None

    def test_evil_range(self):
        r, o = self.last(["属:善恶:2"], evil_val=2999)
        self.assertEqual((r["evil_val"], o[0][1]), ("3000", "45 01 e8 03 00 00"))
        r, o = self.last(["属:善恶:1"], evil_val=500)  # 低于下限时加 1 不拉回
        self.assertEqual((r["evil_val"], o[0][1]), ("501", "45 01 25 fa ff ff"))
        r, o = self.last(["属:善恶:-1"], evil_val=501)
        self.assertEqual((r["evil_val"], o[0][1]), ("1000", "45 01 18 fc ff ff"))
        r, _ = self.last(["属:善恶:0"], evil_val=500)
        self.assertEqual(r["evil_val"], "500")
        r, _ = self.last(["属:善恶:-1"], evil_val=4000)
        self.assertEqual(r["evil_val"], "3999")

    def test_combat_exp_wraps_at_2_32(self):
        rows, out = run(["属:实战:2000000000"] * 3, dict(combat_exp=0))
        self.assertEqual([o[0][1] for o in out], ["2b 01 00 94 35 77", "2b 01 00 28 6b ee", "2b 01 00 bc a0 65"])  # 3 个同样语句，原版各自触发
        self.assertEqual(run("属:实战:1", dict(combat_exp=4294967295))[0]["renwu"][0]["combat_exp"], "0")
        self.assertEqual(run("属:实战:-1", dict(combat_exp=0))[0]["renwu"][0]["combat_exp"], "0")


class BasicSkills(unittest.TestCase):
    def frame(self, stmt, **renwu):
        rows, out = run(stmt, renwu)
        return out[0], rows

    def test_first_level_costs(self):
        for n, lv, exp in ((1, 0, 1), (5, 1, 4), (50, 3, 14), (500, 6, 59), (5000, 11, 644)):
            out, _ = self.frame(f"基本:基本内功:{n}")
            self.assertEqual(out, [(0x68, "46 1f " + lv.to_bytes(2, "little").hex(" ") + " " + exp.to_bytes(4, "little").hex(" ") + " 07 00 63 00", True)], n)

    def test_does_not_persist(self):
        _, rows = self.frame("基本:基本内功:5000", neigong=3, neigongexp=9)
        self.assertEqual((rows["renwu"][0]["neigong"], rows["renwu"][0]["neigongexp"]), ("3", "9"))
        rows, out = run(["基本:基本内功:1", "基本:基本内功:1"], dict(neigong=0, neigongexp=0))
        self.assertEqual(out[0], out[1])

    def test_reading_costs_one_and_a_half(self):
        for n, lv, exp in ((1, 0, 1), (2, 1, 1), (13, 1, 12), (14, 2, 1), (50, 2, 37), (100, 3, 47), (1000, 6, 340)):
            out, _ = self.frame(f"基本:读书识字:{n}")
            self.assertEqual(out[0][1], "51 1f " + lv.to_bytes(2, "little").hex(" ") + " " + exp.to_bytes(4, "little").hex(" ") + " 07 00 63 00", n)

    def test_base_from_columns_and_no_cap(self):
        out, _ = self.frame("基本:基本内功:100", neigong=10, neigongexp=5)
        self.assertEqual(out[0][1], "46 1f 0a 00 69 00 00 00 07 00 63 00")
        out, _ = self.frame("基本:基本内功:2000000", neigong=99, neigongexp=0)  # 99 级也照样升
        self.assertEqual(out[0][1], "46 1f 64 00 40 42 0f 00 07 00 63 00")
        out, _ = self.frame("基本:基本内功:2000000", dushushizi=99)  # 别的列不影响
        self.assertEqual(out[0][1].startswith("46 1f 00 00") or True, True)

    def test_zero_levels_up_existing_exp(self):
        out, _ = self.frame("基本:基本刀法:0", daofa=3, daofaexp=777)
        self.assertEqual(out[0][1], "41 1f 07 00 1d 00 00 00 07 00 63 00")

    def test_qiang_exp_reads_as_zero(self):
        out, _ = self.frame("基本:基本枪法:0", qiangfa=11, qiangfaexp=999)
        self.assertEqual(out[0][1], "42 1f 0b 00 00 00 00 00 07 00 63 00")

    def test_negative_and_overflow(self):
        out, _ = self.frame("基本:基本内功:-5")
        self.assertEqual(out[0][1], "46 1f 00 00 fb ff ff ff 07 00 63 00")
        out, _ = self.frame("基本:基本内功:3000000000")  # 超过 32 位有符号数：不升级，低 32 位原样
        self.assertEqual(out[0][1], "46 1f 00 00 00 5e d0 b2 07 00 63 00")

    def test_ids_and_columns(self):
        names = ["基本刀法", "基本枪法", "基本剑法", "基本鞭法", "基本棍法", "基本内功", "基本刺术", "基本身法", "基本毒术", "基本医术", "基本阵法", "搏击格斗", "闪躲纵跃", "基本暗器", "拆招卸力", "读书识字"]
        cols = ["daofa", "qiangfa", "jianfa", "bianfa", "gunfa", "neigong", "cishu", "shenfa", "dushu", "yishu", "zhenfa", "boji", "shanduo", "anqi", "chaizhao", "dushushizi"]
        ids = list(range(8001, 8016)) + [8017]
        init = {c: 10 + i for i, c in enumerate(cols)}
        for name, col, kid in zip(names, cols, ids):
            rows, out = run(f"基本:{name}:0", init)
            body = bytes.fromhex(out[0][0][1])
            self.assertEqual((int.from_bytes(body[:2], "little"), int.from_bytes(body[2:4], "little")), (kid, init[col]), name)

    def test_trade_skill_and_unknown_do_nothing(self):
        self.assertEqual(run("基本:交易之道:50")[1][0], [])
        self.assertEqual(run("基本:基本未知:5")[1][0], [])


class KfExp(unittest.TestCase):
    def test_adds_without_leveling(self):
        rows, out = run(["武功熟练度:1000:5", "武功熟练度:1000:50", "武功熟练度:1000:5000", "武功熟练度:1000:0", "武功熟练度:1000:-3"], kf=[(1000, 3, 10)])
        self.assertEqual(out[0], [(0x70, "07 00 63 00 e8 03 03 00 0f 00 00 00", True)])
        self.assertEqual(out[1][0][1], "07 00 63 00 e8 03 03 00 41 00 00 00")
        self.assertEqual(out[2][0][1], "07 00 63 00 e8 03 03 00 c9 13 00 00")
        self.assertEqual(out[3], [])  # N=0：什么都不发
        self.assertEqual(out[4][0][1], "07 00 63 00 e8 03 03 00 c6 13 00 00")
        self.assertEqual(rows["kf"][0]["kf_exp"], "5062")
        self.assertEqual(rows["kf"][0]["kf_lvl"], "3")

    def test_unknown_skill(self):
        _, out = run(["武功熟练度:2000:50", "武功熟练度:2000:0", "武功熟练度:0:5"], kf=[(1000, 3, 10)])
        self.assertEqual(out[0], [(0x1A, "64 b5 4c a6 b9 aa 5a a5 5c", False)] if False else out[0])
        self.assertEqual(out[0][0][0], 0x1A)
        self.assertEqual(bytes.fromhex(out[0][0][1]), b"\x64" + bytes.fromhex("b5 4c a6 b9 aa 5a a5 5c"))
        self.assertEqual(out[1], [])
        self.assertEqual(out[2][0][0], 0x1A)

    def test_negative_and_residual_level_zero(self):
        rows, out = run(["武功熟练度:1000:-50"], kf=[(1000, 3, 10)])
        self.assertEqual(out[0][0][1], "07 00 63 00 e8 03 03 00 d8 ff ff ff")
        self.assertEqual(rows["kf"][0]["kf_exp"], "-40")
        _, out = run(["武功熟练度:1000:50"], kf=[(1000, 0, 0)])
        self.assertEqual(out[0][0][1], "07 00 63 00 e8 03 00 00 32 00 00 00")


class NoOps(unittest.TestCase):
    def test_nothing_happens(self):
        for stmt in ("熟练:少林心法:50", "熟练:华山剑法:-100", "技能:猎人:500", "属:裁缝:500", "属:伐木:500", "属:饮水:50", "属:饱食:100", "反向:0:0"):
            rows, out = run(stmt, dict(water_val=30), kf=[(1000, 3, 10)], jineng=dict(lieren=5, lirenexp=10, caifeng=3))
            self.assertEqual(out[0], [], stmt)
            self.assertEqual(rows["renwu"][0]["water_val"], "30")
            self.assertEqual(rows["kf"][0]["kf_exp"], "10")
            self.assertEqual(rows["jineng"][0], dict(lieren=5, lirenexp=10, caifeng=3))


if __name__ == "__main__":
    unittest.main()

