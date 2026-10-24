## 把键鼠、手柄、触屏合成一帧 SimCommand（在 _physics_process 里调用，与世界同步 60 帧）。
## 瞄准：手柄右摇杆 > 触屏拖技能键 > 最近动过的鼠标；都没有就留空，由世界按面向 / 最近敌人自动瞄。
class_name PlayerInput
extends RefCounted

const ACTIONS := ["attack", "skill_1", "skill_2", "skill_3", "utility", "combo", "dodge", "cancel", "interact"]
const MOUSE_IDLE := 2.0   # 鼠标多久不动就不再当瞄准

var hud: Hud
var mouse_pos := Vector2.ZERO
var _mouse_t := 99.0
var _mouse_left := {"pressed": false, "held": false, "released": false}
var _mouse_right := false


func _init(h: Hud) -> void:
	hud = h


## 由场景的 _unhandled_input 转进来
func feed(event: InputEvent) -> void:
	if hud.mobile:
		return  # 触屏模拟出来的鼠标事件一律不认
	if event is InputEventMouseMotion:
		mouse_pos = event.position
		_mouse_t = 0.0
	elif event is InputEventMouseButton:
		mouse_pos = event.position
		_mouse_t = 0.0
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				_mouse_left.pressed = true
				_mouse_left.held = true
			else:
				_mouse_left.held = false
				_mouse_left.released = true
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed:
			_mouse_right = true


func build(me: SimFighter, dt: float) -> SimCommand:
	_mouse_t += dt
	var cmd := SimCommand.new()
	cmd.move = Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if hud.touch_move.length() > 0.0:
		cmd.move = hud.touch_move
	var tp := hud.take_pressed()
	var tr := hud.take_released()
	for a in ACTIONS:
		if Input.is_action_just_pressed(a) or tp.has(a):
			cmd.pressed[a] = true
		if Input.is_action_pressed(a) or hud.touch_held.has(a):
			cmd.held[a] = true
		if Input.is_action_just_released(a) or tr.has(a):
			cmd.released[a] = true
	if _mouse_left.pressed:
		cmd.pressed["attack"] = true
	if _mouse_left.held:
		cmd.held["attack"] = true
	if _mouse_right:
		cmd.pressed["cancel"] = true
	_mouse_left.pressed = false
	_mouse_left.released = false
	_mouse_right = false
	# 按住普攻连续出三段（V0.4 手感）
	if cmd.held.has("attack") and me.atk_cd <= 0.0 and me.state != "dodge":
		cmd.pressed["attack"] = true
	# 瞄准
	var stick := Input.get_vector("aim_left", "aim_right", "aim_up", "aim_down")
	if stick.length() > 0.3:
		cmd.aim = stick.normalized()
		cmd.point = me.pos + stick * SimData.COMBO.preview_reach
		cmd.has_point = true
	elif hud.touch_aim.length() > 0.0:
		cmd.aim = hud.touch_aim.normalized()
		cmd.point = me.pos + hud.touch_aim * SimData.COMBO.preview_reach
		cmd.has_point = true
	elif _mouse_t < MOUSE_IDLE and not hud.mobile:
		var to := mouse_pos - me.pos
		if to.length() > 6.0:
			cmd.aim = to.normalized()
		cmd.point = mouse_pos
		cmd.has_point = true
	return cmd
