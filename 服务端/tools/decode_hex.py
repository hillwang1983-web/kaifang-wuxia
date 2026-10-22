"""把十六进制字节解成帧并打印。

    python tools/decode_hex.py c2s "f6 11 01 6a da 8f 9f a7 ae 9e 9e 69 62 9b 9e af ac ad aa ab"
    echo "<hex>" | python tools/decode_hex.py s2c

方向必须指定：C2S 帧带 F6 11 <seq> 前缀，S2C 没有。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import decode_stream  # noqa: E402
from jyserver.opcodes import describe  # noqa: E402


def parse_hex(text: str) -> bytes:
    digits = re.sub(r"[^0-9a-fA-F]", "", text)
    if len(digits) % 2:
        raise SystemExit("十六进制位数为奇数")
    return bytes.fromhex(digits)


def print_frames(data: bytes, direction: str) -> None:
    frames, rest, skipped = decode_stream(data, direction, resync=True)
    for i, f in enumerate(frames):
        seq = f"seq={f.seq} " if f.seq is not None else ""
        kind = "long " if f.wide else "short"
        print(
            f"#{i} {kind} {seq}key=0x{f.key:02x} op=0x{f.opcode:02x} "
            f"len={f.total_length} {describe(direction, f.opcode)}"
        )
        print(f"    payload: {f.payload.hex(' ')}")
    if skipped:
        print(f"(重同步丢弃 {skipped} 字节)")
    if rest:
        print(f"(末尾 {len(rest)} 字节不完整: {rest.hex(' ')})")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("c2s", "s2c"):
        print(__doc__)
        return 2
    text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else sys.stdin.read()
    print_frames(parse_hex(text), sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
