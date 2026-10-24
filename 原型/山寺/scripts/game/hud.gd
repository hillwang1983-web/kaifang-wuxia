## 战斗界面：按 UI设计/布局参数_v01.json 摆放美术交付的框图与图标。
## 电脑：底部一排七个键；手机：左摇杆 + 右侧按键群（同时负责触屏输入）。
class_name Hud
extends Control

signal bag_pressed
signal pause_pressed

const ACTIONS := ["attack", "skill_1", "skill_2", "skill_3", "utility", "combo", "dodge"]
const DESK_X := [326, 418, 510, 602, 694, 786, 878]
const DESK_Y := 478
# 手机按钮：[中心 x, 中心 y, 直径]，顺序同 ACTIONS
const MOBILE := [[824, 458, 80], [704, 354, 64], [784, 354, 64], [864, 354, 64], [744, 458, 64], [664, 458, 64], [904, 458, 64]]
const TALK := [884, 262, 56]   # 手机上下文「交谈 / 互动」键：身边有火把、能说话的人时才出现
const STICK_CENTER := Vector2(126, 400)
const BAG_BTN := Rect2(856, 18, 36, 36)     # 手机右上：物品栏
const PAUSE_BTN := Rect2(902, 18, 36, 36)   # 手机右上：暂停（效果图 04 手机版的 Ⅱ）
const STICK_R := 64.0

var world: SimWorld
var me: SimFighter
var partner: SimFighter
var extra_partners: Array = []  # 第三人等更多队友，依次往下排
var boss: SimFighter
var barks: Array = []           # 不挡操作的字幕 {who, text, t}，一条一条播
var objectives: Array = []      # 当前目标，每行一条
var mobile := false
var force_mobile := false      # 开发开关 mobile：电脑上也显示手机界面
var can_talk := false           # 关卡每帧设置：身边有可互动的东西
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
	mobile = force_mobile or OS.has_feature("web_android") or OS.has_feature("web_ios") or OS.has_feature("mobile")


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
	if not barks.is_empty():
		barks[0].t -= dt
		if barks[0].t <= 0.0:
			barks.pop_front()
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
		if event.pressed and mobile and BAG_BTN.has_point(pos):
			bag_pressed.emit()
			get_viewport().set_input_as_handled()
			return
		if event.pressed and mobile and PAUSE_BTN.has_point(pos):
			pause_pressed.emit()
			get_viewport().set_input_as_handled()
			return
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


func _update_stick(pos: Vector2) -> void:
	var off := pos - STICK_CENTER
	touch_move = (off / STICK_R).limit_length(1.0)
	if touch_move.length() < 0.15:
		touch_move = Vector2.ZERO


func _button_at(pos: Vector2) -> String:
	if can_talk and pos.distance_to(Vector2(TALK[0], TALK[1])) <= TALK[2] * 0.5 + 6.0:
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
			_draw_party(Vector2(16, 128), partner)
		for i in extra_partners.size():
			_draw_party(Vector2(16, 224 + i * 96), extra_partners[i], false)
	else:
		_draw_self(Vector2(16, 416))
		if partner:
			_draw_party(Vector2(16, 16), partner)
		for i in extra_partners.size():
			_draw_party(Vector2(16, 112 + i * 96), extra_partners[i], false)
	if boss and boss.alive and boss.state != "wait":
		_draw_boss(Vector2(256, 16))
	_draw_objectives()
	_draw_invite()
	_draw_toasts()
	_draw_barks()
	if mobile:
		_draw_mobile_controls()
		for pair in [[BAG_BTN, "囊"], [PAUSE_BTN, "Ⅱ"]]:
			UiKit.panel(self, pair[0])
			UiKit.text(self, pair[0].position + Vector2(0, 6), pair[1], 24, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, pair[0].size.x)
	else:
		_draw_skill_bar()
		UiKit.text_r(self, Vector2(944, 386), "Tab 物品栏 · H 丹药", 12, UiKit.MUTED)


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
	var inv: SimInventory = world.inventories.get(me.id)
	if inv:
		UiKit.text_r(self, at + Vector2(212, 92), "丹药 ×%d" % inv.count("pill"), 12, UiKit.MUTED)
	if me.primed:
		UiKit.text(self, at + Vector2(150, 10), "内力满", 12, UiKit.QI)
	elif me.shield > 0.0:
		UiKit.text(self, at + Vector2(150, 10), "金钟罩 %d" % me.shield, 12, UiKit.QI)


func _draw_party(at: Vector2, who: SimFighter, show_moqi := true) -> void:
	draw_texture(UiKit.ui("partybar"), at)
	var state := "（倒地）" if not who.alive else ("（定身）" if who.root_t > 0.0 else "")
	UiKit.text(self, at + Vector2(12, 10), who.name + state)
	UiKit.text_r(self, at + Vector2(184, 10), "%d / %d" % [who.hp, who.max_hp], 12, UiKit.MUTED)
	UiKit.fill(self, Rect2(at + Vector2(12, 32), Vector2(172, 9)), who.hp / who.max_hp, UiKit.HEALTH)
	UiKit.fill(self, Rect2(at + Vector2(12, 49), Vector2(172, 5)), who.qi / who.max_qi, UiKit.QI)
	if not show_moqi:
		return
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
	if boss.kind == "dulao":
		_boss_dulao_status(at)
		return
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


## 毒姥：读条（摄魂指）优先；其次毒罩状态——罩着显示减伤，被震碎显示剩余秒数
func _boss_dulao_status(at: Vector2) -> void:
	var label := "毒罩 · 减伤 95%（摆阵或合击震碎）"
	var color := UiKit.POISON
	var ratio := 0.0
	var right := ""
	if boss.state == "cast":
		var tgt := world.fighter(boss.target_id)
		label = "摄魂指 · 点名%s" % (("「" + tgt.name + "」") if tgt else "")
		color = UiKit.CAST
		ratio = boss.t / boss.atk.cast
		right = "%.1f / %.1f 秒" % [boss.t, boss.atk.cast]
	elif boss.ward_t > 0.0:
		label = "毒罩已破！趁现在输出"
		color = UiKit.QI
		ratio = boss.ward_t / SimData.COMBO.break_formation
		right = "%.1f 秒" % boss.ward_t
	elif boss.state == "sit":
		label = "毒姥收手了"
		color = UiKit.TEXT
	UiKit.text(self, at + Vector2(16, 50), label, 12, color)
	if right != "":
		UiKit.text_r(self, at + Vector2(432, 50), right, 12, color)
	UiKit.fill(self, Rect2(at + Vector2(16, 67), Vector2(416, 6)), ratio, color)


## 字幕：不暂停、不挡操作（规格书第九节 Boss 二后叙事）
func bark(who: String, text: String, secs := 3.5) -> void:
	barks.append({"who": who, "text": text, "t": secs})


func barks_done() -> bool:
	return barks.is_empty()


func _draw_barks() -> void:
	if barks.is_empty():
		return
	var b: Dictionary = barks[0]
	var s: String = (b.who + "：" if b.who != "" else "") + b.text
	var w := minf(UiKit.text_width(s) + 24.0, 620.0)
	var y := 300.0 if mobile else 380.0
	var r := Rect2(Vector2(480 - w / 2.0, y), Vector2(w, 26))
	UiKit.panel(self, r)
	UiKit.text(self, r.position + Vector2(12, 6), s, 12, UiKit.TEXT if b.who != "" else UiKit.MUTED)


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
		UiKit.text(self, at + Vector2(56, 10), "摆放%s光圈" % ("阵法" if world.combo.formation_ready() else "合击"))
		UiKit.text(self, at + Vector2(56, 28), "松开发出邀请 · %s 取消" % ("拖回" if mobile else "Esc"), 12, UiKit.MUTED)
		return
	if inv.is_empty():
		return
	var mine: bool = inv.from == me.id
	var blink := 0.75 + 0.25 * sin(world.time * 10.0)
	draw_texture(UiKit.ui("heji_invite"), at, Color(1, 1, 1, blink if not mine else 1.0))
	var ratio: float = inv.t / SimData.COMBO.window
	_arc(at + Vector2(26, 26), 18.0, ratio, UiKit.CAST)
	var formation: bool = inv.get("kind", "combo") == "formation"
	var word := "阵法" if formation else "合击"
	if mine:
		UiKit.text(self, at + Vector2(56, 8), "%s邀请已发出" % word)
		var wait := "还差 %d 人进圈" % (inv.need - inv.responders.size()) if formation else "等队友走进光圈"
		UiKit.text(self, at + Vector2(56, 26), "%s · %.1f 秒" % [wait, inv.t], 12, UiKit.MUTED)
	else:
		UiKit.text(self, at + Vector2(56, 8), ("阵法邀请！（%d / %d）" % [inv.responders.size(), inv.need]) if formation else "合击邀请！")
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
		"utility":
			return SimData.SKILLS[me.utility].name
	return SimData.SKILLS[me.skills[int(action.right(1)) - 1]].name


## 返回 [冷却比例, 是否可用]
func _slot_state(action: String) -> Array:
	match action:
		"attack":
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
	if can_talk:
		var c := Vector2(TALK[0], TALK[1])
		var r := Rect2(c - Vector2(TALK[2], TALK[2]) / 2.0, Vector2(TALK[2], TALK[2]))
		draw_texture_rect(UiKit.ui("btn_pressed" if touch_held.has("interact") else "btn_base"), r, false)
		draw_texture_rect(UiKit.icon("btn_talk"), r, false)
		UiKit.text(self, c + Vector2(-40, TALK[2] * 0.5 + 1), "交谈", 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, 80)
