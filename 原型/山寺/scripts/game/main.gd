## 第一里程碑流程：开始界面 → 选门派 → 茶棚（节点 0）→ 进山门前选通用技 → 山门（节点 1–3）→ 结算。
## 界面按 UI设计/01–03 效果图：临时山门背景压暗，左侧或居中「墨底金边」面板。
extends Node

const BG := "res://assets/env/env_shanmen_placeholder_v01.png"

var sect := "shaolin"
var utility := "jiemai"
var _layer: CanvasLayer


## 开发用开关：命令行 `-- skip auto quit xiepai yungong`，网页 `?skip&auto`。
## skip 直接进山门；auto 由 AI 代玩、自动翻对话（冒烟测试用）；quit 打完退出并打印结算。
var dev := {}


func _ready() -> void:
	dev = _dev_flags()
	if dev.has("skip") or dev.has("auto"):
		sect = "xiepai" if dev.has("xiepai") else "shaolin"
		for u in SimData.UTILITIES:
			if dev.has(u):
				utility = u
		if dev.has("auto"):
			Engine.time_scale = 4.0 if not OS.has_feature("web") else 1.0
		_shanmen()
		return
	_title()


func _dev_flags() -> Dictionary:
	var out := {}
	var args := Array(OS.get_cmdline_user_args())
	if OS.has_feature("web"):
		var q = JavaScriptBridge.eval("location.search", true)
		if q is String:
			args += Array(q.trim_prefix("?").split("&"))
	for a in args:
		out[a.split("=")[0]] = true
	return out


func _reset() -> CanvasLayer:
	for c in get_children():
		c.queue_free()
	_layer = CanvasLayer.new()
	add_child(_layer)
	return _layer


func _backdrop(dim := 0.35) -> void:
	var bg := TextureRect.new()
	bg.texture = UiKit.tex(BG)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	_layer.add_child(bg)
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, dim)
	shade.set_anchors_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_layer.add_child(shade)


func _panel(rect: Rect2, parent: Node = null) -> Panel:
	var p := Panel.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = UiKit.PANEL
	sb.border_color = UiKit.BORDER
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(2)
	p.add_theme_stylebox_override("panel", sb)
	p.position = rect.position
	p.size = rect.size
	(parent if parent else _layer).add_child(p)
	return p


func _label(parent: Node, text: String, pos: Vector2, size := 12, color := UiKit.TEXT, width := 0.0) -> Label:
	var l := Label.new()
	l.text = text
	l.position = pos
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if width > 0.0:
		l.size = Vector2(width, size + 6)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		l.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	parent.add_child(l)
	return l


# ---------- 开始界面（01） ----------

func _title() -> void:
	_reset()
	_backdrop(0.15)
	var p := _panel(Rect2(48, 40, 336, 456))
	_label(p, "山寺归僧", Vector2(0, 66), 36, UiKit.QI, 336)
	_label(p, "慈云寺 · 山门风波", Vector2(0, 122), 12, UiKit.TEXT, 336)
	var start := MenuButtonUi.make("开始游戏")
	start.position = Vector2(58, 194)
	start.pressed.connect(_sect_select)
	p.add_child(start)
	var cont := MenuButtonUi.make("继续游戏")
	cont.position = Vector2(58, 254)
	cont.disabled = true
	p.add_child(cont)
	_label(p, "第一里程碑试玩 · 角色与场景为占位图", Vector2(0, 336), 12, UiKit.MUTED, 336)
	_label(p, "确认：Enter / A / 点按", Vector2(0, 400), 12, UiKit.MUTED, 336)
	start.grab_focus()


# ---------- 选门派（02） ----------

func _card(rect: Rect2, title: String, title_color: Color, img: Texture2D, img_size: Vector2, desc: String, on_pick: Callable) -> Button:
	var b := Button.new()
	b.position = rect.position
	b.size = rect.size
	b.focus_mode = Control.FOCUS_ALL
	for state in ["normal", "hover", "pressed", "focus"]:
		var sb := StyleBoxFlat.new()
		sb.bg_color = UiKit.PANEL
		sb.border_color = UiKit.BORDER if state != "normal" else Color(UiKit.BORDER, 0.55)
		sb.set_border_width_all(1 if state == "normal" else 2)
		b.add_theme_stylebox_override(state, sb)
	b.pressed.connect(on_pick)
	_layer.add_child(b)
	_label(b, title, Vector2(0, 18), 24, title_color, rect.size.x)
	var t := TextureRect.new()
	t.texture = img
	t.size = img_size
	t.stretch_mode = TextureRect.STRETCH_SCALE
	t.position = Vector2((rect.size.x - img_size.x) / 2.0, 60)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(t)
	_label(b, desc, Vector2(12, rect.size.y - 44), 12, UiKit.TEXT, rect.size.x - 24)
	return b


func _sect_select() -> void:
	_reset()
	_backdrop()
	_label(_layer, "选择门派", Vector2(0, 52), 24, UiKit.QI, 960)
	var confirm := MenuButtonUi.make("确认门派")
	confirm.position = Vector2(370, 466)
	var pick := func(s: String):
		sect = s
		confirm.text = "确认 · " + SimData.SECTS[s].name
		confirm.grab_focus()
	var a := _card(Rect2(96, 112, 352, 336), "少林", UiKit.QI, UiKit.ui("faction_shaolin"), Vector2(192, 224),
		"棍 · 近身强攻，蓄力护体", pick.bind("shaolin"))
	_card(Rect2(512, 112, 352, 336), "邪派", UiKit.PURPLE, UiKit.ui("faction_xiepai"), Vector2(192, 224),
		"刀 · 中距施毒，控场牵制", pick.bind("xiepai"))
	confirm.pressed.connect(_chapeng)
	_layer.add_child(confirm)
	confirm.text = "确认 · 少林"
	a.grab_focus()


# ---------- 茶棚（节点 0）----------

class ChapengBackdrop extends Control:
	func _draw() -> void:
		draw_rect(Rect2(0, 0, 960, 540), Color("#1C2233"))
		draw_rect(Rect2(0, 300, 960, 240), Color("#4A3B2A"))
		for i in 7:
			draw_rect(Rect2(60 + i * 140, 250 - (i % 3) * 30, 70, 60 + (i % 3) * 30), Color("#24302A"))
		draw_rect(Rect2(300, 210, 360, 18), Color("#7A6A48"))   # 茅草棚顶
		draw_rect(Rect2(316, 228, 8, 120), Color("#3B2A20"))
		draw_rect(Rect2(636, 228, 8, 120), Color("#3B2A20"))
		draw_rect(Rect2(380, 300, 90, 30), Color("#5A3F29"))   # 粗桌
		draw_rect(Rect2(520, 300, 90, 30), Color("#5A3F29"))
		draw_circle(Vector2(700, 326), 14, Color("#6E5A44"))     # 泥炉
		draw_rect(Rect2(790, 120, 60, 20), Color("#6E6A5E"))     # 远处寺顶
		UiKit.panel(self, Rect2(720, 16, 224, 24))
		UiKit.text(self, Vector2(732, 21), "场景图待出：山路茶棚", 12, UiKit.MUTED)


func _chapeng() -> void:
	_reset()
	var bd := ChapengBackdrop.new()
	bd.set_anchors_preset(Control.PRESET_FULL_RECT)
	_layer.add_child(bd)
	var d := DialogueBox.new()
	_layer.add_child(d)
	d.finished.connect(_utility_select)
	d.open(Story.chapeng(sect))


# ---------- 进山门前选通用技（03） ----------

func _utility_select() -> void:
	_reset()
	_backdrop()
	_label(_layer, "择一通用技，进入山门", Vector2(0, 52), 24, UiKit.QI, 960)
	_label(_layer, "仅可携带一项，确认后进入山门。", Vector2(0, 90), 12, UiKit.TEXT, 960)
	var confirm := MenuButtonUi.make("确认 · 截脉")
	confirm.position = Vector2(370, 466)
	var descs := {"tiyunzong": "短距闪现，避开锋芒。", "yungong": "自身疗伤，也可向同伴渡气。", "jiemai": "打断读条，夺回出手时机。"}
	var pick := func(u: String):
		utility = u
		confirm.text = "确认 · " + SimData.SKILLS[u].name
		confirm.grab_focus()
	var first: Button
	for i in 3:
		var u: String = SimData.UTILITIES[i]
		var c := _card(Rect2(96 + i * 268, 132, 232, 304), SimData.SKILLS[u].name, UiKit.QI, UiKit.icon("skill_" + u),
			Vector2(128, 128), descs[u], pick.bind(u))
		c.get_child(0).position.y = 210  # 名字放到图标下面
		if u == "jiemai":
			first = c
	utility = "jiemai"
	confirm.pressed.connect(_shanmen)
	_layer.add_child(confirm)
	first.grab_focus()


# ---------- 山门 ----------

func _shanmen() -> void:
	for c in get_children():
		c.queue_free()
	var level := Shanmen.new()
	level.setup(sect, utility)
	level.autoplay = dev.has("auto")
	level.done.connect(_end)
	level.quit_to_title.connect(_title)
	add_child(level)


func _end(stats: Dictionary) -> void:
	if dev.has("auto"):
		print("自动试玩结算：", stats)
		if dev.has("quit"):
			get_tree().quit(0)
			return
	_reset()
	_backdrop(0.45)
	var p := _panel(Rect2(270, 90, 420, 360))
	_label(p, "第一里程碑 · 完", Vector2(0, 28), 24, UiKit.QI, 420)
	_label(p, "山门 · 叛僧教头", Vector2(0, 64), 12, UiKit.TEXT, 420)
	var lines := [
		"门派：%s　　通用技：%s" % [SimData.SECTS[sect].name, SimData.SKILLS[utility].name],
		"用时：%d 分 %02d 秒" % [int(stats.secs) / 60, int(stats.secs) % 60],
		"合击成立 %d 次　　最终默契 %d" % [stats.combos, stats.moqi],
		"打断 %d 次　　闪过 %d 次　　败退 %d 次" % [stats.interrupts, stats.evades, stats.defeats],
		"阿萝在偏殿药房，毒姥看着。——待续",
	]
	for i in lines.size():
		_label(p, lines[i], Vector2(0, 108 + i * 30), 12, UiKit.TEXT if i < 4 else UiKit.MUTED, 420)
	var again := MenuButtonUi.make("再来一次")
	again.position = Vector2(100, 270)
	again.pressed.connect(_title)
	p.add_child(again)
	again.grab_focus()
