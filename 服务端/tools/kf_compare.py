"""武功装备 / 删除对照：同一份 kf 表、同一串指令，对原版(6731)和新服务端(6732)各跑一遍，比 A 和旁观号 W 收到的帧，以及下线后的 kf 表。

    python tools/kf_compare.py [场景名 ...]

A=8617293 的 kf 表每次按场景的 kf 清单重写（MySQL 和 SQLite 两边）；跑完请用 restore_fixture.py 还原，并重启原版。
"""

from __future__ import annotations

import difflib
import json
import sqlite3
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multi_probe import Client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MYSQL = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\MySQL5.5\bin\mysql.exe"
JY, WATCH = 8617293, 1234567
PW = "38363137323933"  # 账号密码 8617293 的十六进制
BAD = "38363137323934"
KF = [(1000, 10, 100), (1002, 5, 50), (1003, 3, 30), (1004, 4, 40), (1211, 2, 20), (3860, 10, 0), (9999, 3, 0)]


def le(n: int) -> str:
    return struct.pack("<H", n).hex()


def tp(m: int, x: int = 100, y: int = 100):
    return (0x5D, le(m) + le(x) + le(y))


def ev(m: int, e: int):
    return (0x6B, "00000000" + le(m) + le(e))


BASE_STATS = dict(str=30, crg=30, wint=30, luk=30, dex=30, agi=30, vit=30, fame_val=0, exp_val=0, combat_exp=0, online_time=0, school=0)
def _data_csv(name: str):
    import csv
    import io

    raw = (Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data") / name).read_bytes().decode("gbk", errors="replace")
    return list(csv.reader(io.StringIO(raw)))


def pure_learn_events():
    """事件.csv 里结果全是「武功:」语句的事件 (地图, 事件id)，每个 (地图,事件) 只取一次。"""
    seen, out = set(), []
    for r in _data_csv("事件.csv")[1:]:
        if len(r) > 8 and "武功:" in r[7]:
            sts = [s for s in r[7].split(";") if s.strip()]
            if all(s.startswith("武功:") for s in sts) and (r[0], r[2]) not in seen:
                seen.add((r[0], r[2]))
                out.append((int(r[0]), int(r[2])))
    return out


def prereq_ids():
    ids = set()
    for r in _data_csv("防挂验证.csv")[1:]:
        if len(r) > 6 and r[0].strip().isdigit():
            for i in (1, 3, 5):
                if r[i].strip().isdigit() and int(r[i]):
                    ids.add(int(r[i]))
    return sorted(ids)


def learn_cmds():
    cmds, cur = [], None
    for m, e in pure_learn_events():
        if m != cur:
            cmds.append(tp(m))
            cur = m
        cmds.append(ev(m, e))
    return cmds


def prereq_kf(level: int):
    return [(k, level, 0) for k in prereq_ids()]


def stats(n, **kw):
    return {**BASE_STATS, **dict(str=n, crg=n, wint=n, luk=n, dex=n, agi=n, vit=n), **kw}


def rand_profile(seed: int):
    """随机但可复现的人物状态：属性 / 名声 / 历练 / 实战 / 上线时间 / 门派都落在各条件的门槛附近，前置武功等级随机（有的没有）。"""
    import random

    r = random.Random(seed)
    ren = stats(0, **{c: r.randint(8, 45) for c in ("str", "crg", "wint", "luk", "dex", "agi", "vit")})
    ren.update(fame_val=r.choice([0, 500, 2000, 5000, 12000]), exp_val=r.choice([0, 1000, 5000, 20000, 60000]), combat_exp=r.choice([0, 1000000, 3000000, 5000000, 9000000]),
               online_time=48 * r.choice([0, 100, 1000, 1600, 3000]), school=r.choice([0, 0, 10, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23, 26, 30, 33, 38]))
    kf = [(k, r.choice([0, 20, 40, 50, 60, 80, 100, 200]), 0) for k in prereq_ids() if r.random() < 0.8]
    return kf, ren


BOOKS2 = [(35022, 2), (35031, 2), (40177, 2)]


def book(iid: int, hi: int = 0, dur: int = 0):
    return (0x60, le(iid & 0xFFFF) + le(hi) + f"{dur:02x}")


XD_SAMPLE = [(10003, 1014, 2411), (10004, 1018, 2409), (10005, 1008, 2408), (10008, 1019, 2415), (10008, 8004, 2415), (10008, 8011, 2415), (10029, 1007, 2408), (10039, 8006, 2408), (10041, 1005, 2416), (10130, 4249, 5000), (12016, 1206, 4101), (13009, 8010, 3311)]


BASIC_COLS = ["daofa", "qiangfa", "jianfa", "bianfa", "gunfa", "neigong", "cishu", "shenfa", "dushu", "yishu", "zhenfa", "boji", "shanduo", "anqi", "chaizhao", "dushushizi", "jiaoyi"]
XD_BASIC_RENWU = {**{c: 3 for c in BASIC_COLS}, **{c + "exp": 0 for c in BASIC_COLS}, **dict(str=31, crg=32, wint=33, luk=34, dex=35, agi=36, vit=37, study_count=30000, school=0)}
XD_BASIC_WATCH = tuple(BASIC_COLS) + tuple(c + "exp" for c in BASIC_COLS) + ("study_count", "str", "crg", "wint", "luk", "dex", "agi", "vit", "dangqianjing", "zuidajing", "dangqianxue", "zuidaxue", "dangqiannei", "zuidanei")
XD_BASIC = [(10039, 8001, 2408), (11016, 8002, 2501), (10039, 8003, 2408), (10008, 8004, 2415), (10039, 8005, 2408), (10039, 8006, 2408), (10039, 8007, 2408), (10039, 8008, 2408),
            (33001, 8009, 1201), (13009, 8010, 3311), (10008, 8011, 2415), (10039, 8012, 2408), (10039, 8013, 2408), (11016, 8014, 2501), (10039, 8015, 2408), (39032, 8017, 1302)]


def xd(master: int, kid: int, pts: int, seq: int, chk: int):
    """C2S 0x5E 消点：师傅 LE16 | 武功 LE16 | 点数 LE16 | 序号 LE32 | 校验字节"""
    return (0x5E, le(master) + le(kid) + le(pts) + struct.pack("<I", seq).hex() + f"{chk:02x}")


BOOK_CMDS = [book(35022), book(35031), book(40177)]

SCENARIOS = {
    "equip-slots": dict(kf=KF, cmds=[(0x61, f"{s:02x}{le(1000)}") for s in (0, 1, 7, 14, 15, 16, 255)] + [(0x61, f"01{le(3860)}"), (0x61, f"01{le(9999)}")]),
    "equip-unowned": dict(kf=KF, cmds=[(0x61, f"01{le(i)}") for i in (1001, 3879, 0xFFFF, 0, 1024, 1047, 1104)] + [(0x61, f"0f{le(1001)}"), (0x61, f"ff{le(0xFFFF)}")]),
    "equip-shapes": dict(kf=KF, cmds=[(0x61, ""), (0x61, "01"), (0x61, f"01{le(1000)[:2]}"), (0x61, f"01{le(1000)}aabb"), (0x61, f"01{le(1001)}aabb")]),
    "delete-basic": dict(kf=KF, cmds=[(0x6A, f"0107{PW}00{le(1004)}"), (0x6A, f"0107{PW}00{le(1004)}"), (0x6A, f"0107{PW}00{le(1012)}"), (0x6A, f"0007{PW}ff{le(1000)}"), (0x6A, f"0107{PW}00{le(9999)}"), (0x61, f"01{le(9999)}"), (0x61, f"01{le(1004)}")]),
    "delete-multi": dict(kf=KF, cmds=[(0x6A, f"0107{PW}00{le(1003)}{le(1002)}{le(1211)}"), (0x6A, f"0107{PW}00{le(1000)}{le(1000)}"), (0x6A, f"0307{PW}00{le(1002)}")]),
    "delete-3860": dict(kf=KF, cmds=[(0x6A, f"0107{PW}00{le(3860)}"), (0x6A, f"0107{BAD}00{le(3860)}"), (0x6A, f"0107{PW}00{le(1004)}{le(3860)}"), (0x6A, f"0107{PW}00{le(3860)}{le(1004)}"), (0x6A, f"0107{PW}00{le(3860)}aa"), (0x6A, f"0107{PW}{le(3860)}"), (0x61, f"01{le(1004)}")]),
    "delete-password": dict(kf=KF, cmds=[(0x6A, f"0107{BAD}00{le(1004)}"), (0x6A, f"0106{PW[:12]}00{le(1004)}"), (0x6A, f"0108{PW}0000{le(1004)}"), (0x6A, f"0100" + f"00{le(1004)}"), (0x6A, f"0000" + f"00{le(1004)}"), (0x6A, f"0107{PW}00{le(1004)}")]),
    "delete-shapes": dict(kf=KF, cmds=[(0x6A, ""), (0x6A, "01"), (0x6A, "010700"), (0x6A, f"0107{PW}"), (0x6A, f"0107{PW}00"), (0x6A, f"0107{PW}00{le(1004)[:2]}"), (0x6A, f"0107{PW}{le(1004)}"), (0x6A, f"0107{PW}00{le(1004)}aa"), (0x6A, f"0107{PW}00{le(1003)}aa{le(1002)}"), (0x6A, f"0107{PW}00{le(1002)}aabb"), (0x6A, f"0107{PW}00{le(1002)}aabbcc")]),
    "delete-oracle": dict(kf=KF, cmds=[(0x6A, "0100" + s) for s in ("", "00", "00aa", "00aabb", "00aabb14", "00aabb140f", "00140f", "00aa140f", "00aabbcc140f", "00aabbccdd140f", "00aabbccdd14", "00aabbccdd", "00aabbccddee140f", "00aabbccddee")] + [(0x6A, "0102aabb" + s) for s in ("00ec03", "00aaec03", "00aaaaec03", "00aaaaaaec03", "00aaaaaaaaec03")]),
    "equip-zero": dict(kf=KF, cmds=[(0x61, f"{s:02x}0000") for s in (0, 1, 14, 15, 255)] + [(0x61, "010100"), (0x61, "010001"), (0x61, "01ff00"), (0x61, f"01{le(1000)}")]),
    "learn-probe": dict(kf=[], renwu=BASE_STATS, cmds=[tp(2407), ev(2407, 13), ev(2407, 13), tp(16), ev(16, 24), ev(16, 15), tp(4300), ev(4300, 224), tp(4803), ev(4803, 114)]),
    "frame-probe": dict(kf=[], renwu={**BASE_STATS, **dict(dangqianjing=111, zuidajing=222, dangqianshen=33, zuidashen=44, dangqianxue=55, zuidaxue=66, dangqiannei=77, zuidanei=88, school_skill_lv=5, school_skill_exp=9)}, cmds=[tp(2407), ev(2407, 13)]),
    "learn-poor": dict(kf=[], renwu=stats(0), cmds=learn_cmds()),
    "learn-mid": dict(kf=prereq_kf(50), renwu=stats(30, fame_val=5000, exp_val=5000, combat_exp=5000000, online_time=48 * 1000), cmds=learn_cmds()),
    "learn-low": dict(kf=prereq_kf(30), renwu=stats(24, fame_val=1000, exp_val=1000, combat_exp=1000000, online_time=48 * 100), cmds=learn_cmds()),
    "learn-rich": dict(kf=prereq_kf(200), renwu=stats(200, fame_val=10000000, exp_val=100000000, combat_exp=900000000, online_time=48 * 100000), cmds=learn_cmds()),
    "learn-school": dict(kf=prereq_kf(200), renwu=stats(200, fame_val=10000000, exp_val=100000000, combat_exp=900000000, online_time=48 * 100000, school=11), cmds=learn_cmds()),
    "learn-rand1": dict(zip(("kf", "renwu"), rand_profile(1)), cmds=learn_cmds()),
    "learn-rand2": dict(zip(("kf", "renwu"), rand_profile(2)), cmds=learn_cmds()),
    "learn-rand3": dict(zip(("kf", "renwu"), rand_profile(3)), cmds=learn_cmds()),
    "learn-rand4": dict(zip(("kf", "renwu"), rand_profile(4)), cmds=learn_cmds()),
    "bpsm-school": dict(kf=[(1000, 20, 500), (1002, 30, 70), (1003, 10, 0), (1004, 15, 3), (1211, 1, 0), (1005, 0, 9)], renwu=dict(school=10, master=11005, school_skill_lv=7, school_skill_exp=9, study_count=55, dangqianjing=198), watch=("school", "master", "school_skill_lv", "school_skill_exp", "study_count"), cmds=[(0xC7, "0440" + b"bpsm".hex()), (0xC7, "0440" + b"bpsm".hex())]),
    "bpsm-noschool": dict(kf=[(1000, 20, 500), (1002, 30, 70), (1003, 10, 0)], renwu=dict(school=0, master=0, school_skill_lv=0, school_skill_exp=0, study_count=55, dangqianjing=198), watch=("school", "master", "school_skill_lv", "school_skill_exp", "study_count"), cmds=[(0xC7, "0440" + b"bpsm".hex())]),
    "bpsm-odd": dict(kf=[(1000, 21, 500), (1002, 1, 70), (1003, 2, 0), (1004, 3, 3), (3860, 12, 0)], renwu=dict(school=11, master=11005, school_skill_lv=1, school_skill_exp=1, study_count=7, dangqianjing=33), watch=("school", "master", "school_skill_lv", "school_skill_exp", "study_count"), cmds=[(0xC7, "0440" + b"bpsm".hex())]),
    "book-poor": dict(kf=[], renwu=stats(49, zigong=0), items=BOOKS2, watch=("zigong",), cmds=BOOK_CMDS),
    "book-attrs-ok": dict(kf=[], renwu=stats(50, zigong=0), items=BOOKS2, watch=("zigong",), cmds=BOOK_CMDS),
    "book-zigong": dict(kf=[], renwu=stats(50, zigong=1), items=BOOKS2, watch=("zigong",), cmds=BOOK_CMDS),
    "book-rich": dict(kf=[], renwu=stats(60, zigong=1, exp_val=30000, combat_exp=20000000, online_time=48 * 2000, fame_val=1000), items=BOOKS2, watch=("zigong", "study_count"), cmds=BOOK_CMDS + BOOK_CMDS),
    "book-owned": dict(kf=[(2203, 5, 0), (3004, 5, 0), (4023, 5, 0)], renwu=stats(60, zigong=1, exp_val=30000, combat_exp=20000000, online_time=48 * 2000), items=BOOKS2, cmds=BOOK_CMDS),
    "book-nobag": dict(kf=[], renwu=stats(60, zigong=1, exp_val=30000, combat_exp=20000000, online_time=48 * 2000), items=[], cmds=[book(35022)]),
    "book-nobag2": dict(kf=[], renwu=stats(10, zigong=0), items=[], cmds=[book(40177)]),
    "book-other": dict(kf=[], renwu=stats(60, zigong=1), items=[(35041, 1), (35048, 1), (35052, 1), (35022, 1)], cmds=[book(35041), book(35048), book(35052), book(12345), book(0), book(65535)]),
    "book-shapes": dict(kf=[], renwu=stats(60, zigong=1, exp_val=30000, combat_exp=20000000, online_time=48 * 2000), items=BOOKS2, cmds=[(0x60, ""), (0x60, "ce88"), (0x60, "ce8800"), (0x60, "ce880000"), (0x60, "ce88000000"), (0x60, "ce880000ff"), (0x60, "ce88000000aabb")]),
    "book-high": dict(kf=[], renwu=stats(60, zigong=1, exp_val=30000, combat_exp=20000000, online_time=48 * 2000), items=BOOKS2, cmds=[(0x60, "ce880100" + "00"), (0x60, "ce8800" + "0100"), (0x60, "ce88ffff00")]),
    "xd-check": dict(kf=[(1014, 5, 0)], renwu=dict(study_count=1000, map=2411, school=0), watch=("study_count", "map"), cmds=[xd(10003, 1014, 1, 5, c) for c in range(0, 6)]),
    "xd-curve": dict(kf=[(1014, 1, 0)], renwu=dict(study_count=9000, map=2411, school=0), watch=("study_count",), cmds=[xd(10003, 1014, 1, i, 0) for i in range(80)]),
    "xd-model": dict(kf=[(k, 3, 0) for _, k, _ in XD_SAMPLE], renwu=dict(study_count=30000, school=0), watch=("study_count",), cmds=[c for m, k, mp in XD_SAMPLE for c in (tp(mp), xd(m, k, 1, 1, 0), xd(m, k, 500, 2, 0))]),
    "xd-basic": dict(kf=[(1014, 3, 0)], renwu=XD_BASIC_RENWU, watch=XD_BASIC_WATCH, cmds=[tp(2411), xd(10003, 1014, 1, 3, 0)] + [c for m, k, mp in XD_BASIC[:3] for c in (tp(mp), xd(m, k, 1, 1, 0), xd(m, k, 100, 2, 0))] + [tp(2411), xd(10003, 1014, 1, 3, 0)]),
    "xd-one": dict(kf=[], renwu={**XD_BASIC_RENWU, **dict(zuidajing=1000, dangqianjing=1000, zuidashen=2000, dangqianshen=2000, zuidaxue=3000, dangqianxue=3000, zuidanei=4000, dangqiannei=4000)}, watch="*", cmds=[tp(2408), xd(10039, 8001, 100, 1, 0)]),
    "persist-lvl0": dict(kf=[(1000, 0, 5), (1003, 7, 0), (1004, 0, 0), (1002, 5, 50)], cmds=[(0x61, f"01{le(1000)}"), (0x6A, f"0107{PW}00{le(1003)}"), (0x61, f"01{le(1003)}")]),
}


BEFORE: dict = {}
CUR_OP = [0]


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


for _m, _k, _mp in XD_BASIC:
    SCENARIOS[f"xd-one-{_k}"] = dict(kf=[], renwu={**XD_BASIC_RENWU, **dict(zuidajing=1000, dangqianjing=1000, zuidashen=2000, dangqianshen=2000, zuidaxue=3000, dangqianxue=3000, zuidanei=4000, dangqiannei=4000)}, watch="*", cmds=[tp(_mp), xd(_m, _k, 100, 1, 0)])


def _xd_rows():
    return [r for r in _data_csv("师傅.csv")[1:] if len(r) > 8]


def _xd_pick(school_nonzero: bool, kind: str):
    for r in _xd_rows():
        if (r[6] != "0") == school_nonzero and r[7] == kind and r[3].isdigit():
            return int(r[0]), int(r[3]), int(r[8]), int(r[6])
    raise KeyError


_XD_S = _xd_pick(True, "1")  # (师傅, 武功, 地图, 门派)
_XD_BASE = {**XD_BASIC_RENWU, "school": 0}
_XD_RULES = dict(kf=[(1014, 5, 0), (1018, 4, 10), (_XD_S[1], 6, 20)], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 2411}, watch=XD_BASIC_WATCH + ("school", "map"),
                 cmds=[xd(60000, 1014, 1, 1, 0), xd(10003, 1018, 1, 2, 0), tp(100), xd(10003, 1014, 3, 3, 0), tp(2411), xd(10003, 1014, 3, 4, 0), tp(_XD_S[2]), xd(_XD_S[0], _XD_S[1], 3, 5, 0), xd(_XD_S[0], _XD_S[1], 3, 6, 0),
                       tp(2411), xd(10003, 1014, 0, 7, 0), xd(10003, 1014, 2, 8, 0), xd(10003, 1014, 1001, 9, 0), xd(10003, 1014, 1, 10, 0), xd(10003, 1019, 1, 11, 0), xd(10003, 1014, 65535, 12, 0)])
SCENARIOS["xd-rules"] = _XD_RULES
SCENARIOS["xd-nokf"] = dict(kf=[], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 2411}, watch=XD_BASIC_WATCH + ("school", "map"), cmds=[xd(10003, 1014, 1, 1, 0)])
SCENARIOS["xd-shapes"] = dict(kf=[(1014, 5, 0)], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 2411}, watch=("study_count",),
                              cmds=[(0x5E, ""), (0x5E, "1327"), (0x5E, "1327f603"), (0x5E, "1327f6030100"), (0x5E, "1327f603010000"), (0x5E, "1327f60301000000"), (0x5E, "1327f6030100000000"), (0x5E, "1327f603010000000000"), (0x5E, "1327f60301000100000000"), (0x5E, "1327f60301000200000000aabb")])
SCENARIOS["xd-cap"] = dict(kf=[(1014, 198, 0), (1018, 199, 0)], renwu={**_XD_BASE, "study_count": 20000, "wint": 100, "map": 2411, "daofa": 148, "daofaexp": 0, "dushushizi": 98, "dushushiziexp": 0}, watch=XD_BASIC_WATCH,
                           cmds=[xd(10003, 1014, 5000, 1, 0), xd(10003, 1014, 5000, 2, 0), tp(2409), xd(10004, 1018, 3000, 3, 0), tp(2408), xd(10039, 8001, 20000, 4, 0), xd(10039, 8001, 5, 5, 0), tp(1302), xd(39032, 8017, 20000, 6, 0)])


_CAP = {**_XD_BASE, "study_count": 3_000_000, "wint": 100, "daofa": 148, "daofaexp": 0, "dushushizi": 98, "dushushiziexp": 0, "map": 2409}
SCENARIOS["xd-cap-a"] = dict(kf=[(1018, 199, 0)], renwu=_CAP, watch=XD_BASIC_WATCH, cmds=[tp(2409), xd(10004, 1018, 2, 1, 0)])
SCENARIOS["xd-cap-b"] = dict(kf=[], renwu=_CAP, watch=XD_BASIC_WATCH, cmds=[tp(2408), xd(10039, 8001, 2, 1, 0)])
SCENARIOS["xd-cap-c"] = dict(kf=[], renwu=_CAP, watch=XD_BASIC_WATCH, cmds=[tp(1302), xd(39032, 8017, 2, 1, 0)])


_XD_BS = next(((int(r[0]), int(r[3]), int(r[8]), int(r[6])) for r in _xd_rows() if r[6] != "0" and r[3].isdigit() and 8001 <= int(r[3]) <= 8017), None)
SCENARIOS["xd-order"] = dict(kf=[(1014, 5, 0)], renwu={**_XD_BASE, "study_count": 10, "wint": 33, "map": 2411}, watch=("study_count", "map", "daofa", "daofaexp", "school"),
                             cmds=[xd(60000, 1014, 50, 1, 0), tp(100), xd(10003, 1014, 50, 2, 0), xd(10008, 1019, 1, 3, 0), xd(60000, 8001, 1, 4, 0), xd(10039, 8001, 1, 5, 0), xd(60000, 1019, 1, 6, 0), xd(60000, 1014, 0, 7, 0),
                                   tp(2408), xd(10039, 8001, 50, 8, 0), tp(2411), xd(10003, 8001, 1, 9, 0)] + ([tp(_XD_BS[2]), xd(_XD_BS[0], _XD_BS[1], 1, 10, 0)] if _XD_BS else []))


SCENARIOS["xd-victim"] = dict(kf=[(1014, 5, 0), (1018, 0, 7), (3860, 12, 3), (1019, 1, 0)], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 100}, watch=("study_count",),
                              cmds=[xd(10003, 1014, 1, i, 0) for i in range(1, 15)])
SCENARIOS["xd-unowned-school"] = dict(kf=[(1014, 5, 0)], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": _XD_S[2], "school": 0}, watch=("study_count", "school"),
                                      cmds=[xd(_XD_S[0], _XD_S[1] if _XD_S[1] != 1014 else 1019, 1, 1, 0), xd(_XD_S[0], _XD_S[1], 1, 2, 0)])


SCENARIOS["xd-delta0"] = dict(kf=[], renwu={**XD_BASIC_RENWU, "zuidajing": 1000, "zuidashen": 2000, "zuidaxue": 3000, "zuidanei": 4000, "map": 2408}, watch=XD_BASIC_WATCH + ("zuidashen",),
                              cmds=[xd(10039, 8006, 1, 1, 0), xd(10039, 8012, 1, 2, 0), xd(10039, 8013, 1, 3, 0), tp(1302), xd(39032, 8017, 1, 4, 0), xd(39032, 8017, 1, 5, 0), xd(10039, 8006, 1, 6, 0)])


SCENARIOS["xd-rules2"] = dict(kf=[(_XD_S[1], 6, 77)], renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 2411, "school": 0}, watch=("study_count", "school", "map"),
                              cmds=[xd(60000, _XD_S[1], 1, 1, 0), tp(100), xd(_XD_S[0], _XD_S[1], 3, 2, 0), tp(_XD_S[2]), xd(_XD_S[0], _XD_S[1], 3, 3, 0), xd(_XD_S[0], _XD_S[1], 3, 4, 0), xd(_XD_S[0], _XD_S[1], 0, 5, 0), xd(_XD_S[0], 1014, 1, 6, 0)])


for _n, _kfs in (("1", [(1014, 40, 0)]), ("2", [(1014, 40, 0), (1018, 40, 0)]), ("4", [(1014, 40, 0), (1018, 40, 0), (1019, 40, 0), (1005, 40, 0)]), ("8", [(1014, 40, 0), (1018, 40, 0), (1019, 40, 0), (1005, 40, 0), (1007, 40, 0), (1008, 40, 0), (1011, 40, 0), (1017, 40, 0)])):
    SCENARIOS[f"xd-vic{_n}"] = dict(kf=_kfs, renwu={**_XD_BASE, "study_count": 1000, "wint": 33, "map": 100}, watch=("study_count",), cmds=[xd(10003, 1014, 1, i, 0) for i in range(1, 61)])


def zx(kid: int, wait: float = 3.6, extra: str = ""):
    """C2S 0x63 自修：武功 ID(LE16) [其余不看]；两次之间要隔 ≥ 3 秒（整秒），否则「禁止加速自修」。"""
    return (0x63, le(kid) + extra, wait)


_ZX = {**_XD_BASE, "study_count": 50000, "wint": 33, "map": 3511}
_ZX_WATCH = ("study_count", "map", "dangqianjing")
SCENARIOS["zx-basic"] = dict(kf=[(1014, 5, 0), (1018, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, cmds=[zx(1014), zx(1014), zx(1018)])
SCENARIOS["zx-few"] = dict(kf=[(1014, 5, 0), (1018, 5, 0)], renwu={**_ZX, "study_count": 500}, watch=_ZX_WATCH, cmds=[zx(1014), zx(1014)])
SCENARIOS["zx-fast"] = dict(kf=[(1014, 5, 0), (1018, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, cmds=[zx(1014, 1.0), zx(1014, 1.0), zx(1014, 3.6), zx(1014)])
SCENARIOS["zx-map"] = dict(kf=[(1014, 5, 0), (1018, 5, 0), (1019, 5, 0)], renwu={**_ZX, "map": 2411}, watch=_ZX_WATCH, cmds=[zx(1014), zx(1014)])
SCENARIOS["zx-errs"] = dict(kf=[(1014, 5, 0), (3860, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, cmds=[zx(1018), zx(3860), zx(0), zx(1014, extra="aabb")])
SCENARIOS["zx-shapes"] = dict(kf=[(1014, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, cmds=[(0x63, "", 3.6), (0x63, "f6", 3.6), (0x63, "f603", 3.6), (0x63, "f60300", 3.6)])
SCENARIOS["zx-cap"] = dict(kf=[(1014, 200, 0), (1050, 180, 0), (1051, 179, 0)], renwu=_ZX, watch=_ZX_WATCH, cmds=[zx(1014), zx(1050), zx(1051)])
SCENARIOS["zx-book"] = dict(kf=[(1014, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, bank=[(58182, 3)], cmds=[zx(1014), zx(1014)])
SCENARIOS["zx-book1"] = dict(kf=[(1014, 5, 0)], renwu=_ZX, watch=_ZX_WATCH, bank=[(58182, 3)], items=[(58182, 1)], cmds=[zx(1014)])
SCENARIOS["zx-zero"] =dict(kf=[(1014, 5, 0)], renwu={**_ZX, "study_count": 0}, watch=_ZX_WATCH, cmds=[zx(1014)])


def mysql(stmt: str) -> str:
    r = subprocess.run([MYSQL, "-uroot", "-p123456", "--default-character-set=gbk", "--batch", "--skip-column-names", "jydata", "-e", stmt], capture_output=True, text=True, encoding="gbk")
    return r.stdout.strip()


BOOK_IDS = (35022, 35031, 40177, 35041, 35048, 35052, 58182)  # 场景里会放进背包的书；每场先清掉


def set_bank(bank) -> None:
    """钱庄固定成 wupin=0 头行 + 给定物品（None = 不动）。"""
    if bank is None:
        return
    rows = [(0, 0)] + list(bank)
    mysql(f"delete from qianzhuang where jyid={JY}")
    mysql("insert into qianzhuang (id,jyid,wupin,shuliang) values " + ",".join(f"({2049925589 + i},{JY},{w},{q})" for i, (w, q) in enumerate(rows)))
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
    d["qianzhuang"] = [{"jyid": str(JY), "wupin": str(w), "shuliang": str(q)} for w, q in rows]
    c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), JY))
    c.commit()
    c.close()


def set_kf(kf, renwu=None, items=None) -> None:
    mysql(f"update item set item_id=0,shuliang=0 where jyid={JY} and item_id in ({','.join(map(str, BOOK_IDS))})")
    for iid, qty in items or []:
        z = mysql(f"select min(id) from item where jyid={JY} and item_id=0")
        mysql(f"update item set item_id={iid},shuliang={qty} where id={z}")
    if renwu:
        mysql("update renwu set " + ",".join(f"{k}={v}" for k, v in renwu.items()) + f" where jyid={JY}")
    mysql(f"delete from kf where jyid={JY}")
    mysql(f"delete from biaoji where jyid={JY}")  # 标记也清掉（@bpsm 会补师门标记，上一场留下的会让下一场回「已經有此標記」）
    if kf:
        mysql("insert into kf (jyid,kf_id,kf_lvl,kf_exp) values " + ",".join(f"({JY},{a},{b},{c})" for a, b, c in kf))
    c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
    d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
    d["biaoji"] = [r for r in d.get("biaoji", []) if str(r.get("biaoji")) == "0"]
    for r in d["item"]:
        if _int(r.get("item_id")) in BOOK_IDS:
            r["item_id"], r["shuliang"] = "0", "0"
    for iid, qty in items or []:
        r = next(r for r in d["item"] if _int(r.get("item_id")) == 0)
        r["item_id"], r["shuliang"] = str(iid), str(qty)
    d["kf"] = [{"jyid": str(JY), "kf_id": str(a), "kf_lvl": str(b), "kf_exp": str(x)} for a, b, x in kf]
    for k, v in (renwu or {}).items():
        d["renwu"][0][k] = str(v)
    c.execute("update characters set rows=? where jyid=?", (json.dumps(d, ensure_ascii=False), JY))
    c.commit()
    c.close()


def run(port: int, cmds) -> list[str]:
    time.sleep(3.0)
    for attempt in range(4):  # 上一场的下线还没处理完时登录会被拒：等一会儿再试
        a = Client("A", "127.0.0.1", port, JY, None)
        w = Client("W", "127.0.0.1", port, WATCH, None)
        if a.login() and w.login():
            break
        for c in (a, w):
            try:
                c.sock.close()
            except OSError:
                pass
        time.sleep(4)
    else:
        return ["login failed"]
    a.drain(1.0)
    w.drain(1.0)
    out: list[str] = []

    def show(tag, frames):
        for f in frames:
            if f.opcode == 0x05 and tag == "A" and f.payload[:4] == struct.pack("<I", JY):
                pass  # 自己被踢下线的帧（读书没有这本书时）要比较
            elif f.opcode in (0x33, 0x60, 0x05, 0x02, 0x82) or (f.opcode == 0x99 and f.payload[:1] == b"\x04"):
                continue
            if f.opcode == 0x14 and b"\xb9\xc1\xb8\xd5\xa8\xea\xaa\x5a\xa5\x5c\xa1\x54" not in f.payload and f.payload[:1] != b"\x03" and CUR_OP[0] not in (0x5E, 0x63):
                continue  # 只比较「嘗試刷武功」公告（消點时 0x14 全比）
            pl = f.payload[:-1] + b"?" if f.opcode == 0x08 else f.payload  # 0x08 最后一字节随机
            out.append(f"    {tag} <- 0x{f.opcode:02x} {'W' if f.wide else 's'} {pl.hex(' ')}")

    for cmd in cmds:
        op, hx = cmd[0], cmd[1]
        wait = cmd[2] if len(cmd) > 2 else 0.9
        CUR_OP[0] = op
        out.append(f"== 0x{op:02x} {' '.join(hx[i:i+2] for i in range(0, len(hx), 2))}")
        show("A", a.drain(0.05))  # 原版约 75.6 秒一次换密钥(0x99 04)：先收掉，免得用旧密钥发的帧被它忽略
        try:
            a.send(op, bytes.fromhex(hx))
        except OSError:
            out.append("!! connection lost (server crashed?)")
            return out
        show("A", a.drain(wait))
        show("W", w.drain(0.2))
    for c in (a, w):
        try:
            c.sock.close()
        except OSError:
            pass
    return out


def renwu_dump() -> dict:
    cols = [l.split("\t")[0] for l in mysql("desc renwu").splitlines()]
    vals = mysql(f"select * from renwu where jyid={JY}").split("\t")
    return dict(zip(cols, vals))


def state_after(port: int, watch=(), items_watch=False) -> list[str]:
    time.sleep(4)
    extra = []
    if watch == "*" and port == 6731:
        before = BEFORE.get("renwu", {})
        now = renwu_dump()
        extra = ["renwu diff: " + " ".join(f"{k}:{before.get(k)}->{v}" for k, v in now.items() if before.get(k) != v)]
        watch = ()
    elif watch == "*":
        c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
        now = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])["renwu"][0]
        c.close()
        before = BEFORE.get("renwu_new", {})
        extra = ["renwu diff: " + " ".join(f"{k}:{before.get(k)}->{v}" for k, v in now.items() if k in BEFORE.get("renwu", {}) and str(before.get(k)) != str(v))]
        watch = ()
    if watch:
        if port == 6731:
            vals = mysql(f"select {','.join(watch)} from renwu where jyid={JY}").split("\t")
        else:
            c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
            d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
            c.close()
            vals = [str(d["renwu"][0].get(k)) for k in watch]
        extra = ["renwu after: " + " ".join(f"{k}={v}" for k, v in zip(watch, vals))]
    if items_watch:
        if port == 6731:
            bag = sorted((int(a), int(b)) for a, b in (l.split("\t") for l in mysql(f"select item_id,shuliang from item where jyid={JY} and item_id in ({','.join(map(str, BOOK_IDS))}) and shuliang>0").splitlines()))
        else:
            c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
            d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
            c.close()
            bag = sorted((_int(r["item_id"]), _int(r["shuliang"])) for r in d["item"] if _int(r.get("item_id")) in BOOK_IDS and _int(r.get("shuliang")) > 0)
        extra.append("books after: " + " ".join(f"{a}x{b}" for a, b in bag))
    if port == 6731:
        rows = [tuple(int(x) for x in l.split("\t")) for l in mysql(f"select kf_id,kf_lvl,kf_exp from kf where jyid={JY} order by kf_id").splitlines()]
    else:
        c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
        d = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])
        c.close()
        rows = sorted((int(r["kf_id"]), int(r["kf_lvl"]), int(r["kf_exp"])) for r in d.get("kf", []))
    return ["kf after: " + " ".join(f"{a}:{b}:{c}" for a, b, c in rows)] + extra


def restart_original() -> None:
    subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "restart_original.ps1")], capture_output=True)


def main() -> int:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SCENARIOS)
    only_original = "--original" in sys.argv
    bad = 0
    for name in names:
        sc = SCENARIOS[name]
        res = {}
        for port in (6731, 6732):
            if only_original and port == 6732:
                continue
            if port == 6731:  # 原版的标记 / 背包在启动时载入、下线时才回写：先停 → 改库 → 再启动
                subprocess.run(["powershell", "-Command", "Get-Process -Name 服务端 -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
                time.sleep(2)
            set_kf(sc["kf"], sc.get("renwu"), sc.get("items"))
            set_bank(sc.get("bank", [] if "bank" in sc else None))
            if port == 6731:
                BEFORE["renwu"] = renwu_dump()
                restart_original()
            else:
                c = sqlite3.connect(ROOT / "data" / "chars.sqlite")
                BEFORE["renwu_new"] = json.loads(c.execute("select rows from characters where jyid=?", (JY,)).fetchone()[0])["renwu"][0]
                c.close()
            res[port] = run(port, sc["cmds"]) + state_after(port, sc.get("watch", ()), "items" in sc)
        if only_original:
            print(f"### {name} (original)")
            print("\n".join(res[6731]))
            continue
        same = res[6731] == res[6732]
        print(f"### {name}: {'identical' if same else 'DIFF'} ({len(res[6731])} lines)")
        if not same:
            bad += 1
            for l in difflib.unified_diff(res[6731], res[6732], "original", "new", lineterm="", n=1):
                print("   ", l[:240])
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
