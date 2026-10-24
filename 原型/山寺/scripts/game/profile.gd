## 本地存档（user://，网页上存在浏览器 IndexedDB）：物品栏、装备、金钱、武功熟练度。
## 刷新后还在；开新局时物品与熟练度保留（暗黑式，带着装备再打一遍）。
## runs 留给以后多局 / 多存档位；version 用于以后改格式时迁移。
class_name Profile
extends RefCounted

const PATH := "user://shansi_save.json"
static var path := PATH   # 代玩冒烟用单独的存档文件，不碰真存档
const VERSION := 1
const STUDY_EVERY := 5.0   # 参悟中的武功每 5 秒熟练度 +1（规格书第三节：只存储和显示，不影响战斗）

var inventory := {}        # SimInventory.to_dict()
var proficiency := {}      # 武功 id -> 熟练度
var studying := ""         # 参悟中的武功，一次只能一门
var study_t := 0.0
var runs: Array = []       # 预留：每局结算记录
var origin := ""           # 出身（规格书第九节，开局四选一）；空 = 还没选过
var player_name := ""      # 戏班小旦可改名（默认「玉儿」）
var exists := false


static func load_or_new() -> Profile:
	var p := Profile.new()
	if not FileAccess.file_exists(path):
		return p
	var d = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not d is Dictionary or int(d.get("version", 0)) != VERSION:
		return p
	p.exists = true
	p.inventory = d.get("inventory", {})
	for k in d.get("proficiency", {}):
		p.proficiency[k] = int(d.proficiency[k])
	p.studying = str(d.get("studying", ""))
	p.study_t = float(d.get("study_t", 0.0))
	p.runs = d.get("runs", [])
	p.origin = str(d.get("origin", ""))
	p.player_name = str(d.get("player_name", ""))
	return p


func save() -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		push_warning("存档写不进去：%s" % error_string(FileAccess.get_open_error()))
		return
	f.store_string(JSON.stringify({"version": VERSION, "inventory": inventory, "proficiency": proficiency,
		"studying": studying, "study_t": study_t, "runs": runs, "origin": origin, "player_name": player_name}, "\t"))
	exists = true


static func wipe() -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))


## 参悟：换一门就从那门的当前值接着涨；传空字符串停止
func study(skill: String) -> void:
	studying = skill
	study_t = 0.0


## 返回是否涨了一点（涨了就该存档）
func tick_study(dt: float) -> bool:
	if studying == "":
		return false
	study_t += dt
	var gained := false
	while study_t >= STUDY_EVERY - 0.0001:  # 帧时间累加有误差，留一点余量
		study_t -= STUDY_EVERY
		proficiency[studying] = int(proficiency.get(studying, 0)) + 1
		gained = true
	return gained
