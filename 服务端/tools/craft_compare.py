"""合成 / 烹調（C2S 0x1B）对照：同一份人物状态、同一串指令，对原版(6731)和新服务端(6732)各跑一遍，比回包帧和下线后的库。

    python tools/craft_compare.py [场景 ...] [--original]

载荷 = 配方键两个字节（原版把帧转成十六进制文本再按空格拆，取第 5、6 个词当配方键，例如 F0 02 = 熟牛肉）。
成功与否取决于随机数（随机(1..110)/5 取整 < 阈值），场景里把幸运(luk)定在结果固定的地方（0 恒败 / ≥ 23 恒成）。
配方场景名 `r:<键>[:fail]`：按 jyserver/recipes.json 里的材料给两套，连发两次。
跑完之后用 restore_fixture.py 还原，并重启原版。
"""

from __future__ import annotations

import difflib
import json
import re
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
BASE_RENWU = dict(dangqianjing=50, dangqianshen=50, zuidashen=210, wint=33, luk=30, map=2411, jy_money=100000)
BASE_JINENG = dict(famu=5, famuexp=0, gongjiang=0, gongjiangexp=0, zhibu=0, zhibuexp=0, caifeng=0, caifengexp=0, lieren=0, lirenexp=0, caikuang=5, caikuangexp=0, datie=0, datieexp=0, zhujian=0, zhujianexp=0, nongfu=1, nongfuexp=0, buyu=5, buyuexp=0, chushi=0, chushiexp=0)
SKILL_COL = {"厨师": "chushi", "铸剑": "zhujian", "裁缝": "caifeng", "工匠": "gongjiang", "织布": "zhibu", "打铁": "datie", "猎人": "lieren"}
RECIPES = json.loads((ROOT / "jyserver" / "recipes.json").read_text(encoding="utf-8"))["recipes"]

JUNK = 40500  # 凑背包总数用的垃圾物品
K = lambda *b: (0x1B, bytes(b), 1.0)  # noqa: E731
COOK = K(0xF0, 0x02)
COOK_BAG = {44267: 3, 44102: 3, 44104: 3}

SCENARIOS = {
    "cook-fail": dict(renwu=dict(luk=0), bag=COOK_BAG, cmds=[COOK, COOK, COOK, COOK]),
    "cook-ok": dict(jineng=dict(chushi=40), bag=COOK_BAG, cmds=[COOK, COOK, COOK, COOK]),
    "cook-missing": dict(jineng=dict(chushi=40), bag={44267: 1, 44102: 0, 44104: 1}, cmds=[COOK]),
    "cap-ok": dict(jineng=dict(chushi=40), bag=COOK_BAG, total=498, cmds=[COOK, COOK]),  # 身上总数 498（含材料）：能做；做完材料少 3、成品多 1
    "cap-full": dict(jineng=dict(chushi=40), bag=COOK_BAG, total=500, cmds=[COOK, K(0xF0, 0x03)]),  # 500：「身上总数超过499」
    "cap-edge": dict(jineng=dict(chushi=40), bag=COOK_BAG, total=499, cmds=[COOK]),  # 499 刚好挡住（总数 + 1 > 499）
    "cook-shen": dict(jineng=dict(chushi=40), renwu=dict(dangqianshen=2), bag=COOK_BAG, cmds=[COOK, COOK]),
    "cook-cap": dict(jineng=dict(chushi=99, chushiexp=9900), bag=COOK_BAG, cmds=[COOK, COOK]),
    "shapes": dict(jineng=dict(chushi=40), bag=COOK_BAG, cmds=[(0x1B, b"", 0.5), (0x1B, b"\xf0", 0.5), (0x1B, b"\xf0\x02\x00\x00", 1.0), (0x1B, b"\xf0\x03", 0.5), (0x1B, b"\x00\x00", 0.5), (0x1B, b"\x0a\x00", 0.5)]),
}


def recipe_scenario(spec: str) -> dict:
    parts = spec.split(":")
    key = parts[1] if " " in parts[1] else f"{parts[1][:2]} {parts[1][2:]}"
    rec = RECIPES[key]
    bag = {iid: n * 2 for iid, n in rec["needs"]}
    renwu = dict(luk=0) if "fail" in parts[2:] else {}
    jn = {}
    if "lv" in "".join(parts[2:]):
        pass
    payload = bytes(int(x, 16) for x in key.split())
    return dict(renwu=renwu, jineng=jn, bag=bag, extra=[rec["product"]], skill=rec["skill"], loose=rec["win"] != "luk", product=rec["product"], cmds=[(0x1B, payload, 1.0), (0x1B, payload, 1.0)])


def get(name):
    return recipe_scenario(name) if name.startswith("r:") else SCENARIOS[name]


def watch_ids(sc) -> list[int]:
    return sorted(set(sc.get("bag", {})) | set(sc.get("extra", [])) | {31001, 44267, 44102, 44104})


def all_recipe_ids() -> list[int]:
    """所有配方里出现过的物品（材料 / 成品）：每个场景开始前整批清掉，免得上一个场景留在背包里的东西串进来。"""
    s = {JUNK, 31001, 44267, 44102, 44104}
    for r in RECIPES.values():
        s |= {i for i, _ in r["needs"]} | {i for i, _ in r["takes"]} | {r["product"]}
    return sorted(s)


def mysql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


def set_state(sc) -> None:
    renwu = {**BASE_RENWU, **sc.get("renwu", {})}
    jineng = {**BASE_JINENG, **sc.get("jineng", {})}
    bag = sc.get("bag", {})
    ids = all_recipe_ids()
    mysql("update renwu set " + ",".join(f"{k}={v}" for k, v in renwu.items()) + f" where jyid={JY}")
    mysql("update jineng set " + ",".join(f"{k}={v}" for k, v in jineng.items()) + f" where jyid={JY}")
    mysql(f"delete from qianzhuang where jyid={JY}")
    mysql(f"insert into qianzhuang (id,jyid,wupin,shuliang) values (2049925589,{JY},0,0),(2049925590,{JY},28026,1)")
    mysql(f"update item set item_id=0,shuliang=0 where jyid={JY} and item_id in ({','.join(map(str, ids))})")
    for iid, n in bag.items():
        if n:
            z = mysql(f"select min(id) from item where jyid={JY} and item_id=0")
            mysql(f"update item set item_id={iid},shuliang={n} where id={z}")
    total = sc.get("total")
    if total:  # 把背包里所有物品加起来凑成 total（用一行垃圾 JUNK 补）
        mysql(f"update item set item_id=0,shuliang=0 where jyid={JY} and item_id={JUNK}")
        others = int(mysql(f"select coalesce(sum(shuliang),0) from item where jyid={JY}"))
        z = mysql(f"select min(id) from item where jyid={JY} and item_id=0")
        mysql(f"update item set item_id={JUNK},shuliang={total - others} where id={z}")
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
    d["renwu"][0].update({k: str(v) for k, v in renwu.items()})
    d["jineng"][0].update({k: str(v) for k, v in jineng.items()})
    d["qianzhuang"] = [{"jyid": str(JY), "wupin": w, "shuliang": q} for w, q in (("0", "0"), ("28026", "1"))]
    d["item"] = [r for r in d["item"] if int(r.get("item_id") or 0) not in ids and int(r.get("item_id") or 0) != JUNK]
    for iid, n in bag.items():
        if n:
            d["item"].append({"jyid": str(JY), "item_id": str(iid), "shuliang": str(n), "state": "200"})
    if total:
        others = sum(int(r.get("shuliang") or 0) for r in d["item"])
        d["item"].append({"jyid": str(JY), "item_id": str(JUNK), "shuliang": str(total - others), "state": "200"})
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
    ids = watch_ids(sc)
    col = SKILL_COL.get(sc.get("skill", "厨师"), "chushi")
    cols_j = (col, col + "exp")
    if port == 6731:
        j = mysql(f"select {','.join(cols_j)} from jineng where jyid={JY}").split("\t")
        shen = mysql(f"select dangqianshen from renwu where jyid={JY}")
        bag = {int(a): int(b) for a, b in (l.split("\t") for l in mysql(f"select item_id,shuliang from item where jyid={JY} and item_id in ({','.join(map(str, ids))})").splitlines())}
    else:
        c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        c.close()
        j = [str(d["jineng"][0][k]) for k in cols_j]
        shen = str(d["renwu"][0]["dangqianshen"])
        bag = {}
        for r in d["item"]:
            if int(r["item_id"]) in ids and int(r["shuliang"]) > 0:
                bag[int(r["item_id"])] = bag.get(int(r["item_id"]), 0) + int(r["shuliang"])
    return [f"jineng: {' '.join(f'{k}={v}' for k, v in zip(cols_j, j))}", f"shen: {shen}", f"bag: {dict(sorted(bag.items()))}"]


def restart_original() -> None:
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "restart_original.ps1")], capture_output=True)


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SCENARIOS)
    only_original = "--original" in sys.argv
    bad = 0
    for name in names:
        sc = get(name)
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
        for p in res:  # 全服公告（随机数 < 6 且成品「是否广播」）随机出现，不比；文字见 tests/test_craft.py
            res[p] = [l for l in res[p] if not l.startswith("    <- 0x04 W 09 ")]
        if sc.get("loose"):  # 阈值是常数的配方成败随机：成败帧和成品不比
            prod = sc["product"]
            for p in res:
                res[p] = ["    <- 0x64 RESULT" if l.startswith("    <- 0x64 ") else re.sub(rf"\b{prod}: \d+,? ?", "", l) if l.startswith("bag:") else l for l in res[p]]
        same = res[6731] == res[6732]
        print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
        if not same:
            bad += 1
            for l in difflib.unified_diff(res[6731], res[6732], "original", "new", lineterm="", n=1):
                print("   ", l[:240])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

