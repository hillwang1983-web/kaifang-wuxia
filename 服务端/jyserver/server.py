"""新服务端（M1 骨架）：asyncio TCP，说原版协议，原版客户端应能直接连。

目前实现的 C2S 指令（行为都按对原版服务端的实测复刻，依据见 docs/）：

  0x01 登录      载荷 jyid(LE32) + 未知常量(LE32) + 明文密码ASCII；首包密钥 0x9E。
                 （旧笔记把末尾 ASCII 当成「账号名」，其实是密码：测试号密码恰好等于 jyid。）
                 成功 → 回固定的握手响应（密钥 0x9F，34 字节帧 + 1 个明文 00），之后 S2C 密钥 0x7D。
                 还没有角色的账号走「新账号握手」（密钥换成 0x34）→ 0x76 摇点 → 0x20 起名字 → 长 0x19 确认属性，
                 见 jyserver/creation.py、docs/新建角色.md。
  0x76 摇点      → 回 S2C 0x5A：子类型 03 + 7 个属性值，每个 15..25，总和恰为 140。
  0x19 启动登录  载荷恰好 1 字节 → 回登录序列，由 state.py 按角色库里的数据生成
                 （已用 4 个角色与原版回包逐字节比对，见 docs/登录序列布局.md）。
                 登录校验：角色库（jyserver.importer 从原版 MySQL 导入）里的 jyid + 明文密码，state=0 的号拒绝。
                 进入世界后：其他在线玩家收到 0x60/0x14/0x02（上线），下线时收到 0x05/0x14。
  0x02 公共聊天  子类型 01 + 文本 → 转发给其他在线玩家（S2C 0x04），发送者饮食/饮水各 -5（S2C 0x7B）。
  0x06 移动      起点XY+终点XY → 记录新位置，回显 S2C 0x06 给同地图所有人（含自己）。
  0x6B 事件      地图+事件id → 执行 事件.csv 里的结果（标记/物品/数值/验证），见 jyserver/events.py、docs/事件引擎.md。

和原版服务端一致的约定：
  * C2S 密钥 = 0x7D XOR 序号（首包 0x9E）；密钥对不上的帧被静默忽略（原版会把它解成乱码）。
  * 连续两帧序号相同 → 断开连接（原版的防重放）。
  * 握手之前收到其他指令 → 忽略；载荷长度不对 → 断开。

    python -m jyserver.server --host 0.0.0.0 --port 6732
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import signal
import struct
import sys
import time
from pathlib import Path

from .codec import (
    KEY_C2S_HANDSHAKE,
    KEY_DEFAULT,
    KEY_S2C_HANDSHAKE,
    FrameReader,
    c2s_key,
    derive_key,
    encode_s2c,
)
from . import account, bank, battle, commands, craft, creation, events, kungfu, life, org, shop, study, team, trade
from . import items as itemlogic
from .opcodes import describe
from .state import (
    ItemTable,
    Template,
    appear_frames,
    build_login_stream,
    disappear_frames,
    map_enter_frame,
    map_leave_frame,
    neighbour_frames,
)
from .store import Character, CharacterStore

log = logging.getLogger("jyserver")

ROOT = Path(__file__).resolve().parent.parent
# 握手响应和 0x1E 尾部里未解字段的模板：原版对测试号 8617293 的真实回包
DEFAULT_TEMPLATE = ROOT / "data" / "fixtures" / "char-8617293.json"
DEFAULT_CHARS = ROOT / "data" / "chars.sqlite"
# 原版服务端的 data / config：部署包里随包带一份在 原版数据/ 下，开发机上直接读原版目录
_BUNDLED = ROOT / "原版数据"
_ORIGINAL = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端")
DEFAULT_DATA_DIR = str(_BUNDLED / "data" if (_BUNDLED / "data").is_dir() else _ORIGINAL / "data")

DEFAULT_CONFIG_DIR = str(_BUNDLED / "config" if (_BUNDLED / "config").is_dir() else _ORIGINAL / "config")

# 心跳时的换密钥种子：原版 服务端.exe 里内置的 10 条 `99 04 <种子>` 模板（docs/服务端内置封包模板.md）
REKEY_SEEDS = [bytes.fromhex(s) for s in (
    "0e ae a5 31", "0e ae a5 32", "0e ae a5 33", "0e ae a5 34", "0e ae a5 35", "0e ae a5 36", "0e ae a5 37", "0e ae a5 38",
    "29 62 3e b6", "21 3d b0 96",
)]

HANDSHAKE_TRAILER = b"\x00"  # 实测：握手响应帧后面线路上多一个明文 00
# 还没有角色的账号收到的握手响应（模板 A，实测：33 字节整帧、没有尾部 00）；载荷[1:5] 是密钥种子
NEW_ACCOUNT_HANDSHAKE = bytes.fromhex("01a2bc085f0c252677656e21656c6f722a32032e2e2e17121514121315")
ROLL_SUM = 140
ROLL_MIN, ROLL_MAX, ROLL_COUNT = 15, 25, 7


def roll_stats(rng: random.Random | None = None) -> bytes:
    """原版 0x60b4ec：反复随机 7 个 [15,25] 的整数，直到总和恰为 140。"""
    rng = rng or random
    while True:
        vals = [rng.randint(ROLL_MIN, ROLL_MAX) for _ in range(ROLL_COUNT)]
        if sum(vals) == ROLL_SUM:
            return bytes(vals)


class Conn:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.peer = writer.get_extra_info("peername")
        self.rx = FrameReader("c2s", resync=True)
        self.last_seq: int | None = None
        self.jyid: int | None = None
        self.state = 0  # 0=未握手 1=已握手（原版 player+0x454）
        self.base = KEY_DEFAULT  # C2S 密钥 = base XOR 序号
        self.key = KEY_DEFAULT  # S2C 帧密钥；新账号握手（模板 A）之后两个方向都换成 derive_key(种子)
        self.fresh = False  # 本连接里刚用 0x20 建好角色、还没发过确认属性的长 0x19
        self.closed = False
        self.char: Character | None = None  # 登录后的角色；rows 里的 renwu 就是它的实时状态
        self.entered = False  # 已收到 0x19、登录序列发完 = 在游戏世界里
        self.zigong = False  # 0x98 0D 自宫成功（原版 player+0x14c）
        self.life = life.State()  # 生活技能 / 農夫：当前种子、上次采集时间

    @property
    def renwu(self) -> dict:
        return self.char.rows["renwu"][0]

    @property
    def map(self) -> int:
        return int(self.renwu.get("map") or 0)

    def send_raw(self, data: bytes) -> None:
        if not self.closed:
            self.writer.write(data)

    def send(self, opcode: int, payload: bytes = b"", *, key: int | None = None, wide: bool | None = None) -> None:
        log.info("%s <- S2C 0x%02x %s len=%d", self.peer, opcode, describe("s2c", opcode), len(payload) + (5 if wide else 4))
        self.send_raw(encode_s2c(opcode, payload, key=self.key if key is None else key, wide=wide))

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.writer.close()


class GameServer:
    def __init__(
        self,
        store: CharacterStore,
        items: ItemTable,
        template_path: Path = DEFAULT_TEMPLATE,
        rng: random.Random | None = None,
        config_dir: str | Path | None = DEFAULT_CONFIG_DIR,
        data_dir: str | Path | None = DEFAULT_DATA_DIR,
        autosave_interval: float = 0,
        tick_seconds: float = 0,
    ):
        self.autosave_interval = autosave_interval  # 秒；0 = 不定时存档（只在下线时存）
        self.tick_seconds = tick_seconds  # 全服心跳间隔；0 = 不发心跳 / 换密钥（原版实测约 75.6 秒）
        self.tick = 1  # 心跳计数，0x1E 登录包开头的计数器和心跳包里的计数是同一个数
        self._tick_task: asyncio.Task | None = None
        self._autosave_task: asyncio.Task | None = None
        self.store = store
        self.items = items
        self.merchants = shop.Merchants.load(data_dir) if data_dir else shop.Merchants()
        self.event_tables = events.Tables.load(data_dir) if data_dir else events.Tables()
        self.kungfu = kungfu.Kungfu.load(data_dir) if data_dir else kungfu.Kungfu()
        self.life = life.Life.load()
        self.craft = craft.Craft.load()
        self.battles = battle.Battles(battle.Mobs.load(data_dir) if data_dir else battle.Mobs(), items, self.kungfu.attack, rng)
        self.defaults = creation.load_defaults()
        self.starter_items = creation.load_starter_items(config_dir)
        self.template = Template.load(template_path)
        first = self.template.frames[0]  # 握手响应：固定常量，和账号无关
        assert first[0] == 0x01
        self.handshake_payload = first[1]
        self.started = time.monotonic()
        self.rng = rng
        self.online: dict[int, Conn] = {}  # jyid -> 已进入游戏世界的连接
        self.trades = trade.Trades()
        self.teams = team.Teams()
        self.orgs = org.Orgs()  # 组织表只放内存、不随下线清掉（原版一样，库里 zuzhi 表没数据）
        self.ground: list[dict] = []  # 丢弃在地上的物品：{"map","x","y","item","dur","qty","owner"}。拾取（0x0F）从这里找，重启即清空；原版也只放内存
        self.handlers = {
            0x01: self.on_login,
            0x76: self.on_roll,
            0x20: self.on_create,
            0x19: self.on_start_login,
            0x02: self.on_chat,
            0x03: self.on_whisper,
            0x06: self.on_move,
            0x5D: self.on_teleport,
            0x09: self.on_open_shop,
            0x0A: self.on_buy,
            0x22: lambda c, f: self._bank_cmd(c, lambda rows: bank.transfer(rows, self.items, f.payload)),
            0x23: lambda c, f: self._bank_cmd(c, lambda rows: bank.open_bank(rows, self.items)),
            0x71: lambda c, f: self._bank_cmd(c, lambda rows: bank.item_info(f.payload)),
            0x6B: self.on_event,
            0x15: lambda c, f: self._item_cmd(c, itemlogic.equip, f),
            0x16: lambda c, f: self._item_cmd(c, itemlogic.unequip, f),
            0x0B: lambda c, f: self._item_cmd(c, itemlogic.use_item, f),
            0x0D: lambda c, f: self._item_cmd(c, itemlogic.discard, f),
            0x0F: lambda c, f: self._item_cmd(c, lambda rows, table, payload: itemlogic.pickup(rows, self.ground, c.map, payload), f),
            0x1C: lambda c, f: self._trade(c, lambda: self.trades.request(c.jyid, int.from_bytes(f.payload[:4], "little"), self._online_rows()) if len(f.payload) >= 4 else []),
            0x1E: lambda c, f: self._trade(c, lambda: self.trades.add_item(c.jyid, f.payload, self.items)),
            0x1F: lambda c, f: self._trade(c, lambda: self.trades.set_money(c.jyid, f.payload)),
            0x1D: lambda c, f: self._trade(c, lambda: self.trades.command(c.jyid, f.payload, self._online_rows())),
            0x99: lambda c, f: self._item_cmd(c, itemlogic.recycle, f),  # VIP 指令族，目前只做子指令 0x23 回收
            0xC7: self.on_command,
            0x13: self.on_nickname,
            0x33: self.on_delete_character,
            0x98: self.on_password,
            0x67: self.on_betray,
            0x60: self.on_read_book,
            0x5E: self.on_study,
            0x5A: lambda c, f: self._life(c, self.life.work, f),
            0x5B: lambda c, f: self._life(c, lambda *a: self.life.plant(a[0], a[2], a[4], a[5]), f),
            0x5C: lambda c, f: self._life(c, self.life.till_or_harvest, f),
            0x1B: self.on_craft,
            0x26: lambda c, f: self._team(c, lambda on: self.teams.create(c.jyid, f.payload, on)),
            0x2C: lambda c, f: self._team(c, lambda on: self.teams.invite(c.jyid, f.payload, on)),
            0x2D: lambda c, f: self._team(c, lambda on: self.teams.reply(c.jyid, f.payload, on)),
            0x2E: lambda c, f: self._team(c, lambda on: self.teams.chat(c.jyid, f.payload, on)),
            0x27: lambda c, f: self._team(c, lambda on: self.teams.disband(c.jyid, on)),
            0x29: lambda c, f: self._team(c, lambda on: self.teams.leave(c.jyid, on)),
            0x30: lambda c, f: self._battle(c, self.battles.encounter, f),
            0xE3: lambda c, f: self._battle(c, self.battles.enter, f),
            0xD7: lambda c, f: self._battle(c, self.battles.act, f),
            0xD4: lambda c, f: self._battle(c, self.battles.move, f),
            0xD8: lambda c, f: self._battle(c, self.battles.status, f),
            0xE5: lambda c, f: self._battle(c, self.battles.end, f),
            0xE6: lambda c, f: self._battle(c, self.battles.end, f),
            0xDE: lambda c, f: self._battle(c, self.battles.pose, f),
            0xF9: lambda c, f: self._battle(c, self.battles.escape, f),
            0x61: self.on_kf_equip,
            0x6A: self.on_kf_delete,
            0x45: lambda c, f: self._org(c, lambda on: self.orgs.create(c.jyid, f.payload, on)),
            0x4E: lambda c, f: self._org(c, lambda on: self.orgs.recruit(c.jyid, f.payload, on)),
            0x4F: lambda c, f: self._org(c, lambda on: self.orgs.reply(c.jyid, f.payload, on)),
            0x50: lambda c, f: self._org(c, lambda on: self.orgs.kick(c.jyid, f.payload, on)),
            0x51: lambda c, f: self._org(c, lambda on: self.orgs.leave(c.jyid, f.payload, on)),
            0x56: lambda c, f: self._org(c, lambda on: self.orgs.query(c.jyid, f.payload, on)),
        }

    # ---- 网络层
    async def serve(self, host: str, port: int) -> asyncio.AbstractServer:
        server = await asyncio.start_server(self._client, host, port)
        if self.autosave_interval > 0:
            self._autosave_task = asyncio.create_task(self._autosave_loop())
        if self.tick_seconds > 0:
            self._tick_task = asyncio.create_task(self._tick_loop())
        return server

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            self.on_tick()

    def on_tick(self) -> None:
        """全服心跳（原版约每 75.6 秒一次，实测）。对每个在线玩家：

        1. 在线时间 renwu.online_time += 10；
        2. 发 0x33（长帧）= 心跳计数 LE32 + 在线时间 LE32；
        3. 发 0x99（短帧）= 04 + 4 字节种子，随后**双方密钥都换成 derive_key(种子)**
           （0x33 和 0x99 本身还用旧密钥发；此后 S2C 帧用新密钥，C2S 帧密钥基数也换成新值）。
        种子是原版内置的 10 个之一（见 docs/服务端内置封包模板.md）。
        """
        self.tick += 1
        for c in list(self.online.values()):
            if c.closed or not c.entered:
                continue
            c.renwu["online_time"] = str(int(c.renwu.get("online_time") or 0) + 10)
            c.send(0x33, self.tick.to_bytes(4, "little") + int(c.renwu["online_time"]).to_bytes(4, "little"), wide=True)
            seed = (self.rng or random).choice(REKEY_SEEDS)
            c.send(0x99, b"\x04" + seed, wide=False)
            c.key = c.base = derive_key(seed)

    async def _autosave_loop(self) -> None:
        """每隔 autosave_interval 秒把所有在线玩家存一次档，进程崩溃时最多丢这么久的进度。"""
        while True:
            await asyncio.sleep(self.autosave_interval)
            self.save_all()

    def save_all(self) -> int:
        n = 0
        for c in list(self.online.values()):
            if c.entered and c.char is not None:
                self.store.put(c.jyid, c.char.password, kungfu.persistable(c.char.rows), c.char.state)
                n += 1
        if n:
            log.info("autosaved %d online character(s)", n)
        return n

    def stop(self) -> None:
        """停掉后台任务，并把在线玩家存档（正常退出时调用）。"""
        for name in ("_autosave_task", "_tick_task"):
            task = getattr(self, name)
            if task is not None:
                task.cancel()
                setattr(self, name, None)
        self.save_all()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        c = Conn(reader, writer)
        log.info("%s connected", c.peer)
        try:
            while not c.closed:
                data = await reader.read(65536)
                if not data:
                    break
                for f in c.rx.feed(data):
                    self.dispatch(c, f)
                    if c.closed:
                        break
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            self.leave(c)
            c.close()
            log.info("%s disconnected", c.peer)

    # ---- 分发
    def dispatch(self, c: Conn, f) -> None:
        seq = f.seq
        expect = c2s_key(seq, c.base)
        if f.key != expect:
            log.warning("%s C2S 0x%02x seq=%d: key 0x%02x != expected 0x%02x, ignored (original server decodes it to garbage)", c.peer, f.opcode, seq, f.key, expect)
            return
        if seq == c.last_seq:
            log.warning("%s C2S 0x%02x: duplicate seq %d -> disconnect (anti-replay)", c.peer, f.opcode, seq)
            c.close()
            return
        c.last_seq = seq
        log.info("%s -> C2S 0x%02x %s seq=%d len=%d", c.peer, f.opcode, describe("c2s", f.opcode), seq, f.total_length)
        handler = self.handlers.get(f.opcode)
        if handler is None:
            log.info("%s   (no handler for 0x%02x yet)", c.peer, f.opcode)
            return
        if f.opcode != 0x01 and c.state != 1:
            log.info("%s   (0x%02x before handshake, ignored)", c.peer, f.opcode)
            return
        handler(c, f)

    # ---- 指令
    def on_login(self, c: Conn, f) -> None:
        if len(f.payload) < 8:
            c.close()
            return
        jyid, _const = struct.unpack_from("<II", f.payload)
        password = f.payload[8:].decode("ascii", errors="replace")
        log.info("%s   login jyid=%d (password %d chars)", c.peer, jyid, len(password))
        char = self.store.get(jyid)
        if char is None:
            # 实测：原版对完全不存在的账号既不回包、也不建号，直接断开
            c.close()
            return
        # state=0（原版 account.state）= 账号被禁用；原版对此的回复没测过，暂按拒绝处理
        if char.state == 0 or password != char.password:
            # 原版对失败的回复是常量 `F4 44 06 01 00 00`；当时玩家密钥是否已是 0x7D 没验证，这里用握手密钥
            c.send(0x01, b"\x00\x00", key=KEY_S2C_HANDSHAKE, wide=False)
            return
        c.jyid = jyid
        c.char = char
        if char.has_character:
            c.send(0x01, self.handshake_payload, key=KEY_S2C_HANDSHAKE, wide=False)
            c.send_raw(HANDSHAKE_TRAILER)
        else:
            # 还没有角色：另一条握手（33 字节、没有尾部 00），种子 a2 bc 08 5f 把双向密钥换成 0x34
            c.send(0x01, NEW_ACCOUNT_HANDSHAKE, key=KEY_S2C_HANDSHAKE, wide=False)
            c.key = c.base = derive_key(NEW_ACCOUNT_HANDSHAKE[1:5])
        c.state = 1

    def on_roll(self, c: Conn, f) -> None:
        c.send(0x5A, b"\x03" + roll_stats(self.rng), wide=True)

    def on_create(self, c: Conn, f) -> None:
        """C2S 0x20：1 字节（未知）+ 名字。名字被占用回 `25 01`；否则回 `25 00` 并建出角色（只有名字，其余列用默认值）。"""
        if c.char.has_character or c.entered:
            log.warning("%s   0x20 but account already has a character -> disconnect", c.peer)
            c.close()
            return
        raw = f.payload[1:]
        if not raw:
            return
        name = raw.decode("gbk", errors="replace")
        if self.store.name_taken(name):
            c.send(0x25, b"\x01", wide=False)
            return
        c.send(0x25, b"\x00", wide=False)
        creation.create_character_rows(self.defaults, c.char.rows, c.jyid, name)
        self.store.put(c.jyid, c.char.password, c.char.rows, c.char.state)
        c.fresh = True

    def on_start_login(self, c: Conn, f) -> None:
        if len(f.payload) != 1:
            # 长 0x19 = 新角色确认属性；只有本连接里刚建好的号才接受，已有角色的号发这个，原版记日志并断开
            if not c.fresh:
                log.warning("%s   0x19 payload length %d != 1 -> disconnect", c.peer, len(f.payload))
                c.close()
                return
            req = creation.parse_long_start(f.payload)
            if req is None:  # 太短、或属性总和 > 145：原版静默放弃
                log.warning("%s   invalid creation request, ignored", c.peer)
                return
            creation.apply_create(c.char.rows, req, self.starter_items)
            self.store.put(c.jyid, c.char.password, c.char.rows, c.char.state)
            c.fresh = False
        elif not c.char.has_character:
            c.close()
            return
        if c.entered:
            return
        old = self.online.get(c.jyid)
        if old is not None and old is not c:  # 同一账号重复登录：踢掉旧连接（原版的做法没测过，这是简化）
            self.leave(old)
            old.close()
        minutes = self.tick  # 登录包开头的计数器 = 当前心跳计数（实测与 0x33 里的计数同源）
        king = self.store.top_sponsor() == c.jyid
        neighbours = [o.char.rows for o in self.online.values() if o is not c and o.map == c.map]
        stream = build_login_stream(
            self.template, c.char.rows, self.items, uptime_minutes=minutes, sponsor_king=king, neighbours=neighbours
        )
        stream = [(op, self._randomize_position_byte(p) if op == 0x08 else p, w) for op, p, w in stream]
        for opcode, payload, wide in stream:
            c.send(opcode, payload, wide=wide)
        c.entered = True
        self.online[c.jyid] = c
        self.broadcast(appear_frames(c.char.rows, sponsor_king=king), exclude=c)

    # ---- 世界：在线玩家之间的广播
    def broadcast(self, frames, *, exclude: Conn | None = None, map_id: int | None = None) -> None:
        for other in list(self.online.values()):
            if other is exclude or other.closed or (map_id is not None and other.map != map_id):
                continue
            for op, payload, wide in frames:
                other.send(op, payload, wide=wide)

    def leave(self, c: Conn) -> None:
        """玩家离开世界：存档位置/饮食，通知其他在线玩家。"""
        if not c.entered or self.online.get(c.jyid) is not c:
            return
        self._send_all(self.teams.on_logout(c.jyid, self._team_info()))
        del self.online[c.jyid]
        self.trades.drop(c.jyid)
        self.battles.drop(c.jyid)
        c.entered = False
        self.store.put(c.jyid, c.char.password, kungfu.persistable(c.char.rows), c.char.state)
        self.broadcast(disappear_frames(c.char.rows))

    def on_chat(self, c: Conn, f) -> None:
        """C2S 0x02：公共聊天（原版 0x72e01f 的 T[3]==02 分支 + 实测）。

        载荷 = 子类型 01 + 文本字节（原样转发，不转码）。转给除发送者以外的所有在线玩家：
        S2C 0x04 = 01 + 发送者 jyid(LE32) + 文本。发送者每发一句，饮食、饮水各 -5（到 0 为止），
        并收到两条 0x7B（34 = 饮食，36 = 饮水）：子类型 + 01 + 新值(LE32)。
        子类型 05 = 组织聊天（不扣饮食饮水），见 jyserver/org.py；其他子类型（04 轻频等）还没做。
        """
        if c.entered and len(f.payload) >= 2 and f.payload[0] == 0x05:
            self._send_all(self.orgs.chat(c.jyid, f.payload[1:], self._names()))
            return
        if not c.entered or len(f.payload) < 2 or f.payload[0] != 0x01:
            return
        text = f.payload[1:]
        self.broadcast([(0x04, b"\x01" + c.jyid.to_bytes(4, "little") + text, False)], exclude=c)
        for sub, col in ((0x34, "diet_val"), (0x36, "water_val")):
            v = max(0, int(c.renwu.get(col) or 0) - 5)
            c.renwu[col] = str(v)
            c.send(0x7B, bytes([sub, 0x01]) + v.to_bytes(4, "little"), wide=True)

    def on_whisper(self, c: Conn, f) -> None:
        """C2S 0x03：私聊。载荷 = 目标 jyid(LE32) + 文本字节（原样）。

        目标在线就收到 S2C 0x04（长帧）= 03 + 发送者 jyid(LE32) + 文本；目标不在线什么也不回（发送者也收不到任何提示）。
        不扣饮食饮水（和公共聊天不同）。组织聊天（0x02 子类型 05）和 0x04 的「轻频」需要组织 / 队伍状态，没做。
        """
        if not c.entered or len(f.payload) < 5:
            return
        target = self.online.get(int.from_bytes(f.payload[:4], "little"))
        if target is None or target.closed:
            return
        target.send(0x04, b"\x03" + c.jyid.to_bytes(4, "little") + f.payload[4:], wide=True)

    def _randomize_position_byte(self, payload: bytes) -> bytes:
        """0x08 设定位置的最后 1 字节原版是随机值（实测一直在 2..9 之间）。"""
        return payload[:-1] + bytes([(self.rng or random).randint(2, 9)])

    def on_teleport(self, c: Conn, f) -> None:
        """C2S 0x5D：地图(LE16) x(LE16) y(LE16)。实测原版不做任何校验，直接传。

        自己收到：0x08 设位置 + 空帧 02 6D 3D 31；如果换了地图，再对新图上每个已在的人收到 0x02 + 0x82。
        原地图上的人收到 0x62（离开）；新地图上的人收到 0x61（进入）。传送到同一张图时两者是同一批人，
        先 0x62 后 0x61。
        """
        if not c.entered or len(f.payload) < 6:
            return
        self._teleport(c, *struct.unpack_from("<HHH", f.payload))

    def _teleport(self, c: Conn, new_map: int, x: int, y: int) -> None:
        old_map = c.map
        old_mates = [o for o in self.online.values() if o is not c and o.map == old_map]
        c.renwu["map"], c.renwu["x"], c.renwu["y"] = str(new_map), str(x), str(y)
        mates = [o for o in self.online.values() if o is not c and o.map == new_map]
        pos = struct.pack("<HHH", new_map, x, y) + b"\x00"
        c.send(0x08, self._randomize_position_byte(pos), wide=True)
        for op in (0x02, 0x6D, 0x3D, 0x31):
            c.send(op, b"", wide=True)
        if new_map != old_map:
            for o in mates:
                for op, payload, wide in neighbour_frames(o.char.rows):
                    c.send(op, payload, wide=wide)
        for o in old_mates:
            o.send(*map_leave_frame(c.jyid)[:2], wide=False)
        for o in mates:
            op, payload, wide = map_enter_frame(c.char.rows)
            o.send(op, payload, wide=wide)

    def on_command(self, c: Conn, f) -> None:
        """C2S 0xC7：聊天框 @xxx 文字指令，见 jyserver/commands.py 和 docs/文字指令.md。"""
        if not c.entered:
            return
        res = commands.handle(c.char.rows, self.items, self.event_tables, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        if res.to_all:
            self.broadcast(res.to_all)
        if res.teleport is not None:
            self._teleport(c, *res.teleport)
        if res.kick:  # 原版：把「下线」的帧也发给自己，然后断开
            for op, payload, wide in disappear_frames(c.char.rows):
                c.send(op, payload, wide=wide)
            c.close()

    def on_nickname(self, c: Conn, f) -> None:
        """C2S 0x13：改外号，见 jyserver/account.py。"""
        if not c.entered:
            return
        res = account.change_nickname(c.char.rows, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        self.broadcast(res.to_all)

    def on_delete_character(self, c: Conn, f) -> None:
        """C2S 0x33：删除角色（选角色界面，要输密码）。进入世界后发它原版会崩，这里不理会。"""
        if c.entered or c.char is None:
            return
        res = account.delete_character(c.char.rows, c.char.password, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        if res.deleted:
            self.store.put(c.jyid, c.char.password, c.char.rows, c.char.state)

    def on_kf_equip(self, c: Conn, f) -> None:
        """C2S 0x61：装备武功，见 jyserver/kungfu.py。"""
        if not c.entered:
            return
        res = kungfu.equip(c.char.rows, self.kungfu, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        self.broadcast(res.to_all)

    def on_kf_delete(self, c: Conn, f) -> None:
        """C2S 0x6A：删除武功（要账号密码），见 jyserver/kungfu.py。"""
        if not c.entered:
            return
        res = kungfu.delete(c.char.rows, c.char.password, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)

    def on_read_book(self, c: Conn, f) -> None:
        """C2S 0x60：读秘笈学特殊武功（乾坤大挪移 / 葵花宝典 / 太玄经），见 jyserver/kungfu.py read_book。"""
        if not c.entered:
            return
        res = kungfu.read_book(c.char.rows, self.kungfu, self.items, f.payload)
        for i, (op, payload, wide) in enumerate(res.to_self):
            self.broadcast([fr for pos, fr in res.inline if pos == i])
            c.send(op, payload, wide=wide)
        self.broadcast([fr for pos, fr in res.inline if pos >= len(res.to_self)])

    def on_study(self, c: Conn, f) -> None:
        """C2S 0x5E：消点（学习点 → 武功经验），见 jyserver/study.py。"""
        if not c.entered:
            return
        res = study.study(c.char.rows, self.kungfu, self.rng or random, f.payload)
        for i, (op, payload, wide) in enumerate(res.to_self):
            self.broadcast([fr for pos, fr in res.inline if pos == i])
            c.send(op, payload, wide=wide)
        self.broadcast([fr for pos, fr in res.inline if pos >= len(res.to_self)])

    def _life(self, c: Conn, fn, f) -> None:
        """生活技能 / 農夫（0x5A / 0x5B / 0x5C），见 jyserver/life.py：自己的帧先发，同图其他人的帧（开始干活 / 田块变化）广播。"""
        if not c.entered:
            return
        rng = self.rng or random
        if f.opcode in (0x5B, 0x5C) and c.map == life.ZIXIU_MAP:  # 自修洞：不做事，罚一级武功
            res = self.life.zixiu_penalty(c.char.rows, rng, c.jyid)
        else:
            # work / till_or_harvest 的参数是 (rows, items, state, rng, jyid, payload)；plant 只要 (rows, state, jyid, payload)
            res = fn(c.char.rows, self.items, c.life, rng, c.jyid, f.payload)
        if res.to_all:
            self.broadcast(res.to_all)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        if res.to_map:
            self.broadcast(res.to_map, exclude=c, map_id=c.map)

    def on_craft(self, c: Conn, f) -> None:
        """C2S 0x1B：合成 / 烹調 / 打造（配方键两个字节），见 jyserver/craft.py。"""
        if not c.entered:
            return
        res = self.craft.craft(c.char.rows, self.items, self.life, self.rng or random, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        if res.to_all:  # 公告在自己的帧之后，自己也收得到
            self.broadcast(res.to_all)

    def on_betray(self, c: Conn, f) -> None:
        """C2S 0x67：原版是停用的桩，只回一句提示（背叛师门用 @bpsm），见 account.betray_stub。"""
        if c.entered:
            for op, payload, wide in account.betray_stub(f.payload).to_self:
                c.send(op, payload, wide=wide)

    def on_password(self, c: Conn, f) -> None:
        """C2S 0x98：自宫（0D）/ 回显（0F 0E），见 jyserver/account.py。"""
        if c.char is None:
            return
        res = account.password_check(c.char.password, f.payload, c.char.rows)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        c.zigong = c.zigong or res.zigong

    def on_open_shop(self, c: Conn, f) -> None:
        """C2S 0x09：商人 ID(LE16) → 商品清单，见 jyserver/shop.py。"""
        if not c.entered:
            return
        for op, payload, wide in shop.open_shop(self.merchants, f.payload).to_self:
            c.send(op, payload, wide=wide)

    def _bank_cmd(self, c: Conn, fn) -> None:
        """钱庄相关指令（0x22 存取 / 0x23 打开 / 0x71 物品信息），见 jyserver/bank.py。"""
        if not c.entered:
            return
        for op, payload, wide in fn(c.char.rows).to_self:
            c.send(op, payload, wide=wide)

    def on_buy(self, c: Conn, f) -> None:
        """C2S 0x0A：批量购买（8 字节记录 = 物品ID + 数量），见 jyserver/shop.py。"""
        if not c.entered:
            return
        res = shop.buy(c.char.rows, self.items, f.payload, account_label=str(c.jyid))
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)

    def on_event(self, c: Conn, f) -> None:
        """C2S 0x6B：事件（NPC 对话选项 / 任务 / 奖励），见 jyserver/events.py。"""
        if not c.entered:
            return
        res = events.handle(c.char.rows, self.event_tables, self.items, f.payload, wide=f.wide, rng=self.rng)
        for i, (op, payload, wide) in enumerate(res.to_self):
            self.broadcast([fr for pos, fr in res.inline if pos == i])
            c.send(op, payload, wide=wide)
        self.broadcast([fr for pos, fr in res.inline if pos >= len(res.to_self)])
        if res.to_all:
            self.broadcast(res.to_all)

    def _item_cmd(self, c: Conn, fn, f) -> None:
        """穿/脱装备、用物品：纯函数改角色行，网络层负责发帧（自己 / 全服）。"""
        if not c.entered:
            return
        res = fn(c.char.rows, self.items, f.payload)
        for op, payload, wide in res.to_self:
            c.send(op, payload, wide=wide)
        if res.to_all:
            self.broadcast(res.to_all)
        if res.to_map:
            self.broadcast(res.to_map, exclude=c, map_id=c.map)
        if res.dropped is not None:
            self.ground.append({**res.dropped, "map": c.map, "x": int(c.renwu.get("x") or 0), "y": int(c.renwu.get("y") or 0), "owner": c.jyid})

    def _online_rows(self) -> dict[int, dict]:
        return {j: o.char.rows for j, o in self.online.items() if o.entered and not o.closed}

    def _team_info(self) -> dict[int, team.Info]:
        return {j: team.Info(o.map, str(o.renwu.get("name") or "")) for j, o in self.online.items() if o.entered and not o.closed}

    def _send_all(self, frames) -> None:
        for jyid, op, payload, wide in frames:
            target = self.online.get(jyid)
            if target is not None and not target.closed:
                target.send(op, payload, wide=wide)

    def _team(self, c: Conn, fn) -> None:
        """组队指令（0x26 / 0x27 / 0x29 / 0x2C / 0x2D / 0x2E），见 jyserver/team.py。fn(在线玩家信息) 返回 [(收件人 jyid, opcode, 载荷, 长帧?)]。"""
        if c.entered:
            self._send_all(fn(self._team_info()))

    def _battle(self, c: Conn, fn, f) -> None:
        """战斗指令（0x30 / 0xE3 / 0xD7 / 0xD4 / 0xD8 / 0xE5 / 0xE6），见 jyserver/battle.py；只发给自己。"""
        if not c.entered:
            return
        for op, payload, wide in fn(c.char.rows, c.jyid, f.payload):
            c.send(op, payload, wide=wide)

    def _names(self) -> dict[int, str]:
        return {j: str(o.renwu.get("name") or "") for j, o in self.online.items() if o.entered and not o.closed}

    def _org(self, c: Conn, fn) -> None:
        """组织指令（0x45 / 0x4E / 0x4F / 0x50 / 0x51 / 0x56），见 jyserver/org.py。fn(在线玩家名字) 返回 [(收件人 jyid, opcode, 载荷, 长帧?)]。"""
        if c.entered:
            self._send_all(fn(self._names()))

    def _trade(self, c: Conn, fn) -> None:
        """交易指令（0x1C / 0x1D / 0x1E / 0x1F），见 jyserver/trade.py。fn 返回 [(收件人 jyid, opcode, 载荷, 长帧?)]。"""
        if not c.entered:
            return
        for jyid, op, payload, wide in fn():
            target = self.online.get(jyid)
            if target is not None and not target.closed:
                target.send(op, payload, wide=wide)

    def on_move(self, c: Conn, f) -> None:
        """C2S 0x06：移动，载荷 = 起点 XY + 终点 XY（LE16×4）+ 3 字节未解。

        实测原版对起点/步长/尾部都不校验：一律把终点记为新位置，并把 jyid + 这 8 字节作为 S2C 0x06
        发给同一张地图上的所有人（含自己）。"其他地图的人收不到"是从一次双人实测推断的，范围规则没细测。
        """
        if not c.entered or len(f.payload) < 8:
            return
        x, y = struct.unpack_from("<HH", f.payload, 4)
        c.renwu["x"], c.renwu["y"] = str(x), str(y)
        self.broadcast([(0x06, c.jyid.to_bytes(4, "little") + f.payload[:8], False)], map_id=c.map)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=6732, help="默认 6732，避免和正在运行的原服务端(6731)冲突")
    ap.add_argument("--chars", default=str(DEFAULT_CHARS), help="角色库（python -m jyserver.importer 生成）")
    ap.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="物品表 CSV 所在目录（装备数据.csv、药品.csv）")
    ap.add_argument("--config-dir", default=DEFAULT_CONFIG_DIR, help="原版 config 目录（新人上线.ini）")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--autosave", type=float, default=60, help="定时存档间隔（秒），0 = 关闭；默认 60")
    ap.add_argument("--tick", type=float, default=75.6, help="全服心跳 / 换密钥间隔（秒），0 = 关闭；原版实测约 75.6")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s")

    async def run() -> None:
        store = CharacterStore(args.chars)
        gs = GameServer(store, ItemTable.load(args.data_dir), Path(args.template), config_dir=args.config_dir, data_dir=args.data_dir, autosave_interval=args.autosave, tick_seconds=args.tick)
        server = await gs.serve(args.host, args.port)
        log.info("listening on %s:%d (%d characters in %s)", args.host, args.port, len(store.ids()), args.chars)
        if sys.platform != "win32":  # kill / launchd 停服务时发 SIGTERM：和 Ctrl+C 一样先存档再退出
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
        try:
            async with server:
                await server.serve_forever()
        finally:
            gs.stop()  # Ctrl+C 退出时也把在线玩家存档

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
