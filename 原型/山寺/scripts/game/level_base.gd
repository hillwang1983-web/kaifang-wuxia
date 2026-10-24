## 关卡共用：世界、画面、镜头、战斗界面、对话、暂停、合击定格。茶棚与山门继承它。
## 每个物理帧：真人输入（或代玩 AI）+ AI 净心 → SimWorld.step → 关卡读事件 → 画面消费事件。
class_name LevelBase
extends Node

signal done(stats: Dictionary)
signal quit_to_title

const DT := 1.0 / 60.0
const CAMERA_LEAD := 36.0   # 镜头朝瞄准方向的提前量（规格书第五节）

var sect := "shaolin"
var origin := ""             # 出身（Story.ORIGINS 之一）：只影响开场、进寺对话与 Boss 一收尾，不改任何战斗数值
var utility := "jiemai"
var autoplay := false        # 开发用：AI 代玩玩家、自动翻对话
var map_size := Vector2(960, 540)
var world: SimWorld
var me: SimFighter
var jingxin: SimFighter
var ai: SimPartnerAI
var auto_ai: SimPartnerAI
var input: PlayerInput
var sfx: Sfx
var view: WorldView
var camera: Camera2D
var hud: Hud
var dialogue: DialogueBox
var inventory_ui: InventoryUi
var profile: Profile          # 由 main 传入；没有就不存档（测试用）
var _save_t := 0.0
var _dirty := false
var _skip_freeze := false   # 合击定格时点了屏幕：跳过定格
var _swallow_t := 0.0     # 对话 / 物品栏刚关上：吞掉这一下按键，免得关对话的 E 顺手熄了火把
var freeze_rect: TextureRect
var pause_layer: Control
var stage := "intro"
var paused := false
var partner_active := true   # 净心是否由 AI 驱动（郎中开场时他蹲着不动）
var skippable := false       # 出身开场：暂停菜单里多一项「跳过开场」
var _tips := {}


func setup(sect_id: String, utility_id: String) -> void:
	sect = sect_id
	utility = utility_id


## 子类先建好 world / me / jingxin，再调这个把画面和界面挂上
func build_scene(background: Variant, foreground := "") -> void:
	if jingxin:
		ai = SimPartnerAI.new(world, jingxin.id, me.id)
	else:
		partner_active = false  # 开场里没有净心（郎中线除外）
	view = WorldView.new()
	view.world = world
	view.me_id = me.id
	view.background = background if background is Texture2D else UiKit.tex(background)
	if foreground != "":
		view.foreground = UiKit.tex(foreground)
	add_child(view)

	sfx = Sfx.new()
	sfx.world = world
	sfx.me_id = me.id
	add_child(sfx)

	camera = Camera2D.new()
	camera.limit_left = 0
	camera.limit_top = 0
	camera.limit_right = int(map_size.x)
	camera.limit_bottom = int(map_size.y)
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 8.0
	camera.position = me.pos
	add_child(camera)
	camera.make_current()

	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Hud.new()
	hud.add_to_group("hud")
	if get_parent() and get_parent().get("dev") is Dictionary and get_parent().dev.has("mobile"):
		hud.mobile = true
		hud.force_mobile = true
	hud.world = world
	hud.me = me
	hud.partner = jingxin
	layer.add_child(hud)
	input = PlayerInput.new(hud)
	input.to_world = func(p: Vector2) -> Vector2: return view.get_canvas_transform().affine_inverse() * p

	freeze_rect = TextureRect.new()
	freeze_rect.texture = UiKit.tex("res://assets/vfx/vfx_heji_freeze_v01.png")
	freeze_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	freeze_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	freeze_rect.hide()
	layer.add_child(freeze_rect)

	dialogue = DialogueBox.new()
	layer.add_child(dialogue)
	dialogue.finished.connect(_on_dialogue_done)

	if profile:
		Sfx.apply_volumes(profile.settings)
		if not profile.inventory.is_empty():
			world.inventories[me.id] = SimInventory.from_dict(profile.inventory)
		world.refresh_stats(me)
		me.hp = me.max_hp
		me.qi = me.max_qi
	else:
		profile = Profile.new()
	inventory_ui = InventoryUi.new()
	inventory_ui.world = world
	inventory_ui.me = me
	inventory_ui.profile = profile
	layer.add_child(inventory_ui)
	inventory_ui.changed.connect(func(): _dirty = true)
	inventory_ui.closed.connect(_on_inventory_closed)
	hud.bag_pressed.connect(open_inventory)
	hud.pause_pressed.connect(func(): _set_paused(true))

	sfx.play_music()
	pause_layer = _make_pause()
	layer.add_child(pause_layer)

	if autoplay:
		auto_ai = SimPartnerAI.new(world, me.id, jingxin.id if jingxin else me.id)
		auto_ai.use_skills = true
		dialogue.auto = true
	camera.reset_smoothing()


## 物品栏开关放在 _input（早于界面和 _unhandled_input），按下就处理，不和别的节点抢事件。
## 打不开时在控制台留一条原因，方便以后复现「第一次按 Tab 偶尔打不开」。
func _input(event: InputEvent) -> void:
	if world and world.freeze_t > 0.0 and ((event is InputEventMouseButton and event.pressed) or (event is InputEventScreenTouch and event.pressed)):
		_skip_freeze = true
	if not event.is_action_pressed("inventory", false, true) or inventory_ui == null or inventory_ui.visible:
		return
	var why := "对话中" if _blocking_dialogue() else ("已暂停" if paused else ("已结算" if stage == "end" else ""))
	if why != "":
		push_warning("物品栏没打开：%s" % why)
		return
	open_inventory()
	get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	input.feed(event)
	if event.is_action_pressed("pause") or (event.is_action_pressed("cancel") and me.state != "charge" and me.state != "aim" and world.combo.preview.is_empty()):
		if not _blocking_dialogue() and stage != "end":
			_set_paused(not paused)
			get_viewport().set_input_as_handled()


## 对话开着并且要停住世界（开场演出这类阻塞对话）
func _blocking_dialogue() -> bool:
	return dialogue.visible and dialogue.blocking


func _physics_process(dt: float) -> void:
	freeze_rect.visible = world.freeze_t > 0.0 and profile.settings.get("freeze", true)
	hud.visible = not _blocking_dialogue() and not inventory_ui.visible  # 阻塞对话、物品栏开着时收起战斗界面
	_update_camera(dt)
	_autosave(dt)
	if paused or _blocking_dialogue() or inventory_ui.visible or stage == "end":
		_swallow_t = 0.15
		return
	if profile.tick_study(dt):
		_dirty = true
	if view.hitstop > 0.0:
		view.hitstop -= dt
		return
	var pc := player_command()
	if _swallow_t > 0.0:
		# 阻塞的对话 / 物品栏 / 暂停刚关：只吞关掉它的确认键（交谈、普攻），闪避和技能照常
		_swallow_t -= dt
		pc.pressed.erase("interact")
		pc.pressed.erase("attack")
	if dialogue.visible:
		pc.pressed.erase("interact")  # 不阻塞的对话开着时，交谈键是翻页，不再拿去熄火把、捡东西
	var cmds := {me.id: pc}
	if partner_active and jingxin:
		cmds[jingxin.id] = ai.command(DT)
	cmds.merge(extra_commands())
	if world.freeze_t > 0.0 and (_skip_freeze or freeze_skip_pressed() or not profile.settings.get("freeze", true)):
		world.freeze_t = minf(world.freeze_t, 0.0001)  # 跳过定格：下一步就结算，判定和不跳完全一样
	_skip_freeze = false
	world.step(DT, cmds)
	_item_events(world.events)
	level_events(world.events)
	sfx.handle(world.events)
	_shot_events(world.events)
	view.consume_events()
	after_step(dt)


func player_command() -> SimCommand:
	return auto_command() if autoplay else input.build(me, DT)


# ---------- 物品栏与存档 ----------

func open_inventory() -> void:
	if inventory_ui.visible or _blocking_dialogue() or stage == "end":
		return
	inventory_ui.mobile = hud.mobile
	inventory_ui.open()


func _on_inventory_closed() -> void:
	_dirty = true


func _item_events(events: Array) -> void:
	for e in events:
		match e.type:
			"pickup":
				if e.has("coins"):
					hud.toast("金钱 +%d" % e.coins, 1.5)
				else:
					hud.toast("拾得：%s（%s）" % [SimItems.display_name(e.item), SimItems.quality_name(e.item)], 2.5)
				_dirty = true
			"bag_full":
				hud.toast("物品栏满了，先整理一下（Tab）", 2.5)
			"pill", "equip":
				_dirty = true


## 物品、装备、熟练度有变化就存；最多每秒写一次
func _autosave(dt: float) -> void:
	_save_t -= dt
	if _dirty and _save_t <= 0.0:
		save_profile()


func save_profile() -> void:
	_dirty = false
	_save_t = 1.0
	if profile and world.inventories.has(me.id):
		profile.inventory = world.inventories[me.id].to_dict()
		profile.save()


# ---------- 子类覆写 ----------

func auto_command() -> SimCommand:
	return auto_ai.command(DT)


## 更多 AI 队友（藏经阁的第三人）的指令
func extra_commands() -> Dictionary:
	return {}


func level_events(_events: Array) -> void:
	pass


func after_step(_dt: float) -> void:
	pass


func _on_dialogue_done() -> void:
	pass


# ---------- 镜头 ----------

## 跟随本地玩家，朝瞄准 / 面向方向轻微提前；震屏走镜头偏移，不动世界
func _update_camera(dt: float) -> void:
	var lead := me.facing
	if me.state == "aim" or me.state == "charge":
		lead = me.aim_dir
	camera.position = me.pos + lead * CAMERA_LEAD + Vector2(0, -16)
	if view.shake > 0.0 and not profile.settings.get("shake", true):
		view.shake = 0.0  # 设置里关了屏幕震动
	if view.shake > 0.0:
		camera.offset = Vector2(randf_range(-1, 1), randf_range(-1, 1)).round() * view.shake
		view.shake = maxf(0.0, view.shake - dt * 20.0)
	else:
		camera.offset = Vector2.ZERO


# ---------- 共用小工具 ----------

## 镜头跟着 focus（脚下）时，世界点 p 在 960×540 屏幕上的位置（镜头在地图边缘会被夹住）。
## 用来检查手机上关键物、人物站位不落进触屏操作区（#28，Hud.MOBILE_ZONES）
static func screen_pos(p: Vector2, focus: Vector2, map: Vector2) -> Vector2:
	var half := Vector2(480, 270)
	var cam := (focus + Vector2(0, -16)).clamp(half, map - half)
	return p - cam + half


static func in_mobile_zone(screen: Vector2) -> bool:
	return Hud.MOBILE_ZONES.any(func(z: Rect2): return z.has_point(screen))


## 单屏地图（镜头不动）在手机上的可走区 = 地面减去触屏操作区（#28），人和红区不会钻到按键 / 摇杆底下
static func mobile_bounds(floor: Array) -> PackedVector2Array:
	var poly := PackedVector2Array(floor)
	for z: Rect2 in Hud.MOBILE_ZONES:
		var rect := PackedVector2Array([z.position, Vector2(z.end.x, z.position.y), z.end, Vector2(z.position.x, z.end.y)])
		var parts := Geometry2D.clip_polygons(poly, rect)
		parts.sort_custom(func(a, b): return _area(a) > _area(b))
		poly = parts[0]
	return poly


static func _area(p: PackedVector2Array) -> float:
	var s := 0.0
	for i in p.size():
		s += p[i].cross(p[(i + 1) % p.size()])
	return absf(s) * 0.5


## 副本里的对话默认不阻塞（规格书第九节）；开场演出这类纯剧情段由关卡覆写 dialogue_blocks() 返回真
func say(lines: Array) -> void:
	dialogue.open(lines, dialogue_blocks())


func dialogue_blocks() -> bool:
	return false


func tip(id: String, s: String, secs := 3.5) -> void:
	if _tips.has(id):
		return
	_tips[id] = true
	hud.toast(s, secs)


func revive(f: SimFighter, at: Vector2, ratio: float) -> void:
	f.alive = true
	f.state = "idle"
	f.hp = f.max_hp * ratio
	f.pos = at


## 互动提示：points 为 [[位置, 文字], ...]，离玩家 48 像素内最近的那个亮提示、手机出「交谈」键
func interact_hint(points: Array) -> Variant:
	var best = null
	for p in points:
		if p[0].distance_to(me.pos) < 48.0 and (best == null or p[0].distance_to(me.pos) < best[0].distance_to(me.pos)):
			best = p
	hud.can_talk = best != null
	view.hint_text = "" if best == null else ("" if hud.mobile else "E ") + best[1]
	if best != null:
		view.hint_pos = best[0] + Vector2(0, -72)
	return best


## 代玩：沿路点走向目标（寻路交给世界）
func walk_to(cmd: SimCommand, target: Vector2) -> void:
	cmd.move = world.steer(me.pos, target)


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
	box.position = Vector2(250, 90)
	box.size = Vector2(220, 200)
	box.add_theme_constant_override("separation", 12)
	root.add_child(box)
	var items := [["继续", _resume], ["重新开始这一段", _restart_section], ["返回标题", quit_to_title.emit]]
	if skippable:
		items.insert(1, ["跳过开场", _skip_from_menu])
	for pair in items:
		var b := MenuButtonUi.make(pair[0])
		b.pressed.connect(pair[1])
		box.add_child(b)
	root.add_child(_make_settings())
	return root


## 暂停菜单右半边：音量三条总线、屏幕震动、本局关闭合击提示（规格书第四节防骚扰预留）
func _make_settings() -> Control:
	var panel := VBoxContainer.new()
	panel.position = Vector2(500, 90)
	panel.size = Vector2(220, 300)
	panel.add_theme_constant_override("separation", 8)
	for pair in [["音乐", "music"], ["音效", "sfx"], ["界面", "ui"]]:
		var l := Label.new()
		l.text = pair[0]
		panel.add_child(l)
		var s := HSlider.new()
		s.min_value = 0.0
		s.max_value = 1.0
		s.step = 0.05
		s.custom_minimum_size = Vector2(200, 20)
		s.value = float(profile.settings.get(pair[1], 0.8)) if profile else 0.8
		s.value_changed.connect(func(v: float):
			profile.settings[pair[1]] = v
			Sfx.apply_volumes(profile.settings)
			_dirty = true)
		panel.add_child(s)
	var freeze := CheckButton.new()
	freeze.text = "合击定格"
	freeze.button_pressed = profile.settings.get("freeze", true) if profile else true
	freeze.toggled.connect(func(on: bool):
		profile.settings["freeze"] = on
		_dirty = true)
	panel.add_child(freeze)
	var shake := CheckButton.new()
	shake.text = "屏幕震动"
	shake.button_pressed = profile.settings.get("shake", true) if profile else true
	shake.toggled.connect(func(on: bool):
		profile.settings["shake"] = on
		_dirty = true)
	panel.add_child(shake)
	var hints := CheckButton.new()
	hints.text = "本局关闭合击提示"
	hints.toggled.connect(set_combo_hints_muted)
	panel.add_child(hints)
	return panel


## 本局关闭合击提示（接口在世界的 combo.muted，按英雄记；界面不再弹邀请框、不响提示音、不画引导）。
## 只关提示，不关合击本身：光圈还在，按合击键照样能响应
func set_combo_hints_muted(on: bool) -> void:
	if on:
		world.combo.muted[me.id] = true
	else:
		world.combo.muted.erase(me.id)
	sfx.hints_muted = on
	hud.hints_muted = on
	view.hints_muted = on


func _resume() -> void:
	_set_paused(false)


func _restart_section() -> void:
	_set_paused(false)
	retry()


## 合击 / 阵法定格（不超过 0.5 秒）可跳过（规格书第四节）：普攻、合击、交谈、确认任一键刚按下，或点屏幕。
## 只认「刚按下」：按住普攻自动连击的那种按下不算，免得一直按着普攻的人每次定格都被跳掉
static func freeze_skip_pressed() -> bool:
	for a in ["attack", "combo", "interact", "ui_accept"]:
		if Input.is_action_just_pressed(a):
			return true
	return false


## 子类覆写：这一段从头来
func retry() -> void:
	pass


func _skip_from_menu() -> void:
	_set_paused(false)
	skip_intro()


## 开发截图（main 的 shots=skill,combo）：本地玩家出招、合击 / 阵法成立时通知 main 拍一张
func _shot_events(events: Array) -> void:
	var main := get_parent()
	if main == null or not main.has_method("snap"):
		return
	for e in events:
		if e.type == "skill" and e.get("id", -1) == me.id:
			main.snap("skill")
		elif e.type == "combo_burst":
			main.snap("combo")


## 子类覆写：跳过开场（只有出身开场用）
func skip_intro() -> void:
	pass


func _set_paused(on: bool) -> void:
	paused = on
	pause_layer.visible = on
	if on:
		(pause_layer.get_child(1).get_child(0) as Button).grab_focus()
