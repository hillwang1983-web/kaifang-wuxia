#!/usr/bin/env python3
"""消点（把学习点数花在武功上）：C2S 0x5E，师傅表 = 服务端 data\\师傅.csv。

来自 loginp.exe 静态逆向（学习窗口 0x828c1c "請輸入大於1的正整数 / 數字已超過上限 / 學習的技能等級已達極限"，发送函数 0x9cd6cc）
+ 对原版服务端 6731 实测（2026-10-20，8617293）：

  C2S 0x5E（带会话校验）载荷：
      师傅 ID LE16 | 武功 ID LE16 | 点数 LE16 | 序号 LE32 | 校验字节
      校验下标 k = (师傅 + 0x7530 − 武功 + 序号) % M + 1；序号自选让 k ∈ {2, 6}（同取鏢 / 生活技能 / 農夫）
  服务端检查（师傅.csv 一行 = 一位师傅教的一门武功：ID, 人物, 顺序, 武功代码, 名称, 级数, 门派, 类别, 地图）：
      · (师傅, 武功) 必须是表里的一行，否则 S2C 0x14 03「無此師傅代碼，請聯系GM告知此代碼<师傅>﹔<武功>」（还有一条 0x14 0e 发给 GM 频道）
      · 玩家当前地图必须等于这一行的「地图」，否则 0x14 0e「消點地圖不正确!:<武功>武功隨机掉一級」+ S2C 0x70（随机一门武功掉一级）
      · 这一行的「门派」非 0 时必须等于玩家门派，否则 0x14 0e「嘗試刷不屬于自己門派的武功﹗<武功>武功隨机掉一級」+ 0x70
      · 点数 > 学习点 → 静默不理；点数 = 0 → 回显一条 0x68 不变；没有这门武功 / 学习点 0 → 静默
  成功回应 S2C 0x68：武功 ID LE16 | 等级 LE16 | 经验 LE32 | 学习点 LE16 | 精 LE16（学习点 −点数，经验 += floor(悟性 × 1.5) × 点数（复刻服务端逐帧核对后更正：我最初的『31.5 / 点』只是因为测试号悟性正好 21），
      够了升级；实测悟性 21：lvl 5 花 2000 点 → lvl 18；lvl 79 花 3000 点 → 经验 94500、等级不变）。
  掉级回应 S2C 0x70：学习点 LE16 | 精 LE16 | 武功 ID LE16 | 掉级后的等级 LE16 | 经验 LE32（经验清零）。
"""
import csv
import os
import struct

import biaoju


class Masters:
    """师傅表。rows: [{"master", "name", "order", "kf", "kf_name", "cap", "school", "cls", "map"}]"""

    def __init__(self, path=None, rows=None):
        self.rows = rows if rows is not None else []
        if path and os.path.exists(path):
            with open(path, encoding="gbk", errors="replace", newline="") as f:
                rd = csv.reader(f)
                next(rd, None)
                for r in rd:
                    try:
                        self.rows.append({"master": int(r[0]), "name": r[1], "order": int(r[2]), "kf": int(r[3]), "kf_name": r[4], "cap": int(r[5]),
                                          "school": int(r[6]), "cls": int(r[7]), "map": int(r[8])})
                    except (ValueError, IndexError):
                        continue
        self.by_pair = {(r["master"], r["kf"]): r for r in self.rows}

    def on_map(self, map_id: int):
        """这张图上的师傅：[{"master", "name", "kfs": [row…按顺序]}]"""
        out = {}
        for r in self.rows:
            if r["map"] == map_id:
                out.setdefault(r["master"], {"master": r["master"], "name": r["name"], "kfs": []})["kfs"].append(r)
        for m in out.values():
            m["kfs"].sort(key=lambda r: r["order"])
        return sorted(out.values(), key=lambda m: m["master"])

    def check(self, master: int, kf: int, map_id: int, school: int):
        """按服务端的规则预检；返回错误文字，None = 服务端会收（不会掉级）。"""
        r = self.by_pair.get((master, kf))
        if r is None:
            return "这位师傅不教这门武功"
        if r["map"] != map_id:
            return "这位师傅不在这张地图上（在 %d）" % r["map"]
        if r["school"] and r["school"] != school:
            return "这门武功不属于你的门派（门派 %d）" % r["school"]
        return None


def pick_seq_study(seq_min: int, master: int, kf: int, m: int):
    """k = (师傅 + 0x7530 − 武功 + 序号) % M + 1 落在 SAFE_K 的第一个序号。返回 (序号, k)"""
    seq = max(1, seq_min)
    for _ in range(4 * m):
        k = (master + 0x7530 - kf + seq) % m + 1
        if k in biaoju.SAFE_K:
            return seq, k
        seq += 1
    raise ValueError("凑不出可算的校验下标")


def build_study(master: int, kf: int, points: int, seq: int, provider, k: int) -> bytes:
    """C2S 0x5E 载荷（11 字节）；provider(k) -> 校验字节"""
    return struct.pack("<HHHI", master & 0xFFFF, kf & 0xFFFF, points & 0xFFFF, seq) + bytes([provider(k) & 0xFF])


def parse_68(p: bytes):
    """S2C 0x68（学武功 / 消点）-> {"kf", "lv", "exp", "study", "jing"}；太短返回 None"""
    if len(p) < 12:
        return None
    kf, lv, exp, study, jing = struct.unpack_from("<HHIHH", p, 0)
    return {"kf": kf, "lv": lv, "exp": exp, "study": study, "jing": jing}


def parse_70(p: bytes):
    """S2C 0x70（武功掉一级）-> {"study", "jing", "kf", "lv", "exp"}；太短返回 None"""
    if len(p) < 12:
        return None
    study, jing, kf, lv, exp = struct.unpack_from("<HHHHI", p, 0)
    return {"study": study, "jing": jing, "kf": kf, "lv": lv, "exp": exp}
