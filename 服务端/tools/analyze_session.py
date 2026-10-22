"""分析 jyproxy.py 录下的 JSONL：按连接、按方向拆帧，输出 opcode 统计，可选时间线。

    python tools/analyze_session.py captures/xxx.jsonl
    python tools/analyze_session.py captures/xxx.jsonl --timeline --conn 1

解码是无状态的（密钥在帧头里），所以直接把同一连接同一方向的字节按顺序拼起来拆帧即可。
握手包后面多出的 1 字节 00 会被重同步丢弃并计数。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import FrameReader  # noqa: E402
from jyserver.opcodes import describe  # noqa: E402


def load(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            yield json.loads(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--conn", type=int, default=None, help="只看某个连接号")
    ap.add_argument("--timeline", action="store_true", help="按时间顺序打印每一帧")
    args = ap.parse_args()

    readers: dict[tuple[int, str], FrameReader] = {}
    stats: dict[tuple[int, str, int], list] = defaultdict(list)  # -> [count, min_len, max_len, sample]
    timeline = []
    t0 = None

    for rec in load(args.file):
        if "hex" not in rec:
            continue
        conn, direction = rec["conn"], rec["dir"]
        if args.conn is not None and conn != args.conn:
            continue
        t0 = rec["t"] if t0 is None else t0
        key = (conn, direction)
        reader = readers.setdefault(key, FrameReader(direction, resync=True))
        for f in reader.feed(bytes.fromhex(rec["hex"])):
            s = stats[(conn, direction, f.opcode)]
            if not s:
                s.extend([0, f.total_length, f.total_length, f.payload[:24].hex(" ")])
            s[0] += 1
            s[1] = min(s[1], f.total_length)
            s[2] = max(s[2], f.total_length)
            timeline.append((rec["t"] - t0, conn, direction, f))

    if not stats:
        print("没有可解的数据")
        return 1

    for (conn, direction), reader in sorted(readers.items()):
        extra = f", 重同步丢弃 {reader.skipped} 字节" if reader.skipped else ""
        tail = f", 末尾残留 {len(reader.pending)} 字节" if reader.pending else ""
        print(f"连接 #{conn} {direction}{extra}{tail}")
        rows = sorted((op, s) for (c, d, op), s in stats.items() if c == conn and d == direction)
        for op, (count, lo, hi, sample) in rows:
            length = f"{lo}" if lo == hi else f"{lo}-{hi}"
            print(f"  0x{op:02x} x{count:<4} len={length:<8} {describe(direction, op):<28} {sample}")

    if args.timeline:
        print("\n时间线")
        for t, conn, direction, f in timeline:
            print(
                f"{t:8.3f}s #{conn} {direction} op=0x{f.opcode:02x} key=0x{f.key:02x} "
                f"len={f.total_length} {f.payload[:32].hex(' ')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
