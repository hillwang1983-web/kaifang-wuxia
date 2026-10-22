#!/usr/bin/env python3
"""网页网关对**真正的 jyserver**（网金复刻，不是 combat_server 假战斗）的战斗测试：一只怪、数值由服务端定。
两场：气血足 → 打赢并结算；气血很低 → 被怪打倒、结算、之后不能再开战。
    python test_gateway_fight_real.py
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


SEEN = set()
LAST_ME = [None]


def fights(msgs):
    return [m for m in msgs if m["ev"] == "fight"]


def pump(w, secs, until=None):
    """收 secs 秒内的消息，until(fight_msg) 成立就提前返回；返回 (最后一个 fight, 所有 fight 事件, 其它消息)。"""
    end = time.time() + secs
    last, evs, other = None, [], []
    while time.time() < end:
        for m in w.drain(0.3):
            if m["ev"] == "fight":
                last = m
                evs += [e for e in m["events"] if e["n"] not in SEEN]
                SEEN.update(e["n"] for e in m["events"])
            else:
                other.append(m)
                if m["ev"] == "me":
                    LAST_ME[0] = m
        if last and until and until(last):
            break
    return last, evs, other


def win(gport):
    w = GS.W(gport)
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "登录")
    w.drain(0.5)
    w.send(op="fight_start", mob=38166)
    f = w.wait(lambda m: m["ev"] == "fight" and any(e["team"] == 2 and e["hp"] for e in m["ents"]) and any(e["col"] is not None for e in m["ents"] if e["team"] == 2), 6)
    check(f is not None, "遭遇真服务端 → 自动进战 → 推送战场")
    if f is None:
        return
    en = [e for e in f["ents"] if e["team"] == 2]
    check(len(en) == 1 and en[0]["name"] == "倭寇" and en[0]["hp"] == 19000, "只有 1 只怪（倭寇 19000），页面不依赖怪的数量")
    me_hp = next(e for e in f["ents"] if e["id"] == f["me"])["hp"]
    check(me_hp > 3000, "我方气血 %d" % me_hp)
    me_id = f["me"]
    w.send(op="fight_move", col=26, row=30)
    mv, _, _ = pump(w, 1.5, lambda m: any(e["id"] == me_id and (e["col"], e["row"]) == (26, 30) for e in m["ents"]))
    check(mv is not None and any(e["id"] == me_id and (e["col"], e["row"]) == (26, 30) for e in mv["ents"]), "战斗内移动：走到 (26,30)，服务端回显 D4，页面状态里我的格子变了")
    w.send(op="fight_move", col=en[0]["col"], row=en[0]["row"])
    check(w.wait(lambda m: m["ev"] == "error", 1) is None, "走到怪所在的格子 → 静默忽略")
    hits, last, evs = 0, f, []
    SEEN.clear()
    for _ in range(40):
        w.send(op="fight_act", target=en[0]["id"])
        hits += 1
        cur, e2, _ = pump(w, 1.5, lambda m: m["result"])
        evs += e2
        if cur:
            last = cur
        if last["result"]:
            break
    check(last["result"] == 0x16 and last["counts"][1] == 0, "打赢：客户端判 0x16（%d 招）" % hits)
    check(3 <= hits <= 25, "一场大概 %d 招" % hits)
    hurt = [e for e in evs if e["k"] == "hp" and e["id"] == f["me"] and e["delta"] > 0]
    check(len(hurt) >= 1, "怪替自己出招、玩家被打到（%d 次，共 -%d）" % (len(hurt), sum(e["delta"] for e in hurt)))
    # 等客户端 15 秒内上报：环境里把延迟缩短到 1.5 秒
    end = last if last.get("over") and last["srv_result"] == 1 else None
    if end is None:
        c, e3, _ = pump(w, 8, lambda m: m["over"] and m["srv_result"] == 1)
        end = c
    check(end is not None and end["over"] and end["srv_result"] == 1, "E5 → 服务端 0x81(01)，战斗结束")
    pump(w, 1.0)
    check(LAST_ME[0] is not None and LAST_ME[0]["f"]["combat_exp"] > 0, "实战奖励到账（combat_exp %s）" % (LAST_ME[0] or {"f": {}})["f"].get("combat_exp"))
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)


def lose(gport):
    w = GS.W(gport)
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "（低血号）登录")
    w.drain(0.5)
    w.send(op="fight_start", mob=38166)
    last, evs, other = pump(w, 25, lambda m: m["result"])
    check(last is not None and last["result"] == 0x0B, "怪的招把玩家打到 0 → 客户端判败 0x0B")
    me = next((e for e in last["ents"] if e["id"] == last["me"]), None) if last else None
    check(me is not None and me["hp"] == 0 and me["alive"] is False, "我方气血停在 0")
    c, _, _ = pump(w, 8, lambda m: m["over"] and m["srv_result"] == 2)
    check(c is not None and c["srv_result"] == 2 and c["over"], "败：E5 → 0x81(02)，战斗结束")
    pump(w, 1.0)
    check(LAST_ME[0] is not None and LAST_ME[0]["f"]["dangqianxue"] == 1, "死亡：服务端把气血记成 1（me.dangqianxue = %s）" % (LAST_ME[0] or {"f": {}})["f"].get("dangqianxue"))
    w.send(op="fight_start", mob=38166)
    f2 = w.wait(lambda m: m["ev"] == "fight" and any(e["team"] == 2 for e in m["ents"]), 6)
    check(f2 is not None, "气血 1 可以再开战")
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)


def many(gport):
    w = GS.W(gport)
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "（多只怪）登录")
    w.drain(0.5)
    w.send(op="fight_start", mob=38166, n=3)
    f = w.wait(lambda m: m["ev"] == "fight" and sum(1 for e in m["ents"] if e["team"] == 2 and e["hp"]) == 3 and all(e["col"] is not None for e in m["ents"] if e["team"] == 2), 6)
    check(f is not None, "0x30 数量 3 → 服务端出 3 只怪（实体 id 依次 +1e5）")
    if f:
        ids = sorted(e["id"] for e in f["ents"] if e["team"] == 2)
        check([b - a for a, b in zip(ids, ids[1:])] == [100000, 100000], "实体 id 依次 +1e5：%s" % ids)
        check(len({(e["col"], e["row"]) for e in f["ents"] if e["team"] == 2}) == 3, "三只站位各不相同")
        w.send(op="fight_act", target=ids[1])
        last, _, _ = pump(w, 2.0)
        tgt = next((e for e in (last or f)["ents"] if e["id"] == ids[1]), None)
        check(tgt is not None and tgt["hp"] < tgt["maxhp"], "打指定的那一只（%s 气血 %s/%s）" % (ids[1], tgt and tgt["hp"], tgt and tgt["maxhp"]))
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)


def escape(gport):
    w = GS.W(gport)
    w.login(123456)
    check(w.wait(lambda m: m["ev"] == "me", 8) is not None, "（逃跑）登录")
    w.drain(0.5)
    w.send(op="fight_start", mob=38166)
    f = w.wait(lambda m: m["ev"] == "fight" and any(e["col"] is not None for e in m["ents"] if e["team"] == 2), 6)
    check(f is not None, "遭遇真服务端 → 进战")
    if not f:
        return
    me_id = f["me"]
    w.send(op="fight_pose", cmd=7)
    d = w.wait(lambda m: m["ev"] == "fight" and any(ev["k"] == "act" and ev["cmd"] == 7 and ev["id"] == me_id for ev in m["events"]), 3)
    check(d is not None, "防禦 → C2S 0xDE → 真服务端回 D7(cmd=7)")
    oks = fails = 0
    over = None
    for i in range(15):                                     # 真服务端的 F9 是随机的（约 40% 成功）
        time.sleep(1.4)
        w.drain(0.1)
        w.send(op="fight_escape")
        m = w.wait(lambda m: m["ev"] == "fight" and any(ev["k"] == "escape" for ev in m["events"]), 3)
        if m is None:
            continue
        last = [ev for ev in m["events"] if ev["k"] == "escape"][-1]
        if last["ok"]:
            oks += 1
            over = w.wait(lambda m: m["ev"] == "fight" and m["over"], 6)
            break
        fails += 1
        check(not m["result"] and not m["over"], "F9=00：战斗继续（第 %d 次失败）" % fails) if fails == 1 else None
    check(oks == 1, "逃跑最终成功（失败 %d 次）" % fails)
    check(over is not None and over["result"] == 6 and over["srv_result"] == 1, "F9=01 → 客户端自己发 E5 → 服务端 81(01)，战斗结束，结果码 6")
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)


def with_stack(hp, fn):
    tmp = tempfile.mkdtemp(prefix="jygwreal-")
    db = os.path.join(tmp, "chars.sqlite")
    sp = gp = None
    try:
        T.make_copy(db, T.csv_rows("药品.csv", "ID"))
        sys.path.insert(0, T.REPO)
        from jyserver.store import CharacterStore
        st = CharacterStore(db)
        for jy in (123456, 1234567):
            ch = st.get(jy)
            ch.rows["renwu"][0].update(dangqianxue=str(hp), zuidaxue=str(hp))
            st.put(jy, ch.password, ch.rows)
        st.close()
        sport, gport = T.free_port(), T.free_port()
        sp = T.start_server(db, sport)
        gp = subprocess.Popen([sys.executable, os.path.join(HERE, "gateway.py"), "--listen", "127.0.0.1:%d" % gport, "--server", "127.0.0.1:%d" % sport],
                              cwd=HERE, stdout=open(os.path.join(tmp, "gw.log"), "w"), stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUTF8="1", JY_FIGHT_END_DELAY="1.5"))
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", gport), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.5)
        print("真 jyserver :%d（气血 %d）+ 网关 :%d" % (sport, hp, gport))
        fn(gport)
    finally:
        for pr in (gp, sp):
            if pr:
                pr.terminate()
                try:
                    pr.wait(5)
                except subprocess.TimeoutExpired:
                    pr.kill()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    with_stack(30000, win)
    with_stack(60, lose)
    with_stack(30000, many)
    with_stack(30000, escape)
    print("\n%d/%d 通过" % (sum(T.RES), len(T.RES)))
    return 0 if all(T.RES) else 1


if __name__ == "__main__":
    sys.exit(main())
