"""文本编码。

线上文字是 BIG5 繁体，数据库和 CSV 是 GBK 简体（见 docs/协议模型.md）。
这里只做字节与字符串的互转；简体→繁体的字形转换留到需要下发中文时（M2）再做，
目前没有引入转换表。
"""

from __future__ import annotations


def decode_big5(data: bytes) -> str:
    return data.decode("big5", errors="replace")


def encode_big5(text: str) -> bytes:
    return text.encode("big5", errors="replace")


def decode_gbk(data: bytes) -> str:
    return data.decode("gbk", errors="replace")


def encode_gbk(text: str) -> bytes:
    return text.encode("gbk", errors="replace")
