#!/usr/bin/env python3
"""jyclient 的"社交 / 账号"接口测试：私聊、组队、组织、交易、武功、外号、二级密码、物品信息、VIP 回收、新建角色、删除角色。
对 网金复刻 新服务端的**隔离副本**运行（临时库，起新服务端），三个客户端 A=123456 B=1234567 C=8617293 加一个新账号 9000001。

    python client_social_test.py

预期来自 网金复刻 docs/组队.md 组织.md 丢弃回收交易.md 武功装备与删除.md 账号类指令.md 新建角色.md 钱庄.md 聊天移动与上下线广播.md
（那些文档的期望值都是对原版服务端实测过的）。
"""
import asyncio
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402
from jyclient import JyClient, from_big5, to_big5  # noqa: E402


def tw(s):
    """发出去的话在线上是 BIG5 繁体：和收到的比较要先过一遍同样的转换。"""
    return from_big5(to_big5(s))

check, texts, types = T.check, T.texts, T.types
NEWID, NEWPW = 9000001, "pw9000001"


def prepare(db):
    """复制开发库 -> 临时库：给 A / B 各塞两件有价格、可交易的物品，给 A 塞几门武功。"""
    yp = T.csv_rows("药品.csv", "ID")
    T.make_copy(db, yp)
    zb = T.csv_rows("装备数据.csv", "itemID")
    cols = list(next(iter(zb.values())).keys())
    price = next(k for k in cols if k.startswith("价格"))
    trade = cols[21] if len(cols) > 21 else None
    pick = [i for i, r in sorted(zb.items()) if int(r[price] or 0) > 0 and (trade is None or r[trade] != "0")][:2]
    con = sqlite3.connect(db)
    for jy in (123456, 1234567):
        rows = json.loads(con.execute("select rows from characters where jyid=?", (jy,)).fetchone()[0])
        for k, it in enumerate(pick):
            rows["item"].append({"id": "99100%d%d" % (jy % 10, k), "jyid": str(jy), "item_id": str(it), "state": "200", "shuliang": "2"})
        if jy == 123456:
            rows["kf"] = [{"jyid": "123456", "kf_id": str(a), "kf_lvl": str(b), "kf_exp": "0"} for a, b in ((1000, 10), (1002, 5), (3860, 10))]
        con.execute("update characters set rows=? where jyid=?", (json.dumps(rows, ensure_ascii=False), jy))
    con.commit()
    con.close()
    subprocess.run([sys.executable, "-m", "jyserver.manage", "--chars", db, "add-account", str(NEWID), NEWPW], cwd=T.REPO, check=True, capture_output=True)
    return pick, price


async def login(port, jy, name):
    c = JyClient("127.0.0.1", port, name=name)
    await c.connect()
    assert await c.login(jy), "登录没有握手 %d" % jy
    await c.start()
    await c.drain(0.4)
    return c


async def settle(*cs, q=0.5):
    await asyncio.gather(*(c.drain(q) for c in cs))


async def run(port, pick, price):
    A = await login(port, 123456, "A")
    B = await login(port, 1234567, "B")
    C = await login(port, 8617293, "C")
    ja, jb, jc = (c.me["fields"]["jyid"] for c in (A, B, C))
    for c in (A, B, C):
        await c.teleport(2801, 800 + 40 * (c is B) + 80 * (c is C), 3600)
    await settle(A, B, C, q=0.8)

    print("\n-- 私聊 / 组织聊天 --")
    await A.whisper(jb, "你好，B")
    await settle(A, B, C)
    w = [e for e in B.chat_events if e["ch"] == "whisper"]
    check(w and w[-1]["from"] == ja and w[-1]["text"] == tw("你好，B") and not [e for e in C.chat_events if e["ch"] == "whisper"], "私聊 A->B：只有 B 收到 0x04 子类型 03（%s）" % (w and w[-1]["text"]))
    await A.whisper(999999999, "没人")
    g = await A.drain(0.5)
    check(not g, "私聊不在线的人：没有任何回包")
    await A.say("公共频道")
    await settle(A, B, C)
    check(any(e["ch"] == "public" and e["text"] == tw("公共频道") for e in B.chat_events), "公共聊天 B 也能在 chat_events 里看到")

    print("\n-- 组队 --")
    await A.party_create()
    await settle(A, B, C)
    check(A.parties.get(ja) == [ja] and B.parties.get(ja) == [ja] and C.parties.get(ja) == [ja], "A 创建队伍：全服 0x2A，队伍 %s" % A.parties)
    await A.party_invite(jb)
    await settle(A, B, C)
    check(B.team_invites == [ja] and not C.team_invites, "A 邀请 B：只有 B 收 0x2E（%s）" % B.team_invites)
    await B.party_answer(ja, True)
    await settle(A, B, C)
    check(A.parties.get(ja) == [ja, jb] and B.my_party() == [ja, jb] and C.parties.get(ja) == [ja, jb] and not B.team_invites, "B 接受：全服 0x2F，队伍 [A, B]")
    await A.party_chat("队伍里说话")
    await settle(A, B, C)
    check([e["text"] for e in B.chat_events if e["ch"] == "team"] == [tw("队伍里说话")] and not [e for e in C.chat_events if e["ch"] == "team"], "队伍聊天：B 收到 0x1C，不在队的 C 没有")
    await C.party_answer(ja, False)
    g = await C.drain(0.5)
    check("對方拒絕" in "".join(texts(g, 0x1A)), "C 拒绝邀请：只有自己收「對方拒絕加入隊伍」")
    await B.party_leave()
    await settle(A, B, C)
    check(A.parties.get(ja) == [ja] and B.my_party() == [] and any("隊伍" in n[1] and "脫" in n[1] for n in A.notices), "B 离队：全服 0x2D，队里的人收「脫離隊伍」")
    await A.party_disband()
    await settle(A, B, C)
    check(not A.parties and not B.parties, "A 解散：全服 0x2B，队伍没了")

    print("\n-- 组织 --")
    await A.org_create("测试帮")
    await settle(A, B, C)
    check(A.org and A.org["name"] == "測試幫" and A.org["id"] >= 1, "A 创立组织：收 0x4F（%s）" % (A.org,))
    check(any("創立了組織" in n[1] for n in B.notices + C.notices), "全服公告「…創立了組織﹕名字」")
    await A.org_create("别的")
    g = await A.drain(0.5)
    check("已有組織" in "".join(texts(g, 0x1A)), "已有组织再创立：「已有組織﹗」")
    await B.org_recruit(ja)
    g = await B.drain(0.5)
    check(not g, "B 没有组织就招收：静默（组织号 0 时什么也不做）")
    await A.org_recruit(jb)
    await settle(A, B, C)
    check(len(B.org_invites) == 1 and B.org_invites[0]["creator"] == ja and B.org_invites[0]["org"] == A.org["id"], "A 招收 B：B 收 0x54（%s）" % (B.org_invites,))
    await B.org_join(ja)
    await settle(A, B, C)
    check(B.org and B.org["id"] == A.org["id"] and jb in A.orgs[A.org["id"]]["members"] and jb in C.orgs[A.org["id"]]["members"], "B 加入：全服 0x55，B.org = %s" % (B.org,))
    await A.org_list()
    await settle(A, B, C)
    check(len(A.org_online) == 1 and A.org_online[0] == B.me["name"], "成员列表 0xAD：在线的其他成员 %s" % (A.org_online,))
    await A.org_chat("组织频道")
    await settle(A, B, C)
    check([e["text"] for e in B.chat_events if e["ch"] == "org"] == [tw("组织频道")] and not [e for e in C.chat_events if e["ch"] == "org"], "组织聊天：只有组织成员 B 收到")
    await A.org_query_status(6)
    await settle(A, B, C)
    check(A.org_query == 5, "组织查询 06 -> 0x39 固定返回码 05")
    await A.org_kick(B.me["name"])
    await settle(A, B, C)
    check(B.org is None and jb not in A.orgs[A.org["id"]]["members"], "A 踢 B：全服 0x56，B 不再在组织里")
    await B.org_join(ja)
    await settle(A, B, C)
    await B.org_quit()
    await settle(A, B, C)
    check(B.org is None, "B 退出：全服 0x57")

    print("\n-- 交易 --")
    it0, it1 = pick
    await A.trade_request(jb)
    await settle(A, B, C)
    check(A.trade and A.trade["with"] == jb and B.trade and B.trade["with"] == ja, "A 请求交易：双方 0x1F，会话建立")
    await A.trade_put_item(it0)
    await B.trade_put_item(it1)
    await settle(A, B, C)
    check([o["id"] for o in A.trade["offers"][ja]] == [it0] and [o["id"] for o in B.trade["offers"][jb]] == [it1] and [o["id"] for o in A.trade["offers"][jb]] == [it1], "双方放物品：0x20 同步给两边 %s" % (A.trade["offers"],))
    n_a0, n_b0 = A.bag_count(it1), B.bag_count(it0)
    await A.trade_lock()
    await settle(A, B)
    check(A.trade["locked"] == [] and B.trade["locked"] == [ja], "A 锁定：只有对方 B 收 0x23 01")
    await B.trade_lock()
    await settle(A, B)
    check(A.trade["stage"] == "confirm" and B.trade["stage"] == "confirm", "第 2 次锁定：双方进入确认阶段（0x23 04）")
    await A.trade_confirm()
    await B.trade_confirm()
    await settle(A, B, C, q=0.8)
    check(A.trade is None and B.trade is None and A.trade_log and A.trade_log[-1]["end"] == "done", "第 2 次确认成交：双方 0x22，会话结束")
    # 交易没有背包刷新帧：重新登录核对真实结果
    await A.close()
    A = await login(port, 123456, "A2")
    check(A.bag_count(it1) == n_a0 + 1, "重登核对：A 的背包里多了 B 的物品 %d（%d -> %d）" % (it1, n_a0, A.bag_count(it1)))
    await A.trade_request(jb)
    await A.trade_put_item(it0)
    await settle(A, B)
    await A.trade_cancel()
    await settle(A, B)
    check(A.trade is None and B.trade is None and A.trade_log[-1]["end"] == "cancel", "取消：双方 0x23 00，会话结束")

    print("\n-- 武功 / 外号 / 密码 / 物品信息 / 回收 --")
    await A.kf_equip(0, 1000)
    g = await A.drain(0.5)
    check(A.kf_slots.get(0) == 1000 and types(g) == "6e", "装备武功 1000 到槽 0：0x6E 回显  [%s]" % types(g))
    await A.kf_equip(3, 4242)
    await settle(A, B)
    check(any("嘗試刷武功" in n[1] for n in B.notices), "装备没有的武功：全服「…嘗試刷武功﹗」公告")
    await A.kf_delete("wrongpw", [1002])
    g = await A.drain(0.5)
    check("密碼錯誤" in "".join(texts(g, 0x1A)) and not A.kf_deleted, "删武功密码错：「密碼錯誤」")
    await A.kf_delete("123456", [3860])
    g = await A.drain(0.5)
    check("轉生武功無法刪除" in "".join(texts(g, 0x1A)) and not A.kf_deleted, "删转生武功 3860：「轉生武功無法刪除﹗」")
    await A.kf_delete("123456", [1002])
    g = await A.drain(0.5)
    check(A.kf_deleted == [1002] and types(g) == "7a", "删武功 1002：0x7A 02 1002  [%s]" % types(g))
    await A.set_nickname("测试外号")
    g = await A.drain(0.6)
    check(A.nickname_result and A.nickname_result.startswith("V7Z") and "測試外號" in A.nickname_result and any("更改了外號" in n[1] for n in A.notices), "改外号：0x15 = %r，全服 0x14 公告" % A.nickname_result)
    await A.zigong("nope")            # 密码错 → 「密碼錯誤」，不会自宫（0x98 0D 密码对 = 自宫成功，不可逆）
    g = await A.drain(0.5)
    check("密碼錯誤" in "".join(texts(g, 0x1A)), "自宫（0x98 0D）密码错：「密碼錯誤」")
    await A.password_echo(0x0F, b"\x01\x02\x03\x04\x05")
    await A.drain(0.4)
    check(A.pw_result == (0x13, b"\x01\x02\x03\x04\x05"), "0x98 0F 回显 0xB8 13 + 5 字节 %s" % (A.pw_result,))
    await A.item_info(it0)
    await A.drain(0.4)
    check(A.item_infos.get(it0) == b"\xc8\x00\x00\x00\x00", "物品信息 0x71 -> 0x88 = c8 00 00 00 00")
    m0, n0 = A.me["fields"]["jy_money"], A.bag_count(it0)
    await A.recycle(it0, 1)
    g = await A.drain(0.6)
    price = int(T.csv_rows("装备数据.csv", "itemID")[it0][price_col(price)] or 0)
    check(A.bag_count(it0) == n0 - 1 and A.me["fields"]["jy_money"] == min(m0 + price, 10 ** 9) and "VIP玩家回收" in "".join(texts(g, 0x1A)),
          "VIP 回收 %d：金钱 %d -> %d（价格 %d），背包 %d -> %d  [%s]" % (it0, m0, A.me["fields"]["jy_money"], price, n0, A.bag_count(it0), types(g)))
    await A.recycle(99999999, 1)
    g = await A.drain(0.5)
    check("物品不足" in "".join(texts(g, 0x1A)), "回收没有的物品：「物品不足」")
    for c in (A, B, C):
        await c.close()

    print("\n-- 新账号：摇点 / 起名 / 进入 / 删除角色 --")
    N = JyClient("127.0.0.1", port, name="N")
    await N.connect()
    hs = await N.login(NEWID, password=NEWPW)
    check(hs is not None and N.base == 0x34, "新账号握手：种子 a2 bc 08 5f -> C2S 密钥基数 0x%02x" % (N.base or 0))
    await N.roll()
    await N.drain(0.5)
    check(N.roll_result and len(N.roll_result) == 7 and sum(N.roll_result) == 140 and all(15 <= v <= 25 for v in N.roll_result), "摇点 0x5A：%s（总和 140）" % (N.roll_result,))
    await N.create_name("游戏者之家")
    await N.drain(0.5)
    check(N.name_result == 1, "名字被占用：0x25 01（%r）" % (N.name_result,))
    await N.create_name("新人甲")
    await N.drain(0.5)
    check(N.name_result == 0, "新名字可用：0x25 00")
    await N.create_enter("新人甲", 8105, [30, 20, 20, 20, 20, 20, 15], head=1, mode=1, month=3, day=5)
    got = []
    while True:
        f = await N.wait(lambda f: True, 4)
        if f is None:
            break
        got.append(f)
        if f.type == 0xA9:
            break
    check(N.me and N.me["name"] == "新人甲" and N.me["fields"]["map"] == 8105 and any(f.type == 0x1E for f in got), "进入世界：登录序列 %d 帧，角色 %r 地图 %s 坐标 (%s,%s)" % (len(got), N.me.get("name"), N.me["fields"]["map"] if N.me else None, N.me["fields"]["x"] if N.me else None, N.me["fields"]["y"] if N.me else None))
    await N.close()
    D = JyClient("127.0.0.1", port, name="D")
    await D.connect()
    assert await D.login(NEWID, password=NEWPW)
    await D.delete_role("badpw")
    g = await D.drain(0.6)
    check("密碼錯誤" in "".join(texts(g, 0x1A)) and not D.deleted, "删除角色密码错：「密碼錯誤」")
    await D.delete_role(NEWPW)
    await D.drain(0.6)
    check(D.deleted, "删除角色：0x36 01")
    await D.close()
    E = JyClient("127.0.0.1", port, name="E")
    await E.connect()
    await E.login(NEWID, password=NEWPW)
    check(E.base == 0x34, "删除后再登录：又走新账号握手（密钥基数 0x34）")
    await E.close()
    print("\n%d/%d 通过" % (sum(T.RES), len(T.RES)))
    return 0 if all(T.RES) else 1


def price_col(name):
    return name


def main():
    tmp = tempfile.mkdtemp(prefix="jysocial-")
    db = os.path.join(tmp, "chars.sqlite")
    pr = None
    try:
        pick, price = prepare(db)
        port = T.free_port()
        pr = T.start_server(db, port)
        print("隔离服务端 127.0.0.1:%d（库 %s，物品 %s 已塞入 123456 / 1234567 的背包）" % (port, db, pick))
        return asyncio.run(run(port, pick, price))
    finally:
        if pr:
            pr.terminate()
            try:
                pr.wait(5)
            except subprocess.TimeoutExpired:
                pr.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
