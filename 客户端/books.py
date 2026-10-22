#!/usr/bin/env python3
"""读秘笈学特殊武功：C2S 0x60（无会话校验）。

来自 loginp.exe 静态逆向（物品使用函数 0x8519f8 → 特殊物品分支 0x77e13c，发送函数 0x9cd918）+ 对原版服务端 6731 实测（2026-10-20，8617293）。
它不是拜师 / 转门派——早先只看到空载荷触发『物品不足』就猜成了拜师。

  C2S 0x60 载荷：物品 ID 低 16 位 LE16 | 物品 ID 高 16 位 LE16（背包行 +2 的字，通常 0）| 耐久字节（背包行 +4）      共 5 字节
  服务端（处理函数 0x8b1f16，易语言，只认三个物品）：
      35022 乾坤大挪移秘笈 → 武功 2203 乾坤大挪移      要求 7 项属性（臂力 胆识 悟性 富源 定力 机敏 根骨）都 ≥ 50
      35031 葵花宝典       → 武功 3004 葵花宝典        属性同上 + 已自宫（zigong = 1）
      40177 太玄经         → 武功 4023 太玄经          属性同上 + 已自宫
      · 属性不够（乾坤）：S2C 0x1A「需要全屬性50」；葵花 / 太玄经：「需要全屬性50,需要自宮﹗」（只要缺一样都是这句）；书不扣
      · 条件够了就走和事件语句『武功:ID:1』一样的学武功流程（防挂验证.csv 的前置条件，乾坤大挪移要悟性 50 / 福源 38 / 定力 30 / 根骨 42、历练 20000、
        实战 10000000、上线时间 1000，另两门没有这一行）：成功 → S2C 0x68（武功 | Lv1 | 经验 0 | 学习点 | 精）+ 0x0B / 0x6B（书从背包里没了）；
        防挂验证不满足 → 全服 S2C 0x14 03「玩家﹕<名字>正在刷武功事件﹕<武功>該行為已經記錄﹗」，**书照样被扣**；
        已经有这门武功 → 0x1A「已經有此武功了﹗」，**书照样被扣**。
      · 背包里没有这件物品 → 0x1A「物品不足」，并且把自己踢下线（S2C 0x05 自己的 jyid 01）。
  别的物品（35041 习经书 / 35048 戒气经 / 35052 铁罗汉 / 其它秘笈）客户端也走 0x60，但原版服务端一律静默，什么都不做。
"""
import struct

# 物品 id -> 学到的武功 id / 名 / 要不要自宫
BOOKS = {
    35022: {"kf": 2203, "name": "乾坤大挪移", "zigong": False},
    35031: {"kf": 3004, "name": "葵花宝典", "zigong": True},
    40177: {"kf": 4023, "name": "太玄经", "zigong": True},
}
STATS = ("str", "crg", "wint", "luk", "dex", "agi", "vit")
MIN_STAT = 50


def build_read(item_id: int, dur: int, high: int = 0) -> bytes:
    """C2S 0x60 载荷（5 字节）"""
    return struct.pack("<HHB", item_id & 0xFFFF, high & 0xFFFF, dur & 0xFF)


def check(item_id: int, fields: dict, known_kf):
    """按服务端的规则预检（书会被扣、或把自己踢下线的情况都在这里挡掉）；返回错误文字，None = 可以读。
    fields = 角色属性（jyclient.me["fields"]），known_kf = 已有武功 id 的集合。防挂验证.csv 的前置条件这里不查。"""
    b = BOOKS.get(item_id)
    if b is None:
        return "原版服务端只认乾坤大挪移秘笈 / 葵花宝典 / 太玄经这三本"
    if b["kf"] in known_kf:
        return "已經有此武功了（读了书也会被扣掉）"
    if any(fields.get(k, 0) < MIN_STAT for k in STATS):
        return "需要全屬性50"
    if b["zigong"] and not fields.get("zigong"):
        return "需要全屬性50,需要自宮"
    return None
