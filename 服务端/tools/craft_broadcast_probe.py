"""合成成功后的全服公告探针：对原版连发 N 次同一配方，数收到几条 0x04（「玩家…，合成得到：…」）。

    python tools/craft_broadcast_probe.py 47 07 05 05 ...   # 配方键，两个字节一组，十六进制
用来弄清哪些成品会触发公告（0x88c108 的收尾段：随机数 < 6 且成品在物品表里被标了 1）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import craft_compare as cc  # noqa: E402
from multi_probe import Client  # noqa: E402

N = 20


def main() -> int:
    args = sys.argv[1:]
    keys = [f"{args[i].upper()} {args[i + 1].upper()}" for i in range(0, len(args), 2)]
    import subprocess

    for key in keys:
        rec = cc.RECIPES[key]
        payload = bytes(int(x, 16) for x in key.split())
        sc = dict(renwu=dict(luk=30, dangqianshen=210), jineng={}, bag={i: n * N for i, n in rec["needs"]}, extra=[rec["product"]], skill=rec["skill"], cmds=[])
        subprocess.run(["powershell", "-Command", "Get-Process -Name 服务端 -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
        time.sleep(2)
        cc.set_state(sc)
        cc.restart_original()
        time.sleep(3)
        a = Client("A", "127.0.0.1", 6731, cc.JY, None)
        assert a.login()
        a.drain(1.0)
        hits, texts = 0, []
        for _ in range(N):
            try:
                a.send(0x1B, payload)
            except OSError:
                print("连接断了，第", _, "次")
                break
            for f in a.drain(0.6):
                if f.opcode == 0x04:
                    hits += 1
                    texts.append(f.payload.hex(" "))
        a.sock.close()
        print(f"{key} product={rec['product']} 公告 {hits}/{N}", texts[:1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


