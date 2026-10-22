"""C2S 0x5E 消点：花「学习点」向师傅学武功，换成武功经验（可能升级）。

行为依据 2026-10-20 对原版的实测 + 反编译（0x6ef0f0），tools/kf_compare.py 的 xd-* 场景与原版逐帧、逐库对照，详见 docs/消点.md。
载荷 = 师傅 ID(LE16) 武功 ID(LE16) 点数(LE16) [序号 LE32 校验字节：原版都不看]，至少 6 字节。
"""

from __future__ import annotations

import random
import struct

from .kungfu import Kungfu, Result, _i
from .state import to_big5

REBIRTH_KF = 3860
GAIN_PER_STAT = 1.5  # 每点学习点换到的经验 = 悟性（上限 100）× 1.5，取整数部分
STAT_CAP = 100
BASIC_CAP = 150  # 基本武学（8001–8015）的等级上限；读书识字（8017）100
BASIC_CAP_READING = 100
ALL_POINTS = 2  # 点数填 2 = 把全部学习点都花掉（原版怪规则）
# 基本武学：武功 ID -> (renwu 等级列, 升级系数)；等级 / 经验存在 renwu 里，不在 kf 表。系数取自 武学系数.csv 第 11 列
BASIC = {
    8001: "daofa", 8002: "qiangfa", 8003: "jianfa", 8004: "bianfa", 8005: "gunfa", 8006: "neigong", 8007: "cishu", 8008: "shenfa",
    8009: "dushu", 8010: "yishu", 8011: "zhenfa", 8012: "boji", 8013: "shanduo", 8014: "anqi", 8015: "chaizhao", 8017: "dushushizi",
}
BASIC_ALIAS = {55555: 8017}  # 原版把 0xd903 当成读书识字
# 升到某级时的副作用：每升一级 + 内功 精 / 神 / 气 各 400、内 5；搏击 / 闪躲 / 读书每过 10 级 +1 臂力 / 机敏 / 悟性（0x7B 子类型 1E / 23 / 20）
NEIGONG_MAX = (("zuidajing", 400, 0x15), ("zuidaxue", 400, 0x17), ("zuidashen", 400, 0x19), ("zuidanei", 5, 0x1C))
DECADE_ATTR = {8012: ("str", 0x1E), 8013: ("agi", 0x23), 8017: ("wint", 0x20)}

_NO_MASTER = bytes.fromhex("b5 4c a6 b9 ae 76 b3 c5 a5 4e bd 58 a1 41 bd d0 c1 70 a8 74 47 4d a7 69 aa be a6 b9 a5 4e bd 58")  # 無此師傅代碼，請聯系GM告知此代碼
_NO_MASTER_GM = bytes.fromhex("bd d0 c1 70 a8 74 47 4d a7 69 aa be a6 b9 a5 4e bd 58 3a")  # 請聯系GM告知此代碼:
_SEP = bytes.fromhex("a1 51")  # ﹔
_WRONG_MAP = bytes.fromhex("ae f8 c2 49 a6 61 b9 cf a4 a3 a5 bf da cc 21 3a")  # 消點地圖不正确!:
_TRIED = bytes.fromhex("b9 c1 b8 d5 a8 ea aa 5a a5 5c 3a")  # 嘗試刷武功:
_WRONG_SCHOOL = bytes.fromhex("b9 c1 b8 d5 a8 ea a4 a3 c4 dd a4 5f a6 db a4 76 aa f9 ac a3 aa ba aa 5a a5 5c a1 54")  # 嘗試刷不屬于自己門派的武功﹗
_DROP = bytes.fromhex("aa 5a a5 5c c0 48 c9 f3 b1 bc a4 40 af c5")  # 武功隨机掉一級
_OVER_LEVEL = b"\x64" + bytes.fromhex("b6 57 b9 4c ae f8 c2 49 af c5 bc c6")  # 超過消點等級


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]  # 原版把系数存成单精度


def need(coef: float, level: int) -> int:
    """level → level+1 要的经验 = int(系数 × (level+1)^3)。"""
    return int(_f32(coef) * float(level + 1) ** 3)


def _le16(v: int) -> bytes:
    return (v & 0xFFFF).to_bytes(2, "little")


def _text(sub: int, text: bytes) -> tuple[int, bytes, bool]:
    return (0x14, bytes([sub]) + text, True)


def _0x68(renwu: dict, kid: int, level: int, exp: int, study: int) -> tuple[int, bytes, bool]:
    return (0x68, _le16(kid) + _le16(level) + (exp & 0xFFFFFFFF).to_bytes(4, "little") + _le16(study) + _le16(_i(renwu.get("dangqianjing"))), True)


def _drop_one(rows: dict, renwu: dict, rng: random.Random) -> list[tuple[int, bytes, bool]]:
    """随机一门武功掉一级（身上至少 2 门武功才会；挑中转生武功 / 等级 ≤ 1 的不动，也不回包；原版实测 60 次 × 2/4/8 门武功，每次都挑中一门，大致均匀）；回 0x70 = 学点 精 武功 新等级 经验。"""
    kf = rows.get("kf") or []
    if len(kf) < 2:  # 原版实测：只有一门武功时从不掉级（2 门以上则每次必挑中一门）
        return []
    row = rng.choice(kf)
    kid, lvl = _i(row.get("kf_id")), _i(row.get("kf_lvl"))
    if kid == REBIRTH_KF or lvl <= 1:
        return []
    row["kf_lvl"] = str(lvl - 1)
    return [(0x70, _le16(_i(renwu.get("study_count"))) + _le16(_i(renwu.get("dangqianjing"))) + _le16(kid) + _le16(lvl - 1) + (_i(row.get("kf_exp")) & 0xFFFFFFFF).to_bytes(4, "little"), True)]


def study(rows: dict, table: Kungfu, rng: random.Random, payload: bytes) -> Result:
    res = Result()
    if len(payload) < 6:
        return res
    renwu = rows["renwu"][0]
    master, kid, pts = (int.from_bytes(payload[i : i + 2], "little") for i in (0, 2, 4))
    kid = BASIC_ALIAS.get(kid, kid)
    have = _i(renwu.get("study_count"))
    if pts == ALL_POINTS:
        pts = have
    if have < pts:
        return res
    name = to_big5(renwu.get("name", "") or "")
    basic_col = BASIC.get(kid)
    row = None
    cap = BASIC_CAP_READING if kid == 8017 else BASIC_CAP
    if basic_col is None:
        info = table.masters.get((master, kid))
        owned = next((r for r in rows.get("kf") or [] if _i(r.get("kf_id")) == kid), None)
        if info is None:
            res.to_self.append(_text(0x03, _NO_MASTER + str(master).encode() + _SEP + str(kid).encode()))
            res.inline.append((1, _text(0x0E, name + _NO_MASTER_GM + str(master).encode() + _SEP + str(kid).encode())))
            return res
        if owned is None:  # 没有这门武功（师傅对）：不管地图 / 门派对不对，都是同一句「嘗試刷武功」，没有掉级
            res.inline.append((0, _text(0x0E, name + _TRIED + str(kid).encode())))
            return res
        if info.school != 0 and info.school != _i(renwu.get("school")):
            res.to_self += _drop_one(rows, renwu, rng)
            res.inline.append((len(res.to_self), _text(0x0E, name + _WRONG_SCHOOL + str(kid).encode() + _DROP)))
            return res
        if _i(renwu.get("map")) != info.map:
            res.inline.append((0, _text(0x0E, name + _WRONG_MAP + str(kid).encode() + _DROP)))
            res.to_self += _drop_one(rows, renwu, rng)
            return res
        row = owned
        cap = info.rank
        level, exp = _i(row.get("kf_lvl")), _i(row.get("kf_exp"))
    else:
        level, exp = _i(renwu.get(basic_col)), _i(renwu.get(basic_col + "exp"))
    coef = table.coef.get(kid, 1.0)
    if pts == 0:
        res.to_self.append(_0x68(renwu, kid, level, exp, have))
        return res
    old_level = level
    total = exp + int(pts * min(_i(renwu.get("wint")), STAT_CAP) * GAIN_PER_STAT)
    while True:
        n = need(coef, level)
        if total - n <= 0:
            break
        level += 1
        total -= n
        if level > cap:
            res.to_self.append((0x1A, _OVER_LEVEL, False))
            level = cap
            break
    renwu["study_count"] = str(have - pts)
    if basic_col is None:
        row["kf_lvl"], row["kf_exp"] = str(level), str(total)
    else:
        renwu[basic_col], renwu[basic_col + "exp"] = str(level), str(total)
    res.to_self.append(_0x68(renwu, kid, level, total, have - pts))
    if kid == 8006:  # 基本内功：精 / 神 / 气 / 内 的上限随等级涨，并把四个上限发给客户端
        for col, per, sub in NEIGONG_MAX:
            renwu[col] = str(_i(renwu.get(col)) + per * (level - old_level))
            res.to_self.append((0x7B, bytes([sub, 1]) + (_i(renwu[col]) & 0xFFFFFFFF).to_bytes(4, "little"), True))
    elif kid in DECADE_ATTR:
        col, sub = DECADE_ATTR[kid]
        bonus = level // 10 - old_level // 10
        if bonus:
            renwu[col] = str(_i(renwu.get(col)) + bonus)
            res.to_self.append((0x7B, bytes([sub, 1]) + (min(_i(renwu[col]), STAT_CAP) & 0xFFFFFFFF).to_bytes(4, "little"), True))
    return res
