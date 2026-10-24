## 战斗界面：按 UI设计/布局参数_v01.json 摆放美术交付的框图与图标。
## 电脑：底部一排七个键；手机：左摇杆 + 右侧按键群（同时负责触屏输入）。
class_name Hud
extends Control

const ACTIONS := ["attack", "skill_1", "skill_2", "skill_3", "utility", "combo", "dodge"]
const DESK_X := [326, 418, 510, 602, 694, 786, 878]
const DESK_Y := 478
# 手机按钮：[中心 x, 中心 y, 直径]，顺序同 ACTIONS
const MOBILE := [[824, 458, 80], [704, 354, 64], [784, 354, 64], [864, 354, 64], [744, 458, 64], [664, 458, 64], [904, 458, 64]]
const MOBILE_INTERACT := [864, 270, 64]  # 交互键：只在够得着可交互物时出现
const STICK_CENTER := Vector2(126, 400)
const STICK_R := 64.0

var world: SimWorld
var me: SimFighter
var partner: SimFighter
var boss: SimFighter
var objectives: Array = []      # 当前目标，每行一条
var mobile := false
var toasts: Array = []          # {text, t}

# 触屏状态，PlayerInput 读取
var touch_move := Vector2.ZERO
var touch_aim := Vector2.ZERO   # 拖着技能键时的拖动方向（-1..1）
var touch_held := {}
var _touch_pressed := {}
var _touch_released := {}
var _stick_index := -1
var _button_touch := {}         # touch index -> action
var _button_origin := {}        # action -> 按下位置


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	mobile = OS.has_feature("web_android") or OS.has_feature("web_ios") or OS.has_feature("mobile")


func toast(s: String, secs := 3.0) -> void:
	for t in toasts:
		if t.text == s:
			t.t = secs
			return
	toasts.append({"text": s, "t": secs})
	if toasts.size() > 3:
		toasts.pop_front()


func take_pressed() -> Dictionary:
	var out := _touch_pressed
	_touch_pressed = {}
	return out


func take_released() -> Dictionary:
	var out := _touch_released
	_touch_released = {}
	return out


func _process(dt: float) -> void:
	for t in toasts:
		t.t -= dt
	toasts = toasts.filter(func(t): return t.t > 0.0)
	queue_redraw()


# ---------- 触屏 ----------

func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch or event is InputEventScreenDrag:
		mobile = true
	if not visible or me == null:
		return
	if event is InputEventScreenTouch:
		var pos: Vector2 = event.position
		if event.pressed:
			if pos.x < 480 and _stick_index < 0:
				_stick_index = event.index
				_update_stick(pos)
				get_viewport().set_input_as_handled()
				return
			var a := _button_at(pos)
			if a != "":
				_button_touch[event.index] = a
				_button_origin[a] = pos
				touch_held[a] = true
				_touch_pressed[a] = true
				get_viewport().set_input_as_handled()
		else:
			if event.index == _stick_index:
				_stick_index = -1
				touch_move = Vector2.ZERO
			if _button_touch.has(event.index):
				var a: String = _button_touch[event.index]
				_button_touch.erase(event.index)
				touch_held.erase(a)
				_touch_released[a] = true
				touch_aim = Vector2.ZERO
	elif event is InputEventScreenDrag:
		if event.index == _stick_index:
			_update_stick(event.position)
		elif _button_touch.has(event.index):
			var a: String = _button_touch[event.index]
			var off: Vector2 = event.position - _button_origin[a]
			touch_aim = (off / 60.0).limit_length(1.0) if off.length() > 10.0 else Vector2.ZERO


func _can_interact() -> bool:
	return me.alive and not world.interactable_near(me.pos).is_empty()


func _update_stick(pos: Vector2) -> void:
	var off := pos - STICK_CENTER
	touch_move = (off / STICK_R).limit_length(1.0)
	if touch_move.length() < 0.15:
		touch_move = Vector2.ZERO


func _button_at(pos: Vector2) -> String:
	if _can_interact() and pos.distance_to(Vector2(MOBILE_INTERACT[0], MOBILE_INTERACT[1])) <= MOBILE_INTERACT[2] * 0.5 + 6.0:
		return "interact"
	for i in ACTIONS.size():
		var b: Array = MOBILE[i]
		if pos.distance_to(Vector2(b[0], b[1])) <= b[2] * 0.5 + 6.0:
			return ACTIONS[i]
	return ""


# ---------- 绘制 ----------

func _draw() -> void:
	if me == null:
		return
	if mobile:
		_draw_self(Vector2(16, 16))
		if partner:
			_draw_party(Vector2(16, 128))
	else:
		_draw_self(Vector2(16, 416))
		if partner:
			_draw_party(Vector2(16, 16))
	if boss and boss.alive and boss.state != "wait":
		_draw_boss(Vector2(256, 16))
	_draw_objectives()
	_draw_invite()
	_draw_toasts()
	if mobile:
		_draw_mobile_controls()
	else:
		_draw_skill_bar()


func _draw_self(at: Vector2) -> void:
	draw_texture(UiKit.ui("selfbar"), at)
	UiKit.text(self, at + Vector2(12, 10), "你 · " + SimData.SECTS[me.sect].name)
	var rows := [["生命", me.hp, me.max_hp, UiKit.HEALTH], ["内力", me.qi, me.max_qi, UiKit.QI], ["身法", me.sp, SimData.PLAYER.sp, UiKit.DEX]]
	for i in 3:
		var y := 33 + i * 22
		UiKit.text(self, at + Vector2(12, y - 1), rows[i][0])
		var trough := Rect2(at + Vector2(56, y), Vector2(152, 11))
		UiKit.fill(self, trough, rows[i][1] / rows[i][2], rows[i][3])
		UiKit.text(self, trough.position + Vector2(0, -1), "%d / %d" % [rows[i][1], rows[i][2]], 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, trough.size.x)
	if me.primed:
		UiKit.text(self, at + Vector2(150, 10), "内力满", 12, UiKit.QI)
	elif me.shield > 0.0:
		UiKit.text(self, at + Vector2(150, 10), "金钟罩 %d" % me.shield, 12, UiKit.QI)


func _draw_party(at: Vector2) -> void:
	draw_texture(UiKit.ui("partybar"), at)
	UiKit.text(self, at + Vector2(12, 10), partner.name + ("（倒地）" if not partner.alive else ""))
	UiKit.text_r(self, at + Vector2(184, 10), "%d / %d" % [partner.hp, partner.max_hp], 12, UiKit.MUTED)
	UiKit.fill(self, Rect2(at + Vector2(12, 32), Vector2(172, 9)), partner.hp / partner.max_hp, UiKit.HEALTH)
	UiKit.fill(self, Rect2(at + Vector2(12, 49), Vector2(172, 5)), partner.qi / partner.max_qi, UiKit.QI)
	var lv := world.combo.level()
	UiKit.text(self, at + Vector2(12, 62), "默契")
	draw_texture(UiKit.ui("moqi_lv%d" % (lv + 1)), at + Vector2(48, 64))
	UiKit.text_r(self, at + Vector2(184, 62), ["一级", "二级", "三级"][lv] + " · %d" % world.combo.moqi, 12, UiKit.QI)


func _draw_boss(at: Vector2) -> void:
	draw_texture(UiKit.ui("bossbar"), at)
	UiKit.text(self, at + Vector2(16, 10), boss.name)
	UiKit.text_r(self, at + Vector2(432, 10), "%d / %d" % [boss.hp, boss.max_hp], 12, UiKit.MUTED)
	UiKit.fill(self, Rect2(at + Vector2(16, 31), Vector2(416, 11)), boss.hp / boss.max_hp, UiKit.HEALTH)
	var label := "架势"
	var ratio := 0.0
	var right := ""
	if boss.state == "cast":
		label = "重击蓄力 · 快打断！"
		ratio = boss.t / boss.atk.cast
		right = "%.1f / %.1f 秒" % [boss.t, boss.atk.cast]
	elif boss.state == "stagger":
		label = "失衡！普攻吃满"
		ratio = boss.stagger_t / SimData.ENEMIES.xuancheng.stance_break
	elif boss.state == "sit":
		label = "盘腿坐下了"
	UiKit.text(self, at + Vector2(16, 50), label, 12, UiKit.CAST if boss.state == "cast" else UiKit.TEXT)
	if right != "":
		UiKit.text_r(self, at + Vector2(432, 50), right, 12, UiKit.CAST)
	UiKit.fill(self, Rect2(at + Vector2(16, 67), Vector2(416, 6)), ratio, UiKit.CAST)


func _draw_objectives() -> void:
	if objectives.is_empty():
		return
	var at := Vector2(760, 112) if not mobile else Vector2(752, 112)
	draw_texture(UiKit.ui("taskbar"), at)
	UiKit.text(self, at + Vector2(12, 8), "当前目标")
	for i in mini(objectives.size(), 2):
		UiKit.text(self, at + Vector2(12, 32 + i * 20), "◆ " + objectives[i], 12, UiKit.TEXT)


func _draw_invite() -> void:
	var inv := world.combo.invite
	var at := Vector2(356, 360)
	if not world.combo.preview.is_empty() and world.combo.preview.has(me.id):
		UiKit.panel(self, Rect2(at, Vector2(248, 52)))
		UiKit.text(self, at + Vector2(56, 10), "摆放合击光圈")
		UiKit.text(self, at + Vector2(56, 28), "松开发出邀请 · %s 取消" % ("拖回" if mobile else "Esc"), 12, UiKit.MUTED)
		return
	if inv.is_empty():
		return
	var mine: bool = inv.from == me.id
	var blink := 0.75 + 0.25 * sin(world.time * 10.0)
	draw_texture(UiKit.ui("heji_invite"), at, Color(1, 1, 1, blink if not mine else 1.0))
	var ratio: float = inv.t / SimData.COMBO.window
	_arc(at + Vector2(26, 26), 18.0, ratio, UiKit.CAST)
	if mine:
		UiKit.text(self, at + Vector2(56, 8), "合击邀请已发出")
		UiKit.text(self, at + Vector2(56, 26), "等净心走进光圈 · %.1f 秒" % inv.t, 12, UiKit.MUTED)
	else:
		UiKit.text(self, at + Vector2(56, 8), "合击邀请！")
		UiKit.text(self, at + Vector2(56, 26), "%s 响应或走进光圈 · %.1f 秒" % ["点合击" if mobile else UiKit.KEY_HINTS.combo, inv.t], 12, UiKit.CAST)


func _arc(center: Vector2, r: float, ratio: float, color: Color) -> void:
	draw_arc(center, r, -PI / 2.0, -PI / 2.0 + TAU * ratio, 32, color, 3.0)


func _draw_toasts() -> void:
	var y := 112.0
	for t in toasts:
		var w := UiKit.text_width(t.text) + 24.0
		var a: float = clampf(t.t / 0.4, 0.0, 1.0)
		var r := Rect2(Vector2(480 - w / 2.0, y), Vector2(w, 24))
		draw_rect(r, Color(UiKit.PANEL, 0.87 * a))
		draw_rect(r.grow(-0.5), Color(UiKit.BORDER, a), false, 1.0)
		UiKit.text(self, r.position + Vector2(12, 5), t.text, 12, Color(UiKit.TEXT, a))
		y += 30.0


func _slot_icon(action: String) -> Texture2D:
	match action:
		"attack":
			return UiKit.icon("btn_attack")
		"dodge":
			return UiKit.icon("btn_dodge")
		"combo":
			return UiKit.icon("skill_heji")
		"interact":
			return UiKit.icon("btn_talk")
		"utility":
			return UiKit.icon("skill_" + me.utility)
	return UiKit.icon("skill_" + me.skills[int(action.right(1)) - 1])


func _slot_name(action: String) -> String:
	match action:
		"attack":
			return "普攻"
		"dodge":
			return "闪避"
		"combo":
			return "合击"
		"interact":
			return "熄灭"
		"utility":
			return SimData.SKILLS[me.utility].name
	return SimData.SKILLS[me.skills[int(action.right(1)) - 1]].name


## 返回 [冷却比例, 是否可用]
func _slot_state(action: String) -> Array:
	match action:
		"attack", "interact":
			return [0.0, true]
		"dodge":
			return [me.dodge_cd / SimData.PLAYER.dodge_cd if me.dodge_cd > 0 else 0.0, me.sp >= SimData.PLAYER.dodge_cost]
		"combo":
			return [world.combo.cd / SimData.COMBO.cd, true]
	var skill: String = me.utility if action == "utility" else me.skills[int(action.right(1)) - 1]
	var s: Dictionary = SimData.SKILLS[skill]
	return [me.cd_of(skill) / s.cd, me.qi >= s.cost]


func _draw_slot(action: String, center: Vector2, size: float) -> void:
	var st := _slot_state(action)
	var pressed: bool = touch_held.has(action) or Input.is_action_pressed(action)
	var base := UiKit.ui("btn_pressed" if pressed else ("btn_base" if st[1] else "btn_disabled"))
	var r := Rect2(center - Vector2(size, size) / 2.0, Vector2(size, size))
	draw_texture_rect(base, r, false)
	draw_texture_rect(_slot_icon(action), r, false, Color(1, 1, 1, 1.0 if st[1] else 0.45))
	if not st[1]:
		draw_texture_rect(UiKit.ui("skill_disabled"), r, false)
	UiKit.cooldown_pie(self, center, size * 0.47, st[0])
	var active_skill: bool = (me.state == "charge" or me.state == "aim") and action.begins_with("skill") \
		and me.skills[int(action.right(1)) - 1] == me.active_skill
	if active_skill:
		draw_arc(center, size * 0.5 + 2, 0, TAU, 40, UiKit.BORDER, 2.0)


func _draw_skill_bar() -> void:
	for i in ACTIONS.size():
		var c := Vector2(DESK_X[i], DESK_Y)
		_draw_slot(ACTIONS[i], c, 64.0)
		var key: String = UiKit.KEY_HINTS[ACTIONS[i]]
		var kw := UiKit.text_width(key) + 10.0
		UiKit.panel(self, Rect2(c + Vector2(-kw / 2.0, -50), Vector2(kw, 16)))
		UiKit.text(self, c + Vector2(-kw / 2.0, -49), key, 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, kw)
		var nm := _slot_name(ACTIONS[i])
		UiKit.panel(self, Rect2(c + Vector2(-42, 34), Vector2(84, 18)))
		UiKit.text(self, c + Vector2(-42, 35), nm, 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, 84)


func _draw_mobile_controls() -> void:
	draw_texture(UiKit.ui("stick_base"), STICK_CENTER - Vector2(64, 64))
	var knob := UiKit.ui("stick_knob_pressed" if _stick_index >= 0 else "stick_knob")
	draw_texture(knob, STICK_CENTER + touch_move * STICK_R * 0.7 - Vector2(28, 28))
	for i in ACTIONS.size():
		var b: Array = MOBILE[i]
		var c := Vector2(b[0], b[1])
		_draw_slot(ACTIONS[i], c, b[2])
		UiKit.text(self, c + Vector2(-40, b[2] * 0.5 + 1), _slot_name(ACTIONS[i]), 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, 80)
	if _can_interact():
		var c := Vector2(MOBILE_INTERACT[0], MOBILE_INTERACT[1])
		_draw_slot("interact", c, MOBILE_INTERACT[2])
		UiKit.text(self, c + Vector2(-40, MOBILE_INTERACT[2] * 0.5 + 1), _slot_name("interact"), 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, 80)
