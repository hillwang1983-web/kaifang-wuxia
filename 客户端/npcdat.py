#!/usr/bin/env python3
"""share\\dat\\Npc*.Dat 解码（loginp.exe 0x51b5bc）：每条记录 237 字节，文件第 0 条是占位；
读入后对每条记录做：字节 3..0x16 反转；再对一批字段异或常量（下面 XORS）。
解码后记录首 u16 = 型号（NPC 型号 / MOB id，如 10001、38166）。字段含义见 parse()。
"""
import os
import struct

R = 237
_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包后在 <目录>\share\dat，开发机上在 ..\share\dat
DAT_DIR = os.environ.get("JY_DAT") or (os.path.join(_HERE, "share", "dat") if os.path.isdir(os.path.join(_HERE, "share", "dat")) else os.path.normpath(os.path.join(_HERE, "..", "share", "dat")))
# (偏移, 宽度, 常量)；宽度 1/2/4 字节小端
XORS = [(0x00, 2, 0xA7B), (0x19, 2, 0xD8), (0x1B, 2, 0x511), (0x1D, 4, 0x25FC), (0x21, 2, 0xAA9), (0x23, 2, 0x723), (0x25, 4, 0x1240),
        (0x29, 2, 0x944), (0x2B, 4, 0x7443A), (0x2F, 1, 0x89), (0x30, 1, 0x98), (0x31, 1, 0xAD), (0x32, 1, 0x79), (0x33, 1, 0xD5),
        (0x34, 1, 0xD3), (0x35, 1, 0xD4), (0x41, 4, 0x7F21), (0x45, 4, 0x4044), (0x49, 4, 0x5098D), (0x52, 1, 0x4E)]
XORS += [(0x5D + 2 * k, 2, 0x278) for k in range(15)]
XORS += [(0x7B + 4 * k, 2, 0xA48) for k in range(15)] + [(0x7D + 4 * k, 2, 0x7D) for k in range(15)]
XORS += [(0xBB + 5 * k, 2, 0x173) for k in range(10)]
FMT = {1: "<B", 2: "<H", 4: "<I"}


def decode_record(rec: bytes) -> bytes:
    r = bytearray(rec)
    r[3:0x17] = r[3:0x17][::-1]
    for o, w, c in XORS:
        v = struct.unpack_from(FMT[w], r, o)[0] ^ c
        struct.pack_into(FMT[w], r, o, v & ((1 << (8 * w)) - 1))
    return bytes(r)


def load(path):
    """-> {型号: 解码后的 237 字节记录}（同一文件里重复的型号取后出现的）"""
    b = open(path, "rb").read()
    out = {}
    for k in range(1, len(b) // R):
        r = decode_record(b[k * R:(k + 1) * R])
        i = struct.unpack_from("<H", r, 0)[0]
        if i:
            out[i] = r
    return out


if __name__ == "__main__":
    import sys
    t = load(os.path.join(DAT_DIR, sys.argv[1]))
    print(len(t), "records")
    for i in map(int, sys.argv[2:]):
        r = t.get(i)
        print(i, r.hex(" ") if r else None)
