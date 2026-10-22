#!/usr/bin/env python3
"""客户端 <-> 服务端通信接口覆盖表：网金复刻服务端 opcodes.py 里的每个 C2S / S2C opcode 对应到 jyclient 的方法 / 状态、网关操作、页面入口。

    python api_map.py          # 打印覆盖表；有 opcode 没登记、或登记的方法不存在 -> 退出码 1

分三类：
  done   已封装并在隔离服务端上测过（括号里是方法 / 状态 / 网关 op / 页面入口）
  none   服务端自己没有实现（战斗、轻频聊天、VIP 其它子指令…），客户端没有可对照的行为，只能用 JyClient.send(类型, 载荷) 手发
  ignore S2C 里只需要看一眼、不影响客户端状态的帧
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jyclient import JyClient  # noqa: E402

# C2S：opcode -> (状态, 方法 / 网关 op / 页面入口)
C2S = {
    0x01: ("done", "login(jyid, password) · 网关 login · 登录栏（账号 + 密码）"),
    0x19: ("done", "start() / create_enter(...) · 登录后自动 / 新建角色浮层"),
    0x20: ("done", "create_name(name) · 网关 create_name · 新建角色浮层"),
    0x76: ("done", "roll() · 网关 roll · 新建角色浮层「摇点」"),
    0x33: ("done", "delete_role(password) · 网关 delete_role（单开连接，不进世界）· 登录栏「删角色」"),
    0x02: ("done", "say(text) / org_chat(text) · 网关 say ch=public|org · 聊天框频道"),
    0x03: ("done", "whisper(jyid, text) · 网关 say ch=whisper · 聊天框「私聊」/ 社交页「私聊」"),
    0x04: ("none", "轻频聊天：服务端没实现（条件不明，实测没触发）"),
    0x06: ("done", "move(x1, y1, x2, y2) · 网关 move · 点地图寻路走"),
    0x5D: ("done", "teleport(map, x, y) · 网关 teleport · 传送页"),
    0x09: ("done", "shop_open(merchant) · 网关 shop_open · 商店页 / NPC 对话「买东西」"),
    0x0A: ("done", "buy([(item, n)]) · 网关 buy · 商店页"),
    0x0B: ("done", "use_item(item) · 网关 use · 背包页「使用」"),
    0x0D: ("done", "discard(item) · 网关 discard · 背包页「丢」"),
    0x0F: ("done", "pickup(item, n) · 网关 pickup · 点地上的方块 / 背包页「捡」"),
    0x15: ("done", "equip(slot, item) · 网关 equip · 背包页「穿」"),
    0x16: ("done", "unequip(slot) · 网关 unequip · 背包页「脱下」"),
    0x13: ("done", "set_nickname(text) · 网关 nick · 账号页"),
    0x1C: ("done", "trade_request(jyid) · 网关 trade a=request · 社交页「交易」"),
    0x1D: ("done", "trade_lock() / trade_confirm() / trade_cancel() · 网关 trade a=lock|confirm|cancel · 交易页"),
    0x1E: ("done", "trade_put_item(item) · 网关 trade a=item · 交易页"),
    0x1F: ("done", "trade_put_money(money) · 网关 trade a=money · 交易页"),
    0x22: ("done", "bank_put(item, n) / bank_get(item, n) · 网关 bank_put / bank_get · 钱庄页 / 背包页「存」"),
    0x23: ("done", "bank_open() · 网关 bank_open · 钱庄页"),
    0x71: ("done", "item_info(item) · 网关 item_info · 账号页「物品信息」"),
    0x26: ("done", "party_create() · 网关 party a=create · 社交页"),
    0x27: ("done", "party_disband() · 网关 party a=disband · 社交页"),
    0x29: ("done", "party_leave() · 网关 party a=leave · 社交页"),
    0x2C: ("done", "party_invite(jyid) · 网关 party a=invite · 社交页「组队」"),
    0x2D: ("done", "party_answer(jyid, accept) · 网关 party a=answer · 社交页「接受 / 拒绝」"),
    0x2E: ("done", "party_chat(text) · 网关 say ch=party · 聊天框「队伍」"),
    0x45: ("done", "org_create(name) · 网关 org a=create · 社交页"),
    0x4E: ("done", "org_recruit(jyid) · 网关 org a=recruit · 社交页「招收」"),
    0x4F: ("done", "org_join(jyid) / org_list() · 网关 org a=join|list · 社交页"),
    0x50: ("done", "org_kick(name) · 网关 org a=kick · 社交页"),
    0x51: ("done", "org_quit() · 网关 org a=quit · 社交页"),
    0x56: ("done", "org_query_status(sub) · 网关 org a=query"),
    0x61: ("done", "kf_equip(slot, id) · 网关 kf a=equip · 武功页"),
    0x6A: ("done", "kf_delete(password, ids) · 网关 kf a=delete · 武功页"),
    0x6B: ("done", "event(ev) · NPC 对话里的效果动作自动发 · 点 NPC"),
    0x98: ("done", "zigong(pw)（0D = 自宫，不可逆，不是二级密码验证）/ password_echo(sub) · 网关 pw a=zigong（要 confirm）· 账号页"),
    0x99: ("done", "recycle(item, n)（只有子指令 23 = VIP 回收）· 网关 recycle · 背包页「卖」；其它子指令服务端没实现"),
    0xC7: ("done", "command('@xxx') · 网关 say（以 @ 开头）· 聊天框"),
    0xD4: ("none", "战斗内位置意图上报：载荷含义没解完（战斗协议_客户端侧.md §2），没实现"),
    0xD7: ("done", "fight_act(caster, target_cell, skill) / fight_tick（怪 AI 替怪发）· 网关 fight_act · 战斗浮层"),
    0x30: ("done", "fight_encounter(entity_id) · 网关 fight_start · 战斗页「遭遇」"),
    0xE3: ("done", "fight_enter() · 网关收到 D1 后自动发"),
    0xE5: ("done", "fight_end() · fight_tick 判完胜负、等够 15 秒后自动发"),
    0xE6: ("done", "客户端只发 E5（服务端按 E5 处理 E6）；E6 的发送条件见 战斗协议_客户端侧.md §5"),
}

# S2C：opcode -> (状态, 折进哪里)
S2C = {
    0x01: ("done", "login() 的握手；种子 -> C2S 密钥基数（packet_proxy）"),
    0x02: ("done", "players（外观 / 位置）"),
    0x04: ("done", "chat_events / chat_log（子类型 01 公共 03 私聊 05 组织）；网关 chat / notice"),
    0x05: ("done", "players 移除"),
    0x06: ("done", "pos / players 位置"),
    0x08: ("done", "pos / map_id（传送、登录）"),
    0x09: ("done", "shop"),
    0x0A: ("done", "背包 +1（购买）"),
    0x0B: ("done", "背包 -1（用药 / 钱庄 / 回收；48015 固定帧不入账）"),
    0x0D: ("done", "ground（别人丢的）"),
    0x10: ("done", "背包 +1 / ground（自己捡到）"),
    0x11: ("done", "ground（别人捡走）"),
    0x14: ("done", "notices / 网关 notice"),
    0x15: ("done", "nickname_result / me.second_string"),
    0x17: ("done", "装备槽"),
    0x18: ("done", "装备槽"),
    0x1A: ("done", "notices / 网关 notice"),
    0x1B: ("ignore", "背包新增物品（开店 / 购买时的常量帧，购买结果以 0x0A 为准）"),
    0x1C: ("done", "chat_events（队伍聊天，没有发送者）"),
    0x1E: ("done", "me（parse_0x1e）"),
    0x1F: ("done", "trade"),
    0x20: ("done", "trade.offers"),
    0x21: ("done", "trade.money（原版压帧怪行为，第一次放钱时对方收不到）"),
    0x22: ("done", "trade 结束（成交 / 作废没有明确信号 -> 网关重新同步角色状态）"),
    0x23: ("done", "trade.locked / stage / 取消"),
    0x25: ("done", "name_result"),
    0x27: ("done", "钱庄存取结果 -> 背包 / bank"),
    0x28: ("done", "bank"),
    0x2A: ("done", "parties"),
    0x2B: ("done", "parties"),
    0x2D: ("done", "parties"),
    0x2E: ("done", "team_invites"),
    0x2F: ("done", "parties / team_invites"),
    0x32: ("done", "mall_points"),
    0x33: ("done", "heartbeat（随后的 0x99 04 换密钥由 packet_proxy 处理）"),
    0x36: ("done", "deleted"),
    0x39: ("done", "org_query"),
    0x4F: ("done", "org / orgs"),
    0x54: ("done", "org_invites"),
    0x55: ("done", "org / orgs.members"),
    0x56: ("done", "org / orgs.members（被踢）"),
    0x57: ("done", "org / orgs.members（退出）"),
    0x5A: ("done", "roll_result"),
    0x60: ("done", "names"),
    0x61: ("done", "players（进入视野）"),
    0x62: ("done", "players（离开视野）"),
    0x6B: ("done", "背包 -1（事件失去物品 / 标记）"),
    0x6E: ("done", "kf_slots"),
    0x77: ("done", "背包 +1（事件得到物品 / 标记）"),
    0x7A: ("done", "kf_deleted / me.kf（等级清零）"),
    0x7B: ("done", "me.fields（属性更新）"),
    0x7D: ("done", "事件回应（history / 网关 frame）"),
    0x82: ("done", "players[jyid].state（08 00 = 正在交易）"),
    0x88: ("done", "item_infos"),
    0x99: ("done", "04 换密钥（packet_proxy / JyClient 基数）· 05 buffs"),
    0xAD: ("done", "org_online"),
    0xB8: ("done", "pw_result"),
    0xD4: ("done", "fight.ents 位置（怪移动 / 进战时敌方站位；没收到就用兜底格）"),
    0xD5: ("done", "fight.ents（参战名单：id + A + B）"),
    0xD8: ("done", "fight.ents 气血（绝对值）/ me.fields.dangqianxue"),
    0x81: ("done", "fight.srv_result（01 存活 / 02 气血为 0）"),
    0xC6: ("done", "fight.ready"),
    0xD1: ("done", "fight.d1（遭遇应答；网关据此发 E3）"),
    0xDC: ("done", "fight.ents 气血基准 / maxhp"),
    0xE4: ("done", "fight.items（格子上的掉落）"),
    0xE6: ("done", "fight 实体离场；自己的 = 战斗结束（fight.ended_by_server）"),
    0xE8: ("done", "fight.items 拾走 + 事件"),
    0xEF: ("done", "fight 事件 refuse（没在战斗里发了战斗内上报）"),
}

# 方法名（从"登记说明"里取出来逐个检查它们真的存在于 JyClient）
METHODS = [
    "login", "start", "create_name", "create_enter", "roll", "delete_role", "say", "org_chat", "whisper", "move", "teleport", "shop_open", "buy",
    "use_item", "discard", "pickup", "equip", "unequip", "set_nickname", "trade_request", "trade_lock", "trade_confirm", "trade_cancel",
    "trade_put_item", "trade_put_money", "bank_put", "bank_get", "bank_open", "item_info", "party_create", "party_disband", "party_leave",
    "party_invite", "party_answer", "party_chat", "org_create", "org_recruit", "org_join", "org_list", "org_kick", "org_quit", "org_query_status",
    "fight_encounter", "fight_enter", "fight_act", "fight_end", "fight_tick",
    "kf_equip", "kf_delete", "event", "zigong", "password_echo", "recycle", "command", "my_party",
]


def load_server_opcodes():
    """从网金复刻项目读 opcodes.py（开发机上才有）。"""
    import importlib.util
    path = os.environ.get("JY_OPCODES") or r"C:\游戏\网金复刻\jyserver\opcodes.py"
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location("jy_opcodes", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jy_opcodes"] = mod        # dataclass / NamedTuple 需要
    spec.loader.exec_module(mod)
    return mod


def check():
    bad = []
    for m in METHODS:
        if not hasattr(JyClient, m):
            bad.append("JyClient 没有方法 %s" % m)
    mod = load_server_opcodes()
    if mod is None:
        print("（没有找到服务端 opcodes.py，只检查了方法是否存在）")
    else:
        for op in sorted(set(mod.C2S) - set(C2S)):
            bad.append("C2S 0x%02X %s 没有登记" % (op, mod.C2S[op].name))
        for op in sorted(set(mod.S2C) - set(S2C)):
            bad.append("S2C 0x%02X %s 没有登记" % (op, mod.S2C[op].name))
        for op in sorted(set(C2S) - set(mod.C2S)):
            bad.append("C2S 0x%02X 登记了但服务端 opcodes.py 里没有" % op)
        for op in sorted(set(S2C) - set(mod.S2C)):
            bad.append("S2C 0x%02X 登记了但服务端 opcodes.py 里没有" % op)
    return bad, mod


if __name__ == "__main__":
    bad, mod = check()
    name = lambda tab, op: (tab[op].name if mod is not None and op in tab else "")
    for title, tab, srv in (("C2S（客户端 -> 服务端）", C2S, mod.C2S if mod else {}), ("S2C（服务端 -> 客户端）", S2C, mod.S2C if mod else {})):
        print("== %s：%d 个" % (title, len(tab)))
        for op in sorted(tab):
            st, how = tab[op]
            print("  0x%02X %-6s %-14s %s" % (op, st, srv[op].name if op in srv else "", how))
    n_none = [op for op, (st, _) in list(C2S.items()) + list(S2C.items()) if st == "none"]
    print("\n登记 C2S %d + S2C %d；其中服务端没有实现的 %d 个（轻频聊天、战斗内位置上报 D4 等）" % (len(C2S), len(S2C), len(n_none)))
    for b in bad:
        print("问题：" + b)
    sys.exit(1 if bad else 0)
