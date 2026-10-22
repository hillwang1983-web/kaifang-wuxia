"""codec 单元测试。

向量来源已逐条标明。其中「文档样本」取自 新网金/99-历史/协议抓包-初步分析.md，
「往返」只验证编解码自洽，不能证明与原客户端兼容。
"""

import struct
import unittest

from jyserver.codec import (
    KEY_C2S_HANDSHAKE,
    KEY_DEFAULT,
    KEY_S2C_HANDSHAKE,
    FrameError,
    FrameReader,
    decode_stream,
    derive_key,
    encode_c2s,
    encode_s2c,
    join_frames,
    peek_header,
    xor_bytes,
)

# 文档样本：真实客户端的登录握手首包（C2S，20 字节），测试账号 12345 / 角色 jyid 12345。
C2S_HANDSHAKE = bytes.fromhex("f6 11 01 6a da 8f 9f a7 ae 9e 9e 69 62 9b 9e af ac ad aa ab")


class DeriveKey(unittest.TestCase):
    # 常数项 145 由两组真实流量校准（握手种子、换密钥种子）；前三个是同一公式的算例
    def test_real_traffic(self):
        self.assertEqual(derive_key(bytes.fromhex("a2bc2837")), 0x7D)
        self.assertEqual(derive_key(bytes.fromhex("0eaea531")), 0x0E)

    def test_documented_examples(self):
        self.assertEqual(derive_key(bytes([1, 2, 3, 4])), 0xBA)
        self.assertEqual(derive_key(bytes.fromhex("deadbeef")), 0xCB)
        self.assertEqual(derive_key(bytes(4)), 0x91)

    def test_range_and_args(self):
        for seed in (b"\xff\xff\xff\xff", b"\x00\x00\x00\x01", b"\x10\x20\x30\x40"):
            self.assertTrue(0 <= derive_key(seed) < 217)
        with self.assertRaises(ValueError):
            derive_key(b"\x00\x00\x00")


class C2SHandshake(unittest.TestCase):
    def test_document_sample(self):
        frames, rest, skipped = decode_stream(C2S_HANDSHAKE, "c2s")
        self.assertEqual((rest, skipped), (b"", 0))
        self.assertEqual(len(frames), 1)
        f = frames[0]
        self.assertEqual(f.key, KEY_C2S_HANDSHAKE)  # p[3]^0xF4 == p[4]^0x44 == 0x9E
        self.assertFalse(f.wide)
        self.assertEqual(f.seq, 1)
        self.assertEqual(f.opcode, 0x01)
        self.assertEqual(f.total_length, 17)  # 文档：「1101」= 长度 17 + opcode 1
        self.assertEqual(len(f.payload), 13)
        self.assertEqual(f.payload[:4], (12345).to_bytes(4, "little"))  # jyid
        self.assertEqual(f.payload[8:], b"12345")  # 账号名 ASCII
        self.assertEqual(f.raw, C2S_HANDSHAKE)

    def test_reencode_matches_sample(self):
        f = decode_stream(C2S_HANDSHAKE, "c2s")[0][0]
        again = encode_c2s(f.opcode, f.payload, key=f.key, seq=f.seq)
        self.assertEqual(again, C2S_HANDSHAKE)


class S2CSamples(unittest.TestCase):
    def test_set_position_document_sample(self):
        # 文档：收到 0c 00 08 88 13 94 25 86 09 02（魔数之后的明文），
        # 解出 地图5000 X=9620 Y=2438，与 renwu 表 jyid=12345 一致。
        payload = bytes.fromhex("88 13 94 25 86 09 02")
        wire = encode_s2c(0x08, payload, key=KEY_DEFAULT, wide=True)
        self.assertEqual(wire[:2], bytes([0xF5 ^ KEY_DEFAULT, 0xB3 ^ KEY_DEFAULT]))
        self.assertEqual(xor_bytes(wire, KEY_DEFAULT)[2:], bytes.fromhex("0c000888139425860902"))
        frames, rest, skipped = decode_stream(wire, "s2c")
        f = frames[0]
        self.assertTrue(f.wide)
        self.assertEqual(f.opcode, 0x08)
        map_id, x, y = struct.unpack_from("<HHH", f.payload)
        self.assertEqual((map_id, x, y), (5000, 9620, 2438))
        self.assertEqual((rest, skipped), (b"", 0))

    def test_handshake_response_header_inference(self):
        # 文档：S2C 首包以 6b db bd 9e 9e 3d 23 b7 … 开头，共 35 字节。
        # 以 0x9F 为密钥时前两字节恰为魔数 F4 44（6b^9f=f4, db^9f=44），
        # 长度字节 bd^9f=0x22=34，与「尾部多 1 字节 00」吻合。属于推断，待真实首包验证。
        prefix = bytes.fromhex("6bdbbd9e9e3d23b7")
        self.assertEqual(peek_header(prefix), (KEY_S2C_HANDSHAKE, False, 34))

    def test_move_broadcast_roundtrip(self):
        payload = struct.pack("<IHHHH", 12345, 312, 408, 429, 377)
        wire = encode_s2c(0x06, payload, wide=False)
        f = decode_stream(wire, "s2c")[0][0]
        self.assertEqual((f.opcode, f.wide, f.key), (0x06, False, KEY_DEFAULT))
        self.assertEqual(struct.unpack("<IHHHH", f.payload), (12345, 312, 408, 429, 377))


class Framing(unittest.TestCase):
    def _sample_stream(self):
        return [
            encode_s2c(0x08, bytes.fromhex("88139425860902"), wide=True),
            encode_s2c(0x06, struct.pack("<IHHHH", 12345, 1, 2, 3, 4), wide=False),
            encode_s2c(0x14, b"\x01" + "公告".encode("big5"), key=0x0E, wide=False),
            encode_s2c(0x7B, b"\x2f" + (2020).to_bytes(4, "little"), key=0x9F),
        ]

    def test_concatenated_frames(self):
        frames, rest, skipped = decode_stream(join_frames(self._sample_stream()), "s2c")
        self.assertEqual([f.opcode for f in frames], [0x08, 0x06, 0x14, 0x7B])
        self.assertEqual([f.key for f in frames], [0x7D, 0x7D, 0x0E, 0x9F])
        self.assertEqual((rest, skipped), (b"", 0))

    def test_any_split_point_gives_same_frames(self):
        data = join_frames(self._sample_stream())
        expected = [(f.opcode, f.payload, f.key) for f in decode_stream(data, "s2c")[0]]
        for cut in range(len(data) + 1):
            r = FrameReader("s2c")
            got = r.feed(data[:cut]) + r.feed(data[cut:])
            self.assertEqual([(f.opcode, f.payload, f.key) for f in got], expected, cut)
            self.assertEqual(r.pending, b"")

    def test_c2s_concatenated_and_split(self):
        frames_in = [
            encode_c2s(0x06, struct.pack("<HHHH", 1, 2, 3, 4) + b"\x00\x00\x8a", key=0x7D, seq=n)
            for n in range(1, 6)
        ]
        data = join_frames(frames_in)
        got, rest, _ = decode_stream(data, "c2s")
        self.assertEqual([f.seq for f in got], [1, 2, 3, 4, 5])
        self.assertEqual(rest, b"")
        for cut in range(len(data) + 1):
            r = FrameReader("c2s")
            self.assertEqual(len(r.feed(data[:cut]) + r.feed(data[cut:])), 5)

    def test_long_frame_for_big_payload(self):
        big = bytes(range(256)) * 3
        wire = encode_s2c(0x1E, big)  # 自动选长帧
        f = decode_stream(wire, "s2c")[0][0]
        self.assertTrue(f.wide)
        self.assertEqual(f.payload, big)

    def test_short_frame_limit(self):
        encode_s2c(0x01, bytes(251), wide=False)  # 总长 255，刚好
        with self.assertRaises(FrameError):
            encode_s2c(0x01, bytes(252), wide=False)

    def test_bad_magic_raises_and_resync_skips(self):
        good = encode_s2c(0x08, bytes.fromhex("88139425860902"), wide=True)
        junk = b"\x00"  # 例如握手包后面多出的 1 字节 00
        with self.assertRaises(FrameError):
            FrameReader("s2c").feed(junk + good)
        frames, rest, skipped = decode_stream(junk + good, "s2c", resync=True)
        self.assertEqual(len(frames), 1)
        self.assertEqual(skipped, 1)
        self.assertEqual(rest, b"")

    def test_c2s_requires_prefix(self):
        with self.assertRaises(FrameError):
            decode_stream(encode_s2c(0x01, b"abc"), "c2s")

    def test_rejects_bad_direction(self):
        with self.assertRaises(ValueError):
            FrameReader("both")


if __name__ == "__main__":
    unittest.main()
