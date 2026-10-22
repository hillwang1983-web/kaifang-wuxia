"""把一个处理函数的汇编压缩成「流程大纲」：按地址顺序列出它引用的 SQL、S2C 模板、含中文的字符串，
以及对发包函数 0x407c13 / 断开 0x458b72 / 查玩家 0x406bc5 的调用。

读汇编里的 `PUSH 0x<地址>` / `MOV reg, 0x<地址>`，若地址落在 .rdata 且指向可打印字符串就读出来。

    python tools/flow_outline.py <汇编json> [--templates data/s2c_templates.json] [--exe 服务端.exe]

汇编 json 来自 REA 的 procedure_assembly（结果过大时会自动存成文件）。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\服务端.exe"
ADDR_RE = re.compile(r"^(0x[0-9a-f]+): (?:PUSH|MOV [A-Z]+,) 0x([0-9a-f]+)$")
CALL_RE = re.compile(r"^(0x[0-9a-f]+): CALL 0x([0-9a-f]+)$")
SPECIAL_CALLS = {
    0x407C13: "SEND(msg, conn)",
    0x458B72: "DISCONNECT(conn)",
    0x406BC5: "find_player(conn)",
    0x401B70: None,  # 字符串比较，太多，不列
}
SQL_RE = re.compile(r"^(select|update|insert|delete)\b", re.I)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


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

    def cstr(self, va: int, limit=200) -> bytes | None:
        rva = va - self.base
        for sva, size, rp in self.secs:
            if sva <= rva < sva + size:
                off = rp + rva - sva
                end = self.data.find(b"\x00", off, off + limit)
                return self.data[off:end] if end > off else None
        return None


def classify(raw: bytes, templates: dict[int, str], va: int):
    if va in templates:
        return "TEMPLATE", templates[va]
    try:
        s = raw.decode("gbk")
    except UnicodeDecodeError:
        return None
    if not s or not all(c.isprintable() for c in s):
        return None
    if SQL_RE.match(s):
        return "SQL", s
    if re.match(r"^(F4 44|F5 B3) ", s):
        return "FRAME", s
    if CJK_RE.search(s):
        return "TEXT", s
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("asm")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--templates", default=str(ROOT / "data" / "s2c_templates.json"))
    ap.add_argument("--max-text", type=int, default=90)
    ap.add_argument("--calls", action="store_true", help="同时列出其余（非通用）函数调用")
    args = ap.parse_args()

    img = Image(args.exe)
    templates = {}
    tp = Path(args.templates)
    if tp.exists():
        for r in json.loads(tp.read_text(encoding="utf-8")):
            if r.get("va"):
                templates[int(r["va"], 16)] = r["hex"]

    lines = json.loads(Path(args.asm).read_text(encoding="utf-8"))["raw_result"]["value"].splitlines()
    callcount: dict[int, int] = {}
    for ln in lines:
        m = CALL_RE.match(ln)
        if m:
            callcount[int(m.group(2), 16)] = callcount.get(int(m.group(2), 16), 0) + 1

    seen_at = None
    for ln in lines:
        m = ADDR_RE.match(ln)
        if m:
            va = int(m.group(2), 16)
            if 0x9D0000 <= va < 0xD00000:
                raw = img.cstr(va)
                if raw:
                    c = classify(raw, templates, va)
                    if c:
                        key = (c[0], va)
                        if key != seen_at:
                            print(f"{m.group(1)}  {c[0]:<8} {c[1][: args.max_text]}")
                        seen_at = key
            continue
        m = CALL_RE.match(ln)
        if m:
            tgt = int(m.group(2), 16)
            if tgt in SPECIAL_CALLS:
                if SPECIAL_CALLS[tgt]:
                    print(f"{m.group(1)}  CALL     {SPECIAL_CALLS[tgt]}")
            elif args.calls and 0x410000 <= tgt < 0x900000 and callcount.get(tgt, 0) < 8:
                print(f"{m.group(1)}  call     0x{tgt:x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
