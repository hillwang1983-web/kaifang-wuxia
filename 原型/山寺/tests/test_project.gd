## 工程设置：分辨率、像素风渲染与输入映射没被编辑器改坏。
extends "res://tests/test_case.gd"

const ACTIONS := ["move_up", "move_down", "move_left", "move_right", "aim_up", "aim_down", "aim_left", "aim_right",
	"attack", "skill_1", "skill_2", "skill_3", "utility", "combo", "dodge", "cancel", "interact", "inventory", "pause"]


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


## #28：手机上火把（含火光与提示）不压在任何 HUD 下面，火把 / 喽啰 / 出生点都在手机可走区里
func test_mobile_layout_keeps_targets_clear() -> void:
	var hud_rects := [Rect2(16, 16, 224, 108), Rect2(16, 128, 196, 88), Rect2(752, 112, 184, 80), Rect2(62, 336, 128, 128)]
	for b in Hud.MOBILE + [Hud.MOBILE_INTERACT]:
		var r: float = b[2] * 0.5 + 6.0
		hud_rects.append(Rect2(b[0] - r, b[1] - r, r * 2.0, r * 2.0 + 18.0))  # 命中圈 + 下方名字
	var walk := Shanmen.mobile_bounds()
	for p: Vector2 in Shanmen.TORCHES:
		var look := Rect2(p.x - 26, p.y - 68, 76, 68)
		for h: Rect2 in hud_rects:
			check(not look.intersects(h), "火把 %s 被手机 HUD %s 挡住" % [p, h])
	for p: Vector2 in Shanmen.TORCHES + Shanmen.LOULUO + [Shanmen.START]:
		check(Geometry2D.is_point_in_polygon(p, walk), "%s 不在手机可走区里" % p)
		for z: Rect2 in Hud.MOBILE_ZONES:
			check(not z.has_point(p), "%s 落在手机操作区 %s" % [p, z])


func test_main_scene_loads() -> void:
	var path: String = ProjectSettings.get_setting("application/run/main_scene", "")
	check(path != "", "没有设置主场景")
	if path != "":
		check(load(path) is PackedScene, "主场景无法加载：" + path)
