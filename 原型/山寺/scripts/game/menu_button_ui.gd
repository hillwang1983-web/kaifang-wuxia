## 墨底金边按钮：用美术交付的 ui_button_normal / pressed / disabled（220×44，四像素九宫格边距）。
## 用 Godot 自带 Button，鼠标、触屏、键盘方向键与手柄 A 都能操作。
class_name MenuButtonUi
extends RefCounted


static func make(label: String, size := Vector2(220, 44)) -> Button:
	var b := Button.new()
	b.text = label
	b.custom_minimum_size = size
	b.focus_mode = Control.FOCUS_ALL
	for pair in [["normal", "button_normal"], ["hover", "button_pressed"], ["pressed", "button_pressed"],
			["focus", "button_pressed"], ["disabled", "button_disabled"]]:
		var sb := StyleBoxTexture.new()
		sb.texture = UiKit.ui(pair[1])
		sb.texture_margin_left = 4
		sb.texture_margin_right = 4
		sb.texture_margin_top = 4
		sb.texture_margin_bottom = 4
		b.add_theme_stylebox_override(pair[0], sb)
	b.add_theme_font_size_override("font_size", 24)
	b.add_theme_color_override("font_color", UiKit.TEXT)
	b.add_theme_color_override("font_focus_color", Color.WHITE)
	b.add_theme_color_override("font_hover_color", Color.WHITE)
	b.add_theme_color_override("font_disabled_color", UiKit.MUTED * Color(1, 1, 1, 0.6))
	return b
