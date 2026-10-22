"""把 0x1E 拼接的 57 个变量 + 常量片段，按宽度累加出载荷偏移，并和差分探测得到的「数据库列→偏移」对位。

输入：汇编 json（人物数据回馈 0x615995）、差分探测结果 data/layout/*.json。
未知宽度的变量用 UNKNOWN_SIZES 里的值（由相邻地标反推），脚本会检查所有地标是否对得上，并校验总长 == 1388。

    python tools/align_1e.py <汇编json> [--md docs/0x1E字段表.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concat_args import DEFAULT_EXE, Image, args_of_call  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CALLS = {"A": "0x638768", "B": "0x638abf"}  # A: [EBP-0x200]>0x10 (114 参数)  B: <=0x10 (113 参数，登录样本走 B)
TOTAL = 1388
OFF = r"\[EBP \+ (-?0x[0-9a-f]+)\]"
CONV = {0x40737F: "le", 0x4071C1: "le"}

# 无法从「转换调用」读出宽度的变量（EBP 偏移 → 字节数），由相邻地标反推；见文档
UNKNOWN_SIZES = {
    -0x1D8: 2,    # 背包头第 2 项  "17 00"
    -0x1DC: 115,  # 23 个背包格 × 5
    -0x1B4: 45,   # 9 个装备格 × 5
    -0x3AC: 4,    # jyid
    -0x36C: 1,    # zigong（共享转换调用 0x6368d4 读出 4，被实测 247/248 的相邻锚点否决）
    -0x330: 1,    # b_month
    -0x334: 1,    # b_day
    -0x2B4: 2,    # 门派技能槽前的 2 字节（锚点 378）
    -0x250: 30,   # char_equip 15×2
    -0x1B8: 102,  # 17 种武功 ×(等级2+经验4)
    -0x1FC: 2,    # 锚点 673 − 530
    -0x2B0: 55,   # jineng 11 种生活技能 ×(等级1+经验4)
}


def s32(v):
    return v - (1 << 32) if v > 0x7FFFFFFF else v


def off_of(tok):
    return int(tok, 16) if tok.startswith("-") else s32(int(tok, 16))


def load_probe_columns():
    """列名 → [(offset,width)]（只取 0x1E 帧，即 frame 1；排除时间计数 byte0）。"""
    cols = {}
    for name in ("renwu.json", "renwu3.json", "char_equip.json", "jineng.json", "jineng_lv.json"):
        p = ROOT / "data" / "layout" / name
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        tbl = d.get("table", "")
        for col, info in d["columns"].items():
            for c in info.get("changes", []) if isinstance(info, dict) else []:
                if c["frame"] == 1 and c["offset"] != 0:
                    cols.setdefault(f"{tbl}.{col}", []).append((c["offset"], c["width"]))
    p2 = ROOT / "data" / "layout" / "renwu2.json"
    if p2.exists():  # 第二轮：用结构变化列的小值得到的位置
        d = json.loads(p2.read_text(encoding="utf-8"))
        for col, info in d["columns"].items():
            for t in info.get("trials", []):
                for c in t.get("changes", []):
                    if c["frame"] == 1 and c["offset"] != 0:
                        cols.setdefault(f"renwu.{col}", [])
                        if (c["offset"], c["width"]) not in cols[f"renwu.{col}"]:
                            cols[f"renwu.{col}"].append((c["offset"], c["width"]))
    return cols


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asm")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--md", default=None)
    ap.add_argument("--variant", default="B", choices=["A", "B"])
    a = ap.parse_args()
    img = Image(a.exe)
    lines = json.load(open(a.asm, encoding="utf-8"))["raw_result"]["value"].splitlines()
    idx = {l.split(":")[0]: i for i, l in enumerate(lines)}
    CALL = CALLS[a.variant]
    call_i = idx[CALL]
    body = lambda i: lines[i].split(": ", 1)[1]
    store_re = re.compile(r"MOV dword ptr " + OFF + r", ([A-Z]{3}|0x[0-9a-f]+)$")

    segs = []
    for _, b in args_of_call(lines, CALL):
        m = re.match(r"PUSH 0x([0-9a-f]+)$", b)
        if m:
            va = int(m.group(1), 16)
            s = img.cstr(va, 4000).decode("gbk", "replace") if 0x9D0000 <= va < 0xD00000 else ""
            toks = s.split()
            if s.strip() == "" or all(re.fullmatch(r"[0-9A-Fa-f]{1,2}", t) for t in toks):
                segs.append({"kind": "const", "bytes": [int(t, 16) for t in toks], "va": va})
            else:
                segs.append({"kind": "const", "bytes": [], "text": s, "va": va})
            continue
        m = re.match(r"PUSH dword ptr " + OFF + "$", b)
        segs.append({"kind": "var", "ebp": off_of(m.group(1))} if m else {"kind": "?", "text": b})

    # 变量宽度
    for s in segs:
        if s["kind"] != "var":
            continue
        si = next((i for i in range(call_i - 1, -1, -1) if (m := store_re.match(body(i))) and off_of(m.group(1)) == s["ebp"]), None)
        s["store"] = lines[si].split(":")[0] if si is not None else None
        width = None
        if si is not None:
            for q in range(si, max(0, si - 90), -1):
                m = re.match(r"CALL 0x([0-9a-f]+)$", body(q))
                if m and int(m.group(1), 16) in CONV:
                    for r in range(q - 1, q - 6, -1):
                        mm = re.match(r"PUSH 0x([0-9a-f]+)$", body(r))
                        if mm:
                            width = int(mm.group(1), 16)
                            s["conv"] = f"0x{int(m.group(1), 16):x}@{lines[q].split(':')[0]}"
                            break
                    break
        if s["ebp"] in UNKNOWN_SIZES:
            width = UNKNOWN_SIZES[s["ebp"]]
            s["conv"] = "(inferred)"
        s["width"] = width

    # 累加偏移（前缀 5 字节是帧头，不在载荷里）
    off = 0
    rows = []
    for n, s in enumerate(segs):
        if n == 0:
            continue  # 前缀常量 F5 B3 07 04 1E
        if s["kind"] == "const":
            size = len(s["bytes"])
        else:
            size = s["width"]
        rows.append({"n": n, "kind": s["kind"], "offset": off, "size": size, "seg": s})
        off += size or 0
    unresolved = [r for r in rows if r["size"] is None]
    print(f"sum of known sizes = {off} (expected {TOTAL}); unresolved vars: {[hex(r['seg']['ebp']) for r in unresolved]}")

    cols = load_probe_columns()
    by_off = {}
    for name, locs in cols.items():
        for o, w in locs:
            by_off.setdefault(o, []).append(f"{name}(+{w})")

    ok = bad = 0
    out_lines = []
    for r in rows:
        s = r["seg"]
        o, size = r["offset"], r["size"] or 0
        hits = [x for k in range(o, o + max(size, 1)) for x in by_off.get(k, [])]
        hits = list(dict.fromkeys(hits))
        if s["kind"] == "const":
            what = "const " + " ".join(f"{b:02X}" for b in s["bytes"][:12]) + (" …" if len(s["bytes"]) > 12 else "")
        else:
            what = f"var [EBP{s['ebp']:+#x}] {s.get('conv','')}"
        out_lines.append((o, size, r["kind"], what, hits, s.get("store")))
        print(f"{o:5d} {size:4d} {r['kind']:<5} {what:<54} {', '.join(hits)}")
    print(f"landmarks mapped to a segment start/inside: {sum(1 for x in out_lines if x[4])} segments carry probe columns")

    if a.md:
        md = ["| 载荷偏移 | 大小 | 类型 | 内容（代码：拼接参数 / 常量） | 差分实测命中的数据库列 |", "|---|---|---|---|---|"]
        for o, size, kind, what, hits, store in out_lines:
            md.append(f"| {o} | {size} | {kind} | {what} | {', '.join(hits)} |")
        Path(a.md).write_text("\n".join(md), encoding="utf-8")
        print("wrote", a.md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



