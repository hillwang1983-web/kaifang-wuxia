#!/usr/bin/env python3
"""jyclient 的动作封装测试：穿 / 脱装备、用药、商店（开店 / 购买），对 网金复刻 新服务端的**隔离副本**运行。

默认自己起服务端：把 C:\\游戏\\网金复刻\\data\\chars.sqlite 复制到临时目录，往测试号 123456 的背包里塞几种药，
在空闲端口起 `python -m jyserver.server --tick 0 --autosave 0`，测完关掉并删除临时库——所以不会改动开发库，也可重复运行。
  python client_actions_test.py                # 自起隔离服务端
  python client_actions_test.py --port 6732    # 直接连已有服务端（会改它的库，不推荐）

预期来自 网金复刻 docs/装备与物品.md、药品效果.md、商店.md（对原版服务端实测并逐包对照过）。
"""
import argparse
import asyncio
import csv
import json
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient, SLOT_NAME, from_big5  # noqa: E402

REPO = r"C:\游戏\网金复刻"
DATA = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data"
RES = []


def check(c, m):
    RES.append(bool(c))
    print(("PASS " if c else "FAIL ") + m)


def csv_rows(name, key):
    with open(os.path.join(DATA, name), encoding="gbk", errors="replace", newline="") as f:
        return {int(r[key]): r for r in csv.DictReader(f)}


def texts(frames, t):
    return [from_big5(f.payload[1:]) for f in frames if f.type == t]


def types(frames):
    return " ".join("%02x" % f.type for f in frames)


def s7b(frames):
    """0x7B -> {子类型: 新值}（按先后，保留重复）。"""
    return [(f.payload[0], struct.unpack_from("<I", f.payload, 2)[0]) for f in frames if f.type == 0x7B]


# ------------------------------------------------------------ 隔离服务端
def pick_meds(yp):
    """药品表里只有 精/气/神/内 效果、没有任何 max 和其它效果的药（每类各一）。"""
    other = [k for k in next(iter(yp.values())).keys() if k not in ("ID", "名称", "耐久", "重量", "价格", "精", "气", "神", "内")]
    simple = [r for r in yp.values() if all(r[k] in ("0", "") for k in other) and any(int(r[k] or 0) for k in ("精", "气", "神", "内"))]
    qi = next(r for r in simple if int(r["气"] or 0) > 0 and int(r["精"] or 0) == 0 and int(r["神"] or 0) == 0 and int(r["内"] or 0) == 0)
    return qi


def make_copy(dst, yp):
    src = os.path.join(REPO, "data", "chars.sqlite")
    shutil.copy(src, dst)
    db = sqlite3.connect(dst)
    rows = json.loads(db.execute("select rows from characters where jyid=123456").fetchone()[0])
    med = pick_meds(yp)
    mid = int(med["ID"])
    rows["item"].append({"id": "990000001", "jyid": "123456", "item_id": str(mid), "state": "200", "shuliang": "3"})
    db.execute("update characters set rows=? where jyid=123456", (json.dumps(rows, ensure_ascii=False),))
    # 给 1234567 穿上 Item3.Dat 里有外观码的装备（头盔 mb / 衣 pb / 武器 wd），让别人看到的外观有层可画
    r2 = json.loads(db.execute("select rows from characters where jyid=1234567").fetchone()[0])
    if r2.get("renwu"):
        import gateway
        L = gateway.Looks(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "share", "dat", "Item3.Dat"))
        pick = lambda lo, hi, pre: next(i for i, (a, b) in sorted(L.table.items()) if lo <= i < hi and b.startswith(pre))
        for col, val in (("toukui", pick(16000, 18000, "mb")), ("yifu", pick(18000, 20000, "pb")), ("wuqi", pick(2000, 8000, "wd"))):
            r2["renwu"][0][col] = str(val)
        db.execute("update characters set rows=? where jyid=1234567", (json.dumps(r2, ensure_ascii=False),))
    db.commit()
    db.close()
    return mid


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server(db, port):
    out = open(os.path.join(os.path.dirname(db), "server.log"), "w")
    pr = subprocess.Popen([sys.executable, "-m", "jyserver.server", "--port", str(port), "--chars", db, "--tick", "0", "--autosave", "0"],
                          cwd=REPO, stdout=out, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            return pr
        except OSError:
            time.sleep(0.25)
    pr.kill()
    raise SystemExit("隔离服务端没起来，见 " + out.name)


# ------------------------------------------------------------ 测试
async def run(host, port, med_id, yp, zb):
    c = JyClient(host, port, name="act", log="client_actions.jsonl")
    await c.connect()
    assert await c.login(123456), "登录没有握手"
    await c.start()
    await c.drain(0.5)
    F = c.me["fields"]
    jy = F["jyid"]
    print("角色 %s：金钱 %d，背包 %d 件，血 %d/%d" % (c.me["name"], F["jy_money"], c.bag_count(), F["dangqianxue"], F["zuidaxue"]))

    # ---------------- 装备
    print("\n-- 装备 --")
    shoe = c.me["equip"]["xiezi"][0]
    sid, sst = shoe["item_id"], shoe["zhuangtai"]
    z = zb[sid]
    before = (F["wuqiqiangdu"], F["fangjuqiangdu"])
    bag_before = c.bag_count()
    await c.unequip(9)
    g = await c.drain(0.6)
    f18 = [f for f in g if f.type == 0x18]
    check(f18 and struct.unpack_from("<IB", f18[0].payload) == (jy, 9), "脱鞋子(槽位 9)：0x18 = jyid + 槽位  [%s]" % types(g))
    check(c.me["equip"]["xiezi"][0]["item_id"] == 0, "本地状态：鞋子槽已空")
    want = []
    if int(z["攻击"]):
        want.append((0x2F, before[0] - int(z["攻击"])))
    if int(z["防御"]):
        want.append((0x30, before[1] - int(z["防御"])))
    check(s7b(g) == want, "脱下 %s（攻 %s 防 %s）后 0x7B 强度更新 %s" % (z["itenae"], z["攻击"], z["防御"], [("%02x" % a, b) for a, b in s7b(g)]))
    check(c.bag_count() == bag_before, "脱装备不改背包（%d 件）" % bag_before)

    await c.unequip(9)
    g = await c.drain(0.5)
    check(any(f.type == 0x18 for f in g), "对空槽位再脱：照样回 0x18（原版行为）")

    await c.equip(9, 99999999, 200)
    g = await c.drain(0.6)
    t14 = texts([f for f in g if f.payload[:1] == b"\x0e"], 0x14)
    check(t14 and "刷裝備" in t14[0] and not any(f.type == 0x17 for f in g), "背包里没有的物品：广播「嘗試刷裝備」且不穿 %s" % t14)

    await c.equip(9, sid, sst)
    g = await c.drain(0.6)
    f17 = [f for f in g if f.type == 0x17]
    check(f17 and struct.unpack_from("<IBIB", f17[0].payload) == (jy, 9, sid, sst), "穿回 %s：0x17 = jyid 槽位 物品ID 状态 [%s]" % (z["itenae"], types(g)))
    check(s7b(g) == [(a, b + (int(z["攻击"]) if a == 0x2F else int(z["防御"]))) for a, b in want], "穿上后强度恢复 %s" % [("%02x" % a, b) for a, b in s7b(g)])
    check((c.me["fields"]["wuqiqiangdu"], c.me["fields"]["fangjuqiangdu"]) == before, "本地强度回到 %s" % (before,))

    await c.equip(9, 24076, 200)       # 钻石项炼，在背包里；鞋子槽已有装备 -> 静默忽略
    g = await c.drain(0.6)
    check(not g, "槽位上已有装备：静默忽略（没有任何回包）")
    for bad in (0, 5, 10, 11):
        await c.equip(bad, 24076, 200)
        await c.unequip(bad)
    g = await c.drain(0.6)
    check(not g, "无效槽位 0/5/10/11 的穿和脱：原版都不回包")

    # ---------------- 用药
    print("\n-- 用药 --")
    med = yp[med_id]
    gain = int(med["气"])
    cur, mx = c.me["fields"]["dangqianxue"], c.me["fields"]["zuidaxue"]
    n0 = c.bag_count(med_id)
    await c.use_item(med_id)
    g = await c.drain(0.6)
    exp = min(cur + gain, mx)
    check(s7b(g) == [(0x18, exp)], "使用 %s（气 +%d）：0x7B 18 = min(%d+%d, %d) = %d  [%s]" % (med["名称"], gain, cur, gain, mx, exp, types(g)))
    f0b = [f for f in g if f.type == 0x0B]
    check(f0b and struct.unpack_from("<I", f0b[0].payload)[0] == med_id and f0b[0].payload[5] == 1 and g[-1].type == 0x0B,
          "最后回 0x0B 确认 = 物品ID + 耐久 + 01")
    check(c.bag_count(med_id) == n0 - 1 and c.me["fields"]["dangqianxue"] == exp, "本地：背包 %d→%d 件，血 %d" % (n0, n0 - 1, c.me["fields"]["dangqianxue"]))
    await c.use_item(med_id)
    await c.drain(0.6)
    await c.use_item(med_id)
    await c.drain(0.6)
    check(c.bag_count(med_id) == 0, "用完 3 件，背包里没有了")
    await c.use_item(med_id)
    g = await c.drain(0.8)
    check("物品不足" in "".join(texts([f for f in g if f.payload[:1] == b"\x64"], 0x1A)) and any(f.type == 0x05 for f in g)
          and "背包沒有此物品" in "".join(texts(g, 0x14)), "背包没有该药：0x1A「物品不足」+ 0x05 + 0x14「背包沒有此物品」 [%s]" % types(g))

    # ---------------- 商店
    print("\n-- 商店 --")
    await c.shop_open(53)
    g = await c.drain(0.8)
    check(types(g) == "1a 09 1b 1b", "开店 53（京城药店）：1a 09 1b 1b  [%s]" % types(g))
    check("批量購買" in "".join(texts(g, 0x1A)), "提示「批量購買，需重登后顯示﹗」")
    check(c.shop and len(c.shop["items"]) > 5 and all(i["id"] in zb or i["id"] in yp for i in c.shop["items"]), "商品列表 %d 件，物品ID 都在物品表里" % len(c.shop["items"]))
    await c.shop_open(60000)
    g = await c.drain(0.6)
    check("沒錄入" in "".join(texts(g, 0x1A)), "不认识的商人：「此商人沒錄入，通知GM﹗」 [%s]" % types(g))

    buyable = next(i for i, r in zb.items() if r["商品"] == "1" and i not in (sid,))
    banned = next(i for i, r in zb.items() if r["商品"] == "0")
    money, n0 = c.me["fields"]["jy_money"], c.bag_count(buyable)
    await c.buy([(buyable, 7)])
    g = await c.drain(0.8)
    check(types(g) == "7b 0a 1b 1a", "购买 %s ×7：回包顺序 7b 0a 1b 1a  [%s]" % (zb[buyable]["itenae"], types(g)))
    check(s7b(g) == [(0x3C, money - 7)], "金钱 %d → %d（原版单价恒为 1，按数量扣）" % (money, money - 7))
    check("購買成功" in "".join(texts(g, 0x1A)), "提示「購買成功﹗」")
    check(c.bag_count(buyable) == n0 + 1, "背包只加 1 件（原版怪规则）：%d → %d" % (n0, c.bag_count(buyable)))
    money2 = c.me["fields"]["jy_money"]
    await c.buy([(banned, 1)])
    g = await c.drain(0.8)
    check("不允許購買" in "".join(texts(g, 0x1A)) and not s7b(g) and c.me["fields"]["jy_money"] == money2,
          "「商品」列=0 的 %s：整包拒绝，不扣钱 [%s]" % (zb[banned]["itenae"], types(g)))
    await c.buy([(buyable, 1), (banned, 1)])
    g = await c.drain(0.8)
    check("不允許購買" in "".join(texts(g, 0x1A)) and c.me["fields"]["jy_money"] == money2, "混合购买里有一件不合格：整包不处理")
    await c.buy([(buyable, money2 + 1)])
    g = await c.drain(0.8)
    check("錢不夠" in "".join(texts(g, 0x1A)) and c.me["fields"]["jy_money"] == money2, "钱不够：「錢不夠﹗」，不扣钱 [%s]" % types(g))
    # ---------------- 钱庄 / 丢弃 / 文字指令
    print("\n-- 钱庄 / 丢弃 / 指令 --")
    have = c.bag_count(buyable)
    check(have >= 1, "前面买到的 %s 在背包里（%d 件）" % (zb[buyable]["itenae"], have))
    await c.bank_open()
    g = await c.drain(0.6)
    check(types(g) == "28" and c.bank == [], "打开钱庄：0x28，清单为空  [%s]" % types(g))
    await c.bank_put(buyable, 1)
    g = await c.drain(0.6)
    check(types(g) == "0b 77 27" and c.bag_count(buyable) == have - 1 and c.bank and c.bank[0]["id"] == buyable and c.bank[0]["n"] == 1,
          "存 1 件：0b 77 27；背包 %d→%d，钱庄 %s（48015 的固定帧不入账）" % (have, c.bag_count(buyable), c.bank))
    await c.bank_put(buyable, 5)
    g = await c.drain(0.6)
    check("物品數量不足" in "".join(texts(g, 0x1A)) and c.bag_count(buyable) == have - 1, "存超量：「物品數量不足，請重登﹗」背包不变  [%s]" % types(g))
    await c.bank_get(buyable, 1)
    g = await c.drain(0.6)
    check(types(g) == "0b 77 27 28" and c.bag_count(buyable) == have and c.bank == [], "取 1 件：0b 77 27 28；背包回到 %d，钱庄清空" % have)
    await c.bank_get(buyable, 1)
    g = await c.drain(0.6)
    check("數量不足" in "".join(texts(g, 0x1A)) and c.bag_count(buyable) == have, "取不存在的：「數量不足」  [%s]" % types(g))
    await c.discard(buyable, 1)
    g = await c.drain(0.6)
    check(not g and c.bag_count(buyable) == have - 1 and len(c.ground) == 1 and c.ground[0]["id"] == buyable, "丢 1 件：自己什么也收不到，背包 %d→%d，记一条地上物品" % (have, have - 1))
    await c.pickup(buyable, 1)
    g = await c.drain(0.6)
    check(types(g) == "10" and c.bag_count(buyable) == have and not c.ground, "捡回来：0x10，背包加 1 件，地上清空  [%s]" % types(g))
    await c.discard(99999999, 1)
    g = await c.drain(0.6)
    check("物品不足" in "".join(texts(g, 0x1A)), "丢背包里没有的：「物品不足」  [%s]" % types(g))
    await c.command("@where")
    g = await c.drain(0.6)
    check(any(f.type == 0x04 for f in g), "@where：收到一行聊天回复  [%s]" % types(g))

    # ---------------- 事件（0x6B）：2801 号图的事件 53 = 物品:40354:1;标记:51238:1;属:名声:5;属:历练:5（无前置条件）
    print("\n-- 事件 --")
    await c.teleport(2801, 800, 3600)
    await c.drain(0.8)
    fame, exp, n_it, n_mk = F["fame_val"], F["exp_val"], c.bag_count(40354), c.bag_count(51238)
    await c.event(53)
    g = await c.drain(1.0)
    check(types(g).split()[-1] == "7d" and struct.unpack_from("<H", g[-1].payload, 0)[0] == 53, "事件 53：回包以 0x7D（事件 id 53）结尾  [%s]" % types(g))
    check(c.bag_count(40354) == n_it + 1 and c.bag_count(51238) == n_mk + 1, "本地背包：物品 40354 与标记 51238 各 +1（0x77 折进状态）")
    check(F["fame_val"] == fame + 5 and F["exp_val"] == exp + 5, "名声 %d → %d，历练 %d → %d（0x7B 折进状态）" % (fame, F["fame_val"], exp, F["exp_val"]))
    check("得到物品" in "".join(texts(g, 0x14)) and "得到標記" in "".join(texts(g, 0x14)), "提示「得到物品﹕…」「得到標記﹕…」")
    await c.event(32)           # 标记:53327:-1;标记:53328:1：身上没有 53327 -> 中止，不改库
    g = await c.drain(0.8)
    check("缺少標記" in "".join(texts(g, 0x14)) and c.bag_count(53328) == 0, "事件 32 缺标记：「缺少標記﹕53327」，不加 53328  [%s]" % types(g))
    await c.close()
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = 自起隔离服务端")
    a = ap.parse_args()
    yp, zb = csv_rows("药品.csv", "ID"), csv_rows("装备数据.csv", "itemID")
    tmp = pr = None
    try:
        if a.port:
            med = int(pick_meds(yp)["ID"])
            print("警告：直连已有服务端 %s:%d，测试会改它的库；药品测试需要背包里有 3 件 %d" % (a.host, a.port, med))
            port = a.port
        else:
            tmp = tempfile.mkdtemp(prefix="jytest-")
            db = os.path.join(tmp, "chars.sqlite")
            med = make_copy(db, yp)
            port = free_port()
            pr = start_server(db, port)
            print("隔离服务端 127.0.0.1:%d（库 %s，药 %d 已塞入 123456 的背包）\n" % (port, db, med))
        return asyncio.run(run(a.host, port, med, yp, zb))
    finally:
        if pr:
            pr.terminate()
            try:
                pr.wait(5)
            except subprocess.TimeoutExpired:
                pr.kill()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
