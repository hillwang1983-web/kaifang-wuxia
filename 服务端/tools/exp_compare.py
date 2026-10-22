"""经验类事件语句对照：把一批「结果」语句临时写进原版 data/事件.csv（地图 8、事件id 从 50001 起），
重启原版，再对原版（6731）和一个新起的新服务端（临时端口、临时角色库副本）各跑一遍，比 8617293 收到的帧和下线后的库。

    python tools/exp_compare.py exp-gate [场景 ...]       # 对原版和新服务端各跑，比较
    python tools/exp_compare.py --original exp-gate       # 只跑原版，打印结果（摸行为用）
    python tools/exp_compare.py --list
    python tools/exp_compare.py --cleanup                 # 还原 事件.csv（先备份在 tools/_event_csv.bak）

场景定义在 SCENARIOS：init = 先写进 renwu / jineng 表的列，stmts = 依次触发的事件结果语句。
**跑完必须**：python tools/exp_compare.py --cleanup；python tools/restore_fixture.py 8617293 1234567；重启原版；python -m jyserver.importer。
"""

from __future__ import annotations

import difflib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402
from kf_compare import JY, MYSQL, le, mysql, restart_original, tp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ORIG_DIR = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端")
CSV = ORIG_DIR / "data" / "事件.csv"
BAK = Path(__file__).resolve().parent / "_event_csv.bak"
MAP = 8
FIRST_ID = 50001
SHOW_COLS = ("school", "master", "school_skill_lv", "school_skill_exp", "kill_val", "pk_val", "diet_val", "water_val", "fame_val", "exp_val", "evil_val", "study_count", "combat_exp", "jy_money")
BASIC = ("daofa", "qiangfa", "jianfa", "bianfa", "gunfa", "neigong", "cishu", "shenfa", "dushu", "yishu", "zhenfa", "boji", "shanduo", "chaizhao", "anqi", "dushushizi", "jiaoyi")
JN = ("famu", "gongjiang", "zhibu", "caifeng", "lieren", "caikuang", "datie", "zhujian", "nongfu", "buyu", "chushi")


def jexp(c: str) -> str:
    return "lirenexp" if c == "lieren" else c + "exp"  # 原版表里的笔误：猎人经验列叫 lirenexp


def basics(v: int = 0, e: int = 0):
    return {**{c: v for c in BASIC}, **{c + "exp": e for c in BASIC}}


def jn(v: int = 0, e: int = 0):
    return {**{c: v for c in JN}, **{jexp(c): e for c in JN}}


S = lambda lv, ex, **kw: dict(school_skill_lv=lv, school_skill_exp=ex, **kw)  # noqa: E731

SCENARIOS: dict[str, dict] = {}


def sc(name: str, stmts, **init):
    SCENARIOS[name] = dict(stmts=stmts, **init)


# ---- 摸行为用的场景在 tools/exp_scenarios.py 里扩充
try:
    from exp_scenarios import register  # noqa: E402

    register(sc, S, basics, jn)
except ImportError:
    pass


def patch_csv(stmts_all: list[str]) -> dict[str, int]:
    if not BAK.exists():
        shutil.copyfile(CSV, BAK)
    base = BAK.read_bytes()
    ids: dict[str, int] = {}
    add = b""
    for s in stmts_all:
        if s not in ids:
            ids[s] = FIRST_ID + len(ids)
            add += f"{MAP},,{ids[s]},,0, , ,".encode("gbk") + s.encode("gbk") + b",1\r\n"
    CSV.write_bytes(base + add)
    return ids


def cleanup() -> None:
    if BAK.exists():
        shutil.copyfile(BAK, CSV)
        BAK.unlink()
        print("事件.csv 已还原")


def set_init(init: dict, sqlite_path: str | None) -> None:
    base = dict(str=30, crg=30, wint=30, luk=30, dex=30, agi=30, vit=30, jy_money=1000000, kill_val=0, pk_val=0, school=0, master=0, school_skill_lv=0, school_skill_exp=0, combat_exp=0, fame_val=0, exp_val=0, evil_val=2000, study_count=0, dangqianjing=210, diet_val=100, water_val=100, map=MAP)
    base.update(basics())
    renwu = {**base, **init.get("renwu", {})}
    skills = {**jn(), **init.get("jineng", {})}
    mysql("update renwu set " + ",".join(f"{k}={v}" for k, v in renwu.items()) + f" where jyid={JY}")
    mysql("update jineng set " + ",".join(f"{k}={v}" for k, v in skills.items()) + f" where jyid={JY}")
    mysql(f"delete from kf where jyid={JY}")
    mysql(f"delete from biaoji where jyid={JY}")
    kf = init.get("kf", [])
    if kf:
        mysql("insert into kf (jyid,kf_id,kf_lvl,kf_exp) values " + ",".join(f"({JY},{a},{b},{c})" for a, b, c in kf))
    if sqlite_path:
        c = sqlite3.connect(sqlite_path)
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        for k, v in renwu.items():
            d["renwu"][0][k] = str(v)
        for k, v in skills.items():
            d["jineng"][0][k] = str(v)
        d["kf"] = [{"jyid": str(JY), "kf_id": str(a), "kf_lvl": str(b), "kf_exp": str(x)} for a, b, x in kf]
        d["biaoji"] = []
        c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), JY))
        c.commit()
        c.close()


def read_state(port: int, sqlite_path: str | None) -> list[str]:
    time.sleep(4)
    cols = list(SHOW_COLS) + list(BASIC) + [c + "exp" for c in BASIC]
    if port == 6731:
        vals = mysql(f"select {','.join(cols)} from renwu where jyid={JY}").split("\t")
        jv = mysql(f"select {','.join(k for c in JN for k in (c, jexp(c)))} from jineng where jyid={JY}").split("\t")
        ren = dict(zip(cols, vals))
        jin = dict(zip([k for c in JN for k in (c, jexp(c))], jv))
    else:
        c = sqlite3.connect(sqlite_path)
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        c.close()
        ren = {k: str(d["renwu"][0].get(k)) for k in cols}
        jin = {k: str(d["jineng"][0].get(k)) for c2 in JN for k in (c2, jexp(c2))}
    if port == 6731:
        kfrows = sorted(tuple(int(x) for x in l.split("\t")) for l in mysql(f"select kf_id,kf_lvl,kf_exp from kf where jyid={JY}").splitlines())
    else:
        c = sqlite3.connect(sqlite_path)
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        c.close()
        kfrows = sorted((int(r["kf_id"]), int(r["kf_lvl"]), int(r["kf_exp"])) for r in d.get("kf", []))
    out = ["kf: " + " ".join(f"{a}:{b}:{c}" for a, b, c in kfrows)]
    out += ["state: " + " ".join(f"{k}={ren[k]}" for k in SHOW_COLS)]
    nz = [f"{k}={ren[k]}" for k in cols[len(SHOW_COLS):] if ren[k] != "0"]
    out.append("basic: " + " ".join(nz))
    nz = [f"{k}={v}" for k, v in jin.items() if v != "0"]
    out.append("jineng: " + " ".join(nz))
    return out


def run(port: int, ids: list[int], names: list[str]) -> list[str]:
    time.sleep(3.0)
    a = Client("A", "127.0.0.1", port, JY, None)
    if not a.login():
        return ["login failed"]
    a.drain(1.0)
    out: list[str] = []

    def show(frames):
        for f in frames:
            if f.opcode in (0x33, 0x60, 0x05, 0x02, 0x82, 0x08) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            txt = ""
            if f.opcode in (0x14, 0x1A):
                txt = "  | " + (f.payload[1:] if f.opcode == 0x14 else f.payload[1:]).decode("big5", "replace")
            out.append(f"    <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {f.payload.hex(' ')}{txt}")

    for op, hx in [tp(MAP, 100, 100)]:
        a.send(op, bytes.fromhex(hx))
        a.drain(0.5)
    for i, n in zip(ids, names):
        out.append(f"== {n}")
        show(a.drain(0.05))
        a.send(0x6B, bytes.fromhex("00000000" + le(MAP) + le(i)))
        show(a.drain(0.7))
    a.sock.close()
    return out


def start_new(tmp_db: str, port: int):
    p = subprocess.Popen([sys.executable, "-m", "jyserver.server", "--host", "127.0.0.1", "--port", str(port), "--chars", tmp_db, "--tick", "0", "--autosave", "0"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    return p


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--list" in sys.argv:
        print("\n".join(SCENARIOS))
        return 0
    if "--cleanup" in sys.argv:
        cleanup()
        return 0
    only_original = "--original" in sys.argv
    names = args or list(SCENARIOS)
    stmts_all = [s for n in names for s in SCENARIOS[n]["stmts"]]
    ids = patch_csv(stmts_all)
    restart_original()
    tmp = tempfile.mkdtemp()
    tmp_db = str(Path(tmp) / "chars.sqlite")
    shutil.copyfile(ROOT / "data" / "chars.sqlite", tmp_db)
    proc = None if only_original else start_new(tmp_db, 6741)
    bad = 0
    try:
        for name in names:
            s = SCENARIOS[name]
            res = {}
            for port in (6731, 6741):
                if only_original and port == 6741:
                    continue
                set_init(s, tmp_db if port == 6741 else None)
                if port == 6741:
                    pass
                res[port] = run(port, [ids[x] for x in s["stmts"]], s["stmts"]) + read_state(port, tmp_db)
            if only_original:
                print(f"### {name} (original)")
                print("\n".join(res[6731]))
                continue
            same = res[6731] == res[6741]
            print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
            if not same:
                bad += 1
                for l in difflib.unified_diff(res[6731], res[6741], "original", "new", lineterm="", n=2):
                    print("   ", l[:240])
    finally:
        if proc:
            proc.terminate()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())




