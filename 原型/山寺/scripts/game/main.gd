## 第一里程碑流程：开始界面 → 选门派 → 茶棚（节点 0）→ 进山门前选通用技 → 山门（节点 1–3）→ 结算。
## 界面按 UI设计/01–03 效果图：临时山门背景压暗，左侧或居中「墨底金边」面板。
extends Node

const BG := "res://assets/env/env_shanmen_placeholder_v01.png"

var sect := "shaolin"
var utility := "jiemai"
var profile: Profile
var _layer: CanvasLayer


## 开发用开关：命令行 `-- skip auto quit xiepai yungong`，网页 `?skip&auto`。
## skip 直接进山门；auto 由 AI 代玩、自动翻对话，从茶棚走到山门结算（冒烟测试用）；quit 打完退出并打印结算；
## fresh 先清空存档；mobile 强制手机界面（在电脑上看触屏布局用）；items 塞样品物品到单独的演示存档；torch 山门出生在火把旁；boss2 直接进藏经阁（Boss 二）；shots=秒,秒 存画面截图（原生窗口）。
var dev := {}


func _ready() -> void:
	# 手机上整数倍放大常常只能退回 1 倍，画面缩在中央（#25）：改为非整数等比缩放铺满；电脑保持整数倍，像素不糊
	if _is_phone():
		get_window().content_scale_stretch = Window.CONTENT_SCALE_STRETCH_FRACTIONAL
	dev = _dev_flags()
	if dev.has("auto"):
		Profile.path = "user://shansi_autotest.json"
		Profile.wipe()
	if dev.has("fresh"):
		Profile.wipe()
	if dev.has("items"):
		Profile.path = "user://shansi_demo.json"
		Profile.wipe()
	profile = Profile.load_or_new()
	if dev.has("items"):
		_demo_items()
	if dev.has("skip") or dev.has("auto") or dev.has("boss2"):
		sect = "xiepai" if dev.has("xiepai") else "shaolin"
		for u in SimData.UTILITIES:
			if dev.has(u):
				utility = u
		if dev.has("auto"):
			Engine.time_scale = 4.0 if not OS.has_feature("web") else 1.0
		if dev.has("boss2"):
			_cangjingge()
		elif dev.has("auto"):
			_chapeng()  # 代玩从茶棚走起，覆盖三张地图
		else:
			_shanmen()
		return
	_title()


## 开发开关 items：塞几件样品进单独的演示存档，用来看物品栏（不碰真存档）
func _demo_items() -> void:
	var r := RandomNumberGenerator.new()
	r.seed = 2026
	var inv := SimInventory.new()
	inv.coins = 128
	var n := 1
	for pair in [["gun", "rare"], ["dao", "magic"], ["pijia", "rare"], ["sengpao", "normal"], ["yupei", "magic"], ["fozhu", "rare"], ["xiujian", "normal"]]:
		var it := SimItems.roll_equipment(r, pair[0], pair[1])
		it.uid = n
		n += 1
		inv.add(it)
	var pill := SimItems.make_consumable("pill", 7)
	pill.uid = n
	inv.add(pill)
	inv.equip(1, "weapon")
	inv.equip(5, "acc1")
	profile.inventory = inv.to_dict()
	profile.proficiency = {"luohanquan": 12, "jinzhongzhao": 3}
	profile.studying = "luohanquan"


## 开发开关 shots=8,14,20：按真实秒数把画面存成 user://shot_秒数.png（原生窗口运行才有画面），最后一张存完退出
var _shot_times: Array = []
var _shot_clock := 0.0


func _process(dt: float) -> void:
	if _shot_times.is_empty():
		return
	_shot_clock += dt / maxf(Engine.time_scale, 0.001)
	if _shot_clock >= float(_shot_times[0]):
		var t: float = _shot_times.pop_front()
		var path := "user://shot_%02d.png" % int(t)
		get_viewport().get_texture().get_image().save_png(path)
		print("截图：", ProjectSettings.globalize_path(path))
		if _shot_times.is_empty():
			get_tree().quit(0)


func _is_phone() -> bool:
	return OS.has_feature("web_android") or OS.has_feature("web_ios") or OS.has_feature("mobile")


func _dev_flags() -> Dictionary:
	var out := {}
	var args := Array(OS.get_cmdline_user_args())
	if OS.has_feature("web"):
		var q = JavaScriptBridge.get_interface("location").search
		if q is String:
			args += Array(q.trim_prefix("?").split("&"))
	for a in args:
		out[a.split("=")[0]] = true
		if a.begins_with("shots="):
			_shot_times = Array(a.trim_prefix("shots=").split(",")).map(func(s): return float(s))
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
	var wipe := MenuButtonUi.make("清空存档")
	wipe.position = Vector2(58, 254)
	wipe.disabled = not profile.exists
	wipe.pressed.connect(_confirm_wipe.bind(wipe))
	p.add_child(wipe)
	if profile.exists:
		var inv := SimInventory.from_dict(profile.inventory)
		_label(p, "存档：金钱 %d · 物品 %d 件 · 已装备 %d 件" % [inv.coins, inv.entries.size(), inv.equipped_items().size()], Vector2(0, 306), 12, UiKit.MUTED, 336)
	_label(p, "第一里程碑试玩 · 角色与场景为占位图", Vector2(0, 336), 12, UiKit.MUTED, 336)
	_label(p, "确认：Enter / A / 点按", Vector2(0, 400), 12, UiKit.MUTED, 336)
	start.grab_focus()


## 清空存档要按两次，免得手滑
func _confirm_wipe(b: Button) -> void:
	if b.text != "再按一次确认":
		b.text = "再按一次确认"
		return
	Profile.wipe()
	profile = Profile.load_or_new()
	_title()


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

func _chapeng() -> void:
	for c in get_children():
		c.queue_free()
	var level := Chapeng.new()
	level.setup(sect, utility)
	level.profile = profile
	level.autoplay = dev.has("auto")
	level.done.connect(_after_chapeng)
	level.quit_to_title.connect(_title)
	add_child(level)


func _after_chapeng(_stats: Dictionary) -> void:
	if dev.has("auto"):
		_shanmen()
	else:
		_utility_select()


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
	level.profile = profile
	level.autoplay = dev.has("auto")
	level.done.connect(_after_shanmen)
	level.quit_to_title.connect(_title)
	add_child(level)


## 山门打完接后殿藏经阁（Boss 二）；两段的结算合在一起
var _run_stats := {}


func _after_shanmen(stats: Dictionary) -> void:
	_run_stats = stats
	_cangjingge()


func _cangjingge() -> void:
	for c in get_children():
		c.queue_free()
	var level := Cangjingge.new()
	level.setup(sect, utility)
	level.profile = profile
	level.autoplay = dev.has("auto")
	level.done.connect(_after_cangjingge)
	level.quit_to_title.connect(_title)
	add_child(level)


func _after_cangjingge(stats: Dictionary) -> void:
	var s := _run_stats.duplicate()
	s["secs"] = float(s.get("secs", 0.0)) + float(stats.secs)
	s["combos"] = int(s.get("combos", 0)) + int(stats.combos)
	s["formations"] = stats.formations
	s["breaks"] = stats.breaks
	s["defeats"] = int(s.get("defeats", 0)) + int(stats.defeats)
	s["moqi"] = stats.moqi
	s["loot"] = "%s、%s" % [s.get("loot", "—"), stats.loot]
	s["boss2"] = true
	_end(s)


func _end(stats: Dictionary) -> void:
	if dev.has("auto"):
		print("自动试玩结算：", stats)
		if dev.has("quit"):
			get_tree().quit(0)
			return
	_reset()
	_backdrop(0.45)
	var p := _panel(Rect2(270, 90, 420, 360))
	_label(p, "山门与藏经阁 · 完", Vector2(0, 28), 24, UiKit.QI, 420)
	_label(p, "叛僧教头 · 护法毒姥", Vector2(0, 64), 12, UiKit.TEXT, 420)
	var lines := [
		"门派：%s　　通用技：%s" % [SimData.SECTS[sect].name, SimData.SKILLS[utility].name],
		"用时：%d 分 %02d 秒" % [int(stats.secs) / 60, int(stats.secs) % 60],
		"合击 %d 次　　阵法 %d 次　　破罩 %d 次　　默契 %d" % [stats.combos, stats.get("formations", 0), stats.get("breaks", 0), stats.moqi],
		"打断 %d 次　　闪过 %d 次　　败退 %d 次" % [stats.interrupts, stats.evades, stats.defeats],
		"所获：%s" % stats.get("loot", "—"),
		"一年之约。大雄宝殿里那个铁东西，不认人。——待续",
	]
	for i in lines.size():
		_label(p, lines[i], Vector2(0, 100 + i * 28), 12, UiKit.TEXT if i < 5 else UiKit.MUTED, 420)
	var again := MenuButtonUi.make("再来一次")
	again.position = Vector2(100, 280)
	again.pressed.connect(_title)
	p.add_child(again)
	again.grab_focus()
