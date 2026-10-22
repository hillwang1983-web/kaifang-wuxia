"""找 0x61/0x02 外观包里那个来源不明的 `90 01`：把 123456 克隆成 8 份，每份改掉一组列，
重启原版服务端后逐个上线，看 `90 01` 在哪个变体里消失。

    python tools/appear_variants.py setup      # 克隆并改库（约 8 分钟，建议后台跑）
    python tools/appear_variants.py observe    # 逐个上线并打印另一端看到的外观包
    python tools/appear_variants.py cleanup

克隆号 jyid = 9999002 .. 9999009；登录密码 = 源号 123456。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_probe as lp  # noqa: E402
from multi_probe import Client  # noqa: E402

SRC = 123456
VARIANTS = {
    9999002: "zongxiaofei=0",
    9999003: "wuqi=0,wuqizhuangtai=0",
    9999004: "toukui=0,toukuizhuangtai=0",
    9999005: "yifu=0,yifuzhuangtai=0",
    9999006: "pifeng=0,pifengzhuangtai=0",
    9999007: "xianglian=0,huwan=0,jiezhi=0,xiezi=0",
    9999008: "combat_exp=0,kill_val=0,evil_val=0,fame_val=0,online_time=0,jy_money=0,study_count=0",
    9999009: "ysgengu=0,yswuxing=0,ysbili=0,ysjimin=0,jmkey=0",
}


def setup() -> None:
    for dst, sets in VARIANTS.items():
        lp.clone(SRC, dst)
        lp.sql(f"update renwu set {sets} where jyid={dst}", fetch=False)
        print("cloned", dst, sets, flush=True)


def observe(host="127.0.0.1", port=6731) -> None:
    lp.PASSWORD["value"] = str(SRC)
    watcher = Client("W", host, port, 8617293, None)
    assert watcher.login()
    for dst, sets in VARIANTS.items():
        time.sleep(2.7)
        c = Client("V", host, port, dst, str(SRC))
        if not c.login():
            print(dst, "login failed")
            continue
        frames = watcher.drain(1.2)
        for f in frames:
            if f.opcode == 0x02 and len(f.payload) == 96:
                print(dst, sets, "->", f.payload[53:63].hex(" "))
        c.sock.close()
        watcher.drain(0.5)


def cleanup() -> None:
    for dst in VARIANTS:
        lp.cleanup(dst, quiet=True)
        print("cleaned", dst, flush=True)


if __name__ == "__main__":
    {"setup": setup, "observe": observe, "cleanup": cleanup}[sys.argv[1]]()
