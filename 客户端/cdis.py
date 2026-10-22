#!/usr/bin/env python3
"""用 capstone 反汇编 loginp.exe（比 x86mini.py 准，能认全部 x86 指令）。
    python cdis.py 0x6b0a83 0x6b0c31            # 线性反汇编一段
    python cdis.py 0x6b0a83 0x6b0c31 --refs     # 给 call 目标和字符串常量加注释
Delphi 的长字符串常量（前面 8 字节是引用计数 + 长度）会被认出来并按 Big5 显示。"""
import os
import struct
import sys

import capstone

EXE = os.environ.get("JY_LOGINP", r"C:\游戏\网金最原始文件\网金最原始文件\客户端\maina\loginp.exe")
_d = open(EXE, "rb").read()
_pe = struct.unpack_from("<I", _d, 0x3C)[0]
_n = struct.unpack_from("<H", _d, _pe + 6)[0]
_opt = struct.unpack_from("<H", _d, _pe + 20)[0]
BASE = struct.unpack_from("<I", _d, _pe + 24 + 28)[0]
_secs = []
for _i in range(_n):
    _o = _pe + 24 + _opt + 40 * _i
    _vs, _va, _rs, _rp = struct.unpack_from("<IIII", _d, _o + 8)
    _secs.append((BASE + _va, max(_vs, _rs), _rp))


def fo(a):
    for v, sz, rp in _secs:
        if v <= a < v + sz:
            return rp + a - v


def rd(a, n):
    f = fo(a)
    return _d[f:f + n] if f is not None else b""


def lstr(a):
    h = rd(a - 4, 4)
    if len(h) != 4:
        return None
    ln = struct.unpack("<I", h)[0]
    if not 1 <= ln <= 200:
        return None
    s = rd(a, ln)
    if len(s) != ln or rd(a + ln, 1) != b"\x00":
        return None
    try:
        t = s.decode("big5")
    except UnicodeDecodeError:
        return None
    return t if all(ord(c) >= 32 for c in t) else None


def dis(lo, hi, refs=False):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = False
    out = []
    for ins in md.disasm(rd(lo, hi - lo), lo):
        note = ""
        if refs:
            for tok in ins.op_str.replace("[", " ").replace("]", " ").replace(",", " ").split():
                if tok.startswith("0x"):
                    try:
                        v = int(tok, 16)
                    except ValueError:
                        continue
                    if BASE <= v < 0xB00000:
                        s = lstr(v)
                        if s:
                            note = "  ; \"%s\"" % s[:40]
        out.append("%x  %-6s %s%s" % (ins.address, ins.mnemonic, ins.op_str, note))
    return out


if __name__ == "__main__":
    lo, hi = int(sys.argv[1], 0), int(sys.argv[2], 0)
    print("\n".join(dis(lo, hi, "--refs" in sys.argv)))

