## 关卡共用：世界、画面、镜头、战斗界面、对话、暂停、合击定格。茶棚与山门继承它。
## 每个物理帧：真人输入（或代玩 AI）+ AI 净心 → SimWorld.step → 关卡读事件 → 画面消费事件。
class_name LevelBase
extends Node

signal done(stats: Dictionary)
signal quit_to_title

const DT := 1.0 / 60.0
const CAMERA_LEAD := 36.0   # 镜头朝瞄准方向的提前量（规格书第五节）

var sect := "shaolin"
var utility := "jiemai"
var autoplay := false        # 开发用：AI 代玩玩家、自动翻对话
var map_size := Vector2(960, 540)
var world: SimWorld
var me: SimFighter
var jingxin: SimFighter
var ai: SimPartnerAI
var auto_ai: SimPartnerAI
var input: PlayerInput
var view: WorldView
var camera: Camera2D
var hud: Hud
var dialogue: DialogueBox
var freeze_rect: TextureRect
var pause_layer: Control
var stage := "intro"
var paused := false
var partner_active := true   # 净心是否由 AI 驱动（茶棚开场时他蹲着不动）
var _tips := {}


func setup(sect_id: String, utility_id: String) -> void:
	sect = sect_id
	utility = utility_id


## 子类先建好 world / me / jingxin，再调这个把画面和界面挂上
func build_scene(background: String, foreground := "") -> void:
	ai = SimPartnerAI.new(world, jingxin.id, me.id)
	view = WorldView.new()
	view.world = world
	view.me_id = me.id
	view.background = UiKit.tex(background)
	if foreground != "":
		view.foreground = UiKit.tex(foreground)
	add_child(view)

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

	pause_layer = _make_pause()
	layer.add_child(pause_layer)

	if autoplay:
		auto_ai = SimPartnerAI.new(world, me.id, jingxin.id)
		dialogue.auto = true
	camera.reset_smoothing()


func _unhandled_input(event: InputEvent) -> void:
	input.feed(event)
	if event.is_action_pressed("pause") or (event.is_action_pressed("cancel") and me.state != "charge" and me.state != "aim" and world.combo.preview.is_empty()):
		if not dialogue.visible and stage != "end":
			_set_paused(not paused)
			get_viewport().set_input_as_handled()


func _physics_process(dt: float) -> void:
	freeze_rect.visible = world.freeze_t > 0.0
	hud.visible = not dialogue.visible  # 对话时收起战斗界面（效果图 06）
	_update_camera(dt)
	if paused or dialogue.visible or stage == "end":
		return
	if view.hitstop > 0.0:
		view.hitstop -= dt
		return
	var cmds := {me.id: player_command()}
	if partner_active:
		cmds[jingxin.id] = ai.command(DT)
	world.step(DT, cmds)
	level_events(world.events)
	view.consume_events()
	after_step(dt)


func player_command() -> SimCommand:
	return auto_command() if autoplay else input.build(me, DT)


# ---------- 子类覆写 ----------

func auto_command() -> SimCommand:
	return auto_ai.command(DT)


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
	if view.shake > 0.0:
		camera.offset = Vector2(randf_range(-1, 1), randf_range(-1, 1)).round() * view.shake
		view.shake = maxf(0.0, view.shake - dt * 20.0)
	else:
		camera.offset = Vector2.ZERO


# ---------- 共用小工具 ----------

func say(lines: Array) -> void:
	dialogue.open(lines)


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
	retry()


## 子类覆写：这一段从头来
func retry() -> void:
	pass


func _set_paused(on: bool) -> void:
	paused = on
	pause_layer.visible = on
	if on:
		(pause_layer.get_child(1).get_child(0) as Button).grab_focus()
