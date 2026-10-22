#!/usr/bin/env python3
"""NPC 对话 / 事件脚本解释器（原版 loginp.exe 的事件语义，靠 evtdata.py 的数据 + 数据里的交叉验证推出，不是照抄反编译）。

语义（每条都有证据，见 逆向笔记_loginp.md「NPC 对话与事件脚本」）：
  NPC 的"事件号"列表（NpcMrg）里每个号 = 节点表的 0 起序号 = 服务端 0x6B 的事件 id。
  点 NPC：按列表顺序找第一个主事件（t=1）且条件都满足的节点，执行它的动作表。
  条件（节点 A 列表里的条件编号 -> 条件表）：type1 = 标记/物品都有（数量不少于 n）且属性 ≥；type2 = 这些标记/物品都没有（属性不满足）；
    type3 = 属性 ==；type4 = 属性 !=。属性号 = 服务端 0x7B 子类型的十进制（61 名声 43 实战 68 历练 65 门派 66 师承 24 当前血 …）。
  动作种类：1 文本（-1 分隔，-1 开头 = NPC 先说，否则玩家先说，轮流）；28 [(说话者 mob 号 | 0 = 玩家, 文本号)] 多人对话；14 提示文字（获得 …）；
    5 效果（标记 / 物品 / 属性变化——由服务端执行，这里只"发 0x6B 事件号"）；9 选单 [提示文本, (选项文本, 目标节点)…]；16 随机挑一个子事件；
    11 转到节点；10 打开商店（商人 id，对应服务端 商人.csv）；2 战斗（yield {"t":"fight","mobs":[...]}，见 fight_mobs）；其它（3 动画 / 19 彩票 / 26 分支 / 27 时间 …）还没解。
引擎是生成器：yield 出"要给浏览器看的一步"，选单步用 .send(选项下标) 回答。
"""
import random
import struct

ATTR_FIELDS = {            # 属性号（0x7B 子类型的十进制）-> (me["fields"] 列, 偏移)
    24: ("dangqianxue", 0), 22: ("dangqianjing", 0), 26: ("dangqianshen", 0), 27: ("dangqiannei", 0), 23: ("zuidaxue", 0),
    30: ("str", 0), 31: ("crg", 0), 32: ("wint", 0), 33: ("luk", 0), 34: ("dex", 0), 35: ("agi", 0), 36: ("vit", 0),
    40: ("study_count", 0), 43: ("combat_exp", 0), 55: ("kill_val", 0), 56: ("pk_val", 0), 60: ("jy_money", 0),
    61: ("fame_val", 0), 65: ("school", 0), 66: ("master", 0), 68: ("exp_val", 0), 69: ("evil_val", -2000),
}


class PlayerState:
    """条件判断要的玩家状态。bag_ids 是背包记录里的物品 / 标记号（每件一条），fields 是 me["fields"]。"""

    def __init__(self, bag_ids, fields, kf=None, status=None, clock=None):
        self.counts = {}
        for i in bag_ids:
            self.counts[i] = self.counts.get(i, 0) + 1
        self.fields = fields
        self.kf = dict(kf or {})              # 武功号 -> 等级（0x1E 的 kf 行）
        self.clock = clock                    # 游戏时钟（服务端心跳计数，每格约 75 秒）；None = 还没校过时
        self.status = dict(status or {})    # (槽 1..11, 类 0..3) -> 数值：原版客户端 +0x756e 起的 16 条"状态"表，服务端目前没有推，空 = 都没有

    def count(self, i):
        return self.counts.get(i, 0)

    def kf_level(self, i):
        return self.kf.get(i)

    def calendar(self):
        """游戏日历（原版 0x6bdad8）：时钟 T（每格 75 秒）→ (年, 月 0..11, 日 0..29, 时辰 0..11, 刻 0..7)；一天 96 格，一月 30 天，一年 12 月。"""
        if self.clock is None:
            return None
        t = self.clock
        return t // 34560, t % 34560 // 2880, t % 2880 // 96, t % 96 >> 3, t & 7

    def attr(self, code):
        col = ATTR_FIELDS.get(code)
        if not col or col[0] not in self.fields:
            return None
        return self.fields[col[0]] + col[1]


def _cmp(mode, a, v):
    """原版比较器（0x7794b4 / 0x7810xx / 0x781bc1）：模式 0 ≥、1 <、2 ==、3 ≠"""
    return (a >= v, a < v, a == v, a != v)[mode]


# 原版客户端条件分发（0x922344，switch 0..0x20）里直接 mov bl,1 的类型；类型 0 走 default，同样成立。
ALWAYS_TRUE_CONDS = {0, 7, 8, 9, 10, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x1B, 0x1C}
# 原版动作分发（FUN_006cbdf4，switch 0..0x23）里只"跳到下一个动作"或落到 default 的类型：客户端什么都不做（有的由服务端执行）
NOOP_ACTIONS = {0, 4, 6, 7, 8, 0x0C, 0x0D, 0x11, 0x15, 0x17, 0x18, 0x1D, 0x1E, 0x1F, 0x21}


def _elements(cond, state):
    """条件里的每一项各自求值，返回 [(结果, 是否猜的)]。顺序同原版（0x9223f3）：属性、武功、标记/物品。
    三个列表在原版里对应：属性 +0x40（6 字节 [u16 号, i32 值]，0x7794b4 比较）、武功 +0x44（10 字节 [u16 武功号, i32 等级, i32]，
    0x781068：按武功号在玩家武功表里找，找到就比等级，找不到 = 模式 1 / 3 成立、0 / 2 不成立）、标记/物品 +0x3c（6 字节 [u16 号, i32 个数]，0x781910：数身上的个数）。"""
    t = cond["type"]
    mode = t - 1 if t <= 4 else t - 0xB
    out = []
    for code, v in cond.get("attrs", []):
        a = state.attr(code)
        out.append((True, True) if a is None else (_cmp(mode, a, v), False))
    for i, n, _ in cond.get("items", []):
        lv = state.kf_level(i)
        out.append((mode in (1, 3), False) if lv is None else (_cmp(mode, lv, n), False))
    for i, n in cond.get("marks", []):
        out.append((_cmp(mode, state.count(i), n), False))
    return out


# 动作 0x13（"界面"）的二级分发（0x6ce0f6，跳转表 0x6ce1b2，231 项）：这些功能号的处理块只调"下一个动作"（0x6cb3fc），没有别的调用也没有文字 = 客户端什么都不做（原版里 137 处）
NOOP_UI = {2, 14, 18, 19, 22, 30, 31, 33, 54, 55, 56, 58, 62, 65, 66, 70, 71, 72, 73, 74, 75, 76, 77, 82, 89, 91, 92, 93, 94, 95, 96, 97, 98,
           103, 105, 106, 107, 108, 109, 111, 113, 116, 119, 120, 137, 138, 139, 151, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172,
           184, 185, 186, 187, 188, 189, 190, 191}
# 能从处理块里的提示文字认出主题的功能号
UI_NAMES = {59: "驛站（信件）", 60: "驛站（信件）", 61: "驛站（信件）", 32: "獄中玩家名單", 34: "獄中玩家名單", 38: "雇用 Q 寶", 42: "寄養 Q 寶", 43: "領取 Q 寶", 45: "Q 寶治療", 46: "Q 寶休息", 64: "娛樂場",
            67: "馬匹（已有馬匹跟隨時的提示）", 68: "馬匹（無馬匹跟隨時的提示）", 79: "Q 寶功能", 80: "Q 寶功能"}


def holds(cond, state):
    """一个条件是否成立。还没解的条件类型 / 玩家状态拿不到的属性按"成立"处理（返回 (结果, 是否猜的)）"""
    t = cond["type"]
    guessed = False
    if 1 <= t <= 4:                   # 全部成立（原版 bl 先置 1，任何一项不成立就置 0）
        els = _elements(cond, state)
        ok = all(r for r, _ in els)
        guessed = any(g for _, g in els)
    elif 0xB <= t <= 0xE:             # 同样的项，任意一项成立（bl 先置 0）
        els = _elements(cond, state)
        ok = any(r for r, _ in els)
        guessed = any(g for _, g in els)
    elif t == 0x1F:                   # v[0] 选子类型；0x922abf 的字节表只认 2、13、14、15、16，其余（含 1）直接成立
        v0 = cond["v"][0]
        ok = True
        guessed = v0 in (2, 13, 14, 15, 16)       # 2：玩家 +0x57 == 0x32；13–16：客户端内存里的一批标志字节 / 状态，没有对应数据
    elif t == 0x20:                   # 0x922bf6：v[0] 只认 1 和 4，其余（2、3）直接成立
        v = cond["v"]
        if v[0] == 4:
            ok = _status_cond(v, state)
        else:
            ok, guessed = True, v[0] == 1
    elif t == 6:                      # 游戏日历范围（0x92279c）：a / b 各 5 个下 / 上界（0xff = 不限），年 月 日 时辰 刻
        cal = state.calendar()
        if cal is None:
            ok, guessed = True, True
        else:
            ok = True
            for i, cur in enumerate(cal):
                lo, hi = cond["a"][i], cond["b"][i]
                adj = 1 if i < 3 else 0          # 年月日的界值是 1 起的，时辰 / 刻是 0 起的
                if lo != 0xFF and cur < lo - adj:
                    ok = False
                if hi != 0xFF and cur > hi - adj:
                    ok = False
    elif t in ALWAYS_TRUE_CONDS:
        ok = True                      # 原版客户端的条件分发函数里这些类型直接返回成立（FUN_00922344），由服务端或根本不判
    else:
        ok, guessed = True, True      # 还没解的类型（5 6 0x14–0x16 0x17–0x1a 0x1d 0x1e）：按成立处理并记一笔
    return ok, guessed


def _status_cond(v, state):
    """0x20 / v[0]=4（0x922dc3）：v[2] = 20000 起的编码，v[2]//100 = 210 / 220 / 230 → 类 1 / 2 / 3（其它 → 0），v[2]%100 = 0..10 → 槽 1..11；
    取玩家"状态表"里该 (槽, 类) 的数值，按 v[3]（1 ≥、2 <、3 ==、4 ≠）和 v[4] 比；v[2] < 20000 或槽号 > 10 不成立；表里没有该项 = 0。"""
    code = v[2]
    if code < 20000 or code % 100 > 10:
        return False
    cls = {210: 1, 220: 2, 230: 3}.get(code // 100, 0)
    a = state.status.get((code % 100 + 1, cls), 0)
    return {1: a >= v[4], 2: a < v[4], 3: a == v[4], 4: a != v[4]}.get(v[3], False)


def fight_mobs(a):
    """战斗动作（kind 2）里的对手：[{"mob": MOB id, "name": 名字, "n": 数量}]。
    l26 每条 26 字节 = mob id(u16) + Pascal 名字(21 字节，Big5) + u16(含义未解) + 数量(u8)；l26 为空时 v[0] 就是 MOB id（0 = 没有对手）。
    服务端目前一次遭遇只有一只怪，调用方取第一个。"""
    out = []
    for raw in a.get("l26") or []:
        if len(raw) >= 26 and int.from_bytes(raw[:2], "little"):
            ln = min(raw[2], 20)
            out.append({"mob": int.from_bytes(raw[:2], "little"), "name": raw[3:3 + ln].decode("big5", "replace"), "n": raw[25] or 1})
    if not out and (a.get("v") or [0])[0] and a["v"][0] < 100000:
        out.append({"mob": a["v"][0], "name": "", "n": 1})
    return out

class Engine:
    def __init__(self, rec, texts, state, me_name="你", npc_name="NPC", speakers=None, rng=None):
        self.rec, self.T, self.st = rec, texts, state
        self.me_name, self.npc_name = me_name, npc_name
        self.speakers = speakers or {}
        self.rng = rng or random
        self.sent = set()
        self.guessed = False

    # ---- 条件
    def node_ok(self, ni):
        nd = self.rec["nodes"][ni]
        for ci in nd["A"]:
            if ci >= len(self.rec["conds"]):
                continue
            ok, g = holds(self.rec["conds"][ci], self.st)
            self.guessed |= g
            if not ok:
                return False
        return True

    def text(self, tid):
        s = self.T.get(tid) if self.T else None
        return (s or "（缺文本 %d）" % tid).rstrip()

    # ---- 执行
    def talk(self, events):
        nodes = self.rec["nodes"]
        for ev in events:
            if 0 <= ev < len(nodes) and nodes[ev]["main"] and self.node_ok(ev):
                yield {"t": "start", "ev": ev, "name": nodes[ev]["name"]}
                yield from self.run(ev)
                return
        yield {"t": "note", "text": "（這個 NPC 現在沒有可以說的話）"}

    def pages(self, ids):
        spk_npc = bool(ids) and ids[0] == -1
        side, first = ("npc" if spk_npc else "me"), True
        prev = None
        for t in ids:
            if t == -1:
                prev = -1
                continue
            if prev == -1:
                side = "npc"
            elif not first:
                side = "me" if side == "npc" else "npc"
            first = False
            prev = t
            yield {"t": "say", "side": side, "who": self.npc_name if side == "npc" else self.me_name, "text": self.text(t)}

    def run(self, ni, depth=0):
        if depth > 30 or not 0 <= ni < len(self.rec["nodes"]):
            return
        nd = self.rec["nodes"][ni]
        for ai in nd["M"]:
            if ai >= len(self.rec["acts"]):
                continue
            a = self.rec["acts"][ai]
            k = a["kind"]
            if k == 1:
                yield from self.pages(a["ids"])
            elif k == 28:
                for spk, tid in a["list"]:
                    if spk == 0:
                        yield {"t": "say", "side": "me", "who": self.me_name, "text": self.text(tid)}
                    else:
                        yield {"t": "say", "side": "npc", "who": self.speakers.get(spk) or self.npc_name, "text": self.text(tid)}
            elif k == 14:
                yield {"t": "note", "text": " ".join(self.text(a["v"][0]).split())}
            elif k == 5:
                if ni not in self.sent:
                    self.sent.add(ni)
                    yield {"t": "effect", "ev": ni}
            elif k == 9:
                opts = [(tid, tgt) for tid, tgt in a["list"] if tgt < len(self.rec["nodes"])]
                shown = [o for o in opts if self.node_ok(o[1])] or opts
                if not shown:
                    return
                pick = yield {"t": "menu", "who": self.npc_name, "prompt": self.text(a["v"][0]), "options": [self.text(t) for t, _ in shown]}
                if not isinstance(pick, int) or not 0 <= pick < len(shown):
                    return
                yield from self.run(shown[pick][1], depth + 1)
                return
            elif k == 16:
                cand = [i for i in a["ids"] if 0 <= i < len(self.rec["nodes"]) and self.node_ok(i)]
                if cand:
                    yield from self.run(self.rng.choice(cand), depth + 1)
                return
            elif k == 11:
                yield from self.run(a["v"][0], depth + 1)
                return
            elif k == 10:
                yield {"t": "shop", "merchant": a["v"][0]}
            elif k == 2:
                mobs = fight_mobs(a)
                if mobs:
                    yield {"t": "fight", "mobs": mobs}
                else:
                    yield {"t": "todo", "kind": k, "text": "（原版這裡會進入戰鬥，這場戰鬥沒有可用的對手）"}
                return
            elif k == 3 and len(a.get("raw") or b"") >= 13:
                # 动作 3 = 传送（不是动画）：地图 u32 | x u32 | y u32（格子坐标）| 朝向 u8；传送員 / 羽士 / 各门派入口的对话选完就走这里
                m, x, y, d = struct.unpack_from("<IIIB", a["raw"], 0)
                yield {"t": "teleport", "map": m, "x": x, "y": y, "dir": d}
                return
            elif k in (3, 27) or k in NOOP_ACTIONS:
                pass          # 动画 / 时间设置 / 客户端不做事的动作：不影响对话
            elif k == 0x13 and a["v"][0] in NOOP_UI:
                pass          # 原版二级分发里这个功能号只"跳到下一个动作"
            elif k == 0x13 and a["v"][0] in UI_NAMES:
                yield {"t": "todo", "kind": k, "text": "（原版這裡會開啟「%s」，網頁版還沒有）" % UI_NAMES[a["v"][0]]}
            else:
                yield {"t": "todo", "kind": k, "text": "（原版這裡會執行介面 / 特殊動作 %d，網頁版還沒有）" % k}
