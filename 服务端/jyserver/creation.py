"""新建角色：C2S 0x76（摇点）、0x20（报名字）、长 0x19（确认属性并进游戏）。

流程（2026-10 对原版实测 + 0x60bcd7 / 0x60cc0e 反编译，tools/create_probe.py）：

  1. 0x01 登录一个**还没有角色**的账号 → 原版回另一条握手（模板 A，33 字节、没有尾部 00），把密钥换成
     derive_key(种子 a2 bc 08 5f) = 0x34：此后 S2C 帧都用 0x34，C2S 密钥 = 0x34 XOR 序号。
  2. 0x76 摇点：回 0x5A，7 个 15..25 的数，总和 140（可反复摇）。
  3. 0x20：载荷 = 1 字节（含义未知）+ 名字字节。名字已被占用 → 回 `25 01`；否则回 `25 00`，并
     `insert into renwu (jyid,name)` 等五张表——**只写 jyid 和名字，其余列全靠表结构的默认值**。
  4. 长 0x19（原版里「载荷恰好 1 字节」的启动登录之外的另一种形态，只有刚建好、还没进过游戏的号才接受；
     已有角色的号发这个会被记日志并断开）：

         [0]            未知（实测发 00）
         [1:3]          出生地图 LE16（实测 e8 0c = 3304）
         [3]            名字长度 N        [4:4+N]     名字
         [4+N]          昵称长度 M        [5+N:5+N+M] 昵称
         之后 11 字节   臂力 胆识 悟性 富源 定力 机敏 根骨（总和必须 ≤145，否则原版静默放弃）、
                        头像、模式、生日月、生日日

     原版据此逐列 `update renwu`，并且：sex = 1（头像 1..4）否则 2；ysbili/yswuxing/ysjimin/ysgengu =
     臂力/悟性/机敏/根骨；account.state = 1；按出生地图给出生坐标；再给新人物品（config/新人上线.ini）。
     然后照常发登录序列。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS_PATH = ROOT / "data" / "defaults.json"

# 出生地图 -> 出生坐标（原版硬编码，其它地图不改坐标，保持表默认的 0,0）
START_POSITIONS: dict[int, tuple[int, int]] = {3304: (702, 386), 8105: (1346, 462), 1305: (751, 461), 2802: (447, 475)}
ATTR_COLUMNS = ("str", "crg", "wint", "luk", "dex", "agi", "vit")  # 臂力 胆识 悟性 富源 定力 机敏 根骨
ATTR_TOTAL_MAX = 145

# config/新人上线.ini 找不到时的备用值（取自本机原版配置）
DEFAULT_STARTER = [(18072, 1), (15080, 1), (14056, 1), (13066, 1), (48022, 1), (48631, 1), (12130, 1), (11047, 1),
                   (27058, 1), (26028, 1), (58182, 10), (40145, 1)]


def load_defaults(path: Path = DEFAULTS_PATH) -> dict[str, dict[str, str | None]]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_starter_items(config_dir: str | Path | None) -> list[tuple[int, int]]:
    """读 新人上线.ini 的 `物品=`、`数量=`（逗号分隔，GBK）。"""
    if config_dir:
        p = Path(config_dir) / "新人上线.ini"
        if p.exists():
            vals: dict[str, str] = {}
            for line in p.read_bytes().decode("gbk", errors="replace").splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip()
            try:
                ids = [int(x) for x in vals["物品"].split(",") if x.strip()]
                qty = [int(x) for x in vals["数量"].split(",") if x.strip()]
                return list(zip(ids, qty))
            except (KeyError, ValueError):
                pass
    return list(DEFAULT_STARTER)


def blank_rows(defaults: dict, jyid: int, account: dict) -> dict:
    """只有账号、还没有角色的 rows。"""
    return {"renwu": [], "char_equip": [], "jineng": [], "kf": [], "item": [], "account": [account]}


def new_account_row(defaults: dict, jyid: int) -> dict:
    row = {k: ("" if v is None else v) for k, v in defaults.get("account", {}).items()}
    row.update(jyid=str(jyid), state="1", gm_lvl="0", shangchengdianshu="0")
    return row


def create_character_rows(defaults: dict, rows: dict, jyid: int, name: str) -> None:
    """0x20 成功：补上 renwu / char_equip / jineng（原版同时插 ypsx / zssj，那两张表这里不用）。"""
    renwu = {k: v for k, v in defaults["renwu"].items()}
    renwu.update(jyid=str(jyid), name=name)
    rows["renwu"] = [renwu]
    rows["char_equip"] = [{**defaults["char_equip"], "jyid": str(jyid)}]
    rows["jineng"] = [{**defaults["jineng"], "jyid": str(jyid)}]
    rows["biaoji"] = [{"jyid": str(jyid), "biaoji": "0", "zhuangtai": "0"}]  # 实测：原版建号时插一条 (0, 0) 标记行


@dataclass
class CreateRequest:
    map: int
    name: bytes
    nick: bytes
    attrs: tuple[int, ...]
    head: int
    mode: int
    month: int
    day: int


def parse_long_start(payload: bytes) -> CreateRequest | None:
    """解析长 0x19。长度不够、总和超过 145 都返回 None（原版是静默放弃）。"""
    if len(payload) < 5:
        return None
    n = payload[3]
    if len(payload) < 5 + n:
        return None
    m = payload[4 + n]
    if len(payload) < n + m + 16:
        return None
    name = payload[4 : 4 + n]
    nick = payload[5 + n : 5 + n + m]
    rest = payload[5 + n + m : 5 + n + m + 11]
    attrs = tuple(rest[:7])
    if sum(attrs) > ATTR_TOTAL_MAX:
        return None
    return CreateRequest(int.from_bytes(payload[1:3], "little"), name, nick, attrs, rest[7], rest[8], rest[9], rest[10])


def apply_create(rows: dict, req: CreateRequest, starter: list[tuple[int, int]]) -> None:
    """原版 0x60cc0e 里那一串 `update renwu set …`，外加出生坐标、account.state、新人物品。"""
    renwu = rows["renwu"][0]
    renwu["map"] = str(req.map)
    renwu["name"] = req.name.decode("gbk", errors="replace")
    renwu["nickname"] = req.nick.decode("gbk", errors="replace")
    renwu["head_image"], renwu["mode"] = str(req.head), str(req.mode)
    renwu["b_month"], renwu["b_day"] = str(req.month), str(req.day)
    for col, v in zip(ATTR_COLUMNS, req.attrs):
        renwu[col] = str(v)
    renwu["sex"] = "1" if req.head in (1, 2, 3, 4) else "2"
    str_, _crg, wint, _luk, dex, agi, vit = req.attrs
    renwu["ysbili"], renwu["yswuxing"], renwu["ysjimin"], renwu["ysgengu"] = str(str_), str(wint), str(agi), str(vit)
    if req.map in START_POSITIONS:
        renwu["x"], renwu["y"] = (str(v) for v in START_POSITIONS[req.map])
    if rows.get("account"):
        rows["account"][0]["state"] = "1"
    jyid = renwu["jyid"]
    rows["item"] = [{"jyid": jyid, "item_id": str(i), "shuliang": str(q), "state": "200"} for i, q in starter]
