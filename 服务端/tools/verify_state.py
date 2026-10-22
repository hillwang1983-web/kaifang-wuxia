"""用快照夹具检验 jyserver/state.py：从数据库行生成的登录序列是否与原版真实序列一致。

    python tools/verify_state.py data/fixtures/char-8617293.json [...更多夹具]

逐帧、逐字节对比，列出不一致的帧和偏移（0x1E 载荷第 0 字节是计时计数、0x08 帧最后一字节是随机值，已忽略）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jyserver.state import ItemTable, Template, build_login_stream  # noqa: E402

DATA_DIR = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"
TEMPLATE = ROOT / "data" / "fixtures" / "char-8617293.json"


def compare(fix: dict, template: Template, table: ItemTable, extra=None, verbose=True):
    want = [(f["opcode"], bytes.fromhex(f["payload"]), f["wide"]) for f in fix["frames"][1:]]
    king = any(f["opcode"] == 0x14 and bytes.fromhex(f["payload"])[:1] == b"\x0e" for f in fix["frames"])
    got = build_login_stream(template, fix["rows"], table, big5_extra=extra, sponsor_king=king)
    report = []
    if len(want) != len(got):
        report.append(f"frame count: want {len(want)} got {len(got)}")
    for i, (w, g) in enumerate(zip(want, got)):
        if w[0] != g[0] or w[2] != g[2]:
            report.append(f"frame {i + 1}: opcode/wide want 0x{w[0]:02x}/{w[2]} got 0x{g[0]:02x}/{g[2]}")
            continue
        if len(w[1]) != len(g[1]):
            report.append(f"frame {i + 1} (0x{w[0]:02x}): length want {len(w[1])} got {len(g[1])}")
            continue
        offs = [k for k in range(len(w[1])) if w[1][k] != g[1][k]]
        if i == 0:
            offs = [k for k in offs if k >= 4]  # [0:4] 是运行分钟数
        if i == 9:
            offs = [k for k in offs if k != 6]
        if offs:
            report.append(f"frame {i + 1} (0x{w[0]:02x}): {len(offs)} bytes differ at {offs[:16]}{'...' if len(offs) > 16 else ''}")
    return report


def main() -> int:
    template = Template.load(TEMPLATE)
    table = ItemTable.load(DATA_DIR)
    print(f"item durability entries: {len(table.durability)}")
    bad = 0
    for p in sys.argv[1:]:
        fix = json.loads(Path(p).read_text(encoding="utf-8"))
        rep = compare(fix, template, table)
        print(f"{Path(p).name}: " + ("OK (identical except time counter / random byte)" if not rep else f"{len(rep)} problem(s)"))
        for r in rep:
            print("   ", r)
        bad += bool(rep)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
