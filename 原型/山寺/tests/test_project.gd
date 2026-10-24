## 工程设置：分辨率、像素风渲染与输入映射没被编辑器改坏。
extends "res://tests/test_case.gd"

const ACTIONS := ["move_up", "move_down", "move_left", "move_right", "aim_up", "aim_down", "aim_left", "aim_right",
	"attack", "skill_1", "skill_2", "skill_3", "utility", "combo", "dodge", "cancel", "interact", "inventory", "pause", "potion"]


func test_display() -> void:
	check_eq(ProjectSettings.get_setting("display/window/size/viewport_width"), 960, "内部宽度")
	check_eq(ProjectSettings.get_setting("display/window/size/viewport_height"), 540, "内部高度")
	check_eq(ProjectSettings.get_setting("display/window/stretch/scale_mode"), "integer", "整数倍拉伸")
	check_eq(ProjectSettings.get_setting("rendering/textures/canvas_textures/default_texture_filter"), 0, "最近邻过滤")


func test_input_actions() -> void:
	for action in ACTIONS:
		check(InputMap.has_action(action), "缺少输入动作 " + action)
		if InputMap.has_action(action):
			check(not InputMap.action_get_events(action).is_empty(), action + " 没有绑定任何按键")


func test_every_action_has_gamepad() -> void:
	for action in ACTIONS:
		if not InputMap.has_action(action):
			continue
		var pad := InputMap.action_get_events(action).any(func(e): return e is InputEventJoypadButton or e is InputEventJoypadMotion)
		check(pad, action + " 没有手柄绑定")


func test_main_scene_loads() -> void:
	var path: String = ProjectSettings.get_setting("application/run/main_scene", "")
	check(path != "", "没有设置主场景")
	if path != "":
		check(load(path) is PackedScene, "主场景无法加载：" + path)


## #28 套到可卷动的地图：站到每个关键物 / 出生点 / 敌人位置上时（镜头在地图边缘会被夹住），
## 这个点在屏幕上都不落进手机触屏操作区；单屏的茶棚在手机上直接把操作区从可走区里挖掉
func test_mobile_layout_keeps_targets_clear() -> void:
	var levels := {
		"山门": [Shanmen.TORCHES + Shanmen.LOULUO + [Shanmen.START, Shanmen.ARENA_START, Shanmen.BOSS_WAIT]
			+ Shanmen.ENTRY.values().map(func(e): return e.at) + Shanmen.ENTRY.values().filter(func(e): return not e.npc.is_empty()).map(func(e): return e.npc[1])],
		"藏经阁": [Cangjingge.LOULUO + Cangjingge.PROPS.map(func(x): return x[1]) + [Cangjingge.START, Cangjingge.HALL_START, Cangjingge.DULAO_AT]],
		"大雄宝殿": [Daxiongbaodian.PILES.map(func(x): return x[1]) + Daxiongbaodian.SPOTS + [Daxiongbaodian.START, Daxiongbaodian.HALL_START,
			Daxiongbaodian.BALLISTA_AT, Daxiongbaodian.CHEST_AT, Daxiongbaodian.JINGANG_AT]],
	}
	for name in levels:
		for p: Vector2 in levels[name][0]:
			var s := LevelBase.screen_pos(p, p, Vector2(1920, 1080))
			check(not LevelBase.in_mobile_zone(s), "%s：%s 站上去时在屏幕 %s，落进手机操作区" % [name, p, s])
	# 出身开场都是单屏（镜头不动）：关键点直接用屏幕坐标查，手机上可走区挖掉操作区后它们还得走得到
	for o in Prologue.LAYOUTS:
		var lay: Dictionary = Prologue.LAYOUTS[o]
		var walk := LevelBase.mobile_bounds(Prologue.floor_of(o))
		for z: Rect2 in Hud.MOBILE_ZONES:
			check(not Geometry2D.is_point_in_polygon(z.get_center(), walk), "%s 开场手机可走区挖掉了操作区 %s" % [o, z])
		for p: Vector2 in [lay.start, lay.move, lay.prop[1], lay.trainer, lay.info, lay.exit]:
			check(not LevelBase.in_mobile_zone(p), "%s 开场：%s 落在手机操作区" % [o, p])
			check(Geometry2D.is_point_in_polygon(p, walk) or p == lay.exit, "%s 开场：%s 不在手机可走区里" % [o, p])

