"""生活技能 / 农夫对照：同一份人物状态、同一串指令，对原版(6731)和新服务端(6732)各跑一遍，比回包帧和下线后的库。

    python tools/life_compare.py [场景 ...]

产出物品、农夫的「另外的物品」是随机的：场景都选在产出固定的等级（伐木 ≤ 30、捕魚 / 採礦 ≤ 10），农夫收成里的 0x77 / 0x1A「另外的物品」帧不比（它们进背包 / 钱庄的物品也不比）。
跑完之后用 restore_fixture.py 还原，并重启原版。
"""

from __future__ import annotations

import difflib
import json
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from life_probe import farm, life, plant  # noqa: E402
from multi_probe import Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
JY = 8617293
BASE_RENWU = dict(dangqianjing=50, wint=33, map=2411, jy_money=100000)
BASE_JINENG = dict(famu=5, famuexp=0, buyu=5, buyuexp=0, caikuang=5, caikuangexp=0, nongfu=1, nongfuexp=0)
SEED = 44201

# (描述, 指令列表 [(opcode, payload, 等多久)])
W = lambda a, b, seq=1: (0x5A, life(seq, a, b), 0.0)  # noqa: E731


def rounds(b, n, gap=4.3):
    return [(0x5A, life(2 + i, 2, b), gap) for i in range(n)]


SCENARIOS = {
    "famu": dict(jineng=dict(famu=5), cmds=[(0x5A, life(1, 1, 1), 1.0)] + rounds(1, 5) + [(0x5A, life(2, 2, 1), 1.0), (0x5A, life(3, 2, 1), 5.0), (0x5A, life(99, 3, 1), 1.0)]),
    "buyu": dict(renwu=dict(wint=1), jineng=dict(buyu=5), cmds=[(0x5A, life(1, 1, 2), 1.0)] + rounds(2, 4) + [(0x5A, life(99, 3, 2), 1.0)]),
    "caikuang": dict(renwu=dict(wint=1), jineng=dict(caikuang=5), cmds=[(0x5A, life(1, 1, 3), 1.0)] + rounds(3, 4) + [(0x5A, life(99, 3, 3), 1.0)]),
    "famu-cap": dict(jineng=dict(famu=99, famuexp=9900), cmds=[(0x5A, life(1, 1, 1), 1.0)] + rounds(1, 3)),
    "jing": dict(renwu=dict(dangqianjing=3), jineng=dict(famu=5), cmds=[(0x5A, life(1, 1, 1), 1.0)] + rounds(1, 4, 1.0) + [(0x5A, life(0, 0, 0), 1.0)]),
    "shapes": dict(jineng=dict(famu=5), cmds=[(0x5A, b"", 0.5), (0x5A, life(1, 1, 1)[:5], 0.5), (0x5A, life(1, 1, 1)[:6], 1.0), (0x5A, life(2, 2, 9), 0.5), (0x5A, life(2, 7, 1), 0.5), (0x5A, life(2, 2, 1)[:6], 1.0)]),
    "farm": dict(jineng=dict(nongfu=1), seeds=SEED, cmds=sum(([(0x5B, plant(3, SEED), 0.8), (0x5C, farm(10 + 3 * i, 3, 1), 0.8), (0x5C, farm(11 + 3 * i, 3, 2), 4.3)] for i in range(5)), [])
                 + [(0x5C, farm(50, 3, 1), 0.8), (0x5C, farm(51, 3, 2), 4.3), (0x5B, plant(3, 55001), 0.8), (0x5B, plant(3, 55001) + b"\x00", 0.8), (0x5B, plant(3, SEED)[:2], 0.8), (0x5C, farm(60, 3, 2)[:5], 0.8)]),
    "zixiu": dict(renwu=dict(map=3511), kf=[(1000, 10, 0)], cmds=[(0x5B, plant(1, SEED), 1.0), (0x5C, farm(5, 1, 1), 1.0), (0x5C, farm(6, 1, 2), 1.0), (0x5A, life(1, 1, 1), 1.0), (0x5A, life(99, 3, 1), 1.0)]),
    "farm-fast": dict(jineng=dict(nongfu=1), seeds=SEED, cmds=[(0x5B, plant(0, SEED), 0.5), (0x5C, farm(1, 0, 2), 1.0), (0x5C, farm(2, 0, 2), 5.0), (0x5C, farm(3, 0, 2), 1.0)]),
}


def mysql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


def set_state(sc) -> None:
    renwu = {**BASE_RENWU, **sc.get("renwu", {})}
    jineng = {**BASE_JINENG, **sc.get("jineng", {})}
    mysql("update renwu set " + ",".join(f"{k}={v}" for k, v in renwu.items()) + f" where jyid={JY}")
    mysql("update jineng set " + ",".join(f"{k}={v}" for k, v in jineng.items()) + f" where jyid={JY}")
    # 钱庄固定成三行：wupin=0 的头行（没有它原版不载入钱庄，存进去的东西会掉到背包里）、28026 x1、44156 x33
    mysql(f"delete from qianzhuang where jyid={JY}")
    mysql(f"insert into qianzhuang (id,jyid,wupin,shuliang) values (2049925589,{JY},0,0),(2049925590,{JY},28026,1),(2049925591,{JY},44156,33)")
    mysql(f"update item set item_id=0,shuliang=0 where jyid={JY} and (item_id in ({SEED},55001,44206,44156) or item_id between 44001 and 44070 or item_id between 55701 and 55717 or item_id in (44230,44233,44235))")  # 前几场留在背包里的产出
    mysql(f"delete from kf where jyid={JY}")
    kf = sc.get("kf", [])
    if kf:
        mysql("insert into kf (jyid,kf_id,kf_lvl,kf_exp) values " + ",".join(f"({JY},{a},{b},{c})" for a, b, c in kf))
    seed = sc.get("seeds")
    if seed:
        z = mysql(f"select min(id) from item where jyid={JY} and item_id=0")
        mysql(f"update item set item_id={seed},shuliang=40 where id={z}")
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
    d["renwu"][0].update({k: str(v) for k, v in renwu.items()})
    d["jineng"][0].update({k: str(v) for k, v in jineng.items()})
    d["kf"] = [{"jyid": str(JY), "kf_id": str(a), "kf_lvl": str(b), "kf_exp": str(c)} for a, b, c in sc.get("kf", [])]
    d["qianzhuang"] = [{"jyid": str(JY), "wupin": w, "shuliang": q} for w, q in (("0", "0"), ("28026", "1"), ("44156", "33"))]
    for r in d["item"]:
        if int(r.get("item_id") or 0) in (SEED, 55001, 44206, 44156, 44230, 44233, 44235) or 44001 <= int(r.get("item_id") or 0) <= 44070 or 55701 <= int(r.get("item_id") or 0) <= 55717:
            r["item_id"], r["shuliang"] = "0", "0"
    if seed:
        r = next(r for r in d["item"] if str(r.get("item_id")) == "0")
        r["item_id"], r["shuliang"] = str(seed), "40"
    c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), JY))
    c.commit()
    c.close()


def run(port: int, cmds) -> list[str]:
    time.sleep(3.0)
    for attempt in range(4):
        a = Client("A", "127.0.0.1", port, JY, None)
        if a.login():
            break
        a.sock.close()
        time.sleep(4)
    else:
        return ["login failed"]
    a.drain(1.0)
    out: list[str] = []

    def show(frames):
        for f in frames:
            if f.opcode in (0x33, 0x60, 0x05, 0x02) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            if f.opcode == 0x77 and f.payload[:4] != bytes.fromhex("8f bb 00 00") or (f.opcode == 0x1A and b"\xb1\x6f\xa8\xec\xa4\x46" in f.payload):
                continue  # 农夫「另外的物品」
            out.append(f"    <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {f.payload.hex(' ')}")

    for op, payload, wait in cmds:
        out.append(f"== 0x{op:02x} {payload.hex(' ')}")
        show(a.drain(0.05))
        try:
            a.send(op, payload)
        except OSError:
            out.append("!! connection lost")
            return out
        show(a.drain(max(wait, 0.3)))
    a.sock.close()
    return out


def state_after(port: int, sc) -> list[str]:
    time.sleep(4)
    cols_j = ("famu", "famuexp", "buyu", "buyuexp", "caikuang", "caikuangexp", "nongfu", "nongfuexp")
    if port == 6731:
        j = mysql(f"select {','.join(cols_j)} from jineng where jyid={JY}").split("\t")
        jing = mysql(f"select dangqianjing from renwu where jyid={JY}")
        bank_rows = {int(a): int(b) for a, b in (l.split("\t") for l in mysql(f"select wupin,shuliang from qianzhuang where jyid={JY}").splitlines())}
        bag = {int(a): int(b) for a, b in (l.split("\t") for l in mysql(f"select item_id,shuliang from item where jyid={JY} and item_id in (44206,44156,{SEED},55001)").splitlines())}
    else:
        c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        c.close()
        j = [str(d["jineng"][0][k]) for k in cols_j]
        jing = str(d["renwu"][0]["dangqianjing"])
        bank_rows = {}
        for r in d.get("qianzhuang", []):
            bank_rows[int(r["wupin"])] = bank_rows.get(int(r["wupin"]), 0) + int(r["shuliang"])
        bag = {}
        for r in d["item"]:
            if int(r["item_id"]) in (44206, 44156, SEED, 55001):
                bag[int(r["item_id"])] = bag.get(int(r["item_id"]), 0) + int(r["shuliang"])
    bank_total = sum(v for k, v in bank_rows.items() if k not in (0, 28026))
    return [f"jineng: {' '.join(f'{k}={v}' for k, v in zip(cols_j, j))}", f"jing: {jing}", f"bank harvested total: {bank_total}  (44156: {bank_rows.get(44156)})",
            f"bag: {dict(sorted(bag.items()))}"]


def restart_original() -> None:
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "restart_original.ps1")], capture_output=True)


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SCENARIOS)
    only_original = "--original" in sys.argv
    bad = 0
    for name in names:
        sc = SCENARIOS[name]
        res = {}
        for port in (6731, 6732):
            if only_original and port == 6732:
                continue
            if port == 6731:
                subprocess.run(["powershell", "-Command", "Get-Process -Name 服务端 -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
                time.sleep(2)
            set_state(sc)
            if port == 6731:
                restart_original()
            res[port] = run(port, sc["cmds"]) + state_after(port, sc)
        if only_original:
            print(f"### {name} (original)")
            print("\n".join(res[6731]))
            continue
        same = res[6731] == res[6732]
        print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
        if not same:
            bad += 1
            for l in difflib.unified_diff(res[6731], res[6732], "original", "new", lineterm="", n=1):
                print("   ", l[:240])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
