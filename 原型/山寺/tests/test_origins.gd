## 出身（规格书第九节）：台词数据齐全、字数上限、三处分叉按出身分发、邪派进寺一句、
## 出身不改战斗数值（铁匠锤没有属性、不进掉落）、开场布局可走、存档带出身。
extends "res://tests/test_case.gd"


func _chars(lines: Array) -> int:
	var n := 0
	for l in lines:
		n += String(l.text).length()
	return n


func test_story_data_complete() -> void:
	check(Story.data().get("draft", false), "台词文件标着「草稿」，等 Mark 替换")
	check_eq(Story.ORIGINS.size(), 4, "出身四选一")
	for o in Story.ORIGINS:
		var od := Story.origin(o)
		for k in ["name", "card", "wake", "tutorial", "info_hint", "info", "leave", "entry", "coda"]:
			check(od.has(k), "%s 缺 %s" % [o, k])
		for step in ["move", "attack", "dodge"]:
			check(Story.tutorial(o, step).text != "", "%s 教学三项缺 %s" % [o, step])
		var opening := _chars(Story.wake(o)) + _chars(["move", "attack", "dodge"].map(func(s): return Story.tutorial(o, s))) \
			+ _chars(Story.info(o)) + _chars([Story.leave(o)])
		check(opening <= 500, "%s 开场台词不超过 500 字（%d）" % [o, opening])
		check(_chars(Story.coda(o)) <= 100, "%s Boss 一收尾不超过 100 字（%d）" % [o, _chars(Story.coda(o))])
	var shared := 0
	for k in Story.data().shared:
		var v: Array = Story.data().shared[k]
		shared += String(v[1]).length() if v[0] is String else _chars(Story.shared(k))
	check(shared <= 800, "副本内共用对话不超过 800 字（%d）" % shared)
	check(Story.modern().size() > 0, "现代十秒有旁白")


func test_three_forks_by_origin() -> void:
	var downs := {}
	var common := Story.shared("boss_down")
	for o in Story.ORIGINS:
		var d := Story.boss_down(o)
		check_eq(d.slice(0, common.size()), common, "%s：玄诚的真相四条线共用" % o)
		check_eq(d.slice(common.size()), Story.coda(o), "%s：接自己出身的收尾" % o)
		downs[o] = d.slice(common.size())
		var entry := Story.shanmen_intro("shaolin", o)
		check_eq(entry.slice(Story.shared("shanmen_intro").size()), Story.entry(o, "shaolin"), "%s：山门前的进寺对话" % o)
	check_eq(downs.values().map(func(d): return JSON.stringify(d)).reduce(func(a, b): return a if a.has(b) else a + [b], []).size(), 4,
		"四段收尾各不相同")
	check_eq(Story.boss_down(""), common, "没选出身（开发开关直进）只播共用部分")


func test_xiepai_entry_line() -> void:
	var line := "奉命入寺夺取秘籍，却发现叛僧另有图谋。"
	for o in Story.ORIGINS:
		check(Story.entry(o, "xiepai").any(func(l): return l.text == line), "%s 邪派：进山门前多一句进寺理由" % o)
		check(not Story.entry(o, "shaolin").any(func(l): return l.text == line), "%s 少林：没有这一句" % o)


func test_xiban_rename() -> void:
	Story.player_name = "小桃"
	check(Story.wake("xiban")[0].text.begins_with("小桃"), "小旦改名后台词里叫新名字")
	Story.player_name = ""


func test_origin_does_not_change_stats() -> void:
	var stats := []
	for o in Story.ORIGINS:
		var w := SimWorld.new(5)
		var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
		var hammer := SimItems.start_weapon(o)
		if not hammer.is_empty():
			w.inventories[p.id].add(w.stamp(hammer))
			check(w.inv_equip(p, int(hammer.uid), "weapon"), "铁匠之子装上锤子")
		stats.append([p.max_hp, p.max_qi, p.speed, p.stats])
	check(stats.all(func(s): return s == stats[0]), "四种出身开局数值完全一样：%s" % [stats])
	check(SimItems.start_weapon("tiejiang").base == "chui", "铁匠之子起始武器是锤子")
	check(SimItems.start_weapon("shenjia").is_empty(), "其余出身按门派默认，不给物品")
	check(not SimItems.bases_for_slot("weapon").has("chui"), "锤子不进 Boss 掉落")
	check(not SimItems.droppable_bases().has("chui"), "锤子不进通关箱")


func test_prologue_layouts_walkable() -> void:
	for o in Story.ORIGINS:
		check(Prologue.LAYOUTS.has(o), "%s 有开场布局" % o)
		var lay: Dictionary = Prologue.LAYOUTS[o]
		var w := SimWorld.new(1)
		w.bounds = PackedVector2Array(Prologue.floor_of(o))
		if o == "langzhong":
			for b in Prologue.CHAPENG_BLOCKS:
				w.blockers.append(PackedVector2Array(b))
		for k in ["start", "move", "trainer", "info", "exit"]:
			check(w.walkable(lay[k]), "%s 开场的 %s %s 走得到" % [o, k, lay[k]])
		check(w.walkable(lay.prop[1]), "%s 开场的教学道具走得到" % o)


func test_profile_keeps_origin() -> void:
	var old := Profile.path
	Profile.path = "user://shansi_test_origin.json"
	Profile.wipe()
	var p := Profile.load_or_new()
	p.origin = "xiban"
	p.player_name = "小桃"
	p.save()
	var q := Profile.load_or_new()
	check_eq([q.origin, q.player_name], ["xiban", "小桃"], "存档带出身和改过的名字")
	Profile.wipe()
	Profile.path = old
