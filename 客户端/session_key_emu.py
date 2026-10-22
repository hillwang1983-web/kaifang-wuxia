#!/usr/bin/env python3
"""原版客户端"会话密钥调度"的模拟器：用 Unicorn 在内存里直接跑 loginp.exe 的 FUN_009db97c，由服务端下发的 4 字节种子
算出一组会话状态，再调 FUN_009b6798(k) 取出 C2S 校验字节（E3 / DE / D7 尾部那一个字节）。

为什么不手工移植：调度函数有 80 KB 机器码（0x9db97c…0x9efd45，全是定点 / 浮点加减的展开），手抄容易错；模拟器跑的就是原件。

依赖：`pip install unicorn`，以及原版客户端 `maina\\loginp.exe`（路径用环境变量 JY_LOGINP 指定，缺省取本仓库旁边的 ..\\maina\\loginp.exe）。
Mac 部署包里没有 loginp.exe，所以这个模块只在 Windows 开发机上用来对照 / 研究，网关运行时不依赖它。

用法
    from session_key_emu import SessionKey
    sk = SessionKey(bytes.fromhex("a2bc2837"))        # 种子 = 握手 / 换密钥帧载荷[1:5]（jyclient.rekeys[-1][1]）
    sk.modulus                                         # M = (4 个字节之和) % 5 + 8（8..12）
    sk.k_for_e3(jyid, col, row, direction)             # 校验字节在 12 个"提供者"里选哪一个
    sk.provider(2)                                     # 不依赖玩家数据的提供者：k = 2、6
    sk.e3_tail(jyid, col, row, direction)              # 完整的 E3 尾字节（k 落在 2 / 6 之外时需要 g2 参数，见下）

【没解完的】k = 1、3、4、5（以及用到它们的 7–12）还要玩家对象 G2+0x210 那个 64 位数的十进制第 5–8 位（来源没找到）；
SessionKey(seed, g2=<int>) 可以手工给定一个值做对照。
逆向细节见 ..\\逆向笔记_loginp.md「C2S 校验字节」。
"""
import os
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UcError
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP,
                               UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_FS, UC_X86_REG_GDTR, UC_X86_REG_SS)

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = os.environ.get("JY_LOGINP") or os.path.normpath(os.path.join(HERE, "..", "maina", "loginp.exe"))
PAGE = 0x1000

SCHEDULE = 0x9db97c           # FUN_009db97c(eax = 种子的 Delphi 字符串)
PROVIDER_SWITCH = 0x9b6798    # FUN_009b6798(eax = k) -> al
ADDR_M = 0x2052520            # [0xa26304] 指向这里：M
ADDR_X = 0x2052524            # 第二个参数 (种子字节和) % 54 + 1
G2_PTR = 0xa27248             # 玩家数据对象的全局指针（对象里 +0x210 是那个 64 位数）
NEEDS_G2 = {1, 3, 4, 5, 7, 8, 9, 10, 11, 12}

# 导入函数的参数个数（stdcall）；调度函数只会碰到分配 / 临界区 / 线程号这几个
ARGC = {"InitializeCriticalSection": 1, "EnterCriticalSection": 1, "LeaveCriticalSection": 1, "DeleteCriticalSection": 1,
        "LocalAlloc": 2, "LocalFree": 1, "LocalReAlloc": 3, "GlobalAlloc": 2, "GlobalFree": 1, "GlobalReAlloc": 3,
        "VirtualAlloc": 4, "VirtualFree": 3, "VirtualProtect": 4, "HeapAlloc": 3, "HeapFree": 3, "HeapReAlloc": 4,
        "GetProcessHeap": 0, "GetLastError": 0, "SetLastError": 1, "GetCurrentThreadId": 0, "GetTickCount": 0,
        "TlsGetValue": 1, "TlsSetValue": 2, "TlsAlloc": 0, "GetModuleHandleA": 1, "GetVersion": 0, "FlushInstructionCache": 3,
        "InterlockedIncrement": 1, "InterlockedDecrement": 1, "GetACP": 0}


class Emu:
    def __init__(self, exe=EXE):
        d = open(exe, "rb").read()
        pe = struct.unpack_from("<I", d, 0x3c)[0]
        n = struct.unpack_from("<H", d, pe + 6)[0]
        opt = struct.unpack_from("<H", d, pe + 20)[0]
        self.base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        size_of_image = struct.unpack_from("<I", d, pe + 24 + 56)[0]
        uc = self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        top = (self.base + size_of_image + PAGE - 1) & ~(PAGE - 1)
        uc.mem_map(self.base, top - self.base)
        uc.mem_write(self.base, d[:struct.unpack_from("<I", d, pe + 24 + 60)[0]])
        o = pe + 24 + opt
        for _ in range(n):
            vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
            uc.mem_write(self.base + va, d[rp:rp + min(rs, vs)])
            o += 40
        self.STACK = 0x7F000000
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        self.HEAP = 0x60000000
        uc.mem_map(self.HEAP, 0x4000000)
        self.heap_ptr = self.HEAP + 0x1000
        # FS（SEH 链）用一个以 TIB 为基址的段；SS/DS/ES/CS 用平坦 32 位段
        self.TIB, self.GDT = 0x7E000000, 0x7D000000
        uc.mem_map(self.TIB, 0x10000)
        uc.mem_write(self.TIB, struct.pack("<I", 0xFFFFFFFF))
        uc.mem_write(self.TIB + 0x18, struct.pack("<I", self.TIB))
        uc.mem_map(self.GDT, 0x1000)

        def desc(base, limit, access, flags):
            return struct.pack("<HHBBBB", limit & 0xFFFF, base & 0xFFFF, (base >> 16) & 0xFF, access, ((flags & 0xF) << 4) | ((limit >> 16) & 0xF), (base >> 24) & 0xFF)
        gdt = desc(0, 0, 0, 0) + desc(0, 0xFFFFF, 0x93, 0xC) + desc(self.TIB, 0xFFF, 0x93, 0x4) + desc(0, 0xFFFFF, 0x9B, 0xC)
        uc.mem_write(self.GDT, gdt)
        uc.reg_write(UC_X86_REG_GDTR, (0, self.GDT, len(gdt) - 1, 0))
        for reg, sel in ((UC_X86_REG_SS, 1), (UC_X86_REG_DS, 1), (UC_X86_REG_ES, 1), (UC_X86_REG_CS, 3), (UC_X86_REG_FS, 2)):
            uc.reg_write(reg, sel << 3)
        self._install_imports(d, pe)
        self.state = {"lasterr": 0, "tls": {}}

    # ---- 内存 / 调用
    def alloc(self, n):
        n = (n + 15) & ~15
        p = self.heap_ptr
        self.heap_ptr += n + 16
        return p

    def delphi_string(self, b):
        p = self.alloc(len(b) + 12)
        self.uc.mem_write(p, struct.pack("<ii", 1, len(b)) + b + b"\0")
        return p + 8

    def rd(self, a, n=4):
        return bytes(self.uc.mem_read(a, n))

    def u32(self, a):
        return struct.unpack("<I", self.rd(a))[0]

    def call(self, addr, eax=0, edx=0, ecx=0, max_insn=50_000_000):
        uc = self.uc
        ret = 0x7C000000
        try:
            uc.mem_map(ret, PAGE)
        except UcError:
            pass
        uc.mem_write(ret, b"\xf4")
        sp = self.STACK - 4
        uc.mem_write(sp, struct.pack("<I", ret))
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.reg_write(UC_X86_REG_EBP, 0)
        uc.reg_write(UC_X86_REG_EAX, eax)
        uc.reg_write(UC_X86_REG_EDX, edx)
        uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.emu_start(addr, ret, count=max_insn)
        return uc.reg_read(UC_X86_REG_EAX)

    # ---- Windows 导入：每个导入槽改成一个陷阱地址，命中时用 Python 实现
    def _install_imports(self, d, pe):
        uc = self.uc
        imp_rva = struct.unpack_from("<I", d, pe + 24 + 96 + 8)[0]
        slots = {}
        p = self.base + imp_rva
        while True:
            ilt, _, _, name_rva, iat = struct.unpack("<IIIII", self.rd(p, 20))
            if name_rva == 0 and iat == 0:
                break
            t, i = ilt or iat, 0
            while True:
                v = struct.unpack("<I", self.rd(self.base + t + 4 * i))[0]
                if v == 0:
                    break
                nm = ("#%d" % (v & 0xFFFF)) if v & 0x80000000 else self.rd(self.base + v + 2, 80).split(b"\0")[0].decode("latin1")
                slots[self.base + iat + 4 * i] = nm
                i += 1
            p += 20
        TRAP = 0x7B000000
        uc.mem_map(TRAP, 0x10000)
        self.traps = {}
        for i, (slot, nm) in enumerate(sorted(slots.items())):
            t = TRAP + 4 * i
            uc.mem_write(t, b"\xf4")
            uc.mem_write(slot, struct.pack("<I", t))
            self.traps[t] = nm
        uc.hook_add(UC_HOOK_CODE, self._on_trap, begin=TRAP, end=TRAP + 0x10000)

    def _on_trap(self, uc, address, size, ud):
        nm = self.traps.get(address)
        if nm is None:
            return
        argc = ARGC.get(nm)
        if argc is None:
            raise RuntimeError("模拟器遇到未实现的导入函数 %s" % nm)
        sp = uc.reg_read(UC_X86_REG_ESP)
        a = [struct.unpack("<I", bytes(uc.mem_read(sp + 4 + 4 * k, 4)))[0] for k in range(max(argc, 1))]
        val = 0
        if nm in ("LocalAlloc", "GlobalAlloc"):
            val = self.alloc(max(a[1], 16))
        elif nm in ("LocalReAlloc", "GlobalReAlloc"):
            val = self.alloc(max(a[1], 16))
            try:
                uc.mem_write(val, bytes(uc.mem_read(a[0], min(a[1], 4096))))
            except UcError:
                pass
        elif nm == "HeapAlloc":
            val = self.alloc(a[2])
        elif nm == "VirtualAlloc":
            val = self.alloc(max(a[1], 16))
        elif nm in ("HeapFree", "VirtualFree", "VirtualProtect", "FlushInstructionCache"):
            val = 1
        elif nm == "GetProcessHeap":
            val = 0x1000
        elif nm == "GetLastError":
            val = self.state["lasterr"]
        elif nm == "SetLastError":
            self.state["lasterr"] = a[0]
        elif nm == "GetCurrentThreadId":
            val = 1234
        elif nm == "TlsGetValue":
            val = self.state["tls"].get(a[0], 0)
        elif nm == "TlsSetValue":
            self.state["tls"][a[0]] = a[1]
            val = 1
        elif nm == "TlsAlloc":
            val = len(self.state["tls"]) + 1
        elif nm == "GetTickCount":
            val = 100000
        elif nm == "GetModuleHandleA":
            val = self.base
        elif nm == "GetVersion":
            val = 0x0A280105
        elif nm == "GetACP":
            val = 950
        elif nm in ("InterlockedIncrement", "InterlockedDecrement"):
            v = (struct.unpack("<I", bytes(uc.mem_read(a[0], 4)))[0] + (1 if nm == "InterlockedIncrement" else -1)) & 0xFFFFFFFF
            uc.mem_write(a[0], struct.pack("<I", v))
            val = v
        r = struct.unpack("<I", bytes(uc.mem_read(sp, 4)))[0]
        uc.reg_write(UC_X86_REG_ESP, sp + 4 + 4 * argc)
        uc.reg_write(UC_X86_REG_EAX, val & 0xFFFFFFFF)
        uc.reg_write(UC_X86_REG_EIP, r)


class SessionKey:
    """一个种子对应的会话状态。构造时跑一遍调度函数（几秒，Unicorn 里约 1 秒以内）。"""

    def __init__(self, seed: bytes, g2: int = None, exe=EXE):
        if len(seed) != 4:
            raise ValueError("种子是 4 个字节")
        self.seed = bytes(seed)
        self.g2 = g2
        self.e = Emu(exe)
        self.e.call(SCHEDULE, eax=self.e.delphi_string(self.seed))
        if g2 is not None:                                # 玩家对象：[G2_PTR] -> 指针 -> 对象；+0x210 放 64 位数
            obj = self.e.alloc(0x1000)
            self.e.uc.mem_write(obj + 0x210, struct.pack("<q", g2))
            ptr = self.e.alloc(16)
            self.e.uc.mem_write(ptr, struct.pack("<I", obj))
            self.e.uc.mem_write(G2_PTR, struct.pack("<I", ptr))

    @property
    def modulus(self):
        return self.e.u32(ADDR_M)

    @property
    def second(self):
        return self.e.u32(ADDR_X)

    def doubles(self):
        """调度函数算出来的几个全局，调试用。"""
        r = self.e.rd
        return {"D[20524e8]": struct.unpack("<d", r(0x20524e8, 8))[0], "D[2518]": struct.unpack("<d", r(0x2052518, 8))[0],
                "S[252c]": struct.unpack("<f", r(0x205252c, 4))[0], "I64[2538]": struct.unpack("<q", r(0x2052538, 8))[0],
                "R48[250c]": r(0x205250c, 6).hex(), "R48[2530]": r(0x2052530, 6).hex()}

    def provider(self, k: int) -> int:
        """FUN_009b6798(k)：k = 1..12 返回一个字节；其它返回 0。k 需要玩家数据时必须给过 g2。"""
        if k in NEEDS_G2 and self.g2 is None:
            raise ValueError("k=%d 需要玩家对象 G2+0x210 那个 64 位数，构造 SessionKey 时给 g2=" % k)
        return self.e.call(PROVIDER_SWITCH, eax=k) & 0xFF

    def k_for_e3(self, jyid, col, row, direction):
        """E3 的下标：(jyid + 0x1403 + col + row − 2·朝向) % M + 1（FUN_009b6874 的 0xE3 分支）。"""
        return (jyid + 0x1403 + col + row - 2 * direction) % self.modulus + 1

    def e3_tail(self, jyid, col, row, direction):
        return self.provider(self.k_for_e3(jyid, col, row, direction))


if __name__ == "__main__":
    import sys
    seed = bytes.fromhex(sys.argv[1] if len(sys.argv) > 1 else "a2bc2837")
    sk = SessionKey(seed)
    print("种子", seed.hex(), "M =", sk.modulus, "第二参数 =", sk.second)
    print("状态", sk.doubles())
    print("k=2:", sk.provider(2), " k=6:", sk.provider(6))
