## 山门关卡（任务节点 1–3）：熄火把、清喽啰 → 铜锣响、玄诚现身 → 两阶段（教闪避、教打断）→ 坐地交代。
## 每个物理帧：真人输入 + AI 净心 → SimWorld.step → 画面消费事件。
class_name Shanmen
extends Node

signal done(stats: Dictionary)
signal quit_to_title

const DT := 1.0 / 60.0
## 临时山门背景（效果图同源）里能走的石板地面；下沿停在 y≈420，电脑版底部一排技能键不挡人
const BOUNDS := [Vector2(150, 226), Vector2(372, 214), Vector2(380, 150), Vector2(584, 150), Vector2(592, 214),
	Vector2(770, 214), Vector2(842, 300), Vector2(846, 400), Vector2(780, 418), Vector2(270, 418),
	Vector2(160, 344), Vector2(118, 290)]
const TORCHES := [Vector2(262, 252), Vector2(706, 248), Vector2(806, 380)]
const LOULUO := [Vector2(330, 290), Vector2(620, 286), Vector2(740, 350), Vector2(420, 250)]
const START := Vector2(500, 400)
const GATE := Vector2(482, 168)

var sect := "shaolin"
var utility := "jiemai"
var autoplay := false            # 开发用：AI 代玩玩家、自动翻对话
var _auto_ai: SimPartnerAI
var world: SimWorld
var me: SimFighter
var jingxin: SimFighter
var boss: SimFighter
var ai: SimPartnerAI
var input: PlayerInput
var view: WorldView
var hud: Hud
var dialogue: DialogueBox
var freeze_rect: TextureRect
var pause_layer: Control
var stage := "intro"
var paused := false
var _down_t := -1.0
var _partner_down_t := -1.0
var _tips := {}
var _stats := {"start": 0.0, "combos": 0, "interrupts": 0, "evades": 0, "defeats": 0}
var _shake_t := 0.0


func setup(sect_id: String, utility_id: String) -> void:
	sect = sect_id
	utility = utility_id


func _ready() -> void:
	world = SimWorld.new(Time.get_ticks_msec())
	world.bounds = PackedVector2Array(BOUNDS)
	me = world.add_hero("player", sect, utility, START)
	me.facing = Vector2.UP
	jingxin = world.add_hero("partner", "shaolin", "", START + Vector2(-34, 6))
	jingxin.facing = Vector2.UP
	ai = SimPartnerAI.new(world, jingxin.id, me.id)
	for p in TORCHES:
		world.add_interactable("torch", p)
	for p in LOULUO:
		world.add_enemy("louluo", p)
	boss = world.add_enemy("xuancheng", GATE, true)

	view = WorldView.new()
	view.world = world
	view.me_id = me.id
	view.background = UiKit.tex("res://assets/env/env_shanmen_placeholder_v01.png")
	add_child(view)

	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Hud.new()
	hud.add_to_group("hud")
	hud.world = world
	hud.me = me
	hud.partner = jingxin
	hud.boss = boss
	layer.add_child(hud)
	input = PlayerInput.new(hud)

	freeze_rect = TextureRect.new()
	freeze_rect.texture = UiKit.tex("res://assets/vfx/vfx_heji_freeze_v01.png")
	freeze_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	freeze_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	freeze_rect.hide()
	layer.add_child(freeze_rect)

	dialogue = DialogueBox.new()
	layer.add_child(dialogue)
	dialogue.finished.connect(_on_dialogue_done)

	pause_layer = _make_pause()
	layer.add_child(pause_layer)

	if autoplay:
		_auto_ai = SimPartnerAI.new(world, me.id, jingxin.id)
		dialogue.auto = true
	_objectives()
	_say(Story.shanmen_intro(sect))


func _unhandled_input(event: InputEvent) -> void:
	input.feed(event)
	if event.is_action_pressed("pause") or (event.is_action_pressed("cancel") and me.state != "charge" and me.state != "aim" and world.combo.preview.is_empty()):
		if not dialogue.visible and stage != "end":
			_set_paused(not paused)
			get_viewport().set_input_as_handled()


func _physics_process(dt: float) -> void:
	freeze_rect.visible = world.freeze_t > 0.0
	hud.visible = not dialogue.visible  # 对话时收起战斗界面（效果图 06）
	_apply_shake(dt)
	if paused or dialogue.visible or stage == "end":
		return
	if view.hitstop > 0.0:
		view.hitstop -= dt
		return
	var cmds := {me.id: _auto_command() if autoplay else input.build(me, DT), jingxin.id: ai.command(DT)}
	world.step(DT, cmds)
	_story_events()
	view.consume_events()
	_watch_down(dt)
	_teach()


## 代玩：先去熄还亮着的火把，路上和战斗交给 AI；玄诚读条时用通用技
func _auto_command() -> SimCommand:
	var cmd := _auto_ai.command(DT)
	if boss.state == "cast" and boss.t > 0.4:
		cmd.press("utility")
	for it in world.interactables:
		if it.on:
			if it.pos.distance_to(me.pos) < 40.0:
				cmd.press("interact")
			elif not world.foes().any(func(f): return f.in_combat and f.pos.distance_to(me.pos) < 120.0):
				cmd.move = (it.pos - me.pos).normalized()
			break
	return cmd


func _apply_shake(dt: float) -> void:
	if view.shake > 0.0:
		view.position = Vector2(randf_range(-1, 1), randf_range(-1, 1)).round() * view.shake
		view.shake = maxf(0.0, view.shake - dt * 20.0)
	else:
		view.position = Vector2.ZERO


# ---------- 剧情推进 ----------

func _story_events() -> void:
	for e in world.events:
		match e.type:
			"combo_freeze":
				_stats.combos += 1
				hud.toast("合击成立！默契 %d" % world.combo.moqi)
			"interrupt":
				if e.by == me.id or world.fighter(e.by) == jingxin:
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
					_tip("invite", "净心发来合击邀请：%s，或走进地上的金色光圈" % ("点「合击」" if hud.mobile else "按 F"), 4.0)
			"interact":
				hud.toast("火把熄了")
			"phase2":
				_say(Story.phase2())
				stage = "phase2_talk"
			"boss_sit":
				stage = "down_talk"
				world.combo.invite = {}
				world.combo.preview.clear()
				_say(Story.boss_down())
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
			stage = "boss_talk"
			hud.objectives = []
			boss.pos = GATE + Vector2(0, 70)
			_say(Story.boss_intro())


func _say(lines: Array) -> void:
	dialogue.open(lines)


func _on_dialogue_done() -> void:
	match stage:
		"intro":
			stage = "gate"
			_stats.start = world.time
			_tip("move", "WASD 移动，J 普攻（按住连击），空格闪避，E 熄火把" if not hud.mobile else "左摇杆移动，按住普攻连击，点闪避躲开红区", 5.0)
		"boss_talk":
			stage = "boss"
			boss.state = "chase"
			boss.in_combat = true
			hud.objectives = ["看红区，闪避他的横扫", "与净心完成合击"]
			_tip("read", "他在等你躲开：红区出现就闪避，出手前一刻闪过能让他失衡", 5.0)
		"phase2_talk":
			stage = "boss"
			hud.objectives = ["打断玄诚的蓄力重击", "截脉或合击都能打断"]
			if utility != "jiemai":
				_tip("no_jiemai", "你没带截脉：等净心发合击邀请，或自己按住 F 摆光圈", 5.0)
		"down_talk":
			stage = "end"
			var stats := _stats.duplicate()
			stats["secs"] = world.time - _stats.start
			stats["moqi"] = world.combo.moqi
			done.emit(stats)


func _objectives() -> void:
	var left := world.interactables.filter(func(it): return it.on).size()
	var foes := world.foes().filter(func(f): return f.kind == "louluo").size()
	hud.objectives = ["熄灭火把 %d / 3" % (3 - left), "击退守卫 %d / 4" % (4 - foes)]


func _tip(id: String, s: String, secs := 3.5) -> void:
	if _tips.has(id):
		return
	_tips[id] = true
	hud.toast(s, secs)


func _teach() -> void:
	for e in world.foes():
		if e.state == "windup" and e.pos.distance_to(me.pos) < 220.0:
			_tip("tele", "红色范围就是要挨打的地方——闪避（%s）" % ("点闪避" if hud.mobile else "空格"), 3.5)
		if e.state == "cast":
			_tip("cast", "玄诚在读条重击！%s" % ("截脉（K）打断" if utility == "jiemai" and not hud.mobile else "截脉或合击打断"), 3.5)
	if me.primed:
		_tip("primed", "内力积满：下一招附带硬直", 3.0)


# ---------- 败退与重来 ----------

func _watch_down(dt: float) -> void:
	if _partner_down_t > 0.0:
		_partner_down_t -= dt
		if _partner_down_t <= 0.0 and me.alive:
			_revive(jingxin, me.pos + Vector2(-30, 10), 0.4)
			hud.toast("净心爬了起来")
	if _down_t > 0.0:
		_down_t -= dt
		if _down_t <= 0.0:
			_retry()


func _revive(f: SimFighter, at: Vector2, ratio: float) -> void:
	f.alive = true
	f.state = "idle"
	f.hp = f.max_hp * ratio
	f.pos = at


## 败退：两人回到山门口满血重来；Boss 战里玄诚也回满血、回到阶段一
func _retry() -> void:
	_revive(me, START, 1.0)
	_revive(jingxin, START + Vector2(-34, 6), 1.0)
	me.qi = me.max_qi
	_partner_down_t = -1.0
	world.combo.invite = {}
	world.combo.moqi = 0
	world.projectiles.clear()
	world.pools.clear()
	if stage == "boss":
		boss.hp = boss.max_hp
		boss.phase = 1
		boss.state = "chase"
		boss.pos = GATE + Vector2(0, 70)
		boss.atk = {}
		hud.objectives = ["看红区，闪避他的横扫", "与净心完成合击"]
	hud.toast("再来一次", 2.0)


# ---------- 暂停 ----------

func _make_pause() -> Control:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.hide()
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.5)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.add_child(shade)
	var box := VBoxContainer.new()
	box.position = Vector2(370, 170)
	box.size = Vector2(220, 200)
	box.add_theme_constant_override("separation", 12)
	root.add_child(box)
	for pair in [["继续", _resume], ["重新开始这一段", _restart_section], ["返回标题", quit_to_title.emit]]:
		var b := MenuButtonUi.make(pair[0])
		b.pressed.connect(pair[1])
		box.add_child(b)
	return root


func _resume() -> void:
	_set_paused(false)


func _restart_section() -> void:
	_set_paused(false)
	_retry()


func _set_paused(on: bool) -> void:
	paused = on
	pause_layer.visible = on
	if on:
		(pause_layer.get_child(1).get_child(0) as Button).grab_focus()
