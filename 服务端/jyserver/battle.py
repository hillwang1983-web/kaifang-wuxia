"""战斗（单人打怪）：C2S 0x30 遭遇、0xE3 进战、0xD7 出招、0xD4 / 0xD8 战斗内上报、0xE5 / 0xE6 结束。

协议依据：
- 遭遇的回包（D1 / 82 / DC）、结束的回包（81 / 82 / E6 / 7B 18）、D4 的异或坐标、D8 的 EF 拒绝、「無此NPC信息」：对原版实测（docs/战斗.md）；
- 进战之后的 D5 / D4 / DC / C6、出招的 D7 转发 + D8 气血、怪死亡的 D8(0) → E6 → E4 → 77 → E8 顺序、结束由客户端判：
  来自客户端侧反编译（客户端 逆向工具/战斗协议_客户端侧.md §8）。**这一段没有对原版验证**——原版需要正确的校验字节才肯进战，我们没有；
- **伤害公式、怪的伤害、掉落几率、实战奖励都是自己定的**（原版的公式在 0x52d598 里，一百多万字符的反编译，没读），只保证「合理、可玩」。

怪的出招 AI 在客户端（它替怪发 C2S 0xD7），服务端接受并算伤害；不校验尾部校验字节 / 反作弊计数。
"""

from __future__ import annotations

import csv
import io
import random
import struct
from dataclasses import dataclass, field
from pathlib import Path

from .events import _bag_add
from .state import ItemTable

Frame = tuple[int, bytes, bool]

MOB_BASE = 100_000_000  # 实体 id >= 1e8 → 怪（实例序号×1e5 + mob_id）
MIN_MOB_ENTITY = 10_000_001  # 遭遇请求里实体 id 小于它的不进战斗
ENEMY_CELLS = [(30, 27), (31, 28), (29, 29), (32, 27), (28, 28)]  # 一场最多 5 只
MAX_ENEMIES = 5
POSE_CMDS = (7, 8, 9, 11)  # 防禦 / 閃躲 / 養精蓄銳 / 自動（C2S 0xDE 的命令号）
ESCAPE_CHANCE = 0.39  # C2S 0xF9 回 01 的概率：原版 随机(1–100) < 40 + 某属性/10（属性 0 时 39%，实测约 43%）
ENEMY_CELL =ENEMY_CELLS[0]
_NO_NPC = bytes.fromhex("b5 4c a6 b9") + b"NPC" + bytes.fromhex("ab 48 ae a7")  # 無此NPC信息
_DEAD = b"\x08" + bytes.fromhex("a7 41 a4 77 a6 ba a4 60")  # 0x14 08「你已死亡」

SKILL_MULT = 16  # 伤害 = 攻击力 × 16 × 随机(0.9–1.1) × 150/(150+怪的防)；攻击力 = 武器强度 + 臂力×3 + 武功「攻」×(1+等级/200)（没武功按 100）


def le32(v: int) -> bytes:
    return (v & 0xFFFFFFFF).to_bytes(4, "little")


@dataclass
class Mob:
    mob_id: int
    name: str
    reward: int  # 「实战」列：杀死后的实战奖励
    hp: int
    attack: int
    defense: int
    drops: list[int] = field(default_factory=list)  # 掉落物品（A–F 里非 0 的）
    drop_rate: int = 0  # 掉宝率（%）


class Mobs:
    def __init__(self, mobs: dict[int, Mob] | None = None) -> None:
        self.mobs = mobs or {}

    @classmethod
    def load(cls, data_dir: str | Path) -> "Mobs":
        d = Path(data_dir)
        mobs: dict[int, Mob] = {}
        drops: dict[int, tuple[list[int], int]] = {}

        def rows(name):
            p = d / name
            if not p.exists():
                return []
            return list(csv.reader(io.StringIO(p.read_bytes().decode("gbk", errors="replace"))))

        def num(s):
            try:
                return int(s)
            except (TypeError, ValueError):
                return 0

        for r in rows("NPC掉落.csv"):
            if len(r) >= 9 and r[0].strip().isdigit():
                drops.setdefault(int(r[0]), ([num(x) for x in r[2:8] if num(x) > 0], num(r[8])))
        for r in rows("MOB数据.csv"):
            if len(r) >= 7 and r[0].strip().isdigit():
                mid = int(r[0])
                dr, rate = drops.get(mid, ([], 0))
                mobs.setdefault(mid, Mob(mid, r[2], num(r[3]), num(r[4]), num(r[5]), num(r[6]), dr, rate))
        return cls(mobs)


@dataclass
class Enemy:
    entity: int
    mob: Mob
    hp: int
    cell: tuple[int, int]


@dataclass
class Session:
    enemies: dict[int, Enemy]
    entered: bool = False
    cell: tuple[int, int] = (0, 0)


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Battles:
    """每个玩家一场战斗（内存）。所有方法返回要发给**自己**的帧；气血 / 背包 / 实战直接改传进来的角色行。"""

    def __init__(self, mobs: Mobs, items: ItemTable, skill_attack: dict[int, int] | None = None, rng: random.Random | None = None) -> None:
        self.mobs = mobs
        self.items = items
        self.skill_attack = skill_attack or {}
        self.rng = rng or random.Random()
        self.sessions: dict[int, Session] = {}
        self.locked: set[int] = set()  # 发过「小实体」遭遇（只回 D5）的人：原版此后忽略 0x30，直到 E5 / E6（实测）

    # ---- 辅助
    @staticmethod
    def _hp(rows: dict) -> int:
        return _i(rows["renwu"][0].get("dangqianxue"))

    @staticmethod
    def _hp_frame(hp: int) -> Frame:
        return (0x7B, bytes([0x18, 0x01]) + le32(hp), True)

    def drop(self, jyid: int) -> None:
        self.sessions.pop(jyid, None)
        self.locked.discard(jyid)

    # ---- 0x30 遭遇
    def encounter(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """载荷 = 实体 id(LE32) + 19 字节（不看）。实体 id < 10000001 → 只回我方 D5（不进战斗）；怪不在 MOB 表 → 0x1A「無此NPC信息<id>」；
        否则建战斗，回 D1(24 字节：01 00 实体id 00×10 随机数(LE32) 00×4)、82(长) = jyid 02 00、DC(我方气血)。
        发过「小实体」遭遇之后，原版忽略 0x30，直到 E5 / E6（实测）；已经在遭遇状态再发大实体会重新来过（原版另有「禁止快速进战斗」，这里没有）。"""
        if len(payload) < 4 or jyid in self.locked:
            return []
        eid = int.from_bytes(payload[:4], "little")
        if eid < MIN_MOB_ENTITY:
            self.locked.add(jyid)
            return [(0xD5, struct.pack("<H", 1) + le32(jyid) + bytes([0x55, 0x09]), False)]
        mob = self.mobs.mobs.get(eid % 100000)
        if mob is None:
            return [(0x1A, b"\x64" + _NO_NPC + str(eid).encode(), False)]
        # 扩展（原版 19 字节填零 → 1 只）：第一个填充字节 = 同种怪的数量 1–5，实体 id 依次加 1e5（槽位 +1）
        n = payload[4] if len(payload) > 4 and 1 <= payload[4] <= MAX_ENEMIES else 1
        self.sessions[jyid] = Session({eid + k * 100000: Enemy(eid + k * 100000, mob, mob.hp, ENEMY_CELLS[k]) for k in range(n)})
        hp = self._hp(rows)
        return [
            (0xD1, b"\x01\x00" + le32(eid) + bytes(10) + le32(self.rng.randint(1, 100)) + bytes(4), False),
            (0x82, le32(jyid) + b"\x02\x00", True),
            (0xDC, struct.pack("<H", 1) + le32(jyid) + b"\x01\x00\x00\x00" + le32(hp) + bytes(9), False),
        ]

    # ---- 0xE3 进战
    def enter(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """载荷 = jyid(LE32) 列 行 模式(1) 尾字节（不验）。已有战斗且还没进场 → D5(我方) D5(敌方) D4×敌 DC(敌方气血) C6。"""
        s = self.sessions.get(jyid)
        if s is None or s.entered or len(payload) < 6:
            return []
        s.entered = True
        s.cell = (payload[4], payload[5])
        out: list[Frame] = [(0xD5, struct.pack("<H", 1) + le32(jyid) + bytes([0x14, 0x09]), False)]
        out.append((0xD5, struct.pack("<H", len(s.enemies)) + b"".join(le32(e) + bytes([0x55, 0x08]) for e in s.enemies), False))
        out += [(0xD4, le32(e.entity) + bytes(e.cell), False) for e in s.enemies.values()]
        out.append((0xDC, struct.pack("<H", len(s.enemies)) + b"".join(le32(e.entity) + b"\x01\x00\x00\x00" + le32(e.hp) + bytes(9) for e in s.enemies.values()), False))
        out.append((0xC6, b"", False))
        return out

    # ---- 0xD7 出招
    def act(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """28 字节（只用前 27 字节里的：施术者 4、指令类型 1、武功 id×100+招式序号 LE32 @6、格 @11/12、武功等级 LE16 @25）。
        先把前 16 字节转发（S2C D7，动画触发）。玩家出招 → 打中 [11][12] 格上的敌人，没有就打第一个活的；怪出招（施术者是敌人）→ 打玩家。
        敌人气血到 0：D8(0) → E6(敌) → [掉落 E4 → 77 → E8] ；有「实战」奖励就发 0x7B 2b。"""
        s = self.sessions.get(jyid)
        if s is None or not s.entered or len(payload) < 16:
            return []
        caster = int.from_bytes(payload[:4], "little")
        out: list[Frame] = [(0xD7, bytes(payload[:16]), False)]
        renwu = rows["renwu"][0]
        if caster == jyid:
            if self._hp(rows) <= 0:
                return []
            alive = [e for e in s.enemies.values() if e.hp > 0]
            if not alive:
                return []
            cell = (payload[11], payload[12]) if len(payload) > 12 else (0, 0)
            tgt = next((e for e in alive if e.cell == cell), alive[0])
            skill = int.from_bytes(payload[6:10], "little") // 100 if len(payload) >= 10 else 0
            level = int.from_bytes(payload[25:27], "little") if len(payload) >= 27 else 0
            dmg = self._player_damage(renwu, skill, level, tgt.mob)
            tgt.hp = max(0, tgt.hp - dmg)
            out.append((0xD8, b"\x01" + le32(tgt.entity) + le32(tgt.hp), False))
            if tgt.hp == 0:
                out += self._kill(rows, jyid, tgt)
        else:
            e = s.enemies.get(caster)
            if e is None or e.hp <= 0 or self._hp(rows) <= 0:
                return []
            hp = max(0, self._hp(rows) - self._mob_damage(renwu, e.mob))
            renwu["dangqianxue"] = str(hp)
            out.append((0xD8, b"\x01" + le32(jyid) + le32(hp), False))
            out.append(self._hp_frame(hp))
        return out

    def _player_damage(self, renwu: dict, skill: int, level: int, mob: Mob) -> int:
        power = _i(renwu.get("wuqiqiangdu")) + _i(renwu.get("str")) * 3
        s = self.skill_attack.get(skill)
        power += int(s * (1 + level / 200)) if s else 100
        r = 0.9 + self.rng.random() * 0.2
        return max(1, int(power * SKILL_MULT * r * 150 / (150 + max(0, mob.defense))))

    def _mob_damage(self, renwu: dict, mob: Mob) -> int:
        guard = _i(renwu.get("fangjuqiangdu")) + _i(renwu.get("vit")) * 2
        r = 0.8 + self.rng.random() * 0.4
        return max(1, int(mob.attack * r * 2 * 200 / (200 + guard)))  # 怪攻 × 随机(0.8–1.2) × 2 × 200/(200+防具强度+根骨×2)

    def _kill(self, rows: dict, jyid: int, e: Enemy) -> list[Frame]:
        out: list[Frame] = [(0xE6, le32(e.entity), False)]
        col, row = e.cell
        mob = e.mob
        if mob.drops and self.rng.random() * 100 < mob.drop_rate:
            iid = self.rng.choice(mob.drops)
            out.append((0xE4, bytes([col, row]) + struct.pack("<H", iid & 0xFFFF), False))
            out.append((0x77, le32(iid) + (0x100 + self.items.of(iid)).to_bytes(2, "little"), True))
            _bag_add(rows, str(jyid), iid, 1)
            out.append((0xE8, le32(jyid) + bytes([col, row]), False))
        if mob.reward > 0:
            renwu = rows["renwu"][0]
            renwu["combat_exp"] = str(_i(renwu.get("combat_exp")) + mob.reward)
            out.append((0x7B, bytes([0x2B, 0x01]) + le32(_i(renwu["combat_exp"])), True))
        return out

    # ---- 0xD4 / 0xD8 战斗内上报
    def move(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """0xD4 = 实体 id(LE32) + 2 个坐标字节 + …（至少 6 字节）→ S2C D4 = 实体 id + 两个坐标字节。原版回的是坐标字节各异或一个每人不同、每次遭遇都变的密钥
        （实测：该密钥 = 个人底数 + 上一次 D1 里的随机数，客户端用同一个会话值混淆它发的坐标），新服务端不知道这个会话值，原样回显。"""
        if len(payload) < 6:
            return []
        return [(0xD4, payload[:6], False)]

    def status(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """0xD8（14 字节）：已进场 → S2C D8(长) `01`（空清单）；遭遇了但还没进场 → 静默；没有战斗（含小实体遭遇之后）→ 0xEF = jyid + 10（原版实测）。"""
        s = self.sessions.get(jyid)
        if s is None:
            return [(0xEF, le32(jyid) + b"\x10", False)]
        return [(0xD8, b"\x01", True)] if s.entered else []

    # ---- 0xDE 原地姿态 / 0xF9 逃跑
    def pose(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """0xDE（防禦 7 / 閃躲 8 / 養精蓄銳 9 / 自動 11；jyid(LE32) 命令号 计数器(LE32) 校验，10 字节）：已进场且活着 → 回 S2C D7 =
        jyid + 命令号 + 11 个零（出招转发的同形，**自拟**：原版没有校验字节就一律静默，没见过它的回包）；别的静默。没有防御 / 闪躲 / 回气的数值效果。"""
        s = self.sessions.get(jyid)
        if s is None or not s.entered or len(payload) < 10 or payload[4] not in POSE_CMDS or self._hp(rows) <= 0:
            return []
        return [(0xD7, le32(jyid) + bytes([payload[4]]) + bytes(11), False)]

    def escape(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """0xF9（空载荷，客户端只在「逃離點」上才发）→ S2C F9(短) 1 字节：01 / 00 随机（原版实测 84 次 36 次 01 ≈ 43%，不管在不在战斗里、
        载荷是什么，也不改变战斗状态——之后的 E5 照常回结束帧）。这里取 39%（反编译：随机(1–100) < 40 + player+0x23c/10，单人时回 F9 01 / 00；属性不明按 0）。成功后由客户端自己发 E5。"""
        return [(0xF9, b"\x01" if self.rng.random() < ESCAPE_CHANCE else b"\x00", False)]

    # ---- 0xE5 / 0xE6 结束
    def end(self, rows: dict, jyid: int, payload: bytes) -> list[Frame]:
        """客户端自己判胜负后上报（载荷不含结果）。气血 > 1：81(长) 01、82 = jyid 00 00、E6 = jyid、7B 18 气血；
        气血 ≤ 1（死了）：0x14 08「你已死亡」、81 02、7B 18 01、82、E6、7B 18 01，气血记为 1（原版实测，HP=0/1/2 三种对照）。"""
        self.sessions.pop(jyid, None)
        self.locked.discard(jyid)
        hp = self._hp(rows)
        if hp <= 1:  # 原版实测：气血 ≤ 1 就是死了，气血被拉到 1，别的（位置 / 物品 / 实战）都不变（试的号实战不到 10 万）
            rows["renwu"][0]["dangqianxue"] = "1"
            return [
                (0x14, _DEAD, True),
                (0x81, b"\x02", False),
                self._hp_frame(1),
                (0x82, le32(jyid) + b"\x00\x00", False),
                (0xE6, le32(jyid), False),
                self._hp_frame(1),
            ]
        return [
            (0x81, b"\x01", True),
            (0x82, le32(jyid) + b"\x00\x00", False),
            (0xE6, le32(jyid), False),
            self._hp_frame(hp),
        ]
