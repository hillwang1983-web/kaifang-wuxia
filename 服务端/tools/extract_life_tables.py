"""从原版 0x73c6e8（采集产出）的反编译里把 伐木 / 捕魚 / 採礦 的产出表抠出来：把反编译里只含 技能等级 / 随机数(1–100) / 物品 ID 字符串 的嵌套 if 翻成 Python 逐点求值，
再压成区间表写到 data/life_items.json。

    python tools/extract_life_tables.py <condense_pseudo.py 处理过的 0x73c6e8 反编译 .c> [输出 json]

反编译里的写法：`(bVar1) && (pcVar13 = "44006", local_18 != 0)` 只在 bVar1 为真时才赋值；`goto LAB_x` 跳到 then 块末尾（块里只有 bVar1 = false）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 反编译文件（condense 之后）里的行号区间，闭区间：采矿 / 捕魚 / 伐木 的「按技能等级和随机数挑物品」那一段
REGIONS = {"caikuang": (248, 732), "buyu": (859, 1873), "famu": (2000, 2402)}
_ALLOWED = {"r", "lvl", "bVar1", "and", "or", "not", "True", "False", "_assign"}


class _Goto(Exception):
    pass


def cond(c: str) -> str:
    c = re.sub(r'\(pcVar13 = "(\d+)", local_\w+ != \(char \*\)0x0\)', lambda m: f"_assign({m.group(1)!r})", c)
    c = c.replace("&&", " and ").replace("||", " or ")
    c = c.replace("(int *)0x", "0x").replace("(int)(int *)local_30", "lvl").replace("(int *)local_30", "lvl").replace("local_10", "r").replace("iVar3", "lvl")
    c = re.sub(r"\(undefined \*\)\w+ != \(undefined \*\)0x0|local_\w+ != \(char \*\)0x0", "True", c)
    words = set(re.findall(r"[A-Za-z_]\w*", re.sub(r"0x[0-9a-fA-F]+|'\d+'", "", c)))
    if not words <= _ALLOWED:
        return "False"  # 指针 / 循环之类与产出表无关的条件：当作不成立（只管着释放内存）
    return c


def translate(lines: list[str]) -> str:
    out = ["def pick(lvl, r):", "    bVar1 = False"]
    ind = 1
    stack: list[tuple[str, int]] = []  # (kind, 这个块的 if / else 所在缩进)
    last_closed = ""

    def emit(s: str) -> None:
        out.append("    " * ind + s)

    for raw in lines:
        s = re.sub(r"^\s*\d+:\s*", "", raw).strip()
        if not s or re.match(r"LAB_\w+:", s):
            continue
        if s.startswith("}"):
            if not stack:
                continue
            kind, base = stack.pop()
            if kind == "else":
                ind = base + 1
                emit("except _Goto:")
                emit("    pass")
            ind = base
            last_closed = kind
            s = s[1:].strip()
            if not s or s.startswith("while"):
                continue
        m = re.match(r"else if \((.*)\) \{$", s)
        if m:
            emit("elif " + cond(m.group(1)) + ":")
            stack.append(("if", ind))
            ind += 1
            emit("pass")
            continue
        if s == "else {":
            emit("else:")
            stack.append(("else", ind))
            ind += 1
            emit("try:")
            ind += 1
            emit("pass")
            continue
        m = re.match(r"if \((.*)\) \{$", s)
        if m:
            emit("if " + cond(m.group(1)) + ":")
            stack.append(("if", ind))
            ind += 1
            emit("pass")
            continue
        m = re.match(r"if \((.*)\) goto (LAB_\w+);$", s)
        if m:
            emit("if " + cond(m.group(1)) + ":")
            emit("    bVar1 = False")
            emit("    raise _Goto()")
            continue
        if s.endswith("{"):  # for / while / do / 其它与产出表无关的块
            emit("if False:")
            stack.append(("if", ind))
            ind += 1
            emit("pass")
            continue
        m = re.match(r'pcVar13 = "(\d+)";$', s)
        if m:
            emit(f"_assign({m.group(1)!r})")
            continue
        m = re.match(r"bVar1 = (true|false);$", s)
        if m:
            emit("bVar1 = " + ("True" if m.group(1) == "true" else "False"))
    return "\n".join(out)


def build(src_lines: list[str], region: tuple[int, int]):
    a, b = region
    code = translate(src_lines[a - 1 : b])
    state = {"item": None}

    def _assign(x):
        state["item"] = x
        return True

    ns: dict = {"_Goto": _Goto, "_assign": _assign}
    exec(code, ns)
    fn = ns["pick"]

    def run(lvl: int, r: int):
        state["item"] = None
        fn(lvl, r)
        return state["item"]

    return run, code


def main() -> int:
    src = Path(sys.argv[1]).read_text(encoding="utf-8").split("\n")
    out = {}
    for name, region in REGIONS.items():
        run, code = build(src, region)
        Path(f"scratch/life_{name}.py").write_text(code, encoding="utf-8")
        table = {}
        for lvl in range(0, 121):
            ladder: list[list] = []
            for r in range(1, 101):
                item = run(lvl, r)
                if ladder and ladder[-1][2] == item and ladder[-1][1] == r - 1:
                    ladder[-1][1] = r
                else:
                    ladder.append([r, r, item])
            table[str(lvl)] = ladder
        out[name] = table
    Path(sys.argv[2] if len(sys.argv) > 2 else "data/life_items.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
