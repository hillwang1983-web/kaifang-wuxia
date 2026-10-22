"""武功装备 / 删除：期望值来自对原版 8617293 号的实测（2026-10，tools/kf_compare.py）。"""

import unittest

from jyserver.kungfu import Kungfu, Req, delete, equip, forget, learn, meets, persistable, read_book

PW = "8617293"
TABLE = Kungfu({1001: "少林九阳功", 3879: "唐诗剑法", 1024: "风云手", 1047: "五行连环拳"})


def rows():
    return {
        "renwu": [{"name": "123456"}],
        "kf": [{"kf_id": str(a), "kf_lvl": str(b), "kf_exp": str(c)} for a, b, c in ((1000, 10, 100), (1002, 5, 50), (1004, 4, 40), (3860, 10, 0), (9999, 3, 0))],
    }


def le(n):
    return n.to_bytes(2, "little")


def pay(n_pw=PW, ids=(1004,), head=1, x=0):
    return bytes([head, len(n_pw)]) + n_pw.encode() + bytes([x]) + b"".join(le(i) for i in ids)


class EquipTests(unittest.TestCase):
    def test_owned_is_echoed_for_slots_0_to_14_only(self):
        r = rows()
        for slot in (0, 1, 14):
            res = equip(r, TABLE, bytes([slot]) + le(1000))
            self.assertEqual(res.to_self, [(0x6E, bytes([slot]) + le(1000), False)])
            self.assertEqual(res.to_all, [])
        for slot in (15, 16, 255):
            res = equip(r, TABLE, bytes([slot]) + le(1000))
            self.assertEqual((res.to_self, res.to_all), ([], []))

    def test_owned_but_unknown_to_the_table_and_rebirth_are_fine(self):
        self.assertEqual(equip(rows(), TABLE, b"\x01" + le(9999)).to_self[0][1], b"\x01" + le(9999))
        self.assertEqual(equip(rows(), TABLE, b"\x01" + le(3860)).to_self[0][1], b"\x01" + le(3860))
        # ID 0：不管槽位、不查拥有，回显
        for slot in (0, 14, 15, 255):
            self.assertEqual(equip(rows(), TABLE, bytes([slot]) + le(0)).to_self, [(0x6E, bytes([slot]) + le(0), False)])

    def test_unowned_announces_to_everyone_with_name_when_known(self):
        res = equip(rows(), TABLE, b"\x01" + le(1001))
        self.assertEqual(res.to_self, [])
        (op, p, wide), = res.to_all
        self.assertEqual((op, wide), (0x14, True))
        self.assertEqual(p.hex(" "), "0e 31 32 33 34 35 36 b9 c1 b8 d5 a8 ea aa 5a a5 5c a1 54 a4 d6 aa 4c a4 45 b6 a7 a5 5c")
        # 表里的简体名转繁体：风云手 → 風云手（云不变，实测）
        self.assertTrue(equip(rows(), TABLE, b"\x01" + le(1024)).to_all[0][1].endswith(bytes.fromhex("ad b7 a4 aa a4 e2")))
        # 不在表里：只有「嘗試刷武功﹗」，槽位无所谓
        p = equip(rows(), TABLE, b"\xff" + le(0xFFFF)).to_all[0][1]
        self.assertEqual(p.hex(" "), "0e 31 32 33 34 35 36 b9 c1 b8 d5 a8 ea aa 5a a5 5c a1 54")

    def test_short_payload_is_silent_and_trailing_bytes_are_ignored(self):
        for p in (b"", b"\x01", b"\x01\xe8"):
            res = equip(rows(), TABLE, p)
            self.assertEqual((res.to_self, res.to_all), ([], []))
        self.assertEqual(equip(rows(), TABLE, b"\x01" + le(1000) + b"\xaa\xbb").to_self[0][1], b"\x01" + le(1000))


class DeleteTests(unittest.TestCase):
    def test_deleting_zeroes_level_and_exp_and_replies_per_id(self):
        r = rows()
        res = delete(r, PW, pay(ids=(1004, 1002)))
        self.assertEqual(res.to_self, [(0x7A, b"\x02" + le(1004), False), (0x7A, b"\x02" + le(1002), False)])
        self.assertEqual([(k["kf_id"], k["kf_lvl"], k["kf_exp"]) for k in r["kf"]][:3], [("1000", "10", "100"), ("1002", "0", "0"), ("1004", "0", "0")])
        # 还在列表里：再删照样回包，也还能装备
        self.assertEqual(delete(r, PW, pay(ids=(1004,))).to_self[0][0], 0x7A)
        self.assertEqual(equip(r, TABLE, b"\x01" + le(1004)).to_self[0][0], 0x6E)
        # 没有的 ID：跳过
        self.assertEqual(delete(r, PW, pay(ids=(1012,))).to_self, [])

    def test_first_byte_and_marker_byte_are_ignored(self):
        for head, x in ((0, 0xFF), (3, 0)):
            self.assertEqual(delete(rows(), PW, pay(head=head, x=x, ids=(1000,))).to_self[0][0], 0x7A)

    def test_rebirth_kf_blocks_everything_before_the_password_check(self):
        for ids, pw in (((3860,), PW), ((3860,), "8617294"), ((1004, 3860), PW), ((3860, 1004), PW)):
            r = rows()
            res = delete(r, pw, pay(pw, ids))
            self.assertEqual(res.to_self, [(0x1A, bytes.fromhex("64 c2 e0 a5 cd aa 5a a5 5c b5 4c aa 6b a7 52 b0 a3 a1 54"), False)])
            self.assertEqual(r["kf"][2]["kf_lvl"], "4")  # 1004 没动

    def test_wrong_password(self):
        r = rows()
        res = delete(r, PW, pay("8617294"))
        self.assertEqual(res.to_self, [(0x1A, bytes.fromhex("64 b1 4b bd 58 bf f9 bb 7e"), False)])
        self.assertEqual(r["kf"][2]["kf_lvl"], "4")
        self.assertEqual(delete(r, PW, pay("")).to_self[0][1][1:3], bytes.fromhex("b1 4b"))  # 长度 0 的密码也是「密碼錯誤」

    def test_entry_count_is_cint_of_half_the_bytes_after_the_marker(self):
        # 没有条目 / 太短 → 静默
        for p in (b"", b"\x01", b"\x01\x07\x00", pay()[:-2], pay()[:-3], bytes([1, 7]) + PW.encode() + le(1004)):
            r = rows()
            self.assertEqual(delete(r, PW, p).to_self, [], p.hex())
            self.assertEqual(r["kf"][2]["kf_lvl"], "4", p.hex())
        # 多出的字节：奇数个（m=4）最后一条越界但不报错，照样删；5 个字节 → 第二条 (aa,bb) 谁也不是
        self.assertEqual(delete(rows(), PW, pay() + b"\xaa").to_self, [(0x7A, b"\x02" + le(1004), False)])
        self.assertEqual(delete(rows(), PW, pay() + b"\xaa\xbb").to_self, [(0x7A, b"\x02" + le(1004), False)])
        self.assertEqual(delete(rows(), PW, pay() + b"\xaa\xbb\xcc").to_self, [(0x7A, b"\x02" + le(1004), False)])
        # 条目错位一个字节就读不到（密码后少了标记字节）
        self.assertEqual(delete(rows(), PW, bytes([1, 7]) + PW.encode() + le(1004) + b"\xaa").to_self, [])
        # m=5：K=2；3860 放在第二条也拦得住
        self.assertEqual(delete(rows(), PW, pay(ids=(1004, 3860))).to_self[0][0], 0x1A)

    def test_entries_are_wrong_password_checked_after_parsing(self):
        r = rows()
        self.assertEqual(delete(r, PW, bytes([1, 0, 0, 0xAA, 0xBB])).to_self[0][1][1:3], bytes.fromhex("b1 4b"))
        self.assertEqual(delete(r, PW, bytes([1, 0, 0, 0xAA])).to_self, [])  # K=0

class LearnTests(unittest.TestCase):
    """事件语句 武功:ID:等级（期望值来自对原版的实测：learn-* 场景）。"""

    def setUp(self):
        self.table = Kungfu(
            {1046: "倚天屠龙笔法", 1005: "龙爪功", 1902: "万花剑法"},
            {
                1046: Req([(0, 0)] * 3, {"str": 25}, 0, 0, 0),
                1005: Req([(1004, 50), (0, 0), (0, 0)], {"agi": 30}, 4000000, 1500, 0),
                1902: Req([(0, 0)] * 3, {}, 0, 0, 19),
            },
        )
        self.rows = {"renwu": [{"jyid": "8617293", "name": "123456", "str": "30", "agi": "30", "study_count": "0", "dangqianjing": "210", "combat_exp": "0", "online_time": "0", "school": "0"}], "kf": []}

    def test_learning_appends_a_row_and_sends_0x68(self):
        res = learn(self.rows, self.table, 1046, 1)
        self.assertEqual(res.to_self, [(0x68, bytes.fromhex("16 04 01 00 00 00 00 00 00 00 d2 00"), False)])
        self.assertEqual(self.rows["kf"], [{"jyid": "8617293", "kf_id": "1046", "kf_lvl": "1", "kf_exp": "0"}])
        self.rows["renwu"][0].update(study_count="1009", dangqianjing="111")
        self.rows["kf"].append({"jyid": "8617293", "kf_id": "1004", "kf_lvl": "60", "kf_exp": "0"})
        self.rows["renwu"][0].update(agi="30", combat_exp="4000000", online_time=str(48 * 1500))
        res = learn(self.rows, self.table, 1005, 5)
        self.assertEqual(res.to_self[0][1].hex(" "), "ed 03 05 00 00 00 00 00 f1 03 6f 00")

    def test_already_owned_keeps_the_level_and_says_so(self):
        learn(self.rows, self.table, 1046, 1)
        res = learn(self.rows, self.table, 1046, 9)
        self.assertEqual(res.to_self, [(0x1A, b"d" + bytes.fromhex("a4 77 b8 67 a6 b3 a6 b9 aa 5a a5 5c a4 46 a1 54"), False)])
        self.assertEqual(self.rows["kf"][0]["kf_lvl"], "1")

    def test_unmet_conditions_announce_to_everyone_and_learn_nothing(self):
        res = learn(self.rows, self.table, 1005, 1)
        self.assertEqual(res.to_self, [])
        (op, p, wide), = res.to_all
        self.assertEqual((op, wide, p[:1]), (0x14, True, b""))
        self.assertEqual(p[1:7].hex(" "), "aa b1 ae 61 a1 52")  # 玩家﹕
        self.assertTrue(p.endswith(bytes.fromhex("b8 d3 a6 e6 ac b0 a4 77 b8 67 b0 4f bf fd a1 54")))  # 該行為已經記錄﹗
        self.assertEqual(self.rows["kf"], [])

    def test_every_condition_is_a_not_lower_than_check_and_school_is_equality(self):
        r = self.rows
        r["kf"].append({"jyid": "1", "kf_id": "1004", "kf_lvl": "49", "kf_exp": "0"})
        r["renwu"][0].update(combat_exp="4000000", online_time=str(48 * 1500))
        req = self.table.reqs[1005]
        self.assertFalse(meets(r, req))  # 前置 49 < 50
        r["kf"][0]["kf_lvl"] = "50"
        self.assertTrue(meets(r, req))
        r["renwu"][0]["agi"] = "29"
        self.assertFalse(meets(r, req))
        r["renwu"][0].update(agi="30", combat_exp="3999999")
        self.assertFalse(meets(r, req))
        r["renwu"][0].update(combat_exp="4000000", online_time=str(48 * 1500 - 1))
        self.assertFalse(meets(r, req))
        # 门派：必须恰好等于
        self.assertFalse(meets(r, self.table.reqs[1902]))
        r["renwu"][0]["school"] = "19"
        self.assertTrue(meets(r, self.table.reqs[1902]))
        r["renwu"][0]["school"] = "20"
        self.assertFalse(meets(r, self.table.reqs[1902]))
        self.assertTrue(meets(r, None))  # 防挂验证.csv 里没有这门武功 = 随便学

    def test_a_deleted_prerequisite_with_level_zero_does_not_count(self):
        self.rows["kf"].append({"jyid": "1", "kf_id": "1004", "kf_lvl": "0", "kf_exp": "0"})
        self.rows["renwu"][0].update(combat_exp="4000000", online_time=str(48 * 1500))
        self.assertFalse(meets(self.rows, self.table.reqs[1005]))

    def test_forget_zeroes_level_and_replies_only_when_owned(self):
        learn(self.rows, self.table, 1046, 7)
        res = forget(self.rows, 1046)
        self.assertEqual(res.to_self, [(0x7A, b"\x02" + (1046).to_bytes(2, "little"), False)])
        self.assertEqual((self.rows["kf"][0]["kf_lvl"], self.rows["kf"][0]["kf_exp"]), ("0", "0"))
        self.assertEqual(forget(self.rows, 1005).to_self, [])


class PersistTests(unittest.TestCase):
    def test_level_zero_rows_are_not_written(self):
        r = rows()
        delete(r, PW, pay(ids=(1004,)))
        kept = persistable(r)
        self.assertEqual([k["kf_id"] for k in kept["kf"]], ["1000", "1002", "3860", "9999"])
        self.assertEqual(len(r["kf"]), 5)  # 内存里的不动
        clean = rows()
        self.assertIs(persistable(clean), clean)
        self.assertEqual(persistable({"renwu": []}), {"renwu": []})



class FakeItems:
    def of(self, iid):
        return 200


def bag_rows(**attrs):
    renwu = {"name": "123456", "jyid": "8617293", "study_count": "7", "dangqianjing": "33", **{a: "50" for a in ("str", "crg", "wint", "luk", "dex", "agi", "vit")}, **attrs}
    return {"renwu": [renwu], "kf": [], "item": [{"item_id": str(i), "shuliang": "2"} for i in (35022, 35031, 40177, 35041)]}


BOOK_TABLE = Kungfu({2203: "乾坤大挪移"}, {2203: Req([], {"wint": 50, "luk": 38, "dex": 30, "vit": 42, "exp_val": 20000}, 10000000, 1000, 0)})


def book(iid, tail=b"\x00"):
    return iid.to_bytes(4, "little") + tail


class ReadBookTests(unittest.TestCase):
    """期望值来自对原版的逐帧实测（tools/kf_compare.py book-*，10 套场景，与原版一致）。"""

    def run_book(self, r, iid, payload=None):
        return read_book(r, BOOK_TABLE, FakeItems(), payload if payload is not None else book(iid))

    def hexs(self, frames):
        return [(op, p.hex(" ")) for op, p, _ in frames]

    def test_attribute_and_zigong_gates_leave_the_book_alone(self):
        r = bag_rows(vit="49", zigong="0")
        self.assertEqual(self.hexs(self.run_book(r, 35022).to_self), [(0x1A, "64 bb dd ad 6e a5 fe c4 dd a9 ca 35 30")])
        self.assertEqual(self.hexs(self.run_book(r, 35031).to_self), [(0x1A, "64 bb dd ad 6e a5 fe c4 dd a9 ca 35 30 2c bb dd ad 6e a6 db ae 63 a1 54")])
        r = bag_rows(zigong="0")  # 属性够、没自宫：葵花 / 太玄不行
        self.assertEqual(self.run_book(r, 35031).to_self[0][0], 0x1A)
        self.assertEqual(self.run_book(r, 40177).to_self[0][0], 0x1A)
        self.assertEqual({x["item_id"]: x["shuliang"] for x in r["item"]}, {"35022": "2", "35031": "2", "40177": "2", "35041": "2"})

    def test_learning_consumes_one_book_and_sends_68_0b_6b(self):
        r = bag_rows(zigong="1")
        res = self.run_book(r, 35031)
        self.assertEqual(self.hexs(res.to_self), [(0x68, "bc 0b 01 00 00 00 00 00 07 00 21 00"), (0x0B, "d7 88 00 00 c8 01"), (0x6B, "d7 88 00 00 c8 01")])
        self.assertEqual([x["kf_id"] for x in r["kf"]], ["3004"])
        self.assertEqual(next(x["shuliang"] for x in r["item"] if x["item_id"] == "35031"), "1")
        again = self.run_book(r, 35031)  # 已经有：提示 + 书照样扣
        self.assertEqual(self.hexs(again.to_self)[0], (0x1A, "64 a4 77 b8 67 a6 b3 a6 b9 aa 5a a5 5c a4 46 a1 54"))
        self.assertNotIn("35031", [x["item_id"] for x in r["item"]])  # 用光整行删掉

    def test_failed_requirement_announces_to_everyone_before_the_book_frames_and_still_costs_the_book(self):
        r = bag_rows(zigong="0")
        res = self.run_book(r, 35022)
        self.assertEqual([op for op, _, _ in res.to_self], [0x0B, 0x6B])
        self.assertEqual([(pos, fr[0], fr[1][:1]) for pos, fr in res.inline], [(0, 0x14, b"\x03")])
        self.assertEqual(r["kf"], [])
        self.assertEqual(next(x["shuliang"] for x in r["item"] if x["item_id"] == "35022"), "1")

    def test_no_book_in_the_bag_kicks_and_other_items_are_silent(self):
        r = bag_rows(zigong="1")
        r["item"] = [{"item_id": "35041", "shuliang": "1"}]
        res = self.run_book(r, 35022)
        self.assertEqual(self.hexs(res.to_self), [(0x1A, "64 aa ab ab 7e a4 a3 a8 ac"), (0x05, "37 d5 83 00 01".replace("37 d5 83 00", (8617293).to_bytes(4, "little").hex(" ")))])
        self.assertEqual(self.run_book(r, 35041).to_self, [])  # 有但不是秘笈
        self.assertEqual(self.run_book(r, 12345).to_self[0][0], 0x1A)  # 没有 → 物品不足
        self.assertEqual(self.run_book(r, 35022, b"\x00" * 4).to_self, [])  # 载荷太短

    def test_high_word_makes_it_another_item(self):
        r = bag_rows(zigong="1")
        self.assertEqual(self.run_book(r, 35022, (35022 + 65536).to_bytes(4, "little") + b"\x00").to_self[0][0], 0x1A)


if __name__ == "__main__":
    unittest.main()