"""网金封包编解码（无状态）。

线路模型（来源见 docs/协议模型.md；证据等级写在各处注释里）::

    帧(明文) = 魔数(2) + 长度 + opcode(1) + 参数
        短帧: 魔数 F4 44，长度 1 字节，= 整帧字节数（含魔数）
        长帧: 魔数 F5 B3，长度 2 字节小端，= 整帧字节数（含魔数）
    线路 S2C = XOR(key, 帧)
    线路 C2S = F6 11 <seq> + XOR(key, 帧)

密钥直接写在帧头里：key = A ^ 0xF4（短帧）或 A ^ 0xF5（长帧），其中 A 是线路上的
第一个魔数字节，所以解码不需要任何会话状态。编码时必须用客户端当前期望的密钥——
密钥会在会话中途更换，规则见 derive_key()。

两种帧格式都出现在同一方向上，由原服务端按包类型选择，客户端两种都接受，
所以 encode_* 的 wide 参数由调用者决定，默认按长度自动选。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MAGIC_SHORT = (0xF4, 0x44)  # 1 字节长度
MAGIC_LONG = (0xF5, 0xB3)  # 2 字节小端长度
C2S_PREFIX = (0xF6, 0x11)  # 仅客户端→服务端，后接 1 字节序号

# 短帧的单字节长度字段装得下的最大消息（opcode+参数）长度；loginp.exe 0x9dabc8 的阈值。
SHORT_MAX_MSG = 250

# 握手阶段的密钥。C2S 来自抓包（p[3]^0xF4），S2C 由首包头推断（见测试）；
# 之后的默认密钥来自抓包观察，0x7D 在服务端重启前后保持不变。
KEY_C2S_HANDSHAKE = 0x9E
KEY_S2C_HANDSHAKE = 0x9F
KEY_DEFAULT = 0x7D


class FrameError(ValueError):
    """帧头不合法、长度不合理，或消息放不进所选格式。"""


@dataclass(frozen=True)
class Frame:
    opcode: int
    payload: bytes
    key: int
    wide: bool  # True = 长帧(F5 B3, 2 字节长度)
    seq: int | None = None  # 仅 C2S
    raw: bytes = b""  # 线路上的原始字节（含 C2S 前缀）

    @property
    def total_length(self) -> int:
        """整帧字节数，等于帧里长度字段的值（不含 C2S 的 3 字节前缀）。"""
        return len(self.payload) + (5 if self.wide else 4)


def xor_bytes(data: bytes, key: int) -> bytes:
    return bytes(b ^ key for b in data)


def derive_key(seed: bytes) -> int:
    """由 4 字节种子算出新密钥。

    来源：loginp.exe 0x9db97c / 0x9db8b4 的反编译，并用解释器执行 19657 条指令得到
    系数；常数项最初反编译得 163，经真实流量校准改为 145（握手种子 a2 bc 28 37 →
    实际密钥 0x7d；换密钥种子 0e ae a5 31 → 0x0e，用 163 分别多出 18）。触发条件
    （loginp.exe 0x9db508）：收到类型 0x99 且载荷第 1 字节为 0x04 的帧，随后 4 字节是种子。
    """
    if len(seed) != 4:
        raise ValueError("seed must be 4 bytes")
    b0, b1, b2, b3 = seed
    return (138 * b0 + 307 * b1 + 93 * b2 + 78 * b3 + 145) % 217


def c2s_key(seq: int, base: int = KEY_DEFAULT) -> int:
    """服务端解 C2S 帧用的密钥：首包固定 0x9E，之后 = base XOR 序号。

    实测（2026-10，本机原版服务端，对序号 2/3/4/5 各试 256 个密钥字节，
    每个序号恰好只有 base^seq 能让服务端真正处理该帧）。
    base 初始 0x7D。收到 `99 04 <种子>` 换密钥帧后 base 是否变成 derive_key(种子) 尚未验证。
    """
    return KEY_C2S_HANDSHAKE if seq == 1 else (base ^ (seq & 0xFF))


def _plain_frame(opcode: int, payload: bytes, wide: bool) -> bytes:
    if not 0 <= opcode <= 0xFF:
        raise FrameError(f"opcode out of range: {opcode}")
    if not wide:
        total = 4 + len(payload)
        if total > 0xFF:
            raise FrameError(f"short frame too long ({total} > 255); use wide=True")
        return bytes(MAGIC_SHORT) + bytes([total, opcode]) + payload
    total = 5 + len(payload)
    if total > 0xFFFF:
        raise FrameError(f"wide frame too long ({total} > 65535)")
    return bytes(MAGIC_LONG) + total.to_bytes(2, "little") + bytes([opcode]) + payload


def _auto_wide(payload: bytes, wide: bool | None) -> bool:
    if wide is not None:
        return wide
    return 1 + len(payload) > SHORT_MAX_MSG


def encode_s2c(
    opcode: int,
    payload: bytes = b"",
    *,
    key: int = KEY_DEFAULT,
    wide: bool | None = None,
) -> bytes:
    """服务端→客户端。"""
    return xor_bytes(_plain_frame(opcode, payload, _auto_wide(payload, wide)), key)


def encode_c2s(
    opcode: int,
    payload: bytes = b"",
    *,
    key: int,
    seq: int,
    wide: bool | None = None,
) -> bytes:
    """客户端→服务端（测试和模拟客户端用）。长帧的 C2S 布局只是按对称性推断，未经抓包验证。"""
    body = xor_bytes(_plain_frame(opcode, payload, _auto_wide(payload, wide)), key)
    return bytes(C2S_PREFIX) + bytes([seq & 0xFF]) + body


# ---------------------------------------------------------------- 解码

_NEED_MORE = object()


def _header_info(a: int, b: int) -> tuple[int, bool]:
    """由线路上的前两个字节得到 (key, wide)；不是合法魔数就抛 FrameError。"""
    if a ^ b == MAGIC_SHORT[0] ^ MAGIC_SHORT[1]:  # 0xB0
        return a ^ MAGIC_SHORT[0], False
    if a ^ b == MAGIC_LONG[0] ^ MAGIC_LONG[1]:  # 0x46
        return a ^ MAGIC_LONG[0], True
    raise FrameError(f"bad frame magic: {a:02x} {b:02x}")


def peek_header(buf: bytes, offset: int = 0) -> tuple[int, bool, int] | None:
    """只看帧头，返回 (key, wide, 整帧字节数)；数据不够返回 None。不含 C2S 前缀。"""
    if len(buf) - offset < 2:
        return None
    key, wide = _header_info(buf[offset], buf[offset + 1])
    need = 4 if wide else 3
    if len(buf) - offset < need:
        return None
    if wide:
        total = ((buf[offset + 2] ^ key) | ((buf[offset + 3] ^ key) << 8))
    else:
        total = buf[offset + 2] ^ key
    return key, wide, total


def _decode_frame(buf: bytes, pos: int, c2s: bool):
    """尝试从 pos 解一帧。返回 (Frame, 消耗字节数)，数据不够返回 _NEED_MORE。"""
    start = pos
    seq = None
    if c2s:
        if len(buf) - pos < 3:
            return _NEED_MORE
        if (buf[pos], buf[pos + 1]) != C2S_PREFIX:
            raise FrameError(f"bad C2S prefix: {buf[pos]:02x} {buf[pos + 1]:02x}")
        seq = buf[pos + 2]
        pos += 3
    head = peek_header(buf, pos)
    if head is None:
        return _NEED_MORE
    key, wide, total = head
    min_total = 5 if wide else 4
    if total < min_total:
        raise FrameError(f"frame length {total} < {min_total}")
    if len(buf) - pos < total:
        return _NEED_MORE
    body = xor_bytes(buf[pos : pos + total], key)
    opcode = body[4] if wide else body[3]
    payload = body[5:] if wide else body[4:]
    end = pos + total
    frame = Frame(opcode, payload, key, wide, seq, bytes(buf[start:end]))
    return frame, end - start


class FrameReader:
    """流式拆帧：feed() 喂入任意切分的字节块，返回本次凑齐的完整帧。

    resync=True 时遇到非法帧头会丢 1 字节后继续找（计入 skipped）；
    否则抛 FrameError，缓冲区保持不变。
    """

    def __init__(self, direction: str, *, resync: bool = False):
        if direction not in ("c2s", "s2c"):
            raise ValueError("direction must be 'c2s' or 's2c'")
        self._c2s = direction == "c2s"
        self._resync = resync
        self._buf = bytearray()
        self.skipped = 0

    @property
    def pending(self) -> bytes:
        return bytes(self._buf)

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames: list[Frame] = []
        pos = 0
        buf = bytes(self._buf)
        while pos < len(buf):
            try:
                result = _decode_frame(buf, pos, self._c2s)
            except FrameError:
                if not self._resync:
                    del self._buf[:pos]
                    raise
                pos += 1
                self.skipped += 1
                continue
            if result is _NEED_MORE:
                break
            frame, used = result
            frames.append(frame)
            pos += used
        del self._buf[:pos]
        return frames


def decode_stream(
    data: bytes, direction: str, *, resync: bool = False
) -> tuple[list[Frame], bytes, int]:
    """一次性解整段字节流，返回 (帧列表, 末尾不完整的剩余字节, 重同步丢弃的字节数)。"""
    reader = FrameReader(direction, resync=resync)
    frames = reader.feed(data)
    return frames, reader.pending, reader.skipped


def join_frames(frames: Iterable[bytes]) -> bytes:
    """把若干已编码的帧拼成一个 TCP 块（模拟粘包）。"""
    return b"".join(frames)
