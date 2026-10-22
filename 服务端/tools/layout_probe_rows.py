"""按「行」做差分：背包 item 表（一个角色多行）和武功 kf 表（一个角色多行，原本为空）。

    python tools/layout_probe_rows.py --dst 9999001 --out data/layout/rows.json

做法与 layout_probe.py 相同：只改一处，重新登录，对比整条登录序列。
  * item：改第 k 行(按 id 排序)的 item_id / state / shuliang，看第 k 个格子在包里的位置和宽度；
  * kf：插入一行 (kf_id, kf_lvl, kf_exp)，看多出来的字节；再插第二行、改字段。
结束后会还原/删除这些改动。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import layout_probe as lp  # noqa: E402


def stream(args):
    time.sleep(2.5)
    return lp.login_stream(args.host, args.port, args.dst)


def changes(base, got):
    if not got:
        return {"result": "no-stream"}
    d = lp.diff_streams(base, got)
    if d is None:
        return {
            "result": "structure-changed",
            "frame_lengths_before": [len(p) for _, p, _ in base],
            "frame_lengths_after": [len(p) for _, p, _ in got],
        }
    d = [(i, op, [x for x in offs if (i, x) not in lp.IGNORE and (i, x) != (10, 6)]) for i, op, offs in d]
    d = [t for t in d if t[2]]
    return {"changes": lp.describe_change(base, got, d)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dst", type=int, default=9999001)
    ap.add_argument("--src", type=int, default=8617293)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--out", default="data/layout/rows.json")
    args = ap.parse_args()
    lp.PASSWORD["value"] = str(args.src)

    base = stream(args)
    if not base:
        print("baseline failed")
        return 1
    out = {"baseline_stream": [(f"0x{op:02x}", len(p)) for op, p, _ in base], "item": {}, "kf": {}}

    # ---- item：第 0、1、2、58 行的各列
    ids = [int(r[0]) for r in lp.sql(f"select id from item where jyid={args.dst} order by id")]
    print(f"item rows for clone: {len(ids)}")
    orig = {int(r[0]): r[1:] for r in lp.sql(f"select id,item_id,state,shuliang from item where jyid={args.dst}")}
    for k in (0, 1, 2, 58):
        if k >= len(ids):
            continue
        rid = ids[k]
        for col, val, idx in (("item_id", 12345, 0), ("state", 7, 1), ("shuliang", 9, 2)):
            lp.sql(f"update item set {col}={val} where id={rid}", fetch=False)
            try:
                res = changes(base, stream(args))
            finally:
                lp.sql(f"update item set {col}={orig[rid][idx]} where id={rid}", fetch=False)
            out["item"][f"row{k}.{col}={val}"] = res
            tag = res.get("result") or ", ".join(f"f{c['frame']}@{c['offset']}+{c['width']}({c['old']}->{c['new']})" for c in res["changes"])
            print(f"item row{k:<3} {col:<9}={val:<6} -> {tag}", flush=True)

    # ---- kf：插入一行并观察
    lp.sql(f"delete from kf where jyid={args.dst}", fetch=False)
    try:
        for step, stmt in (
            ("insert(kf_id=777,lvl=5,exp=123456)", f"insert into kf (jyid,kf_id,kf_lvl,kf_exp) values ({args.dst},777,5,123456)"),
            ("add 2nd row(kf_id=888,lvl=6,exp=654321)", f"insert into kf (jyid,kf_id,kf_lvl,kf_exp) values ({args.dst},888,6,654321)"),
            ("change 1st lvl 5->9", f"update kf set kf_lvl=9 where jyid={args.dst} and kf_id=777"),
            ("change 1st exp 123456->222222", f"update kf set kf_exp=222222 where jyid={args.dst} and kf_id=777"),
        ):
            lp.sql(stmt, fetch=False)
            res = changes(base, stream(args))
            out["kf"][step] = res
            if "changes" in res:
                tag = ", ".join(f"f{c['frame']}@{c['offset']}+{c['width']}({c['old'][:30]}->{c['new'][:30]})" for c in res["changes"][:6])
            else:
                tag = f"{res['result']} before={res.get('frame_lengths_before', [])[:3]} after={res.get('frame_lengths_after', [])[:3]}"
            print(f"kf {step:<45} -> {tag}", flush=True)
    finally:
        lp.sql(f"delete from kf where jyid={args.dst}", fetch=False)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
