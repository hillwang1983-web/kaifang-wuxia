#!/usr/bin/env python3
"""网关的战斗入口测试：遭遇 → 自动进战 → 玩家出招 → 怪自动出招 → 掉落拾取 → 胜负判定 → 自动上报结算。
自起 combat_server.py（jyserver + 模拟战斗，隔离库）和网关，WebSocket 当"浏览器"。
    python test_gateway_fight.py
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402
import test_gateway_social as GS  # noqa: E402

check = T.check
HERE = os.path.dirname(os.path.abspath(__file__))


def fights(msgs):
    return [m for m in msgs if m["ev"] == "fight"]


def run(gport):
    w = GS.W(gport)
    w.send(op="fight_act", target=1)
    check(w.wait(lambda m: m["ev"] == "error", 2) is not None, "没登录就出招 → 错误提示")
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "登录成功")
    w.drain(0.5)
    w.send(op="fight_act", target=1)
    check(w.wait(lambda m: m["ev"] == "error" and "不能出招" in m["msg"], 2) is not None, "没在战斗中出招 → 被拒")
    w.send(op="fight_start", mob=0)
    check(w.wait(lambda m: m["ev"] == "error", 2) is not None, "怪物编号无效 → 被拒")
    w.send(op="fight_start", mob=38166)
    f = w.wait(lambda m: m["ev"] == "fight" and sum(1 for e in m["ents"] if e["team"] == 2 and e["hp"]) == 3 and any(e["col"] is not None for e in m["ents"]), 6)
    check(f is not None, "遭遇 → 网关自动发 E3 → 推送战场（3 只敌人有血有格）")
    if f is None:
        return
    en = [e for e in f["ents"] if e["team"] == 2]
    check(all(e["name"] == "倭寇" and e["hp"] == 19000 for e in en), "怪名取自 MOB数据.csv，血量 19000")
    check(any(e["id"] == f["me"] and e["team"] == 1 for e in f["ents"]) and f["cell"] == [24, 31], "我方实体 = 自己，进战格 (24,31)")
    w.send(op="fight_start", mob=38166)
    check(w.wait(lambda m: m["ev"] == "error" and "已经在战斗" in m["msg"], 2) is not None, "战斗中再次遭遇 → 被拒")
    # 命令栏：防禦(7) → C2S 0xDE → 服务端回 D7(cmd=7)；紧接着的第二条太快；非法命令被拒且不占间隔
    w.send(op="fight_pose", cmd=7)
    w.send(op="fight_pose", cmd=9)
    msgs = w.drain(1.0)
    evs0 = [ev for m in fights(msgs) for ev in m["events"]]
    check(any(ev["k"] == "act" and ev["cmd"] == 7 and ev["id"] == f["me"] for ev in evs0), "防禦 → 服务端转发 D7(cmd=7)")
    check(any(m["ev"] == "error" and "太快" in m["msg"] for m in msgs), "命令间隔 < 1.3 秒 → 被拒")
    time.sleep(1.4)
    w.send(op="fight_pose", cmd=2)
    check(w.wait(lambda m: m["ev"] == "error" and "命令无效" in m["msg"], 2) is not None, "非法命令号（2 不是 0xDE 命令）→ 被拒")
    w.send(op="fight_pose", cmd=9)
    msgs = w.drain(1.0)
    check(any(ev["k"] == "act" and ev["cmd"] == 9 for m in fights(msgs) for ev in m["events"]), "非法命令不占间隔：紧接着的 養精蓄銳(9) 通过")
    time.sleep(1.4)
    # 第一招；紧接着第二招太快
    w.send(op="fight_act", target=en[0]["id"])
    w.send(op="fight_act", target=en[0]["id"])
    msgs = w.drain(1.0)
    check(any(m["ev"] == "error" and "太快" in m["msg"] for m in msgs), "出招间隔 < 1.3 秒 → 被拒")
    last = fights(msgs)[-1]
    tgt = next(e for e in last["ents"] if e["id"] == en[0]["id"])
    check(tgt["hp"] == 12000, "玩家一招 → 目标 19000 → 12000")
    time.sleep(0.5)
    seen_mob_act = False
    over_seen = None
    cur = None
    evs = []
    for _ in range(40):
        w.send(op="fight_act", target=0)           # 缺省：第一只活着的怪
        time.sleep(1.4)
        msgs = w.drain(0.1)
        for m in fights(msgs):
            for ev in m["events"]:
                evs.append(ev)
                if ev["k"] == "act" and ev["id"] >= 100000000:
                    seen_mob_act = True
        if fights(msgs):
            cur = fights(msgs)[-1]
            if cur["over"] and cur["srv_result"] == 1:
                over_seen = cur
        if cur and cur["result"]:
            break
    check(seen_mob_act, "怪自动出招（网关替怪发 D7，服务端转发回来）")
    check(cur is not None and cur["result"] == 0x16 and cur["counts"][1] == 0, "敌方全灭 → 客户端判胜 0x16")
    drops = {(e["n"]) for e in evs if e["k"] == "drop"}
    picks = {(e["n"]) for e in evs if e["k"] == "pick"}
    check(len(drops) == 3 and len(picks) == 3, "三只怪各掉一件、各被拾走（%d/%d）" % (len(drops), len(picks)))
    check(cur["items"] == [], "拾取后格子清空")
    end = over_seen or w.wait(lambda m: m["ev"] == "fight" and m["over"] and m["srv_result"] == 1, 8)
    check(end is not None and end["srv_result"] == 1, "等够延迟 → 自动发 E5 → 服务端 0x81(01)，战斗结束")
    # 结束后可以再来一场
    w.drain(0.5)
    w.send(op="fight_start", mob=38268)
    f2 = w.wait(lambda m: m["ev"] == "fight" and not m["over"] and sum(1 for e in m["ents"] if e["team"] == 2 and e["hp"] == 25000) == 3, 6)
    check(f2 is not None, "第二场：野蛮人 3 只，血 25000")
    # 逃跑：C2S 0xF9（空载荷）→ S2C F9（1 字节，不改战斗状态）；00 失败、战斗继续；01 成功 → 客户端立刻自己发 E5 → 服务端 81 + E6(自己)
    w.send(op="fight_escape")
    fe = w.wait(lambda m: m["ev"] == "fight" and any(ev["k"] == "escape" for ev in m["events"]), 4)
    ev1 = [ev for ev in (fe or {"events": []})["events"] if ev["k"] == "escape"]
    check(fe is not None and ev1[-1]["ok"] is False and not fe["result"] and not fe["over"], "逃跑第 1 次：F9=00 → 逃跑失败，战斗继续")
    time.sleep(1.4)
    w.drain(0.2)
    w.send(op="fight_escape")
    end2 = w.wait(lambda m: m["ev"] == "fight" and m["over"] and m["srv_result"] == 1, 6)
    check(end2 is not None and end2["result"] == 6, "逃跑第 2 次：F9=01 → 结果码 6 → 客户端自己发 E5（不等 15 秒）→ 服务端 81 + E6 自己")
    w.drain(0.5)
    w.send(op="fight_start", mob=38268)
    f3 = w.wait(lambda m: m["ev"] == "fight" and not m["over"] and sum(1 for e in m["ents"] if e["team"] == 2 and e["hp"] == 25000) == 3, 6)
    check(f3 is not None, "逃跑后可以再开一场")
    # 战斗中直接退出：不能崩
    w.send(op="logout")
    check(w.wait(lambda m: m["ev"] == "closed", 3) is not None, "战斗中退出 → 正常关闭")
    w.send(op="fight_act", target=1)
    check(w.wait(lambda m: m["ev"] == "error", 2) is not None, "退出后出招 → 提示还没有登录")


def main():
    tmp = tempfile.mkdtemp(prefix="jygwfight-")
    db = os.path.join(tmp, "chars.sqlite")
    sp = gp = None
    try:
        T.make_copy(db, T.csv_rows("药品.csv", "ID"))
        sport, gport = T.free_port(), T.free_port()
        sp = subprocess.Popen([sys.executable, os.path.join(HERE, "combat_server.py"), "--port", str(sport), "--chars", db, "--tick", "0", "--autosave", "0"],
                              cwd=T.REPO, stdout=open(os.path.join(tmp, "srv.log"), "w"), stderr=subprocess.STDOUT, env=dict(os.environ, COMBAT_HP="69000"))
        glog = open(os.path.join(tmp, "gw.log"), "w")
        gp = subprocess.Popen([sys.executable, os.path.join(HERE, "gateway.py"), "--listen", "127.0.0.1:%d" % gport, "--server", "127.0.0.1:%d" % sport],
                              cwd=HERE, stdout=glog, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUTF8="1", JY_FIGHT_END_DELAY="1.5"))
        for port in (sport, gport):
            for _ in range(120):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
                    break
                except OSError:
                    time.sleep(0.5)
        print("战斗服务端 :%d + 网关 :%d\n" % (sport, gport))
        run(gport)
        print("\n%d/%d 通过" % (sum(T.RES), len(T.RES)))
        return 0 if all(T.RES) else 1
    finally:
        for pr in (gp, sp):
            if pr:
                pr.terminate()
                try:
                    pr.wait(5)
                except subprocess.TimeoutExpired:
                    pr.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
