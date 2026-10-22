"""事件探针：登录原版（或新服务端）后依次发 C2S 0x6B（事件）等指令，记下所有回包和落库差异。

    python tools/event_probe.py --jyid 9999041 --password pw9999041 --step tp:8,100,100 --step ev:8:3 --step ev:8:10 --step relogin --step ev:8:11

--step 可重复，按顺序执行：
    tp:地图,x,y         发 0x5D 传送（原版不校验）
    ev:地图:事件id      发 0x6B，载荷 = 00000000 + 地图(LE16) + 事件id(LE16)（十进制）
    raw:OP:HEX          发任意 opcode 和载荷（OP、HEX 都是十六进制）
    relogin             断开 → 等落库 → 打印和上次快照的差异 → 重新登录
    sql:<语句>          断开 → 等落库 → 执行 SQL（语句里的 JYID 换成角色号，只对原版 MySQL）→ 重新登录。用来预置 online_time、jy_money 之类
--target mysql（默认，对原版）或 sqlite:<库路径>（对新服务端，读它的角色库）决定怎么取快照。
--json 把整个过程（每步的回包、每次快照差异）写成 JSON，供测试夹具用。
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from multi_probe import Client  # noqa: E402

TABLES = ("renwu", "item", "biaoji", "kf", "jineng", "char_equip")


def frame_text(f) -> str:
    txt = ""
    if f.opcode in (0x1A, 0x14):
        body = f.payload[1:] if f.opcode == 0x14 else f.payload
        txt = "  | " + body.decode("big5", "replace")
    return f"<- 0x{f.opcode:02x}{' W' if f.wide else ''} {f.payload.hex(' ')}{txt}"


def frames_of(raw):
    return [f for f in raw if not (f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"))]


def snapshot_mysql(jyid: int) -> dict:
    import layout_probe as lp

    snap: dict = {}
    for t in TABLES:
        cols = [r[0] for r in lp.sql(f"show columns from {t}")]
        order = " order by id" if "id" in cols else (" order by ID" if "ID" in cols else "")
        rows = lp.sql(f"select * from {t} where jyid={jyid}{order}")
        snap[t] = [dict(zip(cols, r)) for r in rows]
    return snap


def snapshot_sqlite(path: str, jyid: int) -> dict:
    from jyserver.store import CharacterStore

    st = CharacterStore(path)
    ch = st.get(jyid)
    rows = ch.rows if ch else {}
    st.close()
    return {t: [dict(r) for r in rows.get(t, [])] for t in TABLES}


STATE_COLS = ("jy_money", "fame_val", "exp_val", "combat_exp", "study_count", "evil_val", "kill_val", "pk_val", "school", "master")


def state_view(snap: dict) -> dict:
    """快照里和事件有关的部分（给测试夹具用）：标记、背包、几个数值列。"""
    renwu = (snap.get("renwu") or [{}])[0]
    return {
        "biaoji": sorted([int(r["biaoji"]), int(r["zhuangtai"])] for r in snap.get("biaoji", [])),
        "item": sorted([int(r["item_id"]), int(r["shuliang"]), int(r["state"])] for r in snap.get("item", [])),
        "renwu": {k: renwu.get(k) for k in STATE_COLS},
    }


def diff(a: dict, b: dict) -> dict:
    out: dict = {}
    for t in TABLES:
        ra, rb = a.get(t, []), b.get(t, [])
        if t == "renwu":
            da, db = (ra[0] if ra else {}), (rb[0] if rb else {})
            ch = {k: (da.get(k), db.get(k)) for k in sorted(set(da) | set(db)) if da.get(k) != db.get(k)}
            if ch:
                out[t] = ch
        elif t == "biaoji":
            key = lambda r: (int(r["biaoji"]), int(r["zhuangtai"]))  # noqa: E731
            la, lb = sorted(key(r) for r in ra), sorted(key(r) for r in rb)
            if la != lb:
                out[t] = {"before": la, "after": lb}
        else:
            drop = {"id", "ID"}
            norm = lambda rows: sorted(json.dumps({k: v for k, v in r.items() if k not in drop}, sort_keys=True, ensure_ascii=False) for r in rows)  # noqa: E731
            if norm(ra) != norm(rb):
                out[t] = {"before": [json.loads(x) for x in norm(ra)], "after": [json.loads(x) for x in norm(rb)]}
    return out


def create_over_network(host: str, port: int, jyid: int, password: str, name: str) -> None:
    """新账号流程：握手（密钥 0x34）→ 摇点 → 0x20 起名 → 长 0x19 确认属性（同 effects_probe create / tests/test_creation.py）。
    账号要事先存在（原版：手工插 account 行；新服务端：python -m jyserver.manage add-account）。"""
    from multi_probe import UNKNOWN_CONST

    c = Client("N", host, port, jyid, password)
    c.send(0x01, struct.pack("<II", jyid, UNKNOWN_CONST) + password.encode())
    c.drain(1.5)
    c.base = 0x34
    c.send(0x76, b"")
    c.drain(0.8)
    c.send(0x20, b"\x00" + name.encode("gbk"))
    c.drain(1.0)
    nm = name.encode("gbk")
    c.send(0x19, b"\x00" + struct.pack("<H", 3304) + bytes([len(nm)]) + nm + bytes([4]) + b"nick" + bytes([20] * 7) + bytes([1, 1, 5, 17]))
    frames = c.drain(3.0)
    print("created; login stream:", " ".join(f"{f.opcode:02x}" for f in frames))
    c.sock.close()


def apply_sqlite_update(path: str, jyid: int, stmt: str) -> None:
    """对新服务端的 sqlite 库做 `update renwu set a=b[,c=d] where jyid=JYID`（下线后改库的等价物）。"""
    from jyserver.store import CharacterStore

    m = re.fullmatch(r"update renwu set (.+) where jyid=JYID", stmt)
    if not m:
        raise SystemExit(f"sqlite target only supports 'update renwu set … where jyid=JYID': {stmt}")
    st = CharacterStore(path)
    ch = st.get(jyid)
    for pair in m.group(1).split(","):
        k, _, v = pair.partition("=")
        ch.rows["renwu"][0][k.strip()] = v.strip()
    st.put(jyid, ch.password, ch.rows, ch.state)
    st.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password")
    ap.add_argument("--step", action="append", default=[])
    ap.add_argument("--wait", type=float, default=1.2)
    ap.add_argument("--target", default="mysql")
    ap.add_argument("--save-wait", type=float, default=4.0)
    ap.add_argument("--json")
    ap.add_argument("--create", metavar="NAME", help="先走新账号流程建角色（账号要事先存在），再执行 --step")
    args = ap.parse_args()
    if args.create:
        create_over_network(args.host, args.port, args.jyid, args.password or f"pw{args.jyid}", args.create)
        time.sleep(args.save_wait)

    def snap():
        return snapshot_mysql(args.jyid) if args.target == "mysql" else snapshot_sqlite(args.target.split(":", 1)[1], args.jyid)

    log: list = []
    base = snap()
    log.append({"step": "start", "state": state_view(base)})

    def login() -> Client | None:
        c = Client("A", args.host, args.port, args.jyid, args.password)
        if not c.login():
            print("login failed")
            return None
        print("login pos:", c.position())
        c.drain(0.3)
        return c

    c = login()
    if c is None:
        return 1
    for spec in args.step:
        kind, _, rest = spec.partition(":")
        if kind in ("relogin", "sql"):
            c.sock.close()
            time.sleep(args.save_wait)
            cur = snap()
            d = diff(base, cur)
            print(f"== {kind}; db diff vs last snapshot:", json.dumps(d, ensure_ascii=False)[:600])
            log.append({"step": spec, "db_diff": d, "state": state_view(cur)})
            if kind == "sql":  # 下线后改库，再上线（原版每次 0x19 重新读 renwu；新服务端读 sqlite）
                if args.target == "mysql":
                    import layout_probe as lp

                    lp.sql(rest.replace("JYID", str(args.jyid)), fetch=False)
                else:
                    apply_sqlite_update(args.target.split(":", 1)[1], args.jyid, rest)
                cur = snap()
            base = cur
            c = login()
            if c is None:
                return 1
            continue
        if kind == "tp":
            m, x, y = (int(v) for v in rest.split(","))
            op, payload = 0x5D, struct.pack("<HHH", m, x, y)
        elif kind == "ev":
            m, e = (int(v) for v in rest.split(":"))
            op, payload = 0x6B, bytes(4) + struct.pack("<HH", m, e)
        elif kind == "raw":
            o, _, h = rest.partition(":")
            op, payload = int(o, 16), bytes.fromhex(h.replace(" ", ""))
        else:
            raise SystemExit(f"bad step {spec}")
        c.send(op, payload)
        got = frames_of(c.drain(args.wait))
        print(f"== {spec}  (0x{op:02x} {payload.hex(' ')})")
        for f in got:
            print("   " + frame_text(f))
        log.append({"step": spec, "op": op, "payload": payload.hex(), "frames": [[f.opcode, f.payload.hex(), f.wide] for f in got]})
    c.sock.close()
    time.sleep(args.save_wait)
    cur = snap()
    d = diff(base, cur)
    print("== final db diff:", json.dumps(d, ensure_ascii=False))
    log.append({"step": "final", "db_diff": d, "state": state_view(cur)})
    if args.json:
        Path(args.json).write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
