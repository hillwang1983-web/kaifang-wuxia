## 平衡批量代玩（规格书第十节第十一周「首通成功率三到五成」的参考）：三个 Boss × 两门派 × 三通用技 × 多种子 × 两种玩家水平。
## 「满操作」= 代玩同款 AI；「新手」= 玩家一方闪避概率 0.4、反应慢、响应合击慢、截脉一半时候按晚了、
## 踩进毒池 / 毒雾 1.5 秒后才往外走、不提前躲雾边。队友 AI 始终满操作。
## 一次尝试：Boss 倒下算成功；玩家倒下或 300 秒没打完算失败（关卡里玩家倒下就整段重来）。队友倒下 8 秒后爬起。
## 运行：Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://tools/balance.gd
## 结果写到 res://试玩/平衡_代玩统计.md，并打印到控制台。AI 不等于真人，这份表只用来比较改动前后的相对难度。
extends SceneTree

const DT := 1.0 / 60.0
const LIMIT := 300.0
const SEEDS := [101, 202, 303]
const CENTER := Vector2(960, 420)


func _init() -> void:
	var rows := []
	for boss in ["xuancheng", "dulao", "jingang"]:
		for profile in ["满操作", "新手"]:
			var runs := []
			for sect in ["shaolin", "xiepai"]:
				for util in SimData.UTILITIES:
					for s in SEEDS:
						runs.append(_run(boss, profile, sect, util, s))
			rows.append(_summary(boss, profile, runs))
			print(_line(rows[-1]))
	var md := "# 平衡代玩统计\n\n" \
		+ "生成：`tools/balance.gd`（%s）。每格 %d 次尝试（两门派 × 三通用技 × %d 个种子）。AI 不等于真人，只看相对变化。\n\n" % [Time.get_datetime_string_from_system(), 6 * SEEDS.size(), SEEDS.size()] \
		+ "| Boss | 玩家水平 | 首通成功率 | 成功平均用时 | 玩家倒下次数 | 平均合击 | 平均阵法 | 破罩 / 撞偏 |\n|---|---|---|---|---|---|---|---|\n"
	for r in rows:
		md += "| %s | %s | %d%% | %s | %d | %.1f | %.1f | %.1f / %.1f |\n" % [r.boss, r.profile, roundi(r.rate * 100.0),
			("%.0f 秒" % r.secs) if r.secs > 0.0 else "—", r.downs, r.combos, r.formations, r.breaks, r.deflects]
	md += "
## 铁甲金刚战：弩车与 AI 站位

| 玩家水平 | 弩车被冲撞 | 被扔来的人砸中 | 非操弩 AI 离弩车平均 | 扎堆（90 像素内）时长 |
|---|---|---|---|---|
"
	for r in rows:
		if r.dist > 0.0:
			md += "| %s | %.1f 次 | %.1f 次 | %.0f 像素 | %.1f 秒 |
" % [r.profile, r.hit_charge, r.hit_throw, r.dist, r.crowd_t]
	var f := FileAccess.open("res://试玩/平衡_代玩统计.md", FileAccess.WRITE)
	if f:
		f.store_string(md)
	quit(0)


func _line(r: Dictionary) -> String:
	var s := "%s · %s：首通 %d%%，成功平均 %.0f 秒，玩家倒下 %d 次，合击 %.1f，阵法 %.1f" % [r.boss, r.profile, roundi(r.rate * 100.0), r.secs, r.downs, r.combos, r.formations]
	if r.dist > 0.0:
		s += "；弩车被冲撞 %.1f 次、被扔来的人砸 %.1f 次；AI 离弩车平均 %.0f 像素，扎堆（90 像素内）%.1f 秒" % [r.hit_charge, r.hit_throw, r.dist, r.crowd_t]
	return s


func _summary(boss: String, profile: String, runs: Array) -> Dictionary:
	var ok := runs.filter(func(x): return x.win)
	var avg := func(key: String) -> float:
		return runs.reduce(func(a, x): return a + float(x[key]), 0.0) / maxf(1.0, runs.size())
	return {"boss": SimData.ENEMIES[boss].name, "profile": profile, "rate": float(ok.size()) / runs.size(),
		"secs": ok.reduce(func(a, x): return a + x.secs, 0.0) / ok.size() if not ok.is_empty() else 0.0,
		"downs": runs.filter(func(x): return x.player_down).size(), "combos": avg.call("combos"),
		"formations": avg.call("formations"), "breaks": avg.call("breaks"), "deflects": avg.call("deflects"),
		"hit_charge": avg.call("hit_charge"), "hit_throw": avg.call("hit_throw"), "crowd_t": avg.call("crowd_t"),
		"dist": runs.reduce(func(a, x): return a + x.dist_sum, 0.0) / maxf(1.0, runs.reduce(func(a, x): return a + x.dist_n, 0))}


func _run(boss_kind: String, profile: String, sect: String, util: String, seed_value: int) -> Dictionary:
	var w := SimWorld.new(seed_value)
	w.bounds = PackedVector2Array([Vector2(240, 120), Vector2(1680, 120), Vector2(1680, 900), Vector2(240, 900)])
	var three := boss_kind != "xuancheng"
	w.formation_enabled = three
	var start := CENTER + Vector2(0, 240)
	var boss: SimFighter
	if boss_kind == "jingang":
		SimBallista.setup(w, Vector2(960, 640), [Vector2(400, 400), Vector2(1500, 400), Vector2(400, 760), Vector2(1500, 760)])
		start = Vector2(960, 820)
	var p := w.add_hero("player", sect, util, start)
	var j := w.add_hero("partner", "shaolin", "jiemai", start + Vector2(-40, 0))
	var heroes := [p, j]
	if three:
		heroes.append(w.add_hero("ally", "shaolin", "jiemai", start + Vector2(40, 0)))
	if boss_kind == "jingang":
		for pr in [["chassis", Vector2(400, 300)], ["arm", Vector2(1520, 300)], ["winch", Vector2(1520, 680)]]:
			SimBallista.bind_pile(w, w.add_enemy("pile", pr[1]), pr[0])
		boss = w.add_enemy("jingang", Vector2(960, 290))
	elif boss_kind == "dulao":
		boss = w.add_enemy("dulao", CENTER + Vector2(0, -120))
		boss.home = CENTER
	else:
		boss = w.add_enemy("xuancheng", CENTER)
	boss.state = "chase"
	var ais := []
	for h in heroes:
		var ai := SimPartnerAI.new(w, h.id, j.id if h == p else p.id)
		if boss_kind == "jingang":
			ai.porter = h.kind != "partner"
			ai.may_ride = h.kind != "ally"
		ais.append(ai)
	var novice := profile == "新手"
	if novice:
		ais[0].dodge_chance = 0.4
		ais[0].react = 0.35
		ais[0].invite_react = [1.0, 2.2]
		ais[0].hazard_react = 1.5
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var out := {"win": false, "secs": 0.0, "player_down": false, "combos": 0, "formations": 0, "breaks": 0, "deflects": 0,
		"hit_charge": 0, "hit_throw": 0, "dist_sum": 0.0, "dist_n": 0, "crowd_t": 0.0}
	var revive := {}
	var late_interrupt := false
	var cast_seen := -1.0
	while out.secs < LIMIT:
		var cmds := {}
		for i in heroes.size():
			cmds[heroes[i].id] = ais[i].command(DT)
		# 玩家在玄诚读条时按通用技：满操作 0.4 秒就按，新手一半时候反应不过来
		if boss.state == "cast" and boss_kind == "xuancheng":
			if cast_seen != boss.heavy_timer:
				cast_seen = boss.heavy_timer
				late_interrupt = novice and rng.randf() < 0.5
			if boss.t > (1.9 if late_interrupt else 0.4):
				cmds[p.id].press("utility")
		w.step(DT, cmds)
		out.secs += DT
		for e in w.events:
			match e.type:
				"combo_freeze":
					out[("formations" if e.kind == "formation" else "combos")] += 1
				"ward_break":
					out.breaks += 1
				"deflect":
					out.deflects += 1
				"ballista_hit":
					out[("hit_charge" if e.cause == "charge" else "hit_throw")] += 1
				"hero_down":
					if e.id == p.id:
						out.player_down = true
					else:
						revive[e.id] = 8.0
		w.events.clear()
		# 金刚战：不在车上、手上没事（不拼装、不背零件）的 AI 离弩车多远；离车 90 像素内算扎堆
		if boss_kind == "jingang" and w.ballista.built:
			for h in heroes:
				if h.kind == "player" or not h.alive or h.state == "mounted" or h.state == "build" or not SimBallista.carried(w, h).is_empty():
					continue
				var d: float = h.pos.distance_to(w.ballista.center)
				out.dist_sum += d
				out.dist_n += 1
				if d < 90.0:
					out.crowd_t += DT
		for id in revive.keys():
			revive[id] -= DT
			if revive[id] <= 0.0:
				var f := w.fighter(id)
				f.alive = true
				f.state = "idle"
				f.hp = f.max_hp * 0.4
				revive.erase(id)
		if boss.state == "sit":
			out.win = true
			break
		if out.player_down:
			break
	return out
