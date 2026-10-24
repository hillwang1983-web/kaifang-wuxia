## 流程：开始界面 → 选出身（四选一）→ 选门派 → 出身开场（现代十秒、附身醒来、开场演出与教学，可整段跳过）
## → 进山门前选通用技 → 山门（节点 1–3，进寺对话与 Boss 一收尾按出身分叉）→ 藏经阁（节点 4–5）
## → 大雄宝殿（节点 6–7）→ 三段合并结算 → 回开始界面。出身和门派分开选，出身不改任何战斗数值。
## 界面按 UI设计/01–03 效果图：临时山门背景压暗，左侧或居中「墨底金边」面板。
extends Node

const BG := "res://assets/env/env_shanmen_placeholder_v01.png"

var sect := "shaolin"
var utility := "jiemai"
var origin := "langzhong"
var profile: Profile
var _layer: CanvasLayer


## 开发用开关：命令行 `-- skip auto quit xiepai yungong`，网页 `?skip&auto`。
## skip 直接进山门；auto 由 AI 代玩、自动翻对话，从出身开场一路打到结算（冒烟测试用）；quit 打完退出并打印结算；
## origin=shenjia|tiejiang|xiban|langzhong 指定出身（代玩默认郎中）；skipintro 开场一开始就走「跳过开场」；
## until=shanmen 走到山门就打印代玩计时并退出；
## fresh 先清空存档；mobile 强制手机界面（在电脑上看触屏布局用）；items 塞样品物品到单独的演示存档；torch 山门出生在火把旁；
## boss2 直接进藏经阁（Boss 二）；boss3 直接进大雄宝殿（Boss 三）；shots=秒,秒 存画面截图（原生窗口）。
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
	if dev.has("skip") or dev.has("auto") or dev.has("boss2") or dev.has("boss3"):
		sect = "xiepai" if dev.has("xiepai") else "shaolin"
		for u in SimData.UTILITIES:
			if dev.has(u):
				utility = u
		if dev.get("pad", "") in ["xbox", "ps"]:
			UiKit.device = dev.pad  # 开发开关 pad=xbox|ps：没插手柄也能看手柄按键提示（截图用）
		if dev.get("origin", "") in Story.ORIGINS:
			origin = dev.origin
		Story.player_name = Story.origin(origin).get("default_name", "")
		if dev.has("auto"):
			# 加速：time_scale 只放大每个物理帧的 delta，不增加物理帧数；世界每帧固定走 1/60 秒，
			# 所以物理帧率要一起乘上去（每帧 delta 仍是 1/60），整局才真的快。无界面（冒烟、发布构建）八倍，窗口四倍
			var speed := 1.0 if OS.has_feature("web") else (8.0 if DisplayServer.get_name() == "headless" else 4.0)
			Engine.time_scale = speed
			Engine.physics_ticks_per_second = int(60 * speed)
			Engine.max_physics_steps_per_frame = 16
		if dev.has("boss3"):
			_daxiong()
		elif dev.has("boss2"):
			_cangjingge()
		elif dev.has("auto"):
			_prologue()  # 代玩从出身开场走起，覆盖全部地图
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


## 开发开关 shots=8,14,20：按真实秒数把画面存成 user://shot_秒数.png（原生窗口运行才有画面），最后一张存完退出。
## 也可以写事件名（shots=aim,deflect）：关卡里发生这件事时调 snap(名字)，稍等一下存成 user://shot_名字.png
var _shot_times: Array = []
var _shot_names: Array = []
var _shot_pending := {}      # 名字 -> 还要等几秒（真实时间）再拍，让特效先出来
var _shot_clock := 0.0


func snap(shot_name: String) -> void:
	if shot_name in _shot_names:
		_shot_names.erase(shot_name)
		_shot_pending[shot_name] = 0.12


func _save_shot(path: String) -> void:
	get_viewport().get_texture().get_image().save_png(path)
	print("截图：", ProjectSettings.globalize_path(path))
	if _shot_times.is_empty() and _shot_names.is_empty() and _shot_pending.is_empty():
		get_tree().quit(0)


## 开发开关 fps：每 5 秒（真实时间）打印一次平均帧率和最低帧率，记手机尺寸下的性能用
var _fps_t := 0.0
var _fps_min := 999.0


func _process(dt: float) -> void:
	if dev.has("fps"):
		var real_dt := dt / maxf(Engine.time_scale, 0.001)
		_fps_t += real_dt
		_fps_min = minf(_fps_min, 1.0 / maxf(real_dt, 0.0001))
		if _fps_t >= 5.0:
			print("帧率：平均 %d，最低 %d，窗口 %s" % [Engine.get_frames_per_second(), int(_fps_min), get_window().size])
			_fps_t = 0.0
			_fps_min = 999.0
	if _clock_on:
		_run_clock += dt
	var real := dt / maxf(Engine.time_scale, 0.001)
	for k in _shot_pending.keys():
		_shot_pending[k] -= real
		if _shot_pending[k] <= 0.0:
			_shot_pending.erase(k)
			_save_shot("user://shot_%s.png" % k)
	if _shot_times.is_empty():
		return
	_shot_clock += real
	if _shot_clock >= float(_shot_times[0]):
		var t: float = _shot_times.pop_front()
		_save_shot("user://shot_%02d.png" % int(t))


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
		var kv: PackedStringArray = a.split("=", true, 1)
		out[kv[0]] = kv[1] if kv.size() > 1 else true
		if a.begins_with("shots="):
			for s in a.trim_prefix("shots=").split(","):
				if s.is_valid_float():
					_shot_times.append(float(s))
				else:
					_shot_names.append(s)
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
	start.pressed.connect(_origin_select)
	p.add_child(start)
	var wipe := MenuButtonUi.make("清空存档")
	wipe.position = Vector2(58, 254)
	wipe.disabled = not profile.exists
	wipe.pressed.connect(_confirm_wipe.bind(wipe))
	p.add_child(wipe)
	if profile.exists:
		var inv := SimInventory.from_dict(profile.inventory)
		_label(p, "存档：金钱 %d · 物品 %d 件 · 已装备 %d 件" % [inv.coins, inv.entries.size(), inv.equipped_items().size()], Vector2(0, 306), 12, UiKit.MUTED, 336)
		if profile.origin in Story.ORIGINS:
			_label(p, "上次出身：%s" % Story.origin_name(profile.origin), Vector2(0, 280), 12, UiKit.MUTED, 336)
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


# ---------- 选出身（规格书第九节：四选一，定稿不再加；和门派分开选） ----------

func _origin_select() -> void:
	_reset()
	_backdrop()
	_label(_layer, "选择出身", Vector2(0, 40), 24, UiKit.QI, 960)
	_label(_layer, "出身决定你是谁、为什么要进慈云寺；不影响任何战斗数值。门派下一步再选。", Vector2(0, 76), 12, UiKit.TEXT, 960)
	var confirm := MenuButtonUi.make("确认出身")
	confirm.position = Vector2(370, 476)
	var name_box := LineEdit.new()
	name_box.position = Vector2(370, 434)
	name_box.size = Vector2(220, 30)
	name_box.max_length = 6
	name_box.placeholder_text = "小旦的名字"
	name_box.hide()
	_layer.add_child(name_box)
	var pick := func(o: String):
		origin = o
		var od := Story.origin(o)
		name_box.visible = od.get("renamable", false)
		if name_box.visible and name_box.text == "":
			name_box.text = profile.player_name if profile.player_name != "" else od.default_name
		confirm.text = "确认 · " + od.name
		confirm.grab_focus()
	var first: Button
	for i in Story.ORIGINS.size():
		var o: String = Story.ORIGINS[i]
		var od := Story.origin(o)
		var c := _card(Rect2(40 + i * 224, 108, 208, 316), od.name, UiKit.QI, null, Vector2.ZERO, od.card, pick.bind(o))
		_label(c, "%s线" % od.weight, Vector2(0, 52), 12, UiKit.MUTED, 208)
		var desc: Label = c.get_child(c.get_child_count() - 2)
		desc.position.y = 96
		desc.size.y = 200
		if o == (profile.origin if profile.origin in Story.ORIGINS else "langzhong"):
			first = c
	confirm.pressed.connect(func():
		Story.player_name = name_box.text.strip_edges() if name_box.visible and name_box.text.strip_edges() != "" else Story.origin(origin).get("default_name", "")
		profile.origin = origin
		profile.player_name = Story.player_name
		profile.save()
		_sect_select())
	_layer.add_child(confirm)
	first.pressed.emit()
	first.grab_focus()


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
	confirm.pressed.connect(_prologue)
	_layer.add_child(confirm)
	confirm.text = "确认 · 少林"
	a.grab_focus()


# ---------- 出身开场（节点 0）----------

## 从开场开始计的游戏时间（代玩计时：规格书第九节「任选一种出身，五分钟内能走到山门」）
var _run_clock := 0.0
var _clock_on := false
var _intro_stats := {}


## 所有关卡都这样建：门派、通用技、出身、存档、代玩
func _level(level: LevelBase, on_done: Callable) -> void:
	for c in get_children():
		c.queue_free()
	level.setup(sect, utility)
	level.origin = origin
	level.profile = profile
	level.autoplay = dev.has("auto")
	level.done.connect(on_done)
	level.quit_to_title.connect(_title)
	add_child(level)


func _prologue() -> void:
	_run_clock = 0.0
	_clock_on = true
	var level := Prologue.new()
	_level(level, _after_prologue)
	if dev.has("skipintro"):
		get_tree().create_timer(0.5).timeout.connect(level.skip_intro)


func _after_prologue(stats: Dictionary) -> void:
	_intro_stats = stats
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
	if _clock_on:
		_clock_on = false
		print("代玩计时：出身 %s%s，从开场到山门 %.0f 秒（游戏时间）" % [Story.origin_name(origin),
			"（跳过开场）" if _intro_stats.get("skipped", false) else "", _run_clock])
		if dev.get("until", "") == "shanmen":
			get_tree().quit(0)
			return
	_level(Shanmen.new(), _after_shanmen)


## 山门打完接后殿藏经阁（Boss 二），再接大雄宝殿（Boss 三）；每段的结算存下来，最后一起显示
var _run_stats := {}
var _parts: Array = []      # [[段名, 这一段的结算], ...]


func _after_shanmen(stats: Dictionary) -> void:
	_run_stats = stats
	_parts = [["山门", stats]]
	_cangjingge()


func _cangjingge() -> void:
	_level(Cangjingge.new(), _after_cangjingge)


func _after_cangjingge(stats: Dictionary) -> void:
	_parts.append(["藏经阁", stats])
	var s := _run_stats.duplicate()
	s["secs"] = float(s.get("secs", 0.0)) + float(stats.secs)
	s["combos"] = int(s.get("combos", 0)) + int(stats.combos)
	s["formations"] = stats.formations
	s["breaks"] = stats.breaks
	s["defeats"] = int(s.get("defeats", 0)) + int(stats.defeats)
	s["moqi"] = stats.moqi
	s["loot"] = "%s、%s" % [s.get("loot", "—"), stats.loot]
	s["boss2"] = true
	_run_stats = s
	_daxiong()


func _daxiong() -> void:
	_level(Daxiongbaodian.new(), _after_daxiong)


func _after_daxiong(stats: Dictionary) -> void:
	_parts.append(["大雄宝殿", stats])
	var s := _run_stats.duplicate()
	s["secs"] = float(s.get("secs", 0.0)) + float(stats.secs)
	s["combos"] = int(s.get("combos", 0)) + int(stats.combos)
	s["formations"] = int(s.get("formations", 0)) + int(stats.formations)
	s["deflects"] = stats.deflects
	s["defeats"] = int(s.get("defeats", 0)) + int(stats.defeats)
	s["moqi"] = stats.moqi
	s["loot"] = "%s、%s" % [s.get("loot", "—"), stats.loot] if s.has("loot") else stats.loot
	s["boss3"] = true
	_end(s)


## 结算（规格书第九节）：三段各一行（用时、合击 / 阵法 / 破罩 / 撞偏），下面是总计与全部所获，看完回开始界面
func _end(stats: Dictionary) -> void:
	stats["origin"] = origin
	if dev.has("auto"):
		print("自动试玩结算：", stats)
		if dev.has("quit"):
			get_tree().quit(0)
			return
	_reset()
	_backdrop(0.5)
	var p := _panel(Rect2(150, 40, 660, 460))
	_label(p, "慈云寺 · 一夜", Vector2(0, 22), 24, UiKit.QI, 660)
	_label(p, "出身：%s　　门派：%s　　通用技：%s" % [Story.origin_name(origin), SimData.SECTS[sect].name, SimData.SKILLS[utility].name], Vector2(0, 58), 12, UiKit.TEXT, 660)
	var y := 92
	for part in _parts:
		var s: Dictionary = part[1]
		var detail := "合击 %d" % int(s.get("combos", 0))
		if s.has("formations"):
			detail += " · 阵法 %d" % int(s.formations)
		if part[0] == "山门":
			detail += " · 打断 %d · 闪过 %d" % [int(s.get("interrupts", 0)), int(s.get("evades", 0))]
		elif part[0] == "藏经阁":
			detail += " · 破罩 %d" % int(s.get("breaks", 0))
		else:
			detail += " · 撞偏 %d · 弩箭 %d · 弩车散架 %d" % [int(s.get("deflects", 0)), int(s.get("bolts", 0)), int(s.get("breaks", 0))]
		_label(p, "%s　%d 分 %02d 秒　%s" % [part[0], int(s.get("secs", 0.0)) / 60, int(s.get("secs", 0.0)) % 60, detail], Vector2(0, y), 12, UiKit.TEXT, 660)
		_label(p, "所获：%s" % s.get("loot", "—"), Vector2(0, y + 20), 12, UiKit.MUTED, 660)
		y += 52
	if _parts.is_empty():
		_label(p, "（开发开关直接进的这一段）", Vector2(0, y), 12, UiKit.MUTED, 660)
		y += 28
	_label(p, "总用时 %d 分 %02d 秒　　败退 %d 次　　最终默契 %d" % [int(stats.secs) / 60, int(stats.secs) % 60, int(stats.get("defeats", 0)), int(stats.get("moqi", 0))],
		Vector2(0, y + 8), 12, UiKit.QI, 660)
	_label(p, "师父只剩一年。——待续", Vector2(0, y + 40), 12, UiKit.MUTED, 660)
	var again := MenuButtonUi.make("回到开始界面")
	again.position = Vector2(220, 392)
	again.pressed.connect(_title)
	p.add_child(again)
	again.grab_focus()
