## 对话框两种：
## - 阻塞（开场演出）：底部大框（ui_dialog_v01，928×132，左侧 96×96 头像位；没有头像的行不留空框），
##   世界暂停，按 E / J / 回车 / 点屏幕任意处翻页；整段开场可从暂停菜单跳过。
## - 不阻塞（副本内，规格书第九节「副本内对话不阻塞任何玩家操作」）：Boss 血条下方的小框，世界照常跑、
##   战斗界面照常显示，只认交谈键（E / 十字上）或点这个小框翻页，普攻 / 技能 / 闪避不受影响；每行到时自动往下翻。
class_name DialogueBox
extends Control

signal finished

const RECT := Rect2(16, 392, 928, 132)
const MINI := Rect2(256, 176, 448, 60)   # 不阻塞时的小框：Boss 血条与提示条之下、人物头顶之上
const MINI_READ := [2.2, 0.12]          # 不阻塞时每行停留：基础秒数 + 每字秒数
const PORTRAITS := {"净心": "jingxin_normal", "净心·悲": "jingxin_sad", "玄诚": "xuancheng_cold", "玄诚·笑": "xuancheng_smile"}

var lines: Array = []   # {who, text}；who 为空是旁白，"信" 是血书
var index := 0
var _shown := 0.0       # 已显示的字数（逐字）
var _guard := 0.0       # 刚打开时防误触
var auto := false       # 开发用：自动翻页
var blocking := true    # 当前这段对话是否暂停世界
var _line_t := 0.0      # 不阻塞时这一行已经显示了多久
var _last_tap := 0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	hide()


func open(new_lines: Array, block := true) -> void:
	lines = new_lines
	index = 0
	_shown = 0.0
	_line_t = 0.0
	_guard = 0.2
	blocking = block
	# 不阻塞时整块不吃鼠标，点到小框以外就是正常的战斗点击
	mouse_filter = Control.MOUSE_FILTER_STOP if block else Control.MOUSE_FILTER_IGNORE
	show()
	queue_redraw()


func _process(dt: float) -> void:
	if not visible:
		return
	_guard = maxf(0.0, _guard - dt)
	_shown += dt * 40.0
	if not blocking and not lines.is_empty():
		_line_t += dt
		if _line_t >= MINI_READ[0] + MINI_READ[1] * String(lines[index].text).length():
			_next_line()
			return
	if auto and _guard <= 0.0:
		_shown = 9999.0
		_guard = 0.3
		index += 1
		if index >= lines.size():
			hide()
			finished.emit()
			return
	queue_redraw()


## 对话开着时，屏幕上任何位置点一下（鼠标或触屏）都翻页；不依赖控件的鼠标路由
func _input(event: InputEvent) -> void:
	if not visible:
		return
	var tap: bool = (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT) \
		or (event is InputEventScreenTouch and event.pressed)
	if tap and not blocking:
		# 不阻塞：只有点在小框上才算翻页，别处的点击留给战斗（鼠标左键是普攻）
		var pos: Vector2 = event.position
		if not MINI.has_point(pos):
			return
	if tap:
		get_viewport().set_input_as_handled()
		# 手机上一次点按会同时来触屏事件和模拟出来的鼠标事件，只算一次
		var now := Time.get_ticks_msec()
		if now - _last_tap < 150:
			return
		_last_tap = now
		_advance()


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	var page: bool = event.is_action_pressed("interact") if not blocking \
		else (event.is_action_pressed("interact") or event.is_action_pressed("attack") or event.is_action_pressed("ui_accept"))
	if page:
		_advance()
		get_viewport().set_input_as_handled()


func _advance() -> void:
	if _guard > 0.0:
		return
	var full: int = lines[index].text.length()
	if _shown < full:
		_shown = full
		return
	_next_line()


func _next_line() -> void:
	index += 1
	_shown = 0.0
	_line_t = 0.0
	if index >= lines.size():
		hide()
		finished.emit()


func _draw() -> void:
	if lines.is_empty() or index >= lines.size():
		return
	var line: Dictionary = lines[index]
	var who: String = line.who
	var shown: String = line.text.left(int(_shown))
	if not blocking:
		_draw_mini(who, shown)
		return
	if who == "信":
		var paper := Rect2(240, 90, 480, 260)
		draw_rect(paper, Color("#E9DFC8"))
		draw_rect(paper.grow(-0.5), Color("#8C3B2E"), false, 1.0)
		UiKit.text(self, paper.position + Vector2(24, 18), "（一块撕下来的衣襟，血字歪歪扭扭，有几处已经糊了）", 12, Color("#5A4A40"))
		_wrap(shown, paper.position + Vector2(24, 52), 432, 34, Color("#8C1F1A"), 24)
		UiKit.text(self, paper.end - Vector2(150, 30), "点按 / E 继续", 12, Color("#5A4A40"))
		return
	var frame := UiKit.ui("dialog")
	draw_texture(frame, RECT.position)
	var text_x := 152.0
	if PORTRAITS.has(who):
		draw_texture(UiKit.portrait(PORTRAITS[who]), Vector2(32, 408))
	else:
		# 旁白、没有头像的人：用框图自身的空白底盖掉头像框，文字顶到左边（#30）
		draw_texture_rect_region(frame, Rect2(RECT.position + Vector2(12, 12), Vector2(104, 104)), Rect2(200, 12, 104, 104))
		text_x = 32.0
	if who != "":
		UiKit.text(self, Vector2(text_x, 404), who.get_slice("·", 0), 24, UiKit.QI)
	_wrap(shown, Vector2(text_x, 438 if who != "" else 418), 920.0 - text_x, 18, UiKit.TEXT if who != "" else UiKit.MUTED)
	UiKit.text_r(self, Vector2(928, 500), "E / A / 点按 继续", 12, UiKit.MUTED)


## 不阻塞的小框：48×48 小头像（有的话）+ 说话人 + 两行字，右下角一条细进度表示这一行还剩多久
func _draw_mini(who: String, shown: String) -> void:
	UiKit.panel(self, MINI)
	var x := MINI.position.x + 10.0
	if PORTRAITS.has(who):
		draw_texture_rect(UiKit.portrait(PORTRAITS[who]), Rect2(MINI.position + Vector2(6, 6), Vector2(48, 48)), false)
		x = MINI.position.x + 62.0
	var y := MINI.position.y + 6.0
	if who != "":
		UiKit.text(self, Vector2(x, y), who.get_slice("·", 0), 12, UiKit.QI)
		y += 16.0
	_wrap(shown, Vector2(x, y), MINI.end.x - x - 8.0, 16, UiKit.TEXT if who != "" else UiKit.MUTED)
	var total: float = MINI_READ[0] + MINI_READ[1] * String(lines[index].text).length()
	draw_rect(Rect2(MINI.position + Vector2(0, MINI.size.y - 2), Vector2(MINI.size.x * clampf(1.0 - _line_t / total, 0.0, 1.0), 2)), Color(UiKit.QI, 0.6))


## 按宽度逐字折行
func _wrap(s: String, at: Vector2, width: float, line_h: float, color: Color, size := 12) -> void:
	var cur := ""
	var y := at.y
	for ch in s:
		if ch == "\n" or UiKit.text_width(cur + ch, size) > width:
			UiKit.text(self, Vector2(at.x, y), cur, size, color)
			y += line_h
			cur = "" if ch == "\n" else ch
		else:
			cur += ch
	UiKit.text(self, Vector2(at.x, y), cur, size, color)
