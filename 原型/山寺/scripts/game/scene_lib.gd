## 场景图层与可走区：按 data/scenes.json 取底图和前景遮挡层（交了图用图，没交用 PlaceholderArt 的代码占位），
## 可走区与碰撞多边形默认用关卡代码里的常量，data/walk/<场景>.json 存在时用它覆盖。
## 场景图到了以后只要放文件、再用 tools/trace_walkable.py 从可走区遮罩生成 walk JSON，关卡代码不用改。
class_name SceneLib
extends RefCounted

const DATA_PATH := "res://data/scenes.json"
const MAX_VERSION := 5

static var _data := {}
static var _walk := {}


static func data() -> Dictionary:
	if _data.is_empty():
		_data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return _data


static func _env(prefix: String) -> Texture2D:
	if prefix == "":
		return null
	for v in range(MAX_VERSION, 0, -1):
		var path := "res://assets/env/%s_v%02d.png" % [prefix, v]
		if ResourceLoader.exists(path):
			return UiKit.tex(path)
	return null


## 美术交了底图没有
static func has_art(scene: String) -> bool:
	return _env(data().scenes[scene].bg) != null


static func background(scene: String) -> Texture2D:
	var s: Dictionary = data().scenes[scene]
	var t := _env(s.bg)
	if t:
		return t
	return _placeholder(s.get("placeholder", ""))


## 还没交图的场景用的代码占位底图
static func _placeholder(name: String) -> Texture2D:
	match name:
		"cangjingge":
			return PlaceholderArt.cangjingge()
		"daxiongbaodian":
			return PlaceholderArt.daxiongbaodian()
		"workshop":
			return PlaceholderArt.workshop()
		"shenjia_room":
			return PlaceholderArt.shenjia_room()
		"forge":
			return PlaceholderArt.forge()
		"backstage":
			return PlaceholderArt.backstage()
	return null


## 前景遮挡层；只有底图也是美术交的才用（占位底图配真前景会对不上）
static func foreground(scene: String) -> Texture2D:
	return _env(data().scenes[scene].front) if has_art(scene) else null


static func _walk_data(scene: String) -> Dictionary:
	if not _walk.has(scene):
		var path := "res://data/walk/%s.json" % scene
		_walk[scene] = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else {}
	return _walk[scene]


static func _vec(points: Array) -> Array:
	return points.map(func(p): return Vector2(p[0], p[1]))


## 一个多边形（如 floor、hall）：walk JSON 有这个键就用它，没有用关卡代码里的默认值
static func poly(scene: String, key: String, fallback: Array) -> Array:
	var d := _walk_data(scene)
	return _vec(d[key]) if d.has(key) else fallback


## 一组多边形（如 blocks 碰撞）
static func polys(scene: String, key: String, fallback: Array) -> Array:
	var d := _walk_data(scene)
	return d[key].map(func(p): return _vec(p)) if d.has(key) else fallback
