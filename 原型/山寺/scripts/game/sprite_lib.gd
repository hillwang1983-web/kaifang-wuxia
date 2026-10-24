## 角色帧动画：按 data/anim.json 的登记读美术交的动作条（前缀_动作_方向_v版本.png），
## 由角色状态挑动作、由朝向挑方向（右侧镜像左侧）、按脚底锚点画到脚下。只读世界，不改世界。
## 美术以后交新动作只要放文件；缺的动作按 fallback 找替代，连 idle 都没有就返回 false，由画面画代码占位人形。
class_name SpriteLib
extends RefCounted

const DATA_PATH := "res://data/anim.json"
const MAX_VERSION := 5   # 同名多个版本只用最高的（交付约定：开发只导入最高版本）

static var _data := {}
static var _cache := {}   # "前缀|动作|方向" -> Texture2D 或 null


static func data() -> Dictionary:
	if _data.is_empty():
		_data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return _data


## 这个角色用哪套动作条；没有对应的返回空字符串（开场引导人、可破坏物等一律画占位）
static func prefix_for(f: SimFighter) -> String:
	match f.kind:
		"player":
			return "chr_" + f.sect
		"partner":
			return "npc_jingxin"
		"ally":
			return "npc_hanqing"
		"louluo", "xuancheng", "dulao", "jingang":
			return ("npc_" if f.kind == "louluo" else "boss_") + f.kind
	return ""


static func strip(prefix: String, action: String, dir: String) -> Texture2D:
	var key := "%s|%s|%s" % [prefix, action, dir]
	if _cache.has(key):
		return _cache[key]
	var tex: Texture2D = null
	var set_: Dictionary = data().sets.get(prefix, {})
	if not set_.is_empty():
		for v in range(MAX_VERSION, 0, -1):
			var path := "res://assets/%s/%s_%s_%s_v%02d.png" % [set_.dir, prefix, action, dir, v]
			if ResourceLoader.exists(path):
				tex = load(path)
				break
	_cache[key] = tex
	return tex


## 想要的动作找不到时依次换：登记的 fallback → idle
static func resolve(prefix: String, action: String, dir: String) -> Array:
	var chain: Array = [action] + data().fallback.get(action, []) + ["idle"]
	for a in chain:
		var t := strip(prefix, a, dir)
		if t:
			return [a, t]
	return []


## 由角色状态决定要播的动作
static func action_for(f: SimFighter) -> String:
	if not f.alive:
		return "down"
	match f.state:
		"sit":
			return "sit"
		"dodge", "thrown":
			return "roll"
		"windup", "dash", "cast", "recover":
			if f.atk_id != "":
				return f.atk_id
			if f.state != "recover":
				return "atk"
		"stagger":
			return "stagger"
		"flinch":
			return "hit"
	if f.hurt_t > 0.0:
		return "hit"
	if f.swing_t > 0.0 and f.swing_kind != "":
		return f.swing_kind
	if f.moving:
		return "walk"
	return "idle"


## 四方向：左右看横向分量，上下看纵向分量；右侧由左侧镜像
static func dir_for(facing: Vector2) -> String:
	if absf(facing.x) > absf(facing.y) * 1.1:
		return "right" if facing.x > 0.0 else "left"
	return "up" if facing.y < 0.0 else "down"


## 这一刻该画第几帧。起手 + 出手分开的动作条（sets.windup）：预警 / 读条期间停在起手末帧（windup_loop 里的循环起手帧），
## 出手（收招、冲刺）后从出手第一帧接着播；其余按 actions 的 loop / hold
static func frame_of(f: SimFighter, set_: Dictionary, action: String, count: int, clock: float) -> int:
	var act: Dictionary = data().actions.get(action, {})
	var i := int(clock * float(data().fps))
	var wind := int(set_.get("windup", {}).get(action, 0))
	if wind > 0 and wind < count and not f.is_hero():
		if f.state == "windup" or f.state == "cast":
			return i % wind if action in set_.get("windup_loop", []) else mini(i, wind - 1)
		return mini(wind + i, count - 1)
	if act.get("loop", false):
		return i % count
	return mini(mini(i, int(act.get("hold", count - 1))), count - 1)


## 画一帧。clock 是这个动作已经播了多久（秒）。返回 false 表示没有可用的图，由调用方画占位
static func draw(ci: CanvasItem, f: SimFighter, at: Vector2, clock: float, tint: Color) -> bool:
	var prefix := prefix_for(f)
	if prefix == "":
		return false
	var dir := dir_for(f.facing)
	var mirror := dir == "right"
	var found := resolve(prefix, action_for(f), "left" if mirror else dir)
	if found.is_empty():
		return false
	var set_: Dictionary = data().sets[prefix]
	var tex: Texture2D = found[1]
	var fw: int = set_.frame[0]
	var fh: int = set_.frame[1]
	var count := maxi(1, tex.get_width() / fw)
	var i := frame_of(f, set_, found[0], count, clock)
	var anchor := Vector2(set_.anchor[0], set_.anchor[1])
	var src := Rect2(i * fw, 0, fw, fh)
	if mirror:
		ci.draw_set_transform(at, 0.0, Vector2(-1, 1))
		ci.draw_texture_rect_region(tex, Rect2(-anchor, Vector2(fw, fh)), src, tint)
		ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	else:
		ci.draw_texture_rect_region(tex, Rect2(at - anchor, Vector2(fw, fh)), src, tint)
	return true
