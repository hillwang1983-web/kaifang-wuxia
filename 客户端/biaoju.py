#!/usr/bin/env python3
"""鏢局（託鏢）相关的包：把「打工物品」（镖局的包裹 / 运镖车 …）托给别的玩家，对方在鏢局里查看存放。

全部来自 loginp.exe 静态逆向 + 对原版服务端 6731 实测（2026-10-20，两个测试号互相託鏢）：

  C2S 0x3D 託鏢   名字长度(1) 名字(BIG5) 物品ID低16位(LE16) 物品ID高16位(LE16) 耐久(1，原始字节) 数量(1，原始字节)
                  客户端是把"相同的连续几件"合成一包发（耐久相同的算一组，数量 = 件数）；成功：自己收 1A 0E「託鏢成功」，
                  对方收 1A 64「<託鏢人名字>　鏢給你」。耐久必须和背包里那件一致（用 @wp 加的件耐久是物品表里的值），
                  只认"打工物品"（见 JOB_ITEM_RANGES），别的物品回 1A 64「物品數量不足，請重登﹗」。
  C2S 0x3E 查存放 无载荷；没有 → 1A 10「您沒有任何物品」；有 → S2C 0x49（见 parse_49）。
  S2C 0x49        [名字长度(1) 名字(BIG5) 物品ID低16位(LE16) 高16位(LE16) 耐久(1)] × N（託鏢人名字 + 物品）
  C2S 0x40 <子号> 查询鏢局的工作列表 / 价格：回 S2C 0x4D（见 parse_4d；子号 0..3 实测都回 4D 04 <LE32 5000>，语义没细查）。
  S2C 0x3F        邮件 / 鏢局到达提示：LE32 值 + 1 字节；值 == 1 亿 = "系统寄信给你"，> 1 亿 = 玩家 (值 − 1 亿) 寄信给你，
                  第 5 字节 0xFA = 让客户端发 C2S 24 15，0xFF = 对方信箱已满（原版客户端 0x62d704，服务端没有邮件表，没验证）。
  C2S 0x3F 取鏢   校验字节(1) + 要取的行号（每个 1 字节，行号从 1 起，按 0x49 清单的顺序；填 0xFF / 0x00 的会被忽略）。
                  校验字节 = 会话"提供者"(k)，k = (行号字节数 + 0x2A6) % M + 1，M = (握手 / 换密钥种子 4 字节之和) % 5 + 8
                  （0x9cc8d0；提供者算法见 session_key_emu.py，k = 2 / 6 不依赖玩家数据，所以把行号字节数补到让 k 落在 2 / 6 上）。
                  成功：S2C 0x4B（每件 id 低 16 / 高 16 / 耐久，共 5 字节）+ 1A「您已成功領取物品」，物品进背包，存放清单对应行被删。
                  校验不对：全服公告 14 0E「<名字>押鏢刷錢﹗武功隨机降一級﹗」（会真的降武功，别乱试）。
  C2S 0x41 交鏢   `id低16 id高16 耐久 LE32(计数) 校验字节`：交付随身携带的押镖物品（有进行中的押镖 + 到时间才行，
                  否则同样当刷钱处理并公告）；k = ((id低16 + 计数) % M) + 1，计数每发一次加 Random(5)+1。押镖开始的流程没解，没实现。
"""
import struct

# 客户端判断"打工物品"的 id 区间（0x6b0610 里那串 sub / jb），闭开区间 [lo, hi)
JOB_ITEM_RANGES = (
    (0xB799, 0xB799 + 0x48),            # 47001..47072 镖局的包裹 / 运镖车 …
    (0xB799 + 0x54, 0xB799 + 0x54 + 0x36),
    (0xB799 + 0x92, 0xB799 + 0x92 + 0x0F),
    (0xB799 + 0xA2, 0xB799 + 0xA3),
    (0xC74B, 0xC74B + 0x24),
    (0xC74B + 0xB9, 0xC74B + 0xB9 + 6),
    (0xC74B + 0x108, 0xC74B + 0x108 + 0x26),
    (0xC74B + 0x1E2, 0xC74B + 0x1E3),
)


def is_job_item(item_id: int) -> bool:
    return any(lo <= item_id < hi for lo, hi in JOB_ITEM_RANGES)


def build_send(name_big5: bytes, item_id: int, dur: int, count: int = 1) -> bytes:
    """C2S 0x3D 的载荷。"""
    if not 1 <= len(name_big5) <= 255 or not 0 <= dur <= 255 or not 1 <= count <= 255:
        raise ValueError("名字长度 / 耐久 / 数量超范围")
    return bytes([len(name_big5)]) + name_big5 + struct.pack("<HH", item_id & 0xFFFF, (item_id >> 16) & 0xFFFF) + bytes([dur, count])


def parse_49(p: bytes, from_big5):
    """S2C 0x49 -> [{"from": 名字, "item_id", "dur"}]"""
    out, o = [], 0
    while o < len(p):
        n = p[o]
        if o + 1 + n + 5 > len(p):
            break
        name = from_big5(p[o + 1:o + 1 + n])
        lo, hi = struct.unpack_from("<HH", p, o + 1 + n)
        out.append({"from": name, "item_id": lo | (hi << 16), "dur": p[o + 1 + n + 4]})
        o += 1 + n + 5
    return out


PAD = 0xFF            # 取鏢行号列表里的填充字节（服务端忽略）
SAFE_K = (2, 6)       # 不依赖玩家数据的校验提供者下标


def modulus(seed: bytes) -> int:
    """M = (种子 4 字节之和) % 5 + 8（8..12）"""
    return sum(seed[:4]) % 5 + 8


def claim_k(n_bytes: int, m: int) -> int:
    """C2S 0x3F 的校验提供者下标：(行号字节数 + 0x2A6) % M + 1"""
    return (n_bytes + 0x2A6) % m + 1


def build_claim(rows, seed: bytes, provider):
    """C2S 0x3F 的载荷：校验字节 + 行号（1 起；不够长度的补 0xFF 让下标落在 SAFE_K 上）。provider(k) -> 校验字节。"""
    rows = [int(r) for r in rows]
    if not rows or any(not 1 <= r <= 254 for r in rows):
        raise ValueError("行号要 1..254")
    m = modulus(seed)
    body = bytes(rows)
    for extra in range(0, 4 * m):
        if claim_k(len(body) + extra, m) in SAFE_K:
            body += bytes([PAD]) * extra
            break
    else:
        raise ValueError("凑不出可算的校验下标")
    return bytes([provider(claim_k(len(body), m)) & 0xFF]) + body


def parse_4b(p: bytes):
    """S2C 0x4B（取鏢成功送来的物品）-> [{"item_id", "dur"}]：每件 5 字节 = id 低 16 / 高 16 / 耐久"""
    out = []
    for o in range(0, len(p) - 4, 5):
        lo, hi = struct.unpack_from("<HH", p, o)
        out.append({"item_id": lo | (hi << 16), "dur": p[o + 4]})
    return out


def parse_4d(p: bytes):
    """S2C 0x4D -> (子号, [LE32 …])；子号 1..6 后面都是一串 LE32（鏢局窗口的列表数据，具体含义没细查）。"""
    if not p:
        return None, []
    return p[0], [struct.unpack_from("<I", p, o)[0] for o in range(1, len(p) - 3, 4)]


def parse_3f(p: bytes):
    """S2C 0x3F -> {"value": LE32, "flag": 第 5 字节, "kind": "system" | "player" | "none" | "full" | "fetch"}"""
    if len(p) < 5:
        return None
    v, flag = struct.unpack_from("<I", p, 0)[0], p[4]
    if flag == 0xFA:
        kind = "fetch"
    elif v == 100000000:
        kind = "system"
    elif v > 100000000:
        kind = "player"
    elif v == 0:
        kind = "none"
    elif flag == 0xFF:
        kind = "full"
    else:
        kind = "none"
    return {"value": v, "flag": flag, "kind": kind, "sender": v - 100000000 if v > 100000000 else None}
