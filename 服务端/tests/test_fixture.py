"""用原版服务端的真实回包做夹具测试。

夹具 data/fixtures/login-8617293.json 由 tools/sim_client.py 录制：向本机原版服务端发
C2S 01（登录）和 C2S 19（启动登录），服务端回的全部 S2C 帧（含线路原始字节）。
"""

import json
import struct
import unittest
from pathlib import Path

from jyserver.codec import FrameReader, c2s_key, encode_c2s, encode_s2c

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "login-8617293.json"


class RealServerFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.frames = cls.data["frames"]

    def test_every_frame_decodes_and_reencodes_byte_for_byte(self):
        self.assertGreaterEqual(len(self.frames), 15)
        for i, f in enumerate(self.frames):
            wire = bytes.fromhex(f["wire"])
            got = FrameReader("s2c").feed(wire)
            self.assertEqual(len(got), 1, f"frame {i}")
            g = got[0]
            self.assertEqual((g.opcode, g.key, g.wide, g.total_length), (f["opcode"], f["key"], f["wide"], f["length"]), f"frame {i}")
            self.assertEqual(g.payload.hex(), f["payload"], f"frame {i}")
            again = encode_s2c(f["opcode"], bytes.fromhex(f["payload"]), key=f["key"], wide=f["wide"])
            self.assertEqual(again, wire, f"frame {i} (op 0x{f['opcode']:02x}) re-encode differs")

    def test_whole_session_as_one_stream(self):
        stream = b"".join(bytes.fromhex(f["wire"]) for f in self.frames)
        reader = FrameReader("s2c")
        got = reader.feed(stream)
        self.assertEqual([g.opcode for g in got], [f["opcode"] for f in self.frames])
        self.assertEqual(reader.pending, b"")

    def test_handshake_reply(self):
        f = self.frames[0]
        self.assertEqual((f["opcode"], f["key"], f["wide"], f["length"]), (0x01, 0x9F, False, 34))

    def test_set_position_matches_database(self):
        # renwu.jyid=8617293 的 map/x/y 是 2200/510/410（见 backups/ 里的备份）
        pos = next(f for f in self.frames if f["opcode"] == 0x08)
        map_id, x, y = struct.unpack_from("<HHH", bytes.fromhex(pos["payload"]))
        self.assertEqual((map_id, x, y), (2200, 510, 410))

    def test_full_state_packet_is_the_big_one(self):
        st = next(f for f in self.frames if f["opcode"] == 0x1E)
        self.assertTrue(st["wide"])
        self.assertEqual(st["length"], 1393)
        self.assertEqual(st["key"], 0x7D)

    def test_after_handshake_server_uses_key_7d(self):
        for f in self.frames[1:]:
            self.assertEqual(f["key"], 0x7D, f"op 0x{f['opcode']:02x}")


class C2SKeyRule(unittest.TestCase):
    def test_rule_matches_live_probe(self):
        # 实测：序号 2/3/4/5 分别只有 0x7F/0x7E/0x79/0x78 能让服务端处理该帧
        self.assertEqual([c2s_key(s) for s in (2, 3, 4, 5)], [0x7F, 0x7E, 0x79, 0x78])
        self.assertEqual(c2s_key(1), 0x9E)

    def test_encoded_probe_frame(self):
        wire = encode_c2s(0x76, b"", key=c2s_key(2), seq=2)
        # F6 11 | seq | (F4^7F) (44^7F) | 04^7F | 76^7F
        self.assertEqual(wire.hex(" "), "f6 11 02 8b 3b 7b 09")


if __name__ == "__main__":
    unittest.main()
