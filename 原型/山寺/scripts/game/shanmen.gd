## 山门关卡（任务节点 1–3），地图 1920×1080（横纵各两屏）：
## 下半山门外石阶熄火把、清喽啰 → 穿过门洞进上半操练场，玄诚现身，锁住操练场 →
## 两阶段（教闪避、教打断）→ 坐地交代。
class_name Shanmen
extends LevelBase

## 可走地面（按 env_shanmen_v01 描的）：上半操练场 + 门洞 + 下半石阶与前庭，是一个连通的多边形
const FLOOR := [Vector2(120, 350), Vector2(260, 124), Vector2(1660, 124), Vector2(1680, 360), Vector2(1680, 524),
	Vector2(1100, 524), Vector2(1100, 704), Vector2(1600, 704), Vector2(1680, 840), Vector2(1410, 890),
	Vector2(1280, 1064), Vector2(640, 1064), Vector2(600, 940), Vector2(320, 860), Vector2(320, 704),
	Vector2(820, 704), Vector2(820, 524), Vector2(120, 524)]
## 玄诚战锁住的操练场（门洞在身后合上）
const ARENA := [Vector2(120, 350), Vector2(260, 124), Vector2(1660, 124), Vector2(1680, 360), Vector2(1680, 520),
	Vector2(120, 520)]
## 挖掉的障碍：两尊石狮、倒地香炉、前庭左侧矮松、操练场左下树丛
const BLOCKS := [
	[Vector2(636, 668), Vector2(736, 668), Vector2(736, 800), Vector2(636, 800)],
	[Vector2(1180, 668), Vector2(1280, 668), Vector2(1280, 800), Vector2(1180, 800)],
	[Vector2(1444, 744), Vector2(1600, 744), Vector2(1600, 850), Vector2(1444, 850)],
	[Vector2(330, 800), Vector2(470, 800), Vector2(470, 880), Vector2(330, 880)],
	[Vector2(150, 430), Vector2(420, 430), Vector2(420, 524), Vector2(150, 524)],
]
## 门洞路点：从下往上依次经过
const GATE_PATH := [Vector2(960, 760), Vector2(960, 620), Vector2(960, 500)]
const TORCHES := [Vector2(590, 860), Vector2(1330, 860), Vector2(1290, 980)]
const LOULUO := [Vector2(820, 880), Vector2(1100, 880), Vector2(740, 990), Vector2(1180, 1000)]
const START := Vector2(960, 1030)
## 第二处分叉「进寺方式」：山门前的出生点与门前的人按出身不同（进了门洞即合流）
const ENTRY := {
	"shenjia": {"at": Vector2(960, 1030), "npc": ["知客僧", Vector2(1010, 960), Color("#8C3B2E"), Color("#E0C8B0")]},
	"tiejiang": {"at": Vector2(760, 1010), "npc": ["邪派管事", Vector2(820, 960), Color("#2B2328"), Color("#2B2320")]},
	"xiban": {"at": Vector2(1160, 1010), "npc": ["守门喽啰", Vector2(1100, 960), Color("#2B2328"), Color("#2B2320")]},
	"langzhong": {"at": Vector2(960, 1030), "npc": []},
}
const BOSS_WAIT := Vector2(960, 300)
const ARENA_ENTRY := 520.0       # 玩家走过这条线（进了操练场）就触发玄诚
const ARENA_START := Vector2(960, 470)

var boss: SimFighter
var _down_t := -1.0
var _partner_down_t := -1.0
var _stats := {"start": 0.0, "combos": 0, "interrupts": 0, "evades": 0, "defeats": 0, "loot": "—", "equipped": ""}
var _loot_t := 0.0


func _ready() -> void:
	map_size = Vector2(1920, 1080)
	world = SimWorld.new(Time.get_ticks_msec())
	world.bounds = PackedVector2Array(FLOOR)
	for b in BLOCKS:
		world.blockers.append(PackedVector2Array(b))
	world.waypoints.assign(GATE_PATH)
	me = world.add_hero("player", sect, utility, START)
	me.facing = Vector2.UP
	jingxin = world.add_hero("partner", "shaolin", SimData.PARTY.ai_utility, START + Vector2(-40, 4))
	jingxin.facing = Vector2.UP
	for p in TORCHES:
		world.add_interactable("torch", p)
	for p in LOULUO:
		world.add_enemy("louluo", p)
	boss = world.add_enemy("xuancheng", BOSS_WAIT, true)
	var entry: Dictionary = ENTRY.get(origin, {})
	if not entry.is_empty():
		me.pos = entry.at
		jingxin.pos = entry.at + Vector2(-40, 4)
	build_scene("res://assets/env/env_shanmen_v01.png", "res://assets/env/env_shanmen_front_v01.png")
	# 开发开关 torch：出生在第一处火把旁边（截图核对「交谈」键用）
	if get_parent() and get_parent().get("dev") is Dictionary and get_parent().dev.has("torch"):
		me.pos = TORCHES[0] + Vector2(28, 6)
		jingxin.pos = me.pos + Vector2(-30, 10)
		camera.position = me.pos
		camera.reset_smoothing()
	hud.boss = boss
	if not entry.is_empty() and not entry.npc.is_empty():
		view.npcs = [{"name": entry.npc[0], "pos": entry.npc[1], "robe": entry.npc[2], "hair": entry.npc[3]}]
	_objectives()
	say(Story.shanmen_intro(sect, origin))


## 代玩：先熄还亮着的火把；火把熄完、喽啰清完就穿门洞进操练场；战斗交给 AI，玄诚读条时用通用技
func auto_command() -> SimCommand:
	var cmd := auto_ai.command(DT)
	if boss.state == "cast" and boss.t > 0.4:
		cmd.press("utility")
	var fighting := world.foes().any(func(f): return f.in_combat and f.pos.distance_to(me.pos) < 140.0)
	if fighting:
		return cmd
	for it in world.interactables:
		if it.on:
			if it.pos.distance_to(me.pos) < 40.0:
				cmd.press("interact")
			else:
				walk_to(cmd, it.pos)
			return cmd
	if stage == "to_arena":
		walk_to(cmd, ARENA_START)
	if stage == "loot":
		for g in world.ground_items:
			if g.coins == 0 and SimItems.is_equipment(g.item):  # 只去捡玄诚的兵器；前庭剩下的钱和药在锁住的门外
				walk_to(cmd, g.pos)
				break
	return cmd


# ---------- 剧情推进 ----------

func level_events(events: Array) -> void:
	for e in events:
		match e.type:
			"combo_freeze":
				_stats.combos += 1
				hud.toast("合击成立！默契 %d" % world.combo.moqi)
			"interrupt":
				if e.by == me.id or e.by == jingxin.id:
					_stats.interrupts += 1
			"evade":
				if e.id == me.id:
					_stats.evades += 1
			"combo_timeout":
				if e.id == me.id:
					hud.toast("没人响应，合击退化成普通招式；默契归零")
				elif e.id == jingxin.id:
					hud.toast("净心的合击没等到你——默契归零")
			"combo_invite":
				if e.id == jingxin.id:
					tip("invite", "净心发来合击邀请：%s，或走进地上的金色光圈" % ("点「合击」" if hud.mobile else "按 F"), 4.0)
			"interact":
				hud.toast("火把熄了")
			"loot":
				if e.id == boss.id:
					hud.toast("玄诚身边掉下一件兵器", 3.0)
			"pickup":
				if stage == "loot" and e.has("item") and SimItems.is_equipment(e.item):
					_on_loot_picked(e.item)
			"phase2":
				say(Story.phase2())
				stage = "phase2_talk"
			"boss_sit":
				stage = "down_talk"
				world.combo.invite = {}
				world.combo.preview.clear()
				say(Story.boss_down(origin))  # 共用的真相 + 第三处分叉：按出身的收尾一段
			"hero_down":
				if e.id == me.id:
					_down_t = 2.0
					_stats.defeats += 1
					hud.toast("你败退了……", 2.0)
				else:
					_partner_down_t = 8.0
					hud.toast("净心倒下了，撑一会儿他会爬起来", 3.0)
	if stage == "gate":
		_objectives()
		if world.interactables.all(func(it): return not it.on) and world.foes().all(func(f): return f.kind != "louluo"):
			stage = "to_arena"
			hud.objectives = ["穿过山门，进操练场"]
			hud.toast("铜锣响了——山门里有人在等")
	elif stage == "to_arena" and me.pos.y < ARENA_ENTRY:
		_lock_arena()
		stage = "boss_talk"
		hud.objectives = []
		say(Story.boss_intro())


## 进了操练场：门洞在身后合上，两人都拉进场内
func _lock_arena() -> void:
	world.bounds = PackedVector2Array(ARENA)
	world.waypoints.clear()
	for f in [me, jingxin]:
		if not world.walkable(f.pos):
			f.pos = ARENA_START + (Vector2(-40, 0) if f == jingxin else Vector2.ZERO)
	boss.pos = BOSS_WAIT + Vector2(0, 40)
	boss.facing = Vector2.DOWN


func _on_dialogue_done() -> void:
	match stage:
		"intro":
			stage = "gate"
			_stats.start = world.time
			tip("move", "WASD 移动，J 普攻（按住连击），空格闪避，E 熄火把" if not hud.mobile else "左摇杆移动，按住普攻连击，点闪避躲开红区", 5.0)
		"boss_talk":
			stage = "boss"
			boss.state = "chase"
			boss.in_combat = true
			hud.objectives = ["看红区，闪避他的横扫", "与净心完成合击"]
			tip("read", "他在等你躲开：红区出现就闪避，出手前一刻闪过能让他失衡", 5.0)
		"phase2_talk":
			stage = "boss"
			hud.objectives = ["打断玄诚的蓄力重击", "截脉或合击都能打断"]
			if utility != "jiemai":
				tip("no_jiemai", "你没带截脉：等净心发合击邀请，或自己按住 F 摆光圈", 5.0)
		"down_talk":
			stage = "loot"
			hud.objectives = ["拾取玄诚掉落的兵器（走过去即可）"]


## 拿到玄诚的兵器：代玩直接装上；真人提示开物品栏，关上物品栏（或等一会儿）后结算
func _on_loot_picked(it: Dictionary) -> void:
	_stats.loot = "%s（%s）" % [SimItems.display_name(it), SimItems.quality_name(it)]
	if autoplay:
		var before := me.stat("atk_flat")
		if world.inv_equip(me, int(it.uid)):
			_stats.equipped = "%s，攻击 %d → %d" % [_stats.loot, before, me.stat("atk_flat")]
		_finish()
		return
	stage = "loot_done"
	_loot_t = 20.0
	hud.objectives = ["打开物品栏换上新兵器（%s）" % ("点右上「囊」" if hud.mobile else "Tab"), "关上物品栏即结算"]
	tip("bag", "拾得玄诚的兵器：打开物品栏，拖到装备栏的「兵器」格就能换上", 5.0)


func _on_inventory_closed() -> void:
	super._on_inventory_closed()
	if stage == "loot_done":
		_finish()


func _finish() -> void:
	stage = "end"
	save_profile()
	var stats := _stats.duplicate()
	stats["secs"] = world.time - _stats.start
	stats["moqi"] = world.combo.moqi
	done.emit(stats)


func _objectives() -> void:
	var left := world.interactables.filter(func(it): return it.on).size()
	var foes := world.foes().filter(func(f): return f.kind == "louluo").size()
	hud.objectives = ["熄灭火把 %d / 3" % (3 - left), "击退守卫 %d / 4" % (4 - foes)]


func after_step(dt: float) -> void:
	_teach()
	if stage == "loot_done":
		_loot_t -= dt
		if _loot_t <= 0.0:
			_finish()
			return
	interact_hint(world.interactables.filter(func(it): return it.on).map(func(it): return [it.pos, "熄灭火把"]))
	if _partner_down_t > 0.0:
		_partner_down_t -= dt
		if _partner_down_t <= 0.0 and me.alive:
			revive(jingxin, me.pos + Vector2(-30, 10), 0.4)
			if not world.walkable(jingxin.pos):
				jingxin.pos = me.pos
			hud.toast("净心爬了起来")
	if _down_t > 0.0:
		_down_t -= dt
		if _down_t <= 0.0:
			retry()


func _teach() -> void:
	for e in world.foes():
		if e.state == "windup" and e.pos.distance_to(me.pos) < 220.0:
			tip("tele", "红色范围就是要挨打的地方——闪避（%s）" % ("点闪避" if hud.mobile else "空格"), 3.5)
		if e.state == "cast":
			tip("cast", "玄诚在读条重击！%s" % ("截脉（K）打断" if utility == "jiemai" and not hud.mobile else "截脉或合击打断"), 3.5)
	if me.primed:
		tip("primed", "内力积满：下一招附带硬直", 3.0)


## 败退：前庭阶段回山门外石阶下；玄诚战回操练场入口，玄诚回满血、回到阶段一
func retry() -> void:
	var in_arena := stage == "boss" or stage == "phase2_talk"
	var at := ARENA_START if in_arena else START
	revive(me, at, 1.0)
	revive(jingxin, at + Vector2(-40, 4), 1.0)
	me.qi = me.max_qi
	_partner_down_t = -1.0
	world.combo.invite = {}
	world.combo.moqi = 0
	world.projectiles.clear()
	world.pools.clear()
	if in_arena:
		stage = "boss"
		boss.hp = boss.max_hp
		boss.phase = 1
		boss.state = "chase"
		boss.pos = BOSS_WAIT + Vector2(0, 40)
		boss.atk = {}
		hud.objectives = ["看红区，闪避他的横扫", "与净心完成合击"]
	camera.reset_smoothing()
	hud.toast("再来一次", 2.0)
