"""从 服务端.exe 的 C2S 总分发函数 0x5f8f04 的机器码里提取「opcode → 处理函数」表（比 dispatch_map_from_asm.py 准）。

易语言生成的分支长这样：`push <字符串地址>; …; push [令牌]; call 0x401b70(比较); add esp,8; cmp eax,0; jne <块尾>`。
所以一次 call 所在的各层「字符串比较」就是它的条件链：最外层是 T[3]==opcode，内层是子类型。
本脚本找出所有 jne 比较块，再给每个 `call rel32` 标上包住它的比较链，只留「出现不多的」调用（排除通用辅助函数）。

    python tools/dispatch_map.py [输出 json]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from va_bytes import EXE, load_sections, read_va  # noqa: E402

START, END = 0x5F8F04, 0x5FE6B2
CMP = re.compile(rb"\x68(....)(?:.{0,16}?)\xe8....\x83\xc4\x08\x83\xf8\x00\x0f\x85(....)", re.S)


def main() -> None:
    data = open(EXE, "rb").read()
    secs = load_sections(data)
    code = read_va(data, secs, START, END - START)
    blocks = []  # (起点, 终点, 字符串)
    for m in CMP.finditer(code):
        a = int.from_bytes(m.group(1), "little")
        if not 0x9D1000 <= a < 0xE28000:
            continue
        s = read_va(data, secs, a, 8).split(b"\x00")[0]
        if not s or len(s) > 3:
            continue
        end_of_jne = START + m.end()
        tgt = end_of_jne + int.from_bytes(m.group(2), "little", signed=True)
        blocks.append((START + m.start(), tgt, s.decode("latin1")))
    calls = []
    for m in re.finditer(rb"\xe8(....)", code):
        pos = START + m.start()
        tgt = pos + 5 + int.from_bytes(m.group(1), "little", signed=True)
        if 0x401000 <= tgt < 0x9D0000:
            calls.append((pos, tgt))
    freq = Counter(t for _, t in calls)
    pushes = []  # (位置, 两位十六进制字符串)
    for m in re.finditer(rb"\x68(....)", code):
        a = int.from_bytes(m.group(1), "little")
        if 0x9D1000 <= a < 0xE28000:
            t = read_va(data, secs, a, 4).split(b"\x00")[0]
            if re.fullmatch(rb"[0-9A-F]{2}", t):
                pushes.append((START + m.start(), t.decode()))
    out: dict[str, list] = {}
    for pos, tgt in calls:
        if freq[tgt] > 6:
            continue
        prev = [p for p in pushes if p[0] < pos and pos - p[0] < 400]
        if not prev:
            continue
        out.setdefault(prev[-1][1], []).append(hex(tgt))
    res = {k: sorted(set(v)) for k, v in sorted(out.items())}
    path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data" / "c2s_dispatch2.json")
    json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(len(blocks), "compare blocks;", len(res), "chains")
    for k, v in res.items():
        print(k, v)


if __name__ == "__main__":
    main()
