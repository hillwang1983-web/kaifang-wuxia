"""组织：期望值来自对原版用 A=8617293、W=1234567、C=123456 三个号的实测（2026-10，tools/org_compare.py）。"""

import unittest

from jyserver.org import Orgs

A, W, C = 8617293, 1234567, 123456
TPL = bytes(range(256)) * 7 + bytes(10)  # 1802 字节，测试用模板


def le(n):
    return n.to_bytes(4, "little")


def hexs(frames, to=None):
    return [(j, op, p.hex(" ")) for j, op, p, _ in frames if to is None or j == to]


class OrgTests(unittest.TestCase):
    def setUp(self):
        self.o = Orgs(template=TPL)
        self.on = {A: "123456", W: "游戏者之家99", C: "游戏者之家"}

    def start(self):
        """A 创立 ab，W、C 加入。"""
        self.o.create(A, b"ab", self.on)
        self.o.reply(W, b"\x01" + le(A), self.on)
        self.o.reply(C, b"\x01" + le(A), self.on)

    def test_create_replies_to_self_and_announces_to_everyone(self):
        out = self.o.create(A, b"ab", self.on)
        self.assertEqual(out[0], (A, 0x4F, bytes.fromhex("4d 7d 83 00 01 00 61 62"), False))
        notice = "0e 31 32 33 34 35 36 a1 41 b3 d0 a5 df a4 46 b2 d5 c2 b4 a1 52 61 62"
        self.assertEqual(hexs(out[1:]), [(j, 0x14, notice) for j in (A, W, C)])
        self.assertTrue(all(w for _, _, _, w in out[1:]))
        out = self.o.create(W, b"cd", self.on)
        self.assertEqual(out[0][2].hex(" "), "87 d6 12 00 02 00 63 64")
        self.assertIn("b4 e5 c0 b8 aa cc a4 a7 ae 61 39 39 a1 41", out[1][2].hex(" "))

    def test_create_refusals(self):
        self.o.create(A, b"ab", self.on)
        self.assertEqual(hexs(self.o.create(A, b"cd", self.on)), [(A, 0x1A, "64 a4 77 a6 b3 b2 d5 c2 b4 a1 54")])
        self.assertEqual(hexs(self.o.create(W, b"ab", self.on)), [(W, 0x1A, "64 b2 d5 c2 b4 a6 57 ad ab ce 60")])
        self.assertEqual(self.o.create(W, b"", self.on), [])  # 原版崩 / 无反应，这里静默
        self.assertEqual(self.o.create(W, b"AB", self.on)[0][1], 0x4F)  # 区分大小写

    def test_recruit_frame_has_leader_name_template_and_org_id(self):
        self.o.create(A, b"ab", self.on)
        self.o.create(W, b"cd", self.on)
        (j, op, p, wide), = self.o.recruit(W, le(C), self.on)
        self.assertEqual((j, op, wide), (C, 0x54, True))
        self.assertEqual(p[:7].hex(" "), "87 d6 12 00 02 63 64")
        rest = p[7:]
        self.assertEqual(len(rest), 1802)
        self.assertEqual(rest[28:30], b"\x02\x00")
        self.assertEqual(rest[:28] + rest[30:], TPL[:28] + TPL[30:])

    def test_recruit_checks_in_original_order(self):
        self.assertEqual(self.o.recruit(A, le(W), self.on), [])  # 自己没组织
        self.start()
        self.assertEqual(hexs(self.o.recruit(W, le(C), self.on)), [(W, 0x1A, "64 b2 d5 c2 b4 b3 d0 a5 df aa cc a4 7e af e0 a9 db a6 ac c0 b0 b2 b3 a1 54")])
        self.assertEqual(hexs(self.o.recruit(A, le(W), self.on)), [(A, 0x1A, "64 b9 ef a4 e8 a4 77 a6 b3 b2 d5 c2 b4 a1 54")])
        self.assertEqual(hexs(self.o.recruit(A, le(A), self.on)), [(A, 0x1A, "64 b9 ef a4 e8 a4 77 a6 b3 b2 d5 c2 b4 a1 54")])
        self.assertEqual(self.o.recruit(A, le(99999), self.on), [])
        self.assertEqual(self.o.recruit(A, b"\x01\x02", self.on), [])

    def test_accept_joins_and_tells_everyone(self):
        self.o.create(A, b"ab", self.on)
        out = self.o.reply(W, b"\x01" + le(A), self.on)
        self.assertEqual(hexs(out), [(j, 0x55, "87 d6 12 00 01 01 00") for j in (A, W, C)])
        self.assertEqual(self.o.orgs[0].members, [A, W])
        self.o.reply(W, b"\x01" + le(A), self.on)
        self.assertEqual(self.o.orgs[0].members, [A, W, W])  # 重复接受 = 重复项

    def test_accept_needs_online_inviter_with_an_org(self):
        self.assertEqual(self.o.reply(W, b"\x01" + le(A), self.on), [])  # 招收人没组织
        self.o.create(A, b"ab", self.on)
        for p in (b"\x01" + le(99999), b"\x01", b"\x01\x00", b"\x02" + le(A), b"\x09", b""):
            self.assertEqual(self.o.reply(W, p, self.on), [])
        self.assertEqual(self.o.org_of.get(W, "0"), "0")

    def test_member_list_skips_self_and_offline_and_repeats_duplicates(self):
        self.start()
        self.o.reply(C, b"\x01" + le(A), self.on)  # C 重复
        out = self.o.reply(A, b"\x07", self.on)
        self.assertEqual(hexs(out), [(A, 0xAD, "10 05 0c b4 e5 c0 b8 aa cc a4 a7 ae 61 39 39 05 0a b4 e5 c0 b8 aa cc a4 a7 ae 61 05 0a b4 e5 c0 b8 aa cc a4 a7 ae 61")])
        on = {A: "123456", W: "游戏者之家99"}
        self.assertEqual(hexs(self.o.reply(W, b"\x07", on)), [(W, 0xAD, "10 05 06 31 32 33 34 35 36")])
        self.assertEqual(hexs(self.o.reply(A, b"\x07", {A: "123456"})), [(A, 0xAD, "10")])
        self.assertEqual(self.o.reply(self.o.orgs and 99999, b"\x07", {99999: "x"}), [])  # 没组织：静默

    def test_kick_by_name_needs_no_leader_and_marks_target(self):
        self.start()
        name = bytes.fromhex("b4 e5 c0 b8 aa cc a4 a7 ae 61 39 39")
        out = self.o.kick(C, b"\x00" * 4 + name, self.on)  # 普通成员也能踢
        self.assertEqual(hexs(out), [(j, 0x56, "40 e2 01 00 87 d6 12 00") for j in (A, W, C)])
        self.assertEqual(self.o.orgs[0].members, [A, C])
        self.assertEqual(self.o.org_of[W], " 0")
        # 被踢的人：不能创立、不能被招收、不能聊天，但能再加入
        self.assertEqual(hexs(self.o.create(W, b"cd", self.on))[0][2], "64 a4 77 a6 b3 b2 d5 c2 b4 a1 54")
        self.assertEqual(hexs(self.o.recruit(A, le(W), self.on))[0][2], "64 b9 ef a4 e8 a4 77 a6 b3 b2 d5 c2 b4 a1 54")
        self.assertEqual(self.o.chat(W, b"x", self.on), [])
        self.assertEqual(hexs(self.o.reply(W, b"\x01" + le(A), self.on))[0][1], 0x55)

    def test_kick_errors(self):
        self.start()
        msg = [(A, 0x1A, "64 a6 b9 aa b1 ae 61 a4 a3 a6 62 bd 75 a4 57 a1 54")]
        self.assertEqual(hexs(self.o.kick(A, b"\x00" * 4 + b"nobody", self.on)), msg)
        self.assertEqual(hexs(self.o.kick(A, b"\x00" * 4, self.on)), msg)
        self.assertEqual(hexs(self.o.kick(A, b"\x00", self.on)), msg)
        self.assertEqual(self.o.kick(A, b"", self.on), [])
        self.assertEqual(self.o.kick(99999, b"\x00" * 4 + b"x", {99999: "x"}), [])
        name = bytes.fromhex("b4 e5 c0 b8 aa cc a4 a7 ae 61")  # 游戲者之家
        self.o.org_of[C] = "0"
        self.assertEqual(self.o.kick(C, b"\x00" * 4 + name, self.on), [])  # 自己没组织：静默

    def test_leave_removes_first_entry_and_resets_to_plain_zero(self):
        self.start()
        out = self.o.leave(W, b"\x01", self.on)
        self.assertEqual(hexs(out), [(j, 0x57, "87 d6 12 00") for j in (A, W, C)])
        self.assertEqual(self.o.orgs[0].members, [A, C])
        self.assertEqual(self.o.org_of[W], "0")
        self.assertEqual(self.o.leave(W, b"\x01", self.on), [])  # 没组织
        self.assertEqual(hexs(self.o.create(W, b"cd", self.on))[0][1], 0x4F)  # 自己退出的人还能创立
        self.assertEqual(self.o.leave(C, b"\x02", self.on), [])
        self.assertEqual(self.o.leave(C, b"", self.on), [])

    def test_leader_leaving_keeps_org_but_cannot_recruit(self):
        self.start()
        self.o.leave(A, b"\x01", self.on)
        self.assertEqual(self.o.recruit(A, le(99999), self.on), [])
        self.assertEqual(self.o.orgs[0].leader, A)
        self.assertEqual(hexs(self.o.recruit(W, le(C), self.on))[0][2][:2], "64")  # 组织还在，成员招收仍是「創立者才能招收」

    def test_org_chat_goes_to_online_members_other_than_sender_once_per_entry(self):
        self.start()
        self.o.reply(C, b"\x01" + le(A), self.on)  # C 重复
        out = self.o.chat(A, b"hello", self.on)
        self.assertEqual(hexs(out), [(W, 0x04, "05 4d 7d 83 00 68 65 6c 6c 6f"), (C, 0x04, "05 4d 7d 83 00 68 65 6c 6c 6f"), (C, 0x04, "05 4d 7d 83 00 68 65 6c 6c 6f")])
        self.assertEqual([j for j, _, _ in hexs(self.o.chat(C, b"x", self.on))], [A, W])  # C 自己的两项都跳过
        self.assertEqual([j for j, _, _ in hexs(self.o.chat(A, b"x", {A: "a", C: "c"}))], [C, C])  # 离线的不发
        self.assertEqual(self.o.chat(A, b"", self.on), [])

    def test_org_id_survives_logout_because_state_is_global(self):
        self.start()
        on = {A: "123456"}  # W、C 下线（状态不动）
        self.assertEqual(self.o.chat(A, b"x", on), [])
        self.assertEqual(self.o.org_of[W], "1")
        self.assertEqual(hexs(self.o.create(W, b"cd", self.on))[0][2], "64 a4 77 a6 b3 b2 d5 c2 b4 a1 54")

    def test_query_is_constant_and_long_frame(self):
        for sub, val in ((6, "05"), (4, "03"), (5, "04")):
            (j, op, p, wide), = self.o.query(C, bytes([sub]), self.on)
            self.assertEqual((j, op, p.hex(), wide), (C, 0x39, val, True))
        self.assertEqual(self.o.query(C, b"\x07", self.on), [])
        self.assertEqual(self.o.query(C, b"", self.on), [])


if __name__ == "__main__":
    unittest.main()
