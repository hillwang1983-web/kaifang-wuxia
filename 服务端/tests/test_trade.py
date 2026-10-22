"""玩家交易：期望值来自对原版服务端用两个号（8617293 = A，1234567 = W）的实测（2026-10，tools/raw_probe.py）。"""

import struct
import unittest
from pathlib import Path

from jyserver.state import ItemTable
from jyserver.trade import Trades

from jyserver.server import DEFAULT_DATA_DIR  # 部署包里是 原版数据/data，开发机上是原版目录
DATA_DIR = Path(DEFAULT_DATA_DIR)
A, W = 8617293, 1234567
A_LE, W_LE = A.to_bytes(4, "little"), W.to_bytes(4, "little")


def hexs(frames, who=None):
    return [(j, op, p.hex(" ")) for j, op, p, _ in frames if who is None or j == who]


def le(n):
    return struct.pack("<I", n)


def add(item, dur=0xC8):
    return b"\x01" + le(item) + bytes([dur])


@unittest.skipUnless(DATA_DIR.exists(), "原版服务端 data 目录不存在")
class TradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = ItemTable.load(DATA_DIR)

    def setUp(self):
        self.t = Trades()
        self.rows = {
            A: {"renwu": [{"jyid": str(A), "map": "2200", "jy_money": "87797"}], "item": self.bag(A, [(28005, 1), (58182, 3)])},
            W: {"renwu": [{"jyid": str(W), "map": "2200", "jy_money": "112800"}], "item": self.bag(W, [(11007, 1), (58182, 7)])},
        }

    @staticmethod
    def bag(jyid, items):
        return [{"jyid": str(jyid), "item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in items]

    def count(self, who, item):
        return sum(int(r["shuliang"]) for r in self.rows[who]["item"] if r["item_id"] == str(item))

    def start(self):
        self.t.request(A, W, self.rows)

    def finish(self, executor_first=A):
        """两边各锁一次、各确认一次；executor_first 先确认，另一个人是 executor。"""
        other = W if executor_first == A else A
        self.t.command(A, b"\x01", self.rows)
        self.t.command(W, b"\x01", self.rows)
        self.t.command(executor_first, b"\x03", self.rows)
        return self.t.command(other, b"\x03", self.rows)

    # ---- 请求
    def test_request_frames_and_status_marks(self):
        out = self.t.request(A, W, self.rows)
        self.assertEqual(
            hexs(out),
            [
                (A, 0x1F, "4d 7d 83 00 87 d6 12 00"),
                (W, 0x1F, "4d 7d 83 00 87 d6 12 00"),
                (W, 0x82, "4d 7d 83 00 08 00"),
                (W, 0x82, "87 d6 12 00 08 00"),
            ],
        )
        again = self.t.request(W, A, self.rows)  # 对方回头也请求：同样的帧，状态标记发给请求者以外的人
        self.assertEqual(hexs(again, A), [(A, 0x1F, "87 d6 12 00 4d 7d 83 00"), (A, 0x82, "87 d6 12 00 08 00"), (A, 0x82, "4d 7d 83 00 08 00")])

    def test_request_to_offline_or_self_is_silent(self):
        self.assertEqual(self.t.request(A, 99999, self.rows), [])
        self.assertEqual(self.t.request(A, A, self.rows), [])

    def test_commands_without_a_session_are_silent(self):
        for out in (self.t.add_item(A, add(11007), self.table), self.t.set_money(A, le(5)), self.t.command(A, b"\x01", self.rows)):
            self.assertEqual(out, [])

    # ---- 放物品
    def test_add_item_goes_to_both_and_is_not_checked_against_the_bag(self):
        self.start()
        out = self.t.add_item(A, add(99999), self.table)  # 背包里没有也收下
        body = "4d 7d 83 00 01 9f 86 01 00 c8 01"
        self.assertEqual(hexs(out), [(A, 0x20, body), (W, 0x20, body)])

    def test_untradable_item_only_tells_the_sender(self):
        self.start()
        out = self.t.add_item(W, add(28280), self.table)
        self.assertEqual(hexs(out), [(W, 0x1A, "64 a6 b9 aa ab ab 7e a4 a3 af e0 a5 e6 a9 f6")])

    def test_short_or_wrong_subtype_ignored(self):
        self.start()
        self.assertEqual(self.t.add_item(A, add(11007)[:5], self.table), [])
        self.assertEqual(self.t.add_item(A, b"\x02" + le(11007) + b"\xc8", self.table), [])

    # ---- 锁定 / 取消
    def test_second_lock_opens_confirm_stage_third_only_notifies(self):
        self.start()
        self.assertEqual(hexs(self.t.command(A, b"\x01", self.rows)), [(W, 0x23, "01 4d 7d 83 00")])
        out = self.t.command(W, b"\x01", self.rows)
        self.assertEqual(hexs(out), [(A, 0x23, "01 87 d6 12 00"), (A, 0x23, "04"), (W, 0x23, "04")])
        self.assertEqual(hexs(self.t.command(W, b"\x01", self.rows)), [(A, 0x23, "01 87 d6 12 00")])

    def test_cancel_tells_both_and_ends_the_session(self):
        self.start()
        self.assertEqual(hexs(self.t.command(A, b"\x00", self.rows)), [(A, 0x23, "00 4d 7d 83 00"), (W, 0x23, "00 4d 7d 83 00")])
        self.assertEqual(self.t.add_item(A, add(11007), self.table), [])

    # ---- 金钱通知的「压帧」怪行为
    def test_money_notice_is_held_until_the_next_frame_replaces_it(self):
        self.start()
        self.assertEqual(self.t.set_money(A, le(100)), [])  # 第一次：压进槽里，什么也不发
        out = self.t.set_money(W, le(50))  # 第二条 1F 把槽里的发出去（不是自己的数值），尾巴 f4 44 0f
        body = "4d 7d 83 00 64 00 00 00 f4 44 0f"
        self.assertEqual(hexs(out), [(A, 0x21, body), (W, 0x21, body)])

    def test_pending_notice_replaces_whatever_frame_comes_next_per_recipient(self):
        self.start()
        self.t.set_money(A, le(100))
        out = self.t.command(W, b"\x01", self.rows)  # 本来给 A 的 0x23 01 被顶掉，A 收到的是 0x21，尾巴是 0x23 帧的长度 09
        self.assertEqual(hexs(out), [(A, 0x21, "4d 7d 83 00 64 00 00 00 f4 44 09")])
        out = self.t.command(A, b"\x01", self.rows)  # W 的槽也还压着：0x23 01 被顶掉；随后第 2 次锁定的 04 正常
        self.assertEqual(hexs(out), [(W, 0x21, "4d 7d 83 00 64 00 00 00 f4 44 09"), (W, 0x23, "04"), (A, 0x23, "04")])

    # ---- 成交
    def test_money_swap_moves_only_the_difference(self):
        self.start()
        self.t.set_money(A, struct.pack("<I", 25601))
        self.t.set_money(W, struct.pack("<I", 12801))
        out = self.finish(executor_first=A)
        self.assertEqual(hexs(out), [(W, 0x22, ""), (A, 0x22, ""), (A, 0x82, "87 d6 12 00 00 00")])
        self.assertEqual((self.rows[A]["renwu"][0]["jy_money"], self.rows[W]["renwu"][0]["jy_money"]), ("74997", "125600"))

    def test_first_confirm_only_marks_the_sender(self):
        self.start()
        self.assertEqual(hexs(self.t.command(A, b"\x03", self.rows)), [(W, 0x82, "4d 7d 83 00 00 00")])

    def test_items_swap_one_piece_per_offer(self):
        self.start()
        self.t.add_item(A, add(28005), self.table)
        self.t.add_item(W, add(58182), self.table)
        self.t.add_item(W, add(58182), self.table)
        out = self.finish(executor_first=A)
        self.assertEqual([(j, op) for j, op, _ in hexs(out)], [(W, 0x22), (A, 0x22), (A, 0x82)])
        self.assertEqual((self.count(A, 28005), self.count(W, 28005), self.count(A, 58182), self.count(W, 58182)), (0, 1, 5, 5))
        self.assertEqual(self.t.by_player, {})  # 会话结束

    def test_no_money_missing_item_stops_midway_and_keeps_earlier_moves(self):
        """实测（A 先确认、W 成交）：W 的 58182 搬给了 A，A 没有的 11007 搬不了，只有 W 收到「物品不足」。"""
        self.start()
        self.t.add_item(A, add(11007), self.table)
        self.t.add_item(W, add(58182), self.table)
        self.rows[A]["item"] = self.bag(A, [(58182, 1)])
        out = self.finish(executor_first=A)
        self.assertEqual(hexs(out), [(W, 0x22, ""), (A, 0x22, ""), (W, 0x1A, "64 aa ab ab 7e a4 a3 a8 ac")])
        self.assertEqual((self.count(A, 58182), self.count(W, 58182), self.count(W, 11007)), (2, 6, 1))

    def test_no_money_executor_items_are_tried_first(self):
        """实测（W 先确认、A 成交）：A 的第一件就不够 → 什么都没搬（A 的 28005 也没搬），A 收到「物品不足」。"""
        self.start()
        self.t.add_item(A, add(11007), self.table)
        self.t.add_item(W, add(58182), self.table)
        self.t.add_item(A, add(28005), self.table)
        out = self.finish(executor_first=W)
        self.assertEqual(hexs(out, A)[-1], (A, 0x1A, "64 aa ab ab 7e a4 a3 a8 ac"))
        self.assertEqual((self.count(A, 28005), self.count(W, 58182), self.count(A, 58182)), (1, 7, 3))

    def test_with_money_a_missing_item_cancels_everything(self):
        self.start()
        self.t.add_item(A, add(11007), self.table)
        self.t.add_item(W, add(58182), self.table)
        self.t.set_money(A, le(1000))
        self.t.set_money(W, le(500))
        out = self.finish(executor_first=A)
        self.assertEqual(hexs(out, W)[-1], (W, 0x1A, "64 aa ab ab 7e a4 a3 a8 ac"))
        self.assertNotIn(0x82, [op for _, op, _, _ in out])
        self.assertEqual((self.count(W, 58182), self.rows[A]["renwu"][0]["jy_money"]), (7, "87797"))

    def test_offering_more_money_than_you_have_voids_the_trade_silently(self):
        self.start()
        self.t.set_money(A, le(1_000_000_000))
        out = self.finish(executor_first=A)
        self.assertEqual(hexs(out)[:3], [(W, 0x22, ""), (A, 0x22, ""), (A, 0x82, "87 d6 12 00 00 00")][:3])
        self.assertEqual((self.rows[A]["renwu"][0]["jy_money"], self.rows[W]["renwu"][0]["jy_money"]), ("87797", "112800"))

    def test_confirming_twice_by_the_same_player_executes_without_locks(self):
        self.start()
        self.t.command(A, b"\x03", self.rows)
        out = self.t.command(A, b"\x03", self.rows)
        self.assertEqual([op for _, op, _, _ in out], [0x22, 0x22, 0x82])
        self.assertEqual(hexs(out)[-1], (W, 0x82, "4d 7d 83 00 00 00"))


if __name__ == "__main__":
    unittest.main()
