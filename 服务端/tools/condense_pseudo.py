"""把 REA 导出的易语言反编译伪代码压缩到能读：去掉「调试标记」习语（`uStack…= DAT_00caXXXX; FUN_00425d99(...)`）
和数组越界检查样板，保留行号方便回查。

    python tools/condense_pseudo.py <REA 结果 json> <输出 .c>

输入是 procedure_pseudo_code 结果过大时自动存下的 json（取 normalized_result）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def condense(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        l = lines[i]
        # 调试标记：4~6 行，赋值 DAT_00cab… / FUN_00425d99 / 释放
        if "= (char *)0x0;" in l and i + 2 < len(lines) and "DAT_00ca" in lines[i + 1] and "FUN_00425d99" in lines[i + 2]:
            i += 6 if i + 4 < len(lines) and "thunk_FUN_0092bab0" in lines[i + 4] else 3
            continue
        # 数组下标越界检查：if (x < 0) { x = thunk_FUN_0092b830(4,…); } / if (n <= x) { x = thunk_FUN_0092b830(1,…); }
        if re.match(r"\s*if \(\w+ (<|<=) \w+\) \{$", l) and i + 2 < len(lines) and "thunk_FUN_0092b830" in lines[i + 1]:
            i += 3
            continue
        out.append(f"{i + 1}: {l}")
        i += 1
    return out


def main() -> int:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    text = json.loads(src.read_text(encoding="utf-8"))["normalized_result"]
    out = condense(text)
    dst.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(text.splitlines())} -> {len(out)} lines -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
