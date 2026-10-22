"""合成 / 烹調 / 打造（C2S 0x1B）。依据 docs/合成.md（反编译 0x741cc2 / 0x7422b7 + 对本机原版的实测，tools/craft_compare.py）。

载荷 = 配方键两个字节（原版把整帧转成十六进制文本再按空格拆，取第 5、6 个词，如 `F0 02`；多出来的字节不看，少于 2 字节静默）。
**神**（dangqianshen）必须 ≥ 2，先扣 1，自己收 `0x7B 1A 01 <神 LE32>`；之后配方里的材料不够就静默结束（神已经扣了）。
配方表 `recipes.json` 是 tools/extract_recipes.py 从原版 0x7422b7 里抠出来的（每个配方：材料检查 / 扣除 / 技能 / 成品 / 成功阈值）。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import bank
from .life import Life, Result as _LifeResult
from .state import ItemTable, to_big5

Frame = tuple[int, bytes, bool]

SKILLS = {"伐木": 0, "捕鱼": 9, "采矿": 5, "打铁": 6, "工匠": 1, "织布": 2, "裁缝": 3, "猎人": 4, "铸剑": 7, "农夫": 8, "厨师": 10}
SKILL_COL = {"工匠": "gongjiang", "织布": "zhibu", "裁缝": "caifeng", "猎人": "lieren", "打铁": "datie", "铸剑": "zhujian", "厨师": "chushi"}
SUB_SHEN = 0x1A
# 随机数 = round(随机(1..110) / 5)，成功 = 随机数 < 阈值；阈值 = 幸运(luk) 或 序言里按局部变量设的常数（0x7422b7 开头：[-0xc]=8, [-0x10]=6, …）
THRESHOLDS = {0xC: 8, 0x10: 6, 0x14: 5, 0x18: 4, 0x1C: 3, 0x20: 2, 0x24: 1, 0x28: 2, 0x2C: 8}
BAG_LIMIT = 499  # 身上物品总数 + 1 超过 499 就不让合成
_BAG_FULL = b"\x64" + to_big5("身上总数超过499")
_NO_ITEM = b"\x64" + bytes.fromhex("aa ab ab 7e a4 a3 a8 ac")  # 物品不足
_UNKNOWN_HEAD =b"\x64" + bytes.fromhex("bd d0 b0 4f bf fd a1 52")  # 請記錄﹕
_UNKNOWN_TAIL = bytes.fromhex("a1 41 a9 4d ad 6e a6 58 a6 a8 aa ba aa ab ab 7e a6 57 ba d9 b5 6f b5 b9 ba de b2 7a ad fb a1 41 b0 a8 a4 57 a5 5b a4 57 a1 54")  # ，和要合成的物品名稱發給管理員，馬上加上！


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


@dataclass
class Craft:
    recipes: dict = field(default_factory=dict)
    unsupported: set = field(default_factory=set)

    @classmethod
    def load(cls) -> "Craft":
        p = Path(__file__).with_name("recipes.json")
        if not p.exists():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        return cls(d["recipes"], set(d["unsupported"]))

    def craft(self, rows: dict, items: ItemTable, life: Life, rng: random.Random, payload: bytes) -> _LifeResult:
        res = _LifeResult()
        if len(payload) < 2:
            return res
        key = f"{payload[0]:02X} {payload[1]:02X}"
        renwu = rows["renwu"][0]
        shen = _i(renwu.get("dangqianshen"))
        if shen < 2:
            return res
        renwu["dangqianshen"] = str(shen - 1)
        res.to_self.append((0x7B, bytes([SUB_SHEN, 1]) + (shen - 1).to_bytes(4, "little"), True))
        if sum(_i(r.get("shuliang")) for r in rows.get("item") or []) + 1 > BAG_LIMIT:
            res.to_self.append((0x1A, _BAG_FULL, False))
            return res
        rec = self.recipes.get(key)
        if rec is None and key in self.unsupported:
            return res  # 特殊配方（没抠出来的）：神照扣，其余不做
        if rec is None:
            res.to_self.append((0x1A, _UNKNOWN_HEAD + key.encode() + _UNKNOWN_TAIL, False))
            return res
        if any(bank.owned(rows, iid) < n for iid, n in rec["needs"]):
            return res
        jyid = str(renwu.get("jyid"))
        # 扣材料用的是配方里另一份清单（takes）：个别配方和检查清单不一致（原版的笔误），缺的那一项只回「物品不足」，配方照样往下做
        for iid, n in rec["takes"]:
            if bank.owned(rows, iid) < n:
                res.to_self.append((0x1A, _NO_ITEM, False))
                continue
            bank._take_from_bag(rows, iid, n)
            res.to_self += [(0x6B, iid.to_bytes(4, "little") + bytes([items.of(iid), 1]), True)] * n  # 每件一帧
        skill = rec["skill"]
        col, code = SKILL_COL[skill], SKILLS[skill]
        level, exp = life._grow(rows, col, code, res)
        win = renwu.get("luk") if rec["win"] == "luk" else THRESHOLDS[rec["win"]]
        roll = (rng.randint(1, 110) + 2) // 5
        won = roll < _i(win)
        if won:
            bank._put_in_bag(rows, jyid, rec["product"], 1)
            res.to_self.append((0x64, rec["product"].to_bytes(2, "little") + bytes([1, code, level & 0xFF]) + exp.to_bytes(4, "little"), False))
        else:
            res.to_self.append((0x64, bytes([0, 0, 0, code, level & 0xFF]) + exp.to_bytes(4, "little"), False))
        # 收尾段（0x88c108）：随机数 < 6 且成品的「是否广播」= 1 → 全服公告。**不看成败**（幸运低的号失败了也会广播）
        if roll < THRESHOLDS[0x10] and rec["product"] in items.broadcast:
            text = to_big5("玩家" + str(renwu.get("name", "")) + "，合成得到﹕" + items.names.get(rec["product"], ""))
            res.to_all.append((0x04, b"\x09" + _i(renwu.get("jyid")).to_bytes(4, "little") + text, True))
        return res
