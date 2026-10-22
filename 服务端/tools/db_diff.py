"""对原版 MySQL 里某个角色拍快照 / 比较两张快照，用来看一条指令到底改了库里的什么。

    python tools/db_diff.py snap <jyid> <输出.json>
    python tools/db_diff.py diff <前.json> <后.json>

原版只在玩家下线时写库，所以：先 snap，登录发指令、下线，等 3 秒，再 snap，最后 diff。item 表只比非空格子。
"""

from __future__ import annotations

import json
import subprocess
import sys

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
TABLES = ["renwu", "char_equip", "jineng", "kf", "item", "biaoji", "biaoju", "account", "qianzhuang", "ypsx", "zssj"]


def q(sql: str) -> list[list[str]]:
    out = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "jydata", "-e", sql], capture_output=True, text=True, encoding="gbk")
    return [l.split("\t") for l in out.stdout.splitlines()]


def snap(jyid: int) -> dict:
    res = {}
    for t in TABLES:
        rows = q(f"select * from {t} where jyid={jyid}")
        if len(rows) < 2:
            res[t] = []
            continue
        cols = rows[0]
        recs = [dict(zip(cols, r)) for r in rows[1:]]
        if t == "item":
            recs = [r for r in recs if r.get("item_id") != "0"]
        for r in recs:
            r.pop("password", None)
            r.pop("id", None)
        res[t] = recs
    return res


def diff(a: dict, b: dict) -> list[str]:
    out = []
    for t in TABLES:
        ra, rb = a.get(t, []), b.get(t, [])
        if t in ("item", "biaoji", "biaoju", "qianzhuang") or len(ra) != 1 or len(rb) != 1:
            key = lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False)
            sa, sb = {key(r) for r in ra}, {key(r) for r in rb}
            for k in sorted(sa - sb):
                out.append(f"{t} - {k}")
            for k in sorted(sb - sa):
                out.append(f"{t} + {k}")
        else:
            for c in ra[0]:
                if ra[0][c] != rb[0].get(c):
                    out.append(f"{t}.{c}: {ra[0][c]} -> {rb[0].get(c)}")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "snap":
        json.dump(snap(int(sys.argv[2])), open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    else:
        a, b = (json.load(open(p, encoding="utf-8")) for p in sys.argv[2:4])
        print("\n".join(diff(a, b)) or "(no change)")
