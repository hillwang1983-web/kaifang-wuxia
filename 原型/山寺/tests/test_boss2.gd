## Boss 二毒姥与三人阵法（规格书第四、六节）：毒罩减伤、毒雾扩散与伤害、阵法 / 合击破罩时长、
## 毒蛊毒池、摄魂指定身与截脉解穴、三人窗口判定与退化规则、可破坏物掉落。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0
const CENTER := Vector2(960, 420)


func _world() -> SimWorld:
	var w := SimWorld.new(11)
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(1920, 0), Vector2(1920, 1080), Vector2(0, 1080)])
	return w


func _cmd() -> SimCommand:
	return SimCommand.new()


func _run(w: SimWorld, secs: float, cmds := {}) -> void:
	for i in roundi(secs / DT):
		w.step(DT, cmds)


func _boss(w: SimWorld) -> SimFighter:
	var d := w.add_enemy("dulao", CENTER + Vector2(0, -120))
	d.home = CENTER
	d.state = "chase"
	return d


func test_ward_cut() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var d := _boss(w)
	w.damage(p, d, 100.0, {"skill": true})
	check(is_equal_approx(d.max_hp - d.hp, 5.0), "毒罩减伤 95%%：100 只剩 5（实际 %s）" % (d.max_hp - d.hp))
	d.ward_t = 5.0
	var before := d.hp
	w.damage(p, d, 100.0, {"skill": true})
	check(is_equal_approx(before - d.hp, 100.0), "罩子碎了吃满")


func test_fog_spreads_and_hurts() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(560, 0))
	var d := _boss(w)
	d.timers["gu"] = 999.0
	d.timers["soul"] = 999.0
	_run(w, 9.9, {})
	check(w.fog.is_empty(), "开战十秒内没有毒雾")
	_run(w, 0.2, {})
	check(not w.fog.is_empty(), "十秒后毒雾出现")
	_run(w, 6.0, {})
	check(w.in_fog(p.pos), "毒雾从边缘往里压，站在边上会被罩住（半径 %d）" % w.fog.r)
	var hp := p.hp
	_run(w, 2.0, {})
	var lost := hp - p.hp
	check(absf(lost - 60.0) <= 15.0, "雾中每秒掉 3%% 血：两秒约掉 60（实际 %d）" % lost)
	var q := w.add_hero("partner", "shaolin", "jiemai", CENTER)
	var qhp := q.hp
	_run(w, 1.0, {})
	check_eq(q.hp, qhp, "安全圈里不掉血")


func test_break_durations_and_purify() -> void:
	var w := _world()
	var d := _boss(w)
	w.fog = {"center": CENTER, "r": 120.0, "r_max": 640.0, "r_min": 110.0, "pct": 3.0, "tick": 0.0}
	w.break_wards(CENTER + Vector2(0, 200), 116.0, SimData.COMBO.break_formation)
	check(is_equal_approx(d.ward_t, 10.0), "阵法破罩 10 秒")
	check(not w.in_fog(CENTER + Vector2(0, 200)), "阵法圈内净化毒雾")
	check(w.in_fog(CENTER + Vector2(0, 340)), "圈外照样有雾")
	var w2 := _world()
	var d2 := _boss(w2)
	w2.break_wards(CENTER, 56.0, SimData.COMBO.break_combo)
	check(is_equal_approx(d2.ward_t, 5.0), "双人合击破罩 5 秒")


func _invite(w: SimWorld, p: SimFighter, point: Vector2) -> void:
	var press := _cmd().press("combo")
	press.point = point
	press.has_point = true
	w.step(DT, {p.id: press})
	w.step(DT, {p.id: _cmd()})


func test_formation_needs_two() -> void:
	var w := _world()
	w.formation_enabled = true
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 220))
	var a := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(400, 300))
	var b := w.add_hero("ally", "shaolin", "jiemai", CENTER + Vector2(-400, 300))
	var d := _boss(w)
	d.timers["gu"] = 999.0
	d.timers["soul"] = 999.0
	_invite(w, p, CENTER + Vector2(0, 200))
	check_eq(w.combo.invite.kind, "formation", "三人在场：发出的是阵法邀请")
	w.step(DT, {p.id: _cmd(), a.id: _cmd().press("combo")})
	check(not w.combo.invite.is_empty() and w.freeze_t <= 0.0, "只到一人：阵法不成立，邀请还在")
	w.step(DT, {p.id: _cmd(), b.id: _cmd().press("combo")})
	check(w.freeze_t > 0.0, "第二人到：阵法成立")
	_run(w, 0.6, {})
	check(is_equal_approx(d.ward_t, 10.0 - 0.6 + DT * 0) or d.ward_t > 9.0, "阵法震碎毒罩约 10 秒（剩 %.1f）" % d.ward_t)


func test_formation_degrades_to_combo() -> void:
	var w := _world()
	w.formation_enabled = true
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 220))
	var a := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(400, 300))
	w.add_hero("ally", "shaolin", "jiemai", CENTER + Vector2(-400, 300))
	var d := _boss(w)
	d.timers["gu"] = 999.0
	d.timers["soul"] = 999.0
	_invite(w, p, CENTER + Vector2(0, 200))
	w.step(DT, {p.id: _cmd(), a.id: _cmd().press("combo")})
	_run(w, 3.1, {})
	check(w.events.any(func(e): return e.type == "formation_degrade"), "窗口到了只有一人：退化为双人合击")
	_run(w, 0.6, {})
	check(d.ward_t > 4.0 and d.ward_t <= 5.0, "退化的合击破罩 5 秒（剩 %.1f）" % d.ward_t)
	check(w.combo.moqi >= 1, "退化成功也算合击，默契照加")


func test_soul_root_and_cleanse() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "tiyunzong", CENTER + Vector2(0, 200))
	var j := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(40, 200))
	var d := _boss(w)
	d.timers["gu"] = 999.0
	d.timers["soul"] = 0.0
	d.target_id = -1
	w.step(DT, {})
	check_eq(d.state, "cast", "摄魂指读条")
	check(d.target_id == p.id or d.target_id == j.id, "点名了一名英雄")
	d.target_id = p.id
	w.damage(p, d, 9999.0, {"skill": true, "interrupt": true})
	check_eq(d.state, "cast", "摄魂指读条不能打断")
	_run(w, 1.6, {})
	check(p.root_t > 2.0, "读条完：被点名的人定身 3 秒")
	var before := p.pos
	_run(w, 0.3, {p.id: _cmd()})
	var mv := _cmd()
	mv.move = Vector2.RIGHT
	_run(w, 0.3, {p.id: mv})
	check_eq(p.pos, before, "定身时走不动")
	w.step(DT, {p.id: _cmd(), j.id: _cmd().press("utility")})
	check_eq(p.root_t, 0.0, "队友截脉给你解穴")
	check(w.events.any(func(e): return e.type == "cleanse"), "有解穴事件")


func test_gu_pool_hurts_heroes() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 220))
	var d := _boss(w)
	d.timers["soul"] = 999.0
	d.timers["gu"] = 0.0
	w.step(DT, {})
	check_eq(d.atk_id, "gu", "放毒蛊")
	check(SimEnemies.in_zone(d.atk, d.pos, d.facing, p.pos, p.radius, d.aim_point), "红区落在英雄脚下")
	_run(w, 0.85, {})
	check(w.pools.any(func(pl): return pl.get("team", 0) == SimFighter.FOES), "0.8 秒后落地成毒池")
	var hp := p.hp
	_run(w, 2.0, {})
	check(p.hp < hp, "站在毒池里掉血")


func test_props_drop_without_combat() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var c := w.add_enemy("crate", CENTER + Vector2(30, 0))
	check(not w.in_combat(), "木箱不算进战斗")
	w.damage(p, c, 999.0, {})
	check(not c.alive, "木箱打碎了")
	check(w.ground_items.size() >= 1, "木箱掉东西（金钱 / 丹药）")
	var drops := SimItems.roll_drops(w.loot_rng, "crate")
	check(drops.has("parts") and drops.parts.is_empty(), "零件接口在，阶段 D 之前概率为 0")


func test_dulao_drops_armor() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var d := _boss(w)
	d.ward_t = 99.0
	w.damage(p, d, 99999.0, {"skill": true})
	check_eq(d.state, "sit", "毒姥倒下进入离场流程")
	check(w.fog.is_empty(), "毒雾散了")
	var armor := w.ground_items.filter(func(g): return g.coins == 0 and SimItems.is_equipment(g.item))
	check(armor.size() == 1 and SimItems.slot_type(armor[0].item) == "armor", "毒姥必掉一件防具底子")


func test_three_ai_vs_dulao() -> void:
	# 三个 AI（一个代玩家）对毒姥，量时长和破罩轮数；只证明能打完，不代表真人难度
	var w := _world()
	w.formation_enabled = true
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 240))
	var j := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(-40, 250))
	var a := w.add_hero("ally", "shaolin", "jiemai", CENTER + Vector2(40, 250))
	var d := _boss(w)
	var ais := [SimPartnerAI.new(w, p.id, j.id), SimPartnerAI.new(w, j.id, p.id), SimPartnerAI.new(w, a.id, p.id)]
	var secs := 0.0
	var breaks := 0
	var forms := 0
	while secs < 400.0 and d.state != "sit" and p.alive:
		w.step(DT, {p.id: ais[0].command(DT), j.id: ais[1].command(DT), a.id: ais[2].command(DT)})
		for e in w.events:
			if e.type == "ward_break":
				breaks += 1
			if e.type == "combo_freeze" and e.kind == "formation":
				forms += 1
		w.events.clear()
		secs += DT
	print("      三个 AI 对毒姥：%.0f 秒，结果 %s，破罩 %d 次（其中阵法 %d 次），玩家血 %d" % [secs, d.state, breaks, forms, p.hp])
	check(d.state == "sit", "四百秒内打完毒姥")
	check(breaks >= 2, "至少破罩两轮")
