#!/usr/bin/env python3
"""Npc*.Dat 解码 + 型号 -> 精灵号映射的自测（需要客户端 share\\dat；精灵图集那几项需要已预生成的 web\\sprites\\npc）。
    python test_npcsprite.py
"""
import csv
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npcdat  # noqa: E402

RES = []
HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DATA = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def main():
    # 记录布局：237 字节 × 条数（文件第 0 条是占位）
    for fn, n in (("Npc.Dat", 5019), ("Npc1.Dat", 5711), ("Npc2.Dat", 440), ("Npc3.Dat", 6429), ("Npc4.Dat", 1347)):
        p = os.path.join(npcdat.DAT_DIR, fn)
        check(os.path.getsize(p) == n * npcdat.R, "%s = %d × 237 字节" % (fn, n))
    t = npcdat.load(os.path.join(npcdat.DAT_DIR, "Npc3.Dat"))
    check(10001 in t and 38166 in t and 38268 in t, "解码后记录首 u16 = 型号（10001 / 倭寇 38166 / 野蛮人 38268 都在）")
    sp = lambda m: struct.unpack_from("<H", t[m], 0x19)[0]
    check(sp(38166) == 10111 and sp(38268) == 10348, "倭寇 → 精灵 10111，野蛮人 → 精灵 10348（记录 +0x19）")
    check(npcdat.decode_record(b"\x00" * 237)[0:2] == struct.pack("<H", 0xA7B), "全零记录解码：首 u16 = 异或常量 0xA7B")
    # 型号覆盖率（MOB 表里的怪、有精灵的比例）
    mob = [int(r[0]) for r in list(csv.reader(open(os.path.join(SERVER_DATA, "MOB数据.csv"), encoding="gbk", errors="replace", newline="")))[1:] if r and r[0].isdigit()]
    spr_dir = os.path.join(HERE, "web", "sprites", "npc")
    have = {int(f[:-5]) for f in os.listdir(spr_dir) if f.endswith(".json")} if os.path.isdir(spr_dir) else set()
    if len(have) > 900:           # 已经全量预生成
        ok = sum(1 for m in mob if m in t and sp(m) in have)
        check(ok / len(mob) > 0.9, "MOB 表 %d 只怪里 %d 只有精灵（%.0f%%）" % (len(mob), ok, 100 * ok / len(mob)))
    for sid in (10111, 10348):
        jp = os.path.join(spr_dir, "%d.json" % sid)
        if os.path.isfile(jp):
            d = json.load(open(jp, encoding="utf8"))
            S = d["cps"]["S"]
            check(S["fpd"] == 4 and len(S["frames"]) == 32 and all(os.path.isfile(os.path.join(spr_dir, p)) for p in d["pages"]), "精灵 %d：站立 8 方向 × 4 帧，图集页在" % sid)
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
