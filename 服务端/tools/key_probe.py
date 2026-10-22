"""黑盒探测：服务端解 C2S 帧用的密钥是哪个字节？

背景：反编译显示服务端解 C2S 时用的不一定是帧头里的密钥，而是由序号等推出来的（算法在运行时才填充的对象里，
静态上看不到）。这里把第二个包（序号 2）用 0..255 每个密钥字节各发一次：
密钥对了，服务端会真正处理这个包（回包或断开连接）；错了就默默忽略。

每个密钥用一条新连接：登录(01) → 收握手响应 → 发探针帧 → 等 --wait 秒看反应。
默认探针是 C2S 0x76（摇点；要么回 0x5A 包，要么因为角色已存在而断开，两种都可观察，且不改库）。

    python tools/key_probe.py --host 192.168.13.23 --jyid 8617293 --out captures/keyprobe.jsonl
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jyserver.codec import KEY_C2S_HANDSHAKE, FrameReader, encode_c2s  # noqa: E402

UNKNOWN_CONST = 0x0005FCF7


def one_try(host: str, port: int, jyid: int, key: int, seq: int, opcode: int, payload: bytes, wait: float) -> dict:
    s = socket.create_connection((host, port), timeout=5)
    s.settimeout(0.1)
    reader = FrameReader("s2c", resync=True)
    result = {"key": key, "handshake": False, "frames": [], "closed": False}

    def drain(seconds: float, until_first: bool = False) -> None:
        end = time.time() + seconds
        while time.time() < end and not result["closed"]:
            try:
                data = s.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                result["closed"] = True
                return
            if not data:
                result["closed"] = True
                return
            for f in reader.feed(data):
                result["frames"].append({"op": f"0x{f.opcode:02x}", "key": f"0x{f.key:02x}", "len": f.total_length, "payload": f.payload[:24].hex(" ")})
            if until_first and result["frames"]:
                return

    try:
        login = struct.pack("<II", jyid, UNKNOWN_CONST) + str(jyid).encode("ascii")
        s.sendall(encode_c2s(0x01, login, key=KEY_C2S_HANDSHAKE, seq=1, wide=False))
        drain(1.5, until_first=True)
        result["handshake"] = bool(result["frames"]) and result["frames"][0]["op"] == "0x01"
        if not result["handshake"]:
            return result
        before = len(result["frames"])
        s.sendall(encode_c2s(opcode, payload, key=key, seq=seq, wide=False))
        drain(wait)
        result["reaction_frames"] = result["frames"][before:]
    finally:
        try:
            s.close()
        except OSError:
            pass
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=6731)
    ap.add_argument("--jyid", type=int, required=True)
    ap.add_argument("--seq", type=int, default=2, help="探针帧的序号")
    ap.add_argument("--op", type=lambda x: int(x, 16), default=0x76, help="探针 opcode（十六进制）")
    ap.add_argument("--payload", default="", help="探针载荷（十六进制）")
    ap.add_argument("--wait", type=float, default=0.8, help="发探针后等待反应的秒数")
    ap.add_argument("--gap", type=float, default=0.4, help="两次尝试之间的间隔")
    ap.add_argument("--keys", default="0-255", help="要试的密钥范围，如 0-255 或 0x70-0x80")
    ap.add_argument("--out", default="captures/keyprobe.jsonl")
    args = ap.parse_args()

    lo, _, hi = args.keys.partition("-")
    keys = range(int(lo, 0), int(hi, 0) + 1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = bytes.fromhex(args.payload.replace(" ", ""))
    hits = []
    with out.open("w", encoding="utf-8") as fh:
        for k in keys:
            r = one_try(args.host, args.port, args.jyid, k, args.seq, args.op, payload, args.wait)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            reacted = bool(r.get("reaction_frames")) or (r["handshake"] and r["closed"])
            flag = ""
            if not r["handshake"]:
                flag = "NO-HANDSHAKE"
            elif reacted:
                flag = "REACTION  closed=%s frames=%s" % (r["closed"], [f["op"] for f in r.get("reaction_frames", [])])
                hits.append(k)
            print(f"key 0x{k:02x}: {flag}", flush=True) if flag else None
            time.sleep(args.gap)
    print(f"\ndone. keys with a reaction: {[f'0x{k:02x}' for k in hits]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
