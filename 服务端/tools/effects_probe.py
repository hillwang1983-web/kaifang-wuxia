"""药品效果探针：建一个全新角色，往它背包里塞一批药，逐个使用，看每次用完 renwu 表和背包数量变了什么。

    python tools/effects_probe.py create --jyid 9999021 --name fx9021 --columns 毒,酒醉,...
    （手工重启原版服务端，让它把背包读进内存）
    python tools/effects_probe.py use --jyid 9999021 --columns 毒,酒醉,...        # 或 --items 28320,28321

create：手工插一行 account → 登录（新账号握手，密钥 0x34）→ 摇点 → 0x20 起名 → 长 0x19 进游戏 → 断开，
        然后往 item 表插药（原版只在服务端启动时把背包读进内存，所以要重启）。
use   ：登录（普通握手）→ 0x19 → 逐个 0x0B；每次用完读一遍 MySQL 里的 renwu 行，打印变了的列和背包数量。
会改原版数据库；跑完用 layout_probe.py cleanup --dst <jyid> 清理。
"""

from __future__ import annotations

import argparse
import csv
import io
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_probe as lp  # noqa: E402
from multi_probe import UNKNOWN_CONST, Client  # noqa: E402

DATA = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data")


def medicine_table():
    text = (DATA / "药品.csv").read_bytes().decode("gbk", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    hdr = rows[0]
    eff = {}
    for r in rows[1:]:
        if r and r[0].isdigit():
            eff[int(r[0])] = {h: int(v) for h, v in zip(hdr[5:], r[5:]) if v.lstrip("-").isdigit() and int(v) != 0}
    return eff, {int(r[0]): r[1] for r in rows[1:] if r and r[0].isdigit()}


def pick_for_columns(columns):
    eff, _ = medicine_table()
    chosen = []
    for col in columns:
        cands = sorted((len(e), i) for i, e in eff.items() if col in e)
        if cands:
            chosen.append(cands[0][1])  # 效果列最少的那个
    return chosen


def renwu_row(jyid):
    cols = [c for c, _ in lp.columns("renwu")]
    r = lp.sql(f"select * from renwu where jyid={jyid}")
    return dict(zip(cols, r[0])) if r else {}


def item_qty(jyid):
    return {int(a): int(b) for a, b in lp.sql(f"select item_id, sum(shuliang) from item where jyid={jyid} and item_id>0 group by item_id")}


def choose_items(args):
    return [int(x) for x in args.items.split(",") if x] + pick_for_columns([c for c in args.columns.split(",") if c])


def create(args) -> int:
    items = choose_items(args)
    pw = f"pw{args.jyid}"
    hexpw = " ".join(f"{b:02x}" for b in pw.encode())
    lp.sql(f"insert into account (jyid,password,state,gm_lvl,shangchengdianshu,reg_ip) values ({args.jyid},'{hexpw}',1,0,0,'1')", fetch=False)
    c = Client("N", "127.0.0.1", 6731, args.jyid, pw)
    c.send(0x01, struct.pack("<II", args.jyid, UNKNOWN_CONST) + pw.encode())
    c.drain(1.5)
    c.base = 0x34
    c.send(0x76, b"")
    c.drain(0.8)
    c.send(0x20, b"\x00" + args.name.encode("gbk"))
    c.drain(1.0)
    nm = args.name.encode("gbk")
    c.send(0x19, b"\x00" + struct.pack("<H", 3304) + bytes([len(nm)]) + nm + bytes([4]) + b"nick" + bytes([20] * 7) + bytes([1, 1, 5, 17]))
    frames = c.drain(3.0)
    print("login stream:", " ".join(f"{f.opcode:02x}" for f in frames))
    c.sock.close()
    for it in items:
        lp.sql(f"insert into item (jyid,item_id,state,shuliang) values ({args.jyid},{it},200,{args.qty})", fetch=False)
    print("items inserted:", items)
    print("现在请重启原版服务端，再跑 use。")
    return 0


def use(args) -> int:
    items = choose_items(args)
    eff, names = medicine_table()
    pw = f"pw{args.jyid}"
    c = Client("N", "127.0.0.1", 6731, args.jyid, pw)
    if not c.login():
        print("login failed")
        return 1
    inv = next((f for f in c.login_frames if f.opcode == 0x1E), None)
    print("inventory records in 0x1E:", int.from_bytes(inv.payload[4:6], "little") if inv else None)
    c.drain(0.3)
    before = base_row = renwu_row(args.jyid)
    qty0 = item_qty(args.jyid)
    print("stock:", {i: qty0.get(i) for i in items})
    for it in items:
        for k in range(args.repeat):
            c.send(0x0B, struct.pack("<I", it))
            got = c.drain(0.9)
            time.sleep(0.4)
            after = renwu_row(args.jyid)
            diff = {k2: (before.get(k2), v) for k2, v in after.items() if before.get(k2) != v}
            q = item_qty(args.jyid)
            frames_txt = " | ".join(f"{f.opcode:02x}{' W' if f.wide else ''}:{f.payload.hex(' ')}" for f in got)
            print(f"== {it} {names.get(it, '?')} {eff.get(it)} #{k + 1}  qty {qty0.get(it)}->{q.get(it)}")
            print(f"   frames: {frames_txt or '(none)'}")
            print(f"   renwu changed: {diff or '-'}")
            before, qty0 = after, q
    print("rekeys followed:", c.rekeys)
    c.sock.close()
    time.sleep(4)  # 下线时原版才把内存里的角色和背包存回库
    final = renwu_row(args.jyid)
    print("after logout, renwu changed vs start:", {k: (base_row.get(k), v) for k, v in final.items() if base_row.get(k) != v} or "-")
    print("after logout, stock:", {i: item_qty(args.jyid).get(i) for i in items})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("create", "use"))
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--name", default="fxtest")
    ap.add_argument("--items", default="")
    ap.add_argument("--columns", default="", help="效果列名，逗号分隔；每列自动挑一个效果最少的药")
    ap.add_argument("--qty", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=1, help="每个药连用几次")
    args = ap.parse_args()
    return create(args) if args.cmd == "create" else use(args)


if __name__ == "__main__":
    raise SystemExit(main())
