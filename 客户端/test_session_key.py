#!/usr/bin/env python3
"""session_key_emu.py 的回归：固定种子 -> 固定的会话状态和校验字节（值取自对原版客户端代码的模拟运行，再用手算核对过）。
需要 unicorn 和原版 loginp.exe；缺任何一个就整体跳过。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import unicorn  # noqa: F401
    import session_key_emu as S
    if not os.path.isfile(S.EXE):
        raise ImportError(S.EXE)
except ImportError as e:
    print("SKIP 缺 unicorn 或 loginp.exe（%s）" % e)
    sys.exit(0)

ok = bad = 0


def check(c, msg):
    global ok, bad
    if c:
        ok += 1
        print("PASS", msg)
    else:
        bad += 1
        print("FAIL", msg)


s1 = S.SessionKey(bytes([1, 2, 3, 4]))
check(s1.modulus == 8 and s1.second == 11, "种子 01020304：M = (1+2+3+4)%5+8 = 8，第二参数 = 10%54+1 = 11")
d = s1.doubles()
check(d["D[20524e8]"] == 3766.0 and d["D[2518]"] == 3692.0 and d["S[252c]"] == 3359.0, "种子 01020304：调度出的双精度全局 3766 / 3692 / 3359")
check(s1.provider(2) == 3692 % 217, "k=2（P2）= trunc(D[2518]) % 217")

s2 = S.SessionKey(bytes.fromhex("a2bc2837"))
check(s2.modulus == 8, "种子 a2bc2837：M = (162+188+40+55) %5 + 8 = 8")
d2 = s2.doubles()
check(d2["D[2518]"] == 246156.0 and s2.provider(2) == 246156 % 217 == 78, "种子 a2bc2837：P2 = 78（手算一致）")
check(s2.provider(6) == 125, "种子 a2bc2837：P6 = (trunc(Real48 88281.0)+0xa3) % 217 = 125")
check(s2.k_for_e3(8617293, 24, 31, 1) == 6 and s2.e3_tail(8617293, 24, 31, 1) == 125, "E3 (24,31) 朝向 1：k = 6 → 校验字节 0x7d")
try:
    s2.provider(1)
    check(False, "k=1 没给 g2 应该报错")
except ValueError:
    check(True, "k=1 没给 g2 → 明确报错（不返回错误的值）")

print("\n%d/%d 通过" % (ok, ok + bad))
sys.exit(1 if bad else 0)
