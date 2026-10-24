## 特效帧动画：按 data/vfx.json 的登记读美术交的特效横条（assets/vfx/vfx_名称_v版本.png），
## 以画布中心对准特效中心，可旋转（朝右画、程序转向）、可按半径缩放或按两点距离拉伸、可循环。
## 画面层的每个代码特效都先问这里：交了图就画图，没交就返回 false，继续画代码占位。以后特效到了只放文件。
class_name VfxLib
extends RefCounted

const DATA_PATH := "res://data/vfx.json"
const MAX_VERSION := 5

static var _data := {}
static var _cache := {}   # 名称 -> Texture2D 或 null（测试可以往里塞假图）


static func data() -> Dictionary:
	if _data.is_empty():
		_data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return _data


static func tex(vfx: String) -> Texture2D:
	if _cache.has(vfx):
		return _cache[vfx]
	var t: Texture2D = null
	var e: Dictionary = data().effects.get(vfx, {})
	var file: String = e.get("file", "vfx/vfx_" + vfx)   # 物件类单次动画放在 obj/ 下
	for v in range(MAX_VERSION, 0, -1):
		var path := "res://assets/%s_v%02d.png" % [file, v]
		if ResourceLoader.exists(path):
			t = load(path)
			break
	_cache[vfx] = t
	return t


static func has(vfx: String) -> bool:
	return vfx != "" and data().effects.has(vfx) and tex(vfx) != null


static func frames(vfx: String) -> int:
	var t := tex(vfx)
	return maxi(1, t.get_width() / int(data().effects[vfx].frame[0])) if t else 0


## 单次特效播完一遍要多久（秒）
static func length(vfx: String) -> float:
	return frames(vfx) / float(data().fps)


## 画一帧。t 是特效已经播了多久；angle 弧度；size 是程序这一处的大小（r 缩放时是半径，len 拉伸时是长度）。
## 返回 false 表示没图，调用方照常画代码占位
static func draw(ci: CanvasItem, vfx: String, at: Vector2, t: float, angle := 0.0, size := 0.0, alpha := 1.0) -> bool:
	if not has(vfx):
		return false
	var e: Dictionary = data().effects[vfx]
	var fw: float = e.frame[0]
	var fh: float = e.frame[1]
	var n := frames(vfx)
	var i := int(t * float(data().fps))
	i = i % n if e.loop else mini(i, n - 1)
	var sc := Vector2.ONE
	match e.scale:
		"r":
			if size > 0.0:
				sc = Vector2.ONE * (size * 2.0 / fw)
		"len":
			if size > 0.0:
				sc = Vector2(size / fw, 1.0)
	ci.draw_set_transform(at, angle if e.rotate else 0.0, sc)
	# 拉伸类（光束）从起点往前画，其余以中心对准
	var origin := Vector2(0, -fh / 2.0) if e.scale == "len" else Vector2(-fw / 2.0, -fh / 2.0)
	ci.draw_texture_rect_region(tex(vfx), Rect2(origin, Vector2(fw, fh)), Rect2(i * fw, 0, fw, fh), Color(1, 1, 1, alpha))
	ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	return true
