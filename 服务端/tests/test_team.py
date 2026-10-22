"""组队：期望值来自对原版用 A=8617293、W=1234567、C=123456 三个号的实测（2026-10，tools/multi_raw.py / team_compare.py）。"""

import unittest

from jyserver.team import Info, Teams

A, W, C = 8617293, 1234567, 123456


def le(n):
    return n.to_bytes(4, "little")


def hexs(frames, to=None):
    return [(j, op, p.hex(" ")) for j, op, p, _ in frames if to is None or j == to]


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.t = Teams()
        self.on = {A: Info(2200, "123456"), W: Info(2200, "游戏者之家99"), C: Info(2801, "游客")}

    def start(self):
        """A 创建，W 加入。"""
        self.t.create(A, b"", self.on)
        self.t.reply(W, b"\x01" + le(A), self.on)

    def test_create_announces_to_everyone_with_payload_echo(self):
        out = self.t.create(A, b"", self.on)
        self.assertEqual(hexs(out), [(j, 0x2A, "4d 7d 83 00 01 00") for j in (A, W, C)])
        out = self.t.create(A, le(W), self.on)
        self.assertEqual(out[0][2].hex(" "), "4d 7d 83 00 01 00 87 d6 12 00")

    def test_create_on_forbidden_maps(self):
        for m in (3511, 1820, 13000):
            on = {A: Info(m, "x")}
            self.assertEqual(hexs(Teams().create(A, b"", on)), [(A, 0x1A, "64 b7 ed ab 65 a6 61 b9 cf a4 a3 af e0 b2 d5 b6 a4")])

    def test_invite_goes_only_to_the_target_even_on_another_map_or_yourself(self):
        self.assertEqual(hexs(self.t.invite(A, le(W), self.on)), [(W, 0x2E, "4d 7d 83 00")])
        self.assertEqual(hexs(self.t.invite(A, le(C), self.on)), [(C, 0x2E, "4d 7d 83 00")])
        self.assertEqual(hexs(self.t.invite(A, le(A), self.on)), [(A, 0x2E, "4d 7d 83 00")])
        self.assertEqual(hexs(self.t.invite(A, le(W) + b"\xaa\xbb", self.on)), [(W, 0x2E, "4d 7d 83 00")])
        self.assertEqual(hexs(self.t.invite(A, bytes.fromhex("87 d6 12"), self.on)), [(W, 0x2E, "4d 7d 83 00")])  # 不足 4 字节补 0
        for p in (le(99999), b"", b"\x01\x02"):
            self.assertEqual(self.t.invite(A, p, self.on), [])

    def test_accept_joins_and_tells_everyone(self):
        self.t.create(A, b"", self.on)
        out = self.t.reply(W, b"\x01" + le(A), self.on)
        self.assertEqual(hexs(out), [(j, 0x2F, "01 87 d6 12 00 4d 7d 83 00") for j in (A, W, C)])
        self.assertEqual(self.t.team_of[W], self.t.team_of[A])

    def test_refusals_go_only_to_the_sender(self):
        self.t.create(C, b"", self.on)
        other = hexs(self.t.reply(W, b"\x01" + le(C), self.on))
        self.assertEqual(other, [(W, 0x1A, "64 a6 61 b9 cf a4 a3 a6 50 2c a4 a3 af e0 b2 d5 b6 a4")])  # 地圖不同,不能組隊
        self.assertEqual(hexs(self.t.reply(W, b"\x02" + le(C), self.on)), [(W, 0x1A, "64 b9 ef a4 e8 a9 da b5 b4 a5 5b a4 4a b6 a4 a5 ee")])
        self.assertEqual(self.t.reply(W, b"\x01", self.on), [])
        self.assertEqual(self.t.reply(W, b"", self.on), [])

    def test_accepting_an_inviter_without_a_team_is_silent(self):
        self.assertEqual(self.t.reply(W, b"\x01" + le(A), self.on), [])  # 原版此时会崩
        self.assertEqual(self.t.reply(W, b"\x01" + le(99999), self.on), [])

    def test_team_is_full_at_seven(self):
        on = {A: Info(1, "a")}
        on.update({100 + i: Info(1, "m%d" % i) for i in range(8)})
        self.t.create(A, b"", on)
        for i in range(6):
            self.assertEqual(self.t.reply(100 + i, b"\x01" + le(A), on)[0][1], 0x2F)
        out = self.t.reply(106, b"\x01" + le(A), on)
        self.assertEqual(hexs(out), [(106, 0x1A, "64 b2 d5 b6 a4 a5 a2 b1 d1 2c b6 a4 a5 ee a4 77 b8 67 ba a1 ad fb 21")])

    def test_team_chat_drops_the_first_four_bytes(self):
        self.start()
        out = self.t.chat(A, b"hello", self.on)
        self.assertEqual(hexs(out), [(A, 0x1C, "6f"), (W, 0x1C, "6f")])
        self.assertEqual(hexs(self.t.chat(A, b"\x11\x22\x33\x44\x55\x66", self.on), W), [(W, 0x1C, "55 66")])
        self.assertEqual(hexs(self.t.chat(W, b"", self.on)), [(A, 0x1C, ""), (W, 0x1C, "")])

    def test_chat_without_a_team_reaches_everyone_without_one(self):
        self.t.create(A, b"", self.on)
        self.assertEqual(hexs(self.t.chat(C, b"\x00\x00\x00\x00a", self.on)), [(W, 0x1C, "61"), (C, 0x1C, "61")])

    def test_member_leaves_leader_cannot(self):
        self.start()
        out = self.t.leave(W, self.on)
        self.assertEqual(
            hexs(out),
            [(j, 0x2D, "87 d6 12 00") for j in (A, W, C)]
            + [(A, 0x1A, "64 aa b1 ae 61 3a b4 e5 c0 b8 aa cc a4 a7 ae 61 39 39 b2 e6 d6 c3 b6 a4 a5 ee")],  # 玩家:游戏者之家99脫离隊伍，只有队里的人（A）收到
        )
        self.assertEqual(self.t.team_of[W], 0)
        self.start()
        out = self.t.leave(A, self.on)  # 队长在格 0，找不到：没有 0x2D，但队里的人照样收到那条文字（含离不开的队长自己）
        self.assertEqual([(j, op) for j, op, _ in hexs(out)], [(A, 0x1A), (W, 0x1A)])

    def test_leave_without_a_team_tells_everyone_without_one(self):
        out = self.t.leave(A, self.on)
        self.assertEqual([(j, op) for j, op, _ in hexs(out)], [(A, 0x1A), (W, 0x1A), (C, 0x1A)])

    def test_any_member_can_disband(self):
        self.start()
        self.t.create(C, b"", self.on)
        out = self.t.disband(W, self.on)
        self.assertEqual(hexs(out), [(j, 0x2B, "87 d6 12 00") for j in (A, W, C)])
        self.assertEqual((self.t.team_of[A], self.t.team_of[W]), (0, 0))
        self.assertNotEqual(self.t.team_of[C], 0)  # 别的队伍不受影响
        self.assertEqual(self.t.disband(A, self.on), [])  # 没队伍：静默

    def test_logout_of_leader_disbands_member_just_leaves(self):
        self.start()
        out = self.t.on_logout(A, self.on)
        self.assertEqual(hexs(out), [(j, 0x2B, "4d 7d 83 00") for j in (A, W, C)])
        self.assertEqual(self.t.team_of.get(W, 0), 0)
        self.start()
        out = self.t.on_logout(W, self.on)
        self.assertEqual([op for _, op, _ in hexs(out)], [0x2D, 0x2D, 0x2D, 0x1A])
        self.assertEqual(self.t.on_logout(C, self.on), [])  # 没队伍的人下线：什么都不发

    def test_joining_twice_takes_two_slots_and_leaving_frees_one(self):
        self.t.create(A, b"", self.on)
        self.t.reply(W, b"\x01" + le(A), self.on)
        self.t.reply(W, b"\x01" + le(A), self.on)
        tid = self.t.team_of[A]
        self.assertEqual(self.t.slots[tid][:3], [A, W, W])
        self.t.leave(W, self.on)
        self.assertEqual((self.t.slots[tid][:3], self.t.team_of[W]), ([A, 0, W], 0))


if __name__ == "__main__":
    unittest.main()
