"""快照一个角色：数据库里的相关行 + 原版服务端为它发的真实登录序列。

    python tools/snapshot_char.py --jyid 8617293 --password 8617293 --out data/fixtures/char-8617293.json

输出 JSON：
  rows   —— renwu / char_equip / jineng / kf / account(不含 password 列)，字段值都是字符串
  frames —— 真实登录序列的每个 S2C 帧（opcode、key、wide、payload 十六进制、线路字节）
测试用它检验 jyserver/state.py 从 rows 生成的序列是否与真实序列一致。
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

TABLES = ["renwu", "char_equip", "jineng", "kf", "account", "item"]


def read_rows(jyid: int) -> dict:
    rows = {}
    for t in TABLES:
        cols = [c for c, _ in lp.columns(t)]
        order = " order by id" if t == "item" else ""
        data = lp.sql(f"select * from {t} where jyid={jyid}{order}")
        entries = []
        for r in data:
            entries.append({c: v for c, v in zip(cols, r) if c != "password"})
        rows[t] = entries
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    lp.PASSWORD["value"] = args.password
    rows = read_rows(args.jyid)
    time.sleep(2.5)
    stream = lp.login_stream(args.host, args.port, args.jyid)
    if len(stream) < 15:
        print(f"login failed or short stream: {len(stream)} frames")
        return 1
    # 登录后服务端可能回写数据库（在线时间等），再读一次，对比是否一致
    rows_after = read_rows(args.jyid)
    changed = {t: [k for k in rows[t][0] if rows[t] and rows_after[t] and rows[t][0][k] != rows_after[t][0].get(k)] for t in TABLES if rows[t] and rows_after[t]}
    changed = {t: v for t, v in changed.items() if v}
    if changed:
        print("note: the original server wrote back to the DB during login:", changed)
    from jyserver.codec import encode_s2c  # noqa: E402

    frames = []
    for op, payload, wide in stream:
        key = 0x9F if (not frames and op == 0x01) else 0x7D
        frames.append({"opcode": op, "key": key, "wide": wide, "payload": payload.hex()})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"jyid": args.jyid, "rows": rows_after, "rows_before_login": rows if changed else None, "frames": frames}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"wrote {args.out}: {len(frames)} frames, 0x1E payload {len(stream[1][1])} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
