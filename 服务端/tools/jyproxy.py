"""TCP 中转代理：夹在原版客户端和原版服务端之间，逐块记录双向字节流（JSONL）。

做法来自 新网金 的抓包经验：Windows 允许「具体地址绑定」和「通配绑定」共存于同一端口，
且连接优先进入更具体的绑定，所以——

    客户端 ──> <局域网IP>:6731 (本代理，具体绑定)
                    └──> 127.0.0.1:6731 (真服务端，0.0.0.0 通配绑定)

启动顺序：先启动本代理，再启动 服务端.exe。server.ini 不用改（保持原来的局域网 IP，
并存成 GBK）。客户端会拒绝回环地址，所以不能把 server.ini 改成 127.x。

用法：
    python tools/jyproxy.py                       # 自动探测本机局域网 IP
    python tools/jyproxy.py --listen-ip 192.168.0.117 --out captures/login.jsonl

记录里含账号 ID 等信息，captures/ 已在 .gitignore 中，分享前请自行检查。
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import socket
import sys
import time
from pathlib import Path


def lan_ip() -> str:
    """不发送任何数据：对一个不可达地址 connect(UDP) 只是让系统选出口网卡。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Recorder:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._f = path.open("a", encoding="utf-8")
        self.path = path

    def write(self, conn: int, direction: str, data: bytes) -> None:
        rec = {"t": round(time.time(), 3), "conn": conn, "dir": direction, "hex": data.hex()}
        self._f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._f.flush()

    def event(self, conn: int, what: str) -> None:
        self._f.write(json.dumps({"t": round(time.time(), 3), "conn": conn, "event": what}) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


async def _pipe(reader, writer, conn: int, direction: str, rec: Recorder):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            rec.write(conn, direction, data)
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def start_proxy(listen_ip, listen_port, target_host, target_port, rec: Recorder, *, quiet=False):
    """启动代理并返回 asyncio.Server（调用者负责关闭）。"""
    counter = itertools.count(1)

    def say(msg: str) -> None:
        if not quiet:
            print(msg, flush=True)

    async def handle(creader, cwriter):
        conn = next(counter)
        peer = cwriter.get_extra_info("peername")
        rec.event(conn, f"open {peer}")
        say(f"[#{conn}] client {peer} connected")
        try:
            sreader, swriter = await asyncio.open_connection(target_host, target_port)
        except OSError as e:
            say(f"[#{conn}] cannot reach server {target_host}:{target_port}: {e}")
            rec.event(conn, f"server-unreachable {e}")
            cwriter.close()
            return
        await asyncio.gather(
            _pipe(creader, swriter, conn, "c2s", rec),
            _pipe(sreader, cwriter, conn, "s2c", rec),
        )
        rec.event(conn, "close")
        say(f"[#{conn}] closed")

    return await asyncio.start_server(handle, listen_ip, listen_port)


async def run(args) -> None:
    rec = Recorder(Path(args.out))
    server = await start_proxy(args.listen_ip, args.listen_port, args.target_host, args.target_port, rec)
    print(f"proxy listening on {args.listen_ip}:{args.listen_port} -> {args.target_host}:{args.target_port}")
    print(f"recording to {rec.path}  (Ctrl+C to stop)", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen-ip", default=None, help="默认自动探测本机局域网 IP")
    ap.add_argument("--listen-port", type=int, default=6731)
    ap.add_argument("--target-host", default="127.0.0.1")
    ap.add_argument("--target-port", type=int, default=6731)
    ap.add_argument("--out", default=time.strftime("captures/session-%Y%m%d-%H%M%S.jsonl"))
    args = ap.parse_args()

    if args.listen_ip is None:
        args.listen_ip = lan_ip()
        print(f"auto-detected LAN IP: {args.listen_ip}")
    if args.listen_ip.startswith("127.") or args.listen_ip == "0.0.0.0":
        print(
            "WARNING: 监听回环/通配地址。客户端会拒绝回环地址，且与真服务端的通配绑定无法共存；"
            "请指定 --listen-ip 为 server.ini 里的局域网 IP。",
            file=sys.stderr,
        )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
