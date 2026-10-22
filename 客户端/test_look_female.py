#!/usr/bin/env python3
"""自己的人物外观按性别选模型：头像 5..8 建的号（服务端 sex=2）用 girl 模型（128），老号（sex=1）仍是 boy01（1）。
    python test_look_female.py
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
import test_gateway_social as GS  # noqa: E402

check = T.check
HERE = os.path.dirname(os.path.abspath(__file__))


def run(gport):
    roles = json.load(open(os.path.join(HERE, "web", "sprites", "roles.json"), encoding="utf8"))
    check("1" in roles and "128" in roles and roles["128"]["body"] == "G10000", "roles.json 里有 boy01（1）和 girl（128）两个模型")
    w = GS.W(gport)
    w.login(123456)
    me = w.wait(lambda m: m["ev"] == "me", 8)
    check(me is not None and me["look"]["model"] == 1 and me["look"]["layers"], "老号（sex=1）：男模型 1")
    w.send(op="logout")
    w.wait(lambda m: m["ev"] == "closed", 3)
    w = GS.W(gport)
    w.login(9000001, "pw9000001")
    w.wait(lambda m: m["ev"] == "need_create", 8)
    w.send(op="roll")
    r = w.wait(lambda m: m["ev"] == "roll", 4)
    w.send(op="create_name", name="女侠外观")
    w.wait(lambda m: m["ev"] == "name_result", 4)
    w.send(op="create_enter", name="女侠外观", map=3304, head=6, mode=1, month=1, day=1, attrs=r["attrs"])
    me = w.wait(lambda m: m["ev"] == "me", 10)
    check(me is not None and me["f"]["sex"] == 2, "头像 6 建的号：sex = 2")
    check(me is not None and me["look"]["model"] == 128 and any(l["l"].startswith("G1") for l in me["look"]["layers"]), "女号：女模型 128，图层是 G1…（%s）" % (me and [l["l"] for l in me["look"]["layers"]]))
    w.send(op="logout")


def main():
    tmp = tempfile.mkdtemp(prefix="jylookf-")
    db = os.path.join(tmp, "chars.sqlite")
    sp = gp = None
    try:
        S.prepare(db)
        sport, gport = T.free_port(), T.free_port()
        sp = T.start_server(db, sport)
        gp = subprocess.Popen([sys.executable, os.path.join(HERE, "gateway.py"), "--listen", "127.0.0.1:%d" % gport, "--server", "127.0.0.1:%d" % sport],
                              cwd=HERE, stdout=open(os.path.join(tmp, "gw.log"), "w"), stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUTF8="1"))
        import socket
        for _ in range(120):
            try:
                socket.create_connection(("127.0.0.1", gport), timeout=0.3).close()
                break
            except OSError:
                time.sleep(0.5)
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
