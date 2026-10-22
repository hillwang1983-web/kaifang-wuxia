#!/usr/bin/env python3
"""网关自测：对运行中的 gateway.py（默认 127.0.0.1:8088，上游 6732 的新服务端）做协议和安全检查。只用标准库。

    python test_gateway.py [--port 8088] [--jyid 123456]
"""
import argparse
import base64
import json
import os
import socket
import struct
import sys
import time

RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def http(port, req: bytes):
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    s.sendall(req)
    data = b""
    try:
        while True:
            d = s.recv(65536)
            if not d:
                break
            data += d
    except socket.timeout:
        pass
    s.close()
    return data


def ws_connect(port, origin=None):
    s = socket.create_connection(("127.0.0.1", port), timeout=8)
    key = base64.b64encode(os.urandom(16)).decode()
    h = "GET /ws HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n" % (port, key)
    if origin:
        h += "Origin: %s\r\n" % origin
    s.sendall((h + "\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        d = s.recv(4096)
        if not d:
            break
        buf += d
    return s, buf


def ws_send(s, text: bytes, op=1):
    mask = os.urandom(4)
    n = len(text)
    head = bytes([0x80 | op])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += b"\xfe" + struct.pack(">H", n)
    else:
        head += b"\xff" + struct.pack(">Q", n)
    s.sendall(head + mask + bytes(b ^ mask[i & 3] for i, b in enumerate(text)))


def ws_recv(s, timeout=8):
    s.settimeout(timeout)
    h = s.recv(2)
    if len(h) < 2:
        return None
    n = h[1] & 0x7F
    if n == 126:
        n = struct.unpack(">H", s.recv(2))[0]
    elif n == 127:
        n = struct.unpack(">Q", s.recv(8))[0]
    data = b""
    while len(data) < n:
        data += s.recv(n - len(data))
    return h[0] & 0x0F, data


def recv_json(s, until=None, timeout=10):
    import time
    end = time.time() + timeout
    out = []
    while time.time() < end:
        try:
            r = ws_recv(s, max(0.2, end - time.time()))
        except (socket.timeout, TimeoutError):
            break
        if r is None:
            break
        if r[0] == 1:
            m = json.loads(r[1].decode())
            out.append(m)
            if until and until(m):
                break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--jyid", type=int, default=123456)
    ap.add_argument("--fallback", action="store_true", help="被测网关是用 --look-fallback 启动的")
    ap.add_argument("--mutate", action="store_true", help="再测会改角色数据的动作（脱 / 穿 / 开店），只在隔离服务端上用")
    a = ap.parse_args()
    p = a.port

    r = http(p, b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 200") and "网金网页客户端".encode() in r, "GET / 返回页面")
    for path in ("/gateway.py", "/../gateway.py", "/..%2fgateway.py", "/web/index.html", "/index.html/../../x"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404（不泄露源码 / 不跨目录）" % path)
    r = http(p, b"GET /maps/2801.jpg HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    hd, _, body = r.partition(b"\r\n\r\n")
    check(hd.startswith(b"HTTP/1.1 200") and b"image/jpeg" in hd and body[:2] == b"\xff\xd8" and body[-2:] == b"\xff\xd9", "GET /maps/2801.jpg -> 200 完整 JPEG（%d 字节，原版 SceneBG2.mrg 里切出）" % len(body))
    r = http(p, b"GET /walk/2801.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    hd, _, body = r.partition(b"\r\n\r\n")
    try:
        wj = json.loads(body.decode())
        raw = base64.b64decode(wj["data"])
    except (ValueError, KeyError):
        wj, raw = {}, b""
    check(hd.startswith(b"HTTP/1.1 200") and (wj.get("cols"), wj.get("rows"), wj.get("cell"), wj.get("stride")) == (240, 195, 20, 31) and len(raw) == 195 * 31,
          "GET /walk/2801.json -> 240×195 格、每格 20 像素、每行 31 字节（%d 字节）" % len(raw))
    r = http(p, b"GET /walk/2200.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 200"), "GET /walk/2200.json -> 200")
    r = http(p, b"GET /objects/2801.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    try:
        oj = json.loads(r.partition(b"\r\n\r\n")[2].decode())
    except ValueError:
        oj = []
    check(r.startswith(b"HTTP/1.1 200") and len(oj) > 100 and all(set(o) == {"n", "x", "y", "w", "h", "d", "u"} and o["d"] == o["y"] + o["h"] for o in oj),
          "GET /objects/2801.json -> %d 个前景物件，字段 n x y w h d u，深度线 d = y + h" % len(oj))
    if oj:
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % oj[0]["u"]).encode())
        check(r.partition(b"\r\n\r\n")[2][:8] == b"\x89PNG\r\n\x1a\n", "GET %s -> PNG" % oj[0]["u"])
    r = http(p, b"GET /objects/2200.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 404"), "没有前景物件的地图（2200）-> 404")
    r = http(p, b"GET /npcs/2801.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    try:
        nj = json.loads(r.partition(b"\r\n\r\n")[2].decode("utf-8"))
    except ValueError:
        nj = []
    meat = [n for n in nj if n.get("id") == 28]
    check(r.startswith(b"HTTP/1.1 200") and len(nj) >= 200 and all({"id", "name", "x", "y", "dir", "model", "kind", "ev"} <= set(n) <= {"id", "name", "x", "y", "dir", "model", "kind", "ev", "spr"} for n in nj)
          and len({n["id"] for n in nj}) == len(nj), "GET /npcs/2801.json -> %d 个 NPC / 怪物点，字段 id name x y dir model kind ev（+ 可选 spr 精灵号），编号不重复" % len(nj))
    check(len(meat) == 1 and meat[0]["name"] == "肉商" and meat[0]["model"] == 39015 and (meat[0]["x"], meat[0]["y"]) == (330, 2250) and meat[0]["kind"] == "npc" and meat[0]["ev"] == 11,
          "2801 的 28 号 NPC 是肉商（型号 39015，对得上 MOB数据.csv）在 (330,2250)，kind=npc，11 个事件")
    check(all(0 <= n["x"] < 4800 and 0 <= n["y"] < 3900 for n in nj if n["kind"] == "npc"), "2801 的 NPC 坐标都在地图范围内（4800×3900）")
    r = http(p, b"GET /npcs/2200.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 404") or r.startswith(b"HTTP/1.1 200"), "GET /npcs/2200.json -> 200 或 404（该图有没有 NPC 都不报错）")
    for path in ("/npcs/abc.json", "/npcs/../gateway.py", "/npcs/2801.png", "/npcs/99999999.json"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404" % path)
    for path in ("/obj/280135_999x999.png", "/obj/../gateway.py", "/obj/abc.png", "/obj/280135_160x119.json", "/objects/abc.json"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404" % path)
    for path in ("/walk/99999999.json", "/walk/abc.json", "/walk/../gateway.py", "/walk/2801.png"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404" % path)
    r = http(p, b"GET /sprites/1/M10000_0.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    hd, _, body = r.partition(b"\r\n\r\n")
    try:
        sj = json.loads(body.decode())
    except ValueError:
        sj = {}
    check(hd.startswith(b"HTTP/1.1 200") and sj.get("page") == "M10000_0.png" and set(sj.get("cps", {})) == {"1", "7"},
          "GET /sprites/1/M10000_0.json -> 身体层描述（站立 / 行走各 %s 帧）" % [len(v["frames"]) for v in sj.get("cps", {}).values()])
    r = http(p, b"GET /sprites/1/M10000_0.png HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.partition(b"\r\n\r\n")[2][:8] == b"\x89PNG\r\n\x1a\n", "GET /sprites/1/M10000_0.png -> PNG")
    r = http(p, b"GET /sprites/1/M1PB01_5.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 200"), "第 5 套调色板的层也能按需生成")
    for path in ("/sprites/1/M1WF01_0.json", "/sprites/1/M10000_6.json", "/sprites/999/M10000_0.json", "/sprites/1/m10000_0.json",
                 "/sprites/../gateway.py", "/sprites/1/../../gateway.py", "/sprites/1.json", "/sprites/1/M10000_0.exe", "/sprites/"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404" % path)
    for path in ("/maps/99999999.jpg", "/maps/abc.jpg", "/maps/../gateway.py", "/maps/2801.png", "/maps/123456789.jpg", "/maps/-1.jpg"):
        r = http(p, ("GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % path).encode())
        check(r.startswith(b"HTTP/1.1 404"), "GET %s -> 404" % path)
    r = http(p, b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
    check(r.startswith(b"HTTP/1.1 405"), "POST -> 405")

    s, resp = ws_connect(p, origin="http://evil.example")
    check(resp.startswith(b"HTTP/1.1 403"), "跨站 Origin 的 WebSocket 被拒 (403)")
    s.close()

    s, resp = ws_connect(p, origin="http://127.0.0.1:%d" % p)
    check(resp.startswith(b"HTTP/1.1 101"), "同源 WebSocket 握手成功 (101)")
    ms = recv_json(s, lambda m: m["ev"] == "hello", 3)
    check(ms and ms[0]["ev"] == "hello" and ms[0].get("merchants"), "收到 hello（上游 %s，商人表 %d 个）" % (ms[0].get("server"), len(ms[0].get("merchants", []))))
    hello = ms[0] if ms else {}

    ws_send(s, b"not json")
    ms = recv_json(s, lambda m: m["ev"] == "error", 3)
    check(ms and "JSON" in ms[-1].get("msg", ""), "非 JSON -> 错误提示而不是断线")
    ws_send(s, json.dumps({"op": "say", "text": "x"}).encode())
    ms = recv_json(s, lambda m: m["ev"] == "error", 3)
    check(ms and "还没有登录" in ms[-1].get("msg", ""), "未登录就说话 -> 错误提示")
    for bad in ("abc", -5, 0, 2 ** 40, True, None, 1.5):
        ws_send(s, json.dumps({"op": "login", "jyid": bad}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "error", 3)
        check(ms and "正整数" in ms[-1].get("msg", ""), "非法账号 %r -> 被网关拒绝，没有连游戏服务端" % (bad,))

    ws_send(s, json.dumps({"op": "login", "jyid": a.jyid}).encode())
    ms = recv_json(s, lambda m: m["ev"] == "me", 12)
    me = next((m for m in ms if m["ev"] == "me"), None)
    check(me and me["jyid"] == a.jyid and me["f"]["map"], "登录成功，收到角色状态 %r 地图 %s" % (me and me["name"], me and me["f"]["map"]))
    check(me and all(k in me for k in ("bag", "equip", "wugong", "f")) and me["bag"] and "物品#" not in me["bag"][0]["name"],
          "状态里有背包 / 装备 / 武功，物品名已解析: %s" % (me["bag"][0] if me and me["bag"] else None))
    lk = me.get("look") or {}
    names = [e["l"] for e in lk.get("layers", [])]
    check(lk.get("model") == 1 and names[:2] == ["B10S", "M10000"], "me 里有外观层 look=%s" % names)
    if a.jyid == 123456 and not a.fallback:
        check(names == ["B10S", "M10000"] and all(not i["code"] for i in lk["info"]),
              "123456 的盔 / 战甲 / 星剑不在 Item3.Dat 里 -> 只画阴影 + 身体（和原版客户端的做法一致）")
    if a.jyid == 123456 and a.fallback:
        check(names == ["B10S", "M10000", "M1WD01"] and lk["info"][2].get("fallback"),
              "兜底开启：12498（剑）-> M1WD01，盔 / 战甲仍然不画 %s" % names)
        check(hello.get("look_fallback") is True, "hello 里带 look_fallback=true")
    ws_send(s, json.dumps({"op": "say", "text": "a" * 200}).encode())
    ms = recv_json(s, lambda m: m["ev"] == "chat", 3)
    check(ms and len(ms[-1]["text"]) == 60, "过长聊天被截到 60 字")
    ws_send(s, json.dumps({"op": "say", "text": "again"}).encode())
    ms = recv_json(s, lambda m: m["ev"] == "error", 2)
    check(ms and "太快" in ms[-1].get("msg", ""), "连发聊天被限速")
    ws_send(s, json.dumps({"op": "move", "x": -1, "y": 99999}).encode())
    ms = recv_json(s, lambda m: m["ev"] in ("pos", "error"), 1.5)
    check(not any(m["ev"] == "pos" for m in ms), "越界坐标不会发给服务端")
    # ---- 动作入口：参数检查（网关层拦截，不会发给服务端）
    def expect_err(msg, frag, label):
        ws_send(s, json.dumps(msg).encode())
        ms = recv_json(s, lambda m: m["ev"] in ("error", "me", "notice"), 2)
        check(ms and ms[-1]["ev"] == "error" and frag in ms[-1].get("msg", ""), "%s -> 错误「%s」" % (label, frag))

    expect_err({"op": "equip", "slot": 5, "item": 1}, "槽位", "穿装备槽位 5")
    expect_err({"op": "equip", "slot": 9, "item": 99999999}, "背包里没有", "穿背包里没有的物品（避免触发全服刷装备广播）")
    expect_err({"op": "unequip", "slot": 0}, "槽位", "脱装备槽位 0")
    expect_err({"op": "use", "item": "a"}, "无效", "用药物品ID 不是整数")
    expect_err({"op": "buy", "items": []}, "无效", "购买空列表")
    expect_err({"op": "buy", "items": [{"item": 1, "n": 0}]}, "无效", "购买数量 0")
    expect_err({"op": "buy", "items": [{"item": 1, "n": 10000}]}, "无效", "购买数量 10000")
    expect_err({"op": "buy", "items": [{"item": 1, "n": 1}] * 21}, "无效", "一次购买 21 条")
    expect_err({"op": "teleport", "map": 70000, "x": 1, "y": 1}, "无效", "传送地图 70000")
    expect_err({"op": "shop_open", "merchant": -1}, "无效", "商人 ID -1")
    # ---- 地形：按角色所在地图的碰撞格挑一个阻挡点和一个可走点
    r = http(p, ("GET /walk/%d.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n" % me["f"]["map"]).encode())
    try:
        wg = json.loads(r.partition(b"\r\n\r\n")[2].decode())
        wd = base64.b64decode(wg["data"])
    except (ValueError, KeyError):
        wg = None
    if wg:
        def blocked(x, y):
            cx, cy = int(x) // wg["cell"], int(y) // wg["cell"]
            if cx < 0 or cy < 0 or cx >= wg["cols"] or cy >= wg["rows"]:
                return True
            return bool((wd[cy * wg["stride"] + (cx >> 3)] >> (cx & 7)) & 1)
        s0 = (me["f"]["x"], me["f"]["y"])
        ring = [(s0[0] + dx, s0[1] + dy) for r_ in range(30, 400, 30) for dx in range(-r_, r_ + 1, 30) for dy in (-r_, r_)] + \
               [(s0[0] + dx, s0[1] + dy) for r_ in range(30, 400, 30) for dy in range(-r_, r_ + 1, 30) for dx in (-r_, r_)]
        bpt = next((q for q in ring if blocked(*q) and 0 <= q[0] < wg["w"] and 0 <= q[1] < wg["h"]), None)
        fpt = next((q for q in ring if not blocked(*q) and 0 <= q[0] < wg["w"] and 0 <= q[1] < wg["h"]
                    and all(not blocked(s0[0] + (q[0] - s0[0]) * k / 20, s0[1] + (q[1] - s0[1]) * k / 20) for k in range(1, 21))), None)
        if bpt:
            expect_err({"op": "move", "x": bpt[0], "y": bpt[1]}, "地形", "地图 %d 走进阻挡格 %s（起点 %s %s）被网关拦下" % (me["f"]["map"], bpt, s0, "在阻挡格上" if blocked(*s0) else "可走"))
        if fpt and a.mutate:
            ws_send(s, json.dumps({"op": "move", "x": fpt[0], "y": fpt[1]}).encode())
            ms = recv_json(s, lambda m: m["ev"] == "pos", 3)
            check(any(m["ev"] == "pos" and (m["x"], m["y"]) == fpt and m["tp"] is False for m in ms), "走到可走格 %s：收到 pos（tp=false）" % (fpt,))
            ws_send(s, json.dumps({"op": "move", "x": s0[0], "y": s0[1]}).encode())
            recv_json(s, lambda m: m["ev"] == "pos", 3)
    if a.mutate:
        slot_item =next((e for e in me["equip"] if e["slot"] == "xiezi"), None)
        ws_send(s, json.dumps({"op": "unequip", "slot": 9}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "me" and any(e["slot"] == "xiezi" and not e["id"] for e in m["equip"]), 4)
        check(any(m["ev"] == "me" for m in ms), "脱鞋子：收到刷新后的 me，鞋子槽为空")
        ws_send(s, json.dumps({"op": "equip", "slot": 9, "item": slot_item["id"]}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "me" and any(e["slot"] == "xiezi" and e["id"] == slot_item["id"] for e in m["equip"]), 4)
        check(any(m["ev"] == "me" for m in ms), "穿回鞋子：收到刷新后的 me，鞋子槽恢复 %s" % slot_item["name"])
        ws_send(s, json.dumps({"op": "shop_open", "merchant": 53}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "shop", 3)
        check(ms and ms[-1]["ev"] == "shop" and len(ms[-1]["items"]) > 5, "开店 53：收到商品列表 %d 件" % (len(ms[-1]["items"]) if ms and ms[-1]["ev"] == "shop" else 0))
    # ---- NPC 对话
    expect_err({"op": "talk", "npc": -1}, "无效", "对话 NPC 编号 -1")
    expect_err({"op": "talk", "npc": 65000}, "没有事件数据", "对话：这张图上没有这个 NPC")
    ws_send(s, json.dumps({"op": "dlg", "i": 0}).encode())      # 没有进行中的对话：静默忽略
    ms = recv_json(s, lambda m: m["ev"] in ("dialog", "error"), 1)
    check(not ms, "没有进行中的对话时 dlg / dlg_close 被静默忽略")
    if a.mutate:
        def dlg_until(pred, t=3):
            ms_ = recv_json(s, lambda m: m["ev"] == "dialog" and pred(m), t)
            dbg[:] = ms_
            return next((m for m in ms_ if m["ev"] == "dialog" and pred(m)), None)

        dbg = []

        tp0 = (me["f"]["map"], me["f"]["x"], me["f"]["y"])
        ws_send(s, json.dumps({"op": "teleport", "map": 2801, "x": 4400, "y": 3440}).encode())
        recv_json(s, lambda m: m["ev"] == "pos" and m["map"] == 2801, 3)
        r = http(p, b"GET /npcs/2801.json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        nl = json.loads(r.partition(b"\r\n\r\n")[2].decode("utf-8"))
        smith = next(n for n in nl if n["name"] == "打鐵舖老闆")
        far = next(n for n in nl if n["kind"] == "npc" and n["ev"] and abs(n["x"] - 4400) > 800)
        expect_err({"op": "talk", "npc": far["id"]}, "太远", "对话：离 %s 太远" % far["name"])
        ws_send(s, json.dumps({"op": "talk", "npc": smith["id"]}).encode())
        m1 = dlg_until(lambda m: m["kind"] in ("menu", "say"))
        check(m1 and m1["kind"] == "menu" and "裝備" in m1["text"] and len(m1["options"]) == 2 and m1["who"] == "打鐵舖老闆",
              "对话 打鐵舖老闆：收到选单「%s」%s %s" % (m1 and m1["text"], m1 and m1["options"], [] if m1 else dbg))
        ws_send(s, json.dumps({"op": "dlg", "i": 0}).encode())
        m2 = dlg_until(lambda m: m["kind"] == "say")
        check(m2 and m2["side"] == "npc" and "上好的裝備" in m2["text"], "选「想看看」：NPC 说「%s」" % (m2 and m2["text"]))
        ws_send(s, json.dumps({"op": "dlg"}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "shop", 3)
        check(any(m["ev"] == "dialog" and m["kind"] == "end" for m in ms) and any(m["ev"] == "shop" and len(m["items"]) > 3 for m in ms),
              "话说完：对话结束并开店 50（京城装备店）%d 件" % max([len(m["items"]) for m in ms if m["ev"] == "shop"] or [0]))
        ws_send(s, json.dumps({"op": "talk", "npc": smith["id"]}).encode())
        dlg_until(lambda m: m["kind"] == "menu")
        ws_send(s, json.dumps({"op": "dlg_close"}).encode())
        ws_send(s, json.dumps({"op": "dlg", "i": 0}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "dialog", 1)
        check(not ms, "dlg_close 之后再回答选单：被忽略")
        ws_send(s, json.dumps({"op": "teleport", "map": tp0[0], "x": tp0[1], "y": tp0[2]}).encode())
        recv_json(s, lambda m: m["ev"] == "pos", 3)
        # ---- 钱庄 / 丢弃 / 拾取 / 文字指令（净效果为零：存了再取、丢了再捡）
        it = me["bag"][-1]
        ws_send(s, json.dumps({"op": "bank_open"}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "bank", 3)
        n0 = sum(b["n"] for b in ms[-1]["items"] if b["id"] == it["id"]) if ms and ms[-1]["ev"] == "bank" else None
        check(n0 is not None, "打开钱庄：收到 bank 清单（%d 种）" % (len(ms[-1]["items"]) if ms and ms[-1]["ev"] == "bank" else -1))
        ws_send(s, json.dumps({"op": "bank_put", "item": it["id"], "n": 1}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "bank", 3)
        check(ms and ms[-1]["ev"] == "bank" and sum(b["n"] for b in ms[-1]["items"] if b["id"] == it["id"]) == (n0 or 0) + 1, "存 1 件 %s：钱庄里 %s → %s" % (it["name"], n0, ms and ms[-1].get("items") and sum(b["n"] for b in ms[-1]["items"] if b["id"] == it["id"])))
        ws_send(s, json.dumps({"op": "bank_get", "item": it["id"], "n": 1}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "bank", 3)
        check(ms and ms[-1]["ev"] == "bank" and sum(b["n"] for b in ms[-1]["items"] if b["id"] == it["id"]) == (n0 or 0), "取回 1 件：钱庄回到 %s" % n0)
        expect_err({"op": "bank_put", "item": 99999999, "n": 1}, "背包里没有", "存背包里没有的物品")
        expect_err({"op": "bank_put", "item": it["id"], "n": 0}, "数量", "存 0 件")
        expect_err({"op": "discard", "item": 99999999}, "背包里没有", "丢背包里没有的物品")
        expect_err({"op": "pickup", "i": 0}, "地上没有", "地上没有东西时捡")
        dropped = None
        for cand in reversed(me["bag"]):
            ws_send(s, json.dumps({"op": "discard", "item": cand["id"]}).encode())
            ms = recv_json(s, lambda m: m["ev"] in ("ground", "error"), 2)
            if ms and ms[-1]["ev"] == "ground":
                dropped = (cand, ms[-1])
                break
        check(dropped and dropped[1]["list"][-1]["id"] == dropped[0]["id"] and dropped[1]["list"][-1]["mine"], "丢弃 %s：收到 ground 列表（我丢的）" % (dropped and dropped[0]["name"]))
        if dropped:
            time.sleep(2.5)       # 原版服务端：刚丢下的东西（如挪动时空仪）立刻捡没有任何回应，过一会儿才捡得起来
            ws_send(s, json.dumps({"op": "pickup", "i": dropped[1]["list"][-1]["i"]}).encode())
            ms = recv_json(s, lambda m: m["ev"] == "ground" and not m["list"], 3)
            check(any(m["ev"] == "ground" and not m["list"] for m in ms), "捡回来：地上清空")
        ws_send(s, json.dumps({"op": "say", "text": "@where"}).encode())
        ms = recv_json(s, lambda m: m["ev"] == "notice" and m.get("kind") == 2, 3)
        check(ms and ms[-1].get("kind") == 2 and "2801" in ms[-1]["text"] + str(tp0[0]) , "@where：收到系统回复「%s」" % (ms and ms[-1].get("text")))
    ws_send(s, b"x" * 70000)       # 超过 64KB
    r = None
    try:
        for _ in range(50):                # 先把排队中的普通消息读掉，再看是不是关闭帧
            r = ws_recv(s, 3)
            if r is None or r[0] == 8:
                break
    except Exception:
        pass
    check(r is None or r[0] == 8, "超大消息 -> 关闭连接")
    s.close()
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
