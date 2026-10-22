#!/usr/bin/env python3
"""生活技能（伐木 / 捕魚 / 採礦）：C2S 0x5A 开始 / 工作一轮 / 停止，S2C 0x64 是每轮的结果。

全部来自 loginp.exe 静态逆向（工作窗口 0x91b8b8 / 0x91be38，发送函数 0x9cc0f0）+ 对原版服务端 6731 实测（2026-10-20，8617293）：

  C2S 0x5A（带会话校验）载荷：
      序号 LE32 | A(1) | B(1) | F(1) | E LE16 | D LE16 | C(1) | 校验字节(1)
      A：1 = 开始，2 = 工作一轮（客户端每 8 秒发一次），3 = 停止（B / F / E / D / C 全填 0）
      B：工作类型 1 伐木 / 2 捕魚 / 3 採礦（4 農夫走的是 C2S 0x5C / 0x5B，没做）
      F：工具在背包里的位置（实测服务端不挑，填背包下标即可）
      E / D / C：客户端填玩家对象里的三个值（+0x120 u16、+0x7a u16、+0x44 byte），实测填 0 服务端照收
      校验字节 = 会话提供者 k 的值，k = (B + F + 0x1C − A + 序号) % M + 1；序号可以自己选（客户端是每次 +1..5 的计数器，
      服务端接受往上跳几格），所以挑一个让 k 落在 2 / 6 的序号，k = 2 / 6 的提供者只和种子有关（session_key_emu，见 biaoju.py）。
  服务端回应：
      开始 / 停止 → S2C 0x82 `jyid(LE32) 状态(LE16)`：伐木 3、捕魚 4（採礦 5 推测），停止 0
      每轮 → S2C 0x7B 16 01 <精 LE32>（精 −1）、0x76 BE …（技能 / 熟练度计数）、0x64（结果，见 parse_64）；
             有收获时再来 0x0B / 0x77（得到的物品）；VIP 号会自动存进钱庄（1A 64「VIP功能采集物品自動存入錢庄﹗」+ 0x27 钱庄清单）
  S2C 0x64：物品 id(LE16，低 16 位) | 成功(1) | a(1) | b(1) | 计数 LE32（实测载荷只有 8 字节，计数只有 3 字节，缺的按 0）；成功 = 0 时按当前工作类型显示
      「好硬的木頭,手都長水泡了…」/「魚都不吃餌,等到快睡著…」/「好難挖,手都長水泡了…」，成功时「得到 <物品>」。
"""
import struct

import biaoju

JOB_NAMES = {1: "伐木", 2: "捕魚", 3: "採礦"}
STATUS_OF_JOB = {1: 3, 2: 4}          # 0x82 状态值（採礦没验证）
TICK_SECS = 8.0                       # 客户端每 8000 毫秒发一次"工作一轮"
FAIL_TEXT = {1: "好硬的木頭,手都長水泡了...", 2: "魚都不吃餌,等到快睡著...", 3: "好難挖,手都長水泡了...", 4: "耕種失敗"}
# 各工作类型能用的工具名（物品表里的简体名；用关键字匹配，排除兑换券 / 零件）
TOOL_WORDS = {1: ("斧",), 2: ("钓竿",), 3: ("镐",), 4: ("锄",)}      # 4 = 農夫（走 C2S 0x5B / 0x5C）
TOOL_EXCLUDE = ("兑换", "券", "卷", "组合", "碎片", "握柄", "斧刃", "劈天", "神斧", "退休")


def tool_ids(names: dict, job: int):
    """names: 物品 id -> 简体名（gateway.Items.names）；返回这种工作能用的工具 id 列表。"""
    words = TOOL_WORDS[job]
    return sorted(i for i, n in names.items() if any(w in n for w in words) and not any(x in n for x in TOOL_EXCLUDE) and 45000 <= i < 46000)


def pick_seq(seq_min: int, a: int, b: int, f: int, m: int):
    """从 seq_min 起找第一个让校验下标 k 落在 SAFE_K 上的序号。返回 (序号, k)"""
    seq = max(1, seq_min)
    for _ in range(4 * m):
        k = (b + f + 0x1C - a + seq) % m + 1
        if k in biaoju.SAFE_K:
            return seq, k
        seq += 1
    raise ValueError("凑不出可算的校验下标")


def build_z(seq: int, a: int, b: int, f: int, e: int, d: int, c: int, provider, k: int) -> bytes:
    """C2S 0x5A 的载荷；provider(k) -> 校验字节。"""
    return struct.pack("<I", seq) + bytes([a, b, f]) + struct.pack("<HH", e & 0xFFFF, d & 0xFFFF) + bytes([c & 0xFF, provider(k) & 0xFF])


def pick_seq_farm(seq_min: int, plot: int, action: int, m: int):
    """農夫 C2S 0x5C 的序号：k = (plot + action + 序号) % M + 1 要落在 SAFE_K。返回 (序号, k)"""
    seq = max(1, seq_min)
    for _ in range(4 * m):
        k = (plot + action + seq) % m + 1
        if k in biaoju.SAFE_K:
            return seq, k
        seq += 1
    raise ValueError("凑不出可算的校验下标")


def build_plant(plot: int, seed_item: int) -> bytes:
    """C2S 0x5B（播種，无校验）：田块号(1) | 种子物品 id LE16（背包里要有，扣 1 个）"""
    return bytes([plot & 0xFF]) + struct.pack("<H", seed_item & 0xFFFF)


def build_farm(seq: int, plot: int, action: int, e: int, d: int, c: int, provider, k: int) -> bytes:
    """C2S 0x5C（耕種 / 收成）：序号 LE32 | 田块号 | 动作(1 耕種 / 2 收成) | E LE16 | D LE16 | C | 校验字节"""
    return struct.pack("<I", seq) + bytes([plot & 0xFF, action]) + struct.pack("<HH", e & 0xFFFF, d & 0xFFFF) + bytes([c & 0xFF, provider(k) & 0xFF])


def parse_64(p: bytes):
    """S2C 0x64 -> {"item_id" (低 16 位), "ok", "a", "b", "count"}；不足 9 字节返回 None"""
    if len(p) < 6:
        return None
    return {"item_id": struct.unpack_from("<H", p, 0)[0], "ok": p[2] != 0, "a": p[3], "b": p[4], "count": int.from_bytes(p[5:9], "little")}
