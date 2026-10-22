"""把原版 MySQL 里的测试号还原成 data/fixtures/char-<jyid>.json 里记录的样子（renwu / char_equip / jineng / kf / account / item，biaoji 清空）。

    python tools/restore_fixture.py 8617293 1234567

跑完之后必须**重启原版服务端**（它的背包在内存里，下线才写库）：停 服务端.exe → 跑本脚本 → 启动 服务端.exe → python -m jyserver.importer。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
ROOT = Path(__file__).resolve().parent.parent


def sql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    if r.returncode:
        raise RuntimeError(r.stderr + "\n" + stmt[:200])
    return r.stdout.strip()


def lit(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def restore(jyid: str) -> None:
    rows = json.load(open(ROOT / "data" / "fixtures" / f"char-{jyid}.json", encoding="utf-8"))["rows"]
    for table in ("renwu", "char_equip", "jineng", "account"):
        if not rows.get(table):
            continue
        cols = [c for c in rows[table][0] if c != "password"]
        sets = ",".join(f"`{c}`={lit(rows[table][0][c])}" for c in cols)
        sql(f"update {table} set {sets} where jyid={jyid}")
    sql(f"delete from kf where jyid={jyid}")
    for r in rows.get("kf", []):
        cols = [c for c in r if c.lower() != "id"]
        sql(f"insert into kf (`{'`,`'.join(cols)}`) values ({','.join(lit(r[c]) for c in cols)})")
    sql(f"delete from biaoji where jyid={jyid}")
    # 背包：非空格子对齐到快照（只改已有格子，必要时占用空格子）
    want = {r["item_id"]: int(r["shuliang"]) for r in rows.get("item", []) if r["item_id"] != "0"}
    cur = [l.split("\t") for l in sql(f"select id,item_id,shuliang from item where jyid={jyid}").splitlines()]
    seen = set()
    for id_, it, sh in cur:
        if it == "0":
            continue
        if it in want and it not in seen:
            seen.add(it)
            if int(sh) != want[it]:
                sql(f"update item set shuliang={want[it]} where id={id_}")
        else:
            sql(f"update item set item_id=0,shuliang=0 where id={id_}")
    for it, qty in want.items():
        if it not in seen:
            z = sql(f"select min(id) from item where jyid={jyid} and item_id=0")
            sql(f"update item set item_id={it},shuliang={qty} where id={z}")
    print(jyid, "restored")


if __name__ == "__main__":
    for j in sys.argv[1:]:
        restore(j)
