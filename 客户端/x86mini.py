#!/usr/bin/env python3
"""极简 x86-32 线性反汇编（只覆盖 Delphi 编译器常见指令），用于 Ghidra 没反汇编的区域。
python x86mini.py <exe> <起始VA> <结束VA>
"""
import struct
import sys

R32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"]
R16 = ["ax", "cx", "dx", "bx", "sp", "bp", "si", "di"]
R8 = ["al", "cl", "dl", "bl", "ah", "ch", "dh", "bh"]
CC = ["o", "no", "b", "ae", "e", "ne", "be", "a", "s", "ns", "p", "np", "l", "ge", "le", "g"]
ALU = ["add", "or", "adc", "sbb", "and", "sub", "xor", "cmp"]
SH = ["rol", "ror", "rcl", "rcr", "shl", "shr", "sal", "sar"]


class D:
    def __init__(self, data, base):
        self.d, self.base = data, base

    def disasm(self, va):
        d, base = self.d, self.base
        o = va - base
        start = o
        opsz = 4
        seg = ""
        pre = ""
        while d[o] in (0x66, 0x64, 0x65, 0xF2, 0xF3, 0x2E, 0x3E):
            if d[o] == 0x66:
                opsz = 2
            elif d[o] == 0x64:
                seg = "fs:"
            elif d[o] in (0xF2, 0xF3):
                pre = {0xF2: "repne ", 0xF3: "rep "}[d[o]]
            o += 1
        op = d[o]
        o += 1

        def reg(n, sz):
            return (R8 if sz == 1 else R16 if sz == 2 else R32)[n]

        def modrm(sz):
            nonlocal o
            m = d[o]
            o += 1
            mod, r, rm = m >> 6, (m >> 3) & 7, m & 7
            if mod == 3:
                return r, reg(rm, sz)
            base_s = idx = ""
            scale = 1
            if rm == 4:
                sib = d[o]
                o += 1
                sc, ix, bs = sib >> 6, (sib >> 3) & 7, sib & 7
                if ix != 4:
                    idx = R32[ix]
                    scale = 1 << sc
                if bs == 5 and mod == 0:
                    disp = struct.unpack_from("<i", d, o)[0]
                    o += 4
                    s = "%s[%s%s0x%x]" % (seg, (idx + "*%d+" % scale) if idx else "", "-" if disp < 0 else "", abs(disp))
                    return r, s
                base_s = R32[bs]
            elif rm == 5 and mod == 0:
                disp = struct.unpack_from("<I", d, o)[0]
                o += 4
                return r, "%s[0x%x]" % (seg, disp)
            else:
                base_s = R32[rm]
            disp = 0
            if mod == 1:
                disp = struct.unpack_from("<b", d, o)[0]
                o += 1
            elif mod == 2:
                disp = struct.unpack_from("<i", d, o)[0]
                o += 4
            parts = base_s
            if idx:
                parts += "+%s*%d" % (idx, scale) if base_s else "%s*%d" % (idx, scale)
            if disp:
                parts += ("-0x%x" % -disp) if disp < 0 else "+0x%x" % disp
            return r, "%s[%s]" % (seg, parts)

        def imm(sz):
            nonlocal o
            if sz == 1:
                v = d[o]
                o += 1
            elif sz == 2:
                v = struct.unpack_from("<H", d, o)[0]
                o += 2
            else:
                v = struct.unpack_from("<I", d, o)[0]
                o += 4
            return "0x%x" % v

        def simm8():
            nonlocal o
            v = struct.unpack_from("<b", d, o)[0]
            o += 1
            return ("-0x%x" % -v) if v < 0 else "0x%x" % v

        t = None
        if op < 0x40 and (op & 7) < 6:
            name = ALU[op >> 3]
            k = op & 7
            if k < 4:
                sz = 1 if k % 2 == 0 else opsz
                r, rmv = modrm(sz)
                t = "%s %s, %s" % (name, rmv, reg(r, sz)) if k < 2 else "%s %s, %s" % (name, reg(r, sz), rmv)
            elif k == 4:
                t = "%s al, %s" % (name, imm(1))
            else:
                t = "%s eax, %s" % (name, imm(opsz))
        elif 0x40 <= op < 0x48:
            t = "inc " + R32[op - 0x40]
        elif 0x48 <= op < 0x50:
            t = "dec " + R32[op - 0x48]
        elif 0x50 <= op < 0x58:
            t = "push " + R32[op - 0x50]
        elif 0x58 <= op < 0x60:
            t = "pop " + R32[op - 0x58]
        elif op == 0x68:
            t = "push " + imm(4)
        elif op == 0x6A:
            t = "push " + simm8()
        elif op in (0x69, 0x6B):
            r, rmv = modrm(opsz)
            t = "imul %s, %s, %s" % (reg(r, opsz), rmv, imm(4) if op == 0x69 else simm8())
        elif 0x70 <= op < 0x80:
            rel = struct.unpack_from("<b", d, o)[0]
            o += 1
            t = "j%s 0x%x" % (CC[op - 0x70], va + (o - start) + rel)
        elif op in (0x80, 0x81, 0x83):
            sz = 1 if op == 0x80 else opsz
            r, rmv = modrm(sz)
            v = imm(1) if op == 0x80 else imm(sz) if op == 0x81 else simm8()
            t = "%s %s, %s" % (ALU[r], rmv, v)
        elif op in (0x84, 0x85):
            sz = 1 if op == 0x84 else opsz
            r, rmv = modrm(sz)
            t = "test %s, %s" % (rmv, reg(r, sz))
        elif op in (0x86, 0x87):
            sz = 1 if op == 0x86 else opsz
            r, rmv = modrm(sz)
            t = "xchg %s, %s" % (rmv, reg(r, sz))
        elif op in (0x88, 0x89, 0x8A, 0x8B):
            sz = 1 if op % 2 == 0 else opsz
            r, rmv = modrm(sz)
            t = "mov %s, %s" % (rmv, reg(r, sz)) if op < 0x8A else "mov %s, %s" % (reg(r, sz), rmv)
        elif op == 0x8D:
            r, rmv = modrm(4)
            t = "lea %s, %s" % (reg(r, 4), rmv)
        elif op == 0x90:
            t = "nop"
        elif op == 0x99:
            t = "cdq"
        elif op == 0x98:
            t = "cwde"
        elif op in (0xA8, 0xA9):
            t = "test %s, %s" % ("al" if op == 0xA8 else "eax", imm(1 if op == 0xA8 else opsz))
        elif 0xA4 <= op <= 0xA7 or 0xAA <= op <= 0xAF:
            t = pre + {0xA4: "movsb", 0xA5: "movsd", 0xA6: "cmpsb", 0xA7: "cmpsd", 0xAA: "stosb", 0xAB: "stosd", 0xAC: "lodsb", 0xAD: "lodsd", 0xAE: "scasb", 0xAF: "scasd"}[op]
            pre = ""
        elif 0xB0 <= op < 0xB8:
            t = "mov %s, %s" % (R8[op - 0xB0], imm(1))
        elif 0xB8 <= op < 0xC0:
            t = "mov %s, %s" % (reg(op - 0xB8, opsz), imm(opsz))
        elif op in (0xC0, 0xC1, 0xD0, 0xD1, 0xD2, 0xD3):
            sz = 1 if op in (0xC0, 0xD0, 0xD2) else opsz
            r, rmv = modrm(sz)
            cnt = imm(1) if op in (0xC0, 0xC1) else "1" if op in (0xD0, 0xD1) else "cl"
            t = "%s %s, %s" % (SH[r], rmv, cnt)
        elif op == 0xC3:
            t = "ret"
        elif op == 0xC2:
            t = "ret " + imm(2)
        elif op in (0xC6, 0xC7):
            sz = 1 if op == 0xC6 else opsz
            r, rmv = modrm(sz)
            t = "mov %s, %s" % (rmv, imm(sz))
        elif op == 0xE8:
            rel = struct.unpack_from("<i", d, o)[0]
            o += 4
            t = "call 0x%x" % (va + (o - start) + rel)
        elif op == 0xE9:
            rel = struct.unpack_from("<i", d, o)[0]
            o += 4
            t = "jmp 0x%x" % (va + (o - start) + rel)
        elif op == 0xEB:
            rel = struct.unpack_from("<b", d, o)[0]
            o += 1
            t = "jmp 0x%x" % (va + (o - start) + rel)
        elif op in (0xF6, 0xF7):
            sz = 1 if op == 0xF6 else opsz
            r, rmv = modrm(sz)
            if r in (0, 1):
                t = "test %s, %s" % (rmv, imm(sz))
            else:
                t = "%s %s" % (["", "", "not", "neg", "mul", "imul", "div", "idiv"][r], rmv)
        elif op in (0xFE, 0xFF):
            sz = 1 if op == 0xFE else opsz
            r, rmv = modrm(sz)
            t = {0: "inc", 1: "dec", 2: "call", 4: "jmp", 6: "push"}.get(r, "grp5/%d" % r) + " " + rmv
        elif op == 0x0F:
            op2 = d[o]
            o += 1
            if 0x80 <= op2 < 0x90:
                rel = struct.unpack_from("<i", d, o)[0]
                o += 4
                t = "j%s 0x%x" % (CC[op2 - 0x80], va + (o - start) + rel)
            elif 0x90 <= op2 < 0xA0:
                r, rmv = modrm(1)
                t = "set%s %s" % (CC[op2 - 0x90], rmv)
            elif op2 in (0xB6, 0xB7, 0xBE, 0xBF):
                sz = 1 if op2 in (0xB6, 0xBE) else 2
                r, rmv = modrm(sz)
                t = "%s %s, %s" % ("movzx" if op2 < 0xB8 else "movsx", reg(r, opsz), rmv)
            elif op2 == 0xAF:
                r, rmv = modrm(opsz)
                t = "imul %s, %s" % (reg(r, opsz), rmv)
            else:
                t = "?0f%02x" % op2
        else:
            t = "?%02x" % op
        return pre + t, o - start


def main():
    exe, a, b = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
    data = open(exe, "rb").read()
    # PE 节映射：这个程序 VA - 0x400000 == 文件偏移 对 CODE 段成立（已用 search_bytes 的 file_offset 核对）
    dd = D(data, 0x400000)
    va = a
    while va < b:
        try:
            s, n = dd.disasm(va)
        except Exception as e:
            s, n = "!!%r" % e, 1
        raw = data[va - 0x400000:va - 0x400000 + n].hex()
        print("%x  %-24s %s" % (va, raw, s))
        va += n


if __name__ == "__main__":
    main()
