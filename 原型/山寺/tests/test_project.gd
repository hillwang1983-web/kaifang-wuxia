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


func test_main_scene_loads() -> void:
	var path: String = ProjectSettings.get_setting("application/run/main_scene", "")
	check(path != "", "没有设置主场景")
	if path != "":
		check(load(path) is PackedScene, "主场景无法加载：" + path)
