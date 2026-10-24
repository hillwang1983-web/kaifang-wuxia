## 台词：全部在 res://data/story.json（草稿，规格书第九节要求最终稿由 Mark 写，直接替换那个文件即可）。
## 这里只负责按键名取出来，换成对话框要的 {who, text}。出身的开场、进寺、Boss 一收尾是三处分叉，其余四条线共用。
class_name Story
extends RefCounted

const DATA_PATH := "res://data/story.json"
const ORIGINS := ["shenjia", "tiejiang", "xiban", "langzhong"]

static var _data := {}
static var player_name := ""   # 戏班小旦可改名（默认「玉儿」）；台词里的 {name} 换成它


static func data() -> Dictionary:
	if _data.is_empty():
		_data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return _data


static func _lines(rows: Array) -> Array:
	return rows.map(func(r): return {"who": r[0], "text": String(r[1]).replace("{name}", player_name)})


static func shared(key: String) -> Array:
	return _lines(data().shared[key])


static func origin(id: String) -> Dictionary:
	return data().origins[id]


static func origin_name(id: String) -> String:
	return origin(id).name if id != "" else "（未选）"


# ---------- 开场（每条出身） ----------

static func modern() -> Array:
	return _lines(data().modern)


static func wake(id: String) -> Array:
	return _lines(origin(id).wake)


## 教学三项的引导：move / attack / dodge，由在场 NPC 说（字幕，不挡操作）
static func tutorial(id: String, step: String) -> Dictionary:
	return _lines([origin(id).tutorial[step]])[0]


static func info(id: String) -> Array:
	return _lines(origin(id).info)


static func leave(id: String) -> Dictionary:
	return _lines([origin(id).leave])[0]


## 第二处分叉：山门前一小段对话；邪派加一句进寺理由（规格书第九节）
static func entry(id: String, sect: String) -> Array:
	var out := _lines(origin(id).entry) if id != "" else []
	if sect == "xiepai":
		out.append(_lines([data().shared.xiepai_line])[0])
	return out


## 第三处分叉：玄诚倒地后按出身的收尾（赎罪 / 报仇 / 查纸条 / 治病）
static func coda(id: String) -> Array:
	return _lines(origin(id).coda) if id != "" else []


# ---------- 副本内共用 ----------

static func shanmen_intro(sect: String, origin_id := "") -> Array:
	return shared("shanmen_intro") + entry(origin_id, sect)


static func boss_intro() -> Array:
	return shared("boss_intro")


static func phase2() -> Array:
	return shared("phase2")


static func boss_down(origin_id := "") -> Array:
	return shared("boss_down") + coda(origin_id)


static func houdian_intro() -> Array:
	return shared("houdian_intro")


static func dulao_intro() -> Array:
	return shared("dulao_intro")


static func dulao_down() -> Array:
	return shared("dulao_down")


static func daxiong_intro() -> Array:
	return shared("daxiong_intro")


static func jingang_intro() -> Array:
	return shared("jingang_intro")


static func jingang_down() -> Array:
	return shared("jingang_down")


static func daxiong_last() -> String:
	return data().shared.daxiong_last[1]
