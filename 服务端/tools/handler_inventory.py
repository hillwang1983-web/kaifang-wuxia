"""盘点 C2S 总分发函数调到的各个处理函数：大小、引用的 SQL、S2C 模板、含中文的文字。

不依赖 REA：函数终点取「全程序所有 call 目标里，起点之后最近的一个」（上界，可能略大），然后在 [起点, 终点) 里扫 `push imm32` / `mov reg, imm32`
指向 .rdata 的可读字符串。输出 docs 用的 markdown 表格素材。

    python tools/handler_inventory.py > scratch.txt
"""

from __future__ import annotations

import bisect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from va_bytes import EXE, load_sections, read_va  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMM = re.compile(rb"[\x68\xb8-\xbb\xbe\xbf](....)|\xc7[\x45\x85](?:.|....)(....)", re.S)


def cstr(data, secs, a: int, n: int = 160) -> bytes:
    try:
        return read_va(data, secs, a, n).split(b"\x00")[0]
    except Exception:
        return b""


def main() -> None:
    data = open(EXE, "rb").read()
    secs = load_sections(data)
    text = read_va(data, secs, 0x401000, 0x9D0000 - 0x401000)
    starts = sorted({0x401000 + m.start() + 5 + int.from_bytes(text[m.start() + 1 : m.start() + 5], "little", signed=True) for m in re.finditer(rb"\xe8", text) if m.start() + 5 <= len(text)})
    starts = [s for s in starts if 0x401000 <= s < 0x9D0000 and text[s - 0x401000 : s - 0x401000 + 3] == b'\x55\x8b\xec']
    chains = json.load(open(ROOT / "data" / "c2s_dispatch2.json", encoding="utf-8"))
    handlers: dict[int, list[str]] = {}
    for op, hs in chains.items():
        for h in hs:
            handlers.setdefault(int(h, 16), []).append(op)
    for h, ops in sorted(handlers.items()):
        i = bisect.bisect_right(starts, h)
        end = starts[i] if i < len(starts) else h + 4096
        body = text[h - 0x401000 : end - 0x401000]
        sql, tmpl, zh = [], [], []
        for m in IMM.finditer(body):
            a = int.from_bytes(m.group(1) or m.group(2), "little")
            if not 0x9D1000 <= a < 0xE28000:
                continue
            s = cstr(data, secs, a)
            if len(s) < 3:
                continue
            try:
                t = s.decode("gbk")
            except UnicodeDecodeError:
                continue
            if re.match(r"(?i)(select|update|insert|delete)\b", t):
                sql.append(t[:90])
            elif re.match(r"F[45] [0-9A-F]{2} ", t):
                tmpl.append(t.strip()[:20])
            elif re.search(r"[一-鿿]", t) and "命令标记" not in t and "子程序" not in t:
                zh.append(t[:24])
        dedup = lambda xs: list(dict.fromkeys(xs))
        print(f"## {','.join(ops)}  0x{h:x}  ~{end - h}B")
        for label, xs in (("SQL", sql), ("S2C", tmpl), ("文字", zh)):
            xs = dedup(xs)
            if xs:
                print(f"  {label}: " + " | ".join(xs[:8]) + (f" …(+{len(xs) - 8})" if len(xs) > 8 else ""))


if __name__ == "__main__":
    main()
