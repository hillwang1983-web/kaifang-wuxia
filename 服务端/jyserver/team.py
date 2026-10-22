"""组队：C2S 0x26 创建、0x2C 邀请、0x2D 应答、0x2E 队伍聊天、0x27 解散、0x29 离队；下线时的收尾。

行为依据 2026-10 用三个模拟客户端对原版的实测（tools/multi_raw.py），详见 docs/组队.md。
原版的状态是两张全局数组：每个玩家一个队伍号（player+0x3c0，0 = 没队伍），每个队伍一个 7 格的数组（格 0 是队长）。
新服务端用同样的结构，连原版的怪行为（槽位残留、队伍号 0 的「队伍」是所有没组队的人）一起照搬。
"""

from __future__ import annotations

from dataclasses import dataclass

from .state import to_big5

Out = tuple[int, int, bytes, bool]  # (收件人 jyid, opcode, 载荷, 是否长帧)

SLOTS = 7
FORBIDDEN_MAPS = (3511, 1820, 13000)  # 这几张图上不能创建队伍

_MSG = {
    "bad_map": to_big5("当前地图不能组队"),
    "other_map": to_big5("地图不同,不能组队"),
    "full": to_big5("组队失败,队伍已经满员!"),
    "refuse": to_big5("对方拒绝加入队伍"),
}
_LEAVE_PREFIX = bytes.fromhex("aa b1 ae 61") + b":"  # 玩家:
_LEAVE_SUFFIX = bytes.fromhex("b2 e6 d6 c3 b6 a4 a5 ee")  # 脫离隊伍


@dataclass
class Info:
    """teams 需要知道的在线玩家信息。"""

    map: int
    name: str


def _le(n: int) -> bytes:
    return (n & 0xFFFFFFFF).to_bytes(4, "little")


def _text(jyid: int, key: str) -> Out:
    return (jyid, 0x1A, b"\x64" + _MSG[key], False)


class Teams:
    def __init__(self) -> None:
        self.slots: dict[int, list[int]] = {}  # 队伍号 -> 7 格（jyid，0 = 空）
        self.team_of: dict[int, int] = {}  # jyid -> 队伍号，缺省 = 0
        self._next = 1

    # ---- 辅助
    def _same_team(self, team: int, online: dict[int, Info]) -> list[int]:
        """「队伍号等于 team」的在线玩家；team = 0 就是所有没组队的人。"""
        return [j for j in online if self.team_of.get(j, 0) == team]

    @staticmethod
    def _all(online: dict[int, Info], op: int, payload: bytes) -> list[Out]:
        return [(j, op, payload, False) for j in online]

    # ---- 0x26 创建
    def create(self, me: int, payload: bytes, online: dict[int, Info]) -> list[Out]:
        """当前地图是 3511 / 1820 / 13000 → 自己收 0x1A「當前地圖不能組隊」。否则新建队伍（自己在格 0，**不管原来是否已在队伍里**，
        旧队伍的格子照旧残留），全服收 0x2A = 队长 jyid + `01 00` + 载荷原样。"""
        if me not in online:
            return []
        if online[me].map in FORBIDDEN_MAPS:
            return [_text(me, "bad_map")]
        tid = self._next
        self._next += 1
        self.slots[tid] = [me] + [0] * (SLOTS - 1)
        self.team_of[me] = tid
        return self._all(online, 0x2A, _le(me) + b"\x01\x00" + payload)

    # ---- 0x2C 邀请
    def invite(self, me: int, payload: bytes, online: dict[int, Info]) -> list[Out]:
        """载荷前 4 字节（不足补 0）= 对方 jyid（小端）。对方在线（可以是自己、可以在别的地图）→ 对方收 0x2E = 邀请人 jyid。"""
        target = int.from_bytes(payload[:4], "little")
        if me not in online or target not in online:
            return []
        return [(target, 0x2E, _le(me), False)]

    # ---- 0x2D 应答
    def reply(self, me: int, payload: bytes, online: dict[int, Info]) -> list[Out]:
        """载荷 = 子类型(1) + 邀请人 jyid(前 4 字节)…，至少 2 字节。子类型 ≠ 01 = 拒绝：只有自己收 0x1A「對方拒絕加入隊伍」。
        01 = 接受：邀请人必须在线且已在队伍里（否则原版崩，这里静默）、同一张地图（否则自己收「地圖不同,不能組隊」）、
        队伍没满（7 格；满了自己收「組隊失敗,隊伍已經滿員!」）；成功 → 占第一个空格，自己的队伍号 = 邀请人的，
        全服收 0x2F = `01` + 自己 jyid + 载荷第 2 字节起原样。原版还有个「对方繁忙」检查（邀请人处于战斗之类状态），这里没有这个状态。"""
        if me not in online or len(payload) < 2:
            return []
        if payload[0] != 0x01:
            return [_text(me, "refuse")]
        inviter = int.from_bytes(payload[1:5], "little")
        tid = self.team_of.get(inviter, 0)
        if inviter not in online or tid == 0 or tid not in self.slots:
            return []
        if online[me].map != online[inviter].map:
            return [_text(me, "other_map")]
        slots = self.slots[tid]
        free = next((i for i, v in enumerate(slots) if v == 0), None)
        if free is None:
            return [_text(me, "full")]
        slots[free] = me
        self.team_of[me] = tid
        return self._all(online, 0x2F, b"\x01" + _le(me) + payload[1:])

    # ---- 0x2E 队伍聊天
    def chat(self, me: int, payload: bytes, online: dict[int, Info]) -> list[Out]:
        """队伍里（或同样「没队伍」的所有人）收到 0x1C = 载荷去掉前 4 字节（原版拼包时的怪行为，前 4 字节被吃掉）。"""
        if me not in online:
            return []
        return [(j, 0x1C, payload[4:], False) for j in self._same_team(self.team_of.get(me, 0), online)]

    # ---- 0x27 解散
    def disband(self, me: int, online: dict[int, Info]) -> list[Out]:
        """队伍里的**任何人**都能解散：全服收 0x2B = 发起人 jyid；队长（格 0）、其余各格、发起人的队伍号全清 0，队伍的格子清空。没队伍：静默。"""
        tid = self.team_of.get(me, 0)
        if me not in online or tid == 0 or tid not in self.slots:
            return []
        slots = self.slots[tid]
        self.team_of[slots[0]] = 0
        out = self._all(online, 0x2B, _le(me))
        for v in slots[1:]:
            if v:
                self.team_of[v] = 0
        self.team_of[me] = 0
        self.slots[tid] = [0] * SLOTS
        return out

    # ---- 0x29 离队
    def leave(self, me: int, online: dict[int, Info]) -> list[Out]:
        """在队伍里：在格 1–6 里找自己（**格 0 不找**——队长离不开），找到就清格、队伍号归 0、全服收 0x2D = 自己 jyid。
        然后**不管有没有队伍**，原队伍号（没队伍 = 0）的人（此时已不含自己，若找到过）收 0x1A「玩家:<名字>脫离隊伍」——
        没队伍的人发 0x29 会让所有没组队的人（含自己）收到这条。"""
        if me not in online:
            return []
        tid = self.team_of.get(me, 0)
        out: list[Out] = []
        if tid and tid in self.slots:
            slots = self.slots[tid]
            idx = next((i for i in range(1, SLOTS) if slots[i] == me), None)
            if idx is not None:
                self.team_of[me] = 0
                slots[idx] = 0
                out += self._all(online, 0x2D, _le(me))
        msg = b"\x64" + _LEAVE_PREFIX + to_big5(online[me].name) + _LEAVE_SUFFIX
        out += [(j, 0x1A, msg, False) for j in self._same_team(tid, online)]
        return out

    # ---- 下线
    def on_logout(self, me: int, online: dict[int, Info]) -> list[Out]:
        """玩家下线（在 online 里还有他时调用）：在队伍里 → 队长走解散（全服收 0x2B），其他人走离队（0x2D + 队内 0x1A）。"""
        tid = self.team_of.get(me, 0)
        if not tid or tid not in self.slots:
            self.team_of.pop(me, None)
            return []
        out = self.disband(me, online) if self.slots[tid][0] == me else self.leave(me, online)
        self.team_of.pop(me, None)
        return out
