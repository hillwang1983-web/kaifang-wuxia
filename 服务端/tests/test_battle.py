"""战斗：遭遇 / 结束 / D4 / D8 的期望值来自对原版的实测（2026-10，tools/battle_compare.py）；进战之后的帧序列按客户端侧反编译（没对过原版）。"""

import random
import unittest

from jyserver.battle import Battles, Enemy, Mob, Mobs, Session, le32
from jyserver.state import ItemTable

JY = 8617293
EID = 100038166


def rows(hp=2000, **kw):
    r = {"renwu": [{"jyid": str(JY), "dangqianxue": str(hp), "wuqiqiangdu": "300", "str": "30", "fangjuqiangdu": "200", "vit": "30", "combat_exp": "0"}], "item": []}
    r["renwu"][0].update({k: str(v) for k, v in kw.items()})
    return r


def battles(**kw):
    mob = Mob(38166, "倭寇", 1700000, 19000, 135, 135, [15019], 100)
    return Battles(Mobs({38166: mob}), ItemTable({15019: 200}), {1000: 176}, random.Random(1))


def act(caster, cell=(30, 27), skill=1000, level=10):
    p = bytearray(28)
    p[0:4] = le32(caster)
    p[4] = 3
    p[6:10] = le32(skill * 100 + 1)
    p[11], p[12] = cell
    p[25:27] = level.to_bytes(2, "little")
    return bytes(p)


def hexs(frames):
    return [(op, p.hex(" "), w) for op, p, w in frames]


class EncounterTests(unittest.TestCase):
    def test_encounter_frames(self):
        b = battles()
        out = b.encounter(rows(), JY, le32(EID) + bytes(19))
        self.assertEqual([op for op, _, _ in out], [0xD1, 0x82, 0xDC])
        d1 = out[0][1]
        self.assertEqual((len(d1), d1[:6].hex(" "), d1[6:16]), (24, "01 00 16 76 f6 05", bytes(10)))
        self.assertEqual(hexs(out[1:]), [(0x82, "4d 7d 83 00 02 00", True), (0xDC, "01 00 4d 7d 83 00 01 00 00 00 d0 07 00 00 00 00 00 00 00 00 00 00 00", False)])
        self.assertIn(JY, b.sessions)

    def test_small_entity_only_lists_us_and_unknown_mob_is_refused(self):
        b = battles()
        self.assertEqual(hexs(b.encounter(rows(), JY, le32(38166) + bytes(19))), [(0xD5, "01 00 4d 7d 83 00 55 09", False)])
        self.assertNotIn(JY, b.sessions)
        out = battles().encounter(rows(), JY, le32(100000001) + bytes(19))
        self.assertEqual((out[0][0], out[0][1][1:].decode("latin1")[-9:]), (0x1A, "100000001"))
        self.assertEqual(b.encounter(rows(), JY, b"\x01"), [])

    def test_enter_sends_lists_positions_hp_and_heartbeat(self):
        b = battles()
        b.encounter(rows(), JY, le32(EID) + bytes(19))
        out = b.enter(rows(), JY, le32(JY) + bytes([5, 6, 1, 0]))
        self.assertEqual([op for op, _, _ in out], [0xD5, 0xD5, 0xD4, 0xDC, 0xC6])
        self.assertEqual(out[1][1].hex(" "), "01 00 16 76 f6 05 55 08")
        self.assertEqual(out[3][1].hex(" ")[:41], "01 00 16 76 f6 05 01 00 00 00 38 4a 00 00")
        self.assertEqual(b.enter(rows(), JY, le32(JY) + bytes([5, 6, 1, 0])), [])  # 只进一次
        self.assertEqual(battles().enter(rows(), JY, le32(JY) + bytes([5, 6, 1, 0])), [])  # 没有战斗


class FightTests(unittest.TestCase):
    def setUp(self):
        self.b = battles()
        self.r = rows()
        self.b.encounter(self.r, JY, le32(EID) + bytes(19))
        self.b.enter(self.r, JY, le32(JY) + bytes([5, 6, 1, 0]))

    def test_player_hit_forwards_d7_and_broadcasts_absolute_hp(self):
        p = act(JY)
        out = self.b.act(self.r, JY, p)
        self.assertEqual(out[0], (0xD7, p[:16], False))
        self.assertEqual(out[1][0], 0xD8)
        hp = int.from_bytes(out[1][1][5:9], "little")
        self.assertEqual((out[1][1][:5], 0 < hp < 19000), (b"\x01" + le32(EID), True))
        self.assertEqual(self.b.sessions[JY].enemies[EID].hp, hp)

    def test_killing_sequence_drops_item_and_gives_combat_exp(self):
        self.b.sessions[JY].enemies[EID].hp = 1
        out = self.b.act(self.r, JY, act(JY))
        self.assertEqual([op for op, _, _ in out], [0xD7, 0xD8, 0xE6, 0xE4, 0x77, 0xE8, 0x7B])
        self.assertEqual(out[1][1][5:9], b"\x00\x00\x00\x00")
        self.assertEqual(out[3][1].hex(" "), "1e 1b ab 3a")  # 格 (30,27) + 物品 15019
        self.assertEqual(out[4][1].hex(" "), "ab 3a 00 00 c8 01")
        self.assertEqual(out[5][1].hex(" "), "4d 7d 83 00 1e 1b")
        self.assertEqual((out[6][1].hex(" "), self.r["renwu"][0]["combat_exp"]), ("2b 01 20 d1 19 00".replace("20 d1 19 00", (1700000).to_bytes(4, "little").hex(" ")), "1700000"))
        self.assertEqual([(i["item_id"], i["shuliang"]) for i in self.r["item"]], [("15019", "1")])
        self.assertEqual(self.b.act(self.r, JY, act(JY)), [])  # 敌人都死了

    def test_monster_hit_comes_from_the_client_and_hurts_us(self):
        out = self.b.act(self.r, JY, act(EID, cell=(5, 6)))
        self.assertEqual([op for op, _, _ in out], [0xD7, 0xD8, 0x7B])
        hp = int(self.r["renwu"][0]["dangqianxue"])
        self.assertTrue(0 < hp < 2000)
        self.assertEqual(out[1][1], b"\x01" + le32(JY) + le32(hp))
        self.assertEqual(out[2], (0x7B, b"\x18\x01" + le32(hp), True))
        self.assertEqual(self.b.act(self.r, JY, act(123456789)), [])  # 不是本场的怪

    def test_dead_players_and_short_payloads_are_ignored(self):
        self.r["renwu"][0]["dangqianxue"] = "0"
        self.assertEqual(self.b.act(self.r, JY, act(JY)), [])
        self.assertEqual(self.b.act(self.r, JY, act(EID)), [])
        self.assertEqual(self.b.act(rows(), JY, b"\x00" * 10), [])

    def test_end_reports_by_our_own_hp_and_clears_the_fight(self):
        out = self.b.end(self.r, JY, le32(JY) + b"\x01")
        self.assertEqual(hexs(out), [(0x81, "01", True), (0x82, "4d 7d 83 00 00 00", False), (0xE6, "4d 7d 83 00", False), (0x7B, "18 01 d0 07 00 00", True)])
        self.assertNotIn(JY, self.b.sessions)
        # 气血 ≤ 1 = 死亡（原版对 HP=0 / 1 / 2 实测）：你已死亡、81 02、7B 18 01、82、E6、7B 18 01；气血记为 1
        for hp in (0, 1):
            r = rows(hp=hp)
            out = self.b.end(r, JY, le32(JY) + b"\x01")
            self.assertEqual(
                hexs(out),
                [(0x14, "08 a7 41 a4 77 a6 ba a4 60", True), (0x81, "02", False), (0x7B, "18 01 01 00 00 00", True), (0x82, "4d 7d 83 00 00 00", False), (0xE6, "4d 7d 83 00", False), (0x7B, "18 01 01 00 00 00", True)],
            )
            self.assertEqual(r["renwu"][0]["dangqianxue"], "1")
        self.assertEqual(self.b.end(rows(hp=2), JY, le32(JY) + b"\x01")[0], (0x81, b"\x01", True))

    def test_group_encounter_uses_the_first_padding_byte_as_the_count(self):
        b = battles()
        b.encounter(rows(), JY, le32(EID) + bytes([3]) + bytes(18))
        s = b.sessions[JY]
        self.assertEqual(list(s.enemies), [EID, EID + 100000, EID + 200000])
        self.assertEqual(len({e.cell for e in s.enemies.values()}), 3)
        out = b.enter(rows(), JY, le32(JY) + bytes([5, 6, 1, 0]))
        self.assertEqual(out[1][1][:2], b"\x03\x00")
        for n in (0, 6, 255):
            b2 = battles()
            b2.encounter(rows(), JY, le32(EID) + bytes([n]) + bytes(18))
            self.assertEqual(len(b2.sessions[JY].enemies), 1)

    def test_d4_xors_the_coordinates_and_d8_depends_on_being_in_battle(self):
        self.assertEqual(hexs(self.b.move(self.r, JY, le32(EID) + bytes([0x1E, 0x1B, 0x05, 0xAA]))), [(0xD4, "16 76 f6 05 1e 1b", False)])
        self.assertEqual(self.b.move(self.r, JY, b"\x00" * 5), [])
        self.assertEqual(hexs(self.b.status(self.r, JY, bytes(13))), [(0xD8, "01", True)])
        self.assertEqual(hexs(battles().status(self.r, JY, bytes(13))), [(0xEF, "4d 7d 83 00 10", False)])
        b = battles()
        b.encounter(self.r, JY, le32(EID) + bytes(19))
        self.assertEqual(b.status(self.r, JY, bytes(13)), [])  # 遭遇了、没进场：静默

    def test_pose_commands_echo_a_d7_and_need_a_live_entered_fight(self):
        pose = lambda cmd: le32(JY) + bytes([cmd]) + le32(1) + b"\x00"
        for cmd in (7, 8, 9, 11):
            self.assertEqual(hexs(self.b.pose(self.r, JY, pose(cmd))), [(0xD7, le32(JY).hex(" ") + f" {cmd:02x}" + " 00" * 11, False)])
        for bad in (pose(2), pose(10), pose(12), pose(7)[:9]):
            self.assertEqual(self.b.pose(self.r, JY, bad), [])
        self.assertEqual(battles().pose(self.r, JY, pose(7)), [])  # 没有战斗
        b = battles()
        b.encounter(self.r, JY, le32(EID) + bytes(19))
        self.assertEqual(b.pose(self.r, JY, pose(7)), [])  # 还没进场
        self.r["renwu"][0]["dangqianxue"] = "0"
        self.assertEqual(self.b.pose(self.r, JY, pose(7)), [])  # 倒下了

    def test_escape_is_a_random_bit_that_changes_nothing(self):
        got = [self.b.escape(self.r, JY, b"") for _ in range(400)]
        self.assertTrue(all(o[0][0] == 0xF9 and o[0][1] in (b"\x00", b"\x01") and o[0][2] is False for o in got))
        ones = sum(o[0][1] == b"\x01" for o in got)
        self.assertTrue(120 < ones < 200, ones)  # 约 40%
        self.assertEqual(len(battles().escape(rows(), JY, b"x" * 9)), 1)  # 没有战斗、有载荷也照回
        self.assertIn(JY, self.b.sessions)  # 不结束战斗

    def test_small_entity_locks_encounters_until_the_fight_is_reported_over(self):
        b = battles()
        b.encounter(self.r, JY, le32(38166) + bytes(19))
        self.assertEqual(b.encounter(self.r, JY, le32(EID) + bytes(19)), [])
        self.assertEqual(b.encounter(self.r, JY, le32(100000001) + bytes(19)), [])
        self.assertEqual(hexs(b.status(self.r, JY, bytes(13))), [(0xEF, "4d 7d 83 00 10", False)])
        b.end(self.r, JY, le32(JY) + b"\x01")
        self.assertEqual([op for op, _, _ in b.encounter(self.r, JY, le32(EID) + bytes(19))], [0xD1, 0x82, 0xDC])


if __name__ == "__main__":
    unittest.main()
