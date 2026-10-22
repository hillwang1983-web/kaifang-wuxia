#!/usr/bin/env python3
"""生活技能包的构造 / 解析（lifeskill.py），用对原版实测抓到的字节。只用标准库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lifeskill as L  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    # 实测：种子 a2bc2837（M = 8），开始伐木 A=1 B=1 F=0、全 0，序号 1，k = 6，校验字节 125 = 0x7D
    seq, k = L.pick_seq(1, 1, 1, 0, 8)
    check((seq, k) == (1, 6), "pick_seq：A=1 B=1 F=0 M=8 从 1 起 → 序号 1，k = 6（实测那一包）")
    p = L.build_z(seq, 1, 1, 0, 0, 0, 0, lambda kk: {6: 125}[kk], k)
    check(p.hex(" ") == "01 00 00 00 01 01 00 00 00 00 00 00 7d", "build_z：实测开始伐木那一包")
    seq, k = L.pick_seq(2, 3, 0, 0, 8)
    check((seq, k) == (4, 6), "pick_seq：停止（A=3，B=F=0）从 2 起 → 序号 4（实测）")
    check(L.build_z(seq, 3, 0, 0, 0, 0, 0, lambda kk: 125, k).hex(" ") == "04 00 00 00 03 00 00 00 00 00 00 00 7d", "build_z：实测停止那一包")
    seq, k = L.pick_seq(8, 1, 2, 0, 8)
    check(seq == 8 and k == 6, "pick_seq：捕魚开始（B=2）从 8 起 → 序号 8，k = 6（实测，校验字节 125）")
    check(all(L.pick_seq(s, a, b, f, m)[1] in (2, 6) for s in (1, 7, 100) for a in (1, 2, 3) for b in (1, 2, 3) for f in (0, 22) for m in (8, 9, 10, 11, 12)), "pick_seq：各种 M / A / B / F 都能凑到 k = 2 或 6")
    p = L.build_z(5, 2, 1, 22, 0xAFD2, 0x1234, 7, lambda kk: 0x1F, 6)
    check(p == bytes([5, 0, 0, 0, 2, 1, 22, 0xD2, 0xAF, 0x34, 0x12, 7, 0x1F]), "build_z：E / D 是 LE16，校验字节在最后")

    r = L.parse_64(bytes.fromhex("7c ac 01 00 08 06 00 00"))
    check(r == {"item_id": 44156, "ok": True, "a": 0, "b": 8, "count": 6}, "parse_64：实测第一轮的结果（8 字节，44156 = 相思木，成功，计数 6）")
    check(L.parse_64(bytes.fromhex("7c ac 01 00 0a 23 00 00"))["count"] == 0x23 and L.parse_64(bytes.fromhex("7c ac 01 00 08 06 00 00 00"))["count"] == 6, "parse_64：计数 3 字节 / 4 字节都行")
    check(L.parse_64(bytes.fromhex("7c ac 00 00 08 06 00 00 00"))["ok"] is False and L.parse_64(b"\x01\x02") is None, "parse_64：成功字节 = 0 → ok False；太短 → None")

    names = {45010: "斧头", 45023: "黄金斧头", 45001: "钓竿", 45007: "十字镐", 45014: "锄头", 37294: "三阶工具兑换卷", 63798: "斧握柄", 40196: "斧", 45403: "三阶斧", 45204: "万用十字镐"}
    check(L.tool_ids(names, 1) == [45010, 45023, 45403] and L.tool_ids(names, 2) == [45001] and L.tool_ids(names, 3) == [45007, 45204], "tool_ids：按关键字挑工具，排除兑换券 / 零件 / 45xxx 以外的")
    check(L.tool_ids(names, 4) == [45014], "tool_ids：農夫的工具 = 锄头")

    # 農夫：播種 0x5B = 田块 + 种子 id LE16（对原版实测：田块 2 稻米种子 44201 = a9 ac → 回 0x66 … 02 a9 ac 01）
    check(L.build_plant(2, 44201).hex(" ") == "02 a9 ac", "build_plant：田块 + 种子 id LE16（实测 02 a9 ac）")
    check(all(L.pick_seq_farm(s, p, a, m)[1] in (2, 6) for s in (1, 9, 77) for p in range(0, 20) for a in (1, 2) for m in (8, 9, 10, 11, 12)), "pick_seq_farm：各种田块 / 动作 / M 都能凑到 k = 2 或 6")
    seq, k = L.pick_seq_farm(1, 2, 1, 8)
    check(k == (2 + 1 + seq) % 8 + 1 and k in (2, 6), "pick_seq_farm：k = (田块 + 动作 + 序号) % M + 1")
    p = L.build_farm(5, 2, 1, 0, 0, 0, lambda kk: 0x7D, 6)
    check(p.hex(" ") == "05 00 00 00 02 01 00 00 00 00 00 7d", "build_farm：序号 | 田块 | 动作 | E D C | 校验字节（共 12 字节）")
    p = L.build_farm(6, 19, 2, 0x1234, 0x5678, 9, lambda kk: 0x11, 2)
    check(p == bytes([6, 0, 0, 0, 19, 2, 0x34, 0x12, 0x78, 0x56, 9, 0x11]), "build_farm：收成 + E / D 是 LE16")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
