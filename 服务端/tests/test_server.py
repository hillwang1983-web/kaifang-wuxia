"""新服务端的行为测试：与原版服务端的真实回包夹具逐帧对照。"""

import asyncio
import json
import random
import struct
import unittest
from pathlib import Path

from jyserver.codec import KEY_C2S_HANDSHAKE, FrameReader, c2s_key, derive_key, encode_c2s
from jyserver.server import DEFAULT_DATA_DIR, GameServer, roll_stats
from jyserver.state import ItemTable
from jyserver.store import CharacterStore

FIX_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
FIXTURE = json.loads((FIX_DIR / "login-8617293.json").read_text(encoding="utf-8"))
JYID = FIXTURE["jyid"]
UNKNOWN_CONST = 0x0005FCF7


def make_store():
    """把快照夹具里的三个测试号放进内存角色库；密码 = jyid（原版测试号如此）。"""
    store = CharacterStore()
    for jyid in (8617293, 1234567, 123456):
        rows = json.loads((FIX_DIR / f"char-{jyid}.json").read_text(encoding="utf-8"))["rows"]
        store.put(jyid, str(jyid), rows)
    # 一个被禁用的号（原版 account.state=0）
    rows = json.loads((FIX_DIR / "char-8617293.json").read_text(encoding="utf-8"))["rows"]
    store.put(996633, "996633", rows, state=0)
    return store


def login_frame(jyid=JYID, seq=1, password=None):
    # 登录包末尾的 ASCII 是明文密码（测试号的密码恰好等于 jyid）
    payload = struct.pack("<II", jyid, UNKNOWN_CONST) + str(password if password is not None else jyid).encode("ascii")
    return encode_c2s(0x01, payload, key=KEY_C2S_HANDSHAKE, seq=seq, wide=False)


class TestClient:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.rx = FrameReader("s2c", resync=True)
        self.frames = []
        self.raw = b""
        self.eof = False

    async def pump(self, seconds):
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end and not self.eof:
            try:
                data = await asyncio.wait_for(self.reader.read(65536), timeout=max(0.01, end - asyncio.get_event_loop().time()))
            except asyncio.TimeoutError:
                break
            if not data:
                self.eof = True
                break
            self.raw += data
            self.frames += self.rx.feed(data)

    def send(self, data):
        self.writer.write(data)

    async def close(self):
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), timeout=2)
        except Exception:
            pass


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.gs = GameServer(make_store(), ItemTable.load(DEFAULT_DATA_DIR), rng=random.Random(1))
        self.server = await self.gs.serve("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        # 先关客户端：新版 Python 的 Server.wait_closed() 会等所有连接都关闭
        for c in self.clients:
            await c.close()
        self.server.close()
        await asyncio.wait_for(self.server.wait_closed(), timeout=5)
        self.gs.store.close()

    async def connect(self):
        r, w = await asyncio.open_connection("127.0.0.1", self.port)
        c = TestClient(r, w)
        self.clients.append(c)
        return c

    async def login(self):
        c = await self.connect()
        c.send(login_frame())
        await c.pump(0.3)
        return c

    async def test_handshake_matches_original_bytes(self):
        c = await self.login()
        f0 = FIXTURE["frames"][0]
        # 线路上：34 字节帧 + 1 个明文 00（与原版一致）
        self.assertEqual(c.raw, bytes.fromhex(f0["wire"]) + b"\x00")

    async def test_unknown_account_is_dropped_without_reply(self):
        c = await self.connect()
        c.send(login_frame(jyid=424242))
        await c.pump(0.5)
        self.assertEqual(c.frames, [])  # 实测：原版对不存在的账号不回包，直接断开
        self.assertTrue(c.eof)

    async def test_wrong_password_gets_reject(self):
        c = await self.connect()
        c.send(login_frame(password="not-the-password"))
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in c.frames], [(0x01, b"\x00\x00")])

    async def test_start_login_stream_equals_original(self):
        c = await self.login()
        n = len(c.frames)
        c.send(encode_c2s(0x19, b"\x00", key=c2s_key(2), seq=2))
        await c.pump(0.5)
        got = c.frames[n:]
        # login-8617293.json 是更早录的（角色数据后来变过），逐帧对照用当前数据库快照的那份
        want = json.loads((FIX_DIR / "char-8617293.json").read_text(encoding="utf-8"))["frames"][1:]
        self.assertEqual(len(got), len(want))
        for i, (g, w) in enumerate(zip(got, want)):
            self.assertEqual((g.opcode, g.key, g.wide), (w["opcode"], w["key"], w["wide"]), f"frame {i}")
            gp, wp = bytearray(g.payload), bytearray(bytes.fromhex(w["payload"]))
            if g.opcode == 0x1E:  # 载荷[0:4] 是服务端运行分钟数
                gp[0:4] = wp[0:4] = bytes(4)
            if g.opcode == 0x08:  # 最后 1 字节是随机值
                gp[-1] = wp[-1] = 0
            self.assertEqual(bytes(gp), bytes(wp), f"frame {i} (op 0x{w['opcode']:02x})")

    async def _start(self, jyid):
        c = await self.connect()
        c.send(login_frame(jyid=jyid))
        await c.pump(0.3)
        n = len(c.frames)
        c.send(encode_c2s(0x19, b"\x00", key=c2s_key(2), seq=2))
        await c.pump(0.5)
        return c.frames[n:]

    async def test_other_accounts_get_their_own_data(self):
        for jyid in (1234567, 123456):
            frames = await self._start(jyid)
            state = frames[0].payload
            self.assertEqual(frames[0].opcode, 0x1E)
            n = int.from_bytes(state[4:6], "little")
            self.assertEqual(int.from_bytes(state[6 + 5 * n + 45 : 6 + 5 * n + 49], "little"), jyid)  # 模板偏移 166 = 121 + 45

    async def test_only_top_sponsor_gets_king_broadcast(self):
        self.assertEqual(len(await self._start(123456)), 19)
        self.assertEqual(len(await self._start(1234567)), 18)

    async def test_disabled_account_is_rejected(self):
        c = await self.connect()
        c.send(login_frame(jyid=996633))
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in c.frames], [(0x01, b"\x00\x00")])

    async def test_roll_reply_shape(self):
        c = await self.login()
        n = len(c.frames)
        c.send(encode_c2s(0x76, b"", key=c2s_key(2), seq=2))
        await c.pump(0.3)
        f = c.frames[n]
        self.assertEqual((f.opcode, f.wide, f.key, f.total_length), (0x5A, True, 0x7D, 13))
        self.assertEqual(f.payload[0], 0x03)
        vals = list(f.payload[1:])
        self.assertEqual(len(vals), 7)
        self.assertTrue(all(15 <= v <= 25 for v in vals))
        self.assertEqual(sum(vals), 140)

    async def test_wrong_key_is_ignored_then_correct_key_works(self):
        c = await self.login()
        n = len(c.frames)
        c.send(encode_c2s(0x76, b"", key=0x7D, seq=2))  # 错误密钥：原版静默忽略
        await c.pump(0.3)
        self.assertEqual(len(c.frames), n)
        c.send(encode_c2s(0x76, b"", key=c2s_key(3), seq=3))
        await c.pump(0.3)
        self.assertEqual(c.frames[n].opcode, 0x5A)

    async def test_duplicate_seq_disconnects(self):
        c = await self.login()
        c.send(encode_c2s(0x76, b"", key=c2s_key(2), seq=2))
        await c.pump(0.2)
        c.send(encode_c2s(0x76, b"", key=c2s_key(2), seq=2))
        await c.pump(0.5)
        self.assertTrue(c.eof)

    async def test_commands_before_handshake_are_ignored(self):
        c = await self.connect()
        c.send(encode_c2s(0x76, b"", key=c2s_key(2), seq=2))
        await c.pump(0.3)
        self.assertEqual(c.frames, [])
        self.assertFalse(c.eof)

    async def test_bad_start_login_payload_disconnects(self):
        c = await self.login()
        c.send(encode_c2s(0x19, b"\x00\x00", key=c2s_key(2), seq=2))
        await c.pump(0.5)
        self.assertTrue(c.eof)


class AccountWireTests(unittest.IsolatedAsyncioTestCase):
    """删除角色（选角色界面）、二级密码走线路。"""

    asyncSetUp = ServerTests.asyncSetUp
    asyncTearDown = ServerTests.asyncTearDown
    connect = ServerTests.connect
    login = ServerTests.login

    async def test_delete_character_before_entering_world(self):
        c = await self.login()
        n = len(c.frames)
        c.send(encode_c2s(0x33, bytes([0, 7]) + b"8617294", key=c2s_key(2), seq=2))
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in c.frames[n:]], [(0x1A, bytes.fromhex("64 b1 4b bd 58 bf f9 bb 7e"))])
        self.assertTrue(self.gs.store.get(JYID).has_character)
        c.send(encode_c2s(0x33, bytes([0, 7]) + b"8617293", key=c2s_key(3), seq=3))
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in c.frames[n + 1 :]], [(0x36, b"\x01")])
        self.assertFalse(self.gs.store.get(JYID).has_character)
        self.assertEqual(self.gs.store.get(JYID).rows["account"][0]["shangchengdianshu"], "3000")  # 账号还在

    async def test_password_check_and_echo(self):
        c = await self.login()
        n = len(c.frames)
        c.send(encode_c2s(0x98, bytes([0x0D, 7]) + b"8617293", key=c2s_key(2), seq=2))
        c.send(encode_c2s(0x98, bytes.fromhex("0f0102030405"), key=c2s_key(3), seq=3))
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.payload.hex()) for f in c.frames[n:]], [(0xB8, "10"), (0xB8, "130102030405")])


class WorldTests(unittest.IsolatedAsyncioTestCase):
    """两个玩家同时在线：上线/下线广播、公共聊天、移动。对照原版实测（tools/multi_probe.py、enter_probe.py）。"""

    async def asyncSetUp(self):
        self.store = make_store()
        # 把 1234567 放到 8617293 所在的地图 2200，方便测同图广播；123456 留在别的地图 2801
        b = self.store.get(1234567)
        b.rows["renwu"][0]["map"] = "2200"
        self.store.put(1234567, b.password, b.rows)
        self.gs = GameServer(self.store, ItemTable.load(DEFAULT_DATA_DIR), rng=random.Random(1))
        self.server = await self.gs.serve("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            await c.close()
        self.server.close()
        await asyncio.wait_for(self.server.wait_closed(), timeout=5)
        self.gs.store.close()

    async def enter(self, jyid):
        r, w = await asyncio.open_connection("127.0.0.1", self.port)
        c = TestClient(r, w)
        c.seq = 1
        self.clients.append(c)
        c.send(login_frame(jyid=jyid))
        await c.pump(0.2)
        await self.cmd(c, 0x19, b"\x00", 0.3)
        c.frames.clear()
        return c

    async def cmd(self, c, op, payload, wait=0.2):
        c.seq += 1
        c.send(encode_c2s(op, payload, key=c2s_key(c.seq, getattr(c, "base", 0x7D)), seq=c.seq))
        for other in self.clients:  # 广播的接收方也要收一下
            await other.pump(wait)

    async def settle(self, *clients):
        """收掉还在路上的上线广播再清空，免得混进断言。"""
        for c in clients:
            await c.pump(0.2)
            c.frames.clear()

    @staticmethod
    def ops(c):
        return [(f.opcode, f.payload) for f in c.frames]

    async def test_enter_broadcasts_appear_frames_to_others_only(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await a.pump(0.2)
        self.assertEqual([f.opcode for f in a.frames], [0x60, 0x14, 0x02])
        self.assertEqual(a.frames[0].payload[:4], (1234567).to_bytes(4, "little"))
        self.assertEqual(b.frames, [])

    async def test_chat_is_relayed_raw_and_costs_diet_water(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        text = bytes.fromhex("b4e5c0b841")  # 非 ASCII 字节原样转发
        await self.cmd(a, 0x02, b"\x01" + text)
        self.assertEqual(self.ops(b), [(0x04, b"\x01" + (8617293).to_bytes(4, "little") + text)])
        self.assertEqual(self.ops(a), [(0x7B, b"\x34\x01\x5f\x00\x00\x00"), (0x7B, b"\x36\x01\x5f\x00\x00\x00")])
        self.assertTrue(all(f.wide for f in a.frames))
        a.frames.clear()
        await self.cmd(a, 0x02, b"\x01x")
        self.assertEqual(self.ops(a)[0], (0x7B, b"\x34\x01\x5a\x00\x00\x00"))

    async def test_diet_floors_at_zero(self):
        c = self.store.get(8617293)
        c.rows["renwu"][0]["diet_val"] = "3"
        self.store.put(8617293, c.password, c.rows)
        a = await self.enter(8617293)
        await self.cmd(a, 0x02, b"\x01a")
        self.assertEqual(self.ops(a)[0], (0x7B, b"\x34\x01\x00\x00\x00\x00"))

    async def test_chat_other_subtype_and_malformed_are_ignored(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x02, b"\x05hi")
        await self.cmd(a, 0x02, b"\x01")
        self.assertEqual((a.frames, b.frames), ([], []))

    async def test_move_echoes_to_same_map_including_self(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        c = await self.enter(123456)  # 别的地图
        await self.settle(a, b, c)
        step = struct.pack("<HHHH", 510, 410, 520, 415)
        await self.cmd(a, 0x06, step + b"\x00\x00\x00")
        want = [(0x06, (8617293).to_bytes(4, "little") + step)]
        self.assertEqual((self.ops(a), self.ops(b), self.ops(c)), (want, want, []))
        self.assertEqual(self.gs.online[8617293].renwu["x"], "520")

    async def test_leave_notifies_others_and_saves_position(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x06, struct.pack("<HHHH", 510, 410, 530, 420) + b"\x00\x00\x00")
        a.frames.clear()
        await b.close()
        await a.pump(0.4)
        self.assertEqual([f.opcode for f in a.frames], [0x05, 0x14])
        self.assertEqual(a.frames[0].payload, (1234567).to_bytes(4, "little") + b"\x00")
        self.assertNotIn(1234567, self.gs.online)
        await a.close()
        await asyncio.sleep(0.2)
        saved = self.store.get(8617293).rows["renwu"][0]
        self.assertEqual((saved["x"], saved["y"]), ("530", "420"))

    async def test_equip_unequip_are_private_but_cheat_notice_is_global(self):
        a = await self.enter(123456)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x16, b"\x06")
        self.assertEqual([f.opcode for f in a.frames], [0x18, 0x7B])
        self.assertEqual(b.frames, [])  # 实测：脱装备不广播
        a.frames.clear()
        await self.cmd(a, 0x15, b"\x06" + struct.pack("<I", 12498) + b"\x32")
        self.assertEqual([f.opcode for f in a.frames], [0x17, 0x7B])
        self.assertEqual(self.gs.online[123456].renwu["wuqi"], "12498")
        a.frames.clear()
        await self.cmd(a, 0x15, b"\x01" + struct.pack("<I", 25090) + b"\x32")  # 背包里有，但 toukui 槽已占 → 静默
        self.assertEqual((a.frames, b.frames), ([], []))
        await self.cmd(a, 0x15, b"\x05" + struct.pack("<I", 99) + b"\x32")  # 没有的物品 → 全服广播
        self.assertEqual([f.opcode for f in a.frames], [0x14])
        self.assertEqual([f.opcode for f in b.frames], [0x14])
        self.assertEqual(a.frames[0].payload, b.frames[0].payload)

    async def test_use_item_consumes_and_persists(self):
        a = await self.enter(123456)
        await self.settle(a)
        row = next(r for r in self.gs.online[123456].char.rows["item"] if r["item_id"] == "58182")  # 记忆天书(满) x130
        self.assertEqual(row["shuliang"], "130")
        await self.cmd(a, 0x0B, struct.pack("<I", 99999999))  # 没有的物品
        self.assertEqual([f.opcode for f in a.frames], [0x1A, 0x05, 0x14])
        await a.close()
        await asyncio.sleep(0.2)
        self.assertIn("item", self.store.get(123456).rows)

    async def test_discard_tells_same_map_only_and_records_ground_item(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)  # 同在地图 2200
        c = await self.enter(123456)  # 地图 2801
        await self.settle(a, b, c)
        await self.cmd(a, 0x0D, struct.pack("<I", 58182) + b"\xc8" + struct.pack("<I", 1))
        self.assertEqual((a.frames, c.frames), ([], []))
        self.assertEqual([f.opcode for f in b.frames], [0x0D])
        self.assertEqual(b.frames[0].payload[:8], (8617293).to_bytes(4, "little") + struct.pack("<I", 58182))
        self.assertEqual([(g["item"], g["owner"], g["map"]) for g in self.gs.ground], [(58182, 8617293, 2200)])

    async def test_trade_request_lock_cancel_over_the_wire(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x1C, (1234567).to_bytes(4, "little"))
        self.assertEqual([f.opcode for f in a.frames], [0x1F])
        self.assertEqual([f.opcode for f in b.frames], [0x1F, 0x82, 0x82])
        a.frames.clear(), b.frames.clear()
        await self.cmd(b, 0x1D, b"\x01")
        await self.cmd(a, 0x1D, b"\x01")
        self.assertEqual(([f.opcode for f in a.frames], [f.opcode for f in b.frames]), ([0x23, 0x23], [0x23, 0x23]))
        a.frames.clear(), b.frames.clear()
        await self.cmd(a, 0x1D, b"\x00")
        self.assertEqual((a.frames[0].payload, b.frames[0].payload), (b"\x00" + (8617293).to_bytes(4, "little"),) * 2)
        await b.close()  # 下线时会话也清掉，不留尾巴
        await asyncio.sleep(0.2)
        self.assertEqual(self.gs.trades.by_player, {})

    async def test_drop_then_pickup_over_the_wire(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        drop = struct.pack("<I", 58182) + b"\xc8" + struct.pack("<I", 1)
        await self.cmd(a, 0x0D, drop)
        b.frames.clear()
        await self.cmd(b, 0x0F, drop)
        self.assertEqual(([f.opcode for f in a.frames], [f.opcode for f in b.frames]), ([0x11], [0x10]))
        self.assertEqual(self.gs.ground, [])
        a.frames.clear(), b.frames.clear()
        await self.cmd(b, 0x0F, drop)  # 已经捡走了
        self.assertEqual((a.frames, b.frames), ([], []))

    async def test_team_create_join_chat_and_logout_over_the_wire(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        c = await self.enter(123456)
        await self.settle(a, b, c)
        await self.cmd(a, 0x26, b"")
        self.assertEqual([[f.opcode for f in x.frames] for x in (a, b, c)], [[0x2A]] * 3)  # 全服都收到
        for x in (a, b, c):
            x.frames.clear()
        await self.cmd(b, 0x2D, b"\x01" + (8617293).to_bytes(4, "little"))
        self.assertEqual([[f.opcode for f in x.frames] for x in (a, b, c)], [[0x2F]] * 3)
        for x in (a, b, c):
            x.frames.clear()
        await self.cmd(a, 0x2E, b"\x00\x00\x00\x00hi")
        self.assertEqual(([f.payload for f in a.frames], [f.payload for f in b.frames], c.frames), ([b"hi"], [b"hi"], []))  # 只有队里的人
        a.frames.clear(), b.frames.clear()
        await a.close()  # 队长下线 = 解散，全服收到 0x2B
        await asyncio.sleep(0.4)
        await b.pump(0.2)
        self.assertEqual([f.opcode for f in b.frames][:1], [0x2B])
        self.assertEqual(self.gs.teams.team_of.get(1234567, 0), 0)

    async def test_org_create_recruit_join_chat_leave_over_the_wire(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        c = await self.enter(123456)
        await self.settle(a, b, c)
        le = lambda n: n.to_bytes(4, "little")  # noqa: E731
        await self.cmd(a, 0x45, b"ab")
        self.assertEqual([f.opcode for f in a.frames], [0x4F, 0x14])
        self.assertEqual(a.frames[0].payload, le(8617293) + b"\x01\x00ab")
        self.assertEqual(([f.opcode for f in b.frames], [f.opcode for f in c.frames]), ([0x14], [0x14]))
        for x in (a, b, c):
            x.frames.clear()
        await self.cmd(a, 0x4E, le(1234567))  # 只发给被招收的人
        self.assertEqual(([f.opcode for f in a.frames], [f.opcode for f in b.frames], c.frames), ([], [0x54], []))
        self.assertEqual(len(b.frames[0].payload), 4 + 1 + 2 + 1802)
        b.frames.clear()
        await self.cmd(b, 0x4F, b"\x01" + le(8617293))
        self.assertEqual([[(f.opcode, f.payload) for f in x.frames] for x in (a, b, c)], [[(0x55, le(1234567) + b"\x01\x01\x00")]] * 3)
        for x in (a, b, c):
            x.frames.clear()
        await self.cmd(b, 0x02, b"\x05yo")  # 组织聊天：只有 A，发送者不回显，也不扣饮食饮水
        self.assertEqual(([(f.opcode, f.payload) for f in a.frames], b.frames, c.frames), ([(0x04, b"\x05" + le(1234567) + b"yo")], [], []))
        a.frames.clear()
        await self.cmd(a, 0x4F, b"\x07")
        self.assertEqual(a.frames[0].opcode, 0xAD)
        self.assertEqual(a.frames[0].payload[:2], b"\x10\x05")
        a.frames.clear()
        await self.cmd(b, 0x51, b"\x01")
        self.assertEqual([f.opcode for f in c.frames], [0x57])
        self.assertEqual(self.gs.orgs.orgs[0].members, [8617293])
        a.frames.clear(), b.frames.clear(), c.frames.clear()
        await self.cmd(b, 0x02, b"\x05yo")
        self.assertEqual((a.frames, b.frames, c.frames), ([], [], []))

    async def test_nickname_change_is_announced_to_everyone_and_delete_is_ignored_in_world(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x13, b"abc")
        self.assertEqual([f.opcode for f in a.frames], [0x15, 0x14])
        self.assertEqual([f.opcode for f in b.frames], [0x14])
        self.assertTrue(b.frames[0].payload.endswith(b"V7Z0-abc"))
        self.assertEqual(self.gs.online[8617293].renwu["nickname"], "abc")
        a.frames.clear()
        await self.cmd(a, 0x33, bytes([0, 7]) + b"8617293")  # 进入世界后原版会崩；这里不理会
        self.assertEqual(a.frames, [])
        self.assertTrue(self.gs.online[8617293].char.has_character)

    async def test_text_commands_where_kale_and_school_change(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0xC7, b"\x04\x40where")
        self.assertEqual([f.opcode for f in a.frames], [0x04])
        self.assertEqual(a.frames[0].payload[5:], b"2200")
        a.frames.clear(), b.frames.clear()
        self.gs.online[8617293].char.rows["account"][0]["shangchengdianshu"] = "20000"
        await self.cmd(a, 0xC7, b"\x04\x40mp 3")
        self.assertEqual([f.opcode for f in a.frames], [0x32, 0x14, 0x7B, 0x7B, 0x14, 0x05, 0x14])
        self.assertEqual([f.opcode for f in b.frames[:1]], [0x14])  # 全服公告「土豪：…更換了門派」
        await asyncio.sleep(0.3)
        self.assertNotIn(8617293, self.gs.online)  # 改门派后被踢下线
        self.assertEqual(self.store.get(8617293).rows["renwu"][0]["school"], "12")
        self.assertEqual(self.store.get(8617293).rows["account"][0]["shangchengdianshu"], "10001")

    async def test_discard_and_recycle_over_the_wire(self):
        a = await self.enter(8617293)
        await self.settle(a)
        await self.cmd(a, 0x99, b"\x23" + struct.pack("<I", 99999999) + b"\xc8\x01")  # 没有的物品
        self.assertEqual([f.opcode for f in a.frames], [0x1A, 0x05])

    async def test_event_gives_marker_and_persists_on_leave(self):
        """C2S 0x6B：事件 8/3（标记:50528:1）。回包 0x77 + 0x14 + 0x7D，离线落库；期望值来自原版（tests/test_events.py 有完整对照）。"""
        a = await self.enter(8617293)
        await self.cmd(a, 0x5D, struct.pack("<HHH", 8, 100, 100))
        a.frames.clear()
        await self.cmd(a, 0x6B, bytes(4) + struct.pack("<HH", 8, 3))
        self.assertEqual([f.opcode for f in a.frames], [0x77, 0x14, 0x7D])
        self.assertEqual(a.frames[0].payload.hex(" "), "60 c5 00 00 c8 01")
        self.assertEqual(a.frames[2].payload.hex(" "), "03 00 00 00 08 00")
        await a.close()
        await asyncio.sleep(0.2)
        self.assertIn(("50528", "200"), [(r["biaoji"], r["zhuangtai"]) for r in self.store.get(8617293).rows["biaoji"]])

    async def test_event_on_wrong_map_warns_everyone(self):
        a = await self.enter(8617293)  # 地图 2200
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(a, 0x6B, bytes(4) + struct.pack("<HH", 8, 3))  # 人不在地图 8
        self.assertEqual([f.opcode for f in a.frames], [0x7D, 0x14])
        self.assertEqual(a.frames[0].payload, b"\x03\x00")
        self.assertEqual([f.opcode for f in b.frames], [0x14])
        self.assertEqual(a.frames[1].payload[0], 0x0E)
        self.assertEqual(a.frames[1].payload, b.frames[0].payload)

    async def test_teleport_to_other_map(self):
        a = await self.enter(8617293)  # 地图 2200
        b = await self.enter(1234567)  # 测试里被放到 2200
        c = await self.enter(123456)  # 地图 2801
        await self.settle(a, b, c)
        await self.cmd(b, 0x5D, struct.pack("<HHH", 2801, 4242, 1742))
        self.assertEqual([f.opcode for f in b.frames], [0x08, 0x02, 0x6D, 0x3D, 0x31, 0x02, 0x82])
        self.assertEqual(b.frames[0].payload[:6], struct.pack("<HHH", 2801, 4242, 1742))
        self.assertTrue(2 <= b.frames[0].payload[6] <= 9)
        self.assertEqual(b.frames[5].payload[:4], (123456).to_bytes(4, "little"))  # 对图上已有的人：0x02 + 0x82
        self.assertEqual(b.frames[6].payload, (123456).to_bytes(4, "little") + b"\x00\x00")
        self.assertEqual(self.ops(a), [(0x62, (1234567).to_bytes(4, "little"))])
        enter = "87 d6 12 00 f1 0a 92 10 ce 06 01 " + "00 " * 42 + "14"  # 原版实测的 0x61 字节
        self.assertEqual(self.ops(c), [(0x61, bytes.fromhex(enter.replace(" ", "")))])
        self.assertEqual(self.gs.online[1234567].map, 2801)

    async def test_teleport_within_map_reports_leave_then_enter(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        await self.settle(a, b)
        await self.cmd(b, 0x5D, struct.pack("<HHH", 2200, 600, 450))
        self.assertEqual([f.opcode for f in b.frames], [0x08, 0x02, 0x6D, 0x3D, 0x31])  # 同图：没有对方的外观包
        self.assertEqual([f.opcode for f in a.frames], [0x62, 0x61])

    async def test_login_into_occupied_map_lists_neighbours(self):
        a = await self.enter(8617293)
        r, w = await asyncio.open_connection("127.0.0.1", self.port)
        b = TestClient(r, w)
        b.seq = 1
        self.clients.append(b)
        b.send(login_frame(jyid=1234567))
        await b.pump(0.2)
        b.frames.clear()
        await self.cmd(b, 0x19, b"\x00", 0.5)
        ops = [f.opcode for f in b.frames]
        i = ops.index(0x31)
        self.assertEqual(ops[i + 1 : i + 4], [0x02, 0x82, 0x2F])
        self.assertEqual(b.frames[i + 1].payload[:4], (8617293).to_bytes(4, "little"))

    async def test_whisper_reaches_only_the_target_and_costs_nothing(self):
        a = await self.enter(8617293)
        b = await self.enter(1234567)
        c = await self.enter(123456)
        await self.settle(a, b, c)
        text = bytes.fromhex("b4e5c0b841")
        await self.cmd(a, 0x03, (1234567).to_bytes(4, "little") + text)
        self.assertEqual([(f.opcode, f.wide, f.payload) for f in b.frames], [(0x04, True, b"\x03" + (8617293).to_bytes(4, "little") + text)])
        self.assertEqual((a.frames, c.frames), ([], []))  # 没有饮食扣减，也没有别人收到

    async def test_whisper_to_offline_player_is_silent(self):
        a = await self.enter(8617293)
        await self.settle(a)
        await self.cmd(a, 0x03, (999).to_bytes(4, "little") + b"hi")
        self.assertEqual(a.frames, [])

    async def test_tick_sends_heartbeat_then_rekeys_both_directions(self):
        a = await self.enter(8617293)
        await self.settle(a)
        before = int(self.gs.online[8617293].renwu["online_time"])
        self.gs.on_tick()
        await a.pump(0.3)
        self.assertEqual([f.opcode for f in a.frames], [0x33, 0x99])
        hb, rekey = a.frames
        self.assertEqual((hb.key, hb.wide, rekey.key, rekey.wide), (0x7D, True, 0x7D, False))  # 这两帧还用旧密钥
        self.assertEqual(hb.payload, (self.gs.tick).to_bytes(4, "little") + (before + 10).to_bytes(4, "little"))
        self.assertEqual(rekey.payload[0], 4)
        new_key = derive_key(rekey.payload[1:])
        a.base = new_key
        a.frames.clear()
        await self.cmd(a, 0x02, b"\x01x")  # 用新的密钥基数发指令，服务端要认
        self.assertEqual([f.opcode for f in a.frames], [0x7B, 0x7B])
        self.assertTrue(all(f.key == new_key for f in a.frames))  # 之后 S2C 也用新密钥

    async def test_tick_skips_players_not_in_the_world_and_old_key_stops_working(self):
        a = await self.enter(8617293)
        await self.settle(a)
        self.gs.on_tick()
        await a.pump(0.2)
        a.frames.clear()
        await self.cmd(a, 0x02, b"\x01y")  # 还用旧密钥基数 0x7D：被静默忽略
        self.assertEqual(a.frames, [])

    async def test_autosave_writes_online_players_without_waiting_for_logout(self):
        a = await self.enter(8617293)
        await self.cmd(a, 0x06, struct.pack("<HHHH", 510, 410, 540, 430) + b"\x00\x00\x00")
        self.assertEqual(self.store.get(8617293).rows["renwu"][0]["x"], "510")  # 还没存
        self.gs.autosave_interval = 0.05
        task = asyncio.create_task(self.gs._autosave_loop())
        try:
            await asyncio.sleep(0.3)
        finally:
            task.cancel()
        saved = self.store.get(8617293).rows["renwu"][0]
        self.assertEqual((saved["x"], saved["y"]), ("540", "430"))

    async def test_stop_saves_everyone_and_cancels_the_task(self):
        a = await self.enter(8617293)
        await self.cmd(a, 0x06, struct.pack("<HHHH", 510, 410, 550, 440) + b"\x00\x00\x00")
        self.gs.autosave_interval = 1000
        self.gs._autosave_task = asyncio.create_task(self.gs._autosave_loop())
        self.gs.stop()
        await asyncio.sleep(0)
        self.assertIsNone(self.gs._autosave_task)
        self.assertEqual(self.store.get(8617293).rows["renwu"][0]["x"], "550")

    async def test_commands_before_entering_world_are_ignored(self):
        r, w = await asyncio.open_connection("127.0.0.1", self.port)
        c = TestClient(r, w)
        c.seq = 1
        self.clients.append(c)
        c.send(login_frame(jyid=8617293))
        await c.pump(0.2)
        c.frames.clear()
        await self.cmd(c, 0x02, b"\x01hello")
        await self.cmd(c, 0x06, struct.pack("<HHHH", 1, 2, 3, 4))
        self.assertEqual(c.frames, [])


class RollStats(unittest.TestCase):
    def test_distribution_constraints(self):
        rng = random.Random(7)
        for _ in range(200):
            v = roll_stats(rng)
            self.assertEqual((len(v), sum(v)), (7, 140))
            self.assertTrue(all(15 <= x <= 25 for x in v))


if __name__ == "__main__":
    unittest.main()
