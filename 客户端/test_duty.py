#!/usr/bin/env python3
"""任务手册（MyDuty.dat）解析 + 事件引擎的条件 / 动作分类自测。  python test_duty.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dutydata  # noqa: E402
import evtengine  # noqa: E402

RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def main():
    cats = dutydata.load()
    names = [c["name"] for c in cats]
    check(names[:2] == ["主線任務", "江湖任務"] and len(cats) == 12, "分类：主線任務 / 江湖任務 + 10 个门派（%s）" % names)
    main_ = cats[0]["entries"]
    check(len(main_) == 7 and main_[0]["title"] == "初見郭嘯天、楊鐵心" and main_[0]["level"] == "不限等級" and main_[0]["desc"].startswith("初識郭楊二人"), "主线 7 条，标题 / 等级 / 说明拆对")
    check("回頂端" not in "".join(e["desc"] for c in cats for e in c["entries"]), "版面占位「回頂端」被丢掉")
    check(main_[1]["desc"].endswith("計策。") and len(main_[1]["desc"]) > 34, "跨两个槽的长说明被接起来（主线第 2 条 %d 字，Big5 超过一个槽的 68 字节）" % len(main_[1]["desc"]))
    side = cats[1]["entries"]
    check(len(side) == 114 and side[0]["kind"] == "side" and side[0]["level"] == "1~5 級", "江湖任务 114 条，◎ = 支线，带等级范围")
    check(all(c["entries"][0]["kind"] == "job" for c in cats[2:]), "门派的打工任务（N.標題：說明）")
    # 引擎：原版条件分发里恒成立的类型、客户端不做事的动作
    st = evtengine.PlayerState([], {})
    ok = all(evtengine.holds({"type": t}, st) == (True, False) for t in evtengine.ALWAYS_TRUE_CONDS)
    check(ok, "恒成立的条件类型不再算「猜的」（%d 种）" % len(evtengine.ALWAYS_TRUE_CONDS))
    check(evtengine.holds({"type": 5}, st) == (True, True), "还没解的条件类型（5）仍按成立处理并记为「猜的」")
    check({4, 0x0D, 0x11, 0x15, 0x17} <= evtengine.NOOP_ACTIONS and 1 not in evtengine.NOOP_ACTIONS and 0x13 not in evtengine.NOOP_ACTIONS, "空操作动作集合不含文本 / 界面类动作")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
