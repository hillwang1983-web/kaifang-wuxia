#!/usr/bin/env python3
"""金庸群侠传(网金) 旁路抓包代理：转发 TCP 并解码 loginp.exe 的封包。

只依赖标准库。代理本身不改动任何转发的字节，解码只在副本上做；解码出错也不会影响转发。

用法
  抓包:   python packet_proxy.py --upstream 服务端IP:端口 [--listen 127.0.0.1:19000] [--log capture.jsonl]
          然后让客户端连到 --listen 的地址（改 server.ini / 登录器里的服务器地址，或用 hosts/端口转发）
  回放:   python packet_proxy.py --replay capture.jsonl      （用同一套解码器重新解码已保存的原始数据块）
  自测:   python packet_proxy.py --selftest                  （只用内存数据和本机回环自检，不连任何外部地址）

协议模型（来自对 loginp.exe 的静态逆向，见 逆向笔记_loginp.md，尚未用真实流量验证）
  帧 A: F4 44 | 总长度 1 字节(含魔数) | 类型 1 字节 | 载荷         （消息长度 n<251 时用，总长度=n+3）
  帧 B: F5 B3 | 总长度 2 字节小端(含魔数) | 类型 1 字节 | 载荷       （n>=251 时用，总长度=n+4）
  整个帧（含帧头）逐字节异或同一个单字节密钥。
  握手阶段（连接后的第一批服务端包）密钥固定 0x9f；类型 1(载荷首字节 0)、5、0x92 的包不带种子，之后第一个别的包
  若总长度 >8(A) / >9(B)，则种子=该帧偏移 5..8 (A) / 6..9 (B)，即载荷[1:5]。
  之后服务端发 类型 0x99、载荷[0]==4 的 A 帧会换密钥，新种子=载荷[1:5]。
  密钥 = (138*b0 + 307*b1 + 93*b2 + 78*b3 + 145) mod 217。（常数 145 由两处真实流量校准，静态分析给出的是 163，见 KEY_OFFSET 注释）
  客户端发出的每个数据块前面还有 3 个字节 F6 11 <序号>，不在异或范围内（推测是注入的 wj.dll 钩住发送函数加的）。
  客户端方向：第一个包（序号 1）用密钥 0x9e，之后服务端期望的密钥 = 0x7D XOR 序号（网金复刻项目对序号 2~5 各探测 256 个
  密钥字节得出：0x7F/0x7E/0x79/0x78；用固定 0x7D 的包会被服务端静默忽略）。本工具解码 C2S 时仍从每帧魔数反推实际密钥。

本代理的解码不依赖上面的预测：每个帧都用开头两个字节的魔数直接反推出实际密钥，
并与预测值对比，不一致时输出 "KEY MISMATCH"，用来验证静态分析是否成立。
"""
import argparse
import asyncio
import csv
import json
import os
import random
import struct
import sys
import time
from collections import Counter, defaultdict

MAGIC_A = b"\xf4\x44"
MAGIC_B = b"\xf5\xb3"
HS_KEY = 0x9F
MAX_PENDING = 20000


# 静态解释器算出的常数是 163(0xA3)，但真实流量(2026-10 login-1.jsonl)显示：
#   种子 a2 bc 28 37 -> 实际 0x7d，种子 0e ae a5 31 -> 实际 0x0e，两处都比 163 的结果小 18。
# 因此按实测校准为 145。线性系数 138/307/93/78 与模 217 仍来自静态分析，只有这两个数据点支持。
KEY_OFFSET = 145


def derive_key(seed: bytes) -> int:
    b0, b1, b2, b3 = seed
    return (138 * b0 + 307 * b1 + 93 * b2 + 78 * b3 + KEY_OFFSET) % 217


def xor(data, k: int) -> bytes:
    return bytes(b ^ k for b in data)


def infer_key(two: bytes):
    """由加密后的前两个字节反推 (密钥, 格式)；不是帧开头则返回 None。"""
    if len(two) < 2:
        return None
    k = two[0] ^ 0xF4
    if two[1] ^ k == 0x44:
        return k, "A"
    k = two[0] ^ 0xF5
    if two[1] ^ k == 0xB3:
        return k, "B"
    return None


def encode_frame(msg_type: int, data: bytes, key: int) -> bytes:
    """按客户端 0x9dabc8 + 0x9daca4 的规则构造并加密一个帧（自测和以后写客户端用）。"""
    msg = bytes([msg_type]) + data
    n = len(msg)
    if n < 0xFB:
        frame = MAGIC_A + bytes([n + 3]) + msg
    else:
        frame = MAGIC_B + struct.pack("<H", n + 4) + msg
    return xor(frame, key)


def printable(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


class Decoder:
    """单向字节流解码器（C2S 或 S2C）。"""

    def __init__(self, direction: str, session: "Session"):
        self.dir = direction
        self.s = session
        self.buf = bytearray()
        self.mode = "hs" if direction == "S2C" else "normal"
        # 服务端握手包用 0x9f；客户端的第一个包用 0x9e（实测），收到握手种子后改用握手算出的密钥
        self.expected = HS_KEY if direction == "S2C" else 0x9E
        self.last_key = None
        self.seq = None
        # 客户端方向的服务端期望密钥：首包 0x9e，之后 = 0x7D XOR 序号（网金复刻项目对序号 2~5 各探测 256 个密钥得出）。
        # 服务端换密钥之后 C2S 的规则是否变化未验证，所以收到换密钥帧后置为 None（不再预测，只记录实际密钥）。
        self.c2s_base = 0x7D

    # ---- 喂数据 ----
    def feed(self, data: bytes):
        self.buf += data
        while True:
            # 客户端每次发送前面有 3 字节 F6 11 <序号>，不在异或范围内（实测，见 login-1.jsonl）
            if self.dir == "C2S" and len(self.buf) >= 3 and self.buf[0] == 0xF6 and self.buf[1] == 0x11:
                self.seq = self.buf[2]
                del self.buf[:3]
                continue
            if len(self.buf) < 4:
                return
            inf = infer_key(bytes(self.buf[:2]))
            if inf is None or not self._plausible(0):
                if not self._resync():
                    return
                continue
            key, fmt = inf
            head = xor(self.buf[:4], key)
            total = head[2] if fmt == "A" else head[2] | head[3] << 8
            if len(self.buf) < total:
                return
            raw = bytes(self.buf[:total])
            del self.buf[:total]
            self._frame(xor(raw, key), key, fmt)

    def flush_idle(self):
        """长时间没有新数据且缓冲区解不出帧：把剩余字节作为未成帧数据记录。"""
        if self.buf and (len(self.buf) < 4 or infer_key(bytes(self.buf[:2])) is None or not self._plausible(0)):
            self._unframed(bytes(self.buf), "idle")
            self.buf.clear()

    # ---- 内部 ----
    def _plausible(self, o: int) -> bool:
        b = self.buf
        if len(b) - o < 4:
            return False
        inf = infer_key(bytes(b[o:o + 2]))
        if inf is None:
            return False
        key, fmt = inf
        head = xor(b[o:o + 4], key)
        total = head[2] if fmt == "A" else head[2] | head[3] << 8
        if total < (4 if fmt == "A" else 5):
            return False
        end = o + total
        if end >= len(b) - 1:
            return True
        return infer_key(bytes(b[end:end + 2])) is not None

    def _resync(self) -> bool:
        """在缓冲区里找下一个看起来像帧开头的位置；找到返回 True。"""
        for o in range(1, len(self.buf) - 3):
            if self._plausible(o):
                self._unframed(bytes(self.buf[:o]), "resync")
                del self.buf[:o]
                return True
        if len(self.buf) > MAX_PENDING:
            self._unframed(bytes(self.buf), "overflow")
            self.buf.clear()
        return False

    def _unframed(self, data: bytes, why: str):
        self.s.emit({"ev": "unframed", "dir": self.dir, "why": why, "len": len(data), "hex": data.hex()})

    def _frame(self, frame: bytes, key: int, fmt: str):
        total = len(frame)
        if self.dir == "C2S" and self.seq is not None:
            if self.seq == 1:
                self.expected = 0x9E
            elif self.c2s_base is not None:
                self.expected = (self.c2s_base ^ self.seq) & 0xFF
            else:
                self.expected = None
        if fmt == "A":
            mtype, payload = frame[3], frame[4:]
        else:
            mtype, payload = frame[4], frame[5:]
        ev = {"ev": "frame", "dir": self.dir, "fmt": fmt, "type": mtype, "total": total,
              "key": key, "mode": self.mode, "payload": payload.hex()}
        if self.dir == "C2S" and self.seq is not None:
            ev["seq"] = self.seq
        if self.expected is not None:
            ev["expected_key"] = self.expected
            if key != self.expected:
                ev["warn"] = "KEY MISMATCH: 实际 0x%02x, 预测 0x%02x" % (key, self.expected)
        if self.last_key is not None and key != self.last_key:
            ev["key_changed_from"] = self.last_key
        label = self.s.key_label(key)
        if label:
            ev["key_from_seed"] = label
        self.last_key = key
        self.s.emit(ev)
        if self.dir == "S2C":
            self._model_s2c(fmt, mtype, payload, frame)
        else:
            self.s.note_c2s(key)

    def _model_s2c(self, fmt, mtype, payload, frame):
        """按静态分析的模型预测下一个服务端帧用的密钥。"""
        if self.mode == "hs":
            if fmt == "A" and ((mtype == 1 and payload[:1] == b"\x00") or mtype in (5, 0x92)):
                self.expected = HS_KEY
                return
            self.mode = "normal"
            if fmt == "A" and len(frame) > 8:
                seed = frame[5:9]
            elif fmt == "B" and len(frame) > 9:
                seed = frame[6:10]
            else:
                self.expected = None
                return
            self.expected = self.s.add_seed(seed, "handshake")
        else:
            if fmt == "A" and mtype == 0x99 and payload[:1] == b"\x04" and len(payload) >= 5:
                self.expected = self.s.add_seed(payload[1:5], "rekey")


class Session:
    def __init__(self, conn_id, emit_fn, types=None):
        self.id = conn_id
        self._emit = emit_fn
        self.types = types or {}
        self.seeds = []        # [(seed_hex, key, where)]
        self.c2s = Decoder("C2S", self)
        self.s2c = Decoder("S2C", self)
        self.c2s_keys = []

    def emit(self, ev):
        ev["conn"] = self.id
        ev.setdefault("t", time.time())
        if ev.get("ev") == "frame" and ev["dir"] == "C2S":
            fn = self.types.get(ev["type"])
            if fn:
                ev["code_refs"] = fn[:6]
        self._emit(ev)

    def add_seed(self, seed: bytes, where: str) -> int:
        key = derive_key(seed)
        self.seeds.append((seed.hex(), key, where))
        self.emit({"ev": "seed", "where": where, "seed": seed.hex(), "key": key})
        if where == "rekey":
            self.c2s.c2s_base = None  # 换密钥之后客户端方向的密钥规则未验证
        return key

    def key_label(self, key):
        hits = [i for i, (_, k, _) in enumerate(self.seeds) if k == key]
        return "seed#%d" % hits[-1] if hits else None

    def note_c2s(self, key):
        if not self.c2s_keys or self.c2s_keys[-1] != key:
            self.c2s_keys.append(key)

    def feed(self, direction: str, data: bytes):
        (self.c2s if direction == "C2S" else self.s2c).feed(data)

    def flush_idle(self, direction: str):
        (self.c2s if direction == "C2S" else self.s2c).flush_idle()


# ---------------- 输出 ----------------
class Reporter:
    def __init__(self, log_path=None, quiet=False, raw=True):
        self.log = open(log_path, "a", encoding="utf-8") if log_path else None
        self.quiet = quiet
        self.raw = raw
        self.stats = Counter()
        self.mismatch = 0

    def __call__(self, ev):
        if ev["ev"] == "chunk" and not self.raw:
            return
        if self.log:
            self.log.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self.log.flush()
        k = ev["ev"]
        if k == "frame":
            self.stats[(ev["dir"], ev["type"])] += 1
            if "warn" in ev:
                self.mismatch += 1
        if self.quiet or k == "chunk":
            return
        ts = time.strftime("%H:%M:%S", time.localtime(ev["t"])) + ".%03d" % (int(ev["t"] * 1000) % 1000)
        c = "#%s" % ev.get("conn", "?")
        if k == "frame":
            pl = bytes.fromhex(ev["payload"])
            arrow = "C->S" if ev["dir"] == "C2S" else "S->C"
            line = "%s %s %s %s type=0x%02x total=%d key=0x%02x%s %s |%s|" % (
                ts, c, arrow, ev["fmt"], ev["type"], ev["total"], ev["key"],
                (" seq=%d" % ev["seq"]) if "seq" in ev else "",
                pl[:48].hex(" "), printable(pl[:48]))
            if len(pl) > 48:
                line += " ...(+%d)" % (len(pl) - 48)
            if "key_from_seed" in ev:
                line += "  [key=%s]" % ev["key_from_seed"]
            if "code_refs" in ev:
                line += "  [发送函数 %s]" % ",".join(ev["code_refs"])
            print(line)
            if "warn" in ev:
                print("      !!! " + ev["warn"])
            if "key_changed_from" in ev:
                print("      (密钥由 0x%02x 变为 0x%02x)" % (ev["key_changed_from"], ev["key"]))
        elif k == "seed":
            print("%s %s 种子[%s] %s -> 预测密钥 0x%02x" % (ts, c, ev["where"], ev["seed"], ev["key"]))
        elif k == "unframed":
            print("%s %s %s 未成帧数据(%s) %d 字节: %s" % (
                ts, c, ev["dir"], ev["why"], ev["len"], ev["hex"][:96]))
        elif k in ("open", "close"):
            print("%s %s %s %s" % (ts, c, k, ev.get("peer", "")))

    def summary(self):
        print("\n==== 汇总 ====")
        by = defaultdict(list)
        for (d, t), n in self.stats.items():
            by[d].append((t, n))
        for d in ("C2S", "S2C"):
            if by[d]:
                print(d, "类型计数:", ", ".join("0x%02x×%d" % (t, n) for t, n in sorted(by[d])))
        print("密钥预测不一致次数:", self.mismatch)


def load_types(path):
    types = defaultdict(list)
    if not path or not os.path.exists(path):
        return types
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if len(row) > 1 and row[1].startswith("0x"):
                    for t in (row[6].split() if len(row) > 6 and row[6] else [row[1]]):
                        if row[0] not in types[int(t, 16)]:
                            types[int(t, 16)].append(row[0])
    except Exception as e:  # 类型表只是附加信息
        print("读取类型表失败:", e, file=sys.stderr)
    return types


# ---------------- 代理 ----------------
async def pipe(reader, writer, direction, session, rep):
    try:
        while True:
            try:
                data = await asyncio.wait_for(reader.read(65536), timeout=0.6)
            except asyncio.TimeoutError:
                try:
                    session.flush_idle(direction)
                except Exception as e:
                    print("decoder error:", e, file=sys.stderr)
                continue
            if not data:
                break
            writer.write(data)           # 先转发，保证不改动流量
            await writer.drain()
            try:
                rep({"ev": "chunk", "conn": session.id, "dir": direction, "t": time.time(), "hex": data.hex()})
                session.feed(direction, data)
            except Exception as e:
                print("decoder error:", repr(e), file=sys.stderr)
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def make_handler(up_host, up_port, rep, types, counter):
    async def handle(cr, cw):
        counter[0] += 1
        cid = counter[0]
        session = Session(cid, rep, types)
        peer = cw.get_extra_info("peername")
        rep({"ev": "open", "conn": cid, "t": time.time(), "peer": "%s -> %s:%d" % (peer, up_host, up_port)})
        try:
            ur, uw = await asyncio.open_connection(up_host, up_port)
        except OSError as e:
            rep({"ev": "close", "conn": cid, "t": time.time(), "peer": "上游连接失败: %s" % e})
            cw.close()
            return
        await asyncio.gather(pipe(cr, uw, "C2S", session, rep), pipe(ur, cw, "S2C", session, rep))
        rep({"ev": "close", "conn": cid, "t": time.time()})
    return handle


def split_hostport(s, default_host=None):
    if ":" in s:
        h, p = s.rsplit(":", 1)
        return (h or default_host), int(p)
    return default_host, int(s)


async def run_proxy(args):
    types = load_types(args.types)
    rep = Reporter(args.log, quiet=args.quiet, raw=not args.no_raw)
    up_host, up_port = split_hostport(args.upstream)
    l_host, l_port = split_hostport(args.listen, "127.0.0.1")
    server = await asyncio.start_server(make_handler(up_host, up_port, rep, types, [0]), l_host, l_port)
    print("监听 %s:%d  ->  上游 %s:%d  日志: %s" % (l_host, l_port, up_host, up_port, args.log or "(不写文件)"))
    print("Ctrl+C 结束并输出汇总。")
    try:
        async with server:
            await server.serve_forever()
    finally:
        rep.summary()


# ---------------- 回放 ----------------
def run_replay(args):
    types = load_types(args.types)
    rep = Reporter(None, quiet=False, raw=False)
    sessions = {}
    with open(args.replay, encoding="utf-8") as f:
        for line in f:
            ev = json.loads(line)
            if ev.get("ev") != "chunk":
                continue
            s = sessions.setdefault(ev["conn"], Session(ev["conn"], rep, types))
            s.feed(ev["dir"], bytes.fromhex(ev["hex"]))
    for s in sessions.values():
        s.flush_idle("C2S")
        s.flush_idle("S2C")
    rep.summary()


# ---------------- 自测 ----------------
def _collect():
    out = []
    return out, out.append


def _frames(evs):
    return [(e["dir"], e["fmt"], e["type"], bytes.fromhex(e["payload"])) for e in evs if e["ev"] == "frame"]


def _chunks(data, rnd, size=None):
    i, res = 0, []
    while i < len(data):
        n = size or rnd.randint(1, 9)
        res.append(data[i:i + n])
        i += n
    return res


def selftest():
    rnd = random.Random(7)
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok = ok and cond

    # 1. 密钥公式与解释器给出的样例一致
    # 两处真实流量(login-1.jsonl)：握手种子 a2bc2837 -> 0x7d，换密钥种子 0eaea531 -> 0x0e
    check(derive_key(bytes.fromhex("a2bc2837")) == 0x7D and derive_key(bytes.fromhex("0eaea531")) == 0x0E,
          "密钥公式与两处真实流量一致 (a2bc2837->0x7d, 0eaea531->0x0e)")
    check(derive_key(bytes([1, 2, 3, 4])) == 0xBA and derive_key(bytes(4)) == 0x91,
          "密钥公式样例 (01020304->0xba, 00000000->0x91)")

    # 2. 服务端流：握手 + 换密钥 + 大帧，任意切分
    seed1, seed2 = bytes([9, 8, 7, 6]), bytes([200, 100, 50, 25])
    k1, k2 = derive_key(seed1), derive_key(seed2)
    big = bytes(range(256)) + b"tail"
    plan = [
        (1, b"\x00hi", HS_KEY), (5, b"abc", HS_KEY), (0x92, b"", HS_KEY),
        (0x20, b"\x07" + seed1 + b"zz", HS_KEY),
        (0x31, b"payload", k1), (0x99, b"\x04" + seed2, k1),
        (0x40, big, k2), (0x22, b"", k2),
    ]
    stream = b"".join(encode_frame(t, d, k) for t, d, k in plan)
    for label, chunks in (("随机切分", _chunks(stream, rnd)), ("逐字节", _chunks(stream, rnd, 1)), ("整块", [stream])):
        evs, sink = _collect()
        s = Session(1, sink)
        for c in chunks:
            s.feed("S2C", c)
        got = _frames(evs)
        want = [("S2C", "B" if len(d) + 1 >= 0xFB else "A", t, d) for t, d, _ in plan]
        check(got == want, "S2C 帧还原一致 (%s)" % label)
        check(not any("warn" in e for e in evs), "S2C 无 KEY MISMATCH (%s)" % label)
        check([e["key"] for e in evs if e["ev"] == "seed"] == [k1, k2], "S2C 预测密钥 (%s)" % label)

    # 3. 预测错误时能报警，且仍能解码
    evs, sink = _collect()
    s = Session(2, sink)
    bad = (encode_frame(0x20, b"\x07" + seed1 + b"zz", HS_KEY) + encode_frame(0x31, b"x", (k1 + 1) & 0xFF))
    s.feed("S2C", bad)
    check(any("warn" in e for e in evs) and _frames(evs)[-1][3] == b"x", "密钥预测错误时报警并仍可解码")

    # 4. 客户端流：未成帧前缀 + 密钥变化
    evs, sink = _collect()
    s = Session(3, sink)
    pre = bytes([0x01, 0x02, 0x03, 0x04, 0x05])
    cstream = pre + encode_frame(0x31, b"abc", 0x55) + encode_frame(0x7F, b"\xff", 0x55) + encode_frame(0x24, b"z" * 300, 0x66)
    for c in _chunks(cstream, rnd):
        s.feed("C2S", c)
    s.flush_idle("C2S")
    fr = _frames(evs)
    check([(f[2]) for f in fr] == [0x31, 0x7F, 0x24], "C2S 帧类型序列")
    check(any(e["ev"] == "unframed" and e["hex"] == pre.hex() for e in evs), "C2S 未成帧前缀被单独记录")
    check([e["key"] for e in evs if e["ev"] == "frame"] == [0x55, 0x55, 0x66], "C2S 反推出实际密钥")

    # 4b. 真实流量回归：服务端两个数据块取自 login-1.jsonl（只含服务端方向，不含账号），客户端方向用合成数据
    evs, sink = _collect()
    s = Session(5, sink)
    s.feed("C2S", bytes([0xF6, 0x11, 0x01]) + encode_frame(0x01, b"idxx", 0x9E))
    s.feed("S2C", bytes.fromhex("6bdbbd9e9e3d23b7a899392034f1322895384533d04779477931df8e888b8c8b8b8a00"))
    s.feed("C2S", bytes([0xF6, 0x11, 0x02]) + encode_frame(0x76, b"", 0x7D ^ 2))
    s.feed("S2C", bytes.fromhex("88ce707d4ead7d7d7d777d7d7d893974e47973d3d84c"))
    s.flush_idle("S2C")
    fr = [e for e in evs if e["ev"] == "frame"]
    check([(e["dir"], e["fmt"], e["type"], e["key"]) for e in fr] ==
          [("C2S", "A", 0x01, 0x9E), ("S2C", "A", 0x01, 0x9F), ("C2S", "A", 0x76, 0x7F),
           ("S2C", "B", 0x33, 0x7D), ("S2C", "A", 0x99, 0x7D)], "真实握手流量：帧序列与每帧密钥")
    check([e["seq"] for e in fr if e["dir"] == "C2S"] == [1, 2], "客户端数据块前缀 F6 11 <序号> 被识别为序号")
    check(not any("warn" in e for e in evs), "真实握手流量：无 KEY MISMATCH")
    check([e["key"] for e in evs if e["ev"] == "seed"] == [0x7D, 0x0E], "真实握手流量：预测密钥 0x7d、0x0e")
    check(not any(e["ev"] == "unframed" and e["dir"] == "C2S" for e in evs), "客户端方向没有未成帧数据")

    # 5. 回环端到端：假服务端 + 代理 + 假客户端，转发字节必须原样
    async def e2e():
        got_by_client = bytearray()
        srv_recv = bytearray()
        srv_data = (encode_frame(1, b"\x00hello", HS_KEY) + encode_frame(0x20, b"\x07" + seed1 + b"q", HS_KEY)
                    + encode_frame(0x31, b"ok", k1))
        cli_data = encode_frame(0x31, b"login", k1)

        async def fake_server(r, w):
            w.write(srv_data)
            await w.drain()
            while True:
                d = await r.read(4096)
                if not d:
                    break
                srv_recv.extend(d)
            w.close()

        up = await asyncio.start_server(fake_server, "127.0.0.1", 0)
        up_port = up.sockets[0].getsockname()[1]
        evs, sink = _collect()
        rep = lambda ev: sink(ev)   # noqa: E731
        px = await asyncio.start_server(make_handler("127.0.0.1", up_port, rep, {0x31: ["0x9d0000"]}, [0]),
                                        "127.0.0.1", 0)
        px_port = px.sockets[0].getsockname()[1]
        r, w = await asyncio.open_connection("127.0.0.1", px_port)
        w.write(cli_data)
        await w.drain()
        while len(got_by_client) < len(srv_data):
            d = await asyncio.wait_for(r.read(4096), 3)
            if not d:
                break
            got_by_client.extend(d)
        await asyncio.sleep(0.3)
        w.close()
        await asyncio.sleep(0.3)
        up.close()
        px.close()
        return bytes(got_by_client) == srv_data, bytes(srv_recv) == cli_data, evs

    same_s, same_c, evs = asyncio.run(e2e())
    check(same_s and same_c, "回环：两个方向转发的字节与原始完全一致")
    fr = _frames(evs)
    check([f[2] for f in fr if f[0] == "S2C"] == [1, 0x20, 0x31] and [f[2] for f in fr if f[0] == "C2S"] == [0x31],
          "回环：代理解码出的帧序列")
    check(any(e.get("code_refs") == ["0x9d0000"] for e in evs if e["ev"] == "frame"), "类型表标注生效")
    print("\n全部通过" if ok else "\n有失败项")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listen", default="127.0.0.1:19000", help="本地监听地址，默认 127.0.0.1:19000（只监听本机）")
    ap.add_argument("--upstream", help="服务端 HOST:PORT（抓包模式必填）")
    ap.add_argument("--log", help="JSONL 日志路径（含原始数据块，可用 --replay 重新解码）")
    ap.add_argument("--no-raw", action="store_true", help="日志里不记录原始数据块")
    ap.add_argument("--quiet", action="store_true", help="不在终端打印解码结果")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--types", default=os.path.join(here, "出站消息类型表.csv"), help="出站类型表 CSV（用来标注 C->S 帧）")
    ap.add_argument("--replay", help="回放并重新解码一个日志文件")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.replay:
        return run_replay(args)
    if not args.upstream:
        ap.error("抓包模式需要 --upstream HOST:PORT")
    try:
        asyncio.run(run_proxy(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
