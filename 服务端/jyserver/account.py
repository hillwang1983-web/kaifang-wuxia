"""账号类指令：改外号(C2S 0x13)、删除角色(0x33)、自宫等(0x98)。

行为依据 2026-10 对原版的实测（tools/cmd_probe.py、tools/delete_probe.py），详见 docs/账号类指令.md。
纯函数：入参是角色的数据库行（原地修改）和账号密码，返回要发的帧；网络层在 server.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import from_big5, to_big5

Frame = tuple[int, bytes, bool]

VIP_LEVEL = b"7"  # 外号前缀里的 VIP 等级，恒为 7（见 docs/文字指令.md）
REBIRTH_KF = 3860  # 转生武功：它的等级 // 10 就是外号前缀里的 Z 后面的数
_BAD_PASSWORD = b"\x64" + bytes.fromhex("b1 4b bd 58 bf f9 bb 7e")  # 0x1A: 密碼錯誤
_NO_BETRAY = b"\x64" + bytes.fromhex("bd d0 b1 71 a5 7e ac 45 a4 57 a7 50 aa f9 a1 54")  # 請從外掛上判門﹗（原版 0x67 的停用桩）
_CHANGED = bytes.fromhex("a7 f3 a7 ef a4 46 a5 7e b8 b9 a1 52")  # 更改了外號﹕

# 删除角色时要清空的表（账号行保留，所以账号可以重新建角色）
CHARACTER_TABLES = ("renwu", "char_equip", "jineng", "kf", "item", "biaoji", "qianzhuang")


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)
    to_all: list[Frame] = field(default_factory=list)
    zigong: bool = False  # 自宫成功（0x98 0D 密码对）：renwu.zigong 置 1（原版同时置 player+0x14c = 1）
    deleted: bool = False  # 角色已删除，网络层要存档


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def change_nickname(rows: dict, payload: bytes) -> Result:
    """C2S 0x13：载荷 = 新外号的原始字节（BIG5，到第一个 00 为止；空载荷 = 清空外号，没有长度上限）。

    库里存的是简体（BIG5 解码后过繁转简）。回包：自己收 0x15 = jyid + `V7Z<转生等级>-` + 原始字节；
    **全服**（含自己）收 0x14 `0e` = <名字>更改了外號﹕ + 同样的 `V7Z…-外号`。
    """
    res = Result()
    renwu = rows["renwu"][0]
    raw = payload.split(b"\x00", 1)[0]
    renwu["nickname"] = from_big5(raw)
    z = next((_i(k.get("kf_lvl")) // 10 for k in rows.get("kf") or [] if _i(k.get("kf_id")) == REBIRTH_KF), 0)
    title = b"V" + VIP_LEVEL + b"Z" + str(z).encode() + b"-" + raw
    res.to_self.append((0x15, _i(renwu.get("jyid")).to_bytes(4, "little") + title, False))
    res.to_all.append((0x14, b"\x0e" + to_big5(renwu.get("name", "") or "") + _CHANGED + title, True))
    return res


def _password_arg(payload: bytes, at: int) -> bytes | None:
    """载荷里 `长度(1) + 密码字节` 的那一段；长度不够返回 None（原版此时静默）。"""
    if len(payload) <= at:
        return None
    n = payload[at]
    if len(payload) < at + 1 + n:
        return None
    return payload[at + 1 : at + 1 + n]


def delete_character(rows: dict, password: str, payload: bytes) -> Result:
    """C2S 0x33：载荷 = 1 字节（不看）+ 密码长度(1) + 密码字节（后面多的字节不看）。

    密码对 → 清空角色的 7 张表（账号行保留）、回 0x36 `01`；不对 → 0x1A「密碼錯誤」；载荷不够长 → 静默。
    原版只在**还没进入游戏世界**时能这样用（选角色界面）；进入世界后发它，原版会崩，所以网络层不理会。
    """
    res = Result()
    arg = _password_arg(payload, 1)
    if arg is None:
        return res
    if arg.decode("latin1") != password:
        res.to_self.append((0x1A, _BAD_PASSWORD, False))
        return res
    for table in CHARACTER_TABLES:
        rows[table] = []
    res.deleted = True
    res.to_self.append((0x36, b"\x01", False))
    return res


def betray_stub(payload: bytes) -> Result:
    """C2S 0x67（客户端『背叛師門』确认框发）：原版处理函数一开头无条件回 0x1A「請從外掛上判門﹗」就返回，后面全是死代码。
    载荷 ≥ 5 字节才回（实测 0–4 字节静默）。真正的背叛师门入口是 `@bpsm`（jyserver/commands.py）。"""
    res = Result()
    if len(payload) >= 5:
        res.to_self.append((0x1A, _NO_BETRAY, False))
    return res


def password_check(password: str, payload: bytes, rows: dict | None = None) -> Result:
    """C2S 0x98。子指令（载荷首字节）：

    - 0D = **自宫**（2026-10-20 更正：以前误称二级密码验证）：`0D 长度 密码字节 [暗码，服务端不看]`：账号密码对 → `renwu.zigong` 置 1、回 0xB8 `10`（客户端提示「自宮成功」）；
      不对（含长度 0）→ 0x1A「密碼錯誤」；载荷不够长 → 静默；
    - 0F / 0E：载荷至少 6 字节：回 0xB8 `13` / `12` + 载荷第 2–6 字节（原样回显 5 字节）；
    - 其余子指令、载荷太短：静默（原版对某些过短的载荷会崩，这里不模仿）。
    """
    res = Result()
    if not payload:
        return res
    sub = payload[0]
    if sub == 0x0D:
        arg = _password_arg(payload, 1)
        if arg is None:
            return res
        if arg.decode("latin1") == password:
            res.zigong = True
            if rows and rows.get("renwu"):
                rows["renwu"][0]["zigong"] = "1"
            res.to_self.append((0xB8, b"\x10", False))
        else:
            res.to_self.append((0x1A, _BAD_PASSWORD, False))
    elif sub in (0x0F, 0x0E) and len(payload) >= 6:
        res.to_self.append((0xB8, bytes([0x13 if sub == 0x0F else 0x12]) + payload[1:6], False))
    return res
