#!/usr/bin/env python3
"""网关的社交 / 账号入口测试：私聊 / 队伍 / 组织聊天、组队、组织、交易（含成交后的重新同步）、武功、外号、VIP 回收、新建角色、删除角色。
自起隔离服务端（临时库）和一个网关实例，用 WebSocket 当"浏览器"。

    python test_gateway_social.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402
import client_social_test as S  # noqa: E402
import test_gateway as G  # noqa: E402

check = T.check
HERE = os.path.dirname(os.path.abspath(__file__))


class W:
    """一个"浏览器页面"：WebSocket + 收到消息的缓冲，wait 先扫缓冲再收新的。"""

    def __init__(self, port):
        self.s, resp = G.ws_connect(port, origin="http://127.0.0.1:%d" % port)
        assert resp.startswith(b"HTTP/1.1 101"), resp[:40]
        self.buf = []
        self.wait(lambda m: m["ev"] == "hello", 5)

    def send(self, **m):
        G.ws_send(self.s, json.dumps(m).encode())

    def wait(self, pred, t=4):
        end = time.time() + t
        while True:
            for i, m in enumerate(self.buf):
                if pred(m):
                    del self.buf[:i + 1]
                    return m
            left = end - time.time()
            if left <= 0:
                return None
            for m in G.recv_json(self.s, None, min(left, 0.5)):
                self.buf.append(m)

    def drain(self, t=0.6):
        for m in G.recv_json(self.s, None, t):
            self.buf.append(m)
        out, self.buf = self.buf, []
        return out

    def last(self, ev, t=0.8):
        """t 秒内收到的最后一个 ev 类型的消息。"""
        msgs = self.drain(t)
        return next((m for m in reversed(msgs) if m["ev"] == ev), None), msgs

    def login(self, jy, pw=None):
        self.send(op="login", jyid=jy, **({"password": pw} if pw else {}))


def tw(s):
    return S.tw(s)


def main():
    tmp = tempfile.mkdtemp(prefix="jygwsocial-")
    db = os.path.join(tmp, "chars.sqlite")
    sp = gp = None
    try:
        pick, _ = S.prepare(db)
        sport, gport = T.free_port(), T.free_port()
        sp = T.start_server(db, sport)
        glog = open(os.path.join(tmp, "gw.log"), "w")
        gp = subprocess.Popen([sys.executable, os.path.join(HERE, "gateway.py"), "--listen", "127.0.0.1:%d" % gport, "--server", "127.0.0.1:%d" % sport],
                              cwd=HERE, stdout=glog, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUTF8="1"))
        for _ in range(120):
            try:
                import socket
                socket.create_connection(("127.0.0.1", gport), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        print("隔离服务端 :%d + 网关 :%d\n" % (sport, gport))
        return run(gport, pick)
    finally:
        for pr in (gp, sp):
            if pr:
                pr.terminate()
                try:
                    pr.wait(5)
                except subprocess.TimeoutExpired:
                    pr.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def run(port, pick):
    A, B = W(port), W(port)
    A.login(123456)
    B.login(1234567)
    ma = A.wait(lambda m: m["ev"] == "me", 12)
    mb = B.wait(lambda m: m["ev"] == "me", 12)
    check(ma and mb, "A / B 登录（%s / %s）" % (ma and ma["name"], mb and mb["name"]))
    ja, jb = ma["jyid"], mb["jyid"]
    check(ma["kf"] and {k["id"] for k in ma["kf"]} == {1000, 1002, 3860} and ma["kf"][0]["name"] == "少林心法", "me.kf = 武功行（id / 名字 / 等级）%s" % ma["kf"])
    A.send(op="teleport", map=2801, x=800, y=3600)
    B.send(op="teleport", map=2801, x=840, y=3600)
    A.drain(1.0)
    B.drain(1.0)

    print("\n-- 聊天频道 --")
    A.send(op="say", text="私聊你好", ch="whisper", to=jb)
    m = B.wait(lambda m: m["ev"] == "chat" and m.get("ch") == "whisper", 3)
    check(m and m["jyid"] == ja and m["text"] == tw("私聊你好"), "私聊 A->B：B 收到 chat ch=whisper")
    A.send(op="say", text="私聊你好", ch="whisper", to="x")
    e = A.wait(lambda m: m["ev"] == "error", 2)
    check(e and "无效" in e["msg"], "私聊目标不是整数：被网关拦下")

    print("\n-- 组队 --")
    A.send(op="party", a="create")
    sa, _ = A.last("social")
    check(sa and [x["jyid"] for x in sa["party"]["members"]] == [ja], "A 创建队伍：social.party.members = [A]")
    A.send(op="party", a="invite", jyid=jb)
    sb, _ = B.last("social")
    check(sb and [x["jyid"] for x in sb["party"]["invites"]] == [ja], "邀请 B：B 的 social.party.invites = [A]")
    B.send(op="party", a="answer", jyid=ja, accept=True)
    sa, _ = A.last("social")
    sb, _ = B.last("social")
    check(sa and sb and [x["jyid"] for x in sa["party"]["members"]] == [ja, jb] and not sb["party"]["invites"], "B 接受：双方队伍 [A, B]，邀请清掉")
    A.send(op="say", text="队里说", ch="party")
    m = B.wait(lambda m: m["ev"] == "chat" and m.get("ch") == "party", 3)
    check(m and m["text"] == tw("队里说"), "队伍聊天：B 收到 chat ch=party")
    B.send(op="party", a="leave")
    sa, _ = A.last("social")
    check(sa and [x["jyid"] for x in sa["party"]["members"]] == [ja], "B 离队：A 的队伍只剩自己")
    A.send(op="party", a="disband")
    A.drain(0.5)

    print("\n-- 组织 --")
    A.send(op="org", a="create", name="测试帮")
    sa, _ = A.last("social")
    check(sa and sa["org"] and sa["org"]["name"] == tw("测试帮"), "A 创立组织：social.org = %s" % (sa and sa["org"]))
    A.send(op="org", a="recruit", jyid=jb)
    sb, _ = B.last("social")
    check(sb and len(sb["org_invites"]) == 1 and sb["org_invites"][0]["creator"] == ja, "招收 B：B 的 org_invites 有 A 的邀请")
    B.send(op="org", a="join", jyid=ja)
    sb, _ = B.last("social")
    check(sb and sb["org"] and sb["org"]["id"] == sa["org"]["id"] and not sb["org_invites"], "B 加入：B.org = 同一个组织")
    A.send(op="org", a="list")
    sa2, _ = A.last("social")
    check(sa2 and sa2["org"]["online"] == [mb["name"]], "成员列表：在线的其他成员 %s" % (sa2 and sa2["org"]["online"],))
    A.send(op="say", text="组织里说", ch="org")
    m = B.wait(lambda m: m["ev"] == "chat" and m.get("ch") == "org", 3)
    check(m and m["text"] == tw("组织里说") and m["jyid"] == ja, "组织聊天：B 收到 chat ch=org")
    A.send(op="org", a="kick", name=mb["name"])
    sb, _ = B.last("social")
    check(sb and sb["org"] is None, "A 踢 B：B 的 org 清空")
    B.send(op="org", a="join", jyid=ja)
    B.drain(0.5)
    B.send(op="org", a="quit")
    sb, _ = B.last("social")
    check(sb and sb["org"] is None, "B 退出：org 清空")

    print("\n-- 交易（成交后网关自动重新同步）--")
    it0, it1 = pick
    n_a1 = sum(b["n"] for b in ma["bag"] if b["id"] == it1)
    A.send(op="trade", a="request", jyid=jb)
    sa, _ = A.last("social")
    check(sa and sa["trade"] and sa["trade"]["with"]["jyid"] == jb and sa["trade"]["stage"] == "open", "请求交易：social.trade 建立")
    A.send(op="trade", a="item", item=it0)
    B.send(op="trade", a="item", item=it1)
    sa, _ = A.last("social")
    sb, _ = B.last("social")
    check(sa and [o["id"] for o in sa["trade"]["mine"]] == [it0] and [o["id"] for o in sa["trade"]["theirs"]] == [it1] and sb and [o["id"] for o in sb["trade"]["mine"]] == [it1], "双方放物品：两边的 mine / theirs 对上")
    A.send(op="trade", a="item", item=99999999)
    e = A.wait(lambda m: m["ev"] == "error", 2)
    check(e and "背包" in e["msg"], "放背包里没有的物品：被网关拦下")
    A.send(op="trade", a="money", money=10 ** 9)
    e = A.wait(lambda m: m["ev"] == "error", 2)
    check(e and "钱" in e["msg"], "放超过自己的钱：被网关拦下")
    A.send(op="trade", a="lock")
    B.send(op="trade", a="lock")
    A.send(op="trade", a="confirm")
    B.send(op="trade", a="confirm")
    mA = A.wait(lambda m: m["ev"] == "me" and any(b["id"] == it1 and b["n"] == n_a1 + 1 for b in m["bag"]), 15)
    check(mA is not None, "成交后重新同步：A 的背包里 %d 从 %d 件变成 %d 件" % (it1, n_a1, n_a1 + 1))
    sa, _ = A.last("social", 1.0)
    check(sa is None or not sa["trade"], "交易会话结束")
    B.drain(1.0)

    print("\n-- 武功 / 外号 / 回收 --")
    A.send(op="kf", a="equip", slot=0, id=1000)
    A.drain(0.5)
    A.send(op="kf", a="equip", slot=15, id=1000)
    e = A.wait(lambda m: m["ev"] == "error", 2)
    check(e and "0–14" in e["msg"], "武功槽位 15：被网关拦下")
    A.send(op="kf", a="delete", ids=[1002], password="123456")
    m = A.wait(lambda m: m["ev"] == "me" and any(k["id"] == 1002 and k["lv"] == 0 for k in m["kf"]), 4)
    check(m is not None, "删武功 1002：等级清零（0x7A）")
    A.send(op="kf", a="delete", ids=[], password="x")
    e = A.wait(lambda m: m["ev"] == "error", 2)
    check(e and "无效" in e["msg"], "删武功列表为空：被网关拦下")
    A.send(op="nick", text="网关外号")
    m = A.wait(lambda m: m["ev"] == "me" and m["nickname"] == tw("网关外号"), 4)
    check(m is not None, "改外号：me.nickname = %s" % (m and m["nickname"]))
    mA = A.drain(0.3)
    cur = next((m for m in reversed(mA) if m["ev"] == "me"), None)
    A.send(op="recycle", item=it0, n=1)
    msgs = A.drain(1.5)
    note = next((m for m in msgs if m["ev"] == "notice" and "回收" in m["text"]), None)
    check(note is not None, "VIP 回收：收到「VIP玩家回收自動折算金錢…」（%s）" % ([ (m["ev"], m.get("text") or m.get("msg")) for m in msgs if m["ev"] in ("notice", "error")][-3:],))
    A.send(op="item_info", item=it0)
    note = A.wait(lambda m: m["ev"] == "notice" and "服务端物品信息" in m["text"], 3)
    check(note and "c800000000" in note["text"], "物品信息：%s" % (note and note["text"]))
    A.send(op="pw", a="zigong", password="nope")           # 不带 confirm：网关直接拦下（0x98 0D 验证成功 = 自宫，不可逆）
    err = A.wait(lambda m: m["ev"] == "error" and "确认" in m["msg"], 3)
    check(err is not None, "自宫没带 confirm：网关拦下")
    A.send(op="pw", a="zigong", password="nope", confirm=True)
    note = A.wait(lambda m: m["ev"] == "notice" and "密碼錯誤" in m["text"], 3)
    check(note is not None, "自宫（密码错）：「密碼錯誤」，不会自宫")

    print("\n-- 新账号：摇点 / 起名 / 进入 / 删除角色 --")
    N = W(port)
    N.login(S.NEWID, "wrongpw")
    e = N.wait(lambda m: m["ev"] == "error", 8)
    check(e and "密码" in e["msg"], "新账号密码错：登录被拒 %s" % (e and e["msg"]))
    N.login(S.NEWID, S.NEWPW)
    nc = N.wait(lambda m: m["ev"] == "need_create", 8)
    check(nc and 8105 in nc["births"], "新账号：收到 need_create（出生地 %s）" % (nc and nc["births"]))
    N.send(op="roll")
    r = N.wait(lambda m: m["ev"] == "roll", 4)
    check(r and len(r["attrs"]) == 7 and sum(r["attrs"]) == 140, "摇点：%s" % (r and r["attrs"]))
    N.send(op="create_name", name="游戏者之家")
    r = N.wait(lambda m: m["ev"] == "name_result", 4)
    check(r and not r["ok"], "名字被占用：name_result.ok = false")
    N.send(op="create_name", name="网关新人")
    r = N.wait(lambda m: m["ev"] == "name_result", 4)
    check(r and r["ok"], "名字可用：name_result.ok = true")
    N.send(op="create_enter", name="网关新人", map=8105, attrs=[30, 20, 20, 20, 20, 20, 30], head=1, mode=1, month=3, day=5)
    e = N.wait(lambda m: m["ev"] == "error", 2)
    check(e and "无效" in e["msg"], "属性总和 > 145：被网关拦下")
    N.send(op="create_enter", name="网关新人", map=8105, attrs=[30, 20, 20, 20, 20, 20, 15], head=1, mode=1, month=3, day=5)
    m = N.wait(lambda m: m["ev"] == "me", 12)
    check(m and m["name"] == "網關新人" or (m and m["name"].endswith("新人")), "进入世界：角色 %r 地图 %s" % (m and m["name"], m and m["f"]["map"]))
    check(m and m["f"]["map"] == 8105 and m["f"]["str"] == 30 and m["f"]["vit"] == 15, "出生地图 8105，属性 臂力 30 / 根骨 15 照着发")
    N.send(op="logout")
    N.drain(0.5)
    N.send(op="delete_role", jyid=S.NEWID, password="bad")
    e = N.wait(lambda m: m["ev"] == "error", 8)
    check(e and "服务端没有回应登录" in e["msg"], "删除角色密码错：登录就被拒（账号密码就是删除密码）%s" % (e and e["msg"]))
    N.send(op="delete_role", jyid=S.NEWID, password=S.NEWPW)
    st = N.wait(lambda m: m["ev"] == "status" and "已删除" in m["text"], 8)
    check(st is not None, "删除角色成功")
    N.login(S.NEWID, S.NEWPW)
    nc = N.wait(lambda m: m["ev"] == "need_create", 8)
    check(nc is not None, "删除后再登录：又是新账号流程")
    N.send(op="delete_role", jyid=S.NEWID, password=S.NEWPW)
    e = N.wait(lambda m: m["ev"] == "error", 3)
    check(e and "先退出" in e["msg"], "已登录时不允许删除角色")
    print("\n%d/%d 通过" % (sum(T.RES), len(T.RES)))
    return 0 if all(T.RES) else 1


if __name__ == "__main__":
    sys.exit(main())
