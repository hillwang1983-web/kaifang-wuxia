"""钱庄（随身钱庄）：C2S 0x23 打开、0x22 存 / 取物品、0x71 物品信息。

行为依据 2026-10 对本机原版服务端的实测（tools/bank_probe.py 的前身脚本，见 docs/钱庄.md）和 0x891670 的反编译。

库表 `qianzhuang(id, jyid, wupin, shuliang)`：每个账号一行以上；`wupin=0` 那行是历史遗留（shuliang 总是 0，打开钱庄时
放在清单最前面的 4 字节里），其余每行一种物品。新服务端把它们放在 rows['qianzhuang']（列表，顺序 = 库里 id 升序）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import ItemTable

Frame = tuple[int, bytes, bool]

# 每次存 / 取之后原版都会发的两条固定帧：物品 48015（随身钱庄）的「使用确认」和「新增」，内容恒定
_USE_ACK = (0x0B, bytes.fromhex("8f bb 00 00 c8 01"), False)
_ITEM_ADD = (0x77, bytes.fromhex("8f bb 00 00 c8 01"), False)
_DEPOSIT_SHORT = bytes.fromhex("64 aa ab ab 7e bc c6 b6 71 a4 a3 a8 ac a1 41 bd d0 ad ab b5 6e a1 54")  # 物品數量不足，請重登﹗
_WITHDRAW_SHORT = bytes.fromhex("64 bc c6 b6 71 a4 a3 a8 ac")  # 數量不足
_WITHDRAW_TAIL = bytes.fromhex("ee dc 00 00")  # 取物回包 0x27 末尾的 4 字节，实测恒定，含义不明


@dataclass
class Result:
    to_self: list[Frame] = field(default_factory=list)


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def owned(rows: dict, item_id: int) -> int:
    return sum(_i(r.get("shuliang")) for r in rows.get("item") or [] if _i(r.get("item_id")) == item_id)


def banked(rows: dict, item_id: int) -> int:
    return sum(_i(r.get("shuliang")) for r in rows.get("qianzhuang") or [] if _i(r.get("wupin")) == item_id)


def _take_from_bag(rows: dict, item_id: int, qty: int) -> None:
    for r in list(rows.get("item") or []):
        if qty <= 0:
            break
        if _i(r.get("item_id")) != item_id:
            continue
        have = _i(r.get("shuliang"))
        used = min(have, qty)
        qty -= used
        if have - used > 0:
            r["shuliang"] = str(have - used)
        else:
            rows["item"].remove(r)  # 数量用光，整行删掉（原版库里也是这样）


def _put_in_bag(rows: dict, jyid: str, item_id: int, qty: int) -> None:
    for r in rows.setdefault("item", []):
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200:
            r["shuliang"] = str(_i(r.get("shuliang")) + qty)
            return
    rows["item"].append({"jyid": jyid, "item_id": str(item_id), "shuliang": str(qty), "state": "200"})


def listing(rows: dict, table: ItemTable) -> Frame:
    """S2C 0x28（长帧）= wupin=0 行的数 LE32 + 逐种物品 [物品ID LE32][耐久][数量 LE16]，**最新存的排最前**。"""
    bank = rows.get("qianzhuang") or []
    head = next((_i(r.get("shuliang")) for r in bank if _i(r.get("wupin")) == 0), 0)
    body = b"".join(
        _i(r["wupin"]).to_bytes(4, "little") + bytes([table.of(_i(r["wupin"]))]) + (_i(r["shuliang"]) & 0xFFFF).to_bytes(2, "little")
        for r in reversed(bank)
        if _i(r.get("wupin")) != 0 and _i(r.get("shuliang")) > 0
    )
    return (0x28, head.to_bytes(4, "little") + body, True)


def open_bank(rows: dict, table: ItemTable) -> Result:
    return Result([listing(rows, table)])


def item_info(payload: bytes) -> Result:
    """C2S 0x71：物品ID(LE32)+…（至少 5 字节）→ S2C 0x88（短帧）= 物品ID + `c8 00 00 00 00`。对任何 ID 都这样回。"""
    if len(payload) < 5:
        return Result()
    return Result([(0x88, payload[:4] + bytes.fromhex("c8 00 00 00 00"), False)])


def transfer(rows: dict, table: ItemTable, payload: bytes) -> Result:
    """C2S 0x22：子类型(1) 物品ID(LE32) 耐久(1，被忽略) 数量(LE16)。子类型 00 = 存入钱庄，01 = 取出。

    存：背包里不够 → 只回 0x1A「物品數量不足，請重登﹗」+ 固定的 0x77；够（含数量 0）→ 背包扣掉、钱庄加上，
    回 0x0B + 0x77（固定）+ 0x27 = 00 物品ID 数量 当前金钱(LE32) 耐久（取自物品表）。
    取：钱庄里不够 → 0x0B、0x1A「數量不足」、0x77；够 → 钱庄扣掉、背包加上，回 0x0B + 0x77 + 0x27 = 01 物品ID 数量 ee dc 00 00，
    再把新的钱庄清单 0x28 刷给客户端。
    """
    res = Result()
    if len(payload) < 8 or payload[0] not in (0, 1):
        return res
    sub = payload[0]
    item_id = int.from_bytes(payload[1:5], "little")
    qty = int.from_bytes(payload[6:8], "little")
    renwu = rows["renwu"][0]
    jyid = str(renwu.get("jyid"))
    bank = rows.setdefault("qianzhuang", [])
    if sub == 0:
        if item_id == 0 or owned(rows, item_id) < qty:
            res.to_self += [(0x1A, _DEPOSIT_SHORT, False), _ITEM_ADD]
            return res
        if qty > 0:
            _take_from_bag(rows, item_id, qty)
            for r in bank:
                if _i(r.get("wupin")) == item_id:
                    r["shuliang"] = str(_i(r["shuliang"]) + qty)
                    break
            else:
                bank.append({"jyid": jyid, "wupin": str(item_id), "shuliang": str(qty)})
        body = bytes([0]) + item_id.to_bytes(4, "little") + qty.to_bytes(2, "little") + _i(renwu.get("jy_money")).to_bytes(4, "little") + bytes([table.of(item_id)])
        res.to_self += [_USE_ACK, _ITEM_ADD, (0x27, body, False)]
        return res
    if item_id == 0 or banked(rows, item_id) < qty:
        res.to_self += [_USE_ACK, (0x1A, _WITHDRAW_SHORT, False), _ITEM_ADD]
        return res
    for r in list(bank):
        if _i(r.get("wupin")) == item_id and qty > 0:
            left = _i(r["shuliang"]) - qty
            if left > 0:
                r["shuliang"] = str(left)
            else:
                bank.remove(r)
            break
    if qty > 0:
        _put_in_bag(rows, jyid, item_id, qty)
    body = bytes([1]) + item_id.to_bytes(4, "little") + qty.to_bytes(2, "little") + _WITHDRAW_TAIL
    res.to_self += [_USE_ACK, _ITEM_ADD, (0x27, body, False), listing(rows, table)]
    return res
