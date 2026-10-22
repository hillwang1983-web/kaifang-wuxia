#!/usr/bin/env python3
"""S2C 0x1A 子类型表（notices.py）。只用标准库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notices  # noqa: E402

RES = []


def check(c, msg):
    RES.append(bool(c))
    print(("PASS" if c else "FAIL"), msg)


def b5(b):
    return b.decode("big5", "replace")


def main():
    d = notices.decode_1a
    check(d(b"\x64" + "善惡在-1000到1000之間".encode("big5"), b5) == "善惡在-1000到1000之間", "子类型 0x64：后面直接是文字（对原版实测的格式）")
    check(d(b"\x2f", b5) == "沒有這個玩家", "子类型 0x2F：固定文字「沒有這個玩家」")
    check(d(b"\x03" + "阿明".encode("big5"), b5) == "信件已成功寄給：阿明", "子类型 0x03：固定文字 + 玩家名")
    check(d(b"\x08" + "小華".encode("big5"), b5) == "寄件失敗,查無以下玩家：小華", "子类型 0x08：固定文字 + 玩家名")
    check(d(b"\x05", b5) == "沒有新信件" and d(b"\x4c", b5) == "已婚者不能預約婚禮", "子类型 0x05 / 0x4C 固定文字")
    check(d(b"\x66" + "測試".encode("big5"), b5) == "測試", "子类型 0x66：后面是文字")
    check(all(d(bytes([c]), b5) is None for c in notices.NO_MESSAGE) and d(b"\x65", b5) is None and d(b"\xff", b5) is None, "没有文字的子类型 / 不认识的子类型 → None")
    check(d(b"", b5) is None and d(b"\x64", b5) is None, "空载荷 / 0x64 后没有文字 → None")
    check(len(notices.CODES) == 74 and min(notices.CODES) == 3 and max(notices.CODES) == 0x51, "表里 74 个子类型（3..0x51）")
    print("\n%d/%d 通过" % (sum(RES), len(RES)))
    return 0 if all(RES) else 1


if __name__ == "__main__":
    sys.exit(main())
