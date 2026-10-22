"""比较两份 tools/event_probe.py --json 记录（通常是 原版 vs 新服务端）：逐步比回包，逐次下线比库里的状态。

    python tools/compare_event_logs.py tests/fixtures/events/scenario_a.orig.json new.json

tp 步骤的回包不比（0x08 最后一字节是随机数）。限时标记（类型 != 200）的 zhuangtai 允许原版比新实现小 0~2（原版会倒数，见 docs/事件引擎.md）。
有差异时打印并以退出码 1 结束。
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    a = json.load(open(sys.argv[1], encoding="utf-8"))
    b = json.load(open(sys.argv[2], encoding="utf-8"))
    bad = 0
    if len(a) != len(b):
        print(f"length differs: {len(a)} vs {len(b)}")
        bad += 1
    frames_checked = states_checked = 0
    for x, y in zip(a, b):
        if x["step"] != y["step"]:
            print("step mismatch:", x["step"], y["step"])
            bad += 1
            continue
        if "frames" in x and not x["step"].startswith("tp:"):
            frames_checked += 1
            if x["frames"] != y["frames"]:
                bad += 1
                print("FRAMES differ at", x["step"])
                for i in range(max(len(x["frames"]), len(y["frames"]))):
                    fa = x["frames"][i] if i < len(x["frames"]) else None
                    fb = y["frames"][i] if i < len(y["frames"]) else None
                    if fa != fb:
                        print("   orig:", fa)
                        print("   new :", fb)
        if "state" in x:
            states_checked += 1
            sa, sb = x["state"], y["state"]
            ba, bb = sa["biaoji"], sb["biaoji"]
            ok_markers = len(ba) == len(bb) and all(p[0] == q[0] and (p[1] == q[1] or (p[1] != 200 and 0 <= q[1] - p[1] <= 2)) for p, q in zip(ba, bb))
            if not ok_markers or sa["item"] != sb["item"] or sa["renwu"] != sb["renwu"]:
                bad += 1
                print("STATE differs after", x["step"])
                for k in ("biaoji", "item", "renwu"):
                    if sa[k] != sb[k]:
                        print("   ", k, "orig:", sa[k])
                        print("   ", k, "new :", sb[k])
    print(f"compared {frames_checked} step(s) of frames and {states_checked} state snapshot(s): {'ALL SAME' if not bad else str(bad) + ' difference(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
