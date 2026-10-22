"""账号类指令：期望值来自对原版的实测（2026-10，8617293 号及其克隆号，tools/cmd_probe.py / delete_probe.py / cmd_compare.py）。"""

import unittest

from jyserver import account

JYID = 8617293
BAD_PW = [(0x1A, "64 b1 4b bd 58 bf f9 bb 7e")]  # 密碼錯誤


def hexs(frames):
    return [(op, p.hex(" ")) for op, p, _ in frames]


def rows(kf_lvl=None):
    r = {
        "renwu": [{"jyid": str(JYID), "name": "123456", "nickname": "123"}],
        "kf": [],
        "item": [{"item_id": "28290", "shuliang": "1"}],
        "biaoji": [{"biaoji": "1"}],
        "char_equip": [{"x": 1}],
        "jineng": [{"x": 1}],
        "qianzhuang": [{"wupin": "0"}],
        "account": [{"jyid": str(JYID), "shangchengdianshu": "3000"}],
    }
    if kf_lvl is not None:
        r["kf"] = [{"kf_id": "3860", "kf_lvl": str(kf_lvl)}]
    return r


class Nickname(unittest.TestCase):
    def test_ascii_nickname_goes_to_self_and_everyone(self):
        r = rows()
        res = account.change_nickname(r, b"abc")
        self.assertEqual(hexs(res.to_self), [(0x15, "4d 7d 83 00 56 37 5a 30 2d 61 62 63")])
        self.assertEqual(
            hexs(res.to_all),
            [(0x14, "0e 31 32 33 34 35 36 a7 f3 a7 ef a4 46 a5 7e b8 b9 a1 52 56 37 5a 30 2d 61 62 63")],
        )
        self.assertEqual(r["renwu"][0]["nickname"], "abc")

    def test_big5_bytes_are_forwarded_raw_and_stored_simplified(self):
        r = rows()
        res = account.change_nickname(r, bytes.fromhex("c4e3bac3"))
        self.assertTrue(res.to_self[0][1].endswith(bytes.fromhex("56 37 5a 30 2d c4 e3 ba c3")))
        self.assertEqual(r["renwu"][0]["nickname"], "斓疑")  # 库里是简体（原版同样）

    def test_empty_and_nul_clear_the_nickname_and_there_is_no_length_limit(self):
        for payload in (b"", b"\x00", b"\x00abc"):
            r = rows()
            res = account.change_nickname(r, payload)
            self.assertEqual(res.to_self[0][1], (JYID).to_bytes(4, "little") + b"V7Z0-")
            self.assertEqual(r["renwu"][0]["nickname"], "")
        long = b"a" * 36
        self.assertTrue(account.change_nickname(rows(), long).to_self[0][1].endswith(long))
        self.assertEqual(account.change_nickname(rows(), b"ab c").to_self[0][1][4:], b"V7Z0-ab c")

    def test_rebirth_skill_level_sets_z(self):
        self.assertTrue(account.change_nickname(rows(kf_lvl=25), b"a").to_self[0][1].endswith(b"V7Z2-a"))
        self.assertTrue(account.change_nickname(rows(kf_lvl=9), b"a").to_self[0][1].endswith(b"V7Z0-a"))


class Deletion(unittest.TestCase):
    PW = "8617293"

    @staticmethod
    def req(pw: bytes, first=0x00, n=None):
        return bytes([first, len(pw) if n is None else n]) + pw

    def test_right_password_wipes_character_tables_but_keeps_the_account(self):
        r = rows()
        res = account.delete_character(r, self.PW, self.req(b"8617293"))
        self.assertEqual(hexs(res.to_self), [(0x36, "01")])
        self.assertTrue(res.deleted)
        for t in account.CHARACTER_TABLES:
            self.assertEqual(r[t], [], t)
        self.assertEqual(r["account"][0]["shangchengdianshu"], "3000")

    def test_first_byte_and_trailing_bytes_are_ignored(self):
        r = rows()
        res = account.delete_character(r, self.PW, self.req(b"8617293", first=0x05) + b"9")
        self.assertTrue(res.deleted)

    def test_wrong_password_or_zero_length(self):
        for payload in (self.req(b"8617294"), self.req(b"861729"), self.req(b"", n=0), self.req(b"86172930", n=8)):
            r = rows()
            res = account.delete_character(r, self.PW, payload)
            self.assertEqual((hexs(res.to_self), res.deleted), (BAD_PW, False))
            self.assertEqual(len(r["renwu"]), 1)

    def test_too_short_payload_is_silent(self):
        for payload in (b"", b"\x01", bytes([0x07, 0x38]) + b"8617293"[:3], bytes([0x00, 0x08]) + b"8617293"):
            r = rows()
            res = account.delete_character(r, self.PW, payload)
            self.assertEqual((res.to_self, res.deleted), ([], False))


class BetrayStub(unittest.TestCase):
    def test_replies_with_the_fixed_refusal_from_five_bytes_on(self):
        want = [(0x1A, "64 bd d0 b1 71 a5 7e ac 45 a4 57 a7 50 aa f9 a1 54")]
        for n in (5, 6, 20):
            self.assertEqual(hexs(account.betray_stub(bytes(n)).to_self), want)
        for n in (0, 1, 4):
            self.assertEqual(account.betray_stub(bytes(n)).to_self, [])


class PasswordCheck(unittest.TestCase):
    PW = "8617293"

    def test_0d_right_wrong_and_short(self):
        ok = account.password_check(self.PW, bytes.fromhex("0d07") + b"8617293")
        self.assertEqual((hexs(ok.to_self), ok.zigong), ([(0xB8, "10")], True))
        for payload in (bytes.fromhex("0d07") + b"8617294", bytes.fromhex("0d03") + b"8617293", bytes.fromhex("0d00")):
            res = account.password_check(self.PW, payload)
            self.assertEqual((hexs(res.to_self), res.zigong), (BAD_PW, False))
        for payload in (b"", b"\x0d", bytes.fromhex("0d08") + b"8617293"):
            self.assertEqual(account.password_check(self.PW, payload).to_self, [])

    def test_0d_is_zigong_and_writes_the_column_only_when_the_password_is_right(self):
        rows = {"renwu": [{"zigong": "0"}]}
        account.password_check(self.PW, bytes.fromhex("0d07") + b"8617294", rows)
        self.assertEqual(rows["renwu"][0]["zigong"], "0")
        account.password_check(self.PW, bytes.fromhex("0d07") + b"8617293" + bytes.fromhex("03") + b"abc", rows)  # 暗码不看
        self.assertEqual(rows["renwu"][0]["zigong"], "1")

    def test_0f_and_0e_echo_five_bytes(self):
        self.assertEqual(hexs(account.password_check(self.PW, bytes.fromhex("0f0102030405")).to_self), [(0xB8, "13 01 02 03 04 05")])
        self.assertEqual(hexs(account.password_check(self.PW, bytes.fromhex("0f01020304050607")).to_self), [(0xB8, "13 01 02 03 04 05")])
        self.assertEqual(hexs(account.password_check(self.PW, bytes.fromhex("0e0102030405")).to_self), [(0xB8, "12 01 02 03 04 05")])
        self.assertEqual(account.password_check(self.PW, bytes.fromhex("0e01020304")).to_self, [])
        self.assertEqual(account.password_check(self.PW, bytes.fromhex("0c0102030405")).to_self, [])


if __name__ == "__main__":
    unittest.main()
