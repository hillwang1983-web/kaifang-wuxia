"""loginp.exe 握手后的单字节异或密钥：由 4 字节种子算出。

key = (138*b0 + 307*b1 + 93*b2 + 78*b3 + 145) mod 217

来源与可信度
- 线性系数 138/307/93/78 和模数 217：对 FUN_009db97c / FUN_009db8b4 的逐指令解释（emu_9db97c.py），
  60 组随机种子验证为线性。仍属静态结果。
- 常数项：静态解释器给出 163(0xA3)，但真实流量(C:\\游戏\\网金复刻\\captures\\login-1.jsonl)里
    种子 a2 bc 28 37 的实际密钥是 0x7d，种子 0e ae a5 31 的实际密钥是 0x0e，
  都恰好比 163 的结果小 18，所以按实测校准为 145。只有这两个数据点支持，且没找出解释器少算 18 的原因。
"""
import sys

KEY_OFFSET = 145


def derive_key(seed: bytes) -> int:
    if len(seed) != 4:
        raise ValueError("seed must be 4 bytes")
    b0, b1, b2, b3 = seed
    return (138 * b0 + 307 * b1 + 93 * b2 + 78 * b3 + KEY_OFFSET) % 217


if __name__ == "__main__":
    for h in sys.argv[1:] or ["a2bc2837", "0eaea531", "00000000"]:
        print(h, "-> 0x%02x" % derive_key(bytes.fromhex(h)))
