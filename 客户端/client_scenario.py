#!/usr/bin/env python3
"""用 jyclient 对服务端跑一遍"多人在线"场景并按文档预期断言（默认连网金复刻新服务端 127.0.0.1:6732）。

场景（预期来自 C:\\游戏\\网金复刻\\docs\\聊天移动与上下线广播.md，那份文档是对原版服务端实测的）
  1. B 先上线并走完登录序列；A 再上线 -> B 收到 0x60、0x14(子类型 08 玩家上線)、0x02 外观包
  2. A 移动 -> A 收到 0x06 回显（jyid + 起终点 8 字节）；A 的本地位置变为终点
  3. A 公共聊天 -> B 收到 0x04 01 <A jyid> 文本；A 自己不收到 0x04；A 收到 0x7B 34 01 / 36 01（饮食、饮水 -5）
  4. A 把位置移回原处后下线 -> B 收到 0x05 + 0x14(08 離開)
  5. A 再登录 -> 0x1E 里的位置 = 下线前最后一次移动的终点
只在本机测试用，用的是新服务端自己的 SQLite 角色库；不要拿它去连原版服务端。
"""
import argparse
import asyncio
import json
import struct
import sys

from jyclient import JyClient, from_big5

RESULTS = []


def check(cond, msg):
    RESULTS.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + msg)


def desc(frames):
    return " ".join("%02x" % f.type for f in frames)


async def online(c, jyid):
    hs = await c.login(jyid)
    if hs is None:
        raise SystemExit("账号 %d 登录没有回握手（不存在 / 被拒 / 被单点登录挤掉）" % jyid)
    seq = await c.start()
    return hs, seq


async def main(a):
    A = JyClient(a.host, a.port, log=a.log, name="A")
    B = JyClient(a.host, a.port, log=a.log + ".B" if a.log else None, name="B")
    await B.connect()
    await online(B, a.b)
    check(B.me and B.me["fields"]["jyid"] == a.b, "B 登录序列里有 0x1E，jyid=%d，名字 %r，地图 %s 位置 %s" % (
        a.b, B.me["name"], B.me["fields"]["map"], (B.me["fields"]["x"], B.me["fields"]["y"])))
    await B.drain(0.5)

    await A.connect()
    hs, seq = await online(A, a.a)
    check(seq and seq[-1].type == 0xA9, "A 登录序列以 0xA9 结尾，共 %d 帧: %s" % (len(seq), desc(seq)))
    af = A.me["fields"]
    orig = (af["x"], af["y"])
    print("   A: 名字 %r 地图 %d 位置 %s 背包容量 %d" % (A.me["name"], af["map"], orig, A.me["bag_capacity"]))
    check(not A.me["const_mismatch"] and A.me["tail_is_branch_b"], "A 的 0x1E 通过布局校验（常量块、1222 尾长）")

    got = await B.drain(1.0)
    types = [f.type for f in got]
    check(0x60 in types and 0x14 in types and 0x02 in types, "B 收到 A 上线广播 %s" % desc(got))
    notice = next((f for f in got if f.type == 0x14 and f.payload[:1] == b"\x08"), None)
    check(notice and str(a.a) not in "" and from_big5(notice.payload[1:]).endswith("上線了"),
          "B 的上线通知: %r" % (from_big5(notice.payload[1:]) if notice else None))
    same_map = B.me["fields"]["map"] == af["map"]
    print("   两人%s同一张地图" % ("在" if same_map else "不在"))

    # ---- 移动 ----
    await A.drain(0.3)
    dest = (orig[0] + 30, orig[1] + 20)
    await A.move(orig[0], orig[1], dest[0], dest[1])
    f = await A.wait(lambda f: f.type == 0x06, 3)
    check(f is not None and struct.unpack_from("<IHHHH", f.payload) == (a.a, orig[0], orig[1], dest[0], dest[1]),
          "A 收到自己的 0x06 回显 %s" % (f.payload.hex(" ") if f else None))
    check(A.pos == dest, "A 本地位置更新为 %s" % (A.pos,))
    fb = await B.wait(lambda f: f.type == 0x06, 1.5)
    check((fb is not None) == same_map, "B %s收到 A 的移动广播（同图=%s）" % ("" if fb else "没有", same_map))

    # ---- 聊天 ----
    await A.drain(0.3)
    await B.drain(0.3)
    text = "你好,网金复刻"
    await A.say(text)
    fb = await B.wait(lambda f: f.type == 0x04, 3)
    check(fb is not None and fb.payload[:1] == b"\x01" and struct.unpack_from("<I", fb.payload, 1)[0] == a.a,
          "B 收到 0x04 01 <A jyid>，文本 %r" % (B.chat_log[-1][2] if B.chat_log else None))
    rest = await A.drain(1.0)
    check(all(f.type != 0x04 for f in rest), "A 自己没有收到 0x04（实际收到: %s）" % desc(rest))
    b7 = [f.payload for f in rest if f.type == 0x7B]
    check(len(b7) == 2 and b7[0][:2] == b"\x34\x01" and b7[1][:2] == b"\x36\x01",
          "A 收到两条 0x7B：饮食 %s 饮水 %s" % tuple(struct.unpack_from("<I", p, 2)[0] for p in (b7 + [b"\0" * 6] * 2)[:2]))

    # ---- 回原位并下线 ----
    await A.move(dest[0], dest[1], orig[0], orig[1])
    await A.wait(lambda f: f.type == 0x06, 2)
    await B.drain(0.3)
    await A.close()
    got = await B.drain(1.0)
    types = [f.type for f in got]
    check(0x05 in types and any(f.type == 0x14 and from_big5(f.payload[1:]).endswith("開游戲") for f in got),  # 原文是"离開游戲"（简繁混用，新旧服务端一致）
          "A 下线后 B 收到 0x05 + 離開游戲: %s" % desc(got))

    # ---- 重新登录，位置应是下线前最后一次移动的终点（=原位）----
    A2 = JyClient(a.host, a.port, name="A2")
    await A2.connect()
    await online(A2, a.a)
    check((A2.me["fields"]["x"], A2.me["fields"]["y"]) == orig, "A 重新登录后位置 %s == 原位 %s" % (
        (A2.me["fields"]["x"], A2.me["fields"]["y"]), orig))
    await A2.close()
    await B.close()
    print("\n%d/%d 通过" % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


async def map_scenario(a):
    """传送与同图可见性（docs/传送与地图可见性.md）。A 传进 B 所在的地图，再传回原处。"""
    A = JyClient(a.host, a.port, log=a.log, name="A")
    B = JyClient(a.host, a.port, log=a.log + ".B" if a.log else None, name="B")
    await B.connect()
    await online(B, a.b)
    bf = B.me["fields"]
    bmap, bpos = bf["map"], (bf["x"], bf["y"])
    await A.connect()
    await online(A, a.a)
    af = A.me["fields"]
    amap, apos = af["map"], (af["x"], af["y"])
    await B.drain(0.5)
    b_orig = (bmap, bpos)
    if amap == bmap:        # 库被重置过（几个测试号都在 2200）：先把 B 传到别的图，测完再传回去
        other = 8105 if amap != 8105 else 2801
        await B.teleport(other, 1151, 499)
        await B.drain(0.8)
        await A.drain(0.8)
        bmap, bpos = other, (1151, 499)
        print("   （A、B 原来在同一张地图 %d，已把 B 传到 %d）" % (amap, other))
    check(amap != bmap, "起点：A 在地图 %d，B 在地图 %d（不同图）" % (amap, bmap))
    dest = (bpos[0] + 40, bpos[1] + 20)

    # ---- A 传进 B 的地图 ----
    await A.drain(0.3)
    await A.teleport(bmap, *dest)
    got = await A.drain(1.0)
    check([f.type for f in got][:5] == [0x08, 0x02, 0x6D, 0x3D, 0x31], "A 传送后先收到 08 02 6d 3d 31: %s" % desc(got))
    check(got and struct.unpack_from("<HHH", got[0].payload) == (bmap, *dest), "A 收到的 0x08 = 新地图/坐标 %s" % (got[0].payload.hex(" ") if got else None))
    seen = [f for f in got[5:] if f.type == 0x02]
    check(len(seen) == 1 and struct.unpack_from("<I", seen[0].payload)[0] == a.b and any(f.type == 0x82 for f in got),
          "A 换图后看到图上的 B（0x02 外观 + 0x82）")
    check(a.b in A.players, "A 的本地视野里有 B: %s" % A.players.get(a.b))
    got_b = await B.drain(1.0)
    f61 = next((f for f in got_b if f.type == 0x61), None)
    check(f61 is not None and struct.unpack_from("<IHHH", f61.payload) == (a.a, bmap, *dest),
          "B 收到 0x61（A 进入视野，坐标 %s）: %s" % (dest, desc(got_b)))
    check(a.a in B.players, "B 的本地视野里有 A")

    # ---- 同图移动 / 聊天 ----
    await A.drain(0.2)
    to = (dest[0] + 10, dest[1] + 10)
    await A.move(*dest, *to)
    fb = await B.wait(lambda f: f.type == 0x06, 2)
    check(fb is not None and struct.unpack_from("<IHHHH", fb.payload) == (a.a, *dest, *to), "同图后 B 收到 A 的移动广播 %s" % (fb.payload.hex(" ") if fb else None))
    check(B.players.get(a.a, {}).get("pos") == to, "B 本地记录 A 位置 = %s" % (to,))

    # ---- A 传回原处 ----
    await B.drain(0.3)
    await A.teleport(amap, *apos)
    await A.drain(1.0)
    got_b = await B.drain(1.0)
    f62 = next((f for f in got_b if f.type == 0x62), None)
    check(f62 is not None and struct.unpack_from("<I", f62.payload)[0] == a.a, "A 离开后 B 收到 0x62: %s" % desc(got_b))
    check(a.a not in B.players, "B 的视野里已没有 A")
    await A.close()
    await B.drain(0.5)
    A2 = JyClient(a.host, a.port, name="A2")
    await A2.connect()
    await online(A2, a.a)
    p = A2.me["fields"]
    check((p["map"], p["x"], p["y"]) == (amap, *apos), "A 重新登录位置 %s == 原位" % ((p["map"], p["x"], p["y"]),))
    await A2.close()
    if b_orig[0] != bmap:
        await B.teleport(b_orig[0], *b_orig[1])
        await B.drain(0.8)
    await B.close()
    print("\n%d/%d 通过" % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


async def rekey_scenario(a):
    """周期性换密钥：服务端发 0x33 + 0x99 04 <种子>，客户端必须改 C2S 密钥基数。
    要连一个带心跳的服务端（python -m jyserver.server --tick 4 ...），默认 --tick 0 的实例不会发。"""
    A = JyClient(a.host, a.port, log=a.log, name="A")
    await A.connect()
    await online(A, a.a)
    af = A.me["fields"]
    pos = (af["x"], af["y"])
    check(len(A.rekeys) == 1 and A.rekeys[0][0] == "handshake" and A.base == 0x7D, "握手种子 %s -> 基数 0x%02x" % (A.rekeys[0][1], A.base))
    f99 = await A.wait(lambda f: f.type == 0x99 and f.payload[:1] == b"\x04", 15)
    check(f99 is not None, "收到 0x99 04 换密钥帧: %s" % (f99.payload.hex(" ") if f99 else None))
    if f99 is None:
        return 1
    await A.drain(0.5)
    check(len(A.rekeys) >= 2 and A.base == A.rekeys[-1][2], "客户端基数改为 derive_key(种子) = 0x%02x（种子 %s）" % (A.base, A.rekeys[-1][1]))
    old_base = A.rekeys[-2][2]
    # 正例：用新基数
    await A.move(pos[0], pos[1], pos[0] + 5, pos[1])
    f = await A.wait(lambda f: f.type == 0x06, 2)
    check(f is not None, "换密钥后用新基数发移动：服务端处理并回显")
    # 反例：用旧基数（原版会静默忽略）
    await A.drain(0.3)
    A.base = old_base
    await A.move(pos[0] + 5, pos[1], pos[0] + 10, pos[1])
    f = await A.wait(lambda f: f.type == 0x06, 2)
    check(f is None, "换密钥后仍用旧基数 0x%02x：服务端静默忽略（没有回显）" % old_base)
    await A.close()
    print("\n%d/%d 通过" % (sum(RESULTS), len(RESULTS)))
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6732)
    ap.add_argument("--a", type=int, default=123456)
    ap.add_argument("--b", type=int, default=1234567)
    ap.add_argument("--log", default=None)
    ap.add_argument("--scenario", choices=("chat", "map", "rekey"), default="chat",
                    help="chat=聊天/移动/上下线；map=传送与同图可见性；rekey=周期换密钥（需带心跳的服务端）")
    args = ap.parse_args()
    fn = {"chat": main, "map": map_scenario, "rekey": rekey_scenario}[args.scenario]
    sys.exit(asyncio.run(fn(args)))
