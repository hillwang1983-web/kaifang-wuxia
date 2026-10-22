#!/usr/bin/env python3
"""外观表自测（离线，不连任何服务端）：用 Item3.Dat 和 role\\boy01.mrg 检查 gateway.Looks 的规则。

    python test_looks.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gateway  # noqa: E402

RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def main():
    pic = os.path.normpath(os.path.join(gateway.HERE, "..", "share"))
    L = gateway.Looks(os.path.join(pic, "dat", "Item3.Dat"))
    check(len(L.table) > 4000, "Item3.Dat 读到 %d 条有效外观码（共约 2 万条记录，多数物品没有外观码）" % len(L.table))
    check(L.table[0xFFFF] == ("ma0101", "ma0101"), "表里 0xFFFF = 默认头发 ma0101（0x51cd46 / 0x51cd7f 写入的常量）")
    # 记录布局：用样本核对（传家宝衣 27058 在 Item3.Dat 里是 wf0101，女 / 男同码）
    check(L.table.get(27058) == ("wf0101", "wf0101"), "27058 传家宝衣 -> wf0101")
    # 男 / 女取码：找一条男女码不同的记录
    diff = next((i for i, (a, b) in L.table.items() if a and b and a != b and i != 0xFFFF), None)
    a, b = L.table[diff]
    male = L.layers(1, [diff, 0, 0])
    check(any(e["l"] == "M1" + b[:4].upper() for e in male["layers"]) or any(i.get("missing") for i in male["info"]),
          "男模型取男码：id %d 女码 %s / 男码 %s -> %s" % (diff, a, b, male["info"][0]))
    # 头槽为 0 -> 默认头发 M1MA01 第 1 套
    d = L.layers(1, [0, 0, 0])
    check([(e["l"], e["s"]) for e in d["layers"]] == [("B10S", 0), ("M10000", 0), ("M1MA01", 1)], "三个槽全空：阴影 + 身体 + 默认头发 M1MA01 套 1 %s" % [(e["l"], e["s"]) for e in d["layers"]])
    check(d["layers"][0].get("alpha") == 0.5, "阴影半透明")
    # 头槽有物品但表里没有 -> 不画头（不会退回默认头发）
    n = L.layers(1, [25091, 27181, 12498])
    check([e["l"] for e in n["layers"]] == ["B10S", "M10000"] and all(not i["code"] for i in n["info"]),
          "表里没有的物品（25091 / 27181 / 12498）-> 只有阴影 + 身体，没有头发")
    # 武器：找一个 w? 码的 2xxx-7xxx 号物品
    w = next(i for i, (a, b) in L.table.items() if 2000 <= i < 8000 and b.startswith("wd"))
    r = L.layers(1, [0, 0, w])
    check(any(e["l"] == "M1WD01" for e in r["layers"]), "武器 id %d（%s）-> M1WD01 套 %s" % (w, L.table[w][1], [e["s"] for e in r["layers"] if e["l"] == "M1WD01"]))
    # 层在模型里不存在 -> 不画并标记 missing（wf 在 boy01 里没有 WF01 层）
    f = L.layers(1, [0, 27058, 0])
    check(not any(e["l"] == "M1WF01" for e in f["layers"]) and f["info"][1].get("missing"), "27058 的 wf 层在 boy01 里不存在 -> 不画 %s" % f["info"][1])
    # 叠放顺序：模型 3 是 衣、头、武器；模型 1 是 头、衣、武器
    p = next(i for i, (a, b) in L.table.items() if b.startswith("pa"))
    m1 = [e["l"] for e in L.layers(1, [0, p, w])["layers"]]
    m3 = [e["l"] for e in L.layers(3, [0, p, w])["layers"]]
    check(m1.index("M1MA01") < m1.index("M1PA01"), "模型 1：头发在衣服前面画 %s" % m1)
    check(m3.index("M3PA01") < m3.index("M3MA01"), "模型 3：衣服在头发前面画 %s" % m3)
    # ---- 兜底开关（默认关闭，非原版行为）
    items = gateway.Items(gateway.DEFAULT_ITEM_DIR)
    check(L.fallback is None and [e["l"] for e in L.layers(1, [0, 0, 12498])["layers"]] == ["B10S", "M10000", "M1MA01"],
          "默认关闭：12498（剑）不在表里 -> 不画武器")
    L.fallback = items.weapon_letter
    try:
        want = {11047: "M1WA01", 12130: "M1WD01", 13066: "M1WB01", 14056: "M1WC01", 15080: "M1WE01", 12498: "M1WD01"}
        got = {i: [e["l"] for e in L.layers(1, [0, 0, i])["layers"]][-1] for i in want}
        check(got == want, "开启：传家宝刀 / 剑 / 棍 / 枪 / 鞭 和 12498 -> WA / WD / WB / WC / WE / WD %s" % got)
        r = L.layers(1, [0, 0, 12498])
        check(r["info"][2].get("fallback") and r["layers"][-1] == {"l": "M1WD01", "s": 0}, "兜底的层标了 fallback，款式 01 调色板第 0 套 %s" % r["info"][2])
        check(items.weapon_letter(18072) is None and [e["l"] for e in L.layers(1, [0, 0, 18072])["layers"]][-1] == "M1MA01", "爪（type2=29）没有对应层 -> 不画")
        inn = L.layers(1, [0, 0, w])       # 表里有的武器仍然按表（不被兜底改写）
        check(not inn["info"][2].get("fallback") and any(e["l"] == "M1WD01" and e["s"] == 3 for e in inn["layers"]), "表里有的武器不受影响 %s" % inn["info"][2])
        h = L.layers(1, [25091, 27181, 0])
        check([e["l"] for e in h["layers"]] == ["B10S", "M10000"], "头盔 / 衣服没有兜底（只做武器）")
    finally:
        L.fallback = None
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
