"""列出汇编里某次 `CALL 0x004010dd`（易语言字符串拼接，可变参数，ECX=参数个数）的全部参数，按拼接顺序。

参数从右往左压栈，所以紧挨着 CALL 之前的 PUSH 是第一个参数（这里是 F5 B3 07 04 1E 前缀常量）。
常量参数（PUSH 立即数）会从 exe 里读出字符串；变量参数（PUSH [EBP+x]）列出栈偏移。

    python tools/concat_args.py <汇编json> 0x638768 [--exe 服务端.exe]
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

DEFAULT_EXE = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\服务端.exe"


class Image:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        n = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        self.base = struct.unpack_from("<I", self.data, pe + 24 + 28)[0]
        self.secs = []
        for i in range(n):
            o = pe + 24 + opt + 40 * i
            vs, va, rs, rp = struct.unpack_from("<IIII", self.data, o + 8)
            self.secs.append((va, max(vs, rs), rp))

    def cstr(self, va, limit=400):
        rva = va - self.base
        for sva, size, rp in self.secs:
            if sva <= rva < sva + size:
                off = rp + rva - sva
                end = self.data.find(b"\x00", off, off + limit)
                return self.data[off:end] if end >= off else None
        return None


def args_of_call(lines, call_addr: str):
    idx = next(i for i, l in enumerate(lines) if l.startswith(call_addr + ":"))
    pushes = []
    k = idx - 1
    # 向上收集：PUSH 之间可能夹着 MOV ECX 之类，直到遇到非 PUSH/MOV ECX 的指令
    while k >= 0:
        l = lines[k]
        body = l.split(": ", 1)[1] if ": " in l else l
        if body.startswith("PUSH"):
            pushes.append((l.split(":")[0], body))
        elif body.startswith("MOV ECX"):
            pass
        else:
            break
        k -= 1
    return pushes  # pushes[0] 是第一个参数（最后压栈）


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asm")
    ap.add_argument("call")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    a = ap.parse_args()
    img = Image(a.exe)
    lines = json.load(open(a.asm, encoding="utf-8"))["raw_result"]["value"].splitlines()
    pushes = args_of_call(lines, a.call)
    print(f"{len(pushes)} pushes before {a.call}")
    for n, (addr, body) in enumerate(pushes):
        m = re.match(r"PUSH 0x([0-9a-f]+)$", body)
        if m:
            va = int(m.group(1), 16)
            s = img.cstr(va) if 0x9D0000 <= va < 0xD00000 else None
            txt = repr(s.decode("gbk", "replace")) if s is not None else f"imm 0x{va:x}"
            print(f"{n:3d} {addr} CONST 0x{va:x} {txt}")
        else:
            m = re.match(r"PUSH dword ptr \[EBP \+ (-?0x[0-9a-f]+)\]$", body)
            if m:
                off = int(m.group(1), 16)
                if off > 0x7FFFFFFF:
                    off -= 1 << 32
                print(f"{n:3d} {addr} VAR   [EBP{off:+#x}]")
            else:
                print(f"{n:3d} {addr} {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
