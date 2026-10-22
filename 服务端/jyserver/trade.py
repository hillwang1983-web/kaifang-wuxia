"""玩家之间的交易：C2S 0x1C 请求 / 0x1E 放物品 / 0x1F 放金钱 / 0x1D 锁定·确认·取消。

行为依据 2026-10 对本机原版服务端、用两个号（tools/raw_probe.py）的实测，详见 docs/丢弃回收交易.md。
原版的交易子程序有 7000 行反编译，这里只复现实测到的主路径；原版的几处怪行为（见 deliver()）照搬，没测到的情形不做。

会话：A 发 0x1C 给 B 就建好会话（B 回不回 0x1C 都一样，B 立即可以放东西、锁定）。会话里每个人有 offers（物品列表）和 money。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import ItemTable

Out = tuple[int, int, bytes, bool]  # (收件人 jyid, opcode, 载荷, 是否长帧)

_NO_TRADE_MSG = bytes.fromhex("64 a6 b9 aa ab ab 7e a4 a3 af e0 a5 e6 a9 f6")  # 0x1A: 64 +「此物品不能交易」
_NO_ITEM_MSG = bytes.fromhex("64 aa ab ab 7e a4 a3 a8 ac")  # 0x1A: 64 +「物品不足」


def _i(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _le(n: int) -> bytes:
    return (n & 0xFFFFFFFF).to_bytes(4, "little")


@dataclass
class Session:
    a: int  # 发起人
    b: int
    offers: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # jyid -> [(物品ID, 耐久字节)]
    money: dict[int, int] = field(default_factory=dict)
    slots: dict[int, bytes] = field(default_factory=dict)  # 收件人 jyid -> 压住没发的 0x21 载荷（见 deliver）
    locks: int = 0
    confirms: int = 0

    def other(self, jyid: int) -> int:
        return self.b if jyid == self.a else self.a


class Trades:
    def __init__(self) -> None:
        self.by_player: dict[int, Session] = {}

    def drop(self, jyid: int) -> None:
        """玩家下线 / 会话结束：把会话从双方身上摘掉（对方不通知——原版怎么做没测）。"""
        s = self.by_player.get(jyid)
        if s is not None:
            self.by_player.pop(s.a, None)
            self.by_player.pop(s.b, None)

    @staticmethod
    def deliver(s: Session, frames: list[Out]) -> list[Out]:
        """原版发包子程序的怪行为（实测）：每个收件人有一个槽。要发 0x21（金钱通知）而槽是空的，就压进槽里不发；
        槽里有东西时，**任何**要发给他的交易帧（0x1F/0x20/0x21/0x22/0x23/0x82）都不发了，改发槽里的 0x21，
        后面多带 3 字节 `f4 44 <被顶掉那帧的长度字节>`（拼包时多带的帧头残渣；0x21 自己的长度字节是 0x0F），槽清空。0x1A 文字消息不走这条路。
        于是第一次放金钱时对方什么也收不到，要等下一条交易帧来「顶」它。"""
        out: list[Out] = []
        for jyid, op, payload, wide in frames:
            if op == 0x1A:
                out.append((jyid, op, payload, wide))
            elif jyid in s.slots:
                length = 0x0F if op == 0x21 else 4 + len(payload)  # 0x21 帧的长度字节固定 0x0F
                out.append((jyid, 0x21, s.slots.pop(jyid) + bytes([0xF4, 0x44, length]), False))
            elif op == 0x21:
                s.slots[jyid] = payload
            else:
                out.append((jyid, op, payload, wide))
        return out

    # ---- 0x1C 请求
    def request(self, sender: int, target: int, online: dict[int, dict]) -> list[Out]:
        """载荷 = 对方 jyid(LE32)。对方不在线 / 是自己 / 双方有一方已在别的会话里：静默忽略。

        回 0x1F = 发起人 + 对方，给双方；同图其他所有人（不含请求者）收到两条 0x82 = jyid + 08 00（先请求者、后对方，
        是「正在交易」的状态标记）。对方回头也发 0x1C 给你，只是把同样的帧再发一遍。
        """
        if target == sender or sender not in online or target not in online:
            return []
        s = self.by_player.get(sender)
        t = self.by_player.get(target)
        if s is None and t is None:
            s = Session(sender, target)
            self.by_player[sender] = self.by_player[target] = s
        elif s is None or s is not t:
            return []
        out: list[Out] = [(sender, 0x1F, _le(sender) + _le(target), False), (target, 0x1F, _le(sender) + _le(target), False)]
        sender_map = _i(online[sender]["renwu"][0].get("map"))
        for j, rows in online.items():
            if j != sender and _i(rows["renwu"][0].get("map")) == sender_map:
                out += [(j, 0x82, _le(sender) + b"\x08\x00", False), (j, 0x82, _le(target) + b"\x08\x00", False)]
        return self.deliver(s, out)

    # ---- 0x1E 放物品
    def add_item(self, sender: int, payload: bytes, table: ItemTable) -> list[Out]:
        """载荷 = 01 物品ID(LE32) 耐久(1)，至少 6 字节。「交易」列 = 0 的物品只有发送者收到 0x1A「此物品不能交易」。
        其余一律收下（**不检查背包里有没有**，到成交时才查），给双方 0x20 = 发送者 + 01 + 物品ID + 耐久 + 01。"""
        s = self.by_player.get(sender)
        if s is None or len(payload) < 6 or payload[0] != 0x01:
            return []
        item, dur = int.from_bytes(payload[1:5], "little"), payload[5]
        if item in table.no_trade:
            return [(sender, 0x1A, _NO_TRADE_MSG, False)]
        s.offers.setdefault(sender, []).append((item, dur))
        body = _le(sender) + b"\x01" + payload[1:5] + bytes([dur]) + b"\x01"
        return self.deliver(s, [(s.a, 0x20, body, False), (s.b, 0x20, body, False)])

    # ---- 0x1F 放金钱
    def set_money(self, sender: int, payload: bytes) -> list[Out]:
        """载荷 = 金钱(LE32)（后面多的字节不看，不足 4 字节忽略）。记在发送者名下，成交时用。通知帧 0x21 = 发送者 + 金钱，
        但经过 deliver() 的「压帧」怪行为，见那里。"""
        s = self.by_player.get(sender)
        if s is None or len(payload) < 4:
            return []
        value = int.from_bytes(payload[:4], "little")
        s.money[sender] = value
        body = _le(sender) + _le(value)
        return self.deliver(s, [(s.a, 0x21, body, False), (s.b, 0x21, body, False)])

    # ---- 0x1D 锁定 / 确认 / 取消
    def command(self, sender: int, payload: bytes, rows_of: dict[int, dict]) -> list[Out]:
        """载荷首字节：01 = 锁定、03 = 确认、00 = 取消。

        锁定：对方收到 0x23 01 <发送者>；会话里累计第 2 次锁定（不管谁锁的）时双方都收到 0x23 04（进入确认阶段），第 3 次起只通知。
        确认：累计第 1 次，对方收到 0x82 <发送者> 00 00；累计第 2 次（不管谁确认、有没有锁定过）执行成交，见 settle()。
        取消：双方收到 0x23 00 <发送者>，会话结束。"""
        s = self.by_player.get(sender)
        if s is None or not payload:
            return []
        other = s.other(sender)
        sub = payload[0]
        if sub == 0x01:
            s.locks += 1
            out: list[Out] = [(other, 0x23, b"\x01" + _le(sender), False)]
            if s.locks == 2:
                out += [(other, 0x23, b"\x04", False), (sender, 0x23, b"\x04", False)]
            return self.deliver(s, out)
        if sub == 0x03:
            s.confirms += 1
            if s.confirms == 1:
                return self.deliver(s, [(other, 0x82, _le(sender) + b"\x00\x00", False)])
            return self.settle(s, sender, rows_of)
        if sub == 0x00:
            out = [(s.a, 0x23, b"\x00" + _le(sender), False), (s.b, 0x23, b"\x00" + _le(sender), False)]
            self.drop(sender)
            return self.deliver(s, out)
        return []

    def settle(self, s: Session, executor: int, rows_of: dict[int, dict]) -> list[Out]:
        """第 2 次确认的人（executor）触发成交。实测规则：

        - 双方金钱出价都不超过各自金钱，否则整笔作废（不转任何东西、不报错）；
        - 有人出了金钱（>0）：先把双方出价的物品都查一遍，任何一件背包里不够（同一物品出价几次就要几件）→ 整笔作废，
          只有 executor 收到 0x1A「物品不足」；
        - 没人出金钱：按 executor 的物品、再对方的物品逐件搬，遇到第一件不够的就停（前面已经搬了的不退），executor 收到 0x1A；
        - 金钱按差额转（A 出 x、B 出 y，A 净付 x−y）。物品每次出价搬 1 件。
        结束一律双方收到 0x22（空）；没有物品错误时再给对方 0x82 <executor> 00 00。会话结束。"""
        partner = s.other(executor)
        out: list[Out] = [(executor, 0x22, b"", False), (partner, 0x22, b"", False)]
        self.drop(executor)
        done: list[Out] = [(partner, 0x82, _le(executor) + b"\x00\x00", False)]
        if any(s.money.get(j, 0) > _i(rows_of[j]["renwu"][0].get("jy_money")) for j in (s.a, s.b)):
            return self.deliver(s, out + done)
        plans = [(executor, partner), (partner, executor)]
        failed = False
        if any(s.money.get(j, 0) > 0 for j in (s.a, s.b)):
            need: dict[tuple[int, int], int] = {}
            for giver, _ in plans:
                for item, _dur in s.offers.get(giver, []):
                    need[(giver, item)] = need.get((giver, item), 0) + 1
            if any(_owned(rows_of[g], item) < n for (g, item), n in need.items()):
                return self.deliver(s, out) + [(executor, 0x1A, _NO_ITEM_MSG, False)]
        for giver, taker in plans:
            for item, _dur in s.offers.get(giver, []):
                if not _move_one(rows_of[giver], rows_of[taker], item):
                    failed = True
                    break
            if failed:
                break
        if failed:
            return self.deliver(s, out) + [(executor, 0x1A, _NO_ITEM_MSG, False)]
        diff = s.money.get(s.a, 0) - s.money.get(s.b, 0)
        if diff:
            ra, rb = rows_of[s.a]["renwu"][0], rows_of[s.b]["renwu"][0]
            ra["jy_money"] = str(_i(ra.get("jy_money")) - diff)
            rb["jy_money"] = str(_i(rb.get("jy_money")) + diff)
        return self.deliver(s, out + done)


def _owned(rows: dict, item_id: int) -> int:
    return sum(_i(r.get("shuliang")) for r in rows.get("item") or [] if _i(r.get("item_id")) == item_id)


def _move_one(src: dict, dst: dict, item_id: int) -> bool:
    row = next((r for r in src.get("item") or [] if _i(r.get("item_id")) == item_id and _i(r.get("shuliang")) > 0), None)
    if row is None:
        return False
    left = _i(row["shuliang"]) - 1
    if left > 0:
        row["shuliang"] = str(left)
    else:
        src["item"].remove(row)
    jyid = str(dst["renwu"][0].get("jyid"))
    for r in dst.setdefault("item", []):
        if _i(r.get("item_id")) == item_id and _i(r.get("state") or 200) == 200:
            r["shuliang"] = str(_i(r.get("shuliang")) + 1)
            break
    else:
        dst["item"].append({"jyid": jyid, "item_id": str(item_id), "shuliang": "1", "state": "200"})
    return True
