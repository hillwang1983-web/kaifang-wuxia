## 纯逻辑层：普攻与架势、闪避无敌、预警与看破、重击读条与截脉、合击与默契、AI 净心、门派被动。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0


func _world() -> SimWorld:
	var w := SimWorld.new(7)
	return w


func _run(w: SimWorld, secs: float, cmds := {}, each := Callable()) -> void:
	var n := roundi(secs / DT)
	for i in n:
		var c: Dictionary = each.call() if each.is_valid() else cmds
		w.step(DT, c)


func _cmd() -> SimCommand:
	return SimCommand.new()


func test_attack_and_stance() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	var m := w.add_enemy("louluo", Vector2(150, 100))
	w.step(DT, {p.id: _cmd().press("attack")})
	check_eq(m.hp, 240.0 - 30.0, "喽啰吃第一段普攻满伤害")
	var b := w.add_enemy("xuancheng", Vector2(100, 160))
	m.alive = false
	p.atk_cd = 0.0
	p.combo_t = 0.0
	w.step(DT, {p.id: _cmd().press("attack")})
	check_eq(b.hp, 5000.0 - 15.0, "玄诚架势：普攻只吃一半")
	w.stagger(b, 2.0)
	p.atk_cd = 0.0
	p.combo_t = 0.0
	w.step(DT, {p.id: _cmd().press("attack")})
	check_eq(b.hp, 5000.0 - 15.0 - 30.0, "失衡时普攻吃满")


func test_dodge_iframes() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	var m := w.add_enemy("louluo", Vector2(140, 100))
	_run(w, 0.2)
	check_eq(m.state, "windup", "喽啰贴近后出刀预警")
	_run(w, 0.4)
	w.step(DT, {p.id: _cmd().press("dodge")})
	_run(w, 0.2)
	check_eq(p.hp, 1000.0, "闪避躲过出刀")
	# 无敌帧硬吃：站在原地、带着无敌时间挨刀
	var w2 := _world()
	var p2 := w2.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	w2.add_enemy("louluo", Vector2(140, 100))
	_run(w2, 0.6)
	p2.inv_t = 0.3
	_run(w2, 0.2)
	check_eq(p2.hp, 1000.0, "无敌帧内不掉血")
	check(w2.events.any(func(e): return e.type == "evade"), "有「闪过」事件")


func test_boss_sweep_telegraph_and_read() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var b := w.add_enemy("xuancheng", Vector2(270, 200))
	b.state = "chase"
	w.step(DT, {})
	check_eq(b.state, "windup", "玄诚进入横扫预警")
	check_eq(b.atk_id, "sweep", "近身先用横扫")
	_run(w, 0.5)
	check_eq(p.hp, 1000.0, "预警 0.8 秒内还没挨打")
	# 出手前 0.5 秒内闪避：看破，玄诚失衡
	w.step(DT, {p.id: _cmd().press("dodge")})
	_run(w, 0.4)
	check_eq(p.hp, 1000.0, "闪过横扫")
	check_eq(b.state, "stagger", "看破横扫，玄诚失衡")


func test_sweep_hits_when_not_dodged() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var b := w.add_enemy("xuancheng", Vector2(270, 200))
	b.state = "chase"
	_run(w, 1.0)
	check_eq(p.hp, 1000.0 - 120.0, "不闪就吃横扫 120")


func test_heavy_cast_and_jiemai() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var b := w.add_enemy("xuancheng", Vector2(330, 200))
	b.hp = b.max_hp * 0.5
	b.state = "chase"
	_run(w, 2.6)
	var hit_cast := false
	for i in 200:
		if b.state == "cast":
			hit_cast = true
			break
		w.step(DT, {})
	check(hit_cast, "半血后进入重击读条")
	_run(w, 2.1)
	check_eq(p.hp <= 1000.0 - 350.0, true, "没打断：重击全场重伤")
	# 再来一次，这次截脉打断
	var w2 := _world()
	var p2 := w2.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var b2 := w2.add_enemy("xuancheng", Vector2(330, 200))
	b2.hp = b2.max_hp * 0.5
	b2.state = "chase"
	for i in 400:
		if b2.state == "cast":
			break
		w2.step(DT, {})
	_run(w2, 0.5)
	w2.step(DT, {p2.id: _cmd().press("utility")})
	check_eq(b2.state, "stagger", "截脉打断读条，玄诚失衡")
	check(b2.stagger_t >= 1.9, "失衡约 2 秒")
	_run(w2, 1.0)
	check(p2.hp > 1000.0 - 350.0, "打断后不吃重击")


func test_combo_success_and_moqi() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var j := w.add_hero("partner", "shaolin", "", Vector2(260, 260))
	var b := w.add_enemy("xuancheng", Vector2(300, 200))
	b.hp = b.max_hp * 0.5
	b.state = "cast"
	b.atk = SimData.ENEMIES.xuancheng.attacks.heavy
	b.atk_id = "heavy"
	var press := _cmd().press("combo")
	press.point = Vector2(290, 200)
	press.has_point = true
	w.step(DT, {p.id: press})
	w.step(DT, {p.id: _cmd()})
	check(not w.combo.invite.is_empty(), "松开合击键发出邀请")
	# 队友不在光圈里、也没按键：不成立
	w.step(DT, {p.id: _cmd(), j.id: _cmd()})
	check(not w.combo.invite.is_empty(), "队友没响应前邀请还在")
	w.step(DT, {p.id: _cmd(), j.id: _cmd().press("combo")})
	check(w.freeze_t > 0.0, "队友按合击键：成立并定格")
	check_eq(w.combo.moqi, 1, "默契 +1")
	_run(w, 0.6)
	check_eq(b.state, "stagger", "合击打断重击读条")
	check(b.hp < b.max_hp * 0.5 - 100.0, "合击造成伤害")


func test_combo_timeout_fallback() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	w.add_hero("partner", "shaolin", "", Vector2(400, 400))
	w.combo.moqi = 4
	var qi := p.qi
	var press := _cmd().press("combo")
	w.step(DT, {p.id: press})
	w.step(DT, {p.id: _cmd()})
	_run(w, 3.1)
	check(w.combo.invite.is_empty(), "三秒无人响应，邀请结束")
	check_eq(w.combo.moqi, 0, "超时默契归零")
	check(w.events.any(func(e): return e.type == "skill" and e.skill == "luohanquan"), "退化为罗汉拳")
	check(p.qi >= qi - 0.01, "退化招式不耗内力")
	check_eq(w.combo.cd, 0.0, "不消耗合击冷却")


func test_moqi_streak_and_levels() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var j := w.add_hero("partner", "shaolin", "", Vector2(220, 200))
	for k in 2:
		w.combo.cd = 0.0
		w.step(DT, {p.id: _cmd().press("combo")})
		w.step(DT, {p.id: _cmd(), j.id: _cmd()})  # 光圈默认落在身前 70，队友站在里面
		_run(w, 0.6)
	check_eq(w.combo.moqi, 3, "第一次 +1，三十秒内连续成功再 +2")
	check_eq(w.combo.level(), 1, "默契 3 为二级")


func test_partner_ai_answers_invite() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var j := w.add_hero("partner", "shaolin", "", Vector2(320, 300))
	var ai := SimPartnerAI.new(w, j.id, p.id)
	w.step(DT, {p.id: _cmd().press("combo"), j.id: ai.command(DT)})
	w.step(DT, {p.id: _cmd(), j.id: ai.command(DT)})
	var ok := false
	for i in 180:
		w.step(DT, {p.id: _cmd(), j.id: ai.command(DT)})
		if w.combo.moqi > 0:
			ok = true
			break
	check(ok, "AI 净心三秒内走进光圈完成合击")


func test_shaolin_passive_and_shield() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(200, 200))
	var m := w.add_enemy("louluo", Vector2(400, 400))
	w.damage(m, p, 310.0)
	check(p.primed, "受击积满内力")
	w.step(DT, {p.id: _cmd().press("skill_2")})
	check_eq(p.state, "charge", "金钟罩进入蓄力")
	_run(w, 1.3, {p.id: _cmd().press("skill_2")})
	w.step(DT, {p.id: _cmd()})
	check(p.shield >= 290.0, "蓄满的金钟罩护盾接近上限")
	w.step(DT, {p.id: _cmd().press("skill_3")})
	w.step(DT, {p.id: _cmd().press("cancel")})
	check_eq(p.cd_of("dalijingangzhang"), 0.0, "瞄准中取消不进冷却")


func test_xiepai_poison_and_pool() -> void:
	var w := _world()
	var p := w.add_hero("player", "xiepai", "jiemai", Vector2(200, 200))
	var m := w.add_enemy("louluo", Vector2(240, 200))
	m.state = "wait"
	m.state = "idle"
	for i in 3:
		p.atk_cd = 0.0
		w.step(DT, {p.id: _cmd().press("attack")})
	check(m.poison_t > 0.0, "三次命中引爆叠毒")
	var aim := _cmd().press("skill_2")
	aim.point = Vector2(300, 260)
	aim.has_point = true
	w.step(DT, {p.id: aim})
	var rel := _cmd()
	rel.point = Vector2(300, 260)
	rel.has_point = true
	w.step(DT, {p.id: rel})
	check_eq(w.pools.size(), 1, "化功散落地成毒池")


func test_boss_sits_and_full_fight() -> void:
	# 两个 AI（用净心的 AI 代玩家）对打玄诚，量一下时长；只证明流程能打完，不代表真人难度
	var w := _world()
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(960, 0), Vector2(960, 540), Vector2(0, 540)])
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(300, 300))
	var j := w.add_hero("partner", "shaolin", "", Vector2(260, 330))
	var b := w.add_enemy("xuancheng", Vector2(480, 200))
	b.state = "chase"
	var ai_p := SimPartnerAI.new(w, p.id, j.id)
	var ai_j := SimPartnerAI.new(w, j.id, p.id)
	var secs := 0.0
	while secs < 400.0 and b.state != "sit" and p.alive and j.alive:
		w.step(DT, {p.id: ai_p.command(DT), j.id: ai_j.command(DT)})
		secs += DT
	print("      两个 AI 对玄诚：%.0f 秒，结果 %s，玩家血 %d，净心血 %d，默契 %d" % [secs, b.state, p.hp, j.hp, w.combo.moqi])
	check(b.state == "sit" or not p.alive or not j.alive, "四百秒内分出结果")
	if b.state == "sit":
		check(not b.active(), "玄诚坐地后不再参战")


func test_blockers_and_gate_steering() -> void:
	# 上下两块地由一道墙隔开，中间留门洞；墙下有一块石狮
	var w := _world()
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(400, 0), Vector2(400, 180), Vector2(220, 180), Vector2(220, 240),
		Vector2(400, 240), Vector2(400, 400), Vector2(0, 400), Vector2(0, 240), Vector2(180, 240), Vector2(180, 180), Vector2(0, 180)])
	w.blockers.append(PackedVector2Array([Vector2(60, 280), Vector2(120, 280), Vector2(120, 340), Vector2(60, 340)]))
	w.waypoints.assign([Vector2(200, 260), Vector2(200, 160)])
	check(not w.walkable(Vector2(90, 300)), "石狮占的地方不能走")
	check(not w.clear_line(Vector2(60, 380), Vector2(60, 60)), "隔着墙看不见")
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(60, 380))
	var target := Vector2(60, 60)
	for i in 600:
		var c := _cmd()
		c.move = w.steer(p.pos, target)
		w.step(DT, {p.id: c})
		if p.pos.distance_to(target) < 8.0:
			break
	check(p.pos.distance_to(target) < 8.0, "经门洞路点绕到墙那边（停在 %s）" % p.pos)
