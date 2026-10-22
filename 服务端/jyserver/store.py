"""角色存储：SQLite，一个账号一行。

    characters(jyid PK, password, state, zongxiaofei, name, rows)

rows 是 JSON：{'renwu': [...], 'char_equip': [...], 'jineng': [...], 'kf': [...], 'item': [...], 'account': [...]}，
格式和 tools/snapshot_char.py 相同（字段值都是字符串、列名同原版 MySQL 库），state.py 直接吃这个格式。
password 是明文（登录包里本来就是明文）；state=0 表示账号被禁用（原版 account.state）。
**还没创建角色的账号**也存在这里：rows['renwu'] 是空列表（登录时走「新账号」握手，见 creation.py）。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Character:
    jyid: int
    password: str
    state: int
    rows: dict

    @property
    def has_character(self) -> bool:
        return bool(self.rows.get("renwu"))


def decode_db_password(text: str) -> str:
    """原版 account.password 是「每个字符的十六进制，空格分隔」，如 '31 32 33' = '123'。"""
    try:
        return bytes(int(t, 16) for t in text.split()).decode("ascii")
    except ValueError:
        return text


class CharacterStore:
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "create table if not exists characters ("
            "jyid integer primary key, password text not null, state integer not null default 1,"
            "zongxiaofei integer not null default 0, rows text not null)"
        )
        cols = {r[1] for r in self.db.execute("pragma table_info(characters)")}
        if "name" not in cols:  # 旧库升级：补上名字列，并回填
            self.db.execute("alter table characters add column name text not null default ''")
            for jyid, rows in self.db.execute("select jyid, rows from characters").fetchall():
                self.db.execute("update characters set name=? where jyid=?", (self._name_of(json.loads(rows)), jyid))
        self.db.commit()

    @staticmethod
    def _name_of(rows: dict) -> str:
        renwu = rows.get("renwu") or []
        return (renwu[0].get("name") or "") if renwu else ""

    def close(self) -> None:
        self.db.close()

    def put(self, jyid: int, password: str, rows: dict, state: int = 1) -> None:
        renwu = (rows.get("renwu") or [{}])[0]
        try:
            spent = int(renwu.get("zongxiaofei") or 0)
        except ValueError:
            spent = 0
        self.db.execute(
            "insert or replace into characters (jyid,password,state,zongxiaofei,rows,name) values (?,?,?,?,?,?)",
            (jyid, password, state, spent, json.dumps(rows, ensure_ascii=False), self._name_of(rows)),
        )
        self.db.commit()

    def get(self, jyid: int) -> Character | None:
        r = self.db.execute("select jyid,password,state,rows from characters where jyid=?", (jyid,)).fetchone()
        return Character(r[0], r[1], r[2], json.loads(r[3])) if r else None

    def ids(self) -> list[int]:
        return [r[0] for r in self.db.execute("select jyid from characters order by jyid")]

    def name_taken(self, name: str) -> bool:
        """名字已被某个角色占用（原版：`select * from renwu where name = '…'` 有结果）。"""
        return self.db.execute("select 1 from characters where name=? limit 1", (name,)).fetchone() is not None

    def top_sponsor(self) -> int | None:
        """总消费点数最高（且 > 0）的角色；并列取 jyid 小的。登录时它会多收一条「本服贊助王」广播。"""
        r = self.db.execute("select jyid from characters where zongxiaofei>0 order by zongxiaofei desc, jyid limit 1").fetchone()
        return r[0] if r else None
