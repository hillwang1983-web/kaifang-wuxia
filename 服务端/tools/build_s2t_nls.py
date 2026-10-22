"""用 Windows NLS 的「简体→繁体」映射生成完整简繁表 data/s2t.json，并用 MOB数据.csv 里的
BIG5_NAME / GBK_NAME 两列校验（6738 行，应当逐字吻合；吻合率就是这个方法的可信度）。

    python tools/build_s2t_nls.py [--write]

原版服务端是易语言程序，大概率直接调系统的 LCMapString(LCMAP_TRADITIONAL_CHINESE)；
这里在 Windows 上做同样的事，把结果落成纯 Python 能用的静态表，之后不再依赖 Windows。
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import io
import json
from pathlib import Path

DATA_DIR = Path(r"C:\游戏\网金最原始文件\网金最原始文件\服务端\data")
OUT = Path(__file__).resolve().parent.parent / "data" / "s2t.json"
LCMAP_TRADITIONAL_CHINESE = 0x04000000
LOCALE_ZH_CN = 0x0804


def nls_traditional(text: str) -> str:
    k32 = ctypes.windll.kernel32
    n = k32.LCMapStringW(LOCALE_ZH_CN, LCMAP_TRADITIONAL_CHINESE, text, len(text), None, 0)
    buf = ctypes.create_unicode_buffer(n)
    k32.LCMapStringW(LOCALE_ZH_CN, LCMAP_TRADITIONAL_CHINESE, text, len(text), buf, n)
    return buf.value


def all_gbk_chars() -> list[str]:
    out = []
    for hi in range(0x81, 0xFF):
        for lo in range(0x40, 0xFF):
            try:
                ch = bytes([hi, lo]).decode("gbk")
            except UnicodeDecodeError:
                continue
            if len(ch) == 1 and ord(ch) > 0x7F:
                out.append(ch)
    return out


def encode_like_original(text: str, table: dict[str, str]) -> bytes:
    out = bytearray()
    for ch in text:
        c = table.get(ch, ch)
        try:
            out += c.encode("big5")
        except UnicodeEncodeError:
            out += b"?"
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    chars = all_gbk_chars()
    table = {}
    mapped = nls_traditional("".join(chars))
    assert len(mapped) == len(chars)
    for s, t in zip(chars, mapped):
        if s != t:
            table[s] = t
    print(f"GBK 汉字 {len(chars)} 个，NLS 简→繁映射 {len(table)} 个")

    text = (DATA_DIR / "MOB数据.csv").read_bytes().decode("gbk", errors="replace")
    rows = [r for r in csv.reader(io.StringIO(text)) if len(r) > 2 and r[0].strip().isdigit()]
    ok = bad = 0
    shown = 0
    for r in rows:
        big5_name, gbk_name = r[1], r[2]
        want = big5_name.encode("big5", errors="replace")
        got = encode_like_original(gbk_name, table)
        if want == got:
            ok += 1
        else:
            bad += 1
            if shown < 12:
                shown += 1
                print(f"  不吻合 {r[0]}: GBK {gbk_name!r} 原表 BIG5 {big5_name!r} 我们 {got.decode('big5', errors='replace')!r}")
    print(f"MOB 校验：吻合 {ok} / {ok + bad}")
    if args.write:
        OUT.write_text(json.dumps(table, ensure_ascii=False, indent=0), encoding="utf-8")
        print("写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
