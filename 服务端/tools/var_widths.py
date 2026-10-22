"""对 0x1E 拼接的每个变量：找出生成它的最后一次「数值→小端十六进制文本」调用，读出宽度参数。

易语言服务端里：
    CALL 0x0040737f(&文本变量, 宽度)   —— 数值文本 → 宽度字节的小端十六进制文本（实测：宽度 4 对应 LE32）
    CALL 0x004071c1(&文本变量, 宽度)   —— 同类（另一个重载），在摇点代码里宽度 1
    CALL 0x00407066(数值, 补零标志)    —— 数值 → 十六进制文本
    CALL 0x004010dd(...)               —— 字符串拼接（复合变量）
对每个包内变量，向上找最近的这些调用并打印其宽度。复合变量（由多段拼成）标为 concat。

    python tools/var_widths.py <汇编json> 0x638768
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concat_args import args_of_call, DEFAULT_EXE, Image  # noqa: E402

CONV = {0x40737F: "to_le(text,w)", 0x4071C1: "to_le2(text,w)", 0x407066: "tohex(num,pad)", 0x4010DD: "concat", 0x406F92: "f406f92", 0x4389BA: "f4389ba"}
OFF = r"\[EBP \+ (-?0x[0-9a-f]+)\]"


def s32(v):
    return v - (1 << 32) if v > 0x7FFFFFFF else v


def off_of(tok):
    return int(tok, 16) if tok.startswith("-") else s32(int(tok, 16))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asm")
    ap.add_argument("call")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    a = ap.parse_args()
    img = Image(a.exe)
    lines = json.load(open(a.asm, encoding="utf-8"))["raw_result"]["value"].splitlines()
    idx = {l.split(":")[0]: i for i, l in enumerate(lines)}
    call_i = idx[a.call]
    body = lambda i: lines[i].split(": ", 1)[1]

    packet = []  # (kind, value)
    for _, b in args_of_call(lines, a.call):
        m = re.match(r"PUSH 0x([0-9a-f]+)$", b)
        if m:
            va = int(m.group(1), 16)
            s = img.cstr(va, 300) if 0x9D0000 <= va < 0xD00000 else None
            packet.append(("const", s.decode("gbk", "replace") if s is not None else f"0x{va:x}"))
            continue
        m = re.match(r"PUSH dword ptr " + OFF + "$", b)
        packet.append(("var", off_of(m.group(1))) if m else ("?", b))

    store_re = re.compile(r"MOV dword ptr " + OFF + r", ([A-Z]{3}|0x[0-9a-f]+)$")
    pos = 0
    print(f"{'#':>3} {'kind':<6} {'what':<46} producer")
    for n, (kind, val) in enumerate(packet):
        if kind == "const":
            toks = [t for t in val.split() if t]
            note = f"const {len(toks)} byte(s)" if all(re.fullmatch(r"[0-9A-Fa-f]{1,2}", t) for t in toks) else "const"
            print(f"{n:3d} const  {val.strip()[:44]!r:<46} {note}")
            continue
        off = val
        # 最后一次赋值
        si = None
        for i in range(call_i - 1, -1, -1):
            m = store_re.match(body(i))
            if m and off_of(m.group(1)) == off:
                si = i
                break
        prod = "(no store before)"
        if si is not None:
            # 向上找最近的转换/拼接调用
            for q in range(si, max(0, si - 90), -1):
                m = re.match(r"CALL 0x([0-9a-f]+)$", body(q))
                if m and int(m.group(1), 16) in CONV:
                    tgt = int(m.group(1), 16)
                    width = ""
                    if tgt in (0x40737F, 0x4071C1):
                        for r in range(q - 1, q - 6, -1):
                            mm = re.match(r"PUSH 0x([0-9a-f]+)$", body(r))
                            if mm:
                                width = f" width={int(mm.group(1), 16)}"
                                break
                    prod = f"{CONV[tgt]}{width} @ {lines[q].split(':')[0]}"
                    if tgt == 0x4010DD:
                        prod += "  (compound)"
                    break
            else:
                prod = "no conv call within 90 lines"
        print(f"{n:3d} var    [EBP{off:+#x}]{'':<30} {prod}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
