#!/usr/bin/env python3
"""战斗协议（客户端侧）——收包状态、发包构造、客户端自己的胜负判定与怪物出招 AI。
依据 战斗协议_客户端侧.md（loginp.exe 反编译）。没有真实对局抓包验证，凡是文档标【推】/【未解】的地方这里也是假设：
  * C2S 0xD7 玩家 [13][14] 的混淆种子 SEED 未知，默认 0（新服务端不校验）；
  * C2S 校验尾字节的字符表未知，默认用 0x41；
  * 怪物出招间隔（D5 里 A、B 两字节的精确含义未解）用固定间隔 + 抖动；
  * E5 载荷按服务端侧旧实测：jyid(LE32) + 1 字节。
纯标准库；JyClient 通过 apply() 折进状态，通过 build_* 构造 C2S 载荷。
"""
import random
import struct
import time

MOB_BASE = 100000000          # 实体 id >= 1e8 = 怪物实例
RES_WIN, RES_LOSE = 0x16, 0x0B
RES_ESCAPE = 6            # 原版结果码 6 = 逃跑/退出（FUN_009973a8：结果 6 / 33 立即上报，不等 15 秒）
END_DELAY = 15.0              # 客户端判定结果后等多久再发 E5（反编译：未到 15001ms 且结果不是 6/33 就等）
BASIC_SKILL = 800301          # 基本剑法·第 1 招（武功 id×100+招式序号），怪物 AI 的默认出招


def is_mob(eid):
    return eid >= MOB_BASE


def mob_id(eid):
    return eid % 100000


def mob_slot(eid):
    return (eid % MOB_BASE) // 100000


FALLBACK_CELLS = [(30, 27), (31, 28), (29, 29), (32, 27), (28, 28)]    # 服务端一直没发 D4 时，怪物显示 / 瞄准用的兜底格（抓包里怪常站的位置）


class Ent:
    def __init__(self, eid, A=0, B=0):
        self.id = eid
        self.team = 2 if is_mob(eid) else 1
        self.hp = None
        self.maxhp = None
        self.col = self.row = None
        self.dir = 0
        self.A, self.B = A, B
        self.alive = True
        self.left = False         # 收到 E6（离场）
        self.cmd = 0
        self.skill = 0
        self.next_act = 0.0       # 客户端 AI 的下次出招时刻（只对怪物用）
        self.cell_guess = False   # 格子是兜底值（没收到 D4）

    def view(self):
        return {"id": self.id, "team": self.team, "hp": self.hp, "maxhp": self.maxhp, "col": self.col, "row": self.row,
                "dir": self.dir, "alive": self.alive, "mob": mob_id(self.id) if is_mob(self.id) else None}


class FightState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.ents = {}
        self.items = {}           # (col,row) -> 物品 id（E4 放、E8 清）
        self.events = []          # 给界面的事件流：{"n": 序号, "k": 种类, ...}
        self._n = 0
        self.ready = False        # C6
        self.d1 = None
        self.srv_result = None    # S2C 0x81 第 1 字节：1 = 存活 2 = 气血为 0
        self.ended_by_server = False    # 收到自己的 E6
        self.result = 0           # 客户端自己判的结果码 0 / 0x16 / 0x0B
        self.result_at = 0.0
        self.end_sent = False
        self.escaped = False      # 收到 S2C F9 = 01（逃跑成功）；成功后由客户端自己发 E5（服务端说明，原版是否如此是推测）
        self.entered = False

    def ev(self, k, **kw):
        self._n += 1
        d = {"n": self._n, "k": k}
        d.update(kw)
        self.events.append(d)
        if len(self.events) > 400:
            del self.events[:100]
        return d

    def ent(self, eid):
        e = self.ents.get(eid)
        if e is None:
            e = self.ents[eid] = Ent(eid)
        return e

    # ---------- 收 ----------
    def apply(self, t, p, me_id=None, me_fields=None):
        """折一帧 S2C。返回 True 表示这帧属于战斗协议（已处理）。"""
        if t == 0xC6:
            self.ready = True
            return True
        if t == 0xD1 and len(p) >= 4:
            self.d1 = bytes(p)
            self.active = True
            return True
        if t == 0xD5 and len(p) >= 2:
            if self.ended_by_server:
                self.reset()
            n = struct.unpack_from("<H", p, 0)[0]
            for k in range(n):
                o = 2 + 6 * k
                if o + 6 > len(p):
                    break
                eid = struct.unpack_from("<I", p, o)[0]
                e = self.ent(eid)
                e.A, e.B = p[o + 4], p[o + 5]
                e.alive, e.left = True, False
                if e.col is None and is_mob(eid):          # D4 通常在 D5 之后才到，到了会覆盖；没到就用兜底格（D4 里的格子服务端不一定还原）
                    e.col, e.row = FALLBACK_CELLS[mob_slot(eid) % len(FALLBACK_CELLS)]
                    e.cell_guess = True
                self.ev("join", id=eid, team=e.team)
            self.active = True
            return True
        if t == 0xDC and len(p) >= 2:
            n = struct.unpack_from("<H", p, 0)[0]
            for k in range(n):
                o = 2 + 21 * k
                if o + 14 > len(p):
                    break
                eid = struct.unpack_from("<I", p, o)[0]
                hp = struct.unpack_from("<I", p, o + 8)[0]
                e = self.ent(eid)
                e.hp = hp
                if e.maxhp is None or hp > e.maxhp:
                    e.maxhp = hp
                e.alive = hp > 0
                self.ev("hp", id=eid, hp=hp, delta=0)
            self.active = True
            return True
        if t == 0xD8 and len(p) >= 9:
            for o in range(1, len(p) - 7, 8):
                eid, hp = struct.unpack_from("<II", p, o)
                e = self.ent(eid)
                old = e.hp
                e.hp = hp
                if e.maxhp is None or hp > e.maxhp:
                    e.maxhp = hp
                e.alive = hp > 0
                if me_fields is not None and eid == me_id:
                    me_fields["dangqianxue"] = hp
                self.ev("hp", id=eid, hp=hp, delta=(old - hp) if old is not None else 0)
            return True
        if t == 0xD7 and len(p) >= 16:
            eid = struct.unpack_from("<I", p, 0)[0]
            e = self.ent(eid)
            e.cmd = 3 if p[4] == 0x10 else p[4]
            e.skill = struct.unpack_from("<I", p, 6)[0]
            e.dir = p[15]
            self.ev("act", id=eid, cmd=e.cmd, skill=e.skill, col=p[11], row=p[12], tcol=p[13], trow=p[14], dir=p[15])
            return True
        if t == 0xD4 and len(p) >= 6:
            eid = struct.unpack_from("<I", p, 0)[0]
            e = self.ent(eid)
            e.col, e.row = p[4], p[5]
            e.cell_guess = False
            self.ev("move", id=eid, col=p[4], row=p[5])
            return True
        if t == 0xE4 and len(p) >= 4:
            for o in range(0, len(p) - 3, 4):
                cell = (p[o], p[o + 1])
                item = struct.unpack_from("<H", p, o + 2)[0]
                self.items[cell] = item
                self.ev("drop", col=cell[0], row=cell[1], item=item)
            return True
        if t == 0xE8 and len(p) >= 6:
            eid = struct.unpack_from("<I", p, 0)[0]
            cell = (p[4], p[5])
            item = self.items.pop(cell, 0)
            self.ev("pick", id=eid, col=cell[0], row=cell[1], item=item)
            return True
        if t == 0xE6 and len(p) >= 4:
            eid = struct.unpack_from("<I", p, 0)[0]
            e = self.ent(eid)
            e.left = True
            if me_id is not None and eid == me_id:
                self.ended_by_server = True          # 自己的 E6 = 战斗结束（不改"存活"：气血为 0 才算倒下）
            else:
                e.alive = False
            self.ev("leave", id=eid, me=eid == me_id)
            return True
        if t == 0xE7 and len(p) >= 5:
            for o in range(0, len(p) - 4, 5):
                self.ent(struct.unpack_from("<I", p, o)[0]).dir = p[o + 4]
            return True
        if t == 0xEF and len(p) >= 5:                    # 服务端拒绝：没在战斗里发了战斗内上报（jyid + 10）
            self.ev("refuse", code=p[4])
            return True
        if t == 0xF9 and self.active and len(p) >= 1:    # 逃跑应答（回 C2S F9）：1 字节，01 成功 / 00 失败；不改战斗状态，成功后客户端自己发 E5
            ok = p[0] == 1
            if ok:
                self.escaped = True
            self.ev("escape", ok=ok)
            return True
        if t == 0x81 and self.active and len(p) >= 1:
            self.srv_result = p[0]
            self.ev("srv_result", v=p[0])
            return True
        return False

    # ---------- 客户端自己的判定（FUN_009973a8 的简化：按队伍统计存活） ----------
    def counts(self):
        a = sum(1 for e in self.ents.values() if e.team == 1 and e.alive and not e.left)
        b = sum(1 for e in self.ents.values() if e.team == 2 and e.alive and not e.left)
        return a, b

    def judge(self, now=None):
        """返回结果码：0 进行中 / 0x16 我方胜 / 0x0B 我方败。第一次得出非 0 结果时记下时刻。"""
        now = time.time() if now is None else now
        if not self.active or not self.ents or self.end_sent:
            return self.result
        a, b = self.counts()
        res = 0
        known_enemy = any(e.team == 2 for e in self.ents.values())
        known_ally = any(e.team == 1 for e in self.ents.values())
        if self.escaped:
            res = RES_ESCAPE
        elif known_ally and a == 0:
            res = RES_LOSE
        elif known_enemy and b == 0:
            res = RES_WIN
        if res and not self.result:
            self.result_at = now
        self.result = res
        return res

    def end_due(self, now=None, delay=END_DELAY):
        """判定结果已出、且等够了 delay 秒、还没上报 → True（调用方发 E5）。"""
        now = time.time() if now is None else now
        if self.judge(now) and not self.end_sent and now - self.result_at >= (0 if self.result == RES_ESCAPE else delay):
            return True
        return False

    # ---------- 怪物出招 AI（反编译：FUN_009a8220，客户端替怪发 C2S D7） ----------
    def plan_enemy_acts(self, me_id, now=None, interval=4.0, jitter=1.5, rng=random):
        """到点的怪物各出一招，返回 [(怪 id, 目标 id)]。目标 = 第一个活着的我方（单人战斗就是玩家）。"""
        now = time.time() if now is None else now
        if not self.active or self.result or self.end_sent:
            return []
        targets = [e for e in self.ents.values() if e.team == 1 and e.alive and not e.left]
        if not targets:
            return []
        tgt = next((e for e in targets if e.id == me_id), targets[0])
        out = []
        for e in self.ents.values():
            if e.team != 2 or not e.alive or e.left:
                continue
            if e.next_act == 0.0:
                e.next_act = now + 1.0 + rng.random() * jitter
            if now >= e.next_act:
                e.next_act = now + interval + rng.random() * jitter
                out.append((e.id, tgt.id))
        return out

    def view(self):
        a, b = self.counts()
        return {"active": self.active, "over": self.ended_by_server, "end_sent": self.end_sent, "result": self.result, "srv_result": self.srv_result,
                "ents": [dict(e.view(), rem=(max(0.0, e.next_act - time.time()) if e.next_act else None)) for e in self.ents.values()], "items": [{"col": c, "row": r, "item": i} for (c, r), i in self.items.items()],
                "counts": [a, b], "events": self.events[-60:]}


# ---------- 发：载荷构造（opcode 由调用方给） ----------
def build_encounter(entity_id, count=1):
    """C2S 0x30：怪物实体 id + 19 字节。原版客户端填零（= 1 只）；新服务端的扩展：第一个填充字节 = 同种怪的数量 1–5（实体 id 依次 +1e5）。
    实体 id < 10000001 时原版只回我方名单、不进战斗。"""
    return struct.pack("<I", entity_id) + bytes([max(1, min(5, int(count))) if count and count > 1 else 0]) + b"\x00" * 18


def build_enter(jyid, col, row, flag=1, tail=0x41):
    """C2S 0xE3 进战：jyid + 格 col row + 01 + 尾校验字节。"""
    return struct.pack("<I", jyid) + bytes([col & 0xFF, row & 0xFF, flag & 0xFF, tail & 0xFF])


def build_act(caster, cmd, skill, cell, target_cell, level=0, tick=0, direction=0, mob=False, jyid=None, seed=0, b5=None, b10=None, tail=0):
    """C2S 0xD7 出招，28 字节（布局见文档 §2.1）。
    cell = (col,row) → [11][12]；target_cell → 玩家发混淆值 [13][14]，怪直接发目标格。"""
    jyid = caster if jyid is None else jyid
    if b5 is None:
        b5 = 1 if mob else 1
    if b10 is None:
        b10 = 5 if mob else 0
    if mob:
        t13, t14 = target_cell
    else:
        t13 = ((jyid + seed + 0x0B) % 100) ^ target_cell[0]
        t14 = ((jyid + seed + 0x17) % 100) ^ target_cell[1]
    b = bytearray(28)
    struct.pack_into("<I", b, 0, caster)
    b[4], b[5] = cmd & 0xFF, b5 & 0xFF
    struct.pack_into("<I", b, 6, skill)
    b[10] = b10 & 0xFF
    b[11], b[12] = cell[0] & 0xFF, cell[1] & 0xFF
    b[13], b[14] = t13 & 0xFF, t14 & 0xFF
    b[15] = direction & 0xFF
    struct.pack_into("<H", b, 21, tick & 0xFFFF)
    struct.pack_into("<H", b, 25, level & 0xFFFF)
    b[27] = tail & 0xFF
    return bytes(b)


# 战斗命令号 = 命令表（loginp.exe 全局串表 0xa12310，36 项）的下标，也是 G+0x24d83f3 / 实体动作字节 G+0x25d 的取值；
# 执行入口 FUN_009901a4（0x9901a4）按命令号走跳转表 0x99037b。逆向见 逆向笔记_loginp.md「战斗命令栏」。
CMD = {"move": 1, "attack": 2, "special": 3, "hidden": 4, "poison": 5, "heal": 6, "defend": 7, "dodge": 8, "rest": 9,
       "escape": 10, "auto": 11, "equip": 12, "kungfu": 13, "system": 14, "attr": 15, "formation": 16, "neigong": 17,
       "qinggong": 18, "seal": 19, "tame": 20, "merc": 21}
CMD_NAMES = {1: "移動", 2: "一般攻擊", 3: "特殊攻擊", 4: "暗器", 5: "毒術", 6: "醫療", 7: "防禦", 8: "閃躲", 9: "養精蓄銳",
             10: "逃跑", 11: "自動", 12: "裝備", 13: "武功", 14: "系統", 15: "屬性", 16: "陣法", 17: "內功", 18: "輕功",
             19: "封穴", 20: "馴服", 21: "傭兵"}
# 发 C2S 0xDE（"原地姿态"类命令）的命令号：防禦 7 / 閃躲 8 / 養精蓄銳 9 / 自動 11；逃跑 10 发空载荷的 C2S 0xF9；裝備 12 只开窗口、不发包
POSE_CMDS = (7, 8, 9, 11)
OP_POSE, OP_ESCAPE = 0xDE, 0xF9


def build_pose(jyid, cmd, counter=0, tail=0):
    """C2S 0xDE，10 字节：自己的 jyid(LE32) + 命令号(1) + 计数器(LE32，和 D7 同一个"攻击间隔"计数器) + 校验字节(1)。
    布局来自 FUN_009b6874 的 0xDE 分支（0x9ba31b 起）；服务端旧版会用计数器 / 校验字节防外挂，新服务端不校验。"""
    return struct.pack("<I", jyid) + bytes([cmd & 0xFF]) + struct.pack("<I", counter & 0xFFFFFFFF) + bytes([tail & 0xFF])


def build_escape():
    """C2S 0xF9 逃跑：空载荷（原版只在"逃離點"上才发，否则本地提示"此處非逃離點"；条件在客户端，服务端按自己的规则回应）。"""
    return b""


def build_end(jyid, tail=0x41):
    """C2S 0xE5 战斗结束上报：jyid + 1 字节（服务端侧旧实测）。载荷不含胜负。"""
    return struct.pack("<I", jyid) + bytes([tail & 0xFF])


def build_move(entity_id, col, row, tick=0, key=0):
    """C2S 0xD4 战斗内移动：实体 id + 目标格 col row（原版：两个坐标字节各异或第 3 个字节"密钥"，密钥 = 个人底数 + D1 里的随机数；
    新服务端不还原、原样回显，所以密钥填 0 = 明文）+ 保留字节 + tick(LE16 @8) + 补零到 13 字节。"""
    b = bytearray(13)
    struct.pack_into("<I", b, 0, entity_id)
    b[4], b[5], b[6] = (col ^ key) & 0xFF, (row ^ key) & 0xFF, key & 0xFF
    struct.pack_into("<H", b, 8, tick & 0xFFFF)
    return bytes(b)
