"""打印汇编转储里某地址前后的精简上下文（CALL/跳转/比较/指向 exe 字符串的常量），离线读代码用。

    python tools/asm_ctx.py <汇编json> 0x62845e [--back 80] [--fwd 5]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concat_args import DEFAULT_EXE, Image  # noqa: E402

KEEP = ("CALL", "J", "CMP", "LEA", "IMUL", "SHL", "MOV ECX, 0x", "MOV EAX, 0x", "MOV EBX, 0x")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asm")
    ap.add_argument("addr")
    ap.add_argument("--back", type=int, default=80)
    ap.add_argument("--fwd", type=int, default=5)
    ap.add_argument("--all", action="store_true", help="不过滤，打印全部指令")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    a = ap.parse_args()
    img = Image(a.exe)
    lines = json.load(open(a.asm, encoding="utf-8"))["raw_result"]["value"].splitlines()
    idx = {l.split(":")[0]: i for i, l in enumerate(lines)}
    i = idx[a.addr]
    for l in lines[max(0, i - a.back): i + a.fwd + 1]:
        ad, b = l.split(": ", 1)
        note = ""
        m = re.match(r"(?:PUSH|MOV E.X,) 0x([0-9a-f]+)$", b)
        if m and 0x9D0000 <= int(m.group(1), 16) < 0xD00000:
            s = img.cstr(int(m.group(1), 16), 80)
            note = f"   ; {s.decode('gbk', 'replace')!r}" if s is not None else ""
        if a.all or note or b.startswith(KEEP) or re.match(r"PUSH dword ptr \[EBP", b) or re.match(r"MOV dword ptr \[EBP", b):
            if "0x90a3f1" in b:
                continue
            print(f"{ad}: {b}{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
