"""从 REA 导出的 C2S 总分发函数汇编里，提取「opcode → 候选处理函数」表。

总分发函数是 服务端.exe 的 0x5f8f04：它把收到的封包文本按空格拆成十六进制字符串，
再用字符串比较（0x401b70）逐个对照 ~88 个 opcode 常量。本脚本找出每个比较点，
取比较点之后、下一个比较点之前出现的第一个「非通用」调用作为候选处理函数。

这是启发式提取，**不是完整的控制流分析**：
  - 某些 opcode 的处理是内联的（没有独立函数），表里记为空；
  - 一个 opcode 可能有多个比较点（不同分支）；
  - 已被独立证据验证的只有：0x15 → 0x6b78f1（函数里 8 次构造 `F4 44 0E 17` 即 S2C 穿装备广播）。

用法：先用 REA 的 procedure_assembly 导出 0x5f8f04 的汇编（结果过大时会自动存成 JSON 文件），再
    python tools/dispatch_map_from_asm.py <汇编json> [服务端.exe] [输出json]
"""

from __future__ import annotations

import json
import re
import struct
import sys
from collections import Counter, OrderedDict
from pathlib import Path

DEFAULT_EXE = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\服务端.exe"
CALL_RE = re.compile(r"^(0x[0-9a-f]+): CALL 0x([0-9a-f]+)$")


class Image:
    def __init__(self, path: str):
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

    def cstr(self, va: int) -> bytes | None:
        rva = va - self.base
        for sva, size, rp in self.secs:
            if sva <= rva < sva + size:
                off = rp + rva - sva
                return self.data[off : self.data.index(b"\x00", off)]
        return None


def build(asm_json: str, exe: str):
    img = Image(exe)
    lines = json.load(open(asm_json, encoding="utf-8"))["raw_result"]["value"].splitlines()
    callcount: Counter[int] = Counter()
    for ln in lines:
        m = CALL_RE.match(ln)
        if m:
            callcount[int(m.group(2), 16)] += 1

    sites = []
    for i, ln in enumerate(lines):
        if ln.endswith("CALL 0x00401b70"):
            for k in range(1, 7):
                m = re.search(r"PUSH 0x([0-9a-f]+)$", lines[i - k]) if i - k >= 0 else None
                if m and 0x9D0000 <= int(m.group(1), 16) < 0xD00000:
                    s = img.cstr(int(m.group(1), 16))
                    if s is not None and re.fullmatch(rb"[0-9A-Fa-f]{2}", s):
                        sites.append((i, s.decode().upper()))
                    break

    helpers = {a for a, c in callcount.items() if c >= 8 or a < 0x410000 or a >= 0x900000}
    result: "OrderedDict[str, list]" = OrderedDict()
    for idx, (i, const) in enumerate(sites):
        end = sites[idx + 1][0] if idx + 1 < len(sites) else min(len(lines), i + 400)
        callees = []
        for ln in lines[i + 1 : end]:
            m = CALL_RE.match(ln)
            if m:
                a = int(m.group(2), 16)
                if a not in helpers and a not in callees:
                    callees.append(a)
        result.setdefault(const, []).append(
            {"compare_at": lines[i].split(":")[0], "handlers": [f"0x{a:x}" for a in callees[:4]]}
        )
    return result, len(sites)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    asm = sys.argv[1]
    exe = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_EXE
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "data" / "c2s_dispatch.json"
    result, nsites = build(asm, exe)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    with_handler = sum(1 for v in result.values() if any(e["handlers"] for e in v))
    print(f"compare sites: {nsites}, opcodes: {len(result)}, with a candidate handler: {with_handler}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
