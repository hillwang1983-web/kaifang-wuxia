"""模拟客户端：连接原版服务端，走登录流程，把服务端回的每个包解码打印。

    python tools/sim_client.py --host 192.168.13.23 --jyid 8617293 --scenario login
    python tools/sim_client.py --host 192.168.13.23 --jyid 8617293 --scenario old

场景：
  login   只发登录包 01，等握手响应，再多听几秒（看服务端会不会主动发东西）。
  enter   login + 一个 C2S 0x19（「启动登录」，载荷 1 字节 00）。
  old     login + 按旧抓包里观察到的顺序补发登录阶段的其余包：0x74、0x18、0x19、0x2A、0x24、0x31。
          ⚠️ 这些包的载荷大多是**猜的**（旧笔记只有长度和零星字段），逐包标注在 SCENARIO_NOTES 里。

密钥处理（见 docs/协议模型.md）：首包用 0x9E；握手响应之后用 0x7D；
收到 `99 04 <种子>` 帧后，C2S 密钥改为 derive_key(种子)（公式尚未被真实流量验证，所以这里同时打印，便于核对
之后服务端发来的帧头里是不是同一个密钥）。S2C 解码不依赖状态（密钥在帧头里）。

建议通过抓包代理（tools/jyproxy.py）连接，这样双向字节都会被录下来。
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import (  # noqa: E402
    KEY_C2S_HANDSHAKE,
    KEY_DEFAULT,
    FrameReader,
    derive_key,
    encode_c2s,
)
from jyserver.opcodes import describe  # noqa: E402
from jyserver.text import decode_big5  # noqa: E402

UNKNOWN_CONST = 0x0005FCF7  # 登录包里的未知常量，照抄旧样本


class Session:
    def __init__(self, host: str, port: int):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(0.2)
        self.reader = FrameReader("s2c", resync=True)
        self.t0 = time.time()
        self.seq = 1
        self.base = KEY_DEFAULT  # C2S 密钥 = base XOR 序号（实测，见 docs/协议模型.md）；首包固定 0x9E
        self.follow_key_change = False
        self.frames = []  # 收到的全部帧
        self.closed = False

    def key_for(self, seq: int) -> int:
        return KEY_C2S_HANDSHAKE if seq == 1 else (self.base ^ (seq & 0xFF))

    def stamp(self) -> str:
        return f"+{time.time() - self.t0:6.2f}s"

    def send(self, opcode: int, payload: bytes, note: str = "") -> None:
        key = self.key_for(self.seq)
        wire = encode_c2s(opcode, payload, key=key, seq=self.seq, wide=False)
        print(f"{self.stamp()} C2S op=0x{opcode:02x} seq={self.seq} key=0x{key:02x} len={len(payload) + 4} {note}")
        print(f"          {payload[:48].hex(' ')}{' ...' if len(payload) > 48 else ''}")
        self.sock.sendall(wire)
        self.seq += 1

    def pump(self, seconds: float) -> int:
        """接收 seconds 秒，解码并打印；返回本次收到的帧数。"""
        end = time.time() + seconds
        got = 0
        while time.time() < end and not self.closed:
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                self.closed = True
                print(f"{self.stamp()} -- connection error")
                break
            if not data:
                self.closed = True
                print(f"{self.stamp()} -- server closed the connection")
                break
            for f in self.reader.feed(data):
                got += 1
                self.frames.append(f)
                text = ""
                if f.opcode in (0x14, 0x1A):
                    t = decode_big5(f.payload[1:])
                    if any("一" <= c <= "鿿" for c in t):
                        text = f"  BIG5: {t}"
                print(
                    f"{self.stamp()} S2C op=0x{f.opcode:02x} key=0x{f.key:02x} {'long' if f.wide else 'short'} "
                    f"len={f.total_length} {describe('s2c', f.opcode)}{text}"
                )
                print(f"          {f.payload[:48].hex(' ')}{' ...' if len(f.payload) > 48 else ''}")
                if f.opcode == 0x99 and len(f.payload) == 5 and f.payload[0] == 0x04:
                    new = derive_key(f.payload[1:])
                    note = "C2S base switched" if self.follow_key_change else "ignored (use --follow-key-change to apply)"
                    print(f"          ** key-change: seed {f.payload[1:].hex(' ')} -> derive_key=0x{new:02x}; {note}")
                    if self.follow_key_change:
                        self.base = new
        return got

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def login_payload(jyid: int, account: str) -> bytes:
    return struct.pack("<II", jyid, UNKNOWN_CONST) + account.encode("ascii")


def do_login(s: Session, jyid: int, account: str) -> bool:
    s.send(0x01, login_payload(jyid, account), "login (jyid + const + account)")
    n = s.pump(2.0)
    first = s.frames[0] if s.frames else None
    ok = bool(first and first.opcode == 0x01 and first.total_length == 34)
    if ok:
        print(f"{s.stamp()} -- handshake accepted; C2S key from now on = 0x{s.base:02x} XOR seq")
    else:
        print(f"{s.stamp()} -- no valid handshake response ({n} frames)")
    return ok


SCENARIO_NOTES = """\
旧抓包里登录阶段的 C2S 序列（opcode: 长度）：0x74:65  0x18:17  0x19:5  0x2A:30  0x24:32  0x31:33。
载荷来源与可信度：
  0x74  62 字节：首字节 02 + 15 个 LE32。旧样本只有前 4 个值(0x3bd134 0x19e157 0x179d0f 0x2832b6)，其余填 0   [猜]
  0x18  13 字节：内容未知，填 0                                                                           [猜]
  0x19  1 字节：未知，填 00                                                                               [猜]
  0x2A  26 字节：内容未知，填 0                                                                           [猜]
  0x24  28 字节：旧样本形如 (索引, 数量) 二元组 07 01 06 01 03 01 ...，这里照抄前 8 对再补 0              [半猜]
  0x31  29 字节：59 | 长度字节 | IP 文本 | BIG5 服务器名（旧样本里长度字节==IP 字符数）                    [半猜]
"""


def scenario_old(s: Session, ip: str) -> None:
    ints = [0x3BD134, 0x19E157, 0x179D0F, 0x2832B6] + [0] * 11
    s.send(0x74, b"\x02" + b"".join(struct.pack("<I", v) for v in ints), "[guess] 4 known ints + zeros")
    s.pump(0.5)
    s.send(0x18, bytes(13), "[guess]")
    s.pump(0.5)
    s.send(0x19, b"\x00", "[guess]")
    s.pump(0.5)
    s.send(0x2A, bytes(26), "[guess]")
    s.pump(0.5)
    pairs = [(7, 1), (6, 1), (3, 1), (4, 1), (8, 1), (0x0A, 1), (0x0C, 2), (0x0D, 1)]
    s.send(0x24, b"".join(bytes(p) for p in pairs) + bytes(28 - 2 * len(pairs)), "[half-guess] index/count pairs")
    s.pump(0.5)
    name = "淘寶遊戲者之家".encode("big5")
    body = bytes([0x59, len(ip)]) + ip.encode("ascii") + name
    body = (body + bytes(29))[:29]
    s.send(0x31, body, "[half-guess] server.ini report")
    s.pump(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--password", "--account", dest="account", default=None, help="明文密码（登录包末尾的 ASCII），默认等于 jyid 的十进制文本（测试号的密码就是这样）")
    ap.add_argument("--scenario", choices=["login", "enter", "old"], default="login")
    ap.add_argument("--listen", type=float, default=6.0, help="场景结束后再听多少秒")
    ap.add_argument("--notes", action="store_true", help="打印 old 场景各载荷的来源说明后退出")
    ap.add_argument("--follow-key-change", action="store_true", help="收到 99 04 换密钥帧后，把 C2S 的 base 改成 derive_key(种子)")
    ap.add_argument("--probe", default=None, metavar="OP[:HEX]", help="握手后只发这一帧（用正确的密钥规则），看服务端反应")
    ap.add_argument("--dump-json", default=None, metavar="PATH", help="把收到的全部 S2C 帧（完整载荷）写成 JSON，作为测试夹具")
    args = ap.parse_args()
    if args.notes:
        print(SCENARIO_NOTES)
        return 0

    account = args.account or str(args.jyid)
    s = Session(args.host, args.port)
    s.follow_key_change = args.follow_key_change
    print(f"connected {args.host}:{args.port}  scenario={args.scenario}  jyid={args.jyid}")
    try:
        if do_login(s, args.jyid, account):
            if args.probe:
                op_s, _, hex_s = args.probe.partition(":")
                s.send(int(op_s, 16), bytes.fromhex(hex_s.replace(" ", "")), "[probe]")
                s.pump(3.0)
            elif args.scenario == "enter":
                s.send(0x19, b"\x00", "[guess] start login")
                s.pump(3.0)
            elif args.scenario == "old":
                scenario_old(s, args.host)
        print(f"{s.stamp()} -- listening {args.listen:.0f}s more")
        s.pump(args.listen)
    finally:
        s.close()
    if args.dump_json:
        import json

        Path(args.dump_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dump_json).write_text(
            json.dumps(
                {
                    "note": "原版服务端对 C2S 登录(01)+启动登录(19) 的真实回包，由 tools/sim_client.py 录制；"
                    "wire 是线路原始字节(含密钥异或)，用 jyserver.codec 解码",
                    "jyid": args.jyid,
                    "frames": [
                        {
                            "opcode": f.opcode,
                            "key": f.key,
                            "wide": f.wide,
                            "length": f.total_length,
                            "payload": f.payload.hex(),
                            "wire": f.raw.hex(),
                        }
                        for f in s.frames
                    ],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.dump_json} ({len(s.frames)} frames)")
    ops = {}
    for f in s.frames:
        ops[f.opcode] = ops.get(f.opcode, 0) + 1
    print(
        f"\nsummary: {len(s.frames)} S2C frames, server_closed={s.closed}, skipped={s.reader.skipped}, "
        f"opcodes={ {f'0x{k:02x}': v for k, v in sorted(ops.items())} }"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
