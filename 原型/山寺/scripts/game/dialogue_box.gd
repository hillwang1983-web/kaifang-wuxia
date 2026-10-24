## 底部对话框（ui_dialog_v01，928×132，左侧 96×96 头像位）。逐行显示，按 E / J / 回车 / 点按翻页。
## 不阻塞战斗以外的东西：对话开着时关卡自己决定要不要暂停世界。
class_name DialogueBox
extends Control

signal finished

const RECT := Rect2(16, 392, 928, 132)
const PORTRAITS := {"净心": "jingxin_normal", "净心·悲": "jingxin_sad", "玄诚": "xuancheng_cold", "玄诚·笑": "xuancheng_smile"}

var lines: Array = []   # {who, text}；who 为空是旁白，"信" 是血书
var index := 0
var _shown := 0.0       # 已显示的字数（逐字）
var _guard := 0.0       # 刚打开时防误触
var auto := false       # 开发用：自动翻页
var _last_tap := 0


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	hide()


func open(new_lines: Array) -> void:
	lines = new_lines
	index = 0
	_shown = 0.0
	_guard = 0.2
	show()
	queue_redraw()


func _process(dt: float) -> void:
	if not visible:
		return
	_guard = maxf(0.0, _guard - dt)
	_shown += dt * 40.0
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
	if event.is_action_pressed("interact") or event.is_action_pressed("attack") or event.is_action_pressed("ui_accept"):
		_advance()
		get_viewport().set_input_as_handled()


func _advance() -> void:
	if _guard > 0.0:
		return
	var full: int = lines[index].text.length()
	if _shown < full:
		_shown = full
		return
	index += 1
	_shown = 0.0
	if index >= lines.size():
		hide()
		finished.emit()


func _draw() -> void:
	if lines.is_empty() or index >= lines.size():
		return
	var line: Dictionary = lines[index]
	var who: String = line.who
	var shown: String = line.text.left(int(_shown))
	if who == "信":
		var paper := Rect2(240, 90, 480, 260)
		draw_rect(paper, Color("#E9DFC8"))
		draw_rect(paper.grow(-0.5), Color("#8C3B2E"), false, 1.0)
		UiKit.text(self, paper.position + Vector2(24, 18), "（一块撕下来的衣襟，血字歪歪扭扭，有几处已经糊了）", 12, Color("#5A4A40"))
		_wrap(shown, paper.position + Vector2(24, 52), 432, 34, Color("#8C1F1A"), 24)
		UiKit.text(self, paper.end - Vector2(150, 30), "点按 / E 继续", 12, Color("#5A4A40"))
		return
	draw_texture(UiKit.ui("dialog"), RECT.position)
	var text_x := 152.0
	if PORTRAITS.has(who):
		draw_texture(UiKit.portrait(PORTRAITS[who]), Vector2(32, 408))
	if who != "":
		UiKit.text(self, Vector2(text_x, 404), who.get_slice("·", 0), 24, UiKit.QI)
	_wrap(shown, Vector2(text_x, 438 if who != "" else 418), 920.0 - text_x, 18, UiKit.TEXT if who != "" else UiKit.MUTED)
	UiKit.text_r(self, Vector2(928, 500), "E / A / 点按 继续", 12, UiKit.MUTED)


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
