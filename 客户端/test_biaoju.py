#!/usr/bin/env python3
"""鏢局（託鏢）包的构造 / 解析（biaoju.py），用的是对原版服务端实测抓到的字节。只用标准库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import biaoju  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def b5(b):
    return b.decode("big5", "replace")


def main():
    name = "123456".encode("big5")
    check(biaoju.build_send(name, 47001, 24, 1).hex(" ") == "06 31 32 33 34 35 36 99 b7 00 00 18 01", "build_send：实测「託鏢成功」那一包（名字 123456，47001，耐久 24，1 件）")
    big = biaoju.build_send(b"ab", 0x12345, 7, 3)
    check(big == bytes([2]) + b"ab" + bytes([0x45, 0x23, 0x01, 0x00, 7, 3]), "build_send：物品 id 超过 16 位时低 16 位在前、高 16 位在后")
    ok = True
    for bad in ((b"", 1, 1, 1), (name, 1, 256, 1), (name, 1, 1, 0), (name, 1, 1, 256)):
        try:
            biaoju.build_send(*bad)
            ok = False
        except ValueError:
            pass
    check(ok, "build_send：名字为空 / 耐久、数量超范围 → ValueError")

    got = bytes.fromhex("06 31 32 33 34 35 36 99 b7 00 00 18  06 31 32 33 34 35 36 99 b7 00 00 18".replace("  ", " "))
    check(biaoju.parse_49(got, b5) == [{"from": "123456", "item_id": 47001, "dur": 24}] * 2, "parse_49：实测的两条存放记录")
    check(biaoju.parse_49(got[:-3], b5) == [{"from": "123456", "item_id": 47001, "dur": 24}], "parse_49：最后一条被截断就丢掉，不抛错")
    check(biaoju.parse_4d(bytes.fromhex("04 88 13 00 00")) == (4, [5000]), "parse_4d：实测 4D 04 88 13 00 00 → 子号 4，[5000]")
    check(biaoju.parse_4d(b"") == (None, []), "parse_4d：空载荷")

    check(biaoju.parse_3f(bytes.fromhex("00 e1 f5 05 00"))["kind"] == "system", "parse_3f：值 = 1 亿 → 系统寄信")
    r = biaoju.parse_3f(bytes.fromhex("39 e1 f5 05 00"))
    check(r["kind"] == "player" and r["sender"] == 0x39, "parse_3f：值 > 1 亿 → 玩家寄信，sender = 值 − 1 亿")
    check(biaoju.parse_3f(bytes.fromhex("01 00 00 00 fa"))["kind"] == "fetch" and biaoju.parse_3f(b"\x01\x00") is None, "parse_3f：第 5 字节 0xFA = fetch；载荷太短 → None")

    check(biaoju.is_job_item(47001) and biaoju.is_job_item(47036) and biaoju.is_job_item(47037) and not biaoju.is_job_item(12130) and not biaoju.is_job_item(48022),
          "is_job_item：47001（镖局的包裹）/ 47037（运镖车）是，12130 / 48022 不是")
    check(sum(1 for i in range(65536) if biaoju.is_job_item(i)) == 223, "is_job_item：16 位 id 里共 223 个打工物品（和 Items 表对过）")
    # 取鏢 C2S 0x3F：对原版实测（种子 a2bc2837，M = 8，3 个行号 → k = 2，校验字节 78 = 0x4E）
    seed = bytes.fromhex("a2bc2837")
    check(biaoju.modulus(seed) == 8 and [biaoju.claim_k(n, 8) for n in (1, 2, 3, 7)] == [8, 1, 2, 6], "modulus / claim_k：种子 a2bc2837 → M = 8；1 / 2 / 3 / 7 个行号 → k = 8 / 1 / 2 / 6")
    check(biaoju.build_claim([1, 2, 3], seed, lambda k: {2: 78}[k]).hex(" ") == "4e 01 02 03", "build_claim：实测那一包（行号 1 2 3，k = 2，校验字节 78）")
    got = biaoju.build_claim([1], seed, lambda k: k * 10)
    check(got == bytes([20, 1, 0xFF, 0xFF]), "build_claim：只取 1 行时补 0xFF 到 3 字节让 k 落在 2（校验字节 = provider(2)）")
    got = biaoju.build_claim([1, 2, 3, 4], seed, lambda k: k * 10)
    check(got == bytes([60, 1, 2, 3, 4, 0xFF, 0xFF, 0xFF]), "build_claim：4 行补到 7 字节，k = 6")
    ok = True
    for bad in ([], [0], [255], ["x"]):
        try:
            biaoju.build_claim(bad, seed, lambda k: 0)
            ok = False
        except (ValueError, TypeError):
            pass
    check(ok, "build_claim：空 / 0 / 255 / 非数字行号 → 报错")
    check(biaoju.parse_4b(bytes.fromhex("99 b7 00 00 18 99 b7 00 00 18")) == [{"item_id": 47001, "dur": 24}] * 2 and biaoju.parse_4b(b"\x01\x02") == [], "parse_4b：实测 4B 的两件；不满 5 字节 → 空")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
