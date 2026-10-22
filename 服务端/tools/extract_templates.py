"""从 服务端.exe 里提取内置的 S2C 封包常量。

易语言服务端把很多固定封包存成「空格分隔的十六进制文本」常量（明文帧，未异或），
发送时逐字节与玩家密钥异或（见 docs/服务端逆向笔记.md 的发包流程）。两类常量：

  frame  —— 整帧：从头到尾恰好被若干完整帧吃完，例如 `F4 44 09 99 04 0E AE A5 31`
  prefix —— 前缀：只有帧头和前几个字节，后面的字段由代码拼接，例如 `F4 44 0E 17 `
            （帧头里的长度字段仍然是整帧长度，所以能得到该 opcode 的固定长度）

    python tools/extract_templates.py [服务端.exe 路径]

输出：data/s2c_templates.json、data/s2c_prefixes.json、docs/服务端内置封包模板.md。
解析只信长度字段。注意：有的常量里单个十六进制位没有补零（如 `6`、`A`），按数值解析。
"""

from __future__ import annotations

import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jyserver.codec import derive_key  # noqa: E402

DEFAULT_EXE = r"C:\游戏\网金最原始文件\网金最原始文件\服务端\服务端.exe"
# 以魔数开头、由 1~2 位十六进制 token 组成、可带尾部空格、以 NUL 结束
HEX_TEMPLATE = re.compile(rb"(?<![0-9A-Za-z ])((?:F4 44|F5 B3) (?:[0-9A-Fa-f]{1,2} ?)*)(?=\x00)")


def pe_sections(data: bytes):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    n = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    image_base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    out = []
    for i in range(n):
        o = pe + 24 + opt_size + 40 * i
        vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", data, o + 8)
        out.append((va, max(vsize, rawsize), rawptr, rawsize))
    return image_base, out


def file_offset_to_va(off: int, image_base: int, secs) -> int | None:
    for va, size, rawptr, rawsize in secs:
        if rawptr <= off < rawptr + rawsize:
            return image_base + va + (off - rawptr)
    return None


def header_of(b: bytes, pos: int = 0):
    """返回 (total, op_index, wide) 或 None（数据不足/魔数不对）。"""
    head = b[pos : pos + 2]
    if head == b"\xf4\x44" and pos + 4 <= len(b):
        return b[pos + 2], 3, False
    if head == b"\xf5\xb3" and pos + 5 <= len(b):
        return b[pos + 2] | (b[pos + 3] << 8), 4, True
    return None


def split_frames(b: bytes):
    """把明文切成若干完整帧；返回 (frames, 消耗字节数)。"""
    frames, pos = [], 0
    while pos < len(b):
        h = header_of(b, pos)
        if h is None:
            break
        total, op_i, wide = h
        if total < op_i + 1 or pos + total > len(b):
            break
        frames.append(
            {
                "opcode": b[pos + op_i],
                "wide": wide,
                "length": total,
                "payload": b[pos + op_i + 1 : pos + total],
            }
        )
        pos += total
    return frames, pos


def try_big5(payload: bytes) -> str | None:
    for start in (0, 1, 2):
        try:
            s = payload[start:].decode("big5")
        except UnicodeDecodeError:
            continue
        if sum("\u4e00" <= c <= "\u9fff" for c in s) >= 2:
            return s
    return None


def main() -> int:
    exe = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXE)
    data = exe.read_bytes()
    image_base, secs = pe_sections(data)

    frames_out, prefixes_out = [], []
    for m in HEX_TEMPLATE.finditer(data):
        text = m.group(1).decode()
        try:
            raw = bytes(int(t, 16) for t in text.split())
        except ValueError:
            continue
        va = file_offset_to_va(m.start(1), image_base, secs)
        va_s = f"0x{va:x}" if va else None
        frames, used = split_frames(raw)
        if frames:
            rec = {
                "va": va_s,
                "hex": text.strip().upper(),
                "complete": used == len(raw),
                "frames": [
                    {
                        "opcode": f"0x{f['opcode']:02x}",
                        "wide": f["wide"],
                        "length": f["length"],
                        "payload": f["payload"].hex(" "),
                        **({"big5": t} if (t := try_big5(f["payload"])) else {}),
                    }
                    for f in frames
                ],
            }
            for f in frames:
                if f["opcode"] == 0x99 and len(f["payload"]) == 5 and f["payload"][0] == 0x04:
                    rec["key_change"] = {
                        "seed": f["payload"][1:].hex(" "),
                        "key": f"0x{derive_key(f['payload'][1:]):02x}",
                    }
            frames_out.append(rec)
            continue
        h = header_of(raw)
        if h is not None:  # 只有帧头：前缀
            total, op_i, wide = h
            prefixes_out.append(
                {
                    "va": va_s,
                    "hex": text.rstrip().upper(),
                    "opcode": f"0x{raw[op_i]:02x}",
                    "wide": wide,
                    "declared_length": total,
                    "bytes_present": len(raw),
                }
            )

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "s2c_templates.json").write_text(json.dumps(frames_out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "data" / "s2c_prefixes.json").write_text(json.dumps(prefixes_out, ensure_ascii=False, indent=1), encoding="utf-8")

    hist = Counter(f["opcode"] for r in frames_out for f in r["frames"])
    complete = sum(r["complete"] for r in frames_out)
    lines = [
        "# 服务端.exe 内置的 S2C 封包常量",
        "",
        f"由 `tools/extract_templates.py` 从 `{exe.name}` 自动生成。明文帧，发送时逐字节与玩家密钥异或。",
        f"整帧常量 {len(frames_out)} 条（{complete} 条被长度字段恰好完整吃掉）；前缀常量 {len(prefixes_out)} 条。",
        "",
        "**这些是原服务端真实会发出的字节**，但每条在什么时机发、字段含义是什么，仍需结合代码或抓包确认；"
        "下表只列事实。",
        "",
        "## 整帧常量：opcode 出现次数",
        "",
        ", ".join(f"{op}×{n}" for op, n in sorted(hist.items())),
        "",
        "## 密钥更换帧（类型 0x99 / 载荷 04 + 4 字节种子）",
        "",
    ]
    for r in frames_out:
        if "key_change" in r:
            lines.append(f"- `{r['va']}` 种子 `{r['key_change']['seed']}` → 密钥 `{r['key_change']['key']}`（按 derive_key 公式算出，未经真实流量验证）")

    lines += ["", "## 前缀常量（后面的字段由代码拼接）：S2C opcode 与整帧长度", "",
              "同一 opcode 可能有多种长度。长度是帧头里声明的整帧字节数（含魔数）。", "",
              "| opcode | 声明长度 | 帧类型 | 前缀 | 地址 |", "|---|---|---|---|---|"]
    for p in sorted(prefixes_out, key=lambda p: (p["opcode"], p["declared_length"])):
        lines.append(f"| {p['opcode']} | {p['declared_length']} | {'长' if p['wide'] else '短'} | `{p['hex']}` | {p['va']} |")

    lines += ["", "## 整帧常量：全部", "", "| 地址 | 帧 | 说明 |", "|---|---|---|"]
    for r in frames_out:
        parts, notes = [], []
        for f in r["frames"]:
            parts.append(f"{f['opcode']}{'L' if f['wide'] else 'S'}/{f['length']}")
            if "big5" in f:
                notes.append("BIG5: " + f["big5"])
        flag = "" if r["complete"] else " ⚠️未吃完"
        text = f"`{r['hex'][:90]}{'…' if len(r['hex']) > 90 else ''}`"
        lines.append(f"| {r['va']} | {' '.join(parts)}{flag} | {text} {'; '.join(notes)} |")
    lines += ["", "帧列：`opcode` 后 S=短帧(F4 44) L=长帧(F5 B3)，`/` 后为整帧长度。", ""]
    (ROOT / "docs" / "服务端内置封包模板.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"frames: {len(frames_out)} (complete {complete}); prefixes: {len(prefixes_out)}")
    pre_hist = Counter(p["opcode"] for p in prefixes_out)
    print("prefix opcodes:", ", ".join(f"{op}x{n}" for op, n in sorted(pre_hist.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
