#!/usr/bin/env python3
"""任务进度：标记名拆分 / 分组（gateway.Items）+ 对隔离的新服务端触发事件，看标记进 me.quests、不再混进背包。
需要服务端 data\\标记.csv（开发机读原版服务端 data；缺就跳过数据相关项）。"""
import asyncio
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gateway as G  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def unit():
    sp = G.Items.split_marker
    check(sp("风月夷光一A退青") == ("风月夷光", "一A", "退青"), "拆分：风月夷光一A退青 → 任务 / 一A / 退青")
    check(sp("五行掌A触发") == ("五行掌", "A", "触发"), "拆分：五行掌A触发（没有汉字序号）")
    check(sp("日月A01探访") == ("日月", "A01", "探访"), "拆分：步骤号可以是 A01")
    check(sp("老妇1A通知菲青") == ("老妇", "1A", "通知菲青"), "拆分：1A 通知…")
    check(sp("杨家枪2-巧遇") == ("杨家枪", "2", "巧遇"), "拆分：去掉说明前面的 -")
    check(sp("学葵花") == ("其它", "", "学葵花"), "没有 ASCII 步骤号的名字放进「其它」")
    check(sp("A标记") == ("其它", "", "A标记"), "任务名不足 2 个字的放进「其它」")
    data_dir = G.DEFAULT_ITEM_DIR
    if not os.path.isfile(os.path.join(data_dir, "标记.csv")):
        print("SKIP 没有 标记.csv（%s）" % data_dir)
        return None
    it = G.Items(data_dir)
    check(len(it.markers) > 6000, "标记.csv 载入 %d 条" % len(it.markers))
    check(it.is_marker(33369) and not it.is_marker(12020) and it.name(33369).startswith("標記·风月夷光"), "33369 是标记、12020（玄铁重剑）不是；标记名带前缀")
    check(not (set(it.markers) & set(it.names)), "标记 id 和装备 / 药品 id 不重合")
    qv = it.quest_view({33369: 1, 33370: 2, 12020: 1})
    check(qv == [{"quest": "风月夷光", "steps": [{"id": 33369, "step": "一A", "what": "退青", "n": 1, "name": "风月夷光一A退青"},
                                              {"id": 33370, "step": "一B", "what": "跳赢", "n": 2, "name": "风月夷光一B跳赢"}]}], "quest_view：只收标记、按任务分组、步骤按 id 排")
    return it


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def integ(it):
    sys.path.insert(0, os.path.join(HERE))
    from jyclient import JyClient
    port = free_port()
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "isolated_server.py"), "--port", str(port)], cwd=HERE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, PYTHONUTF8="1"))
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        c = JyClient("127.0.0.1", port, name="quest")
        await c.connect()
        assert await c.login(123456)
        await c.start()
        await c.drain(0.6, 3)
        await c.teleport(2801, 800, 3600)
        await c.drain(0.8)
        t = c.game_time()
        check(isinstance(t, int) and t >= 0 and c.clock is not None, "登录后有游戏时钟（0x1E 开头的计数）：%s" % t)
        gw = G.Gateway("127.0.0.1", port, it)
        before = gw.view_me(c)
        check(before["clock"] == c.game_time(), "me 里带游戏时钟（页面 HUD 显示日期时辰用）")
        check(before["f"]["map"] == c.map_id == 2801 and (before["f"]["x"], before["f"]["y"]) == c.pos, "me 里的位置是传送后的最新位置（以前是登录时的快照，背包一变页面就被拉回登录的地图）：%s %s" % (before["f"]["map"], c.pos))
        n0 = sum(len(g["steps"]) for g in before["quests"])
        await c.event(53)                      # 2801 事件 53 = 物品:40354:1;标记:51238:1;属:名声:5;属:历练:5
        await c.drain(1.0)
        after = gw.view_me(c)
        steps = [s for g in after["quests"] for s in g["steps"]]
        mk = next((s for s in steps if s["id"] == 51238), None)
        check(mk is not None and sum(len(g["steps"]) for g in after["quests"]) == n0 + 1, "事件 53 之后：标记 51238 出现在 me.quests（%s）" % (mk and mk["name"]))
        check(all(b["id"] != 51238 for b in after["bag"]) and any(b["id"] == 40354 for b in after["bag"]), "标记不混进背包列表；物品 40354 还在背包里")
        check(it.name(51238).startswith("標記·"), "标记名可读：%s" % it.name(51238))
        await c.close()
    finally:
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()


def main():
    it = unit()
    if it is not None:
        asyncio.run(integ(it))
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
