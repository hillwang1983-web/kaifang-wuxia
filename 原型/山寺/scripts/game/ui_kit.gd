## 界面共用：配色（美术说明第三节、布局参数）、字体、贴图与「墨底金边」面板。
class_name UiKit
extends RefCounted

const FONT := preload("res://assets/fonts/fusion-pixel/fusion-pixel-12px-proportional-zh_hans.otf.woff2")

const PANEL := Color("#15121A", 0.87)
const BORDER := Color("#FFD24A")
const TEXT := Color("#FFF3C4")
const MUTED := Color("#C8C0A8")
const HEALTH := Color("#D9534F")
const QI := Color("#FFD24A")
const DEX := Color("#C8C8C8")
const CAST := Color("#FFC83D")
const WARN := Color("#FF3B3B")
const MONK := Color("#8C3B2E")
const SASH := Color("#D8A64A")
const CULT := Color("#15121A")
const POISON := Color("#7BE38A")
const PURPLE := Color("#9B4DFF")
const DARK_PURPLE := Color("#4A2A6B")
const GOLD_WHITE := Color("#FFF3C4")

const KEY_HINTS := {"attack": "J", "skill_1": "U", "skill_2": "I", "skill_3": "O", "utility": "K",
	"combo": "F", "dodge": "空格", "interact": "E", "cancel": "Esc", "inventory": "Tab", "potion": "H"}

## 手柄按键提示（规格书第五节：Xbox 与 PS 即插即用，图标按手柄类型切换）。绑定见 tools/setup_input.gd
const PAD_XBOX := {"attack": "A", "skill_1": "X", "skill_2": "Y", "skill_3": "B", "utility": "RB",
	"combo": "RT", "dodge": "LB", "interact": "十字↑", "cancel": "LT", "inventory": "Start", "potion": "十字↓"}
const PAD_PS := {"attack": "×", "skill_1": "□", "skill_2": "△", "skill_3": "○", "utility": "R1",
	"combo": "R2", "dodge": "L1", "interact": "十字↑", "cancel": "L2", "inventory": "OPTIONS", "potion": "十字↓"}
static var device := "kb"   # 最近用的输入：kb 键鼠 / xbox / ps

static var _tex := {}


## 某个动作当前该显示的按键（跟着最近用的设备变）
static func key(action: String) -> String:
	match device:
		"xbox":
			return PAD_XBOX.get(action, KEY_HINTS.get(action, ""))
		"ps":
			return PAD_PS.get(action, KEY_HINTS.get(action, ""))
	return KEY_HINTS.get(action, "")


## 看一眼输入事件，记下最近用的设备；手柄名里带 PlayStation / DualSense / DualShock 就当 PS，其余当 Xbox
static func detect(event: InputEvent) -> void:
	if event is InputEventJoypadButton or (event is InputEventJoypadMotion and absf(event.axis_value) > 0.5):
		device = pad_kind(Input.get_joy_name(event.device))
	elif event is InputEventKey or event is InputEventMouseButton:
		device = "kb"


static func pad_kind(joy_name: String) -> String:
	var n := joy_name.to_lower()
	for w in ["playstation", "dualsense", "dualshock", "ps4", "ps5", "sony", "wireless controller"]:
		if n.contains(w):
			return "ps"
	return "xbox"


static func tex(path: String) -> Texture2D:
	if not _tex.has(path):
		_tex[path] = load(path)
	return _tex[path]


## 美术替换的通用取图：assets/<dir>/<name>_v0N.png 取最高版本，没交返回 null（调用方回落到代码画的占位）
static var _art := {}


static func art(dir: String, name: String) -> Texture2D:
	var key := dir + "/" + name
	if not _art.has(key):
		var t: Texture2D = null
		for v in range(5, 0, -1):
			var path := "res://assets/%s/%s_v%02d.png" % [dir, name, v]
			if ResourceLoader.exists(path):
				t = load(path)
				break
		_art[key] = t
	return _art[key]


## 横条里的第 i 帧（帧宽 fw），画在 rect 里；没图返回假
static func draw_strip(ci: CanvasItem, tex2: Texture2D, fw: float, i: int, rect: Rect2, modulate := Color.WHITE) -> bool:
	if tex2 == null:
		return false
	var n := maxi(1, int(tex2.get_width() / fw))
	ci.draw_texture_rect_region(tex2, rect, Rect2((i % n) * fw, 0, fw, tex2.get_height()), modulate)
	return true


## 手柄按键图标的文件名（交换清单第 78 条）：ui_pad_xbox_a、ui_pad_ps_cross……
const PAD_ICON := {
	"xbox": {"attack": "a", "skill_1": "x", "skill_2": "y", "skill_3": "b", "utility": "rb", "combo": "rt",
		"dodge": "lb", "cancel": "lt", "inventory": "start", "interact": "dup", "potion": "ddown"},
	"ps": {"attack": "cross", "skill_1": "square", "skill_2": "triangle", "skill_3": "circle", "utility": "r1", "combo": "r2",
		"dodge": "l1", "cancel": "l2", "inventory": "options", "interact": "dup", "potion": "ddown"},
}


## 当前设备是手柄时这个动作的按键图标；键鼠或没交图返回 null
static func pad_icon(action: String) -> Texture2D:
	if not PAD_ICON.has(device) or not PAD_ICON[device].has(action):
		return null
	return art("ui", "ui_pad_%s_%s" % [device, PAD_ICON[device][action]])


static func ui(name: String) -> Texture2D:
	return tex("res://assets/ui/ui_%s_v01.png" % name)


static func icon(name: String) -> Texture2D:
	return tex("res://assets/ico/ico_%s_v01.png" % name)


static func portrait(name: String) -> Texture2D:
	return tex("res://assets/por/por_%s_v01.png" % name)


## 墨底金边面板（没有专门框图的地方用）
static func panel(c: CanvasItem, r: Rect2) -> void:
	c.draw_rect(r, PANEL)
	c.draw_rect(r.grow(-0.5), BORDER, false, 1.0)


static func text(c: CanvasItem, at: Vector2, s: String, size := 12, color := TEXT, align := HORIZONTAL_ALIGNMENT_LEFT, width := -1.0) -> void:
	c.draw_string(FONT, at + Vector2(0, size), s, align, width, size, color)


## 右对齐：at 是文字右端
static func text_r(c: CanvasItem, at: Vector2, s: String, size := 12, color := TEXT) -> void:
	text(c, at - Vector2(text_width(s, size), 0), s, size, color)


static func text_width(s: String, size := 12) -> float:
	return FONT.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x


## 按比例填一条槽：trough 是槽外框（含 1px 边），填色画在框内
static func fill(c: CanvasItem, trough: Rect2, ratio: float, color: Color) -> void:
	var inner := trough.grow(-1)
	inner.size.x = floorf(inner.size.x * clampf(ratio, 0.0, 1.0))
	if inner.size.x > 0:
		c.draw_rect(inner, color)


## 顺时针扇形遮罩（技能冷却）。画成半径 r/2、线宽 r 的粗圆弧，不走多边形三角化——
## 扇形快转满一圈时首尾两点几乎重合，draw_colored_polygon 会三角化失败并刷屏报错
static func cooldown_pie(c: CanvasItem, center: Vector2, r: float, ratio: float) -> void:
	if ratio <= 0.0:
		return
	var start := -PI / 2.0
	c.draw_arc(center, r * 0.5, start, start + TAU * minf(ratio, 1.0), maxi(4, ceili(48.0 * ratio)), Color(0, 0, 0, 0.62), r)
