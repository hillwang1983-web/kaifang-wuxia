"""@文字指令对照：同一个起始状态、同一串指令，对原版(6731)和新服务端(6732)各跑一遍，比回包和下线后的库状态。

    python tools/cmd_compare.py

场景写在 SCENARIOS 里：setup 里的 renwu / account 字段会同时写进 MySQL 和 SQLite（并先把背包 / 标记清成同样的）。
8617293 号的原始状态用完会还原成 data/fixtures/char-8617293.json 的样子，所以跑之前请确认原版没有别人在线。
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
JY = 8617293
WATCH = 1234567
CHECK = {"renwu": ["nickname", "school", "master", "school_skill_lv", "school_skill_exp", "jy_money", "map", "x", "y"], "account": ["shangchengdianshu"]}

SCENARIOS = {
    "status-and-simple": dict(setup={}, cmds=["where", "tw\x00", "tw\x01", "cxwg", "bj\x00", "sqsq", "bpsm", "se 100", "se -100", "se 5000", "se 0", "scb 0", "scb abc", "scb -5", "scb 1001", "cxg\x88", "cxg\x89", "cxg\x87"]),
    "cpw": dict(setup={}, cmds=["cpw"]),
    "kale": dict(setup={}, cmds=["kale"]),
    "wp-gm": dict(setup={"account": {"gm_lvl": 1}}, cmds=["wp 28005", "wp 31011", "wp 99999", "wp 1100", "wp 1100a", "wp 011005", "WP 11005"]),
    "wp-nongm": dict(setup={"account": {"gm_lvl": 0}}, cmds=["wp 28005"]),
    "scb": dict(setup={"renwu": {"jy_money": 350000}, "account": {"shangchengdianshu": 5000}}, cmds=["scb 1", "scb 2", "scb 1", "scb 1", "scb 0"]),
    "mp-ok": dict(setup={"account": {"shangchengdianshu": 20000}}, cmds=["mp 3"]),
    "mp-poor": dict(setup={"account": {"shangchengdianshu": 9998}}, cmds=["mp 2", "mp", "mp x"]),
    "mp-edge": dict(setup={"account": {"shangchengdianshu": 9999}, "renwu": {"school": 13, "master": 5}}, cmds=["mp 0"]),
    "bpsm-school": dict(setup={"renwu": {"school": 12, "school_skill_lv": 7, "school_skill_exp": 555, "master": 333}}, cmds=["bpsm"]),
    "nick": dict(setup={}, cmds=[(0x13, "616263"), (0x13, "c4e3bac3"), (0x13, "00"), (0x13, ""), (0x13, "61" * 36), (0x13, "61622063")]),
    "nick-kf": dict(setup={"kf": 25}, cmds=[(0x13, "61"), (0x13, "a4a4a4e5")]),
    "password": dict(setup={}, cmds=[(0x98, "0d0738363137323933"), (0x98, "0d0738363137323934"), (0x98, "0d0338363137323933"), (0x98, "0d00"), (0x98, "0f0102030405"), (0x98, "0f01020304050607"), (0x98, "0e0102030405")]),
    "bpsm-none": dict(setup={"renwu": {"school": 0, "school_skill_lv": 7, "school_skill_exp": 555, "master": 333}}, cmds=["bpsm"]),
}


def mysql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


def sqlite_edit(fn) -> None:
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    row = c.execute("select rows from characters where jyid=?", (JY,)).fetchone()
    d = json.loads(row[0])
    fn(d)
    c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), JY))
    c.commit()
    c.close()


def sqlite_get() -> dict:
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
    c.close()
    return d


BASE = {"renwu": {"nickname": "'123'", "school": 0, "master": 0, "school_skill_lv": 0, "school_skill_exp": 0, "jy_money": 100000, "map": 2200, "x": 510, "y": 410}, "account": {"shangchengdianshu": 0, "gm_lvl": 0}}
BAG = [(28290, 1), (40145, 1), (58182, 10), (26028, 1), (27058, 1), (11047, 1), (12130, 1), (48631, 1), (48022, 1), (13066, 1), (14056, 1), (15080, 1), (18072, 1)]


def apply_setup(setup: dict) -> None:
    vals = {t: {**BASE[t], **setup.get(t, {})} for t in BASE}
    mysql(f"delete from kf where jyid={JY}")
    if "kf" in setup:
        mysql(f"insert into kf (jyid,kf_id,kf_lvl,kf_exp) values ({JY},3860,{setup['kf']},0)")
    for t, kv in vals.items():
        sets = ",".join(f"{k}={v}" for k, v in kv.items())
        mysql(f"update {t} set {sets} where jyid={JY}")
    # 背包：把非空格子清成和基线一样（只改数量，不增删行；原版重启之前它用内存里的背包）
    def edit(d):
        for t, kv in vals.items():
            d[t][0].update({k: str(v).strip("'") for k, v in kv.items()})
        d["kf"] = [{"jyid": str(JY), "kf_id": "3860", "kf_lvl": str(setup["kf"]), "kf_exp": "0"}] if "kf" in setup else []
    sqlite_edit(edit)


def run(port: int, cmds: list[str]) -> list[str]:
    time.sleep(3.5)
    c = Client("A", "127.0.0.1", port, JY, None)
    if not c.login():
        return ["login failed"]
    c.drain(0.5)
    out = []
    for cmd in cmds:
        if isinstance(cmd, tuple):  # (操作码, 十六进制载荷)
            c.send(cmd[0], bytes.fromhex(cmd[1]))
            out.append(f"== op 0x{cmd[0]:02x} {cmd[1]}")
        else:
            c.send(0xC7, b"\x04\x40" + cmd.encode("latin1"))
            out.append(f"== @{cmd!r}")
        for f in c.drain(1.2):
            if f.opcode == 0x33 or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            p = f.payload
            if f.opcode == 0x08:
                p = p[:-1] + b"?"  # 最后一字节随机
            out.append(f"  <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {p.hex(' ')}")
        if c.sock.fileno() == -1:
            break
    try:
        c.sock.close()
    except OSError:
        pass
    return out


def state_after(port: int) -> list[str]:
    time.sleep(4)
    if port == 6731:
        r = {}
        for t, cols in CHECK.items():
            vals = mysql(f"select {','.join(cols)} from {t} where jyid={JY}").split("\t")
            r.update({f"{t}.{k}": v for k, v in zip(cols, vals)})
        items = mysql(f"select item_id,shuliang from item where jyid={JY} and item_id<>0 order by item_id").splitlines()
        marks = [m for m in mysql(f"select biaoji from biaoji where jyid={JY} order by biaoji").splitlines() if m != "0"]
    else:
        d = sqlite_get()
        r = {}
        for t, cols in CHECK.items():
            r.update({f"{t}.{k}": str(d[t][0].get(k)) for k in cols})
        agg: dict[str, int] = {}
        for it in d.get("item", []):
            if it["item_id"] != "0":
                agg[it["item_id"]] = agg.get(it["item_id"], 0) + int(it["shuliang"])
        items = [f"{k}\t{v}" for k, v in sorted(agg.items(), key=lambda kv: int(kv[0]))]
        marks = sorted(str(m["biaoji"]) for m in d.get("biaoji", []))
    return [f"{k}={v}" for k, v in sorted(r.items())] + ["items:" + ";".join(i.replace("\t", "x") for i in items), "markers:" + ",".join(sorted(marks, key=int))]


def main() -> int:
    only = sys.argv[1:] or list(SCENARIOS)
    bad = 0
    for name in only:
        sc = SCENARIOS[name]
        results = {}
        for port in (6731, 6732):
            apply_setup(sc["setup"])
            if port == 6731:
                # 原版的背包在它内存里；这里只比较「命令造成的变化」，所以先记下开始时的状态
                pass
            before = state_after(port)
            out = run(port, sc["cmds"])
            after = state_after(port)
            results[port] = (out, [l for l in after if l not in before] if False else after)
        a, b = results[6731], results[6732]
        same_frames = a[0] == b[0]
        same_state = a[1] == b[1]
        print(f"### {name}: frames {'identical' if same_frames else 'DIFF'} ({len(a[0])} lines); state {'identical' if same_state else 'DIFF'}")
        if not same_frames:
            for l in difflib_lines(a[0], b[0]):
                print("   ", l)
        if not same_state:
            for l in difflib_lines(a[1], b[1]):
                print("   ", l)
        bad += (not same_frames) + (not same_state)
    return 1 if bad else 0


def difflib_lines(a, b):
    import difflib

    return [l for l in difflib.unified_diff(a, b, "original", "new", lineterm="", n=1)]


if __name__ == "__main__":
    raise SystemExit(main())
