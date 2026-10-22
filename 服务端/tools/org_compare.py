"""组织对照：同一串「谁:操作码:载荷」，对原版(6731)和新服务端(6732)各跑一遍，比每一方收到的帧。

    python tools/org_compare.py [场景名 ...]

三个号 A=8617293、W=1234567、C=123456，全放在地图 2200（组织不看地图）。伪操作：`X:close:` 断开，`X:open:` 重新登录。
每个场景前脚本自己重启原版（restart_original.ps1）和新服务端（组织表是内存数组、没有删除，号码不回收，不重启就会串）。
`--original` = 只跑原版并打印回包。
"""

from __future__ import annotations

import difflib
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402
from team_compare import MAPS, NOISE, WHO, set_maps  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAPS.update({"A": 2200, "W": 2200, "C": 2200})

SCENARIOS = {
    "create": ["A:45:6162", "A:45:6364", "W:45:6162", "W:45:4142", "W:45:616220", "C:45:3132333435363738393031323334353637383930", "A:56:06", "A:56:04", "A:56:05"],
    "recruit": ["A:45:6162", "A:4E:{1234567}", "W:4F:01{8617293}", "A:4F:07", "W:4F:07", "C:4F:07", "A:4E:{123456}", "W:4E:{123456}", "A:4E:{99999}", "A:4E:{8617293}", "C:4F:01{1234567}", "C:4F:07"],
    "chat": ["A:45:6162", "W:4F:01{8617293}", "C:4F:01{8617293}", "C:4F:01{8617293}", "A:02:0568656c6c6f", "W:02:0561", "C:02:0562", "A:02:05", "A:02:0501", "A:02:01aa", "A:02:04aa"],
    "kick": ["A:45:6162", "W:4F:01{8617293}", "C:4F:01{8617293}", "A:50:00000000b4e5c0b8aacca4a7ae613939", "A:4F:07", "A:02:0561", "W:02:0561", "W:4E:{123456}", "W:45:6364", "C:50:00000000b4e5c0b8aacca4a7ae613939", "C:50:000000003132333435", "A:50:00000000", "A:50:00000000aabbcc", "A:50:{1234567}"],
    "kicked-state": ["A:45:6162", "W:4F:01{8617293}", "A:50:00000000b4e5c0b8aacca4a7ae613939", "W:45:6364", "A:4E:{1234567}", "W:4F:01{8617293}", "A:4F:07", "W:51:01", "W:4F:01{8617293}"],
    "leave": ["A:45:6162", "W:4F:01{8617293}", "W:51:01", "A:4F:07", "W:4F:07", "A:02:0561", "W:02:0561", "W:45:6364", "A:4E:{1234567}", "W:4F:01{8617293}", "W:51:01", "W:51:01", "C:51:01", "A:51:01", "A:4E:{123456}", "A:4F:07"],
    "non-leader": ["A:45:6162", "W:4F:01{8617293}", "W:4E:{123456}", "C:4E:{1234567}", "C:4F:01{8617293}", "C:4E:{99999}"],
    "accept-edge": ["C:4F:01{1234567}", "W:4F:01{8617293}", "A:45:6162", "W:4F:01{8617293}", "W:4F:01{99999}", "W:4F:", "W:4F:01", "W:4F:0200000000", "W:4F:0100", "A:4F:09"],
    "offline-member": ["A:45:6162", "W:4F:01{8617293}", "C:4F:01{8617293}", "W:close:", "A:4F:07", "C:02:0561", "A:02:0561", "W:open:", "W:4F:07", "A:4F:07", "W:02:0561", "C:02:0561", "W:45:6364", "W:4E:{123456}"],
    "two-orgs": ["A:45:6162", "W:45:6364", "A:4E:{123456}", "W:4E:{123456}", "C:4F:01{1234567}", "A:4F:07", "W:4F:07", "C:4F:07", "C:02:0561", "A:02:0561", "W:02:0561", "C:51:01", "C:4F:01{8617293}", "C:02:0562"],
    "noorg-ops": ["C:50:00000000b4e5c0b8aacca4a7ae613939", "C:51:01", "C:4F:07", "C:02:0561", "C:56:06", "C:56:04", "C:56:05", "C:56:07", "C:4E:00", "C:4E:aabbcc", "C:50:00", "C:51:02", "C:02:05"],
    "empty-45": ["C:45:", "C:56:06"],
    "empty-45b": ["A:45:6162", "W:45:", "W:56:06"],
    "empty-4e": ["A:45:6162", "A:4E:", "A:56:06"],
    "empty-4f": ["A:4F:", "A:56:06"],
    "empty-50": ["A:50:", "A:56:06"],
    "empty-51": ["A:51:", "A:56:06"],
    "empty-56": ["A:56:", "A:56:06"],
    "create-edge": ["A:45:" + "61" * 60, "W:45:fffe", "C:45:" + "61" * 60, "A:45:6162"],
    "leader-leaves": ["A:45:6162", "W:4F:01{8617293}", "A:51:01", "A:4E:{123456}", "W:4E:{123456}", "A:02:0561", "W:02:0561", "A:4F:07", "W:4F:07", "A:45:6364"],
}


def restart_original() -> None:
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "restart_original.ps1")], capture_output=True)


_NEW = None


def restart_new() -> None:
    """杀掉占着 6732 的进程，重新起新服务端（组织表在内存里）。"""
    global _NEW
    subprocess.run(
        ["powershell", "-Command", "Get-NetTCPConnection -LocalPort 6732 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"],
        capture_output=True,
    )
    time.sleep(1.0)
    _NEW = subprocess.Popen(
        [sys.executable, "-m", "jyserver.server", "--host", "0.0.0.0", "--port", "6732", "--tick", "0"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3.0)


def run(port: int, steps: list[str]) -> list[str]:
    time.sleep(2.0)
    clients: dict[str, Client] = {}
    for name, jy in WHO.items():
        c = Client(name, "127.0.0.1", port, jy, None)
        if not c.login():
            return [f"login failed for {name}"]
        clients[name] = c
    for c in clients.values():
        c.drain(1.5)
    out: list[str] = []

    def show(tag, frames):
        for f in frames:
            if f.opcode in NOISE or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            if f.opcode == 0x14 and b"\xa1\x41\xb3\xd0\xa5\xdf\xa4\x46\xb2\xd5\xc2\xb4\xa1\x52" not in f.payload:
                continue  # 只比较「創立了組織」公告；定时公告、登录 / 下线公告不比较
            if f.opcode in (0x60, 0x05, 0x02, 0x82, 0x7B):
                continue  # 上线 / 下线 / 可见性帧
            out.append(f"    {tag} <- 0x{f.opcode:02x} {f.payload.hex(' ')}")

    for step in steps:
        who, op, hx = step.split(":", 2)
        if op == "close":
            clients[who].sock.close()
            out.append(f"== {who} disconnects")
            del clients[who]
            for name, c in clients.items():
                show(name, c.drain(1.0))
            continue
        if op == "open":
            c = Client(who, "127.0.0.1", port, WHO[who], None)
            ok = c.login()
            c.drain(1.0)
            out.append(f"== {who} logs in ({ok})")
            clients[who] = c
            for name, cc in clients.items():
                show(name, cc.drain(0.5) if name != who else [])
            continue
        hx = re.sub(r"\{(\d+)\}", lambda m: struct.pack("<I", int(m.group(1))).hex(), hx)
        payload = bytes.fromhex(hx.replace(" ", ""))
        out.append(f"== {who} sends 0x{int(op, 16):02x} {payload.hex(' ')}")
        try:
            clients[who].send(int(op, 16), payload)
            for name, c in clients.items():
                show(name, c.drain(0.8 if name == who else 0.3))
        except OSError:
            out.append("!! connection lost (server crashed?)")
            return out
    for c in clients.values():
        try:
            c.sock.close()
        except OSError:
            pass
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only_original = "--original" in sys.argv
    names = args or list(SCENARIOS)
    bad = 0
    for name in names:
        res = {}
        for port in (6731, 6732):
            if only_original and port == 6732:
                continue
            if port == 6731:
                restart_original()
            else:
                restart_new()
            set_maps()
            res[port] = run(port, SCENARIOS[name])
            time.sleep(1.0)
        if only_original:
            print(f"### {name} (original)")
            print("\n".join(res[6731]))
            continue
        same = res[6731] == res[6732]
        print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
        if not same:
            bad += 1
            for l in difflib.unified_diff(res[6731], res[6732], "original", "new", lineterm="", n=1):
                print("   ", l[:260])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
