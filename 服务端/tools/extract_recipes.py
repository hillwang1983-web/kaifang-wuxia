"""从原版 服务端.exe 的合成函数 0x7422b7（C2S 0x1B 的处理，1.36 MB）里抠配方表 -> jyserver/recipes.json。

    python tools/extract_recipes.py [--report]

函数的主体是 1445 段「if 配方键 == "F0 02" { … }」，键是帧的第 5、6 个十六进制词（载荷头两个字节，大写、空格隔开）。
绝大多数段是同一个模板：
    检查 n 种材料 >= 数量 -> 逐种扣除 -> 技能经验(0x737bc6) -> 随机数 < 阈值 ? 给成品(0x740523) : 失败帧(技能等级 / 经验)
本脚本用 capstone 线性反汇编，把每段归一成结构化记录；模板对不上的段（特殊配方）记入 unsupported，不进表。
需要：pip install capstone。字符串常量按 GBK 解。
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import capstone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import va_bytes as v  # noqa: E402

START, END = 0x7422B7, 0x88F10A
KEY_CMP = 0x401B70  # 字符串比较
HAVE = 0x4709D7  # 背包里某物品的数量
TAKE = 0x88F10A  # 扣物品(物品串, 数量串, 玩家)
EXP = 0x737BC6
GIVE = 0x740523
GATE = "0xdd88bc"

SKILLS = {"伐木": 0, "捕鱼": 9, "采矿": 5, "打铁": 6, "工匠": 1, "织布": 2, "裁缝": 3, "猎人": 4, "铸剑": 7, "农夫": 8, "厨师": 10}
SKILL_COL = {"工匠": "gongjiang", "织布": "zhibu", "裁缝": "caifeng", "猎人": "lieren", "打铁": "datie", "铸剑": "zhujian", "厨师": "chushi"}
# 等级 / 经验在玩家对象里的偏移 -> 技能（0x737bc6 里逐个读出来的）
OFFSETS = {0x1B4: "工匠", 0x1BC: "织布", 0x1C4: "裁缝", 0x1CC: "猎人", 0x1D4: "采矿", 0x1DC: "打铁", 0x1E4: "铸剑", 0x1F8: "捕鱼", 0x1FC: "厨师", 0x1AC: "伐木"}


def load():
    data = v.EXE.read_bytes()
    secs = v.load_sections(data)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    code = v.read_va(data, secs, START, END - START)
    ins = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(code, START)]
    return data, secs, ins


def cstr(data, secs, va: int) -> str:
    return v.read_va(data, secs, va, 64).split(b"\0")[0].decode("gbk", errors="replace")


def find_keys(data, secs, ins):
    keys = []
    for k in range(len(ins) - 3):
        a, m, o = ins[k]
        if m == "push" and re.match(r"0x[0-9a-f]{6}$", o) and ins[k + 1][2] == "ebx, dword ptr [ebp + 8]" and ins[k + 3][2] == hex(KEY_CMP):
            keys.append((k, cstr(data, secs, int(o, 16))))
    return keys


def collapse(bl):
    """把「取玩家对象字段」的样板压成 ('P', 偏移)。"""
    out, k = [], 0
    while k < len(bl):
        a, m, o = bl[k]
        if m == "mov" and o == "ebx, dword ptr [0xdd8518]" and k + 1 < len(bl) and bl[k + 1][2] == "0x40140b":
            j, off = k, None
            while j < min(len(bl), k + 45):
                if bl[j][1] == "add" and re.match(r"ebx, 0x[0-9a-f]+$", bl[j][2]) and bl[j - 1][2] == "ebx, dword ptr [ebx]":
                    off = int(bl[j][2].split()[-1], 16)
                    break
                j += 1
            if off is not None:
                out.append((a, "P", off))
                k = j + 1
                continue
        out.append((a, m, o))
        k += 1
    return out


def parse(bl, data, secs):
    """成功返回记录，模板对不上返回 (None, 原因)。"""
    c = collapse(bl)
    rec = {"needs": [], "takes": []}
    # 开头：键比较 + jne
    gate_msg = None
    idx = 0
    n = len(c)
    # 全局开关
    for i, (a, m, o) in enumerate(c[:12]):
        if m == "cmp" and o.startswith(f"dword ptr [{GATE}]"):
            rec["gate"] = True
            for q in c[i : i + 12]:
                if q[1] == "mov" and re.match(r"eax, 0x[0-9a-f]{6}$", q[2]):
                    gate_msg = int(q[2].split()[-1], 16)
                    break
            break
    if gate_msg:
        rec["gate_msg"] = cstr(data, secs, gate_msg)
    # 材料检查
    for i, (a, m, o) in enumerate(c):
        if m == "call" and o == hex(HAVE):
            item = int(c[i - 1][2], 16) if c[i - 1][1] == "push" else None
            cnt = None
            for q in c[i + 1 : i + 4]:
                if q[1] == "cmp":
                    t = q[2].split(",")[-1].strip()
                    cnt = int(t, 16) if t.startswith("0x") else int(t)
            if item is None or cnt is None:
                return None, "have"
            rec["needs"].append([item, cnt])
        if m == "call" and o == hex(TAKE):
            strs = [int(q[2].split()[-1], 16) for q in c[max(0, i - 16) : i] if q[1] == "mov" and re.match(r"eax, 0x[0-9a-f]{6}$", q[2])]
            if len(strs) != 2:
                return None, "take"
            cnt_s, item_s = cstr(data, secs, strs[0]), cstr(data, secs, strs[1])
            if not item_s.isdigit() or not cnt_s.isdigit():
                return None, "take-str"
            rec["takes"].append([int(item_s), int(cnt_s)])
        if m == "call" and o == hex(EXP):
            sk = [cstr(data, secs, int(q[2].split()[-1], 16)) for q in c[max(0, i - 6) : i] if q[1] == "mov" and re.match(r"eax, 0x[0-9a-f]{6}$", q[2])]
            if len(sk) != 1 or sk[0] not in SKILLS:
                return None, "skill"
            rec["skill"] = sk[0]
        if m == "mov" and o.startswith("dword ptr [ebp - 0x50], 0x"):
            rec["product"] = int(o.split(",")[1], 16)
    if not rec["needs"] or len(rec["needs"]) != len(rec["takes"]) or "skill" not in rec or "product" not in rec:
        return None, "shape"
    # 成功判定：随机数 [ebp-8] < 阈值（luk 或 局部变量）
    luk = any(m == "P" and o == 0xE0 for a, m, o in c)
    var = None
    for i, (a, m, o) in enumerate(c):
        if m == "cmp" and o == "dword ptr [ebp - 8], eax":
            if luk:
                var = "luk"
            else:
                prev = c[i - 1]
                mm = re.match(r"eax, dword ptr \[ebp - (0x[0-9a-f]+)\]$", prev[2]) if prev[1] == "mov" else None
                if not mm:
                    return None, "cmp"
                var = int(mm.group(1), 16)
            break
    if var is None:
        return None, "nocmp"
    rec["win"] = var
    # 失败帧里的等级 / 经验偏移
    offs = [o for a, m, o in c if m == "P" and o != 0xE0]
    if len(offs) < 2 or offs[1] != offs[0] + 4 or OFFSETS.get(offs[0]) != rec["skill"]:
        return None, "offs"
    rec["lvl_off"] = offs[0]
    return rec, None


def main() -> int:
    data, secs, ins = load()
    keys = find_keys(data, secs, ins)
    addr = {a: i for i, (a, _, _) in enumerate(ins)}
    recipes: dict[str, dict] = {}
    bad = Counter()
    unsupported: dict[str, str] = {}
    for n, (k, key) in enumerate(keys):
        j = keys[n + 1][0] if n + 1 < len(keys) else len(ins)
        rec, why = parse(ins[k:j], data, secs)
        if key in recipes or key in unsupported:
            continue  # 重复的键：先比较到的赢
        if rec is None:
            bad[why] += 1
            unsupported[key] = why
            continue
        recipes[key] = rec
    thresholds = {"0xc": 8, "0x10": 6, "0x14": 5, "0x18": 4, "0x1c": 3, "0x20": 2, "0x24": 1, "0x28": 2, "0x2c": 8}
    out = {"recipes": recipes, "unsupported": unsupported, "thresholds": {int(k, 16): v_ for k, v_ in thresholds.items()}}
    (ROOT / "jyserver" / "recipes.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(keys)} 段，{len(recipes)} 个配方进表，{len(unsupported)} 个不支持 {dict(bad)}")
    if "--report" in sys.argv:
        by = defaultdict(int)
        for r in recipes.values():
            by[(r["skill"], r["win"] if r["win"] == "luk" else hex(r["win"]), len(r["needs"]), r.get("gate", False))] += 1
        for kk, vv in sorted(by.items(), key=str):
            print(kk, vv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

