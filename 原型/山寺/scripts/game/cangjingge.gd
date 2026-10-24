## 后殿藏经阁（任务节点 4–5），占位地图 1920×1080：
## 下半后院回廊（过渡段：三名喽啰、木箱酒坛）→ 门洞 → 上半藏经阁大厅；
## 进阁时第三人（临时 AI 侠客，见 SimData.PARTY）加入、三人阵法启用、大厅锁边界 → 毒姥战 →
## 毒姥离场、阿萝脱险、一年之约（字幕，不挡操作）→ 拾取毒姥掉的防具 → 结算。
class_name Cangjingge
extends LevelBase

## 可走地面：大厅 + 门洞 + 回廊
const FLOOR := [Vector2(300, 200), Vector2(1620, 200), Vector2(1620, 700), Vector2(1020, 700), Vector2(1020, 780),
	Vector2(1320, 780), Vector2(1320, 1064), Vector2(600, 1064), Vector2(600, 780), Vector2(900, 780),
	Vector2(900, 700), Vector2(300, 700)]
## 毒姥战锁住的大厅
const HALL := [Vector2(300, 200), Vector2(1620, 200), Vector2(1620, 696), Vector2(300, 696)]
## 书架岛、散落经卷、回廊柱子
const BLOCKS := [
	[Vector2(380, 620), Vector2(440, 620), Vector2(440, 670), Vector2(380, 670)],
	[Vector2(1480, 620), Vector2(1540, 620), Vector2(1540, 670), Vector2(1480, 670)],
	[Vector2(640, 820), Vector2(680, 820), Vector2(680, 860), Vector2(640, 860)],
	[Vector2(1240, 820), Vector2(1280, 820), Vector2(1280, 860), Vector2(1240, 860)],
]
const DOOR_PATH := [Vector2(960, 830), Vector2(960, 740), Vector2(960, 650)]
const START := Vector2(960, 1030)
const ARENA_CENTER := Vector2(960, 430)
const DULAO_AT := Vector2(960, 300)
const HALL_ENTRY := 690.0          # 走过这条线（进了大厅）就触发
const HALL_START := Vector2(960, 640)
const LOULUO := [Vector2(780, 900), Vector2(1140, 900), Vector2(960, 960)]
const PROPS := [["crate", Vector2(660, 960)], ["jar", Vector2(700, 1030)], ["crate", Vector2(1260, 960)], ["jar", Vector2(1220, 1030)]]
const EXIT := Vector2(960, 150)

var boss: SimFighter
var ally: SimFighter
var ally_ai: SimPartnerAI
var _down_t := -1.0
var _revive_t := {}               # 队友 id -> 爬起来倒计时
var _stats := {"start": 0.0, "combos": 0, "formations": 0, "breaks": 0, "defeats": 0, "loot": "—"}
var _got_loot := false


func _ready() -> void:
	map_size = Vector2(1920, 1080)
	world = SimWorld.new(Time.get_ticks_msec())
	world.bounds = PackedVector2Array(SceneLib.poly("cangjingge", "floor", FLOOR))
	for b in SceneLib.polys("cangjingge", "blocks", BLOCKS):
		world.blockers.append(PackedVector2Array(b))
	world.waypoints.assign(DOOR_PATH)
	me = world.add_hero("player", sect, utility, START)
	me.facing = Vector2.UP
	jingxin = world.add_hero("partner", "shaolin", SimData.PARTY.ai_utility, START + Vector2(-40, 4))
	jingxin.facing = Vector2.UP
	for p in LOULUO:
		world.add_enemy("louluo", p)
	for pr in PROPS:
		world.add_enemy(pr[0], pr[1])
	boss = world.add_enemy("dulao", DULAO_AT, true)
	boss.home = ARENA_CENTER + Vector2(0, -100)
	build_scene(SceneLib.background("cangjingge"), SceneLib.foreground("cangjingge"))
	hud.boss = boss
	hud.objectives = ["穿过后院回廊", "击退守卫 0 / 3"]
	say(Story.houdian_intro())


## 代玩：回廊里交给 AI，清完往大厅走；打完去捡防具
func auto_command() -> SimCommand:
	var cmd := auto_ai.command(DT)
	if stage == "to_hall":
		walk_to(cmd, HALL_START + Vector2(0, -40))
	elif stage == "leaving":
		for g in world.ground_items:
			if g.coins == 0 and SimItems.is_equipment(g.item):
				walk_to(cmd, g.pos)
				break
	return cmd


func after_step(dt: float) -> void:
	# 保险：毒姥战里玩家不该出大厅（有一次原生窗口截图拍到玩家在回廊，没能复现）；
	# 真出去了就拉回门口，并在控制台留下位置，方便以后查
	if stage == "boss" and me.alive and not world.walkable(me.pos):
		push_warning("毒姥战中玩家在大厅外：%s，已拉回" % me.pos)
		me.pos = HALL_START
	if stage == "corridor":
		var left := world.foes().filter(func(f): return f.kind == "louluo").size()
		hud.objectives = ["穿过后院回廊", "击退守卫 %d / 3" % (3 - left)]
		if left == 0:
			stage = "to_hall"
			hud.objectives = ["进藏经阁"]
	elif stage == "to_hall" and me.pos.y < HALL_ENTRY:
		_enter_hall()
	elif stage == "boss":
		_teach()
	elif stage == "leaving":
		_boss_leave(dt)
		if _got_loot and hud.barks_done():
			_finish()
			return
	_watch_down(dt)


## 第三人（拍板：临时 AI 侠客，和净心同一套 AI）的指令，由基类塞进同一帧
func extra_commands() -> Dictionary:
	if ally and ally_ai and ally.alive:
		return {ally.id: ally_ai.command(DT)}
	return {}


func _enter_hall() -> void:
	stage = "hall_talk"
	hud.objectives = []
	world.bounds = PackedVector2Array(SceneLib.poly("cangjingge", "hall", HALL))
	world.waypoints.clear()
	for f in [me, jingxin]:
		if not world.walkable(f.pos):
			f.pos = HALL_START + (Vector2(-40, 0) if f == jingxin else Vector2.ZERO)
	var third: Dictionary = SimData.PARTY.third
	if third.enabled:
		ally = world.add_hero(third.kind, third.sect, third.utility, HALL_START + Vector2(160, -20))
		ally.facing = Vector2.LEFT
		ally_ai = SimPartnerAI.new(world, ally.id, me.id)
		hud.extra_partners = [ally]
		hud.bark(third.name, third.join_line, 4.0)
	world.formation_enabled = third.enabled
	say(Story.dulao_intro())


func level_events(events: Array) -> void:
	for e in events:
		match e.type:
			"combo_freeze":
				if e.kind == "formation":
					_stats.formations += 1
					hud.toast("金刚伏魔圈成立！默契 %d" % world.combo.moqi)
				else:
					_stats.combos += 1
					hud.toast("合击成立！默契 %d" % world.combo.moqi)
			"formation_degrade":
				hud.toast("只到了一人——阵法退化成双人合击，破罩只有 5 秒")
			"combo_timeout":
				if e.id == me.id:
					hud.toast("没人响应，退化成普通招式；默契归零")
			"combo_invite":
				if e.id != me.id and e.get("kind", "") == "formation":
					tip("formation", "队友在摆金刚伏魔圈：%s，或走进金色光圈（要三人到齐）" % ("点「合击」" if hud.mobile else "按 F"), 4.0)
			"ward_break":
				_stats.breaks += 1
				hud.toast("毒罩碎了！%d 秒内全力输出" % int(e.secs), 2.5)
			"fog_close":
				hud.toast("毒雾在收口——再不摆阵破罩，最后这一圈也要没了！", 3.0)
			"fog_start":
				tip("fog", "毒雾从四边压进来：待在圈里，摆阵能净化脚下的雾", 4.0)
			"rooted":
				if e.id == me.id:
					tip("rooted", "你被摄魂指定住了：截脉能自解，队友也会来给你解", 3.5)
			"cleanse":
				if e.id == me.id and e.by != me.id:
					hud.toast("%s 给你解了穴" % world.fighter(e.by).name, 2.0)
			"boss_sit":
				if e.kind == "dulao":
					_on_dulao_down()
			"pickup":
				if stage == "leaving" and e.has("item") and SimItems.is_equipment(e.item):
					_stats.loot = "%s（%s）" % [SimItems.display_name(e.item), SimItems.quality_name(e.item)]
					_got_loot = true
					if autoplay:
						world.inv_equip(me, int(e.item.uid))
			"hero_down":
				if e.id == me.id:
					_down_t = 2.0
					_stats.defeats += 1
					hud.toast("你败退了……", 2.0)
				else:
					_revive_t[e.id] = 8.0
					hud.toast("%s倒下了，撑一会儿会爬起来" % world.fighter(e.id).name, 3.0)


func _on_dialogue_done() -> void:
	match stage:
		"intro":
			stage = "corridor"
			_stats.start = world.time
			tip("props", "木箱、酒坛打碎了有东西", 3.0)
		"hall_talk":
			stage = "boss"
			boss.state = "chase"
			boss.in_combat = true
			hud.objectives = ["躲开毒雾与毒池", "三人摆阵（%s）震碎毒罩" % ("合击键" if hud.mobile else "F")]


## 毒姥收手：字幕播剧情（不暂停），她往后殿走，阿萝出来；防具留在原地
func _on_dulao_down() -> void:
	stage = "leaving"
	world.combo.invite = {}
	world.combo.preview.clear()
	hud.objectives = ["拾取毒姥留下的防具"]
	view.npcs = [{"pos": boss.pos + Vector2(70, -30), "name": "阿萝", "robe": Color("#7A6E62"), "hair": Color("#2B2320")}]
	for line in Story.dulao_down():
		hud.bark(line.who, line.text, 3.6)


## 毒姥往后殿走，走到门口就不见了（剧情字幕同时在播）
func _boss_leave(dt: float) -> void:
	if not boss.alive:
		return
	var to := EXIT - boss.pos
	if to.length() < 8.0:
		boss.alive = false
	else:
		boss.pos += to.normalized() * 40.0 * dt
		boss.facing = to.normalized()


func _teach() -> void:
	for e in world.foes():
		if e.state == "windup" and e.atk_id == "gu" and e.aim_point.distance_to(me.pos) < 80.0:
			tip("gu", "脚下红圈是毒蛊落点——走开或闪避", 3.0)


func _watch_down(dt: float) -> void:
	for id in _revive_t.keys():
		_revive_t[id] -= dt
		if _revive_t[id] <= 0.0 and me.alive:
			var f := world.fighter(id)
			revive(f, me.pos + Vector2(-30, 10), 0.4)
			if not world.walkable(f.pos):
				f.pos = me.pos
			_revive_t.erase(id)
			hud.toast("%s爬了起来" % f.name)
	if _down_t > 0.0:
		_down_t -= dt
		if _down_t <= 0.0:
			retry()


## 败退：回廊阶段回入口；毒姥战回大厅门口，毒姥回满血、毒雾散、毒罩复原
func retry() -> void:
	var in_hall := stage == "boss"
	var at := HALL_START if in_hall else START
	for f in [me, jingxin, ally]:
		if f:
			revive(f, at + Vector2(randf_range(-40, 40), 0), 1.0)
	me.qi = me.max_qi
	_revive_t.clear()
	world.combo.invite = {}
	world.combo.moqi = 0
	world.projectiles.clear()
	world.pools.clear()
	if in_hall:
		boss.hp = boss.max_hp
		boss.state = "chase"
		boss.pos = DULAO_AT
		boss.atk = {}
		boss.ward_t = 0.0
		boss.timers.clear()
		world.fog = {}
		world.safe_zones.clear()
	camera.reset_smoothing()
	hud.toast("再来一次", 2.0)


func _finish() -> void:
	stage = "end"
	save_profile()
	var stats := _stats.duplicate()
	stats["secs"] = world.time - _stats.start
	stats["moqi"] = world.combo.moqi
	stats["boss2"] = true
	done.emit(stats)
