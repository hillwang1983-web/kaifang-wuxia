#!/usr/bin/env python3
"""解析 S2C 0x1E「登录角色完整状态」包的载荷（本机原版服务端 / 网金复刻新服务端，分支 B，角色段 1222 字节）。

只依赖标准库。用法:
    python parse_0x1e.py <夹具.json>           # 解析夹具里的 0x1E 帧并打印
    python parse_0x1e.py --jsonl <日志.jsonl>   # 解析 test_client/packet_proxy 日志里第一个 S2C 0x1E
    python parse_0x1e.py --selftest            # 夹具 + 备份 + 新服务端抓到的日志做自测（文件不存在则跳过）

布局来源: C:\\游戏\\网金复刻\\docs\\0x1E字段表.md（服务端.exe 构造函数 0x615995 的静态分析 + 逐列差分），
本文件按它实现，并用 8617293 的夹具/数据库备份逐列核对。

结构:  头(4 字节 LE32 计数, 每次登录不同) + 背包容量 cap(LE16) + cap×5 背包槽 + 9×5 装备槽 + 角色段(以 jyid 为 0 点)
  jyid 偏移 = 6 + 5×(cap+9)。8617293 的 cap=23 → 166；123456 的 cap=177 → 936。
  背包槽 = 物品ID(LE32) + 1 字节（耐久，算法未读到）；装备槽第 5 字节是 renwu.<部位>zhuangtai，武器位置输出两次。
  角色段从 jyid 到包尾恒为 1222 字节（分支 B；分支 A 是 1264，没有样本）。
"""
import json
import os
import sys

HDR = 6
EQUIP_SLOTS = ("toukui", "xianglian", "yifu", "pifeng", "wuqi", "wuqi", "huwan", "jiezhi", "xiezi")
TAIL_B = 1222       # jyid 到包尾，分支 B (载荷 1388 且 cap=23)；cap 变大时背包变长，角色段不变

# (相对 jyid 的偏移, 宽度, 名字) —— 名字就是 renwu 的列名
RENWU_FIELDS = [
    (38, 4, "map"), (42, 4, "x"), (46, 4, "y"),
    (50, 2, "zuidajing"), (52, 2, "dangqianjing"),
    (54, 4, "zuidaxue"), (58, 4, "dangqianxue"),
    (62, 2, "zuidashen"), (64, 2, "dangqianshen"),
    (66, 4, "dangqiannei"), (70, 4, "zuidanei"),
    (74, 1, "str"), (75, 1, "crg"), (76, 1, "wint"), (77, 1, "luk"), (78, 1, "dex"), (79, 1, "agi"), (80, 1, "vit"),
    (81, 1, "zigong"), (82, 2, "study_count"), (92, 4, "combat_exp"),
    (108, 2, "wuqiqiangdu"), (110, 2, "fangjuqiangdu"),
    (116, 1, "diet_val"), (119, 1, "water_val"), (120, 4, "kill_val"), (124, 1, "pk_val"),
    (133, 4, "jy_money"), (137, 4, "fame_val"), (183, 4, "online_time"),
    (187, 1, "b_month"), (188, 1, "b_day"), (191, 1, "sex"), (192, 1, "school"), (194, 2, "master"),
    (202, 4, "exp_val"), (206, 2, "evil_val"),
    (212, 1, "school_skill_lv"), (213, 4, "school_skill_exp"),
    (562, 1, "head_image"), (563, 1, "mode"),
]
# 固定值（服务端.exe 里的常量），解析时用来校验布局是否对得上
CONSTS = [
    (112, bytes.fromhex("8a000000")), (117, bytes.fromhex("9b00")), (125, bytes.fromhex("0f00000000000000")),
    (189, bytes.fromhex("0317")), (217, bytes.fromhex("d007") + bytes(10)), (361, b"\x0a"),
]
CHAR_EQUIP = ("dao", "qiang", "jian", "bian", "gun", "xin", "ci", "qing", "du", "yi", "zhen", "quan", "shan", "ge", "no")  # 229, 15×LE16
WUGONG = ("daofa", "qiangfa", "jianfa", "bianfa", "gunfa", "neigong", "cishu", "shenfa", "dushu", "yishu",
          "zhenfa", "boji", "shanduo", "anqi", "chaizhao", "dushushizi", "jiaoyi")      # 259, 17×(LE16 等级 + LE32 经验)
JINENG = ("famu", "gongjiang", "zhibu", "caifeng", "lieren", "caikuang", "datie", "zhujian", "nongfu", "buyu", "chushi")  # 507, 11×(1+4)
KF_COUNT, KF_ROWS, KF_ROW = 362, 363, 9       # 每行 9 字节：+1 等级 +3..5 经验 LE24 +7..8 武功 ID LE16。2026-10-20 对原版 6731 实测：写进 4 条 kf（1000/1102/1104/1113），0x1E 里紧挨着 9 字节一条；
                                              # 16 条 × 9 = 144 字节正好填满 kf 区（0x1E 字段表 528..672），11 字节一条放不下 16 条。新服务端 state.py 写成了 11 字节，和原版不一致


def u(b, o, w):
    return int.from_bytes(b[o:o + w], "little")


def text(b, o):
    """长度字节 + 16 字节缓冲区。"""
    n = b[o]
    raw = b[o + 1:o + 1 + min(n, 16)]
    return raw.decode("big5", "replace")      # 线上中文是 BIG5（服务端已把库里的 GBK 转成 BIG5）


def layout(p: bytes):
    """返回 (背包容量, jyid 偏移)。"""
    cap = u(p, 4, 2)
    return cap, HDR + 5 * (cap + len(EQUIP_SLOTS))


def parse(p: bytes) -> dict:
    cap, J = layout(p)
    if J + 600 > len(p):
        raise ValueError("载荷太短或背包容量不合理: len=%d cap=%d" % (len(p), cap))
    out = {"payload_len": len(p), "header_counter": u(p, 0, 4), "bag_capacity": cap, "jyid_offset": J,
           "tail_from_jyid": len(p) - J, "tail_is_branch_b": len(p) - J == TAIL_B}
    bag = []
    for k in range(cap):
        o = HDR + 5 * k
        if u(p, o, 4) or p[o + 4]:
            bag.append({"slot": k, "item_id": u(p, o, 4), "byte5": p[o + 4]})
    out["bag"] = bag
    eq = {}
    for k, nm in enumerate(EQUIP_SLOTS):
        o = HDR + 5 * (cap + k)
        eq.setdefault(nm, []).append({"item_id": u(p, o, 4), "zhuangtai": p[o + 4]})
    out["equip"] = eq
    f = {"jyid": u(p, J, 4)}
    out["name"] = text(p, J + 4)
    out["second_string"] = text(p, J + 21)      # 5 字节前缀 V7Z0- + nickname
    for rel, w, nm in RENWU_FIELDS:
        f[nm] = u(p, J + rel, w)
    out["fields"] = f
    out["char_equip"] = {nm: u(p, J + 229 + 2 * i, 2) for i, nm in enumerate(CHAR_EQUIP)}
    out["wugong"] = {nm: {"lv": u(p, J + 259 + 6 * i, 2), "exp": u(p, J + 261 + 6 * i, 4)} for i, nm in enumerate(WUGONG)}
    out["jineng"] = {nm: {"lv": p[J + 507 + 5 * i], "exp": u(p, J + 508 + 5 * i, 4)} for i, nm in enumerate(JINENG)}
    n_kf = u(p, J + KF_COUNT, 2)
    out["kf_count"] = n_kf
    out["kf_rows"] = [p[J + KF_ROWS + KF_ROW * i:J + KF_ROWS + KF_ROW * (i + 1)].hex(" ") for i in range(min(n_kf, 16))]
    out["const_mismatch"] = [rel for rel, v in CONSTS if p[J + rel:J + rel + len(v)] != v]
    return out


def first_0x1e(path):
    """从夹具 .json 或 test_client/packet_proxy 的 .jsonl 日志取第一个 S2C 0x1E 的载荷。"""
    if path.lower().endswith(".jsonl"):
        for line in open(path, encoding="utf8"):
            r = json.loads(line)
            if r.get("ev") == "frame" and r.get("dir") == "S2C" and r.get("type") == 0x1E:
                return bytes.fromhex(r["payload"])
        raise SystemExit("日志里没有 S2C 0x1E")
    j = json.load(open(path, encoding="utf8"))
    return bytes.fromhex(next(x for x in j["frames"] if x["opcode"] == 0x1E)["payload"])


def selftest():
    fx = r"C:\游戏\网金复刻\data\fixtures\login-8617293.json"
    bk = r"C:\游戏\网金复刻\backups\jyid-8617293-before-replay.tsv"
    live = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_newserver_123456_19.jsonl")
    ok = True

    def check(c, m):
        nonlocal ok
        print(("PASS " if c else "FAIL ") + m)
        ok = ok and c

    if os.path.exists(fx) and os.path.exists(bk):
        r = parse(first_0x1e(fx))
        lines = open(bk, encoding="gbk", errors="replace").read().split("\n")
        i = lines.index("### renwu ")
        R = dict(zip(lines[i + 1].split("\t"), lines[i + 2].split("\t")))
        F = r["fields"]
        check(r["payload_len"] == 1388 and r["bag_capacity"] == 23 and r["jyid_offset"] == 166, "夹具: 载荷 1388, cap=23, jyid 在 166")
        check(r["tail_is_branch_b"], "夹具: jyid 到包尾 1222")
        check(not r["const_mismatch"], "夹具: 服务端常量块全部对上 %s" % r["const_mismatch"])
        check(F["jyid"] == int(R["jyid"]) and r["name"] == R["name"], "jyid / name = %r" % r["name"])
        check(r["second_string"] == "V7Z0-" + R["nickname"], "第二串 = V7Z0- + nickname (%r)" % r["second_string"])
        for rel, w, nm in RENWU_FIELDS:
            if nm == "online_time":
                check(F[nm] >= int(R[nm]), "online_time 递增 (%d >= %s)" % (F[nm], R[nm]))
            elif nm in R:
                check(F[nm] == int(R[nm]), "%s = %d" % (nm, F[nm]))
            else:
                print("SKIP %s：备份里没有这一列" % nm)
        for nm in WUGONG:
            if nm in R and nm + "exp" in R:
                check(r["wugong"][nm] == {"lv": int(R[nm]), "exp": int(R[nm + "exp"])}, "武功 %s %s" % (nm, r["wugong"][nm]))
        for nm in set(EQUIP_SLOTS):
            if nm in R and nm + "zhuangtai" in R:
                for e in r["equip"][nm]:
                    check(e == {"item_id": int(R[nm]), "zhuangtai": int(R[nm + "zhuangtai"])}, "装备 %s %s" % (nm, e))
        j = lines.index("### item ")
        rows = []
        for ln in lines[j + 2:]:
            if ln.startswith("###"):
                break
            c = ln.split("\t")
            if len(c) >= 5 and c[0].isdigit():
                rows += [int(c[2])] * int(c[4])
        check([s["item_id"] for s in r["bag"]] == rows, "背包 %d 槽与 DB item 表（数量展开）逐项一致" % len(rows))
    else:
        print("夹具或备份不存在，跳过夹具部分")
    if os.path.exists(live):
        r = parse(first_0x1e(live))
        check(r["fields"]["jyid"] == 123456, "新服务端抓包: jyid 在 cap 推出的偏移 %d 处 = 123456" % r["jyid_offset"])
        check(r["bag_capacity"] == 177 and r["tail_is_branch_b"], "新服务端抓包: cap=177, jyid 到包尾 1222")
        check(not r["const_mismatch"], "新服务端抓包: 常量块对上 %s" % r["const_mismatch"])
        check(r["second_string"].startswith("V7Z0-"), "新服务端抓包: 第二串 %r" % r["second_string"])
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) >= 3 and sys.argv[1] == "--jsonl":
        print(json.dumps(parse(first_0x1e(sys.argv[2])), ensure_ascii=False, indent=2))
    elif len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        print(json.dumps(parse(first_0x1e(sys.argv[1])), ensure_ascii=False, indent=2))
    else:
        print(__doc__)
        sys.exit(2)
