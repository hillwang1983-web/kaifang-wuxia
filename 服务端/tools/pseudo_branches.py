"""列出反编译伪代码里「拿某个令牌和某个短字符串比较」的所有位置——易语言的 `如果 令牌[N] == "30"` 分支树。

    python tools/pseudo_branches.py <REA 结果 json> [--max-len 3]

输出：行号 | 比较的令牌下标（取比较前最近一次 `iVarN = <数字>;`）| 被比较的字符串（从 服务端.exe 里按虚拟地址读出）。
用来在 9 万字节的大函数里先把「哪个 opcode / 子类型进哪一段」的骨架画出来。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from va_bytes import EXE, load_sections, read_va  # noqa: E402

CMP = re.compile(r"FUN_00401b70\((?P<a>[^;]*?),&?(?P<b>DAT_[0-9a-f]+|0x[0-9a-f]+)\)")
IDX = re.compile(r"(?:iVar|uVar|local_)\w+ = (\d+);")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--max-len", type=int, default=3)
    args = ap.parse_args()
    text = json.loads(Path(args.src).read_text(encoding="utf-8"))["normalized_result"].replace("\r\n", "\n")
    data = EXE.read_bytes()
    secs = load_sections(data)
    last_idx = None
    out = []
    for n, line in enumerate(text.split("\n"), 1):
        m = IDX.search(line)
        if m:
            last_idx = int(m.group(1))
        c = CMP.search(line)
        if not c:
            continue
        b = c.group("b")
        va = int(b[4:], 16) if b.startswith("DAT_") else int(b, 16)
        s = read_va(data, secs, va, 24).split(b"\0")[0]
        try:
            s = s.decode("gbk")
        except UnicodeDecodeError:
            continue
        if 0 < len(s) <= args.max_len:
            out.append((n, last_idx, s))
    for n, idx, s in out:
        print(f"{n:>7}  T[{idx}]  == {s!r}")
    print(f"-- {len(out)} comparisons", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
