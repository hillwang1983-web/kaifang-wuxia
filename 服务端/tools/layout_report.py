"""分析 layout_probe 的结果：每列的宽度、字节序，以及 0x1E 载荷第 0 字节（校验字节）的规律。

    python tools/layout_report.py data/layout/renwu.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def le(b: bytes) -> int:
    return int.from_bytes(b, "little")


def be(b: bytes) -> int:
    return int.from_bytes(b, "big")


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    byte0 = []  # (field_delta_info, old0, new0)
    for col, info in data["columns"].items():
        if "changes" not in info:
            rows.append((col, info.get("result", "?"), "", "", ""))
            continue
        v = int(info["value"]) if info["value"].lstrip("-").isdigit() else None
        main_ch = [c for c in info["changes"] if not (c["frame"] == 1 and c["offset"] == 0)]
        c0 = [c for c in info["changes"] if c["frame"] == 1 and c["offset"] == 0]
        parts = []
        for c in main_ch:
            new = bytes.fromhex(c["new"].replace(" ", ""))
            old = bytes.fromhex(c["old"].replace(" ", ""))
            note = ""
            if v is not None:
                mask = (1 << (8 * c["width"])) - 1
                if le(new) == (v & mask):
                    note = f"LE uint{8*c['width']}"
                elif be(new) == (v & mask):
                    note = f"BE uint{8*c['width']}"
                else:
                    note = f"?? new={le(new)}(le)/{be(new)}(be) for value {v}"
            parts.append(f"f{c['frame']}[{c['opcode']}]@{c['offset']}+{c['width']} {note}")
        rows.append((col, info["value"], "; ".join(parts), c0[0]["old"] if c0 else "", c0[0]["new"] if c0 else ""))
        if c0 and main_ch and len(main_ch) == 1 and main_ch[0]["frame"] == 1:
            m = main_ch[0]
            byte0.append(
                (
                    col,
                    m["offset"],
                    bytes.fromhex(m["old"].replace(" ", "")),
                    bytes.fromhex(m["new"].replace(" ", "")),
                    int(c0[0]["old"], 16),
                    int(c0[0]["new"], 16),
                )
            )
    print(f"{'column':<24}{'value':<12}{'field(s) in stream':<70}byte0 old->new")
    for col, val, desc, o0, n0 in rows:
        print(f"{col:<24}{val:<12}{desc:<70}{o0}->{n0}" if o0 else f"{col:<24}{val:<12}{desc}")

    print("\n== 校验字节假设检验：byte0 = (byte0_old + sum(Δ) * w) mod 256 的各种形式 ==")
    for name, fn in {
        "sum:  Δ0 = -(Σ Δbytes)": lambda m, d: -d,
        "xor:  Δ0 = Δ(xor)": None,
    }.items():
        pass
    ok_sum = ok_xor = ok_wsum = 0
    for col, off, old, new, o0, n0 in byte0:
        d0 = (n0 - o0) & 0xFF
        dsum = sum(n - o for n, o in zip(new, old)) & 0xFF
        dxor = 0
        for n, o in zip(new, old):
            dxor ^= n ^ o
        if d0 == dsum:
            ok_sum += 1
        elif d0 == (-dsum) & 0xFF:
            ok_sum += 1000  # 反号记另一个计数（不显示）
        if (o0 ^ n0) == dxor:
            ok_xor += 1
    print(f"  样本 {len(byte0)} 个；Δ0==ΣΔ 的有 {ok_sum % 1000}；Δ0==-ΣΔ 的有 {ok_sum // 1000}；(old0^new0)==xorΔ 的有 {ok_xor}")
    print("  前 12 个样本：")
    for col, off, old, new, o0, n0 in byte0[:12]:
        d0 = (n0 - o0) & 0xFF
        dsum = sum(n - o for n, o in zip(new, old)) & 0xFF
        print(f"   {col:<18} @{off:<4} old={old.hex(' ')} new={new.hex(' ')}  byte0 {o0:#04x}->{n0:#04x}  Δ0={d0:#04x}  ΣΔ={dsum:#04x}  -ΣΔ={(-dsum)&0xFF:#04x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
