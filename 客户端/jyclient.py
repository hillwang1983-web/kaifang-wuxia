#!/usr/bin/env python3
"""金庸群侠传 Online 客户端协议库（asyncio，只用标准库）——逆向出来的"客户端"本体，不带画面。

以后网页版的网关（WebSocket <-> 本库）和任何自动化脚本都建立在它上面。

线路规则（均来自真实流量，见 逆向笔记_loginp.md / 网金复刻 docs/协议模型.md）
  C2S: F6 11 <序号> + XOR(密钥, 明文帧)；首包（序号 1，登录）密钥固定 0x9E，之后密钥 = base ^ 序号，
       base = derive_key(最近一次收到的种子)：握手种子（已有角色 -> 0x7D，新账号 -> 0x34）和之后每个 0x99 04 <种子> 换密钥帧。
  S2C: 解码交给 packet_proxy.Decoder（由帧头反推密钥；握手后跟着一个孤立的 00 字节会被它当作未成帧数据忽略）。
  文本: 线上是 BIG5。

用法（见 client_scenario.py）:
    c = JyClient("127.0.0.1", 6732, log="x.jsonl")
    await c.connect(); await c.login(123456); await c.start()
    await c.move(510, 410, 520, 410); await c.say("hello")
    await c.wait(lambda f: f.type == 0x04, 3)
    await c.close()
"""
import asyncio
import collections
import json
import os
import struct
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import packet_proxy as pp  # noqa: E402
import parse_0x1e  # noqa: E402
import jyfight  # noqa: E402
import notices  # noqa: E402
import biaoju  # noqa: E402
import lifeskill  # noqa: E402
import masters  # noqa: E402
import books  # noqa: E402

HEARTBEAT_SECS = 75.0         # 游戏时钟一格的时长（原版 0x6bdad8：距校时每满 75000 毫秒加一，最多加 3；服务端心跳约 75.6 秒一次）
LOGIN_CONST = 0x0005FCF7     # 登录帧里的常量，含义未知，照抄抓包
# 简->繁字表（可选）：环境变量 JY_S2T > <本目录>/data/s2t.json（打包后）> 开发机上网金复刻项目里那份
_HERE = os.path.dirname(os.path.abspath(__file__))
S2T_PATH = os.environ.get("JY_S2T") or (os.path.join(_HERE, "data", "s2t.json") if os.path.isfile(os.path.join(_HERE, "data", "s2t.json")) else r"C:\游戏\网金复刻\data\s2t.json")


# C2S 装备槽位号 -> renwu 列（网金复刻 docs/装备与物品.md；槽位 0、5、10 以上原版不回包）
SLOT_NAME = {1: "toukui", 2: "xianglian", 3: "yifu", 4: "pifeng", 6: "wuqi", 7: "huwan", 8: "jiezhi", 9: "xiezi"}
SLOT_LABEL = {"toukui": "头盔", "xianglian": "项链", "yifu": "衣服", "pifeng": "披风", "wuqi": "武器", "huwan": "护腕", "jiezhi": "戒指", "xiezi": "鞋子"}
# S2C 0x7B 属性更新的子类型 -> renwu 列（同上文档；2F/30 是现算的武器/防具强度，对应 0x1E 里的 wuqiqiangdu/fangjuqiangdu）
STAT_COL = {0x16: "dangqianjing", 0x1A: "dangqianshen", 0x18: "dangqianxue", 0x1B: "dangqiannei", 0x17: "zuidaxue",
            0x1E: "str", 0x1F: "crg", 0x20: "wint", 0x21: "luk", 0x22: "dex", 0x23: "agi", 0x24: "vit",
            0x28: "study_count", 0x2B: "combat_exp", 0x2F: "wuqiqiangdu", 0x30: "fangjuqiangdu",
            0x34: "diet_val", 0x36: "water_val", 0x3C: "jy_money", 0x3D: "fame_val", 0x44: "exp_val",
            0x37: "kill_val", 0x38: "pk_val"}


@dataclass
class Frame:
    type: int
    payload: bytes
    fmt: str = "A"
    key: int = 0
    t: float = field(default_factory=time.time)

    def __repr__(self):
        return "Frame(0x%02x, %d字节)" % (self.type, len(self.payload))


def _load_s2t():
    try:
        return json.load(open(S2T_PATH, encoding="utf8"))
    except Exception:
        return {}


_S2T = None


def to_big5(s: str) -> bytes:
    """简体字符串 -> BIG5 字节（有简繁表就先转繁体，转不了的字符用 ? 代替）。"""
    global _S2T
    if _S2T is None:
        _S2T = _load_s2t()
    s = "".join(_S2T.get(ch, ch) for ch in s)
    return s.encode("big5", errors="replace")


def from_big5(b: bytes) -> str:
    return b.split(b"\x00")[0].decode("big5", errors="replace")


def pstr(b: bytes, o: int) -> str:
    """长度字节 + 16 字节缓冲区（BIG5 或 GBK 都用 big5 读，线上是 BIG5）。"""
    n = b[o]
    return b[o + 1:o + 1 + min(n, 16)].decode("big5", errors="replace")


class JyClient:
    def __init__(self, host="127.0.0.1", port=6731, log=None, name=None, keep_queue=True):
        self.host, self.port = host, port
        self.name = name or "client"
        self.reader = self.writer = None
        self.seq = 0
        self.base = None            # C2S 密钥基数
        self.keep_queue = keep_queue    # False：不攒队列，只通过 listeners 推送（长连接网关用）
        self.frames = asyncio.Queue()   # 所有收到的 S2C 帧
        self.history = collections.deque(maxlen=2000)   # 最近收到的帧，方便断言
        self.listeners = []         # 每收到一个 S2C 帧（状态已更新后）调用 fn(frame)；连接关闭时调用 fn(None)
        self.names = {}             # jyid -> 名字（来自 0x1E / 0x60 / 0x02）
        self.shop = None            # 最近一次 0x09 商品列表
        self.bank = None                  # 钱庄清单 [{id, dur, n}]（0x28），没打开过是 None
        self.ground = []                  # 本图地上物品（别人丢的、自己丢的）：{by, id, dur, n, pos}
        self.chat_events = []             # 全部聊天：{ch: public|whisper|org|team, from: jyid|None, text, t}
        self.parties = {}                 # 队长 jyid -> [成员 jyid…]（来自全服的 0x2A / 0x2F / 0x2D / 0x2B 广播）
        self.team_invites = []            # 收到的组队邀请（邀请人 jyid）
        self.org = None                   # 自己的组织 {id, name}（创立 0x4F / 加入 0x55 之后）
        self.orgs = {}                    # 组织号 -> {name, creator, members:[jyid]}（只记自己见到的广播）
        self.org_invites = []             # 收到的组织招收 {creator, name, org}
        self.org_online = []              # 0xAD 列表：在线的其他成员名字
        self.org_query = None             # 0x39 的固定返回码
        self.trade = None                 # 进行中的交易 {with, offers:{jyid:[物品…]}, money:{jyid:金钱}, locked:[jyid], stage}
        self.trade_log = []               # 交易结束 / 取消记录
        self.kf_slots = {}                # 0x6E 回显：槽位 -> 武功 ID
        self.kf_deleted = []              # 0x7A：已删除（等级清零）的武功 ID
        self.roll_result = None           # 0x5A 摇点结果（7 项属性）
        self.name_result = None           # 0x25：0 = 名字可用 1 = 已被占用
        self.deleted = False              # 0x36：删除角色成功
        self.pw_result = None             # 0xB8 二级密码结果 (子类型, 回显字节)
        self.item_infos = {}              # 0x88：物品 ID -> 原始载荷
        self.mall_points = None           # 0x32：商城点数
        self.heartbeat = None             # 0x33：(心跳计数, 在线时间)
        self.work = None                  # 正在做的生活技能 {"job", "slot"}
        self.work_seq = 0                 # C2S 0x5A 的序号（只增不减）
        self.work_results = []            # S2C 0x64 的结果（lifeskill.parse_64）
        self.farm_active = False          # 做过農夫的包之后为真（现在只是个标记，0x64 的物品一律本地补进背包）
        self.farm_plots = {}              # 田块号 -> {"seed", "status"}（S2C 0x66）
        self.study_log = []               # S2C 0x68 / 0x70 的结果（masters.parse_68 / parse_70，掉级的带 lost=True）
        self.my_state = 0                 # 自己的实体状态（0x82：3 伐木 / 4 捕魚 / 8 交易）
        self.last_claim_padded = False   # 最近一次取鏢是否补了 0xFF（补了就没有 0x4B，要重登同步背包）
        self._session_keys = {}           # 种子 -> session_key_emu.SessionKey（取鏢的校验字节用）
        self.biaoju_list = []             # 0x49：鏢局里别人託给我的（{"from", "item_id", "dur"}）
        self.biaoju_info = {}             # 0x4D：子号 -> [LE32 …]
        self.mail_notice = None           # 0x3F 最近一条（biaoju.parse_3f）
        self.clock = None                 # 游戏时钟的校时点：(时钟值, 校时时刻 time.monotonic())；game_time() 折算当前值
        self.buffs = []                   # 0x99 05：临时增益通知
        self.nickname_result = None       # 0x15：改外号后的 V7Z<n>-外号
        self.fight = jyfight.FightState()  # 战斗状态（D5/D7/D8/DC/E4/E6/E8…），见 jyfight.py / 战斗协议_客户端侧.md
        self.fight_cell = (24, 31)         # 进战时报告的自己所在格（E3）
        self.session = pp.Session(1, self._on_event)
        self.log = open(log, "w", encoding="utf8") if log else None
        self.me = {}                # 来自 0x1E 的角色状态（parse_0x1e.parse 的结果）
        self.pos = None             # (x, y) 最后已知位置
        self.map_id = None
        self.players = {}           # 同图其它玩家：jyid -> dict
        self.chat_log = []          # (时间, 发送者jyid, 文本)
        self.notices = []           # 0x14 系统消息文本
        self.rekeys = []
        self._reader_task = None
        self.closed = False

    # ---------- 连接 ----------
    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        self._reader_task = asyncio.create_task(self._read_loop())
        self._log({"ev": "open", "peer": "%s:%d" % (self.host, self.port)})

    async def close(self):
        self.closed = True
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        if self._reader_task:
            self._reader_task.cancel()
        if self.log:
            self.log.close()

    def _log(self, ev):
        if self.log:
            ev.setdefault("t", time.time())
            ev["who"] = self.name
            self.log.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self.log.flush()

    # ---------- 收 ----------
    async def _read_loop(self):
        try:
            while True:
                data = await self.reader.read(65536)
                if not data:
                    self._log({"ev": "eof"})
                    self.closed = True
                    await self.frames.put(None)
                    self._notify(None)
                    return
                self._log({"ev": "chunk", "dir": "S2C", "hex": data.hex()})
                self.session.feed("S2C", data)
        except (asyncio.CancelledError, ConnectionError):
            pass

    def _on_event(self, ev):
        self._log(ev)
        if ev.get("ev") == "seed":
            self.base = ev["key"]
            self.rekeys.append((ev["where"], ev["seed"], ev["key"]))
        elif ev.get("ev") == "frame" and ev["dir"] == "S2C":
            f = Frame(ev["type"], bytes.fromhex(ev["payload"]), ev["fmt"], ev["key"])
            self.history.append(f)
            self._apply(f)
            if self.keep_queue:
                self.frames.put_nowait(f)
            self._notify(f)

    def _set_equip(self, slot, item, state):
        name = SLOT_NAME.get(slot)
        if name and name in self.me["equip"]:
            for e in self.me["equip"][name]:       # 武器在 0x1E 里出现两次，同步改
                e["item_id"], e["zhuangtai"] = item, state

    def _bag_remove(self, item):
        bag = self.me["bag"]
        for i, s in enumerate(bag):
            if s["item_id"] == item:
                del bag[i]
                return

    def _ground_remove(self, item, n):
        for i, g in enumerate(self.ground):
            if g["id"] == item and g["n"] == n:
                del self.ground[i]
                return

    def bag_count(self, item=None):
        """背包里某物品的数量（item=None 返回总件数）。背包按"每件一槽"展开。"""
        if not self.me:
            return 0
        return sum(1 for s in self.me["bag"] if item is None or s["item_id"] == item)

    async def biaoju_query(self):
        """C2S 0x3E：查鏢局里别人託给我的。没有 -> 1A 10「您沒有任何物品」；有 -> S2C 0x49（存进 self.biaoju_list）。"""
        self.biaoju_list = []
        return await self.send(0x3E, b"")

    async def biaoju_send(self, name: str, item_id: int, count: int = 1):
        """C2S 0x3D 託鏢：把背包里的打工物品（镖局的包裹 / 运镖车，见 biaoju.is_job_item）託给名字叫 name 的玩家。耐久取背包里这件的值。
        成功 -> 自己收 1A 0E「託鏢成功」，对方收 1A 64「…　鏢給你」；物品不对 / 不够 -> 1A 64「物品數量不足，請重登﹗」。"""
        slot = next((s for s in (self.me or {}).get("bag", []) if s["item_id"] == item_id), None)
        if slot is None:
            raise ValueError("背包里没有这件物品")
        return await self.send(0x3D, biaoju.build_send(name.encode("big5"), item_id, slot["byte5"], count))

    def checksum_provider(self, seed: bytes, k: int):
        """会话校验字节（原版 FUN_009b6798(k)）：只能借 session_key_emu 在 Windows + loginp.exe + unicorn 上算；算不了返回 None。
        只支持 k = 2 / 6（不依赖玩家数据）。结果按种子缓存。"""
        try:
            sk = self._session_keys.get(seed)
            if sk is None:
                from session_key_emu import SessionKey      # 延迟导入：Mac 包里没有 loginp.exe / unicorn
                sk = self._session_keys[seed] = SessionKey(seed)
            return sk.provider(k)
        except Exception:
            return None

    async def biaoju_claim(self, rows):
        """C2S 0x3F 取鏢：rows = 0x49 清单里要取的行号（1 起）。成功 -> S2C 0x4B 物品进背包 + 1A「您已成功領取物品」。
        需要会话校验字节（见 checksum_provider）；这台机器算不了就抛 RuntimeError。校验不对服务端会公告并降武功。"""
        if not self.rekeys:
            raise RuntimeError("还没有会话种子")
        seed = bytes.fromhex(self.rekeys[-1][1]) if isinstance(self.rekeys[-1][1], str) else bytes(self.rekeys[-1][1])
        fail = []

        def prov(k):
            v = self.checksum_provider(seed, k)
            if v is None:
                fail.append(k)
                return 0
            return v
        payload = biaoju.build_claim(rows, seed, prov)
        if fail:
            raise RuntimeError("这台机器算不出会话校验字节（需要 Windows + 原版 loginp.exe + pip install unicorn）")
        # 行号字节数正好让 k 落在 2 / 6 时服务端回 S2C 0x4B（物品进背包）；补了 0xFF 的包物品也会到服务端的背包，但没有 0x4B，要重新登录才看得到
        self.last_claim_padded = len(payload) - 1 != len(rows)
        return await self.send(0x3F, payload)

    def _seal(self, pick):
        """生活技能 / 農夫共用的序号（self.work_seq）：pick(seq_min, M) -> (序号, k)；返回 (序号, k, 校验字节)，算不了抛 RuntimeError。"""
        if not self.rekeys:
            raise RuntimeError("还没有会话种子")
        seed = bytes.fromhex(self.rekeys[-1][1]) if isinstance(self.rekeys[-1][1], str) else bytes(self.rekeys[-1][1])
        seq, k = pick(self.work_seq + 1, biaoju.modulus(seed))
        v = self.checksum_provider(seed, k)
        if v is None:
            raise RuntimeError("这台机器算不出会话校验字节（需要 Windows + 原版 loginp.exe + pip install unicorn）")
        self.work_seq = seq
        return seq, k, v

    async def _work_send(self, a: int, b: int, f: int):
        """C2S 0x5A（生活技能开始 / 一轮 / 停止）；校验字节的要求同 biaoju_claim，算不了抛 RuntimeError。"""
        seq, k, v = self._seal(lambda lo, m: lifeskill.pick_seq(lo, a, b, f, m))
        return await self.send(0x5A, lifeskill.build_z(seq, a, b, f, 0, 0, 0, lambda _k: v, k))

    def _set_kf_row(self, kf: int, lv: int, exp: int):
        """把 kf_rows 里这门武功的等级 / 经验改成 S2C 0x68 / 0x70 给的值（没有这行就加一行）。行 = 9 字节：标志 | 等级 LE16 | 经验 LE32 | 武功 ID LE16。"""
        rows, hit = [], False
        for h in self.me.get("kf_rows", []):
            b = bytearray.fromhex(h)
            if len(b) >= 9 and struct.unpack_from("<H", b, 7)[0] == kf:
                b[1:3] = struct.pack("<H", lv)
                b[3:7] = struct.pack("<I", exp & 0xFFFFFFFF)
                hit = True
            rows.append(b.hex(" "))
        if not hit:
            rows.append((b"\x00" + struct.pack("<HIH", lv, exp & 0xFFFFFFFF, kf)).hex(" "))
        self.me["kf_rows"] = rows

    async def read_book(self, item_id: int):
        """读秘笈学特殊武功（C2S 0x60，见 books.py）。背包里必须有这本书——没有的话原版回『物品不足』并把你踢下线。"""
        slot = next((s for s in (self.me or {}).get("bag", []) if s["item_id"] == item_id), None)
        if slot is None:
            raise ValueError("背包里没有这件物品")
        return await self.send(0x60, books.build_read(item_id, slot["byte5"]))

    async def study(self, master: int, kf: int, points: int):
        """消点：把 points 点学习点花在 kf 上（C2S 0x5E，师傅 master 要在这张图上，见 masters.py）。成功回 S2C 0x68，答错师傅 / 地图 / 门派会被掉一级武功。"""
        seq, k, v = self._seal(lambda lo, m: masters.pick_seq_study(lo, master, kf, m))
        return await self.send(0x5E, masters.build_study(master, kf, points, seq, lambda _k: v, k))

    async def farm_plant(self, plot: int, seed_item: int):
        """農夫播種 C2S 0x5B（无校验）：背包里要有这种种子，服务端扣 1 个，回 S2C 0x66 状态 1（self.farm_plots[plot]）。"""
        if not any(s["item_id"] == seed_item for s in (self.me or {}).get("bag", [])):
            raise ValueError("背包里没有这种种子")
        self.farm_active = True
        return await self.send(0x5B, lifeskill.build_plant(plot, seed_item))

    async def farm_till(self, plot: int):
        """耕種 C2S 0x5C 动作 1（带会话校验）：服务端回 S2C 0x66 状态 3 + 0x82 状态 6。"""
        self.farm_active = True
        seq, k, v = self._seal(lambda lo, m: lifeskill.pick_seq_farm(lo, plot, 1, m))
        return await self.send(0x5C, lifeskill.build_farm(seq, plot, 1, 0, 0, 0, lambda _k: v, k))

    async def farm_harvest(self, plot: int):
        """收成 C2S 0x5C 动作 2：S2C 0x64 结果（作物，成功时 farm_active 下本地补进背包）+ 0x76 BE 技能计数；偶尔另有 0x77 的额外物品。"""
        self.farm_active = True
        seq, k, v = self._seal(lambda lo, m: lifeskill.pick_seq_farm(lo, plot, 2, m))
        return await self.send(0x5C, lifeskill.build_farm(seq, plot, 2, 0, 0, 0, lambda _k: v, k))

    async def work_start(self, job: int, tool_item: int):
        """开始生活技能（1 伐木 / 2 捕魚 / 3 採礦）。tool_item = 背包里的工具物品 id；之后每 lifeskill.TICK_SECS 秒调一次 work_tick。"""
        if job not in lifeskill.JOB_NAMES:
            raise ValueError("工作类型 1..3")
        idx = next((i for i, s in enumerate((self.me or {}).get("bag", [])) if s["item_id"] == tool_item), None)
        if idx is None:
            raise ValueError("背包里没有这件工具")
        self.farm_active = False
        self.work = {"job": job, "slot": min(idx, 255)}
        return await self._work_send(1, job, self.work["slot"])

    async def work_tick(self):
        """生活技能做一轮（客户端每 8 秒一次）。"""
        if not self.work:
            raise ValueError("没有在工作")
        return await self._work_send(2, self.work["job"], self.work["slot"])

    async def work_stop(self):
        job = (self.work or {}).get("job", 0)
        self.work = None
        # 真客户端停止时 B = 0（原版接受）；复刻服务端 2026-10-21 版要求 B 是 1–3，所以带上当前工作类型，两边都认
        return await self._work_send(3, job, 0)

    async def biaoju_jobs(self, sub: int = 0):
        """C2S 0x40 <子号>：鏢局工作列表 / 价格，回 S2C 0x4D（self.biaoju_info[子号]）。"""
        return await self.send(0x40, bytes([sub]))

    def game_time(self):
        """当前游戏时钟（没收到过校时返回 None）：校时值 + 距校时每满 75 秒一格（最多 3 格，同原版 0x6bdad8）。"""
        if not self.clock:
            return None
        base, t0 = self.clock
        return base + min(3, max(0, int((time.monotonic() - t0) / HEARTBEAT_SECS)))

    def stop_queue(self):
        """登录流程（login/start 靠队列等帧）结束后调用：不再攒队列，之后只靠 listeners 推送。"""
        self.keep_queue = False
        while not self.frames.empty():
            self.frames.get_nowait()

    def _notify(self, f):
        for fn in list(self.listeners):
            try:
                fn(f)
            except Exception as e:
                self._log({"ev": "listener_error", "err": repr(e)})

    def _apply_social(self, f: Frame):
        """聊天 / 组队 / 组织 / 交易 / 武功 / 账号类的 S2C（网金复刻 docs 里全部验证过的类型）。"""
        p, t = f.payload, f.type
        me = self.me["fields"]["jyid"] if self.me else None
        if t == 0x04 and len(p) >= 5 and p[0] in (1, 3, 5):         # 01 公共 / 03 私聊 / 05 组织：子类型 + 发送者 jyid + 文本
            ch = {1: "public", 3: "whisper", 5: "org"}[p[0]]
            self.chat_events.append({"ch": ch, "from": struct.unpack_from("<I", p, 1)[0], "text": from_big5(p[5:]), "t": f.t})
        elif t == 0x1C:                                              # 队伍聊天：载荷原样，没有发送者
            self.chat_events.append({"ch": "team", "from": None, "text": from_big5(p), "t": f.t})
        elif t == 0x2A and len(p) >= 4:                              # 有人创建队伍：队长 jyid + 01 00 + 请求载荷
            leader = struct.unpack_from("<I", p, 0)[0]
            self.parties[leader] = [leader]
        elif t == 0x2B and len(p) >= 4:                              # 队伍解散：发起人 jyid（队里任何人都能解散）
            who = struct.unpack_from("<I", p, 0)[0]
            for ld in [k for k, v in self.parties.items() if who in v]:
                del self.parties[ld]
        elif t == 0x2D and len(p) >= 4:                              # 有人离队
            who = struct.unpack_from("<I", p, 0)[0]
            for v in self.parties.values():
                if who in v[1:]:
                    v.remove(who)
        elif t == 0x2E and len(p) >= 4:                              # 收到组队邀请：邀请人 jyid
            self.team_invites.append(struct.unpack_from("<I", p, 0)[0])
        elif t == 0x2F and len(p) >= 9:                              # 有人入队：01 + 加入者 jyid + 邀请人 jyid
            who, inv = struct.unpack_from("<II", p, 1)
            ld = next((k for k, v in self.parties.items() if inv in v), None)
            if ld is None:
                ld = inv
                self.parties.setdefault(ld, [ld])
            if who not in self.parties[ld]:
                self.parties[ld].append(who)
            if who == me:
                self.team_invites = [i for i in self.team_invites if i != inv]
        elif t == 0x4F and len(p) >= 6:                              # 创立组织结果：创立者 jyid + 组织号(LE16) + 名字
            jy, oid = struct.unpack_from("<IH", p, 0)
            name = from_big5(p[6:])
            self.orgs[oid] = {"name": name, "creator": jy, "members": [jy]}
            if jy == me:
                self.org = {"id": oid, "name": name}
        elif t == 0x54 and len(p) >= 6:                              # 组织招收邀请：创立者 jyid + 名字长度 + 名字 + 1802 字节模板（组织号 LE16 在模板偏移 28）
            jy, ln = struct.unpack_from("<IB", p, 0)
            name = p[5:5 + ln].decode("big5", errors="replace")
            tpl = p[5 + ln:]
            oid = struct.unpack_from("<H", tpl, 28)[0] if len(tpl) >= 30 else None
            self.org_invites.append({"creator": jy, "name": name, "org": oid})
        elif t == 0x55 and len(p) >= 7:                              # 有人加入组织：jyid + 01 + 组织号
            jy, oid = struct.unpack_from("<I", p, 0)[0], struct.unpack_from("<H", p, 5)[0]
            o = self.orgs.setdefault(oid, {"name": None, "creator": None, "members": []})
            o["members"].append(jy)
            if jy == me:
                inv = next((i for i in self.org_invites if i["org"] == oid), None)
                self.org = {"id": oid, "name": o["name"] or (inv and inv["name"])}
                self.org_invites = [i for i in self.org_invites if i["org"] != oid]
        elif t == 0x56 and len(p) >= 8:                              # 有人被踢：踢人者 jyid + 被踢者 jyid
            victim = struct.unpack_from("<I", p, 4)[0]
            for o in self.orgs.values():
                if victim in o["members"]:
                    o["members"].remove(victim)
            if victim == me:
                self.org = None
        elif t == 0x57 and len(p) >= 4:                              # 有人退出组织
            who = struct.unpack_from("<I", p, 0)[0]
            for o in self.orgs.values():
                if who in o["members"]:
                    o["members"].remove(who)
            if who == me:
                self.org = None
        elif t == 0xAD and len(p) >= 1:                              # 在线成员列表：10 + N×[05 名字长度 名字]
            names, o = [], 1
            while o + 2 <= len(p):
                ln = p[o + 1]
                names.append(p[o + 2:o + 2 + ln].decode("big5", errors="replace"))
                o += 2 + ln
            self.org_online = names
        elif t == 0x39 and len(p) >= 1:
            self.org_query = p[0]
        elif t == 0x1F and len(p) >= 8:                              # 交易会话建立：发起人 jyid + 对方 jyid
            a, b = struct.unpack_from("<II", p, 0)
            other = b if a == me else a
            if not self.trade or self.trade["with"] != other:
                self.trade = {"with": other, "offers": {a: [], b: []}, "money": {a: 0, b: 0}, "locked": [], "stage": "open"}
        elif t == 0x20 and len(p) >= 11 and self.trade:              # 放入物品：jyid + 01 + 物品 ID + 耐久 + 01
            jy, item, dur = struct.unpack_from("<I", p, 0)[0], struct.unpack_from("<I", p, 5)[0], p[9]
            self.trade["offers"].setdefault(jy, []).append({"id": item, "dur": dur})
        elif t == 0x21 and len(p) >= 8 and self.trade:              # 金钱通知（原版"压帧"怪行为：先压住，被下一帧顶出来）
            jy, m = struct.unpack_from("<II", p, 0)
            self.trade["money"][jy] = m
        elif t == 0x23 and len(p) >= 1 and self.trade:               # 状态：01 jyid = 对方锁定 | 04 = 确认阶段 | 00 jyid = 取消
            if p[0] == 1 and len(p) >= 5:
                self.trade["locked"].append(struct.unpack_from("<I", p, 1)[0])
            elif p[0] == 4:
                self.trade["stage"] = "confirm"
            elif p[0] == 0:
                self.trade_log.append({"end": "cancel", "by": struct.unpack_from("<I", p, 1)[0] if len(p) >= 5 else None, "with": self.trade["with"], "t": f.t})
                self.trade = None
        elif t == 0x22 and self.trade:                               # 成交结束（可能成功也可能整笔作废，没有明确信号）
            self.trade_log.append({"end": "done", "trade": self.trade, "t": f.t})
            self.trade = None
        elif t == 0x82 and len(p) >= 6:                              # 实体状态标记：08 00 = 正在交易，00 00 = 正常，03 / 04 = 伐木 / 捕魚
            jy = struct.unpack_from("<I", p, 0)[0]
            if jy in self.players:
                self.players[jy]["state"] = struct.unpack_from("<H", p, 4)[0]
            if self.me and jy == self.me["fields"]["jyid"]:
                self.my_state = struct.unpack_from("<H", p, 4)[0]
        elif t == 0x64 and len(p) >= 6:                              # 生活技能每轮的结果
            r = lifeskill.parse_64(p)
            if r:
                self.work_results.append(r)
                if r["ok"] and r["item_id"] and self.me is not None:
                    # 采集 / 收成的物品只在 0x64 里（不跟 0x0B / 0x77；48015 那对是钱庄的固定帧）：先进背包。
                    # 背包里已经有这件物品时服务端把它自动存进钱庄（VIP），随后的 0x27 存入会再扣掉这一件，净效果和服务端一致。
                    self.me["bag"].append({"slot": None, "item_id": r["item_id"], "byte5": 200})
        elif t == 0x66 and len(p) >= 8:                              # 農夫田块：jyid(4) 田块号(1) 种子 id LE16 状态(1)（1 = 种下 / 3 = 耕種中，收成后种子清零）
            if self.me and struct.unpack_from("<I", p, 0)[0] == self.me["fields"]["jyid"]:
                seed = struct.unpack_from("<H", p, 5)[0]
                self.farm_plots[p[4]] = {"seed": seed, "status": p[7]}
                if p[7] == 1 and seed and self.me:       # 播种成功：背包少一个种子
                    for i, s in enumerate(self.me["bag"]):
                        if s["item_id"] == seed:
                            del self.me["bag"][i]
                            break
        elif t in (0x68, 0x70) and len(p) >= 12:                     # 学武功 / 消点（0x68）与武功掉一级（0x70）：武功行 + 学习点 + 精
            r = masters.parse_68(p) if t == 0x68 else masters.parse_70(p)
            if r and self.me:
                self._set_kf_row(r["kf"], r["lv"], r["exp"])
                self.me["fields"]["study_count"] = r["study"]
                self.me["fields"]["dangqianjing"] = r["jing"]
                self.study_log.append(dict(r, lost=t == 0x70))
        elif t == 0x6E and len(p) >= 3:                              # 装备武功回显：槽位 + 武功 ID(LE16)
            self.kf_slots[p[0]] = struct.unpack_from("<H", p, 1)[0]
        elif t == 0x7A and len(p) >= 3:                              # 删除武功：02 + 武功 ID(LE16)；原版只把等级经验写 0（行还在，下线才消失）
            kid = struct.unpack_from("<H", p, 1)[0]
            self.kf_deleted.append(kid)
            if self.me:
                rows = []
                for h in self.me.get("kf_rows", []):
                    b = bytearray.fromhex(h)
                    if len(b) >= 9 and struct.unpack_from("<H", b, 7)[0] == kid:
                        b[1] = 0
                        b[3:6] = b"\x00" * 3
                    rows.append(b.hex(" "))
                self.me["kf_rows"] = rows
        elif t == 0x5A and len(p) >= 8:                              # 摇点：03 + 7 项属性
            self.roll_result = list(p[1:8])
        elif t == 0x25 and len(p) >= 1:
            self.name_result = p[0]
        elif t == 0x36 and len(p) >= 1:
            self.deleted = p[0] == 1
        elif t == 0xB8 and len(p) >= 1:
            self.pw_result = (p[0], p[1:])
            if p[0] == 0x10 and self.me:             # 0xB8 10 = 自宫成功（客户端 0x66db00 提示「自宮成功」）
                self.me["fields"]["zigong"] = 1
        elif t == 0x88 and len(p) >= 4:
            self.item_infos[struct.unpack_from("<I", p, 0)[0]] = p[4:]
        elif t == 0x32 and len(p) >= 5 and p[0] == 0x6F:
            self.mall_points = struct.unpack_from("<I", p, 1)[0]
        elif t == 0x33 and len(p) >= 8:
            self.heartbeat = struct.unpack_from("<II", p, 0)
            self.clock = (self.heartbeat[0], time.monotonic())            # 原版 0x626b2c：心跳计数 = 游戏时钟（0x6bdc48）
        elif t == 0x49:                                                       # 鏢局存放清单（回 C2S 0x3E）
            self.biaoju_list = biaoju.parse_49(p, from_big5)
        elif t == 0x4B and self.me:                                           # 取鏢成功：物品进背包（原版客户端 0x63687c → 0x787390）
            for it in biaoju.parse_4b(p):
                self.me["bag"].append({"slot": None, "item_id": it["item_id"], "byte5": it["dur"]})
            self.biaoju_list = []
        elif t == 0x4D and p:                                                 # 鏢局工作列表 / 价格（回 C2S 0x40）
            sub, vals = biaoju.parse_4d(p)
            self.biaoju_info[sub] = vals
        elif t == 0x3F:                                                       # 邮件 / 鏢局到达提示
            self.mail_notice = biaoju.parse_3f(p)
        elif t == 0x99 and len(p) >= 1 and p[0] == 0x05:
            self.buffs.append(p[1:])
        elif t == 0x15 and len(p) >= 4 and self.me and struct.unpack_from("<I", p, 0)[0] == me:      # 改外号结果：jyid + V7Z<n>- + 外号
            self.nickname_result = from_big5(p[4:])
            self.me["second_string"] = self.nickname_result

    def _apply(self, f: Frame):
        """把帧折进本地状态。只处理已确认含义的类型。"""
        p = f.payload
        try:
            self._apply_social(f)
            self.fight.apply(f.type, p, self.me["fields"]["jyid"] if self.me else None, self.me["fields"] if self.me else None)
            if f.type == 0x1E:
                self.me = parse_0x1e.parse(p)
                tk = self.me["header_counter"]                              # 原版 0x6263e4：0x1E 开头的 LE32 也是游戏时钟，先取整到 4 的倍数、余数按每格 75 秒折成已过时间
                self.clock = (tk - (tk & 3), time.monotonic() - (tk & 3) * HEARTBEAT_SECS)
                fl = self.me["fields"]
                self.pos, self.map_id = (fl["x"], fl["y"]), fl["map"]
                self.names[fl["jyid"]] = self.me["name"]
            elif f.type == 0x60 and len(p) >= 21:      # 别人上线：jyid + 名字(17) + 称号(17)
                self.names[struct.unpack_from("<I", p, 0)[0]] = pstr(p, 4)
            elif f.type == 0x04 and len(p) >= 6 and p[0] == 0x01:
                sender = struct.unpack_from("<I", p, 1)[0]
                self.chat_log.append((f.t, sender, from_big5(p[5:])))
            elif f.type == 0x14 and len(p) >= 2:
                self.notices.append((p[0], from_big5(p[1:])))
            elif f.type == 0x06 and len(p) >= 12:
                jy, x1, y1, x2, y2 = struct.unpack_from("<IHHHH", p, 0)
                if self.me and jy == self.me["fields"]["jyid"]:
                    self.pos = (x2, y2)
                elif jy in self.players:
                    self.players[jy]["pos"] = (x2, y2)
            elif f.type == 0x02 and len(p) >= 59:
                jy, mp, x, y = struct.unpack_from("<IHHH", p, 0)
                # 外观包：jyid 地图 x y 01 名字(17) 称号(17) 6×00 01 01 头盔 衣服 武器(LE16×3) 善恶-2000(LE16)（docs/聊天移动与上下线广播.md）
                self.players[jy] = {"jyid": jy, "map": mp, "pos": (x, y), "name": pstr(p, 11),
                                    "look": dict(zip(("toukui", "yifu", "wuqi"), struct.unpack_from("<HHH", p, 53)))}
                self.names[jy] = self.players[jy]["name"]
            elif f.type == 0x05 and len(p) >= 4:
                self.players.pop(struct.unpack_from("<I", p, 0)[0], None)
            elif f.type == 0x61 and len(p) >= 10:      # 有人进入本图视野：jyid + 地图/x/y + 01 + 头盔 衣服 武器(LE16×3) + 善恶
                jy, mp, x, y = struct.unpack_from("<IHHH", p, 0)
                self.players.setdefault(jy, {"jyid": jy})
                self.players[jy].update(map=mp, pos=(x, y))
                if len(p) >= 17:
                    self.players[jy]["look"] = dict(zip(("toukui", "yifu", "wuqi"), struct.unpack_from("<HHH", p, 11)))
            elif f.type == 0x62 and len(p) >= 4:       # 有人离开本图视野
                self.players.pop(struct.unpack_from("<I", p, 0)[0], None)
            elif f.type == 0x08 and len(p) >= 6:       # 自己被传送/登录：地图 x y
                mp, x, y = struct.unpack_from("<HHH", p, 0)
                if self.map_id is not None and mp != self.map_id:
                    self.ground.clear()
                    self.players.clear()       # 换图：旧图的人不在视野里了，新图上的人随后由 0x02 + 0x82 补发
                self.map_id, self.pos = mp, (x, y)
            elif f.type == 0x7B and len(p) >= 6 and self.me:      # 属性更新：子类型 + 01 + 新值 LE32
                col = STAT_COL.get(p[0])
                if col:
                    self.me["fields"][col] = struct.unpack_from("<I", p, 2)[0]
            elif f.type == 0x17 and len(p) >= 10 and self.me:     # 穿上：jyid 槽位 物品ID 状态
                slot, item, state = p[4], struct.unpack_from("<I", p, 5)[0], p[9]
                self._set_equip(slot, item, state)
            elif f.type == 0x18 and len(p) >= 5 and self.me:      # 脱下：jyid 槽位
                self._set_equip(p[4], 0, 0)
            elif f.type == 0x28 and len(p) >= 4:                   # 钱庄清单：wupin=0 行数(LE32) + [物品ID LE32, 耐久, 数量 LE16]*
                self.bank = [{"id": struct.unpack_from("<I", p, o)[0], "dur": p[o + 4], "n": struct.unpack_from("<H", p, o + 5)[0]} for o in range(4, len(p) - 6, 7)]
            elif f.type == 0x27 and len(p) >= 7 and self.me:      # 钱庄存 / 取结果：子类型(0 存 1 取) 物品ID 数量(LE16) …
                sub, item, n = p[0], struct.unpack_from("<I", p, 1)[0], struct.unpack_from("<H", p, 5)[0]
                if sub == 0:
                    for _ in range(n):
                        self._bag_remove(item)
                    if self.bank is not None:
                        e = next((b for b in self.bank if b["id"] == item), None)
                        if e:
                            e["n"] += n
                        else:
                            self.bank.insert(0, {"id": item, "dur": p[-1], "n": n})      # 最新存入的排最前
                else:
                    for _ in range(n):
                        self.me["bag"].append({"slot": None, "item_id": item, "byte5": 200})
                    if self.bank is not None:        # 随后服务端会再发一次 0x28 校正，这里先扣掉
                        e = next((b for b in self.bank if b["id"] == item), None)
                        if e:
                            e["n"] -= n
                            if e["n"] <= 0:
                                self.bank.remove(e)
            elif f.type == 0x0D and len(p) >= 13:                  # 同图别人丢东西：jyid 物品ID 耐久 数量(LE32)；丢的人站在哪就落在哪
                by, item, dur, n = struct.unpack_from("<IIBI", p, 0)
                self.ground.append({"by": by, "id": item, "dur": dur, "n": n, "pos": (self.players.get(by) or {}).get("pos")})
            elif f.type == 0x10 and len(p) >= 9 and self.me:      # 自己捡起来了：物品ID 耐久 数量（背包只加 1 件）
                item, dur, n = struct.unpack_from("<IBI", p, 0)
                self.me["bag"].append({"slot": None, "item_id": item, "byte5": dur})
                self._ground_remove(item, n)
            elif f.type == 0x11 and len(p) >= 13:                  # 别人捡走了：jyid + 同样 9 字节
                item, n = struct.unpack_from("<I", p, 4)[0], struct.unpack_from("<I", p, 9)[0]
                self._ground_remove(item, n)
            elif f.type == 0x77 and len(p) >= 6 and self.me:      # 得到物品 / 标记（事件结果）：ID(LE32) + (0x100+类型)(LE16)，每件一帧
                if struct.unpack_from("<I", p, 0)[0] != 48015:        # 48015（随身钱庄）：存取时服务端固定回的 0x0B + 0x77，成对抵消，不入账
                    self.me["bag"].append({"slot": None, "item_id": struct.unpack_from("<I", p, 0)[0], "byte5": p[4] if len(p) > 4 else 200})
            elif f.type == 0x6B and len(p) >= 4 and self.me:      # 失去物品 / 标记（事件结果）：同上，每件一帧
                self._bag_remove(struct.unpack_from("<I", p, 0)[0])
            elif f.type == 0x0B and len(p) >= 6 and self.me:      # 用药成功：物品ID + 耐久 + 01，背包少一件
                if struct.unpack_from("<I", p, 0)[0] != 48015:
                    self._bag_remove(struct.unpack_from("<I", p, 0)[0])
            elif f.type == 0x09 and len(p) >= 1:                  # 商店列表：00 + [物品ID, 商人表里的数]*
                items = [struct.unpack_from("<II", p, o) for o in range(1, len(p) - 7, 8)]
                self.shop = {"items": [{"id": i, "n": n} for i, n in items]}
            elif f.type == 0x0A and self.me:                      # 购买成功：[01, 物品ID, 余额]*，原版每条只入背包 1 件
                for o in range(0, len(p) - 8, 9):
                    self.me["bag"].append({"slot": None, "item_id": struct.unpack_from("<I", p, o + 1)[0], "byte5": 200})
            elif f.type == 0x1A and len(p) >= 1:                  # 提示文字：子类型 64 = 后面跟文字，3..0x51 = 客户端里写死的文字（notices.py）
                txt = notices.decode_1a(p, from_big5)
                if txt:
                    self.notices.append((0x1A, txt))
        except Exception as e:  # 解析出错不能拖垮读循环
            self._log({"ev": "apply_error", "type": f.type, "err": repr(e)})

    async def wait(self, pred, timeout=5.0):
        """等到满足条件的帧（从当前队列里往后取，不满足的丢掉）；超时返回 None。"""
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                return None
            try:
                f = await asyncio.wait_for(self.frames.get(), left)
            except asyncio.TimeoutError:
                return None
            if f is None:
                return None
            if pred(f):
                return f

    async def drain(self, quiet=0.6, limit=10.0):
        """收集帧，直到连续 quiet 秒没有新帧。返回这段时间收到的帧。"""
        got, end = [], time.time() + limit
        while time.time() < end:
            try:
                f = await asyncio.wait_for(self.frames.get(), quiet)
            except asyncio.TimeoutError:
                break
            if f is None:
                break
            got.append(f)
        return got

    # ---------- 发 ----------
    def _key(self):
        if self.seq == 1:
            return 0x9E
        if self.base is None:
            raise RuntimeError("还没有收到握手种子，无法算 C2S 密钥")
        return (self.base ^ self.seq) & 0xFF

    async def send(self, mtype: int, payload: bytes = b"", *, key=None):
        self.seq = (self.seq + 1) & 0xFF
        k = self._key() if key is None else key
        wire = b"\xf6\x11" + bytes([self.seq]) + pp.encode_frame(mtype, payload, k)
        self.writer.write(wire)
        await self.writer.drain()
        self._log({"ev": "send", "type": mtype, "seq": self.seq, "key": k, "payload": payload.hex(), "wire": wire.hex()})
        return wire

    # ---------- 动作 ----------
    async def login(self, jyid: int, timeout=5.0, password=None):
        """0x01 登录：jyid(LE32) + 常量(LE32) + 明文密码（ASCII，登录包里就是明文；缺省 = jyid 的十进制，测试号的密码都是这样）。
        成功返回握手帧；账号不存在 / 密码不对 / 被封时服务端回一个 6 字节的空握手并断开，返回 None。"""
        self.jyid = jyid
        pw = str(jyid) if password is None else str(password)
        await self.send(0x01, struct.pack("<II", jyid, LOGIN_CONST) + pw.encode("ascii", "ignore"))
        f = await self.wait(lambda f: f.type == 0x01, timeout)
        if f is not None and len(f.payload) < 8:        # 被拒（密码不对 / 账号不存在 / 被封）：服务端回一个 2 字节载荷的空握手，随后断开
            return None
        return f

    async def start(self, timeout=8.0):
        """0x19 启动登录：服务端回整个登录序列，以 0xA9 结尾。返回收到的全部帧。"""
        await self.send(0x19, b"\x00")
        got = []
        end = time.time() + timeout
        while time.time() < end:
            f = await self.wait(lambda f: True, end - time.time())
            if f is None:
                break
            got.append(f)
            if f.type == 0xA9:
                break
        return got

    async def move(self, x1, y1, x2, y2, tail=b"\x00\x00\x00"):
        """0x06 移动：起点 xy + 终点 xy（LE16×4）+ 3 字节未解（原版不校验）。"""
        return await self.send(0x06, struct.pack("<HHHH", x1, y1, x2, y2) + tail)

    async def teleport(self, map_id, x, y):
        """0x5D 传送：地图 x y（LE16×3）。原版不校验地图/坐标/道具。"""
        return await self.send(0x5D, struct.pack("<HHH", map_id, x, y))

    async def equip(self, slot: int, item_id: int, state: int = 200):
        """0x15 穿装备：槽位(1) 物品ID(LE32) 状态(1)。背包里没有 -> 全服广播"嘗試刷裝備"；槽位有装备 -> 静默忽略。
        成功回 0x17 + 武器/防具强度的 0x7B；穿脱都不改背包。"""
        return await self.send(0x15, struct.pack("<BIB", slot, item_id, state))

    async def unequip(self, slot: int):
        """0x16 脱装备：槽位(1)。有效槽位一律回 0x18（槽位本来为空也回）。"""
        return await self.send(0x16, struct.pack("<B", slot))

    async def event(self, ev: int, map_id=None, x=0):
        """0x6B 事件：[4 字节 X][地图 LE16][事件 id LE16]（docs/事件引擎.md；X 原版不看，type≥3 的事件会原样回显）。
        事件 id = 事件脚本节点的 0 起序号（pic\\EvtMrg*.Mrg，见 evtdata.py）。地图必须是当前所在地图，否则服务端按"刷事件"处理。"""
        mp = self.map_id if map_id is None else map_id
        return await self.send(0x6B, struct.pack("<IHH", x, mp, ev))

    async def bank_open(self):
        """0x23 打开随身钱庄（无载荷）-> 0x28 清单（最新存入的排最前）。"""
        return await self.send(0x23)

    async def bank_put(self, item_id: int, n: int, dur: int = 200):
        """0x22 子类型 00 存：物品ID(LE32) 耐久(1，被忽略) 数量(LE16)。背包不够 -> 0x1A「物品數量不足」。钱庄只管物品（ID 0 当不够）。"""
        return await self.send(0x22, struct.pack("<BIBH", 0, item_id, dur, n))

    async def bank_get(self, item_id: int, n: int, dur: int = 200):
        """0x22 子类型 01 取：同上。钱庄里不够 -> 0x1A「數量不足」。成功后服务端再发一次 0x28 清单。"""
        return await self.send(0x22, struct.pack("<BIBH", 1, item_id, dur, n))

    async def discard(self, item_id: int, n: int = 1, dur: int = 200):
        """0x0D 丢弃：物品ID(LE32) 耐久(1) 数量(LE32)（至少 9 字节）。原版只扣 1 件不管数量；「交易」列=0 的物品回「此物品不能丟棄」。
        丢的人自己收不到确认，本地状态自己扣 1 件并记一条地上物品（调用方要先确认背包里有、且能丢）。"""
        await self.send(0x0D, struct.pack("<IBI", item_id, dur, n))
        if self.me and any(s["item_id"] == item_id for s in self.me["bag"]):
            self._bag_remove(item_id)
            self.ground.append({"by": self.me["fields"]["jyid"], "id": item_id, "dur": dur, "n": n, "pos": self.pos})

    async def pickup(self, item_id: int, n: int, dur: int = 200):
        """0x0F 拾取：物品ID 耐久 数量（和丢弃 / 同图广播 0x0D 的 9 字节一样）。同图地上物品里按"物品ID + 数量"匹配；成功回 0x10，背包只加 1 件。"""
        return await self.send(0x0F, struct.pack("<IBI", item_id, dur, n))

    async def command(self, text: str):
        """0xC7 文字指令：`04` + `@xxx`（ASCII，docs/文字指令.md：@where @cpw @scb N @wp ID(GM) …）。"""
        return await self.send(0xC7, b"\x04" + text.encode("ascii", "ignore"))

    # ---------- 聊天 ----------
    async def whisper(self, target_jyid: int, text: str):
        """0x03 私聊：目标 jyid(LE32) + 文本。目标在线收 0x04 子类型 03；不在线无回包；不扣饮食饮水。"""
        return await self.send(0x03, struct.pack("<I", target_jyid) + to_big5(text))

    async def org_chat(self, text: str):
        """0x02 子类型 05 组织聊天：发给自己组织里在线的其他成员（不回显、不扣饮食饮水）；没有组织静默。"""
        return await self.send(0x02, b"\x05" + to_big5(text))

    # ---------- 组队（docs/组队.md） ----------
    async def party_create(self, payload: bytes = b"\x00"):
        """0x26 创建队伍（3511 / 1820 / 13000 图不能）。全服收 0x2A = 队长 jyid + 01 00 + 载荷。"""
        return await self.send(0x26, payload)

    async def party_invite(self, target_jyid: int):
        """0x2C 邀请：对方在线就收 0x2E = 邀请人 jyid。"""
        return await self.send(0x2C, struct.pack("<I", target_jyid))

    async def party_answer(self, inviter_jyid: int, accept: bool = True):
        """0x2D 应答：01 + 邀请人 jyid = 接受（要同图，邀请人要有队伍），其它 = 拒绝（自己收 0x1A「對方拒絕加入隊伍」）。"""
        return await self.send(0x2D, bytes([1 if accept else 0]) + struct.pack("<I", inviter_jyid))

    async def party_chat(self, text: str):
        """0x2E 队伍聊天：4 字节（服务端吃掉）+ 内容；队伍号相同的人收 0x1C（没有发送者）。"""
        return await self.send(0x2E, b"\x00\x00\x00\x00" + to_big5(text))

    async def party_disband(self):
        """0x27 解散（队里任何人都能解散）：全服收 0x2B。"""
        return await self.send(0x27)

    async def party_leave(self):
        """0x29 离队（队长离不开）：全服收 0x2D，原队伍的人收 0x1A「玩家:…脫離隊伍」。"""
        return await self.send(0x29)

    def my_party(self):
        """自己所在队伍的成员 jyid 列表（队长在前）；没有队伍返回 []。只根据全服广播推，登录前就存在的队伍看不到。"""
        me = self.me["fields"]["jyid"] if self.me else None
        return next((list(v) for v in self.parties.values() if me in v), [])

    # ---------- 组织（docs/组织.md） ----------
    async def org_create(self, name: str):
        """0x45 创立组织（名字 BIG5 原样）：自己收 0x4F，全服收 0x14 公告；已有组织 -> 0x1A「已有組織﹗」。"""
        return await self.send(0x45, to_big5(name))

    async def org_recruit(self, target_jyid: int):
        """0x4E 招收（只有创立者）：对方收 0x54（要再发 0x4F 01 才算加入）。"""
        return await self.send(0x4E, struct.pack("<I", target_jyid))

    async def org_join(self, recruiter_jyid: int):
        """0x4F 01 加入：招收人 jyid；全服收 0x55。原版不检查招收人是不是创立者。"""
        return await self.send(0x4F, b"\x01" + struct.pack("<I", recruiter_jyid))

    async def org_list(self):
        """0x4F 07 成员列表 -> 0xAD（只列在线的、不是自己的）。"""
        return await self.send(0x4F, b"\x07")

    async def org_kick(self, name: str):
        """0x50 踢人：4 字节（不看）+ 对方名字（BIG5，要和在线玩家完全一致）。原版不检查是不是创立者。全服收 0x56。"""
        return await self.send(0x50, b"\x00\x00\x00\x00" + to_big5(name))

    async def org_quit(self):
        """0x51 退出：全服收 0x57。"""
        return await self.send(0x51, b"\x01")

    async def org_query_status(self, sub: int = 6):
        """0x56 查询（子类型 06 / 04 / 05）-> 0x39 固定返回码（05 / 03 / 04）。"""
        return await self.send(0x56, bytes([sub]))

    # ---------- 交易（docs/丢弃回收交易.md） ----------
    async def trade_request(self, target_jyid: int):
        """0x1C 请求交易：一发就建会话，双方收 0x1F。"""
        return await self.send(0x1C, struct.pack("<I", target_jyid))

    async def trade_put_item(self, item_id: int, dur: int = 200):
        """0x1E 放物品（每次 1 件，原版不检查背包里有没有；「交易」列=0 的物品只有自己收 0x1A）。双方收 0x20。"""
        return await self.send(0x1E, b"\x01" + struct.pack("<IB", item_id, dur))

    async def trade_put_money(self, money: int):
        """0x1F 放金钱（LE32）。通知帧 0x21 有原版的"压帧"怪行为：第一次对方什么也收不到。"""
        if self.trade and self.me:
            self.trade["money"][self.me["fields"]["jyid"]] = money
        return await self.send(0x1F, struct.pack("<I", money))

    async def trade_lock(self):
        """0x1D 01 锁定：对方收 0x23 01；会话里累计第 2 次锁定双方收 0x23 04（进入确认阶段）。"""
        return await self.send(0x1D, b"\x01")

    async def trade_confirm(self):
        """0x1D 03 确认：累计第 2 次确认成交（双方收 0x22，对方收 0x82）。"""
        return await self.send(0x1D, b"\x03")

    async def trade_cancel(self):
        """0x1D 00 取消：双方收 0x23 00 + 发起人 jyid，会话结束。"""
        return await self.send(0x1D, b"\x00")

    # ---------- 武功 / 外号 / 密码 / 杂项 ----------
    async def kf_equip(self, slot: int, kf_id: int):
        """0x61 装备武功：槽位(1) + 武功 ID(LE16)。有 -> 0x6E 回显（槽位 0–14）；没有这门武功 -> 全服「嘗試刷武功﹗」公告。"""
        return await self.send(0x61, struct.pack("<BH", slot, kf_id))

    async def kf_delete(self, password: str, kf_ids):
        """0x6A 删除武功：1 字节 + 密码长度 + 账号密码 + 1 字节 + K×武功 ID(LE16)。每个删掉的回 0x7A；3860（转生武功）不能删；密码错回「密碼錯誤」。"""
        pw = password.encode("ascii", "ignore")
        return await self.send(0x6A, b"\x00" + bytes([len(pw)]) + pw + b"\x00" + b"".join(struct.pack("<H", i) for i in kf_ids))

    async def set_nickname(self, text: str):
        """0x13 改外号（BIG5，空 = 清空）：自己收 0x15，全服收 0x14 公告。"""
        return await self.send(0x13, to_big5(text) + b"\x00")

    async def zigong(self, password: str, code: str = ""):
        """**自宫（不可逆）**：C2S 0x98 0D <密码长度> <账号密码> <暗码长度> <暗码>（客户端『輸入密暗碼 按確定即執行自宮』0x9d4e04）。
        密码对 -> 服务端把 zigong 置 1，回 0xB8 10（客户端提示「自宮成功」）；不对 -> 0x1A「密碼錯誤」。暗码服务端不看。
        以前这个包被当成"二级密码验证"（password_verify），其实验证成功就是自宫——别当成无副作用的探测。"""
        pw, cd = password.encode("ascii", "ignore"), code.encode("ascii", "ignore")
        return await self.send(0x98, b"\x0d" + bytes([len(pw)]) + pw + bytes([len(cd)]) + cd)

    async def password_echo(self, sub: int, data: bytes = b"\x00" * 5):
        """0x98 0F / 0E + 5 字节：服务端原样回显 0xB8 13 / 12 + 5 字节（客户端用途不清楚）。"""
        return await self.send(0x98, bytes([sub]) + data[:5].ljust(5, b"\x00"))

    async def item_info(self, item_id: int):
        """0x71 物品信息：物品 ID(LE32) + 1 字节 -> 0x88 = 物品 ID + c8 00 00 00 00（对任何 ID 都一样）。"""
        return await self.send(0x71, struct.pack("<I", item_id) + b"\x00")

    async def recycle(self, item_id: int, n: int = 1, dur: int = 200):
        """0x99 子指令 23 VIP 回收：物品 ID(LE32) + 耐久 + 数量(1)。价格 × 数量 > 0：0x7B 3C 新金钱 + 0x1A 提示 + 0x0B；物品不足 -> 0x1A。"""
        return await self.send(0x99, b"\x23" + struct.pack("<IBB", item_id, dur, n))

    # ---------- 新账号流程 / 删除角色（docs/新建角色.md、账号类指令.md）----------
    async def roll(self):
        """0x76 摇点 -> 0x5A = 03 + 7 个 15..25 的数（总和 140）；可以反复摇，结果不存库。"""
        return await self.send(0x76)

    async def create_name(self, name: str):
        """0x20 起名字：1 字节 + 名字（GBK）。回 0x25：00 可用（服务端已插入角色行）/ 01 已被占用。"""
        return await self.send(0x20, b"\x00" + name.encode("gbk", errors="replace"))

    async def create_enter(self, name: str, birth_map: int, attrs, head: int = 1, mode: int = 1, month: int = 1, day: int = 1, nick: str = ""):
        """0x19 长载荷：进入世界并落定角色。[0]未知 [1:3]出生地图 [3]名字长度 名字 昵称长度 昵称 7 项属性(臂力 胆识 悟性 富源 定力 机敏 根骨) 头像 模式 生日月 生日日。
        7 项属性总和 > 145 或长度不够：静默放弃。出生地图 3304 / 8105 / 1305 / 2802 才有出生坐标。成功后服务端照常发整个登录序列。"""
        nm, nk = name.encode("gbk", errors="replace"), nick.encode("gbk", errors="replace")
        body = b"\x00" + struct.pack("<H", birth_map) + bytes([len(nm)]) + nm + bytes([len(nk)]) + nk + bytes(attrs) + bytes([head, mode, month, day])
        return await self.send(0x19, body)

    async def delete_role(self, password: str):
        """0x33 删除角色：1 字节 + 密码长度 + 账号密码。**只能在选角色界面（登录握手之后、还没 start）用**：进入世界后原版会崩。
        成功回 0x36 01（账号保留，之后重新走建角色流程）；密码错回「密碼錯誤」。"""
        pw = password.encode("ascii", "ignore")
        return await self.send(0x33, b"\x00" + bytes([len(pw)]) + pw)

    async def use_item(self, item_id: int):
        """0x0B 使用物品：物品ID(LE32)。药品见 docs/药品效果.md；背包没有 -> 0x1A「物品不足」。"""
        return await self.send(0x0B, struct.pack("<I", item_id))

    async def shop_open(self, merchant_id: int):
        """0x09 开店：商人 ID(LE16，data/商人.csv)。回 0x1A + 0x09 商品列表 + 两条常量 0x1B；不认识的商人回 0x1A「此商人沒錄入」。"""
        return await self.send(0x09, struct.pack("<H", merchant_id))

    async def buy(self, items):
        """0x0A 批量购买：[(物品ID, 数量), ...] -> 每条 8 字节。原版规则：单价恒为 1、背包每条只加 1 件、「商品」列=1 才能买。"""
        return await self.send(0x0A, b"".join(struct.pack("<II", i, n) for i, n in items))

    async def say(self, text: str):
        """0x02 子类型 01 公共聊天。"""
        return await self.send(0x02, b"\x01" + to_big5(text))

    # ---------- 战斗（见 jyfight.py / 战斗协议_客户端侧.md） ----------
    async def fight_encounter(self, entity_id: int, count: int = 1):
        """C2S 0x30 遭遇怪物（实体 id = 实例序号×100000 + mob_id + 1e8；< 10000001 原版不进战斗）。count = 同种怪的数量（新服务端扩展，1–5）。重置本地战斗状态。"""
        self.fight.reset()
        return await self.send(0x30, jyfight.build_encounter(entity_id, count))

    async def fight_enter(self, col=None, row=None):
        """C2S 0xE3 进战：报告自己所在格。"""
        if col is not None:
            self.fight_cell = (col, row)
        self.fight.entered = True
        return await self.send(0xE3, jyfight.build_enter(self.me["fields"]["jyid"], *self.fight_cell))

    async def fight_act(self, caster: int, target_cell, skill: int = jyfight.BASIC_SKILL, cmd: int = 2, cell=None, level: int = 0, direction: int = 0, tick: int = 0):
        """C2S 0xD7 出招。caster 是自己 → 玩家出招（[13][14] 混淆）；是怪物实体 id → 替怪发（客户端跑怪 AI）。"""
        me = self.me["fields"]["jyid"]
        mob = jyfight.is_mob(caster)
        # [11][12]：原版里是施术者自己所在格（怪发的是自己的格 + 目标格在 [13][14]；玩家的目标格被混淆过）；新服务端按 [11][12] 找被打的怪，
        # 所以这里默认把目标格放进去（玩家 / 怪都一样），要发原版形态的传 cell=自己的格。
        cell = cell or target_cell
        # SEED = S2C 0xD1 载荷偏移 16 的 LE32（原版 FUN_00706c4610 把它存进 G+0x24d8197；逆向确认，见 逆向笔记_loginp.md「SEED」）
        d1 = getattr(self.fight, "d1", None) or b""
        seed = struct.unpack_from("<I", d1, 16)[0] if len(d1) >= 20 else 0
        return await self.send(0xD7, jyfight.build_act(caster, cmd, skill, cell, target_cell, level=level, tick=tick, direction=direction, mob=mob, jyid=me, seed=seed))

    async def fight_pose(self, cmd: int, counter: int = None):
        """战斗命令栏的 防禦 7 / 閃躲 8 / 養精蓄銳 9 / 自動 11 → C2S 0xDE（10 字节）。服务端把它当"出招转发"回 S2C D7（cmd = 命令号）。"""
        if cmd not in jyfight.POSE_CMDS:
            raise ValueError("不是 0xDE 命令: %r" % (cmd,))
        counter = int(time.time() * 1000) & 0xFFFFFFFF if counter is None else counter
        return await self.send(jyfight.OP_POSE, jyfight.build_pose(self.me["fields"]["jyid"], cmd, counter))

    async def fight_escape(self):
        """战斗命令栏的 逃跑 → C2S 0xF9（空载荷）。成功与否由服务端回 E6(自己) / 81 决定。"""
        return await self.send(jyfight.OP_ESCAPE, jyfight.build_escape())

    async def fight_end(self):
        """C2S 0xE5 战斗结束上报（客户端自己判完胜负后发；载荷不含胜负）。"""
        self.fight.end_sent = True
        return await self.send(0xE5, jyfight.build_end(self.me["fields"]["jyid"]))

    async def fight_tick(self, now=None, delay=jyfight.END_DELAY, interval=4.0):
        """周期调用：到点的怪物替它们发 D7；胜负已分且等够 delay 秒 → 发 E5。返回本次动作列表。"""
        done = []
        f = self.fight
        me = self.me["fields"]["jyid"] if self.me else None
        for mid, tid in f.plan_enemy_acts(me, now, interval=interval):
            t = f.ents[tid]
            await self.fight_act(mid, (t.col if t.col is not None else self.fight_cell[0], t.row if t.row is not None else self.fight_cell[1]))
            done.append(("mob_act", mid))
        if f.end_due(now, delay):
            await self.fight_end()
            done.append(("end", f.result))
        return done

    async def fight_move(self, col: int, row: int, tick: int = 0):
        """C2S 0xD4 战斗内走到某格（密钥填 0 = 明文坐标）。本地先记下自己的新位置，服务端回显的 S2C D4 会再确认一次。"""
        me = self.me["fields"]["jyid"]
        self.fight_cell = (col, row)
        e = self.fight.ent(me)
        e.col, e.row = col, row
        return await self.send(0xD4, jyfight.build_move(me, col, row, tick))
