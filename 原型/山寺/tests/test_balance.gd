## 规格书第六节验收：三个 Boss 分别在「不闪避 / 不摆阵 / 不用弩车」时会团灭。
## 用 AI 队伍（和代玩同一套 AI）关掉对应本事去打，倒下不复活，限时内必须全员倒下。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0
const CENTER := Vector2(960, 420)
const LIMIT := 420.0


func _world() -> SimWorld:
	var w := SimWorld.new(31)
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(1920, 0), Vector2(1920, 1080), Vector2(0, 1080)])
	return w


## 跑到 Boss 坐地或全员倒下；返回 [秒数, 是否团灭]
func _fight(w: SimWorld, boss: SimFighter, ais: Array, hero_ids: Array) -> Array:
	var secs := 0.0
	while secs < LIMIT and boss.state != "sit" and hero_ids.any(func(id): return w.fighter(id).alive):
		var cmds := {}
		for i in ais.size():
			cmds[hero_ids[i]] = ais[i].command(DT)
		# 代玩玩家在玄诚读条时按通用技（截脉），和关卡里的代玩一样
		if boss.kind == "xuancheng" and boss.state == "cast" and boss.t > 0.4:
			cmds[hero_ids[0]].press("utility")
		w.step(DT, cmds)
		w.events.clear()
		secs += DT
	return [secs, not hero_ids.any(func(id): return w.fighter(id).alive)]


func _team(w: SimWorld, n: int, at: Vector2) -> Array:
	var ids := []
	for i in n:
		ids.append(w.add_hero(["player", "partner", "ally"][i], "shaolin", "jiemai", at + Vector2(-40 + 40 * i, 0)).id)
	return ids


func _ais(w: SimWorld, ids: Array, setup: Callable) -> Array:
	var out := []
	for i in ids.size():
		var ai := SimPartnerAI.new(w, ids[i], ids[1] if i == 0 else ids[0])
		setup.call(ai)
		out.append(ai)
	return out


func test_xuancheng_wipes_without_dodge() -> void:
	var w := _world()
	var ids := _team(w, 2, CENTER + Vector2(0, 200))
	var boss := w.add_enemy("xuancheng", CENTER)
	boss.state = "chase"
	var r := _fight(w, boss, _ais(w, ids, func(ai): ai.can_dodge = false), ids)
	print("      不闪避打玄诚：%.0f 秒，团灭 %s，玄诚血 %d" % [r[0], r[1], boss.hp])
	check(r[1], "不闪避会被玄诚团灭")


func test_dulao_wipes_without_formation() -> void:
	var w := _world()
	w.formation_enabled = true
	var ids := _team(w, 3, CENTER + Vector2(0, 240))
	var boss := w.add_enemy("dulao", CENTER + Vector2(0, -120))
	boss.home = CENTER
	boss.state = "chase"
	var r := _fight(w, boss, _ais(w, ids, func(ai): ai.can_combo = false), ids)
	print("      不摆阵打毒姥：%.0f 秒，团灭 %s，毒姥血 %d" % [r[0], r[1], boss.hp])
	check(r[1], "不摆阵破罩会被毒姥团灭")


func test_jingang_wipes_without_ballista() -> void:
	var w := _world()
	w.formation_enabled = true
	SimBallista.setup(w, Vector2(960, 700), [Vector2(400, 400), Vector2(1500, 400), Vector2(400, 800)])
	var ids := _team(w, 3, Vector2(960, 820))
	var boss := w.add_enemy("jingang", Vector2(960, 300))
	boss.state = "chase"
	var r := _fight(w, boss, _ais(w, ids, func(ai): ai.use_ballista = false), ids)
	print("      不用弩车打金刚：%.0f 秒，团灭 %s，金刚血 %d" % [r[0], r[1], boss.hp])
	check(r[1], "不用弩车会被铁甲金刚团灭")
