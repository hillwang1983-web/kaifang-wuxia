#!/usr/bin/env python3
"""消点包的构造 / 解析 / 师傅表预检（masters.py），用对原版实测抓到的帧。只用标准库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import masters as M  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


ROWS = [
    {"master": 10003, "name": "玄悲", "order": 0, "kf": 1014, "kf_name": "伏魔剑法", "cap": 80, "school": 0, "cls": 1, "map": 2411},
    {"master": 10008, "name": "渡厄", "order": 1, "kf": 8004, "kf_name": "基本鞭法", "cap": 150, "school": 0, "cls": 0, "map": 2415},
    {"master": 10008, "name": "渡厄", "order": 0, "kf": 1019, "kf_name": "金刚伏魔圈", "cap": 100, "school": 0, "cls": 1, "map": 2415},
    {"master": 10029, "name": "慧真", "order": 2, "kf": 1000, "kf_name": "少林心法", "cap": 100, "school": 10, "cls": 0, "map": 2408},
]


def main():
    m = M.Masters(rows=[dict(r) for r in ROWS])
    check([x["master"] for x in m.on_map(2415)] == [10008] and [r["kf"] for r in m.on_map(2415)[0]["kfs"]] == [1019, 8004], "on_map：按师傅分组，武功按顺序排")
    check(m.on_map(1) == [], "on_map：没有师傅的图是空的")
    check(m.check(10003, 1014, 2411, 0) is None, "check：对的师傅 + 武功 + 地图 + 门派 0 → 通过（实测收 0x68）")
    check("不教" in m.check(10003, 1001, 2411, 0) and "不教" in m.check(60000, 1014, 2411, 0), "check：师傅不教这门武功 / 没有这位师傅 → 报错（实测『無此師傅代碼』）")
    check("不在" in m.check(10003, 1014, 2801, 0), "check：地图不对 → 报错（实测『消點地圖不正确』+ 掉一级）")
    check("门派" in m.check(10029, 1000, 2408, 0) and m.check(10029, 1000, 2408, 10) is None, "check：门派 10 的师傅，玩家门派 0 → 报错，门派 10 → 通过（实测）")

    # 校验下标：k = (师傅 + 0x7530 − 武功 + 序号) % M + 1
    seq, k = M.pick_seq_study(1, 10003, 1014, 8)
    check(k == (10003 + 0x7530 - 1014 + seq) % 8 + 1 and k in (2, 6), "pick_seq_study：k 的公式和落点")
    check(all(M.pick_seq_study(s, a, b, mm)[1] in (2, 6) for s in (1, 50) for a in (10003, 10029, 60000) for b in (1014, 1000, 8004) for mm in (8, 9, 10, 11, 12)), "pick_seq_study：各种 M 都能凑到 k = 2 或 6")
    p = M.build_study(10003, 1014, 3, 9, lambda kk: 0x55, 6)
    check(p.hex(" ") == "13 27 f6 03 03 00 09 00 00 00 55", "build_study：师傅 | 武功 | 点数 | 序号 | 校验字节（11 字节）")
    check(len(M.build_study(65535, 65535, 65535, 1, lambda kk: 0, 2)) == 11, "build_study：字段都是 LE16，最大值也是 11 字节")

    r = M.parse_68(bytes.fromhex("f6 03 12 00 68 13 00 00 00 00 c6 00"))
    check(r == {"kf": 1014, "lv": 18, "exp": 4968, "study": 0, "jing": 198}, "parse_68：实测 lvl 5 花 2000 点 → 1014 lvl 18 经验 4968 学点 0 精 198")
    r = M.parse_68(bytes.fromhex("f6 03 05 00 1f 00 00 00 63 00 c6 00"))
    check(r["exp"] == 31 and r["study"] == 99, "parse_68：1 点 → 经验 31，学点 99")
    r = M.parse_70(bytes.fromhex("64 00 c6 00 f6 03 4e 00 00 00 00 00"))
    check(r == {"study": 100, "jing": 198, "kf": 1014, "lv": 78, "exp": 0}, "parse_70：实测掉一级（1014 79 → 78，经验清零）")
    check(M.parse_68(b"\x01\x02") is None and M.parse_70(b"") is None, "parse_68 / parse_70：太短 → None")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
