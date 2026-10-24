## 山寺切片的全部数值表。单位：长度为 960×540 画面像素，时间为秒。
## 起点是 V0.4 第一轮战斗调整后的手感（三连普攻、闪避、预警、架势与失衡），
## 伤害 ×3，玩家生命 1000。玄诚 5000：两个满操作 AI 约 40 秒，按真人约一半输出估到规格书的「约九十秒」；全部待试玩复核。
class_name SimData
extends RefCounted

const PLAYER := {
	"hp": 1000, "qi": 200, "sp": 100, "radius": 12, "speed": 140.0,
	"qi_regen_combat": 3.0, "qi_regen_idle": 12.0, "qi_on_hit": 6.0,
	"sp_regen": 21.0, "dodge_cost": 30.0, "dodge_time": 0.23, "dodge_speed": 430.0,
	"dodge_inv": 0.30, "dodge_cd": 0.5,
	"combo_window": 0.8, "hurt_knockback": 18.0,
}

## 三连普攻，按门派武器分；half 为扇形半角（弧度）。
const ATTACKS := {
	"shaolin": [
		{"dmg": 30, "range": 76.0, "half": 1.15, "cd": 0.27},
		{"dmg": 36, "range": 76.0, "half": 1.15, "cd": 0.27},
		{"dmg": 54, "range": 90.0, "half": 1.6, "cd": 0.39},
	],
	"xiepai": [
		{"dmg": 30, "range": 68.0, "half": 1.0, "cd": 0.25},
		{"dmg": 34, "range": 68.0, "half": 1.0, "cd": 0.25},
		{"dmg": 50, "range": 80.0, "half": 1.4, "cd": 0.37},
	],
}

## 释放机制：tap 快速点按（自动朝最近敌人）、charge 按下蓄力松开释放、aim 拖动瞄准松开释放。
const SKILLS := {
	# 少林：近战硬桥硬马
	"luohanquan": {"name": "罗汉拳", "sect": "shaolin", "mode": "tap", "cost": 40, "cd": 3.0,
		"hits": 3, "dmg": 28, "range": 64.0, "half": 0.9, "interval": 0.12, "lunge": 18.0},
	"jinzhongzhao": {"name": "金钟罩", "sect": "shaolin", "mode": "charge", "cost": 50, "cd": 8.0,
		"max_charge": 1.2, "shield_min": 80, "shield_max": 300, "shield_time": 6.0},
	"dalijingangzhang": {"name": "大力金刚掌", "sect": "shaolin", "mode": "aim", "cost": 60, "cd": 6.0,
		"dmg": 90, "range": 112.0, "half": 0.6, "knockback": 60.0},
	# 邪派：毒功、远程、控制
	"dushazhang": {"name": "毒砂掌", "sect": "xiepai", "mode": "tap", "cost": 35, "cd": 2.5,
		"dmg": 60, "range": 260.0, "speed": 420.0},
	"huagongsan": {"name": "化功散", "sect": "xiepai", "mode": "aim", "cost": 55, "cd": 9.0,
		"reach": 220.0, "radius": 48.0, "time": 5.0, "dps": 30.0, "slow": 0.4},
	"shehunshu": {"name": "摄魂术", "sect": "xiepai", "mode": "charge", "cost": 50, "cd": 7.0,
		"max_charge": 1.0, "dmg": 50, "range": 240.0, "width": 18.0, "root": 2.0},
	# 通用技槽（进山门前三选一）
	"tiyunzong": {"name": "梯云纵", "sect": "", "mode": "tap", "cost": 0, "cd": 8.0, "blink": 110.0, "inv": 0.15},
	"yungong": {"name": "运功疗伤", "sect": "", "mode": "tap", "cost": 0, "cd": 15.0,
		"heal": 200, "share_range": 120.0, "share_heal": 100, "share_qi": 60},
	"jiemai": {"name": "截脉", "sect": "", "mode": "tap", "cost": 0, "cd": 10.0, "range": 170.0, "dmg": 40},
}

const SECTS := {
	"shaolin": {"name": "少林", "skills": ["luohanquan", "jinzhongzhao", "dalijingangzhang"], "fallback": "luohanquan",
		"passive": "积内力：受击积蓄，满时下一招附带硬直"},
	"xiepai": {"name": "邪派", "skills": ["dushazhang", "huagongsan", "shehunshu"], "fallback": "dushazhang",
		"passive": "叠毒：攻击叠毒，三层引爆持续伤害"},
}
const UTILITIES := ["tiyunzong", "yungong", "jiemai"]

## 门派被动
const PASSIVE := {
	"shaolin_fill": 300.0,  # 受到这么多伤害后积满
	"shaolin_stagger": 1.0,  # 积满后下一招附带的硬直
	"poison_stacks": 3, "poison_dps": 20.0, "poison_time": 4.0,
}

## 双人合击、三人阵法与默契（规格书第四节）。合击与阵法共用一套默契等级与反馈。
const COMBO := {
	"window": 3.0, "cd": 10.0, "freeze": 0.45,
	"preview_reach": 160.0, "preview_default": 70.0,
	"radius": [56.0, 76.0, 104.0], "mult": [1.0, 1.5, 2.0], "dmg": 150,
	"streak_gap": 30.0, "stagger": 2.0,
	# 三人阵法「金刚伏魔圈」：圈更大、伤害 ×1.5；两名响应者都进圈才成立
	"formation_radius": [96.0, 116.0, 144.0], "formation_mult": 1.5,
	# 破毒罩：阵法 10 秒、合击 5 秒；破罩期间光圈处净化毒雾
	"break_formation": 10.0, "break_combo": 5.0, "break_reach": 420.0,
	# 阵法成立后下一次要等 16 秒：10 秒破罩窗口过后，毒罩恢复、毒雾回压，大家得撤开、重攒默契再摆阵
	"formation_cd": 16.0,
}

## 队伍配置。第三人：用户 2026-10-24 拍板用临时 AI 侠客，和净心同一套 AI，藏经阁入口加入。
## enabled 关掉就只有玩家与净心（阵法用不了，只能合击破罩）。以后换方案只改这里。
const PARTY := {
	"third": {"enabled": true, "kind": "ally", "name": "韩青", "title": "游方侠客", "sect": "shaolin",
		"utility": "jiemai", "join_line": "路过听见打斗——这阵势一个人摆不开，算我一个。"},
	# AI 队友带截脉，只用来给被定身的人解穴，不替玩家打断 Boss 读条
	"ai_utility": "jiemai",
}

## 敌人。tele 为预警时长（规格书：可闪避攻击前 0.8 秒），cast 为可打断读条。
## prop 为可破坏物（木箱、酒坛）：不动不打、不算进战斗，打碎了掉落。
const ENEMIES := {
	"crate": {"name": "木箱", "hp": 30, "radius": 11, "speed": 0.0, "aggro": 0.0, "flinch": false, "stance": false,
		"prop": true, "attacks": {}},
	"jar": {"name": "酒坛", "hp": 20, "radius": 9, "speed": 0.0, "aggro": 0.0, "flinch": false, "stance": false,
		"prop": true, "attacks": {}},
	# 大雄宝殿两侧的零件堆：打碎了掉关卡指定的那样零件（或一点钱药）
	"pile": {"name": "零件堆", "hp": 40, "radius": 13, "speed": 0.0, "aggro": 0.0, "flinch": false, "stance": false,
		"prop": true, "attacks": {}},
	# Boss 三（规格书第六节）：铁甲对非裂口伤害减免 99%，裂口只能由重弩打出。数值是草稿，待试玩标定。
	"jingang": {"name": "铁甲金刚", "hp": 10000, "radius": 26, "speed": 45.0, "aggro": 9999.0, "boss": true,
		"flinch": false, "stance": false, "armor_cut": 0.99,
		"charge_every": 25.0, "first_charge": 15.0, "quake_every": 9.0, "grab_every": 13.0, "deflect_stagger": 3.0,
		# 狂暴：开战 240 秒还没打下来，踏地震改为每 3 秒一次、伤害 ×1.5（不用弩车必团灭）
		"enrage_at": 240.0, "enrage_quake_every": 3.0, "enrage_mult": 1.5,
		"attacks": {
			# 冲撞：朝弩车（没拼好就朝最近的人）直线冲；预警 2.5 秒（留出摆合击 / 阵法撞偏的时间），冲 0.8 秒
			"charge": {"shape": "line", "range": 520.0, "width": 30.0, "tele": 2.5, "dash_time": 0.8, "dmg": 120, "rec": 1.2, "reach": 9999.0},
			# 踏地震：全场环形冲击波，0.8 秒红区，翻滚或梯云纵的无敌时间能躲
			"quake": {"shape": "quake", "range": 9999.0, "tele": 0.8, "dmg": 140, "rec": 1.0, "reach": 9999.0},
			# 抓人：抓最近的非操弩者往弩车扔，落点离弩车近就砸中弩车
			"grab": {"shape": "circle", "range": 70.0, "tele": 0.6, "dmg": 100, "rec": 0.8, "reach": 70.0, "throw": 220.0},
		}},
	# Boss 二（规格书第六节）。血量是草稿：三个满操作 AI 约四轮破罩打完（单测里打印），
	# 真人输出低一些会多一两轮，对着规格书「三到四轮」偏长一点，待试玩标定。
	"dulao": {"name": "毒姥 · 护法", "hp": 5500, "radius": 16, "speed": 30.0, "aggro": 9999.0, "boss": true,
		"flinch": false, "stance": false, "ward_cut": 0.95,
		"fog_delay": 10.0, "fog_max": 640.0, "fog_shrink": 24.0, "fog_min": 110.0, "fog_pct": 3.0,
		# 收口：毒雾压到最小圈后，再有 30 秒没人破罩，就把最后这一圈也吞掉（不摆阵必团灭，规格书第六节验收）
		"fog_close_after": 30.0, "fog_close_time": 12.0,
		"gu_every": 5.0, "soul_every": 12.0,
		"attacks": {
			"gu": {"shape": "spot", "radius": 48.0, "tele": 0.8, "dmg": 0, "pool_dps": 40.0, "pool_time": 15.0, "rec": 0.6, "reach": 9999.0, "range": 360.0},
			"soul": {"shape": "field", "cast": 1.5, "root": 3.0, "rec": 0.8, "no_interrupt": true},
		}},
	# 开场教学（规格书第九节教学三项之「闪避」）：在场 NPC 走近、比划一下，伤害为 0；名字由开场关卡按出身改
	"trainer": {"name": "引导人", "hp": 99999, "radius": 12, "speed": 80.0, "aggro": 9999.0,
		"flinch": false, "stance": false,
		"attacks": {"slash": {"shape": "cone", "range": 60.0, "half": 1.0, "tele": 1.0, "dmg": 0, "rec": 1.6, "reach": 46.0}}},
	"louluo": {"name": "邪派喽啰", "hp": 240, "radius": 13, "speed": 95.0, "aggro": 260.0,
		"flinch": true, "stance": false,
		"attacks": {"slash": {"shape": "cone", "range": 56.0, "half": 0.9, "tele": 0.7, "dmg": 90, "rec": 0.55, "reach": 46.0}}},
	"xuancheng": {"name": "玄诚 · 叛僧教头", "hp": 5000, "radius": 18, "speed": 80.0, "aggro": 9999.0,
		"flinch": false, "stance": true, "stance_cut": 0.5, "stance_break": 2.0, "read_window": 0.5, "boss": true,
		"phase2_at": 0.5, "heavy_every": 11.0,
		"attacks": {
			"sweep": {"shape": "cone", "range": 104.0, "half": 1.0, "tele": 0.8, "dmg": 120, "rec": 0.6, "reach": 84.0},
			"dash": {"shape": "line", "range": 190.0, "width": 18.0, "tele": 0.8, "dmg": 100, "rec": 0.8, "reach": 210.0, "min_dist": 110.0},
			"heavy": {"shape": "field", "cast": 2.0, "dmg": 350, "rec": 1.0},
		}},
}

## 净心（AI 队友）：少林棍法，输出打折
const PARTNER := {"hp": 800, "dmg_scale": 0.6, "react": 0.25, "dodge_chance": 0.8,
	"invite_react": [0.5, 1.0], "follow": 70.0, "invite_every": 24.0}

## 弩车（规格书第八节）：唯一一处要求联机状态一致的机关，状态全在 SimWorld.ballista，只由 SimBallista 改。
const BALLISTA := {
	"parts": ["chassis", "arm", "winch"],
	"part_names": {"chassis": "底盘", "arm": "弓臂", "winch": "绞盘"},
	"build_time": 3.0, "reach": 56.0, "hp": 3,
	# 蓄力三档：按住普攻蓄力，松开发射；档位决定裂口大小与弩箭伤害
	"charge_steps": [0.5, 1.1], "max_charge": 1.5,
	"bolt_speed": 700.0, "bolt_range": 900.0, "bolt_dmg": [40, 70, 110],
	"breach_radius": [10.0, 16.0, 24.0], "breach_time": 20.0,
	"carry_reach": 24.0,
}

## 通关箱（规格书第七节）：金刚倒下后出现，每人开一件，底子随机，品质魔法六成、稀有四成
const CHEST := {"quality": {"magic": 6, "rare": 4}}