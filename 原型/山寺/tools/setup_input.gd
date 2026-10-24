## 生成 project.godot 里的输入映射（键鼠 + Xbox / PS 手柄）。
## 改键位就改这里再跑一遍，别只在编辑器里手改：
##   Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tools/setup_input.gd
## 键位依据规格书第五节；规格书的 Q W E 与 WASD 里的 W 冲突，三主动改为 U I O。
extends SceneTree

const DEADZONE := 0.2

# 每项是 [类型, 值...]：key = 键盘物理键，mouse = 鼠标键，pad = 手柄按钮，axis = 手柄摇杆 / 扳机及方向。
var ACTIONS := {
	"move_up": [["key", KEY_W], ["key", KEY_UP], ["axis", JOY_AXIS_LEFT_Y, -1.0]],
	"move_down": [["key", KEY_S], ["key", KEY_DOWN], ["axis", JOY_AXIS_LEFT_Y, 1.0]],
	"move_left": [["key", KEY_A], ["key", KEY_LEFT], ["axis", JOY_AXIS_LEFT_X, -1.0]],
	"move_right": [["key", KEY_D], ["key", KEY_RIGHT], ["axis", JOY_AXIS_LEFT_X, 1.0]],
	"aim_up": [["axis", JOY_AXIS_RIGHT_Y, -1.0]],
	"aim_down": [["axis", JOY_AXIS_RIGHT_Y, 1.0]],
	"aim_left": [["axis", JOY_AXIS_RIGHT_X, -1.0]],
	"aim_right": [["axis", JOY_AXIS_RIGHT_X, 1.0]],
	"attack": [["key", KEY_J], ["mouse", MOUSE_BUTTON_LEFT], ["pad", JOY_BUTTON_A]],
	"skill_1": [["key", KEY_U], ["pad", JOY_BUTTON_X]],
	"skill_2": [["key", KEY_I], ["pad", JOY_BUTTON_Y]],
	"skill_3": [["key", KEY_O], ["pad", JOY_BUTTON_B]],
	"utility": [["key", KEY_K], ["pad", JOY_BUTTON_RIGHT_SHOULDER]],
	"combo": [["key", KEY_F], ["axis", JOY_AXIS_TRIGGER_RIGHT, 1.0]],
	"dodge": [["key", KEY_SPACE], ["pad", JOY_BUTTON_LEFT_SHOULDER]],
	# 规格书把手柄取消放在 B，但 B 已是主动三；暂放 LT。
	"cancel": [["key", KEY_ESCAPE], ["mouse", MOUSE_BUTTON_RIGHT], ["axis", JOY_AXIS_TRIGGER_LEFT, 1.0]],
	# 规格书没给手柄交谈 / 互动键，暂放十字键上。
	"interact": [["key", KEY_E], ["pad", JOY_BUTTON_DPAD_UP]],
	"inventory": [["key", KEY_TAB], ["pad", JOY_BUTTON_START]],
	"pause": [["key", KEY_P], ["pad", JOY_BUTTON_BACK]],
}


func _init() -> void:
	for action in ACTIONS:
		var events: Array[InputEvent] = []
		for spec in ACTIONS[action]:
			var ev := _event(spec)
			ev.device = -1  # 与编辑器的「所有设备」一致；不写死只认 0 号手柄
			events.append(ev)
		ProjectSettings.set_setting("input/" + action, {"deadzone": DEADZONE, "events": events})
	var err := ProjectSettings.save()
	print("输入映射写入 project.godot：%d 个动作，%s" % [ACTIONS.size(), error_string(err)])
	quit(0 if err == OK else 1)


func _event(spec: Array) -> InputEvent:
	match spec[0]:
		"key":
			var key := InputEventKey.new()
			key.physical_keycode = spec[1]
			return key
		"mouse":
			var mouse := InputEventMouseButton.new()
			mouse.button_index = spec[1]
			return mouse
		"pad":
			var button := InputEventJoypadButton.new()
			button.button_index = spec[1]
			return button
	var axis := InputEventJoypadMotion.new()
	axis.axis = spec[1]
	axis.axis_value = spec[2]
	return axis
