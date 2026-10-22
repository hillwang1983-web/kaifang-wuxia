"""组织（帮派）：C2S 0x45 创立、0x4E 招收、0x4F 应答 / 成员列表、0x50 踢人、0x51 退出、0x56 查询、0x02 子类型 05 组织聊天。

行为依据 2026-10 用三个模拟客户端对原版的实测（tools/org_compare.py），详见 docs/组织.md。
原版的状态是两样东西，新服务端用同样的结构，连怪行为一起照搬：
- 全局组织数组（号码 = 下标 + 1，只增不删）：名字（原始字节）、创立者 jyid、成员 jyid 数组（int，可重复）；
- 每个玩家一个「组织号字符串」（player+0x450，缺省 "0"）。**它不随下线清掉**（同一进程里重新登录还在），原版重启才没。
  踢人会把它写成 " 0"（带前导空格）——数值上还是 0，但和 "0" 字符串比较不相等，所以被踢的人既不能创立也不能被招收。
组织号数值为 0（或越界）时原版里数组下标出错，这一次指令什么都不做、不报错，这里同样静默。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .state import to_big5

Out = tuple[int, int, bytes, bool]  # (收件人 jyid, opcode, 载荷, 是否长帧)

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "org_recruit_template.hex"
_ORGID_AT = 28  # 招收帧模板里组织号（LE16）的位置
_TEMPLATE_LEN = 1802

# 文字都是原版发出去的 BIG5 字节（实测），不经转换
_MSG = {
    "have": bytes.fromhex("a4 77 a6 b3 b2 d5 c2 b4 a1 54"),  # 已有組織﹗
    "dup": bytes.fromhex("b2 d5 c2 b4 a6 57 ad ab ce 60"),  # 組織名重複
    "target_has": bytes.fromhex("b9 ef a4 e8 a4 77 a6 b3 b2 d5 c2 b4 a1 54"),  # 對方已有組織﹗
    "leader_only": bytes.fromhex("b2 d5 c2 b4 b3 d0 a5 df aa cc a4 7e af e0 a9 db a6 ac c0 b0 b2 b3 a1 54"),  # 組織創立者才能招收﹗
    "not_online": bytes.fromhex("a6 b9 aa b1 ae 61 a4 a3 a6 62 bd 75 a4 57 a1 54"),  # 此玩家不在線上﹗
}
_CREATED = bytes.fromhex("a1 41 b3 d0 a5 df a4 46 b2 d5 c2 b4 a1 52")  # ，創立了組織﹕
_QUERY_REPLY = {0x06: b"\x05", 0x04: b"\x03", 0x05: b"\x04"}  # C2S 0x56 子类型 → S2C 0x39（长帧）；和组织状态无关


def load_template(path: Path = TEMPLATE_PATH) -> bytes:
    """招收帧里组织号之后的固定模板（原版程序里的一整段常量，1802 字节，组织号处先填 0）。读不到就用同长度的零填充。"""
    try:
        data = bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        data = b"\x00" * _TEMPLATE_LEN
    return data


def _le(n: int) -> bytes:
    return (n & 0xFFFFFFFF).to_bytes(4, "little")


def _text(jyid: int, key: str) -> Out:
    return (jyid, 0x1A, b"\x64" + _MSG[key], False)


def _val(s: str) -> int:
    """VB 的 Val：取字符串开头的数字（前导空格忽略），不是数字就 0。"""
    s = s.strip()
    n = 0
    for ch in s:
        if not ch.isdigit():
            break
        n = n * 10 + int(ch)
    return n


@dataclass
class Org:
    name: bytes
    leader: int
    members: list[int] = field(default_factory=list)


class Orgs:
    def __init__(self, template: bytes | None = None) -> None:
        self.orgs: list[Org] = []
        self.org_of: dict[int, str] = {}  # jyid -> 组织号字符串，缺省 "0"
        self.template = load_template() if template is None else template

    # ---- 辅助
    def _id(self, jyid: int) -> str:
        return self.org_of.get(jyid, "0")

    def _org(self, jyid: int) -> Org | None:
        """玩家当前组织号对应的组织；号码为 0 / 越界 → None（原版下标出错，这次指令什么也不做）。"""
        n = _val(self._id(jyid))
        return self.orgs[n - 1] if 1 <= n <= len(self.orgs) else None

    @staticmethod
    def _all(online: dict[int, str], op: int, payload: bytes) -> list[Out]:
        """全服广播（所有已进入世界的玩家）。"""
        return [(j, op, payload, False) for j in online]

    @staticmethod
    def _drop_first(org: Org, jyid: int) -> None:
        if jyid in org.members:
            org.members.remove(jyid)

    # ---- 0x45 创立
    def create(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """载荷 = 组织名（原始字节，不转码；空 = 原版崩溃，这里静默）。自己已有组织（组织号字符串 != "0"）→ 「已有組織﹗」；
        名字和现有组织完全相同（区分大小写）→ 「組織名重複」；否则新建（创立者也在成员数组里），自己的组织号 = 新号码，
        自己收 0x4F = 自己 jyid + 组织号(LE16) + 名字，全服收 0x14（长帧）= 0e + <自己的名字> + 「，創立了組織﹕」 + 名字。"""
        if me not in online or not payload:
            return []
        if self._id(me) != "0":
            return [_text(me, "have")]
        if any(o.name == payload for o in self.orgs):
            return [_text(me, "dup")]
        self.orgs.append(Org(payload, me, [me]))
        n = len(self.orgs)
        self.org_of[me] = str(n)
        notice = b"\x0e" + to_big5(online[me]) + _CREATED + payload
        return [(me, 0x4F, _le(me) + n.to_bytes(2, "little") + payload, False)] + [(j, 0x14, notice, True) for j in online]

    # ---- 0x4E 招收
    def recruit(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """载荷前 4 字节 = 对方 jyid（LE32），至少 4 字节。自己的组织号 0 / 越界 → 静默；自己不是该组织的创立者 → 「組織創立者才能招收﹗」；
        对方不在线 → 静默；对方组织号字符串 != "0" → 「對方已有組織﹗」；否则对方收 0x54（长帧）= 自己 jyid + 组织名长度(1) + 组织名 +
        固定模板（组织号 LE16 嵌在里面）。对方要自己发 0x4F 01 <招收人 jyid> 才算加入。"""
        if me not in online or len(payload) < 4:
            return []
        org = self._org(me)
        if org is None:
            return []
        if org.leader != me:
            return [_text(me, "leader_only")]
        target = int.from_bytes(payload[:4], "little")
        if target not in online:
            return []
        if self._id(target) != "0":
            return [_text(me, "target_has")]
        tpl = bytearray(self.template)
        tpl[_ORGID_AT : _ORGID_AT + 2] = _val(self._id(me)).to_bytes(2, "little")
        return [(target, 0x54, _le(me) + bytes([len(org.name) & 0xFF]) + org.name + bytes(tpl), True)]

    # ---- 0x4F 应答 / 列表
    def reply(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """子类型 01 = 加入：后面 4 字节招收人 jyid（不足 5 字节静默）。招收人在线 → 自己的组织号字符串 := 招收人的（**不检查招收人是不是创立者、
        有没有发过招收**），然后组织号 0 / 越界 → 静默；否则自己 jyid 追加到该组织的成员数组（已在里面也照追加，所以会有重复），
        全服收 0x55 = 自己 jyid + `01` + 组织号(LE16)。子类型 07 = 成员列表：自己的组织号 0 / 越界 → 静默；否则自己收 0xAD = `10` +
        每个**在线的、不是自己的**成员一项 `05 名字长度 名字(BIG5)`（成员数组里有重复就列重复）。"""
        if me not in online or not payload:
            return []
        if payload[0] == 0x01:
            if len(payload) < 5:
                return []
            inviter = int.from_bytes(payload[1:5], "little")
            if inviter not in online:
                return []
            self.org_of[me] = self._id(inviter)
            org = self._org(me)
            if org is None:
                return []
            org.members.append(me)
            return self._all(online, 0x55, _le(me) + b"\x01" + _val(self._id(me)).to_bytes(2, "little"))
        if payload[0] == 0x07:
            org = self._org(me)
            if org is None:
                return []
            body = b""
            for m in org.members:
                if m != me and m in online:
                    name = to_big5(online[m])
                    body += b"\x05" + bytes([len(name) & 0xFF]) + name
            return [(me, 0xAD, b"\x10" + body, False)]
        return []

    # ---- 0x50 踢人
    def kick(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """载荷 = 4 字节（不看）+ 对方名字（BIG5 字节，和在线玩家的名字完全相同），至少 1 字节。**不查是不是创立者**，谁都能踢任何在线玩家：
        找不到名字 → 自己收「此玩家不在線上﹗」；自己的组织号 0 / 越界 → 静默；否则从自己组织的成员数组里删掉对方（第一个，没有也行），
        对方的组织号字符串 := " 0"，全服收 0x56 = 自己 jyid + 对方 jyid。"""
        if me not in online or not payload:
            return []
        name = payload[4:]
        target = next((j for j, n in online.items() if to_big5(n) == name), None)
        if target is None:
            return [_text(me, "not_online")]
        org = self._org(me)
        if org is None:
            return []
        self._drop_first(org, target)
        self.org_of[target] = " 0"
        return self._all(online, 0x56, _le(me) + _le(target))

    # ---- 0x51 退出
    def leave(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """子类型 01：自己的组织号 0 / 越界 → 静默；否则从成员数组里删掉自己（第一个），组织号字符串 := "0"，全服收 0x57 = 自己 jyid。
        创立者退出组织不会解散它，也不会换创立者（创立者字段不变，但他的组织号是 0 了，没法再招收）。"""
        if me not in online or not payload or payload[0] != 0x01:
            return []
        org = self._org(me)
        if org is None:
            return []
        self._drop_first(org, me)
        self.org_of[me] = "0"
        return self._all(online, 0x57, _le(me))

    # ---- 0x56 查询
    def query(self, me: int, payload: bytes, online: dict[int, str]) -> list[Out]:
        """子类型 06 / 04 / 05 → 自己收 0x39（长帧）= 05 / 03 / 04，固定值；其他静默。"""
        if me not in online or not payload or payload[0] not in _QUERY_REPLY:
            return []
        return [(me, 0x39, _QUERY_REPLY[payload[0]], True)]

    # ---- 0x02 子类型 05 组织聊天
    def chat(self, me: int, text: bytes, online: dict[int, str]) -> list[Out]:
        """text = 子类型 05 之后的内容，至少 1 字节。发给自己组织的成员数组里每一项（**重复项收重复**）中在线的、不是自己的人，
        S2C 0x04 = 05 + 发送者 jyid + 内容；不扣饮食饮水。自己的组织号 0 / 越界（含被踢的人）→ 静默。"""
        if me not in online or not text:
            return []
        org = self._org(me)
        if org is None:
            return []
        return [(m, 0x04, b"\x05" + _le(me) + text, False) for m in org.members if m != me and m in online]
