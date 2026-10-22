"""新建角色探针：用一个全新的 jyid 登录原版服务端（账号会被自动建出来），摇点、建角色、再启动登录。

    python tools/create_probe.py --jyid 9999011 --password pw1234 --name test9011 [--sub 00] [--no-roll] [--name-hex ...]

每一步都打印服务端回的所有帧。账号和角色会真的写进原版数据库——用完请手动清理
（python tools/layout_probe.py cleanup --dst <jyid>；account 表也要清）。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import UNKNOWN_CONST, Client  # noqa: E402


def dump(tag, frames):
    if not frames:
        print(f"  {tag}: (no reply)")
    for f in frames:
        body = f.payload.hex(" ")
        print(f"  {tag}: 0x{f.opcode:02x}{' W' if f.wide else ''} key=0x{f.key:02x} len={len(f.payload)} {body[:180]}{'…' if len(body) > 180 else ''}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--name-hex", default="", help="直接给名字字节（十六进制），覆盖 --name")
    ap.add_argument("--sub", default="00", help="名字前面的 1 字节（十六进制）")
    ap.add_argument("--no-roll", action="store_true")
    ap.add_argument("--no-start", action="store_true")
    ap.add_argument("--encoding", default="gbk")
    ap.add_argument("--try-bases", default="0x34,0xcd,0x7d", help="创建后发 0x19 时依次试的 C2S 密钥基数")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0x7D, help="握手之后 C2S 密钥基数（默认 0x7D）")
    ap.add_argument("--full", action="store_true", help="发创建流程里的长 0x19（带地图、名字、昵称、属性…），而不是 1 字节的")
    ap.add_argument("--p0", default="00", help="长 0x19 载荷第 0 字节（含义未知）")
    ap.add_argument("--map", type=int, default=3304)
    ap.add_argument("--map-order", choices=("le", "be"), default="le")
    ap.add_argument("--nick", default="nick")
    ap.add_argument("--attrs", default="20,20,20,20,20,20,20", help="臂力,胆识,悟性,富源,定力,机敏,根骨（总和 ≤145）")
    ap.add_argument("--head", type=int, default=1)
    ap.add_argument("--mode", type=int, default=1)
    ap.add_argument("--month", type=int, default=5)
    ap.add_argument("--day", type=int, default=17)
    ap.add_argument("--dump", help="把创建后收到的登录序列每帧的 opcode/载荷写成 JSON")
    args = ap.parse_args()

    c = Client("N", args.host, args.port, args.jyid, args.password)
    c.send(0x01, struct.pack("<II", args.jyid, UNKNOWN_CONST) + args.password.encode("ascii"))
    dump("login", c.drain(1.5))
    c.base = args.base
    if not args.no_roll:
        c.send(0x76, b"")
        dump("roll", c.drain(1.0))
    name = bytes.fromhex(args.name_hex.replace(" ", "")) if args.name_hex else args.name.encode(args.encoding)
    c.send(0x20, bytes.fromhex(args.sub) + name)
    dump("create", c.drain(1.5))
    if not args.no_start:
        for base in [int(b, 0) for b in args.try_bases.split(",")]:
            c.base = base
            if args.full:
                nick = args.nick.encode(args.encoding)
                attrs = bytes(int(v) for v in args.attrs.split(","))
                map_bytes = struct.pack("<H" if args.map_order == "le" else ">H", args.map)
                payload = (
                    bytes.fromhex(args.p0) + map_bytes + bytes([len(name)]) + name + bytes([len(nick)]) + nick + attrs
                    + bytes([args.head, args.mode, args.month, args.day])
                )
                print("  0x19 payload:", payload.hex(" "))
                c.send(0x19, payload)
            else:
                c.send(0x19, b"\x00")
            frames = c.drain(2.5)
            print(f"  start with base 0x{base:02x}: {len(frames)} frames")
            if frames:
                break
        print("  start: opcodes", " ".join(f"{f.opcode:02x}" for f in frames))
        if args.dump:
            import json
            Path(args.dump).write_text(json.dumps([{"opcode": f.opcode, "wide": f.wide, "payload": f.payload.hex()} for f in frames]), encoding="utf-8")
        for f in frames:
            if f.opcode in (0x1E, 0x08, 0x32):
                dump("start", [f])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
