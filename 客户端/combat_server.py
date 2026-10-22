#!/usr/bin/env python3
"""战斗模拟服务端：在 jyserver（网金复刻 新服务端）上叠一层**按 战斗协议_客户端侧.md §8 写的**最小战斗，
只用来验证网页 / jyclient 的战斗收发。不是新服务端的战斗实现——伤害公式、掉落、怪物表都是假的（见常量）。

    JY_SERVER_REPO=<含 jyserver/ 的目录> python combat_server.py --port 6735 --chars <库> --tick 0 --autosave 0     （参数同 jyserver.server）

流程（单人）：
  C2S 0x30 (怪实体 id + 19B) → S2C D1(24B) 82 DC(我方)；实体 id < 10000001 只回我方 D5、不进战斗
  C2S 0xE3 进战             → S2C D5(我方) D5(敌方) D4×敌 DC(敌方) C6
  C2S 0xD7 出招             → S2C D7(转发前 16B) + D8(被打者新气血)；气血为 0 的怪 → E6 + E4 + 77 + E8
                              被打的是玩家 → 同时 7B 18
  C2S 0xE5                  → S2C 81(01|02) 82 E6(jyid) 7B 18
"""
import logging
import os
import struct
import sys

sys.path.insert(0, os.environ.get("JY_SERVER_REPO") or r"C:\游戏\网金复刻")      # 新服务端（jyserver 包）所在目录；Mac 上设 JY_SERVER_REPO
import jyserver.server as S  # noqa: E402

MOBS = {38166: ("倭寇", 19000, 135, 15019), 38268: ("野蛮人", 25000, 140, 15019)}   # mob_id -> 名, 血, 攻, 掉落物
PLAYER_DMG = 7000          # 玩家一招打掉的血（假的）
MOB_DMG = 120              # 怪一招打掉的血（假的）
MOB_COUNT = 3
ENEMY_CELLS = [(30, 27), (31, 28), (29, 29), (32, 27), (28, 28)]

log = logging.getLogger("combat")


class Battle:
    def __init__(self, conn, base_mob_id, count):
        self.c = conn
        self.mobs = {}                      # 实体 id -> {hp, max, cell, mob}
        name, hp, atk, drop = MOBS.get(base_mob_id, ("怪", 20000, 100, 15019))
        self.drop = drop
        for k in range(count):
            eid = 100000000 + k * 100000 + base_mob_id
            self.mobs[eid] = {"hp": hp, "max": hp, "cell": ENEMY_CELLS[k % len(ENEMY_CELLS)], "mob": base_mob_id, "atk": atk}
        self.entered = False
        self.ended = False


def le(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


class CombatServer(S.GameServer):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.battles = {}
        self.esc_tries = {}                        # jyid -> 本场已发 F9 的次数（假应答用，见 on_escape）
        self.handlers.update({0x30: self.on_encounter, 0xE3: self.on_enter, 0xD7: self.on_act, 0xE5: self.on_end, 0xE6: self.on_end, 0xD4: self.on_move, 0xDE: self.on_pose, 0xF9: self.on_escape})

    def leave(self, c):
        self.battles.pop(getattr(c, "jyid", None), None)
        super().leave(c)

    def _hp(self, c):
        return int(c.renwu.get("dangqianxue") or 0)

    def on_encounter(self, c, f):
        p = f.payload
        if len(p) < 4:
            return
        eid = struct.unpack_from("<I", p, 0)[0]
        me = c.jyid
        if os.environ.get("COMBAT_HP") and eid >= 10000001:         # 测试用：把玩家气血设成固定值（隔离库里的测试号只有 1 点血）
            c.renwu["dangqianxue"] = os.environ["COMBAT_HP"]
            c.send(0x7B, bytes([0x18, 0x01]) + le(int(os.environ["COMBAT_HP"])))
        hp = self._hp(c)
        c.send(0xD5, struct.pack("<H", 1) + le(me) + bytes([0x14, 0x09]))      # 我方名单
        if eid < 10000001:
            return
        cnt = p[4] if len(p) > 4 and 1 <= p[4] <= 5 else MOB_COUNT      # 0x30 填充字节 0 = 同种怪数量（新服务端扩展）
        b = Battle(c, eid % 100000, cnt)
        self.battles[me] = b
        self.esc_tries.pop(me, None)
        c.send(0xD1, b"\x01\x00" + le(eid) + b"\x00" * 10 + le(25) + b"\x00" * 4)
        c.send(0x82, le(me) + b"\x02\x00")
        c.send(0xDC, struct.pack("<H", 1) + le(me) + b"\x01\x00\x00\x00" + le(hp) + b"\x00" * 9)

    def on_enter(self, c, f):
        b = self.battles.get(c.jyid)
        if not b or b.entered:
            return
        b.entered = True
        c.send(0xD5, struct.pack("<H", 1) + le(c.jyid) + bytes([0x14, 0x09]))
        recs = b"".join(le(eid) + bytes([0x55, 0x08]) for eid in b.mobs)
        c.send(0xD5, struct.pack("<H", len(b.mobs)) + recs)
        for eid, m in b.mobs.items():
            c.send(0xD4, le(eid) + bytes(m["cell"]))
        body = b"".join(le(eid) + b"\x01\x00\x00\x00" + le(m["hp"]) + b"\x00" * 9 for eid, m in b.mobs.items())
        c.send(0xDC, struct.pack("<H", len(b.mobs)) + body)
        c.send(0xC6, b"")

    def on_act(self, c, f):
        p = f.payload
        b = self.battles.get(c.jyid)
        if not b or not b.entered or b.ended or len(p) < 16:
            return
        caster = struct.unpack_from("<I", p, 0)[0]
        c.send(0xD7, bytes(p[:16]))                                         # 转发前 16 字节（动画触发）
        if caster < 100000000:                                              # 玩家出招 → 打第一只活着的怪（或 [11][12] 命中的格）
            cell = (p[11], p[12])
            tgt = next((e for e, m in b.mobs.items() if m["hp"] > 0 and m["cell"] == cell), None) or next((e for e, m in b.mobs.items() if m["hp"] > 0), None)
            if tgt is None:
                return
            m = b.mobs[tgt]
            m["hp"] = max(0, m["hp"] - PLAYER_DMG)
            c.send(0xD8, b"\x01" + le(tgt) + le(m["hp"]))
            if m["hp"] == 0:
                c.send(0xE6, le(tgt))
                col, row = m["cell"]
                c.send(0xE4, bytes([col, row]) + struct.pack("<H", b.drop))
                c.send(0x77, le(b.drop) + b"\xc8\x01")
                c.send(0xE8, le(c.jyid) + bytes([col, row]))
        else:                                                               # 怪出招（客户端替怪发）→ 打玩家
            m = b.mobs.get(caster)
            if not m or m["hp"] == 0:
                return
            hp = max(0, self._hp(c) - MOB_DMG)
            c.renwu["dangqianxue"] = str(hp)
            c.send(0xD8, b"\x01" + le(c.jyid) + le(hp))
            c.send(0x7B, bytes([0x18, 0x01]) + le(hp))

    def on_move(self, c, f):
        """0xD4：原样回显 实体 id + 两个坐标字节（和 jyserver 一样，不还原异或）。"""
        b = self.battles.get(c.jyid)
        if b and b.entered and len(f.payload) >= 6:
            c.send(0xD4, bytes(f.payload[:6]))

    def on_pose(self, c, f):
        """0xDE（防禦 7 / 閃躲 8 / 養精蓄銳 9 / 自動 11，10 字节：jyid + 命令号 + 计数器 + 校验）→ 回 S2C D7 转发（前 16 字节，cmd = 命令号，技能 0）。
        原版服务端怎么回这条没抓过，这里是推测（和出招转发同形）。"""
        b = self.battles.get(c.jyid)
        p = f.payload
        if not b or not b.entered or b.ended or len(p) < 10 or p[4] not in (7, 8, 9, 11):
            return
        c.send(0xD7, le(c.jyid) + bytes([p[4]]) + bytes(11))

    def on_escape(self, c, f):
        """0xF9 逃跑（空载荷）→ 回 S2C F9 短帧 1 字节（01 成功 / 00 失败），**不改战斗状态**，成功后由客户端自己发 E5（和 jyserver 现在一样）。
        真服务端是约 40% 随机；这里为了测试可重复：环境变量 COMBAT_ESCAPE=1 总成功、=0 总失败，缺省 = 每场第 1 次失败、第 2 次起成功。"""
        n = self.esc_tries[c.jyid] = self.esc_tries.get(c.jyid, 0) + 1
        mode = os.environ.get("COMBAT_ESCAPE")
        ok = (mode == "1") if mode in ("0", "1") else n >= 2
        c.send(0xF9, b"\x01" if ok else b"\x00")

    def on_end(self, c, f):
        b = self.battles.pop(c.jyid, None)
        if not b:
            return
        hp = self._hp(c)
        c.send(0x81, b"\x01" if hp > 0 else b"\x02")
        c.send(0x82, le(c.jyid) + b"\x00\x00")
        c.send(0xE6, le(c.jyid))
        c.send(0x7B, bytes([0x18, 0x01]) + le(hp))


if __name__ == "__main__":
    S.GameServer = CombatServer
    raise SystemExit(S.main())
