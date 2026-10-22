"""抓原版 0x4E 招收时发给对方的 S2C 0x54 帧（1800 多字节，内容是原版程序里的一整段常量模板），存成 data/org_recruit_template.json。

    python tools/org_capture54.py            # 要求原版刚重启过（组织表是空的）

用两个不同长度的组织名各抓一次，核对「前缀(队长 jyid + 名字长度 + 名字) + 固定模板(含组织号 LE16 的位置)」的拆法。
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

A, W, C = 8617293, 1234567, 123456


def grab(name: bytes, who_org: int) -> bytes:
    a = Client("A", "127.0.0.1", 6731, A, None)
    w = Client("W", "127.0.0.1", 6731, W, None)
    assert a.login() and w.login()
    a.drain(1.0)
    w.drain(1.0)
    a.send(0x45, name)
    a.drain(1.0)
    a.send(0x4E, struct.pack("<I", W))
    a.drain(0.5)
    got = [f for f in w.drain(1.5) if f.opcode == 0x54]
    a.sock.close()
    w.sock.close()
    assert got, "no 0x54"
    return got[0].payload


def main() -> int:
    name = sys.argv[1].encode("latin-1")
    p = grab(name, 0)
    print(name, len(p), p[:12].hex(" "))
    path = Path(__file__).resolve().parent.parent / "data" / "org_recruit_capture.json"
    out = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out[sys.argv[1]] = p.hex()
    path.write_text(json.dumps(out), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
