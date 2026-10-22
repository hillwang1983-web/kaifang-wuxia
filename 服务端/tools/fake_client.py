"""模拟客户端：只用来对原版服务端做登录握手，录下它回的包。

只发一个包：C2S 0x01 登录（密钥 0x9E，seq=1）。载荷 = jyid(LE32) + 0x0005fcf7(LE32) + 账号名 ASCII。
这个包的格式来自旧项目抓包（旧笔记里「只发首包」的回放实验，服务端回了 18 个包）；
中间那个 LE32 是未知常量，这里原样照抄。账号名取 jyid 的十进制文本（旧样本里账号名 == jyid）。

通过抓包代理（tools/jyproxy.py）连接，这样双向字节都会被记录。连接后只读取、不再发其他包，
等待 --wait 秒后正常关闭连接。

    python tools/fake_client.py --host 192.168.13.23 --jyid 8617293
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import KEY_C2S_HANDSHAKE, FrameReader, derive_key, encode_c2s  # noqa: E402
from jyserver.opcodes import describe  # noqa: E402

UNKNOWN_CONST = 0x0005FCF7  # 旧样本里的 f7 fc 05 00


def login_frame(jyid: int) -> bytes:
    payload = struct.pack("<II", jyid, UNKNOWN_CONST) + str(jyid).encode("ascii")
    return encode_c2s(0x01, payload, key=KEY_C2S_HANDSHAKE, seq=1, wide=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--wait", type=float, default=8.0, help="发完登录包后继续收多少秒")
    ap.add_argument(
        "--then",
        action="append",
        default=[],
        metavar="OP[:HEX]",
        help="握手响应到达后追加发送一帧，例如 --then 19:00（opcode 十六进制，可选载荷十六进制）；可重复",
    )
    ap.add_argument("--key", type=lambda x: int(x, 0), default=0x7D, help="追加帧使用的 C2S 密钥，默认 0x7D")
    ap.add_argument(
        "--after-key",
        action="append",
        default=[],
        metavar="OP[:HEX]",
        help="收到密钥更换帧(0x99 04 <种子>)后，改用 derive_key(种子) 作为 C2S 密钥再追加发送；可重复",
    )
    args = ap.parse_args()

    frame = login_frame(args.jyid)
    print(f"connect {args.host}:{args.port}, send login frame ({len(frame)} bytes): {frame.hex(' ')}")
    s = socket.create_connection((args.host, args.port), timeout=5)
    s.settimeout(0.5)
    s.sendall(frame)

    reader = FrameReader("s2c", resync=True)
    t0 = time.time()
    total = 0
    n = 0
    closed_by_server = False
    pending_then = list(args.then)
    pending_after_key = list(args.after_key)
    cur_key = args.key
    seq = 2
    while time.time() - t0 < args.wait:
        try:
            data = s.recv(65536)
        except socket.timeout:
            data = None
        if data is None:
            continue
        if not data:
            closed_by_server = True
            break
        total += len(data)
        first = n == 0
        for f in reader.feed(data):
            n += 1
            print(
                f"+{time.time() - t0:5.2f}s #{n:<2} op=0x{f.opcode:02x} key=0x{f.key:02x} "
                f"{'long ' if f.wide else 'short'} len={f.total_length:<5} {describe('s2c', f.opcode)}"
            )
            print(f"        {f.payload[:40].hex(' ')}{' ...' if len(f.payload) > 40 else ''}")
            if f.opcode == 0x99 and len(f.payload) == 5 and f.payload[0] == 0x04:
                cur_key = derive_key(f.payload[1:])
                print(f"        ** key-change frame: seed {f.payload[1:].hex(' ')} -> derive_key = 0x{cur_key:02x}")
                for spec in pending_after_key:
                    op_s, _, hex_s = spec.partition(":")
                    extra = encode_c2s(int(op_s, 16), bytes.fromhex(hex_s.replace(" ", "")), key=cur_key, seq=seq, wide=False)
                    print(f"+{time.time() - t0:5.2f}s SEND op=0x{int(op_s, 16):02x} seq={seq} key=0x{cur_key:02x}: {extra.hex(' ')}")
                    s.sendall(extra)
                    seq += 1
                pending_after_key = []
        if first and pending_then:  # 握手响应到了，按顺序追加发送
            for spec in pending_then:
                op_s, _, hex_s = spec.partition(":")
                extra = encode_c2s(int(op_s, 16), bytes.fromhex(hex_s.replace(" ", "")), key=args.key, seq=seq, wide=False)
                print(f"+{time.time() - t0:5.2f}s SEND op=0x{int(op_s, 16):02x} seq={seq} key=0x{args.key:02x}: {extra.hex(' ')}")
                s.sendall(extra)
                seq += 1
            pending_then = []
    s.close()
    print(
        f"done: {n} frames, {total} bytes, skipped={reader.skipped}, leftover={len(reader.pending)}, "
        f"server_closed={closed_by_server}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
