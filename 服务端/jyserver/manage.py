"""账号管理（新服务端自己的角色库，不碰原版 MySQL）。

    python -m jyserver.manage add-account 9000001 mypassword [--points 0]
    python -m jyserver.manage list
    python -m jyserver.manage ban 9000001      # state=0，登录会被拒绝
    python -m jyserver.manage unban 9000001

新账号第一次登录时会走「新建角色」流程（摇点、起名字、选头像和属性），见 jyserver/creation.py。
原版靠外部的注册站往 account 表里插行；这里用命令行代替。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import creation
from .store import CharacterStore

DEFAULT_CHARS = Path(__file__).resolve().parent.parent / "data" / "chars.sqlite"


def add_account(store: CharacterStore, jyid: int, password: str, points: int = 0) -> None:
    if store.get(jyid) is not None:
        raise SystemExit(f"账号 {jyid} 已存在")
    if not password.isascii() or not password:
        raise SystemExit("密码只能是 ASCII（登录包里就是明文 ASCII）")
    defaults = creation.load_defaults()
    account = creation.new_account_row(defaults, jyid)
    account["shangchengdianshu"] = str(points)
    store.put(jyid, password, creation.blank_rows(defaults, jyid, account))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chars", default=str(DEFAULT_CHARS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-account")
    a.add_argument("jyid", type=int)
    a.add_argument("password")
    a.add_argument("--points", type=int, default=0, help="商城点数")
    sub.add_parser("list")
    for name in ("ban", "unban"):
        b = sub.add_parser(name)
        b.add_argument("jyid", type=int)
    args = ap.parse_args()

    store = CharacterStore(args.chars)
    if args.cmd == "add-account":
        add_account(store, args.jyid, args.password, args.points)
        print(f"已添加账号 {args.jyid}（还没有角色，首次登录会进入创建流程）")
    elif args.cmd == "list":
        for jyid in store.ids():
            c = store.get(jyid)
            name = c.rows["renwu"][0].get("name") if c.has_character else "(未创建角色)"
            print(f"{jyid:>10}  state={c.state}  {name}")
    else:
        c = store.get(args.jyid)
        if c is None:
            raise SystemExit(f"账号 {args.jyid} 不存在")
        store.put(args.jyid, c.password, c.rows, 0 if args.cmd == "ban" else 1)
        print(("已封禁 " if args.cmd == "ban" else "已解封 ") + str(args.jyid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
