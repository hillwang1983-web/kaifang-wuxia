"""新建角色：纯函数 + 整条服务端流程，期望值来自对原版服务端的实测（tools/create_probe.py、
data/fixtures/char-9999013.json = 原版为新号 9999013 建出的角色的库行 + 真实登录序列）。"""

import asyncio
import json
import random
import struct
import unittest
from pathlib import Path

from jyserver import creation
from jyserver.codec import FrameReader, c2s_key, derive_key, encode_c2s
from jyserver.server import DEFAULT_DATA_DIR, NEW_ACCOUNT_HANDSHAKE, GameServer
from jyserver.state import ItemTable, Template, build_login_stream
from jyserver.store import CharacterStore

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "data" / "fixtures"
FIXTURE = json.loads((FIX / "char-9999013.json").read_text(encoding="utf-8"))

# 创建 9999013 时发给原版的那些东西
JYID, PASSWORD, NAME, NICK = 9999013, "pw9013", "newbie13", "nick13"
LONG_START = bytes.fromhex("00 e8 0c 08 6e 65 77 62 69 65 31 33 06 6e 69 63 6b 31 33 14 14 14 14 14 14 14 01 01 05 11")
STARTER = [(18072, 1), (15080, 1), (14056, 1), (13066, 1), (48022, 1), (48631, 1), (12130, 1), (11047, 1), (27058, 1), (26028, 1), (58182, 10), (40145, 1)]


def built_rows(defaults):
    rows = creation.blank_rows(defaults, JYID, creation.new_account_row(defaults, JYID))
    creation.create_character_rows(defaults, rows, JYID, NAME)
    creation.apply_create(rows, creation.parse_long_start(LONG_START), STARTER)
    return rows


class Pure(unittest.TestCase):
    def test_long_start_parsing(self):
        req = creation.parse_long_start(LONG_START)
        self.assertEqual((req.map, req.name, req.nick, req.attrs, req.head, req.mode, req.month, req.day),
                         (3304, b"newbie13", b"nick13", (20,) * 7, 1, 1, 5, 17))

    def test_rejects_short_or_overweight_requests(self):
        self.assertIsNone(creation.parse_long_start(LONG_START[:-1]))
        self.assertIsNone(creation.parse_long_start(b"\x00\x01"))
        fat = bytearray(LONG_START)
        fat[19] = 21  # 属性总和 141 → 仍然合法
        self.assertIsNotNone(creation.parse_long_start(bytes(fat)))
        fat[19:26] = bytes([21] * 7)  # 147 > 145
        self.assertIsNone(creation.parse_long_start(bytes(fat)))

    def test_created_rows_match_what_original_wrote(self):
        defaults = creation.load_defaults()
        rows = built_rows(defaults)
        want = FIXTURE["rows"]["renwu"][0]
        got = rows["renwu"][0]
        # 原版回读时会给 NULL 列写成空串之类，这里只比两边都有的、有实际值的列
        diff = {k: (got.get(k), v) for k, v in want.items() if k in got and got[k] is not None and got[k] != v and v not in ("NULL",)}
        self.assertEqual(diff, {})
        self.assertEqual((got["x"], got["y"], got["sex"], got["map"]), ("702", "386", "1", "3304"))
        self.assertEqual([(r["item_id"], r["shuliang"]) for r in rows["item"]],
                         [(r["item_id"], r["shuliang"]) for r in FIXTURE["rows"]["item"] if r["item_id"] != "0"])

    def test_sex_follows_head_image(self):
        defaults = creation.load_defaults()
        rows = creation.blank_rows(defaults, 1, creation.new_account_row(defaults, 1))
        creation.create_character_rows(defaults, rows, 1, "x")
        req = creation.parse_long_start(LONG_START)
        req.head = 5
        creation.apply_create(rows, req, [])
        self.assertEqual(rows["renwu"][0]["sex"], "2")

    def test_unknown_birth_map_keeps_default_position(self):
        defaults = creation.load_defaults()
        rows = creation.blank_rows(defaults, 1, creation.new_account_row(defaults, 1))
        creation.create_character_rows(defaults, rows, 1, "x")
        req = creation.parse_long_start(LONG_START)
        req.map = 5000
        creation.apply_create(rows, req, [])
        self.assertEqual((rows["renwu"][0]["x"], rows["renwu"][0]["y"]), ("0", "0"))

    @unittest.skipUnless(Path(DEFAULT_DATA_DIR).exists(), "原版服务端 data 目录不存在")
    def test_login_stream_for_new_character_is_byte_identical_to_original(self):
        defaults = creation.load_defaults()
        rows = built_rows(defaults)
        table = ItemTable.load(DEFAULT_DATA_DIR)
        template = Template.load(FIX / "char-8617293.json")
        got = build_login_stream(template, rows, table)
        want = [(f["opcode"], bytes.fromhex(f["payload"]), f["wide"]) for f in FIXTURE["frames"][1:]]
        self.assertEqual([(op, w) for op, _, w in got], [(op, w) for op, _, w in want])
        for i, ((op, g, _), (_, w, _)) in enumerate(zip(got, want)):
            skip = {0, 1, 2, 3} if i == 0 else {len(w) - 1} if op == 0x08 else set()
            bad = [k for k in range(len(w)) if g[k] != w[k] and k not in skip] if len(g) == len(w) else ["len"]
            self.assertEqual(bad, [], f"frame {i} opcode 0x{op:02x}")


class TestClient:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.rx = FrameReader("s2c", resync=True)
        self.frames, self.raw, self.eof, self.seq = [], b"", False, 0

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

    def send(self, op, payload, base):
        self.seq += 1
        from jyserver.codec import KEY_C2S_HANDSHAKE
        key = KEY_C2S_HANDSHAKE if self.seq == 1 else c2s_key(self.seq, base)
        self.writer.write(encode_c2s(op, payload, key=key, seq=self.seq, wide=False))


@unittest.skipUnless(Path(DEFAULT_DATA_DIR).exists(), "原版服务端 data 目录不存在")
class Flow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = CharacterStore()
        defaults = creation.load_defaults()
        for jyid in (JYID, JYID + 1):
            self.store.put(jyid, f"pw{jyid}", creation.blank_rows(defaults, jyid, creation.new_account_row(defaults, jyid)))
        self.gs = GameServer(self.store, ItemTable.load(DEFAULT_DATA_DIR), rng=random.Random(5), config_dir=None)
        self.server = await self.gs.serve("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        for c in self.clients:
            c.writer.close()
        self.server.close()
        await asyncio.wait_for(self.server.wait_closed(), timeout=5)
        self.store.close()

    async def connect(self, jyid, password):
        r, w = await asyncio.open_connection("127.0.0.1", self.port)
        c = TestClient(r, w)
        self.clients.append(c)
        c.send(0x01, struct.pack("<II", jyid, 0x0005FCF7) + password.encode(), 0x7D)
        await c.pump(0.3)
        return c

    async def test_whole_creation_flow(self):
        c = await self.connect(JYID, f"pw{JYID}")
        self.assertEqual(c.raw, bytes.fromhex("6bdbbe9e9e3d23") + c.raw[7:])  # 帧头（密钥 0x9f）
        self.assertEqual(len(c.raw), 33)  # 33 字节、没有尾部 00
        self.assertEqual(c.frames[0].payload, NEW_ACCOUNT_HANDSHAKE)
        base = derive_key(NEW_ACCOUNT_HANDSHAKE[1:5])
        self.assertEqual(base, 0x34)

        c.frames.clear()
        c.send(0x76, b"", base)
        await c.pump(0.3)
        roll = c.frames[0]
        self.assertEqual((roll.opcode, roll.key, sum(roll.payload[1:])), (0x5A, 0x34, 140))

        c.frames.clear()
        c.send(0x20, b"\x00" + NAME.encode(), base)
        await c.pump(0.3)
        self.assertEqual([(f.opcode, f.key, f.payload) for f in c.frames], [(0x25, 0x34, b"\x00")])

        c.frames.clear()
        c.send(0x19, LONG_START, base)
        await c.pump(0.5)
        self.assertEqual([f.opcode for f in c.frames], [0x1E, 0x44, 0x14, 0x14, 0x14, 0xBC, 0x32, 0x14, 0x14, 0x08, 0x02, 0x6D, 0x3D, 0x31, 0x2F, 0x32, 0x14, 0xA9])
        self.assertTrue(all(f.key == 0x34 for f in c.frames))
        saved = self.store.get(JYID)
        self.assertTrue(saved.has_character)
        self.assertEqual((saved.rows["renwu"][0]["map"], saved.rows["renwu"][0]["name"]), ("3304", NAME))

    async def test_taken_name_is_refused_then_free_name_works(self):
        a = await self.connect(JYID, f"pw{JYID}")
        a.send(0x20, b"\x00" + NAME.encode(), 0x34)
        await a.pump(0.3)
        await asyncio.sleep(2.6)
        b = await self.connect(JYID + 1, f"pw{JYID + 1}")
        b.frames.clear()
        b.send(0x20, b"\x00" + NAME.encode(), 0x34)
        await b.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in b.frames], [(0x25, b"\x01")])
        b.frames.clear()
        b.send(0x20, b"\x00" + b"another", 0x34)
        await b.pump(0.3)
        self.assertEqual([(f.opcode, f.payload) for f in b.frames], [(0x25, b"\x00")])

    async def test_overweight_attributes_are_silently_ignored(self):
        c = await self.connect(JYID, f"pw{JYID}")
        c.send(0x20, b"\x00" + NAME.encode(), 0x34)
        await c.pump(0.3)
        c.frames.clear()
        fat = bytearray(LONG_START)
        fat[19:26] = bytes([21] * 7)
        c.send(0x19, bytes(fat), 0x34)
        await c.pump(0.4)
        self.assertEqual(c.frames, [])
        self.assertFalse(c.eof)

    async def test_long_start_from_account_with_character_disconnects(self):
        c = await self.connect(JYID, f"pw{JYID}")
        c.send(0x20, b"\x00" + NAME.encode(), 0x34)
        await c.pump(0.2)
        c.send(0x19, LONG_START, 0x34)
        await c.pump(0.4)
        c.writer.close()
        await asyncio.sleep(2.6)
        d = await self.connect(JYID, f"pw{JYID}")  # 现在已有角色 → 普通握手 B
        self.assertEqual(len(d.raw), 35)
        d.send(0x19, LONG_START, 0x7D)
        await d.pump(0.4)
        self.assertTrue(d.eof)


if __name__ == "__main__":
    unittest.main()
