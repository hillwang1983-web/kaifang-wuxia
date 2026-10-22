"""登录序列生成器 vs 原版真实回包（快照夹具 data/fixtures/char-*.json）。

物品耐久 / 攻防要读原版服务端的 data 目录；那个目录不在仓库里，找不到就跳过整组。
"""

import json
import unittest
from pathlib import Path

from jyserver.state import ItemTable, Template, appear_frames, build_login_stream, disappear_frames, to_big5

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "data" / "fixtures"
from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)


def _diff(want, got):
    """逐帧比较，忽略 0x1E 的计时字节（载荷[0]）和 0x08 的随机字节（载荷[6]）。返回问题描述列表。"""
    problems = []
    if len(want) != len(got):
        problems.append(f"frame count {len(want)} != {len(got)}")
    for i, (w, g) in enumerate(zip(want, got)):
        if (w[0], w[2]) != (g[0], g[2]) or len(w[1]) != len(g[1]):
            problems.append(f"frame {i}: header/length")
            continue
        skip = {0, 1, 2, 3} if i == 0 else {6} if w[0] == 0x08 else set()
        bad = [k for k in range(len(w[1])) if w[1][k] != g[1][k] and k not in skip]
        if bad:
            problems.append(f"frame {i} (0x{w[0]:02x}): bytes {bad[:8]}")
    return problems


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class LoginStreamMatchesOriginal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Template.load(FIX / "char-8617293.json")
        cls.table = ItemTable.load(DATA_DIR)

    def check(self, name):
        fix = json.loads((FIX / name).read_text(encoding="utf-8"))
        want = [(f["opcode"], bytes.fromhex(f["payload"]), f["wide"]) for f in fix["frames"][1:]]
        king = any(f["opcode"] == 0x14 and bytes.fromhex(f["payload"])[:1] == b"\x0e" for f in fix["frames"])
        got = build_login_stream(self.template, fix["rows"], self.table, sponsor_king=king)
        self.assertEqual(_diff(want, got), [])

    def test_template_character(self):
        self.check("char-8617293.json")

    def test_cjk_name_and_shop_points(self):
        self.check("char-1234567.json")

    def test_sponsor_king_and_derived_strengths(self):
        self.check("char-123456.json")

    def test_cloned_character(self):
        self.check("char-9999001.json")

    def test_kungfu_rows_are_nine_bytes_apart(self):
        """原版实测（2026-10-20，8617293 写入 4 条武功：id 1–4、等级 5–8、经验 1000–4000 后登录抓到的 0x1E 武功区）：行距 9，最多 16 行。"""
        rows = json.loads((FIX / "char-8617293.json").read_text(encoding="utf-8"))["rows"]
        rows["kf"] = [{"jyid": "8617293", "kf_id": str(i), "kf_lvl": str(4 + i), "kf_exp": str(i * 1000)} for i in (1, 2, 3, 4)]
        got = [f for f in build_login_stream(self.template, rows, self.table) if f[0] == 0x1E][0][1]
        want = bytes.fromhex("0a 04 00 05 00 e8 03 00 00 01 00 00 06 00 d0 07 00 00 02 00 00 07 00 b8 0b 00 00 03 00 00 08 00 a0 0f 00 00 04 00 00") + bytes(9 * 12)
        at = got.index(want[:6])
        self.assertEqual(got[at : at + len(want)], want)
        rows["kf"] = [{"jyid": "8617293", "kf_id": str(100 + i), "kf_lvl": "1", "kf_exp": "0"} for i in range(20)]  # 超过 16 条只发前 16
        got = [f for f in build_login_stream(self.template, rows, self.table) if f[0] == 0x1E][0][1]
        self.assertEqual(got[at + 1], 16)

    def test_strengths_are_sum_of_equipment(self):
        fix = json.loads((FIX / "char-123456.json").read_text(encoding="utf-8"))
        self.assertEqual(self.table.strengths(fix["rows"]["renwu"][0]), (1610, 8890))


class AppearFrames(unittest.TestCase):
    """别人上线时其他在线玩家收到的帧，对照 data/fixtures/appear-*.json（原版实测）。"""

    def check(self, jyid, king):
        want = json.loads((FIX / f"appear-{jyid}.json").read_text(encoding="utf-8"))["frames"]
        want = [(f["opcode"], bytes.fromhex(f["payload"]), f["wide"]) for f in want]
        rows = json.loads((FIX / f"char-{jyid}.json").read_text(encoding="utf-8"))["rows"]
        m, x, y = (int.from_bytes(want[2][1][i : i + 2], "little") for i in (4, 6, 8))  # 用实测包里的位置
        got = appear_frames(rows, position=(m, x, y), sponsor_king=king)
        self.assertEqual([(op, w) for op, _, w in got], [(op, w) for op, _, w in want])
        for (op, g, _), (_, w, _) in zip(got, want):
            self.assertEqual(g.hex(" "), w.hex(" "), f"opcode 0x{op:02x}")

    def test_plain_character(self):
        self.check(1234567, False)

    def test_character_with_equipment_and_sponsor_king(self):
        self.check(123456, True)

    def test_disappear(self):
        rows = json.loads((FIX / "char-8617293.json").read_text(encoding="utf-8"))["rows"]
        (op1, p1, w1), (op2, p2, w2) = disappear_frames(rows)
        self.assertEqual((op1, p1.hex(), w1), (0x05, "4d7d830000", False))
        self.assertEqual((op2, w2, p2.hex()), (0x14, True, "08aab1ae61a152313233343536d6c3b67db4e5c0b8"))


class Big5(unittest.TestCase):
    def test_native_big5_chars_are_kept(self):
        self.assertEqual(to_big5("游").hex(), "b4e5")  # 原版不把 游 转成 遊

    def test_simplified_chars_use_table(self):
        self.assertEqual(to_big5("戏").hex(), "c0b8")

    def test_unknown_char_becomes_question_mark(self):
        self.assertEqual(to_big5("\U0001f600"), b"?")

    def test_cp950_chars_are_not_converted_again(self):
        # 原版实测：万 体 气 极 网 儿 蚕 恒 本身就在 CP950 里，不转繁体；噼 勐 不在 BIG5 里 → 全角空格
        self.assertEqual(to_big5("万体气极网儿蚕恒").hex(), "c945ca5ec961cce5ca49a449d3c9f9da")
        self.assertEqual(to_big5("噼勐").hex(), "a140a140")
        self.assertEqual(to_big5("．").hex(), "a14f")

    def test_all_wugong_names_match_the_original_byte_for_byte(self):
        """tools/name_map_probe.py 向原版问来的 846 个武功名（C2S 0x61 装备没有的武功 → 全服公告里带名字）。"""
        p = Path(__file__).resolve().parent.parent / "data" / "orig_name_bytes.json"
        for kid, v in json.loads(p.read_text(encoding="utf-8")).items():
            self.assertEqual(to_big5(v["gbk"]).hex(), v["big5"], kid)


if __name__ == "__main__":
    unittest.main()
