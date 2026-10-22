#!/usr/bin/env python3
"""测试客户端：直接连游戏服务端，按已逆向并经真实流量核对的帧格式收发，只用标准库。

线路格式（C2S）:  F6 11 <序号> + XOR(密钥, F4 44 <总长度> <类型> <载荷>)
C2S 密钥：序号 1（登录包）固定 0x9e；之后服务端期望 0x7D XOR 序号（网金复刻项目对序号 2~5 逐个探测 256 个密钥得出；
用固定 0x7d 的包会被静默忽略）。S2C：握手帧 0x9f，之后 0x7d；服务端发 99 04 <种子> 换密钥（见 packet_proxy.derive_key）。

模式
  被动监听（默认，不发送任何数据）:
      python test_client.py
  握手测试（登录帧，与 C:\\游戏\\网金复刻\\tools\\fake_client.py 的首包相同）:
      python test_client.py --login-jyid 123456          # 干跑：只显示要发送的字节，不连接
      python test_client.py --login-jyid 123456 --go     # 真正连接并发送这一个包，然后监听
  原始字节 / 单个帧:
      python test_client.py --send-hex "..."             # 线上原始字节，不加前缀不加密
      python test_client.py --send-frame 0x19:00 --key 0x7d --seq 2

登录帧载荷 = jyid(小端32位) + 0x0005fcf7(小端32位，含义未知，照抄抓包) + 账号名(jyid 的十进制文本，ASCII)。
注意：原服务端强制单点登录，同一个 jyid 在别处在线时会把对方挤掉；请使用专门的测试账号。
"""
import argparse
import os
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packet_proxy as pp  # noqa: E402

C2S_PREFIX = bytes([0xF6, 0x11])
UNKNOWN_CONST = 0x0005FCF7
KEY_C2S_FIRST = 0x9E
# 服务端对登录包的握手响应（来自 login-1.jsonl，逐字节一致出现了 4 次；线上 35 字节 = 34 字节帧 + 1 个 00）
EXPECTED_HANDSHAKE = bytes.fromhex(
    "6bdbbd9e9e3d23b7a899392034f1322895384533d04779477931df8e888b8c8b8b8a00")


def c2s_wire(msg_type: int, payload: bytes, key: int, seq: int) -> bytes:
    return C2S_PREFIX + bytes([seq & 0xFF]) + pp.encode_frame(msg_type, payload, key)


def login_frame(jyid: int, seq: int = 1) -> bytes:
    payload = struct.pack("<II", jyid, UNKNOWN_CONST) + str(jyid).encode("ascii")
    return c2s_wire(0x01, payload, KEY_C2S_FIRST, seq)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--listen-seconds", type=float, default=6.0, help="发完之后继续监听多久")
    ap.add_argument("--login-jyid", type=int, help="发送登录帧（类型 0x01）使用的测试账号 jyid；默认干跑")
    ap.add_argument("--go", action="store_true", help="真正连接并发送；没有它 --login-jyid 只显示字节")
    ap.add_argument("--send-hex", action="append", default=[], help="连接后依次发送的线上原始字节")
    ap.add_argument("--send-frame", action="append", default=[], help="类型:载荷hex，加前缀并按 --key 异或")
    ap.add_argument("--key", type=lambda s: int(s, 0), default=None,
                    help="--send-frame 用的异或密钥；不给则按服务端实测规则 0x7D XOR 序号（序号 1 固定 0x9e）")
    ap.add_argument("--seq", type=int, default=2, help="--send-frame 起始序号")
    ap.add_argument("--gap", type=float, default=1.0, help="两次发送之间等待的秒数")
    ap.add_argument("--log", help="JSONL 日志（含原始数据块，可用 packet_proxy.py --replay 重新解码）")
    args = ap.parse_args()

    sends = []
    if args.login_jyid is not None:
        lf = login_frame(args.login_jyid)
        plain = bytes(b ^ KEY_C2S_FIRST for b in lf[3:])
        print("将要发送的登录帧（%d 字节）：" % len(lf))
        print("  线路字节   :", lf.hex(" "))
        print("  拆开       : F6 11 01 | 用密钥 0x%02x 异或后的明文帧" % KEY_C2S_FIRST)
        print("  明文帧     :", plain.hex(" "))
        print("  载荷含义   : jyid=%d(小端) | 常量 0x%08x(小端) | 账号名 %r" % (
            args.login_jyid, UNKNOWN_CONST, str(args.login_jyid)))
        if not args.go:
            print("\n干跑模式：没有连接，也没有发送任何数据。确认无误后加 --go。")
            return
        sends.append(("login", lf))
    for h in args.send_hex:
        sends.append(("raw", bytes.fromhex(h.replace(" ", ""))))
    seq = args.seq
    for sf in args.send_frame:
        t, _, pl = sf.partition(":")
        k = args.key if args.key is not None else (KEY_C2S_FIRST if seq == 1 else (0x7D ^ seq) & 0xFF)
        sends.append(("frame", c2s_wire(int(t, 0), bytes.fromhex(pl.replace(" ", "")), k, seq)))
        seq += 1

    rep = pp.Reporter(args.log, quiet=False, raw=True)
    sess = pp.Session(1, rep)
    first_s2c = []

    t0 = time.time()
    print("连接 %s:%d ..." % (args.host, args.port))
    s = socket.create_connection((args.host, args.port), timeout=5)
    s.settimeout(0.2)
    rep({"ev": "open", "conn": 1, "t": time.time(), "peer": "test_client -> %s:%d" % (args.host, args.port)})
    print("已连接。")

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                data = s.recv(65536)
            except socket.timeout:
                sess.flush_idle("S2C")
                continue
            except OSError as e:
                print("连接错误:", e)
                return False
            if not data:
                print("服务端关闭了连接（%.1f 秒后）" % (time.time() - t0))
                return False
            if not first_s2c:
                first_s2c.append(data)
            rep({"ev": "chunk", "conn": 1, "dir": "S2C", "t": time.time(), "hex": data.hex()})
            print("<- 收到 %d 字节: %s" % (len(data), data[:64].hex(" ") + (" ..." if len(data) > 64 else "")))
            sess.feed("S2C", data)
        return True

    alive = pump(1.0)           # 先静听 1 秒，看服务端会不会先说话
    for kind, payload in sends:
        if not alive:
            break
        print("-> 发送(%s) %d 字节: %s" % (kind, len(payload), payload[:64].hex(" ")))
        rep({"ev": "chunk", "conn": 1, "dir": "C2S", "t": time.time(), "hex": payload.hex()})
        sess.feed("C2S", payload)
        s.sendall(payload)
        alive = pump(args.gap)
    if alive:
        pump(args.listen_seconds)
    try:
        s.close()
    except OSError:
        pass
    rep.summary()
    if args.login_jyid is not None:
        if first_s2c and first_s2c[0] == EXPECTED_HANDSHAKE:
            print("握手响应与 login-1.jsonl 逐字节一致（35 字节）。")
        elif first_s2c:
            print("握手响应与 login-1.jsonl 不一致：收到 %d 字节，前 35 字节%s" % (
                len(first_s2c[0]), "相同" if first_s2c[0][:35] == EXPECTED_HANDSHAKE else "不同"))
        else:
            print("没有收到服务端的任何响应。")


if __name__ == "__main__":
    main()
