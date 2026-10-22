#!/usr/bin/env python3
"""起一个新服务端的隔离副本（临时库，药已塞进 123456 的背包），前台运行直到 Ctrl+C / 被结束，退出时删除临时库。
给网关 / 页面做手工试玩用，不会碰开发库。

    python isolated_server.py --port 6734 [--tick 0]
    python gateway.py --listen 127.0.0.1:8089 --server 127.0.0.1:6734
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client_actions_test as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=6734)
ap.add_argument("--tick", default="0")
ap.add_argument("--social", action="store_true", help="同时塞好社交测试用的物品 / 武功，并加一个还没有角色的账号 9000001（密码 pw9000001）")
ap.add_argument("--combat", action="store_true", help="用 combat_server.py（jyserver + 按战斗协议文档写的模拟战斗）代替 jyserver.server")
ap.add_argument("--hp", type=int, default=0, help="把测试号 123456 / 1234567 的气血和最大气血设成这个值（隔离库里的号只有 1 点血，打不了战斗）")
a = ap.parse_args()
yp = T.csv_rows("药品.csv", "ID")
tmp = tempfile.mkdtemp(prefix="jyiso-")
db = os.path.join(tmp, "chars.sqlite")
if a.social:
    import client_social_test as S
    S.prepare(db)
    med = 0
else:
    med = T.make_copy(db, yp)
if a.hp:
    sys.path.insert(0, T.REPO)
    from jyserver.store import CharacterStore
    st = CharacterStore(db)
    for jy in (123456, 1234567):
        ch = st.get(jy)
        if ch is not None:
            ch.rows["renwu"][0].update(dangqianxue=str(a.hp), zuidaxue=str(a.hp))
            st.put(jy, ch.password, ch.rows)
    st.close()
print("隔离服务端 127.0.0.1:%d 库 %s 药 %d" % (a.port, db, med), flush=True)
if a.combat:
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "combat_server.py")]
else:
    cmd = [sys.executable, "-m", "jyserver.server"]
p = subprocess.Popen(cmd + ["--port", str(a.port), "--chars", db, "--tick", a.tick, "--autosave", "0"], cwd=T.REPO)
try:
    p.wait()
except KeyboardInterrupt:
    pass
finally:
    p.terminate()
    shutil.rmtree(tmp, ignore_errors=True)
