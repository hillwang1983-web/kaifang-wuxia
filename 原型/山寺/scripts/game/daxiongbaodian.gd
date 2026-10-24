## 大雄宝殿（任务节点 6–7，小说第五章），占位地图 1920×1080：
## 下半寺后院子（过渡段：玄诚说的库房零件、殿门撞开）→ 殿门 → 上半大雄宝殿；
## 进殿锁边界、铁甲金刚醒来 → 打碎两侧零件堆拿零件 → 中央拼弩车 → 上车蓄力射出裂口、从裂口一侧输出、
## 预警冲撞时摆合击 / 阵法撞偏 → 金刚跪倒（「痛快」）→ 通关箱每人一件 → 净心收尾一句 → 结算。
class_name Daxiongbaodian
extends LevelBase

## 可走地面：大殿 + 殿门 + 院子
const FLOOR := [Vector2(300, 170), Vector2(1620, 170), Vector2(1620, 780), Vector2(1020, 780), Vector2(1020, 840),
	Vector2(1320, 840), Vector2(1320, 1064), Vector2(600, 1064), Vector2(600, 840), Vector2(900, 840),
	Vector2(900, 780), Vector2(300, 780)]
const HALL := [Vector2(300, 170), Vector2(1620, 170), Vector2(1620, 776), Vector2(300, 776)]
## 佛龛台基与四根殿柱
const BLOCKS := [
	[Vector2(820, 170), Vector2(1100, 170), Vector2(1100, 220), Vector2(820, 220)],
	[Vector2(600, 320), Vector2(640, 320), Vector2(640, 360), Vector2(600, 360)],
	[Vector2(1280, 320), Vector2(1320, 320), Vector2(1320, 360), Vector2(1280, 360)],
	[Vector2(600, 600), Vector2(640, 600), Vector2(640, 640), Vector2(600, 640)],
	[Vector2(1280, 600), Vector2(1320, 600), Vector2(1320, 640), Vector2(1280, 640)],
]
const GATE_PATH := [Vector2(960, 900), Vector2(960, 810), Vector2(960, 720)]
const START := Vector2(960, 1030)
const HALL_ENTRY := 770.0
const HALL_START := Vector2(960, 730)
const BALLISTA_AT := Vector2(960, 620)
const JINGANG_AT := Vector2(960, 290)
## 两侧零件堆：三样零件各在一堆，另有一堆只有钱药
const PILES := [["chassis", Vector2(400, 300)], ["arm", Vector2(1520, 300)], ["winch", Vector2(1520, 680)], ["", Vector2(400, 680)]]
## 散架后零件可能落的位置
const SPOTS := [Vector2(420, 330), Vector2(1500, 330), Vector2(420, 650), Vector2(1500, 650), Vector2(760, 470), Vector2(1160, 470)]
const CHEST_AT := Vector2(960, 470)

var boss: SimFighter
var ally: SimFighter
var ally_ai: SimPartnerAI
var chest := {}
var _down_t := -1.0
var _revive_t := {}
var _stats := {"start": 0.0, "combos": 0, "formations": 0, "deflects": 0, "bolts": 0, "breaks": 0, "defeats": 0, "loot": []}
var _end_t := -1.0


func _ready() -> void:
	map_size = Vector2(1920, 1080)
	world = SimWorld.new(Time.get_ticks_msec())
	world.bounds = PackedVector2Array(SceneLib.poly("daxiongbaodian", "floor", FLOOR))
	for b in SceneLib.polys("daxiongbaodian", "blocks", BLOCKS):
		world.blockers.append(PackedVector2Array(b))
	world.waypoints.assign(GATE_PATH)
	me = world.add_hero("player", sect, utility, START)
	me.facing = Vector2.UP
	jingxin = world.add_hero("partner", "shaolin", SimData.PARTY.ai_utility, START + Vector2(-40, 4))
	jingxin.facing = Vector2.UP
	var third: Dictionary = SimData.PARTY.third
	if third.enabled:
		ally = world.add_hero(third.kind, third.sect, third.utility, START + Vector2(40, 4))
		ally.facing = Vector2.UP
		ally_ai = SimPartnerAI.new(world, ally.id, me.id)
		ally_ai.porter = true  # 第三人帮着捡零件
	world.formation_enabled = third.enabled
	SimBallista.setup(world, BALLISTA_AT, SPOTS)
	for pr in PILES:
		var pile := world.add_enemy("pile", pr[1])
		if pr[0] != "":
			SimBallista.bind_pile(world, pile, pr[0])
	boss = world.add_enemy("jingang", JINGANG_AT, true)
	build_scene(SceneLib.background("daxiongbaodian"), SceneLib.foreground("daxiongbaodian"))
	ai.may_ride = true  # 净心：玩家不坐时上车打几发，玩家走过来就让座
	if auto_ai:
		auto_ai.porter = true
		auto_ai.may_ride = true
	if ally:
		hud.extra_partners = [ally]
	hud.boss = boss
	hud.objectives = ["进大雄宝殿"]
	say(Story.daxiong_intro())


## 代玩：院子里往殿里走；殿里交给 AI（捡零件、拼装、上车）；打完开箱、捡东西
func auto_command() -> SimCommand:
	var cmd := auto_ai.command(DT)
	if stage == "court":
		walk_to(cmd, HALL_START + Vector2(0, -40))
	elif stage == "loot":
		cmd = SimCommand.new()
		var target := Vector2.INF
		for g in world.ground_items:
			if g.coins == 0 and SimItems.is_equipment(g.item):
				target = g.pos
				break
		if chest.get("on", false):
			target = chest.pos
			if me.pos.distance_to(chest.pos) < 30.0:
				cmd.press("interact")
		if target != Vector2.INF:
			walk_to(cmd, target)
	return cmd


func extra_commands() -> Dictionary:
	if ally and ally_ai and ally.alive:
		return {ally.id: ally_ai.command(DT)}
	return {}


func after_step(dt: float) -> void:
	if stage == "boss" and me.alive and not world.walkable(me.pos):
		push_warning("金刚战中玩家在殿外：%s，已拉回" % me.pos)
		me.pos = HALL_START
	match stage:
		"court":
			if me.pos.y < HALL_ENTRY:
				_enter_hall()
		"boss":
			_objectives()
			_teach()
			if world.ballista.rider != -1 and world.ballista.charging and world.ballista.charge_t >= SimData.BALLISTA.charge_steps[1] 					and boss.pos.distance_to(world.ballista.center) > 70.0:
				_snap("aim")
		"loot":
			hud.objectives = ["打开通关箱" if chest.get("on", false) else "拾取战利品"]
			var left := world.ground_items.filter(func(g): return g.coins == 0 and SimItems.is_equipment(g.item))
			if not chest.get("on", false) and left.is_empty() and _end_t < 0.0:
				_end_t = 4.0
				hud.bark("净心", Story.daxiong_last(), 4.0)
		_:
			pass
	if _end_t > 0.0:
		_end_t -= dt
		if _end_t <= 0.0 and hud.barks_done():
			_finish()
			return
		elif _end_t <= 0.0:
			_end_t = 0.01
	_hints()
	_watch_down(dt)


## 互动提示：弩车（拼装 / 上车 / 下车）、通关箱
func _hints() -> void:
	var b := world.ballista
	var pts := []
	if me.state == "mounted":
		pts.append([b.center, "下车"])
	elif b.built and b.rider == -1:
		pts.append([b.center, "上弩车"])
	elif not b.built and b.installed.size() == SimData.BALLISTA.parts.size() and b.build_by == -1:
		pts.append([b.center, "拼装弩车（3 秒）"])
	if chest.get("on", false):
		pts.append([chest.pos, "开箱"])
	interact_hint(pts)


func _objectives() -> void:
	var b := world.ballista
	if me.state == "mounted":
		hud.objectives = ["按住%s蓄力、松开发射（三档）" % ("攻击键" if hud.mobile else "左键 / J"), "%s下车" % ("交谈键" if hud.mobile else "E ")]
	elif not b.built:
		var carrying := SimBallista.carried(world, me)
		var line := "弩车零件 %d / 3%s" % [b.installed.size() + world.parts.filter(func(p): return p.carrier != -1).size(),
			("（背着%s，送到中央）" % SimData.BALLISTA.part_names[carrying.part]) if not carrying.is_empty() else ""]
		hud.objectives = [line if b.installed.size() < 3 else "在中央拼装弩车（%s，3 秒）" % ("交谈键" if hud.mobile else "E"), "打碎两侧的零件堆"]
	else:
		hud.objectives = ["弩车耐久 %d / 3" % b.hp, "上弩车射出裂口，从裂口那一侧打", "冲撞预警时摆阵撞偏"]


func _enter_hall() -> void:
	stage = "hall_talk"
	hud.objectives = []
	world.bounds = PackedVector2Array(SceneLib.poly("daxiongbaodian", "hall", HALL))
	world.waypoints.clear()
	for f in [me, jingxin, ally]:
		if f and not world.walkable(f.pos):
			f.pos = HALL_START + Vector2(randf_range(-50, 50), 0)
	say(Story.jingang_intro())


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
			"enrage":
				hud.toast("铁甲金刚狂暴了：踏地震又密又重！", 3.0)
			"deflect":
				_stats.deflects += 1
				_snap("deflect")
				hud.toast("撞偏了！金刚失衡 %d 秒" % int(SimData.ENEMIES.jingang.deflect_stagger), 2.5)
			"telegraph":
				if e.atk == "charge":
					tip("charge", "它要撞%s！%s，或走进金色光圈，大家一起把它撞偏" % ["车" if world.ballista.built else "人", "点「合击」" if hud.mobile else "按 F"], 4.0)
				elif e.atk == "quake":
					tip("quake", "踏地震：落地前翻滚（%s）或梯云纵躲开" % ("闪避键" if hud.mobile else "空格"), 3.0)
			"part_pickup":
				if e.id == me.id:
					tip("carry", "背上了%s：送到殿中央就装上" % SimData.BALLISTA.part_names[e.part], 3.0)
			"part_install":
				hud.toast("装上%s（%d / 3）" % [SimData.BALLISTA.part_names[e.part], e.have], 2.0)
				if e.have == 3:
					tip("build", "零件齐了：在中央%s拼装，读条 3 秒，别走动、别挨打" % ("点「交谈」" if hud.mobile else "按 E"), 4.0)
			"build_broken":
				if e.id == me.id:
					hud.toast("拼装被打断了", 1.5)
			"ballista_built":
				hud.toast("弩车拼好了！", 2.0)
				tip("ride", "上车（%s）后按住攻击蓄力，松开发射；蓄得越久裂口越大" % ("交谈键" if hud.mobile else "E"), 4.0)
			"bolt_fire":
				_stats.bolts += 1
			"breach":
				tip("breach", "裂口！二十息内从裂口那一侧打，铁甲挡不住", 3.5)
			"ballista_hit":
				hud.toast("弩车挨了一下：耐久 %d / 3" % max(e.hp, 0), 2.0)
			"ballista_break":
				_stats.breaks += 1
				hud.toast("弩车散架了！零件散到了殿边，捡回来再拼", 3.0)
			"grab":
				if e.victim == me.id:
					hud.toast("被金刚抓起来扔了出去", 2.0)
			"deny":
				if e.id == me.id and e.skill == "ballista":
					hud.toast("零件还差 %d 样" % (3 - e.have), 1.5)
			"boss_sit":
				if e.kind == "jingang":
					_on_jingang_down()
			"pickup":
				if stage == "loot" and e.has("item") and SimItems.is_equipment(e.item):
					_stats.loot.append("%s（%s）" % [SimItems.display_name(e.item), SimItems.quality_name(e.item)])
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
			stage = "court"
			_stats.start = world.time
			hud.objectives = ["进大雄宝殿"]
		"hall_talk":
			stage = "boss"
			boss.state = "chase"
			boss.in_combat = true
			tip("parts", "它的壳太厚：先打碎两侧的零件堆，把底盘、弓臂、绞盘送到殿中央拼弩车", 5.0)


## 金刚跪倒：「痛快」；殿中央出现通关箱，每人开一件
func _on_jingang_down() -> void:
	stage = "loot"
	world.combo.invite = {}
	world.combo.preview.clear()
	for f in [me, jingxin, ally]:
		if f and f.state == "mounted":
			SimBallista.dismount(world, f)
	chest = world.add_interactable("chest", CHEST_AT)
	for line in Story.jingang_down():
		hud.bark(line.who, line.text, 2.6)


func _teach() -> void:
	if me.state == "mounted":
		return
	var b := world.ballista
	if b.built and b.rider == -1 and me.pos.distance_to(b.center) < 120.0:
		tip("ride_hint", "弩车空着：%s上车" % ("点「交谈」" if hud.mobile else "按 E "), 3.0)


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


## 败退：院子阶段回院子；金刚战回殿门，金刚回满血、裂口合上，弩车与零件保持原样
func retry() -> void:
	var in_hall := stage == "boss"
	var at := HALL_START if in_hall else START
	for f in [me, jingxin, ally]:
		if f:
			if f.state == "mounted":
				SimBallista.dismount(world, f)
			revive(f, at + Vector2(randf_range(-40, 40), 0), 1.0)
	me.qi = me.max_qi
	_revive_t.clear()
	world.combo.invite = {}
	world.combo.moqi = 0
	world.projectiles.clear()
	if in_hall:
		boss.hp = boss.max_hp
		boss.state = "chase"
		boss.pos = JINGANG_AT
		boss.atk = {}
		boss.atk_id = ""
		boss.breaches.clear()
		boss.timers.clear()
	camera.reset_smoothing()
	hud.toast("再来一次", 2.0)


## 开发截图（main 的 shots=aim,deflect）：关卡里到了这个时刻就通知 main 拍一张
func _snap(shot_name: String) -> void:
	if get_parent() and get_parent().has_method("snap"):
		get_parent().snap(shot_name)


func _finish() -> void:
	stage = "end"
	save_profile()
	var stats := _stats.duplicate()
	stats["secs"] = world.time - _stats.start
	stats["moqi"] = world.combo.moqi
	stats["loot"] = "、".join(_stats.loot) if not _stats.loot.is_empty() else "—"
	stats["boss3"] = true
	done.emit(stats)
