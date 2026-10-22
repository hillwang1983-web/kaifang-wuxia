"""多客户端探针：同时登录两个账号，让其中一个发指令，看双方各收到什么（聊天、移动广播之类）。

    python tools/multi_probe.py --port 6731 --a 8617293 --b 1234567 --do A:04:00,74657374 --do B:06:...

--do WHO:OPCODE:HEX 可重复；WHO 是 A 或 B，HEX 是载荷（可含空格/逗号）。每条动作后等 --wait 秒，
打印双方在这段时间内收到的 S2C 帧。登录和「启动登录」(0x19) 的回包不打印。
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import KEY_C2S_HANDSHAKE, FrameReader, c2s_key, derive_key, encode_c2s  # noqa: E402

UNKNOWN_CONST = 0x0005FCF7


class Client:
    def __init__(self, name: str, host: str, port: int, jyid: int, password: str | None):
        self.name, self.jyid = name, jyid
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(0.05)
        self.rx = FrameReader("s2c", resync=True)
        self.seq = 0
        self.base = 0x7D  # C2S 密钥 = base ^ 序号；新账号的握手（模板 A）之后可能不是 0x7D
        self.password = password or str(jyid)
        self.rekeys: list[tuple[str, int]] = []

    def send(self, op: int, payload: bytes) -> None:
        self.seq += 1
        key = KEY_C2S_HANDSHAKE if self.seq == 1 else c2s_key(self.seq, self.base)
        self.sock.sendall(encode_c2s(op, payload, key=key, seq=self.seq, wide=False))

    def drain(self, seconds: float) -> list:
        out, end = [], time.time() + seconds
        while time.time() < end:
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            for f in self.rx.feed(data):
                if f.opcode == 0x99 and f.payload[:1] == b"\x04" and len(f.payload) >= 5:
                    # 服务端的换密钥帧：此后 C2S 密钥基数 = derive_key(种子)（实测见 docs/药品效果.md）
                    self.base = derive_key(f.payload[1:5])
                    self.rekeys.append((f.payload[1:5].hex(), self.base))
                out.append(f)
        return out

    def login(self) -> bool:
        self.send(0x01, struct.pack("<II", self.jyid, UNKNOWN_CONST) + self.password.encode("ascii"))
        got = self.drain(1.5)
        if not got or got[0].opcode != 0x01 or got[0].payload == b"\x00\x00":
            return False
        self.send(0x19, b"\x00")
        self.login_frames = self.drain(2.5)
        return True

    def position(self) -> tuple[int, int, int] | None:
        """登录序列里 0x08 帧给出的 (地图, x, y)。"""
        for f in getattr(self, "login_frames", []):
            if f.opcode == 0x08:
                return tuple(int.from_bytes(f.payload[i : i + 2], "little") for i in (0, 2, 4))
        return None


def show(name: str, frames: list) -> None:
    for f in frames:
        print(f"    {name} <- S2C 0x{f.opcode:02x}{' wide' if f.wide else ''} len={len(f.payload)} {f.payload.hex(' ')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--a", type=int, required=True)
    ap.add_argument("--b", type=int, required=True)
    ap.add_argument("--c", type=int, help="可选的第三个玩家 C")
    ap.add_argument("--login-detail", action="store_true", help="打印每个人登录序列里除常规 18 帧以外的帧")
    ap.add_argument("--do", action="append", default=[])
    ap.add_argument("--wait", type=float, default=1.5)
    args = ap.parse_args()

    clients: dict[str, Client] = {}
    for name, jyid in (("A", args.a), ("B", args.b), ("C", args.c)):
        if jyid is None:
            continue
        if clients:
            time.sleep(2.6)
        c = Client(name, args.host, args.port, jyid, None)
        if not c.login():
            print(f"{name} login failed")
            return 1
        clients[name] = c
        if args.login_detail:
            print(f"{name} login stream: " + " ".join(f"{f.opcode:02x}" for f in c.login_frames), f"pos={c.position()}")
        for other_name, other in clients.items():
            if other is not c:
                show(f"{other_name}(after {name} logged in)", other.drain(1.0))
    a, b = clients["A"], clients["B"]
    for spec in args.do:
        if spec.startswith("sleep:"):
            time.sleep(float(spec[6:]))
            continue
        who, op, hexs = (spec.split(":", 2) + [""])[:3]
        payload = bytes.fromhex(hexs.replace(",", " ").replace(" ", ""))
        print(f"== {who} sends 0x{int(op, 16):02x} {payload.hex(' ')}")
        clients[who].send(int(op, 16), payload)
        for n, c in clients.items():
            show(n, c.drain(args.wait))
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
