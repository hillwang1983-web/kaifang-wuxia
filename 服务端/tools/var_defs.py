"""对汇编里的每个栈变量 [EBP+x]，找出它在某个地址之前最后一次被赋值的位置，并列出生成它的调用与参数。

用来还原「某次拼接的每个变量到底是什么」：配合 concat_args.py 使用。

    python tools/var_defs.py <汇编json> 0x638768 [--vars -0x2bc,-0x1d8,...]   # 默认取 concat_args 的全部变量
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concat_args import DEFAULT_EXE, Image, args_of_call  # noqa: E402

OFF_RE = r"\[EBP \+ (-?0x[0-9a-f]+)\]"


def s32(v: int) -> int:
    return v - (1 << 32) if v > 0x7FFFFFFF else v


def norm_off(tok: str) -> int:
    return s32(int(tok, 16)) if not tok.startswith("-") else int(tok, 16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asm")
    ap.add_argument("call")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--window", type=int, default=40, help="向上看多少行找生成它的调用")
    ap.add_argument("--vars", default=None)
    a = ap.parse_args()
    img = Image(a.exe)
    lines = json.load(open(a.asm, encoding="utf-8"))["raw_result"]["value"].splitlines()
    addr_index = {l.split(":")[0]: i for i, l in enumerate(lines)}
    call_i = addr_index[a.call]

    if a.vars:
        order = [int(x, 16) for x in a.vars.split(",")]
    else:
        order = []
        for _, body in args_of_call(lines, a.call):
            m = re.match(r"PUSH dword ptr " + OFF_RE + "$", body)
            if m:
                order.append(norm_off(m.group(1)))

    store_re = re.compile(r"MOV dword ptr " + OFF_RE + r", ([A-Z]{3}|0x[0-9a-f]+)$")

    def describe(i_from: int, i_to: int) -> str:
        parts = []
        for l in lines[i_from:i_to]:
            body = l.split(": ", 1)[1]
            m = re.match(r"CALL 0x([0-9a-f]+)$", body)
            if m:
                parts.append(f"CALL 0x{int(m.group(1), 16):x}")
                continue
            m = re.match(r"PUSH 0x([0-9a-f]+)$", body)
            if m:
                va = int(m.group(1), 16)
                s = img.cstr(va, 120) if 0x9D0000 <= va < 0xD00000 else None
                if s is not None and 0 < len(s) < 100 and all(32 <= c < 127 or c >= 0x80 for c in s):
                    parts.append("'" + s.decode("gbk", "replace") + "'")
                else:
                    parts.append(f"#{va:#x}")
                continue
            m = re.match(r"PUSH dword ptr " + OFF_RE + "$", body)
            if m:
                parts.append(f"v{norm_off(m.group(1)):+#x}")
                continue
            m = re.match(r"MOV (?:EAX|EBX|ECX|EDX), 0x([0-9a-f]+)$", body)
            if m:
                va = int(m.group(1), 16)
                s = img.cstr(va, 120) if 0x9D0000 <= va < 0xD00000 else None
                if s is not None and 0 < len(s) < 100:
                    parts.append("&'" + s.decode("gbk", "replace") + "'")
        return " ".join(parts)

    seen = set()
    for n, off in enumerate(order, 1):
        if off in seen:
            continue
        seen.add(off)
        defs = []
        for i in range(call_i - 1, -1, -1):
            body = lines[i].split(": ", 1)[1]
            m = store_re.match(body)
            if m and norm_off(m.group(1)) == off:
                defs.append(i)
                if len(defs) >= 2:
                    break
        print(f"--- var#{n} [EBP{off:+#x}]")
        for i in defs:
            start = max(0, i - a.window)
            # 易语言的文本赋值：算新值 → PUSH EAX → 释放旧值(MOV EBX,[var]...CALL free) → POP EAX → MOV [var],EAX。
            # 所以真正生成新值的表达式在「PUSH EAX; MOV EBX,[var]」之前。
            m_idx = None
            for q in range(i, max(start, i - 16), -1):
                if re.search(r"MOV EBX, dword ptr " + OFF_RE.replace("(-?0x[0-9a-f]+)", re.escape(f"{off:#x}" if off >= 0 else f"-{-off:#x}")) + "$", lines[q].split(": ", 1)[1]):
                    m_idx = q
                    break
            end = (m_idx - 1) if m_idx is not None else i
            j = end
            while j > start and not lines[j].split(": ", 1)[1].startswith("CALL"):
                j -= 1
            k = j - 1
            while k > start and lines[k].split(": ", 1)[1].startswith(("PUSH", "MOV ECX", "LEA", "MOV EAX, 0x")):
                k -= 1
            print(f"    def @ {lines[i].split(':')[0]}  = {describe(k + 1, j + 1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
