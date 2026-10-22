"""已知 opcode 表。

只收笔记里**有交叉验证**或**结构自洽**的条目，证据等级：
    verified  —— 有独立证据交叉验证（如与数据库字段逐个吻合、玩家动作与回包一一对应）
    probable  —— 结构自洽但语义靠推断
    unknown   —— 只知道出现过
其余 opcode 一律不收，不要臆测。来源：新网金/99-历史/协议抓包-初步分析.md，
以及后续对服务端.exe 的反编译（结论会在这里补充并注明）。
"""

from __future__ import annotations

from typing import NamedTuple


class OpInfo(NamedTuple):
    name: str
    layout: str  # 参数布局（LE = 小端）
    level: str  # verified / probable / unknown
    note: str = ""


S2C: dict[int, OpInfo] = {
    0x01: OpInfo("握手响应", "(未解)", "probable", "首包，密钥 0x9F，帧后多 1 字节 00；回放即可"),
    0x02: OpInfo("玩家外观/位置（上线）", "jyid(LE32) 地图 x y(LE16×3) 01 名字(17) 称号(17) 6×00 01 01 头盔 衣服 武器(LE16×3) 善恶-2000(LE16) …末字节 32", "verified", "他人上线 / 出现在视野时发"),
    0x09: OpInfo("商店商品清单", "00 + N×[物品ID(LE32) 商人表里的数(LE32)]", "verified", "回 C2S 0x09"),
    0x0A: OpInfo("购买明细", "N×[01 物品ID(LE32) 这条之后的金钱(LE32)]", "verified", "回 C2S 0x0A"),
    0x1B: OpInfo("背包新增物品", "N×[物品ID低3字节 耐久 00000000]（开店时是两条常量）", "verified", "购买成功 / 开店时发"),
    0x27: OpInfo("钱庄存取结果", "存：00 物品ID 数量 金钱LE32 耐久 | 取：01 物品ID 数量 ee dc 00 00", "verified", "回 C2S 0x22"),
    0x28: OpInfo("钱庄清单", "LE32 + N×[物品ID(LE32) 耐久 数量(LE16)]（最新在前）", "verified", "回 C2S 0x23；取成功后也会刷一次"),
    0x77: OpInfo("新增物品(固定)", "8f bb 00 00 c8 01", "probable", "钱庄存取时的固定帧；掉落时也用，含义未全解"),
    0x88: OpInfo("物品信息", "物品ID(LE32) c8 00 00 00 00", "verified", "回 C2S 0x71"),
    0x25: OpInfo("创建角色结果", "00=成功 01=名字已被占用", "verified", "回 C2S 0x20"),
    0x5A: OpInfo("摇点结果", "03 + 7 个属性(15..25, 总和140)", "verified", "回 C2S 0x76"),
    0x04: OpInfo("聊天转发", "子类型 发送者jyid(LE32) 文本(原样字节)", "verified", "01=公共聊天，03=私聊（长帧），05=组织聊天（不回显发送者）；07 轻频未实现"),
    0x33: OpInfo("全服心跳", "心跳计数(LE32) 在线时间(LE32)", "verified", "约每 75.6 秒一次，后面紧跟 0x99 04 换密钥；见 docs/心跳换密钥与存档.md"),
    0x05: OpInfo("移除实体（下线）", "jyid(LE32) 00", "verified"),
    0x06: OpInfo("实体移动广播", "实体ID(LE32) 起X(LE16) 起Y(LE16) 终X(LE16) 终Y(LE16)", "verified", "实体ID==数据库 jyid"),
    0x60: OpInfo("名字牌（上线）", "jyid(LE32) 名字(17) 称号(17) 8 字节未解", "verified"),
    0x08: OpInfo("设定角色位置", "地图(LE16) X(LE16) Y(LE16) 未解(1)", "verified", "与 renwu.map/x/y 吻合；原服务端用长帧"),
    0x0B: OpInfo("使用物品确认", "物品ID(LE32) 耐久 01", "verified", "吃药 / 钱庄 / VIP 回收之后都发"),
    0x14: OpInfo("系统公告", "子类型(1) BIG5文本", "verified"),
    0x17: OpInfo("穿装备确认", "jyid(LE32) 槽位 物品ID(LE32) 状态", "verified", "只发给自己，不广播"),
    0x18: OpInfo("脱装备确认", "jyid(LE32) 槽位", "verified", "只发给自己，不广播"),
    0x1A: OpInfo("BIG5系统提示", "子类型64 BIG5文本", "verified", "吃药三次，文本依次为开始/仍在/仍在；物品不足"),
    0x61: OpInfo("玩家进入地图", "jyid 地图 x y 01 头盔 衣服 武器(LE16×3) 善恶-2000(LE16) … 末14", "verified", "他人传送进入同一地图时发；见 docs/传送与地图可见性.md"),
    0x62: OpInfo("玩家离开地图", "jyid(LE32)", "verified"),
    0x99: OpInfo("换密钥 / 临时增益通知", "04 <种子4字节> | 05 jyid(LE32) ff", "verified", "04：心跳时发，此后双方密钥 = derive_key(种子)（实测）；05：神行丹之类的临时增益"),
    0x82: OpInfo("实体状态标记", "jyid(LE32) 状态(LE16)", "verified", "进入地图时跟在每个已有玩家的 0x02 之后（00 00）；交易中 = 08 00，交易结束 = 00 00"),
    0x1E: OpInfo("登录角色完整状态", "大包，字段按距包尾偏移定位", "verified", "见 99-历史 协议分析 §0x1E 字段表；背包记录后面跟着标记记录（见 docs/事件引擎.md）"),
    0x77: OpInfo("得到物品/标记", "ID(LE32) 0x100+类型(LE16)", "verified", "事件给物品/标记时每件一条；类型 = 标记.csv「类型」列 / 物品耐久；见 docs/事件引擎.md"),
    0x6B: OpInfo("失去物品/标记", "ID(LE32) 0x100+类型(LE16)", "verified", "事件扣物品/标记；缺的时候这帧照发（先发后查）"),
    0x7D: OpInfo("事件回应", "事件id(LE16) [+ 回显的请求字节，个数由事件 type 决定]", "verified", "回 C2S 0x6B；中止/失败时只有 事件id"),
    0x0D: OpInfo("别人丢了东西（地上物品）", "丢的人jyid(LE32) 物品ID(LE32) 耐久字节 数量(LE32)", "verified", "同图其他玩家收到，丢的人自己什么都收不到；见 docs/丢弃回收交易.md"),
    0x10: OpInfo("捡到地上物品", "物品ID(LE32) 耐久 数量(LE32)", "verified", "只发给捡的人；回 C2S 0x0F"),
    0x11: OpInfo("别人捡了地上物品", "捡的人jyid(LE32) 物品ID(LE32) 耐久 数量(LE32)", "verified", "同图其他玩家收到"),
    0x1F: OpInfo("交易请求", "发起人jyid(LE32) 对方jyid(LE32)", "verified", "双方收到；见 docs/丢弃回收交易.md"),
    0x20: OpInfo("交易：放入物品", "放的人jyid(LE32) 01 物品ID(LE32) 耐久 01", "verified", "双方收到"),
    0x21: OpInfo("交易：金钱通知（被压住的）", "jyid(LE32) 金钱(LE32) + f4 44 <被顶掉那帧的长度>", "verified", "原版怪行为：先压在槽里，被下一帧顶出来；见 docs/丢弃回收交易.md"),
    0x22: OpInfo("交易：成交结束", "(空)", "verified", "双方收到"),
    0x23: OpInfo("交易：状态", "01 jyid(LE32)=对方已锁定 | 04=进入确认阶段 | 00 jyid(LE32)=取消", "verified"),    0x32: OpInfo("商城点数", "6f + 点数(LE32)", "verified", "登录序列里有；@scb / @mp 之后也发"),
    0x15: OpInfo("改外号结果", "jyid(LE32) + V7Z<n>- + 外号原始字节", "verified", "回 C2S 0x13，只发给自己"),
    0x36: OpInfo("删除角色成功", "01", "verified", "回 C2S 0x33"),
    0xB8: OpInfo("自宫结果", "10 = 自宫成功（密码对） | 13/12 + 5 字节回显", "verified", "回 C2S 0x98"),    0x1C: OpInfo("队伍聊天", "载荷去掉前 4 字节后的原样字节", "verified", "回 C2S 0x2E；队伍号相同的人收到（没队伍的人发则所有没队伍的人收到）"),
    0x2A: OpInfo("创建队伍", "队长jyid(LE32) 01 00 + 请求载荷原样", "verified", "全服收到"),
    0x2B: OpInfo("队伍解散", "发起人jyid(LE32)", "verified", "全服收到"),
    0x2D: OpInfo("有人离队", "离队者jyid(LE32)", "verified", "全服收到"),
    0x2E: OpInfo("组队邀请", "邀请人jyid(LE32)", "verified", "只发给被邀请的人"),
    0x2F: OpInfo("有人入队", "01 加入者jyid(LE32) + 应答载荷第2字节起原样(邀请人jyid)", "verified", "全服收到"),    0x7B: OpInfo("属性更新", "子类型(1) 值(LE32)", "verified", "子类型→renwu 字段映射见笔记"),
    0x4F: OpInfo("创立组织结果", "创立者jyid(LE32) 组织号(LE16) 组织名原始字节", "verified", "回 C2S 0x45，只发给自己；全服另收 0x14 公告"),
    0x54: OpInfo("组织招收邀请", "创立者jyid(LE32) 组织名长度(1) 组织名 + 1802字节固定模板(组织号LE16在模板第28字节)", "verified", "长帧；只发给被招收的人"),
    0x55: OpInfo("有人加入组织", "加入者jyid(LE32) 01 组织号(LE16)", "verified", "全服收到"),
    0x56: OpInfo("有人被踢出组织", "踢人者jyid(LE32) 被踢者jyid(LE32)", "verified", "全服收到"),
    0x57: OpInfo("有人退出组织", "退出者jyid(LE32)", "verified", "全服收到"),
    0xAD: OpInfo("组织成员列表", "10 + N×[05 名字长度 名字(BIG5)]", "verified", "回 C2S 0x4F 07；只列在线的、不是自己的"),
    0x39: OpInfo("组织查询结果", "05 | 03 | 04（固定）", "verified", "长帧；回 C2S 0x56 子类型 06 / 04 / 05"),    0x6E: OpInfo("装备武功结果", "槽位(1) 武功ID(LE16)", "verified", "回 C2S 0x61；只回显，槽位 0–14"),
    0x7A: OpInfo("删除武功结果", "02 武功ID(LE16)", "verified", "回 C2S 0x6A，每个删掉的 ID 一条"),    0xD1: OpInfo("遭遇应答", "01 00 实体id(LE32) 00×10 随机数(LE32) 00×4（24 字节）", "verified", "回 C2S 0x30；随机数原版 1–100 之间"),
    0xDC: OpInfo("参战实体初始数值", "数量(LE16) + N×[id(LE32) 01 00 00 00 气血(LE32) 00×9]", "verified", "遭遇时回我方，进战时回敌方"),
    0xC6: OpInfo("战斗就绪", "(空)", "probable", "进战应答最后一帧（客户端侧反编译）"),
    0xE4: OpInfo("战斗掉落：格子放物品", "N×[列 行 物品ID(LE16)]", "probable", "怪死亡后；客户端侧反编译，没对过原版"),
    0xE6: OpInfo("实体离场", "实体id(LE32)", "verified", "怪死亡 / 自己的战斗结束（后者原版实测）"),
    0xE8: OpInfo("拾取战斗掉落", "实体id(LE32) 列 行", "probable", "客户端侧反编译"),
    0x81: OpInfo("战斗结算", "01=气血>0 | 02=气血为 0", "verified", "长帧；回 C2S 0xE5 / 0xE6"),
    0xEF: OpInfo("战斗拒绝", "jyid(LE32) 10", "verified", "没在战斗里发 0xD8"),    0xD4: OpInfo("战斗出招回应", "实体ID(LE32) 2字节", "unknown", "疑似伤害，未证实"),
    0xD5: OpInfo("参战名单", "数量(LE16) N×[实体ID(LE32) 类型(LE16)]", "verified", "先我方后敌方各一条"),
    0xD8: OpInfo("气血广播", "01 N×[实体ID(LE32) 当前气血(LE32)]", "verified", "与 0x7B 子类型 0x18 交叉验证"),
    0x64: OpInfo("采集 / 收成结果", "物品ID(LE16) 01 技能号 等级 经验（采集 LE24，農夫 LE32）", "verified", "回 C2S 0x5A / 0x5C"),
    0x66: OpInfo("農夫田块", "jyid(LE32) 田块号 种子ID(LE16) 01=播種 | 03=耕種", "verified", "回 C2S 0x5B / 0x5C"),
    0x76: OpInfo("技能计数", "BE 技能号 01|02 01 值(LE32)：01 = 等级，02 = 经验", "verified", "采集 / 收成每轮发两条"),
    0x68: OpInfo("武功等级经验更新", "武功 ID(LE16) 等级(LE16) 经验(LE32) 学点(LE16) 精(LE16)", "verified", "学武功 / 消点 / 读秘笈；见 docs/消点.md"),
    0xD7: OpInfo("出招转发", "出招 / 姿态载荷的前 16 字节", "probable", "回 C2S 0xD7 / 0xDE；动画触发"),
    0xF9: OpInfo("逃跑应答", "01 | 00", "verified", "短帧；回 C2S 0xF9，随机"),
}

C2S: dict[int, OpInfo] = {
    0x01: OpInfo("登录", "jyid(LE32) 未知(LE32) 明文密码ASCII", "verified", "首包密钥 0x9E；末尾 ASCII 是**明文密码**（实测：克隆号密码不匹配会被拒）"),
    0x20: OpInfo("创建角色", "1字节(未知) + 名字(GBK)", "verified", "只写 jyid 和名字，其余靠表默认值；见 docs/新建角色.md"),
    0x76: OpInfo("摇点", "(空)", "verified", "回 S2C 0x5A；新账号握手后密钥是 0x34"),
    0x19: OpInfo("启动登录", "1字节 | 新角色：长载荷(地图 名字 昵称 属性 头像…)", "verified", "长载荷只对刚建好的角色有效"),
    0x02: OpInfo("公共聊天", "子类型01 文本(原样字节)", "verified", "实测：转给其他在线玩家(S2C 0x04)，发送者饮食/饮水各-5(S2C 0x7B 34/36)；子类型05=组织聊天（见 docs/组织.md）"),
    0x03: OpInfo("私聊", "目标jyid(LE32) 文本(原样字节)", "verified", "转发为 S2C 0x04 子类型 03；目标不在线无回包"),
    0x04: OpInfo("轻频聊天", "N + N×4字节 + 文本", "probable", "反编译 0x72e01f 的 T[3]==04 分支，S2C 04 07；实测未触发，发送条件不明"),
    0x06: OpInfo("移动", "起X 起Y 终X 终Y (均 LE16) + 尾部3字节未解", "verified", "实测：服务端不校验起点/步长/尾部，直接记终点并回显"),
    0x09: OpInfo("开店", "商人ID(LE16)", "verified", "回 0x1A + 0x09(商品清单) + 两条常量 0x1B；见 docs/商店.md"),
    0x22: OpInfo("钱庄存取", "子类型(00存/01取) 物品ID(LE32) 耐久 数量(LE16)", "verified", "见 docs/钱庄.md"),
    0x23: OpInfo("打开钱庄", "(空)", "verified", "回 S2C 0x28 清单"),
    0x71: OpInfo("物品信息", "物品ID(LE32)+…", "verified", "回 S2C 0x88 = 物品ID + c8 00 00 00 00"),
    0x0A: OpInfo("批量购买", "N×[物品ID(LE32) 数量(LE32)]", "verified", "单价恒为 1、背包只加 1 件、「商品」列=1 才能买；见 docs/商店.md"),
    0x6B: OpInfo("事件", "[4 字节原版不看] 地图(LE16) 事件id(LE16)，≥8 字节", "verified", "处理函数 0x63be2f；执行 事件.csv 的「结果」；见 docs/事件引擎.md"),
    0x0B: OpInfo("使用物品", "物品ID(LE32)（后面的字节不看）", "verified", "实测+新服务端逐包一致，见 docs/装备与物品.md"),
    0x15: OpInfo("穿装备", "槽位(1) 物品ID(LE32) 状态(1)", "verified", "槽位 1234 6789；背包没有则全服广播刷装备警告"),
    0x16: OpInfo("脱装备", "槽位(1)", "verified"),
    0x0D: OpInfo("丢弃物品", "物品ID(LE32) 耐久(1) 数量(LE32)，≥9 字节", "verified", "背包只扣 1 件，不管数量；见 docs/丢弃回收交易.md"),
    0x0F: OpInfo("拾取地上物品", "物品ID(LE32) 耐久(1，不比较) 数量(LE32)，≥9 字节", "verified", "同图、物品ID+数量都相等的第一件；背包 +1；见 docs/丢弃回收交易.md"),
    0x26: OpInfo("创建队伍", "任意载荷(原样回显)", "verified", "3511/1820/13000 图不能创建；见 docs/组队.md"),
    0x2C: OpInfo("组队邀请", "对方jyid(LE32，前4字节)", "verified", "对方收 S2C 0x2E"),
    0x2D: OpInfo("组队应答", "01=接受/其他=拒绝 + 邀请人jyid(LE32)", "verified", "接受时邀请人必须已在队伍里，否则原版崩"),
    0x2E: OpInfo("队伍聊天", "4字节(被吃掉) + 内容", "verified"),
    0x27: OpInfo("解散队伍", "(空)", "verified", "队伍里任何人都能解散"),
    0x29: OpInfo("离队", "(空)", "verified", "队长(格0)离不开；没队伍也会向所有没队伍的人发离队文字"),    0x13: OpInfo("改外号", "新外号原始字节(BIG5)，到 00 为止，可空", "verified", "进入世界后有效；见 docs/账号类指令.md"),
    0x33: OpInfo("删除角色", "1字节(不看) 密码长度 密码字节", "verified", "只能在选角色界面用；进入世界后原版会崩，新服务端不理会"),
    0x5A: OpInfo("生活技能", "序号(4) A(1开始 2一轮 3停止) B(1伐木 2捕魚 3採礦) 工具位置 … 校验：不看", "verified", "见 docs/生活技能与农夫.md"),
    0x5B: OpInfo("播種", "田块号(1) 种子ID(LE16)，正好 3 字节", "verified", "回 S2C 0x66"),
    0x5C: OpInfo("耕種 / 收成", "序号(4) 田块号 动作(1耕種 2收成) …，≥6 字节", "verified", "耕種回 66 + 82；收成回 64 + 76 BE"),
    0x1B: OpInfo("合成 / 烹調 / 打造", "配方键 2 字节（如 F0 02 = 熟牛肉），多出来的不看", "verified", "神 ≥ 2，先扣 1（回 7B 1A）；材料不够静默；见 docs/合成.md / craft.py"),
    0x5E: OpInfo("消点", "师傅(LE16) 武功(LE16) 点数(LE16) [序号 校验字节：不看]，≥6 字节", "verified", "学习点换武功经验；基本武学 8001–8017 存 renwu 列；点数 2 = 全部；见 docs/消点.md / study.py"),
    0x60: OpInfo("读秘笈", "物品ID(LE32) 耐久(1)，≥5 字节", "verified", "乾坤大挪移 / 葵花宝典 / 太玄经；背包没有 → 物品不足 + 踢下线；见 kungfu.read_book"),
    0x67: OpInfo("背叛师门（停用桩）", "序号(LE32) 长度 密码 长度 暗码", "verified", "原版无条件回 1A「請從外掛上判門﹗」（载荷≥5 字节）；真入口是 @bpsm"),
    0x98: OpInfo("自宫等", "0D 长度 密码 [暗码] = 自宫（renwu.zigong 置 1） | 0F/0E + 5 字节回显", "verified", "短载荷原版会崩，新服务端静默；0D 是自宫不是二级密码（客户端会话实测库里 zigong 0→1）"),    0xC7: OpInfo("@文字指令", "04 40 + ASCII 文本（where / kale / cpw / se N / wp ID / scb N / mp N / bpsm …）", "partial", "原版 0x6cab50，二十多条；做了其中 12 条，见 docs/文字指令.md"),
    0x99: OpInfo("VIP 指令族", "子指令(1)…；23 = 回收：物品ID(LE32) 耐久(1，不看) 数量(1)", "partial", "只做了 0x23；其余子指令（22/1E/2B…）没碰"),
    0x1C: OpInfo("交易请求", "对方jyid(LE32)", "verified", "一发就建会话；见 docs/丢弃回收交易.md"),
    0x1E: OpInfo("交易：放物品", "01 物品ID(LE32) 耐久(1)", "verified"),
    0x1F: OpInfo("交易：放金钱", "金钱(LE32)", "verified"),
    0x1D: OpInfo("交易：锁定/确认/取消", "01=锁定 03=确认 00=取消", "verified", "第 2 次锁定→双方 23 04；第 2 次确认→成交"),
    0x45: OpInfo("创立组织", "组织名原始字节", "verified", "见 docs/组织.md"),
    0x4E: OpInfo("招收", "对方jyid(LE32)", "verified", "只有创立者；对方收 S2C 0x54"),
    0x4F: OpInfo("组织应答 / 成员列表", "01 招收人jyid(LE32) = 加入 | 07 = 列表", "verified", "加入不检查招收人；见 docs/组织.md"),
    0x50: OpInfo("踢出组织", "4字节(不看) + 对方名字(BIG5字节)", "verified", "谁都能踢任何在线玩家；被踢者组织号写成 \" 0\""),
    0x51: OpInfo("退出组织", "01", "verified", "全服收 S2C 0x57"),
    0x56: OpInfo("组织查询", "06 | 04 | 05", "verified", "回 S2C 0x39 固定值"),    0x61: OpInfo("装备武功", "槽位(1) 武功ID(LE16)", "verified", "没有这门武功 → 全服「嘗試刷武功﹗」公告；见 docs/武功装备与删除.md"),
    0x6A: OpInfo("删除武功", "1字节(不看) 密码长度N 密码 1字节(不看) K×武功ID(LE16)", "verified", "要账号密码；3860 转生武功不能删；删除只是等级经验写 0"),    0x5D: OpInfo("传送", "地图(LE16) X(LE16) Y(LE16)", "verified", "实测：不校验；见 docs/传送与地图可见性.md"),
    0x30: OpInfo("遭遇（进入战斗）", "怪实体id(LE32) + 19 字节(零即可)", "verified", "实体id=实例序号×1e5+mob_id；见 docs/战斗.md"),
    0xE3: OpInfo("进战", "jyid(LE32) 列 行 模式 尾字节", "partial", "尾字节不验；原版要校验我们没有"),
    0xE5: OpInfo("战斗结束上报", "jyid(LE32) + 1 字节", "verified", "载荷里没有胜负，服务端按自己的气血判"),
    0xE6: OpInfo("战斗结束上报(多队)", "同 0xE5", "partial", "按 E5 处理"),    0xD4: OpInfo("战斗出招(旧称)", "目标实体ID(LE32) + 9字节", "unknown"),
    0xD7: OpInfo("战斗出招", "固定 32 字节；bytes[6:10] 十进制=武功ID*100+后缀", "verified", "施术者含怪，怪的出招也由客户端上报"),
    0xDE: OpInfo("战斗原地姿态", "jyid(LE32) 命令号(7防禦 8閃躲 9養精蓄銳 11自動) 计数器(LE32) 校验", "partial", "回 S2C D7 转发是自拟（原版要校验字节才回）"),
    0xF9: OpInfo("逃跑", "(空)", "verified", "回 S2C F9 一字节 01/00 随机（原版实测约 43% 为 01），不改变战斗状态"),
}


def describe(direction: str, opcode: int) -> str:
    table = C2S if direction == "c2s" else S2C
    info = table.get(opcode)
    if info is None:
        return "?"
    return f"{info.name} [{info.level}]"
