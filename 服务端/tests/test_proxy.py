"""抓包代理的集成测试：全部走本机回环的临时端口，不碰 6731。"""

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jyserver.codec import FrameReader, encode_c2s, encode_s2c
from tools.jyproxy import Recorder, start_proxy

ROOT = Path(__file__).resolve().parent.parent


class ProxyRoundTrip(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "cap.jsonl"

        # 假服务端：收到任何数据就回一条 S2C 帧
        self.reply = encode_s2c(0x08, bytes.fromhex("88139425860902"), wide=True)

        async def fake_server(reader, writer):
            await reader.read(65536)
            writer.write(self.reply)
            await writer.drain()
            writer.close()

        self.server = await asyncio.start_server(fake_server, "127.0.0.1", 0)
        sport = self.server.sockets[0].getsockname()[1]
        self.recorder = Recorder(self.log)
        self.proxy = await start_proxy("127.0.0.1", 0, "127.0.0.1", sport, self.recorder, quiet=True)
        self.pport = self.proxy.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        for s in (self.proxy, self.server):
            s.close()
            await s.wait_closed()
        self.recorder.close()  # Windows 上文件被占用时临时目录删不掉

    async def test_bytes_pass_through_and_are_recorded(self):
        req = encode_c2s(0x06, bytes(range(9)), key=0x7D, seq=7)
        reader, writer = await asyncio.open_connection("127.0.0.1", self.pport)
        writer.write(req)
        await writer.drain()
        got = await asyncio.wait_for(reader.read(65536), 5)
        writer.close()
        await asyncio.sleep(0.2)  # 让代理写完 close 事件

        self.assertEqual(got, self.reply)  # 透明转发
        recs = [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()]
        data = {d: b"".join(bytes.fromhex(r["hex"]) for r in recs if r.get("dir") == d) for d in ("c2s", "s2c")}
        self.assertEqual(data["c2s"], req)
        self.assertEqual(data["s2c"], self.reply)

        # 分析脚本能把录像解成帧
        out = (await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(ROOT / "tools" / "analyze_session.py"), str(self.log)],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )).stdout
        self.assertIn("0x06", out)
        self.assertIn("移动", out)
        self.assertIn("0x08", out)
        self.assertIn("设定角色位置", out)

        r = FrameReader("c2s")
        self.assertEqual(r.feed(data["c2s"])[0].seq, 7)


class DecodeHexCli(unittest.TestCase):
    def test_cli_decodes_handshake_sample(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "decode_hex.py"), "c2s",
             "f6 11 01 6a da 8f 9f a7 ae 9e 9e 69 62 9b 9e af ac ad aa ab"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
        self.assertIn("key=0x9e", out)
        self.assertIn("op=0x01", out)
        self.assertIn("登录", out)


if __name__ == "__main__":
    unittest.main()
