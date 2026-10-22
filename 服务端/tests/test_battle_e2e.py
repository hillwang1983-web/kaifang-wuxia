"""战斗联调：用网页客户端那边的 jyclient / jyfight（客户端 逆向工具/）对真正的 jyserver 跑一场完整的遭遇 → 进战 → 打怪 → 掉落 → 怪出招 → 结束。
客户端目录不在（比如部署包里）就整个跳过。"""

import asyncio
import json
import os
import sys
import time
import unittest
from pathlib import Path

CLIENT = Path(os.environ.get("JY_CLIENT_DIR") or r"C:\游戏\网金最原始文件\网金最原始文件\客户端\逆向工具")
ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless((CLIENT / "jyfight.py").exists(), "没有客户端目录")
class BattleE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        sys.path.insert(0, str(CLIENT))
        from jyserver.server import DEFAULT_DATA_DIR, GameServer
        from jyserver.state import ItemTable
        from jyserver.store import CharacterStore
        import random

        store = CharacterStore()
        for jy in (123456, 1234567):
            rows = json.loads((ROOT / "data" / "fixtures" / f"char-{jy}.json").read_text(encoding="utf-8"))["rows"]
            rows["renwu"][0].update(dangqianxue="2000", zuidaxue="2000", map="2200")
            store.put(jy, str(jy), rows)
        self.gs = GameServer(store, ItemTable.load(DEFAULT_DATA_DIR), rng=random.Random(5))
        self.server = await self.gs.serve("127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        for conn in list(self.gs.online.values()):
            conn.close()
        self.server.close()
        try:
            await asyncio.wait_for(self.server.wait_closed(), 3)
        except TimeoutError:
            pass
        self.gs.store.close()
        sys.path.remove(str(CLIENT))

    async def test_a_whole_fight_with_the_web_client_library(self):
        import jyfight as J
        from jyclient import JyClient

        c = JyClient("127.0.0.1", self.port, name="e2e")
        self.addAsyncCleanup(c.close)
        await c.connect()
        self.assertTrue(await c.login(123456))
        await c.start()
        await c.drain(0.3)
        me = c.me["fields"]["jyid"]
        f = c.fight
        await c.fight_encounter(100038166)
        await c.drain(0.3)
        self.assertTrue(f.d1 is not None and len(f.d1) == 24)
        self.assertEqual(f.ents[me].hp, 2000)
        await c.fight_enter()
        await c.drain(0.4)
        enemies = [e for e in f.ents.values() if e.team == 2]
        self.assertEqual((len(enemies), enemies[0].hp, f.ready), (1, 19000, True))
        mob = enemies[0]
        hits = 0
        while mob.alive and hits < 30:
            await c.fight_act(me, (mob.col, mob.row))
            await c.drain(0.1)
            hits += 1
        self.assertFalse(mob.alive)
        self.assertTrue(3 <= hits <= 16, hits)  # 夹具号武器强度低，十几招；有武器 / 武功的号几招
        self.assertEqual(f.judge(), J.RES_WIN)
        self.assertTrue(any(e["k"] == "pick" for e in f.events) or f.items == {})  # 掉落（有掉宝率）要么拾走要么没掉
        self.assertGreater(int(c.me["fields"]["combat_exp"]), 0)
        r = await c.fight_tick(now=time.time() + 20, delay=15)
        await c.drain(0.4)
        self.assertEqual((r, f.srv_result, f.ended_by_server), ([("end", J.RES_WIN)], 1, True))
        await c.close()

    async def test_monster_attacks_from_the_client_hurt_and_can_kill(self):
        import jyfight as J
        from jyclient import JyClient

        ch = self.gs.store.get(123456)
        ch.rows["renwu"][0]["dangqianxue"] = "40"
        self.gs.store.put(123456, ch.password, ch.rows)
        c = JyClient("127.0.0.1", self.port, name="e2e-lose")
        self.addAsyncCleanup(c.close)
        await c.connect()
        self.assertTrue(await c.login(123456))
        await c.start()
        await c.drain(0.3)
        me = c.me["fields"]["jyid"]
        f = c.fight
        await c.fight_encounter(100038166)
        await c.drain(0.3)
        await c.fight_enter()
        await c.drain(0.4)
        t = time.time() + 100
        for k in range(8):
            await c.fight_tick(now=t + k * 10, delay=999)
            await c.drain(0.2)
            if f.ents[me].hp == 0:
                break
        self.assertEqual((f.ents[me].hp, f.judge()), (0, J.RES_LOSE))
        r = await c.fight_tick(now=time.time() + 20, delay=15)
        await c.drain(0.4)
        self.assertEqual((r, f.srv_result), ([("end", J.RES_LOSE)], 2))
        await c.close()


if __name__ == "__main__":
    unittest.main()
