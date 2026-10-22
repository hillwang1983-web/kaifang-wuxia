#!/usr/bin/env python3
"""事件条件的新语义（逆向 0x9223f3 / 0x9224d6 / 0x7794b4 / 0x781068 / 0x922abf / 0x922bf6）：
属性 / 武功 / 标记各自按模式（≥ < == ≠）比较，类型 1–4 = 全部成立，0xB–0xE = 任一成立；
条件里的"物品"表其实是武功（号 + 等级）；0x1F / 0x20 的已解子类型。只用标准库。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import evtengine as E  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def main():
    F = {"fame_val": 50, "school": 26}
    st = E.PlayerState([7001, 7001, 7002], F, kf={1506: 30, 2308: 1})
    h = lambda t, **kw: E.holds(dict({"type": t, "marks": [], "items": [], "attrs": []}, **kw), st)

    # 标记 / 物品：个数比较
    check(h(1, marks=[(7001, 2)]) == (True, False), "类型 1：有 2 个 7001")
    check(h(1, marks=[(7001, 3)])[0] is False, "类型 1：7001 只有 2 个，要 3 个 → 不成立")
    check(h(2, marks=[(7003, 1)])[0] is True and h(2, marks=[(7001, 1)])[0] is False, "类型 2：没有 / 个数 < n")
    check(h(3, marks=[(7001, 2)])[0] is True and h(3, marks=[(7001, 1)])[0] is False, "类型 3：个数 == n")
    check(h(4, marks=[(7001, 1)])[0] is True and h(4, marks=[(7001, 2)])[0] is False, "类型 4：个数 != n")

    # 武功（条件里的「物品」表）：找到就比等级，找不到 = 模式 1 / 3 成立、0 / 2 不成立
    check(h(1, items=[(1506, 30, 0)])[0] is True and h(1, items=[(1506, 31, 0)])[0] is False, "类型 1：武功 1506 等级 ≥ 30")
    check(h(1, items=[(9999, 1, 0)])[0] is False, "类型 1：没学过的武功 → 不成立")
    check(h(2, items=[(1506, 31, 0)])[0] is True and h(2, items=[(1506, 30, 0)])[0] is False and h(2, items=[(9999, 1, 0)])[0] is True,
          "类型 2：武功等级 < n；没学过 → 成立")
    check(h(3, items=[(2308, 1, 0)])[0] is True and h(3, items=[(9999, 1, 0)])[0] is False, "类型 3：武功等级 == n；没学过 → 不成立")
    check(h(4, items=[(9999, 1, 0)])[0] is True, "类型 4：没学过的武功 ≠ → 成立")
    check(h(1, marks=[(7001, 1)], items=[(1506, 99, 0)])[0] is False, "类型 1：标记满足但武功不满足 → 整体不成立（全部成立）")

    # 属性：模式比较
    check(h(1, attrs=[(61, 50)])[0] is True and h(1, attrs=[(61, 51)])[0] is False, "类型 1：属性 ≥")
    check(h(2, attrs=[(61, 51)])[0] is True and h(2, attrs=[(61, 50)])[0] is False, "类型 2：属性 <")
    check(h(3, attrs=[(65, 26)])[0] is True and h(4, attrs=[(65, 26)])[0] is False, "类型 3 / 4：属性 == / ≠")
    check(h(1, attrs=[(999, 1)]) == (True, True), "没有数据的属性号 → 按成立、记「猜的」")

    # 0xB–0xE：任一成立
    check(h(0xB, marks=[(7003, 1), (7001, 1)])[0] is True, "类型 0xB：任一标记有 → 成立")
    check(h(0xB, marks=[(7003, 1), (7004, 1)])[0] is False, "类型 0xB：都没有 → 不成立")
    check(h(0xC, marks=[(7003, 1), (7001, 1)])[0] is True, "类型 0xC：任一「没有」成立（7003）")
    check(h(0xB)[0] is False and h(1)[0] is True, "空列表：0xB 不成立（bl 先置 0），1 成立（先置 1）")
    check(h(0xB, items=[(1506, 30, 0)], marks=[(7004, 1)])[0] is True, "类型 0xB：武功和标记混在一起，任一成立")

    # 0x1F
    c31 = lambda *v: E.holds({"type": 0x1F, "v": list(v)}, st)
    check(c31(1, 1, 1000) == (True, False) and c31(9, 2, 3) == (True, False) and c31(11, 1, 0) == (True, False), "0x1F：v0 = 1 / 9 / 11 … 直接成立，不算猜")
    check(c31(15, 1, 1) == (True, True), "0x1F：v0 = 15（客户端内存里 18 个标志字节）仍记「猜的」")

    # 0x20
    c32 = lambda *v: E.holds({"type": 0x20, "v": list(v)}, st)
    check(c32(3, 1, 25, -1, 0) == (True, False) and c32(2, 1, 1, 0, 0) == (True, False), "0x20：v0 = 2 / 3 直接成立")
    check(c32(4, 1, 20004, 1, 31) == (False, False), "0x20 / 4：没有这个状态（数值 0），要求 ≥ 31 → 不成立")
    check(c32(4, 1, 20004, 2, 41) == (True, False), "0x20 / 4：数值 0 < 41 → 成立")
    check(c32(4, 1, 19999, 2, 41)[0] is False and c32(4, 1, 20011, 2, 41)[0] is False, "0x20 / 4：编码 < 20000 或槽号 > 10 → 不成立")
    st2 = E.PlayerState([], F, status={(5, 0): 35, (1, 1): 7})
    c = lambda *v: E.holds({"type": 0x20, "v": list(v)}, st2)
    check(c(4, 1, 20004, 1, 31)[0] is True and c(4, 1, 20004, 1, 36)[0] is False, "0x20 / 4：编码 20004 = 槽 5 类 0；有状态 35 时按 ≥ 比")
    check(c(4, 1, 21000, 3, 7)[0] is True and c(4, 1, 21000, 4, 7)[0] is False, "0x20 / 4：编码 21000 = 槽 1 类 1（210 → 类 1）；== / ≠")
    # 条件 6：游戏日历范围（时钟 T 每格 75 秒；一天 96 格，一月 30 天，一年 360 天）
    F0 = {}
    cal = lambda t, a, b: E.holds({"type": 6, "a": bytes(a), "b": bytes(b)}, E.PlayerState([], F0, clock=t))
    check(E.PlayerState([], F0, clock=34560 * 3 + 2880 * 11 + 96 * 4 + 8 * 5 + 6).calendar() == (3, 11, 4, 5, 6), "日历：T → 年 3、月 11（0 起）、日 4（0 起）、时辰 5、刻 6")
    check(cal(None, [255] * 5, [255] * 5) == (True, True), "条件 6：没校过时 → 成立，记「猜的」")
    # 「初一開放入寺」ffff 01 00 00 ~ ffff 01 0b 07：每月 1 日（日 0 起 = 0）全天
    day1, day2 = 2880 * 5 + 96 * 0 + 17, 2880 * 5 + 96 * 1 + 17
    check(cal(day1, [255, 255, 1, 0, 0], [255, 255, 1, 11, 7]) == (True, False) and cal(day2, [255, 255, 1, 0, 0], [255, 255, 1, 11, 7])[0] is False,
          "条件 6：初一（日 = 1）全天开放，初二不开")
    # 时辰范围：ffffff 06 00 ~ ffffff 06 07 = 时辰 6 的 8 刻
    check(cal(96 * 7 + 6 * 8 + 3, [255, 255, 255, 6, 0], [255, 255, 255, 6, 7])[0] is True and cal(96 * 7 + 5 * 8 + 3, [255, 255, 255, 6, 0], [255, 255, 255, 6, 7])[0] is False,
          "条件 6：时辰 6 内成立，时辰 5 不成立")
    # 月日范围：12 月 1 日 ~ 12 月 30 日
    check(cal(2880 * 11 + 96 * 29, [255, 12, 1, 0, 0], [255, 12, 30, 11, 7])[0] is True and cal(2880 * 10, [255, 12, 1, 0, 0], [255, 12, 30, 11, 7])[0] is False,
          "条件 6：12 月范围内成立，11 月不成立")

    # 用真实事件数据：2400 的「初一開放入寺 / 十五開放入寺」节点随游戏日历开关
    pic = os.path.normpath(os.path.join(HERE, "..", "share", "pic"))
    try:
        import evtdata
        rec = evtdata.EventIndex(pic).get("2400")
    except Exception:
        rec = None
    if rec:
        names = [n["name"] for n in rec["nodes"]]
        i1, i15 = names.index("初一開放入寺"), names.index("十五開放入寺")

        def open_at(t):
            e = E.Engine(rec, {}, E.PlayerState([], F0, clock=t))
            return e.node_ok(i1), e.node_ok(i15)
        d = lambda day, h=0: 2880 * 3 + 96 * (day - 1) + h * 8
        check(open_at(d(1)) == (True, False) and open_at(d(15, 5)) == (False, True) and open_at(d(2)) == (False, False),
              "真实数据（2400）：初一 / 十五开放入寺随日历开关；初二都关")
        e = E.Engine(rec, {}, E.PlayerState([], F0, clock=None))
        check(e.node_ok(i1) and e.guessed, "没校过时钟：节点按成立走并记「猜的」")
    else:
        print("SKIP 没有 EvtMrg 数据")

    # kf 行：原版 0x1E 里每行 9 字节（2026-10-20 对原版实测：4 条 kf 紧挨着；16 × 9 = 144 正好填满 kf 区）
    import parse_0x1e
    raw = bytes.fromhex("00 0a 00 64 00 00 00 e8 03  00 5a 00 40 e2 01 00 4e 04  00 50 00 00 00 00 00 50 04  00 64 00 00 00 00 00 59 04".replace("  ", " "))
    rows = [raw[i * parse_0x1e.KF_ROW:(i + 1) * parse_0x1e.KF_ROW] for i in range(4)]
    dec = [(int.from_bytes(r[7:9], "little"), r[1], int.from_bytes(r[3:6], "little")) for r in rows]
    check(parse_0x1e.KF_ROW == 9 and dec == [(1000, 10, 100), (1102, 90, 123456), (1104, 80, 0), (1113, 100, 0)], "kf 行 9 字节一条：原版实测的 4 条解出 (1000 Lv10) (1102 Lv90) (1104 Lv80) (1113 Lv100)")

    # 动作 0x13 的二级分发：只"跳到下一个动作"的功能号静默、认得出主题的给名字、其它仍是 todo
    def run_ui(v0):
        rec = {"nodes": [{"id": 1, "name": "n", "main": True, "A": [], "M": [0]}], "conds": [], "acts": [{"kind": 0x13, "v": [v0]}]}
        return list(E.Engine(rec, {}, E.PlayerState([], {})).run(0))
    check(run_ui(71) == [] and run_ui(184) == [], "0x13 功能号 71 / 184（原版只跳下一个动作）→ 静默")
    check(run_ui(34) and "獄中玩家名單" in run_ui(34)[0]["text"], "0x13 功能号 34 → 提示「獄中玩家名單」")
    check(run_ui(198) and run_ui(198)[0]["t"] == "todo", "0x13 功能号 198（没解）仍是 todo")
    check(len(E.NOOP_UI) == 70 and not (E.NOOP_UI & set(E.UI_NAMES)), "NOOP_UI 70 项，和有名字的不重叠")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
