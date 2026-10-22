"""对原版发 C2S 0xC7 文本指令（"@xxx"），可先改库，打印所有回包，可选再查库。

    python tools/cmd_probe.py --port 6731 --jyid 8617293 --sql "update account set gm_lvl=1 where jyid=8617293" "se 100" "wp 11005" --after "select school from renwu where jyid=8617293"

每条指令是不带 @ 的文本，会编成 C7 载荷 `04 40 <ASCII>`。--sql 在登录前执行（原版登录时才读库），--after 在下线 4 秒后执行。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"


def sql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return (r.stdout + r.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    ap.add_argument("--sql", action="append", default=[])
    ap.add_argument("--after", action="append", default=[])
    ap.add_argument("--wait", type=float, default=1.3)
    ap.add_argument("--password", default=None)
    ap.add_argument("--op", default="C7", help="C2S 操作码(十六进制)；非 C7 时指令按十六进制载荷")
    ap.add_argument("--raw", action="store_true", help="指令按十六进制原样当载荷")
    ap.add_argument("cmds", nargs="*")
    a = ap.parse_args()
    for s in a.sql:
        out = sql(s)
        if out:
            print("SQL>", out)
    time.sleep(3)
    c = Client("A", "127.0.0.1", a.port, a.jyid, a.password)
    if not c.login():
        print("login failed")
        return 1
    c.drain(0.5)
    for cmd in a.cmds:
        payload = bytes.fromhex(cmd.replace(" ", "")) if (a.raw or a.op.upper() != "C7") else b"\x04\x40" + cmd.encode("latin1")
        c.send(int(a.op, 16), payload)
        print(f"== @{cmd}")
        for f in c.drain(a.wait):
            if f.opcode in (0x33,) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            txt = ""
            if f.opcode in (0x1A, 0x14, 0x04):
                body = f.payload[1:] if f.opcode == 0x14 else (f.payload[5:] if f.opcode == 0x04 else f.payload[1:])
                txt = "  | " + body.decode("big5", errors="replace")
            print(f"    <- 0x{f.opcode:02x}{' wide' if f.wide else ''} {f.payload.hex(' ')}{txt}")
    c.sock.close()
    if a.after:
        time.sleep(4)
        for s in a.after:
            print("AFTER>", sql(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
