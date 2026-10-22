#!/usr/bin/env python3
"""读秘笈包（books.py）的构造 / 预检，用对原版实测的行为。只用标准库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import books as B  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    check(B.build_read(35022, 200).hex(" ") == "ce 88 00 00 c8", "build_read：乾坤大挪移秘笈 35022 = ce 88，高字 0，耐久 200（实测发出去的那一包）")
    check(B.build_read(40177, 200, 0).hex(" ") == "f1 9c 00 00 c8" and len(B.build_read(1, 0)) == 5, "build_read：太玄经 40177 = f1 9c，共 5 字节")
    ok = {k: 60 for k in B.STATS}
    check(B.check(35022, ok, set()) is None, "check：乾坤大挪移，全属性 60 → 可以读（实测学到 2203 Lv1）")
    check(B.check(35022, dict(ok, wint=49), set()) == "需要全屬性50", "check：有一项 49 → 需要全屬性50（实测书不扣）")
    check(B.check(35022, {}, set()) == "需要全屬性50", "check：属性读不到按 0 算")
    check(B.check(35031, ok, set()) == "需要全屬性50,需要自宮" and B.check(35031, dict(ok, zigong=1), set()) is None, "check：葵花宝典要自宫（实测学到 3004）")
    check(B.check(40177, dict(ok, zigong=1), set()) is None and B.check(40177, ok, set()) is not None, "check：太玄经同样要自宫（实测学到 4023）")
    check("已經有此武功" in B.check(35022, ok, {2203}), "check：已有这门武功 → 拦下（实测书照样被扣）")
    check("只认" in B.check(35041, ok, set()) and "只认" in B.check(0, ok, set()), "check：别的物品原版服务端静默，直接拦下")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
