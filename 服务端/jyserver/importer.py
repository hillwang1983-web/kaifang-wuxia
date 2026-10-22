"""从原版 MySQL 库（jydata）把角色导入 SQLite 存储，经 mysql.exe 命令行读取，不需要 Python 驱动。

    python -m jyserver.importer --db data/chars.sqlite
    python -m jyserver.importer --db data/chars.sqlite --jyid 123456

只读 MySQL，不改它。有账号但还没角色的号也导入（登录时走新建角色流程）。表里没有数据文件的（ypsx/zssj/biaoju/zuzhi，只有 .frm）跳过。
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from .store import CharacterStore, decode_db_password

DEFAULT_MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
CHAR_TABLES = ["renwu", "char_equip", "jineng", "kf", "item", "biaoji", "account", "qianzhuang"]


class MySQL:
    def __init__(self, exe: str = DEFAULT_MYSQL, user: str = "root", password: str = "123456", db: str = "jydata"):
        self.exe, self.user, self.password, self.db = exe, user, password, db

    def query(self, stmt: str) -> list[dict[str, str]]:
        p = subprocess.run(
            [self.exe, f"-u{self.user}", f"-p{self.password}", "--default-character-set=gbk", "--batch", "--raw", self.db, "-e", stmt],
            capture_output=True,
        )
        err = p.stderr.decode("gbk", errors="replace")
        if p.returncode != 0 or "ERROR" in err:
            raise RuntimeError(f"mysql failed: {err.strip()}\nSQL: {stmt[:200]}")
        lines = [ln for ln in p.stdout.decode("gbk", errors="replace").splitlines() if ln]
        if not lines:
            return []
        head = lines[0].split("\t")
        return [dict(zip(head, ln.split("\t"))) for ln in lines[1:]]


def import_character(my: MySQL, store: CharacterStore, jyid: int) -> bool:
    rows: dict[str, list[dict[str, str]]] = {}
    for t in CHAR_TABLES:
        order = " order by id" if t in ("item", "biaoji", "qianzhuang") else ""  # biaoji 的主键列叫 ID，MySQL 列名不分大小写
        try:
            rows[t] = my.query(f"select * from {t} where jyid={jyid}{order}")
        except RuntimeError:
            rows[t] = []
    acct = rows["account"][0] if rows["account"] else None
    if acct is None:
        return False  # 没有账号行；有账号但还没角色的号照样导入（renwu 为空列表）
    password = decode_db_password(acct.pop("password", ""))
    store.put(jyid, password, rows, state=int(acct.get("state") or 0))
    return True


def import_all(my: MySQL, store: CharacterStore, only: int | None = None) -> tuple[int, list[int]]:
    ids = [only] if only is not None else [int(r["jyid"]) for r in my.query("select jyid from account order by jyid")]
    done, skipped = 0, []
    for j in ids:
        if import_character(my, store, j):
            done += 1
        else:
            skipped.append(j)
    return done, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "data" / "chars.sqlite"))
    ap.add_argument("--jyid", type=int)
    ap.add_argument("--mysql", default=DEFAULT_MYSQL)
    args = ap.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    store = CharacterStore(args.db)
    done, skipped = import_all(MySQL(args.mysql), store, args.jyid)
    print(f"imported {done} character(s) -> {args.db}; skipped (no renwu/account row): {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
