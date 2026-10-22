"""生活技能（C2S 0x5A 伐木 / 捕魚 / 採礦）和農夫（0x5B 播種、0x5C 耕種 / 收成）。

依据 2026-10-20 对原版的反编译（0x73645b / 0x89229e / 0x737bc6 / 0x73c6e8 / 0x740523 / 0x893759）和实测（tools/life_probe.py、life_sample.py、farm_sample.py），
详见 docs/生活技能与农夫.md。原版**不看**序号、校验字节、工具位置。

产出表（`jyserver/life_items.json`）是 tools/extract_life_tables.py 从 0x73c6e8 的反编译里逐点求值抠出来的：伐木 / 捕魚 / 採礦各一张，
键 = 技能等级，值 = [[随机数下限, 上限, 物品 ID 或 null], …]，随机数 1–100；null = 这一格什么也不给（原版仍然发一条物品 ID 0 的 0x64 并存 0 号物品）。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import bank
from .study import _DROP, _drop_one
from .state import ItemTable, to_big5

Frame = tuple[int, bytes, bool]

# C2S 0x5A 的 B：1 伐木 / 2 捕魚 / 3 採礦 -> (jineng 列, 0x76 / 0x64 里的技能号, 产出表名, 开始后的实体状态)
WORK = {1: ("famu", 0, "famu", 3), 2: ("buyu", 9, "buyu", 4), 3: ("caikuang", 5, "caikuang", 5)}
FARM_SKILL = ("nongfu", 8)
LEVEL_CAP = 100
MIN_GAP = 4  # 两次采集的间隔（VB DateDiff 的整秒数）小于 4 → 「禁止加速採集」
EXP_PER_WISDOM = 10  # 每轮经验 = 悟性 × 10
EXTRA_CHANCE = 30  # 农夫每次收成有 29%（随机 1–100 < 30）另外得到一件物品
# 种子 -> 作物（0x893759 里逐个比较出来的）
CROPS = {
    44201: 44206, 44202: 44207, 44203: 44208, 44204: 44209, 44205: 44210, 44211: 44212,
    55001: 55004, 55002: 55005, 55003: 55006, 55028: 55007, 55029: 55008, 55030: 55009, 55031: 55010, 55032: 55011, 55033: 55012, 55034: 55013,
    55035: 55014, 55036: 55015, 55037: 55016, 55038: 55017, 55039: 55018, 55040: 55019, 55041: 55020, 55042: 55021, 55043: 55022, 55044: 55023,
    55045: 55024, 55046: 55025, 55047: 55026, 55048: 55027,
    44218: 44213, 44219: 44214, 44220: 44215, 44221: 44216, 44222: 44217, 44226: 44223, 44227: 44224, 44228: 44225, 44229: 44230,
}
EXTRA_ITEMS = [44233, 44235, 44230, *range(55701, 55718)]  # 农夫「另外的物品」：0x59da85 起初始化的 20 项数组（抽样 100 次收成，28 次出现，见到的 16 种都在里面）

_TOO_FAST = b"\x64" + bytes.fromhex("b8 54 a4 ee a5 5b b3 74 aa f6 b6 b0")  # 禁止加速採集
_VIP_STORED = b"\x64" + bytes.fromhex("56 49 50 a5 5c af e0 aa f6 b6 b0 aa ab ab 7e a6 db b0 ca a6 73 a4 4a bf fa c9 dc a1 54")  # VIP功能採集物品自動存入錢庄﹗
_NO_ITEM = b"\x64" + bytes.fromhex("aa ab ab 7e a4 a3 a8 ac")  # 物品不足
ZIXIU_MAP = 3511  # 自修洞：在这张图上发 5B / 5C 要受罚
_CHEAT_PREFIX = bytes.fromhex("aa b1 ae 61 3a")  # 玩家:
_CHEAT_MID = bytes.fromhex("a1 41 a9 6d a6 57 3a")  # ，姓名:
_CHEAT_TAIL = bytes.fromhex("a6 62 a6 db ad d7 ac 7d bd 6d a7 de af e0 a1 41")  # 在自修洞練技能，
_GOT_EXTRA = b"\x64" + bytes.fromhex("b1 6f a8 ec a4 46 a5 74 a5 7e aa ba aa ab ab 7e")  # 拿到了另外的物品


@dataclass
class State:
    """每个连接一份（原版放在玩家对象里）：農夫当前拿着的种子、上一次成功采集的时间（整秒）。"""

    seed: int = 0
    last: int = 0


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_map: list[Frame] = field(default_factory=list)  # 同图其他人
    to_all: list[Frame] = field(default_factory=list)  # 全服（含自己），先于 to_self 发


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Life:
    def __init__(self, tables: dict | None = None) -> None:
        self.tables = tables if tables is not None else {}

    @classmethod
    def load(cls) -> "Life":
        p = Path(__file__).with_name("life_items.json")
        return cls(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})

    def pick(self, skill: str, level: int, r: int) -> int:
        for lo, hi, item in self.tables.get(skill, {}).get(str(min(level, 100)), []):
            if lo <= r <= hi:
                return int(item) if item else 0
        return 0

    def zixiu_penalty(self, rows: dict, rng: random.Random, jyid: int) -> Result:
        """在自修洞（3511 号地图）发 5B / 5C：什么都不做，全服收 0x14 0e 「玩家:<jyid>，姓名:<名字>在自修洞練技能，武功隨机掉一級」，然后随机一门武功掉一级
        （同消点的随机掉级：至少 2 门武功才会，回 0x70）。5A（伐木 / 捕魚 / 採礦）不受影响。实测（原版 0x89229e 开头 + 抓包）。"""
        res = Result()
        renwu = rows["renwu"][0]
        text = _CHEAT_PREFIX + str(jyid).encode() + _CHEAT_MID + to_big5(renwu.get("name", "") or "") + _CHEAT_TAIL + _DROP
        res.to_all.append((0x14, b"\x0e" + text, True))
        res.to_self += _drop_one(rows, renwu, rng)
        return res

    # ---- 5A：A = 1 开始 / 2 一轮 / 3 停止（0 也是停止，在 0x89229e 里）
    def work(self, rows: dict, items: ItemTable, st: State, rng: random.Random, jyid: int, payload: bytes, now: float | None = None) -> Result:
        res = Result()
        if len(payload) < 6:
            return res
        a, b = payload[4], payload[5]
        me = jyid.to_bytes(4, "little")
        if a == 1 and b in WORK:
            frame = (0x82, me + bytes([WORK[b][3], 0]), False)
            res.to_map.append(frame)
            res.to_self.append(frame)
        elif a == 3:  # 停止不看 B（原版接受 B=0）
            res.to_self.append((0x82, me + b"\x00\x00", False))
        elif a == 2 and b in WORK:
            col, skill, table, _ = WORK[b]
            renwu = rows["renwu"][0]
            jing = _i(renwu.get("dangqianjing"))
            if jing <= 1:  # 精至少 2 才能干活
                return res
            renwu["dangqianjing"] = str(jing - 1)
            res.to_self.append((0x7B, bytes([0x16, 1]) + (jing - 1).to_bytes(4, "little"), True))
            level, exp = self._grow(rows, col, skill, res)
            t = int(now if now is not None else time.time())
            if t - st.last < MIN_GAP:
                res.to_self.append((0x1A, _TOO_FAST, False))
                return res
            st.last = t
            item = self.pick(table, level, rng.randint(1, 100))
            res.to_self.append((0x64, item.to_bytes(2, "little") + bytes([1, skill, level & 0xFF]) + (exp & 0xFFFFFF).to_bytes(3, "little"), False))
            res.to_self += self._store(rows, items, item)
        return res

    def _grow(self, rows: dict, col: str, skill: int, res: Result) -> tuple[int, int]:
        """每轮 / 每次收成加经验：悟性 × 10，每级要 (级+1)²，满 100 级清零；等级已经 100 就什么都不变也不发 0x76。返回 (等级, 经验)。"""
        renwu, jn = rows["renwu"][0], rows["jineng"][0]
        level, exp = _i(jn.get(col)), _i(jn.get(col + "exp"))
        if level >= LEVEL_CAP:
            return level, exp
        total = exp + _i(renwu.get("wint")) * EXP_PER_WISDOM
        while total - (level + 1) ** 2 > 0:
            level += 1
            total -= level**2
        if level >= LEVEL_CAP:
            level, total = LEVEL_CAP, 0
        jn[col], jn[col + "exp"] = str(level), str(total)
        res.to_self.append((0x76, bytes([0xBE, skill, 1, 1]) + level.to_bytes(4, "little"), False))
        res.to_self.append((0x76, bytes([0xBE, skill, 2, 1]) + total.to_bytes(4, "little"), False))
        return level, total

    def _store(self, rows: dict, items: ItemTable, item: int) -> list[Frame]:
        """采集到的东西先进背包：背包里**还没有**这件物品就静默 +1（没有任何帧）；已经有了（物品 0 总是）就走 VIP 自动存钱庄 —— 背包不变，
        钱庄 +1，回 0B / 77 / 27，最后一条「VIP功能採集物品自動存入錢庄﹗」。（原版实测：每种物品的第一件留在背包里，之后的都进钱庄。）"""
        if item and bank.owned(rows, item) < 1:
            bank._put_in_bag(rows, str(rows["renwu"][0].get("jyid")), item, 1)
            return []
        return self._deposit(rows, items, item) + [(0x1A, _VIP_STORED, False)]

    def _deposit(self, rows: dict, items: ItemTable, item: int) -> list[Frame]:
        """钱庄里加一件（物品 0 也照存在 wupin=0 那行），回和 C2S 0x22 存物品同样的 0B / 77 / 27 三帧。"""
        renwu = rows["renwu"][0]
        bank_rows = rows.setdefault("qianzhuang", [])
        for r in bank_rows:
            if _i(r.get("wupin")) == item:
                r["shuliang"] = str(_i(r.get("shuliang")) + 1)
                break
        else:
            bank_rows.append({"jyid": str(renwu.get("jyid")), "wupin": str(item), "shuliang": "1"})
        body = bytes([0]) + item.to_bytes(4, "little") + (1).to_bytes(2, "little") + _i(renwu.get("jy_money")).to_bytes(4, "little") + bytes([items.of(item)])
        return [bank._USE_ACK, bank._ITEM_ADD, (0x27, body, False)]

    # ---- 5B 播種：田块号(1) 种子 ID(LE16)，载荷正好 3 字节（原版看帧长字节 == 7）
    def plant(self, rows: dict, st: State, jyid: int, payload: bytes) -> Result:
        res = Result()
        if len(payload) != 3:
            return res
        plot, seed = payload[0], int.from_bytes(payload[1:3], "little")
        st.seed = seed
        res.to_self.append((0x66, jyid.to_bytes(4, "little") + bytes([plot]) + seed.to_bytes(2, "little") + b"\x01", False))
        res.to_map.append((0x67, bytes([plot, 1]), False))
        if bank.owned(rows, seed) < 1:
            res.to_self.append((0x1A, _NO_ITEM, False))
        else:
            bank._take_from_bag(rows, seed, 1)
        return res

    # ---- 5C：序号(4) 田块号 动作(1 耕種 2 收成) …，至少 6 字节
    def till_or_harvest(self, rows: dict, items: ItemTable, st: State, rng: random.Random, jyid: int, payload: bytes, now: float | None = None) -> Result:
        res = Result()
        if len(payload) < 6:
            return res
        plot, action = payload[4], payload[5]
        me = jyid.to_bytes(4, "little")
        if action == 1:
            res.to_self.append((0x66, me + bytes([plot]) + st.seed.to_bytes(2, "little") + b"\x03", False))
            for dest in (res.to_self, res.to_map):
                dest.append((0x82, me + bytes([6, 0]), False))
        elif action == 2:
            t = int(now if now is not None else time.time())
            jn = rows["jineng"][0]
            col, skill = FARM_SKILL
            if t - st.last < MIN_GAP:  # 被拒的收成照样涨经验、同图照样收到 0x67（种子不清）
                res.to_self.append((0x1A, _TOO_FAST, False))
                self._grow(rows, col, skill, res)
                res.to_map.append((0x67, bytes([plot, 0]), False))
                return res
            st.last = t
            level, exp = _i(jn.get(col)), _i(jn.get(col + "exp"))
            crop = CROPS.get(st.seed, 0)
            if crop:  # 没有种子（收成过 / 没播过）就没有 0x64；有种子但随机数掷到 100（1%）→ 失败帧：物品 0、标志 00
                ok = rng.randint(1, 100) < 100
                res.to_self.append((0x64, (crop if ok else 0).to_bytes(2, "little") + bytes([1 if ok else 0, skill, level & 0xFF]) + (exp & 0xFFFFFFFF).to_bytes(4, "little"), False))
                if ok:
                    bank._put_in_bag(rows, str(jyid), crop, 1)  # 农作物不跟 0B / 77，但背包里确实 +1
            if EXTRA_ITEMS and rng.randint(1, 100) < EXTRA_CHANCE:
                extra = rng.choice(EXTRA_ITEMS)
                bank._put_in_bag(rows, str(jyid), extra, 1)
                res.to_self.append((0x77, extra.to_bytes(4, "little") + bytes([items.of(extra), 1]), False))
                res.to_self.append((0x1A, _GOT_EXTRA, False))
            st.seed = 0
            self._grow(rows, col, skill, res)
            res.to_map.append((0x67, bytes([plot, 0]), False))
        return res
