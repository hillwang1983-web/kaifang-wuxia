## 物品栏（规格书第七节）：10×6 格子 + 装备栏四格，金钱；另一页「武学」是熟练度壳（第三节）。
## 三种操作都能用：鼠标拖拽（右键快捷装备 / 使用）、触屏拖拽（点一下选中再点按钮）、手柄 / 键盘光标
## （方向键移动，A / 回车拿起放下，X / E 快捷装备或使用，B / Esc 放回或关闭，Y / I 换页）。
## 打开时单人版战斗暂停。物品操作都交给 SimWorld（以后联机即服务端），这里只显示。
## 图标是代码画的占位，等交换清单里的装备图标到了再换。
class_name InventoryUi
extends Control

signal changed          # 物品 / 装备 / 熟练度变了，关卡据此存档
signal closed

const SLOT_NAMES := {"weapon": "兵器", "armor": "防具", "acc1": "饰品", "acc2": "饰品"}
const SLOT_ORDER := ["weapon", "armor", "acc1", "acc2"]
const WOOD := Color("#3B2A20")
const LINE := Color("#6E6A5E")

var world: SimWorld
var me: SimFighter
var profile: Profile
var mobile := false
var tab := "items"            # items / skills

var cell := 32.0
var panel := Rect2()
var grid_origin := Vector2()
var slot_rects := {}
var tip_rect := Rect2()
var buttons := []             # [{rect, label, act}]

var selected := -1            # 选中的物品 uid（触屏点选、光标所在）
var hover := -1
var held := {}                # {uid, from: "grid"/槽名, grab: Vector2i}
var drag_pos := Vector2.ZERO
var _press_pos := Vector2.ZERO
var cursor := {"area": "grid", "cell": Vector2i.ZERO, "slot": "weapon"}
var cursor_on := false        # 用过手柄 / 键盘才显示光标
var skill_cursor := 0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	hide()


func open() -> void:
	_layout()
	_flash = ""
	held = {}
	selected = -1
	show()
	queue_redraw()


func close() -> void:
	if not held.is_empty():
		held = {}
	hide()
	closed.emit()


func inv() -> SimInventory:
	return world.inventories.get(me.id)


func _layout() -> void:
	cell = 40.0 if mobile else 32.0
	if mobile:
		panel = Rect2(16, 16, 928, 508)
		var o := Vector2(40, 84)
		slot_rects = {"weapon": Rect2(o, Vector2(48, 128)), "armor": Rect2(o + Vector2(60, 0), Vector2(88, 88)),
			"acc1": Rect2(o + Vector2(60, 100), Vector2(48, 48)), "acc2": Rect2(o + Vector2(112, 100), Vector2(48, 48))}
		grid_origin = Vector2(228, 84)
		tip_rect = Rect2(648, 84, 280, 240)
	else:
		panel = Rect2(112, 56, 736, 428)
		var o := Vector2(136, 120)
		slot_rects = {"weapon": Rect2(o, Vector2(40, 104)), "armor": Rect2(o + Vector2(52, 0), Vector2(72, 72)),
			"acc1": Rect2(o + Vector2(52, 84), Vector2(40, 40)), "acc2": Rect2(o + Vector2(100, 84), Vector2(40, 40))}
		grid_origin = Vector2(300, 120)
		tip_rect = Rect2(636, 120, 196, 192)


func _grid_rect() -> Rect2:
	return Rect2(grid_origin, Vector2(SimInventory.W, SimInventory.H) * cell)


func _cell_at(p: Vector2) -> Vector2i:
	var c := ((p - grid_origin) / cell).floor()
	return Vector2i(int(c.x), int(c.y))


func _slot_at(p: Vector2) -> String:
	for s in slot_rects:
		if slot_rects[s].has_point(p):
			return s
	return ""


func _item_rect(uid: int) -> Rect2:
	var e: Dictionary = inv().entries[uid]
	return Rect2(grid_origin + Vector2(e.pos) * cell, Vector2(SimItems.size_of(e.item)) * cell)


func _uid_at(p: Vector2) -> int:
	if _grid_rect().has_point(p):
		return inv().at_cell(_cell_at(p))
	var s := _slot_at(p)
	if s != "" and inv().equipped[s] != null:
		return int(inv().equipped[s].uid)
	return -1


func _slot_of_uid(uid: int) -> String:
	for s in SLOT_ORDER:
		if inv().equipped[s] != null and int(inv().equipped[s].uid) == uid:
			return s
	return ""


# ---------- 操作 ----------

func _pick(uid: int, grab: Vector2i) -> void:
	var s := _slot_of_uid(uid)
	held = {"uid": uid, "from": s if s != "" else "grid", "grab": grab}
	selected = uid


## 放下：落在格子上就移动 / 交换 / 叠堆或卸下到那一格；落在装备格上就装备；别处就放回原处
func _drop(p: Vector2, cell_override := Vector2i(-99, -99)) -> void:
	if held.is_empty():
		return
	var uid: int = held.uid
	var ok := false
	var slot := _slot_at(p) if cell_override.x == -99 else ""
	if cell_override.x != -99 or _grid_rect().has_point(p):
		var c: Vector2i = (cell_override if cell_override.x != -99 else _cell_at(p)) - held.grab
		if held.from == "grid":
			ok = world.inv_move(me, uid, c)
		else:
			ok = world.inv_unequip(me, held.from, c)
	elif slot != "":
		if held.from == "grid":
			ok = world.inv_equip(me, uid, slot)
		else:
			ok = held.from == slot
	held = {}
	if ok:
		changed.emit()
	queue_redraw()


## 快捷：格子里的装备 → 装上；装备栏里的 → 卸下；丹药 → 服用
func _quick(uid: int) -> void:
	if uid < 0:
		return
	var it := inv().item(uid)
	var ok := false
	_flash = ""
	if it.base == "pill":
		ok = world.use_pill(me)
		if not ok:
			_flash = "生命是满的，或丹药还在冷却" if me.hp >= me.max_hp or me.cd_of("pill") > 0 else "没有丹药"
	elif _slot_of_uid(uid) != "":
		ok = world.inv_unequip(me, _slot_of_uid(uid))
		if not ok:
			_flash = "物品栏放不下了"
	elif SimItems.is_equipment(it):
		ok = world.inv_equip(me, uid)
	if ok:
		changed.emit()
	queue_redraw()


var _flash := ""


func _set_study(i: int) -> void:
	var sk: String = _skill_list()[i]
	profile.study("" if profile.studying == sk else sk)
	changed.emit()
	queue_redraw()


func _skill_list() -> Array:
	return me.skills + [me.utility]


# ---------- 输入 ----------

func _input(event: InputEvent) -> void:
	if not visible:
		return
	get_viewport().set_input_as_handled()
	if event.is_action_pressed("inventory", false, true) or (event.is_action_pressed("ui_cancel") and held.is_empty()):
		close()
		return
	if event.is_action_pressed("skill_2"):
		tab = "skills" if tab == "items" else "items"
		queue_redraw()
		return
	# 触屏（手机上不认模拟出来的鼠标事件）
	if event is InputEventScreenTouch and event.index == 0:
		_pointer(event.position, event.pressed, false)
	elif event is InputEventScreenDrag and event.index == 0:
		drag_pos = event.position
		queue_redraw()
	elif event is InputEventMouseButton and not mobile:
		if event.button_index == MOUSE_BUTTON_LEFT:
			_pointer(event.position, event.pressed, false)
		elif event.button_index == MOUSE_BUTTON_RIGHT and event.pressed and tab == "items":
			_quick(_uid_at(event.position))
	elif event is InputEventMouseMotion and not mobile:
		drag_pos = event.position
		hover = _uid_at(event.position) if tab == "items" else -1
		cursor_on = false
		queue_redraw()
	else:
		_pad(event)


func _pointer(p: Vector2, pressed: bool, _right: bool) -> void:
	drag_pos = p
	cursor_on = false
	if pressed:
		_press_pos = p
		for b in buttons:
			if b.rect.has_point(p):
				b.act.call()
				return
		if tab == "skills":
			for i in _skill_list().size():
				if _skill_row(i).has_point(p):
					_set_study(i)
			return
		var uid := _uid_at(p)
		if uid >= 0:
			var grab := Vector2i.ZERO
			if _grid_rect().has_point(p):
				grab = _cell_at(p) - inv().entries[uid].pos
			_pick(uid, grab)
		else:
			selected = -1
	elif not held.is_empty():
		if p.distance_to(_press_pos) < 8.0:
			held = {}  # 点一下：只选中，不挪（触屏再点下方按钮装备 / 使用）
		else:
			_drop(p)
	queue_redraw()


func _pad(event: InputEvent) -> void:
	var dir := Vector2i.ZERO
	if event.is_action_pressed("ui_left"):
		dir = Vector2i.LEFT
	elif event.is_action_pressed("ui_right"):
		dir = Vector2i.RIGHT
	elif event.is_action_pressed("ui_up"):
		dir = Vector2i.UP
	elif event.is_action_pressed("ui_down"):
		dir = Vector2i.DOWN
	if tab == "skills":
		if dir.y != 0:
			skill_cursor = clampi(skill_cursor + dir.y, 0, _skill_list().size() - 1)
			cursor_on = true
		elif event.is_action_pressed("ui_accept"):
			_set_study(skill_cursor)
		queue_redraw()
		return
	if dir != Vector2i.ZERO:
		cursor_on = true
		_move_cursor(dir)
	elif event.is_action_pressed("ui_accept"):
		cursor_on = true
		var p := _cursor_point()
		if held.is_empty():
			var uid := _uid_at(p)
			if uid >= 0:
				var grab := Vector2i.ZERO
				if cursor.area == "grid":
					grab = cursor.cell - inv().entries[uid].pos
				_pick(uid, grab)
		else:
			_drop(p, cursor.cell if cursor.area == "grid" else Vector2i(-99, -99))
	elif event.is_action_pressed("ui_cancel") and not held.is_empty():
		held = {}
	elif event.is_action_pressed("skill_1") or event.is_action_pressed("interact"):
		_quick(_uid_at(_cursor_point()))
	else:
		return
	if held.is_empty():
		selected = _uid_at(_cursor_point())
	queue_redraw()


func _cursor_point() -> Vector2:
	if cursor.area == "grid":
		return grid_origin + (Vector2(cursor.cell) + Vector2(0.5, 0.5)) * cell
	return slot_rects[cursor.slot].get_center()


func _move_cursor(dir: Vector2i) -> void:
	if cursor.area == "grid":
		var c: Vector2i = cursor.cell + dir
		if c.x < 0:
			cursor.area = "equip"
			cursor.slot = "weapon" if c.y < 2 else "acc2"
			return
		cursor.cell = Vector2i(clampi(c.x, 0, SimInventory.W - 1), clampi(c.y, 0, SimInventory.H - 1))
		return
	# 装备栏：武器 | 防具 / 饰品一 饰品二
	var order := {"weapon": {Vector2i.RIGHT: "armor", Vector2i.DOWN: "acc1"},
		"armor": {Vector2i.LEFT: "weapon", Vector2i.DOWN: "acc1", Vector2i.RIGHT: ">"},
		"acc1": {Vector2i.UP: "armor", Vector2i.RIGHT: "acc2", Vector2i.LEFT: "weapon"},
		"acc2": {Vector2i.UP: "armor", Vector2i.LEFT: "acc1", Vector2i.RIGHT: ">"}}
	var nxt: String = order[cursor.slot].get(dir, cursor.slot)
	if nxt == ">":
		cursor.area = "grid"
		cursor.cell = Vector2i(0, 0 if cursor.slot == "armor" else 3)
	else:
		cursor.slot = nxt


# ---------- 绘制 ----------

func _process(_dt: float) -> void:
	if visible:
		queue_redraw()


func _skill_row(i: int) -> Rect2:
	return Rect2(panel.position + Vector2(24, 76 + i * 64), Vector2(panel.size.x - 48, 56))


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, Vector2(960, 540)), Color(0, 0, 0, 0.55))
	UiKit.panel(self, panel)
	# 页签
	var tabs := [["items", "物品"], ["skills", "武学"]]
	for i in 2:
		var r := Rect2(panel.position + Vector2(20 + i * 84, 14), Vector2(76, 28))
		var on: bool = tab == tabs[i][0]
		draw_rect(r, Color(UiKit.BORDER, 0.25) if on else Color(0, 0, 0, 0.3))
		draw_rect(r.grow(-0.5), UiKit.BORDER if on else Color(UiKit.BORDER, 0.4), false, 1.0)
		UiKit.text(self, r.position + Vector2(0, 2), tabs[i][1], 24 if mobile else 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	UiKit.text_r(self, panel.position + Vector2(panel.size.x - 20, 18), "金钱 %d　　%s" % [inv().coins, "Y / I 换页 · B / Esc 关闭" if not mobile else ""], 12, UiKit.QI)
	buttons = []
	if tab == "items":
		_draw_items()
	else:
		_draw_skills()
	var close_r := Rect2(panel.end - Vector2(116, 52), Vector2(96, 36))
	_button(close_r, "关闭", close)


func _button(r: Rect2, label: String, act: Callable) -> void:
	draw_texture_rect(UiKit.ui("button_normal"), r, false)
	UiKit.text(self, r.position + Vector2(0, (r.size.y - 12) / 2.0 - 1), label, 12, UiKit.TEXT, HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	buttons.append({"rect": r, "label": label, "act": act})


func _draw_items() -> void:
	# 装备栏
	for s in SLOT_ORDER:
		var r: Rect2 = slot_rects[s]
		draw_rect(r, Color(WOOD, 0.9))
		draw_rect(r.grow(-0.5), LINE, false, 1.0)
		var it = inv().equipped[s]
		if it != null and not (not held.is_empty() and held.uid == int(it.uid)):
			_draw_item(it, r.grow(-3))
		elif it == null:
			UiKit.text(self, r.position + Vector2(0, r.size.y / 2.0 - 7), SLOT_NAMES[s], 12, Color(UiKit.MUTED, 0.6), HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	UiKit.text(self, slot_rects.weapon.position + Vector2(0, -20), "装备", 12, UiKit.MUTED)
	# 格子
	var g := _grid_rect()
	draw_rect(g, WOOD)
	for x in SimInventory.W + 1:
		draw_line(g.position + Vector2(x * cell, 0), g.position + Vector2(x * cell, g.size.y), LINE, 1.0)
	for y in SimInventory.H + 1:
		draw_line(g.position + Vector2(0, y * cell), g.position + Vector2(g.size.x, y * cell), LINE, 1.0)
	for uid in inv().entries:
		if not held.is_empty() and held.uid == uid:
			continue
		var r := _item_rect(uid).grow(-2)
		_draw_item(inv().entries[uid].item, r)
		if uid == selected:
			draw_rect(r.grow(1), UiKit.BORDER, false, 2.0)
	# 拿在手上的：画在指针 / 光标处，并预览能不能放
	if not held.is_empty():
		var it := inv().item(held.uid)
		var size := Vector2(SimItems.size_of(it)) * cell
		var at: Vector2 = (_cursor_point() if cursor_on else drag_pos) - (Vector2(held.grab) + Vector2(0.5, 0.5)) * cell
		var target := _cell_at(at + Vector2(cell, cell) * 0.5)
		if _grid_rect().has_point(at + Vector2(cell, cell) * 0.5):
			var ok := inv().fits(SimItems.size_of(it), target, [held.uid]) or inv().occupants(Rect2i(target, SimItems.size_of(it)), [held.uid]).size() == 1
			draw_rect(Rect2(grid_origin + Vector2(target) * cell, size), Color(0.4, 1, 0.4, 0.25) if ok else Color(1, 0.3, 0.3, 0.3))
		_draw_item(it, Rect2(at, size).grow(-2), 0.85)
	if cursor_on:
		var cr: Rect2 = Rect2(_cursor_point() - Vector2(cell, cell) / 2.0, Vector2(cell, cell)) if cursor.area == "grid" else slot_rects[cursor.slot]
		draw_rect(cr.grow(1), UiKit.QI, false, 2.0)
	# 说明
	var show_uid := hover if hover >= 0 else selected
	if not held.is_empty():
		show_uid = held.uid
	_draw_tip(show_uid)
	# 触屏 / 鼠标都能点的按钮
	var by := panel.end.y - 52
	if selected >= 0 and held.is_empty():
		var it := inv().item(selected)
		if not it.is_empty():
			var label := "服用" if it.base == "pill" else ("卸下" if _slot_of_uid(selected) != "" else "装备")
			_button(Rect2(Vector2(grid_origin.x, by), Vector2(96, 36)), label, _quick.bind(selected))
	var hint := "拖动摆放 · 拖到装备格装备 · 右键快捷装备 / 服用" if not mobile else "拖动摆放 · 点选后用下方按钮"
	UiKit.text(self, Vector2(grid_origin.x + 112, by + 10), _flash if _flash != "" else hint, 12, UiKit.MUTED)


func _draw_tip(uid: int) -> void:
	UiKit.panel(self, tip_rect)
	if uid < 0:
		UiKit.text(self, tip_rect.position + Vector2(10, 10), "选中物品查看详情", 12, UiKit.MUTED)
		return
	var it := inv().item(uid)
	if it.is_empty():
		return
	UiKit.text(self, tip_rect.position + Vector2(10, 8), SimItems.display_name(it), 24, SimItems.quality_color(it))
	var y := 44.0
	for line in SimItems.describe(it):
		UiKit.text(self, tip_rect.position + Vector2(10, y), line, 12, SimItems.quality_color(it) if line.begins_with("◆") else UiKit.TEXT)
		y += 20.0


## 占位图标：按类型配色的块 + 名字首字 + 品质色描边（美术说明第八节：描边颜色按品质换）
func _draw_item(it: Dictionary, r: Rect2, alpha := 1.0) -> void:
	var fill: Color = {"weapon": Color("#5A3F29"), "armor": Color("#8C3B2E"), "accessory": Color("#5E8F7A")}.get(SimItems.slot_type(it), Color("#E8E2D2"))
	draw_rect(r, Color(fill, alpha))
	draw_rect(r.grow(-1), Color(SimItems.quality_color(it), alpha), false, 2.0)
	var nm: String = SimItems.base(it.base).name
	UiKit.text(self, r.position + Vector2(0, r.size.y / 2.0 - 13), nm.left(1), 24, Color(UiKit.TEXT, alpha), HORIZONTAL_ALIGNMENT_CENTER, r.size.x)
	if it.get("count", 1) > 1:
		UiKit.text_r(self, r.end - Vector2(3, 15), str(it.count), 12, Color(UiKit.TEXT, alpha))


func _draw_skills() -> void:
	UiKit.text(self, panel.position + Vector2(24, 52), "参悟中的武功每 %d 秒熟练度 +1，一次只能参悟一门；熟练度暂不影响战斗。" % int(Profile.STUDY_EVERY), 12, UiKit.MUTED)
	var list := _skill_list()
	for i in list.size():
		var r := _skill_row(i)
		var sk: String = list[i]
		var on := profile.studying == sk
		draw_rect(r, Color(UiKit.BORDER, 0.15) if on else Color(0, 0, 0, 0.25))
		draw_rect(r.grow(-0.5), UiKit.BORDER if (on or (cursor_on and skill_cursor == i)) else Color(LINE, 0.8), false, 1.0)
		draw_texture_rect(UiKit.icon("skill_" + sk), Rect2(r.position + Vector2(8, 4), Vector2(48, 48)), false)
		UiKit.text(self, r.position + Vector2(68, 8), SimData.SKILLS[sk].name, 24, UiKit.TEXT)
		UiKit.text(self, r.position + Vector2(220, 18), "熟练度 %d" % int(profile.proficiency.get(sk, 0)), 12, UiKit.QI)
		UiKit.text_r(self, r.position + Vector2(r.size.x - 12, 18), "参悟中…" if on else "点选参悟", 12, UiKit.QI if on else UiKit.MUTED)
