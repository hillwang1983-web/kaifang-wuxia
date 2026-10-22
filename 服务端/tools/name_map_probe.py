"""向原版问「简体字 → BIG5 字节」的真实转换：对一个没有任何武功的号，发 C2S 0x61 装备每一个武学系数.csv 里的 ID，
原版会全服广播「嘗試刷武功﹗<武功名>」，武功名就是第 5 列简体名过原版转换后的 BIG5 字节。输出 data/orig_name_bytes.json（ID → 十六进制）。

    python tools/name_map_probe.py [--port 6731] [--jyid 8617293]

需要该号 kf 表为空（跑 restore_fixture.py 即可）；原版上只有这个号在线。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data")
PREFIX = bytes.fromhex("b9 c1 b8 d5 a8 ea aa 5a a5 5c a1 54")  # 嘗試刷武功﹗


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, default=8617293)
    a = ap.parse_args()
    raw = (DATA / "武学系数.csv").read_bytes().decode("gbk", errors="replace")
    ids = [(int(r[0]), r[4]) for r in csv.reader(io.StringIO(raw)) if r and r[0].strip().isdigit() and len(r) > 4]
    c = Client("A", "127.0.0.1", a.port, a.jyid, None)
    assert c.login()
    c.drain(1.0)
    out = {}
    for kid, name in ids:
        c.send(0x61, b"\x01" + struct.pack("<H", kid))
        for f in c.drain(0.12):
            if f.opcode == 0x14 and PREFIX in f.payload:
                out[kid] = {"gbk": name, "big5": f.payload.split(PREFIX, 1)[1].hex()}
    (ROOT / "data" / "orig_name_bytes.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(ids), "asked,", len(out), "answered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
