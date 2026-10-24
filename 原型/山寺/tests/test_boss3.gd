## Boss 三铁甲金刚与弩车（规格书第六、七、八节）：零件、拼装与打断、上下车、三档裂口、耐久散架重散、
## 铁甲与裂口伤害、冲撞撞偏、踏地震、抓人扔弩车、通关箱品质权重、三个 AI 打完金刚。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0
const CENTER := Vector2(960, 700)
const SPOTS := [Vector2(400, 400), Vector2(1500, 400), Vector2(400, 800), Vector2(1500, 800)]


func _world() -> SimWorld:
	var w := SimWorld.new(23)
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(1920, 0), Vector2(1920, 1080), Vector2(0, 1080)])
	SimBallista.setup(w, CENTER, SPOTS)
	return w


func _cmd() -> SimCommand:
	return SimCommand.new()


func _run(w: SimWorld, secs: float, cmds := {}) -> void:
	for i in roundi(secs / DT):
		w.step(DT, cmds)


func _built(w: SimWorld) -> void:
	w.ballista.installed = SimData.BALLISTA.parts.duplicate()
	w.ballista.built = true
	w.ballista.hp = SimData.BALLISTA.hp


func _boss(w: SimWorld, at := CENTER + Vector2(0, -400)) -> SimFighter:
	var g := w.add_enemy("jingang", at)
	g.state = "chase"
	for k in ["charge", "quake", "grab"]:
		g.timers[k] = 999.0
	return g


func test_parts_pickup_and_install() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(400, 430))
	var pile := w.add_enemy("pile", Vector2(400, 400))
	SimBallista.bind_pile(w, pile, "chassis")
	w.damage(p, pile, 999.0, {})
	check_eq(w.parts.size(), 1, "零件堆打碎掉一样零件")
	check_eq(w.parts[0].part, "chassis", "掉的是关卡指定的底盘")
	var inv: SimInventory = w.inventories[p.id]
	w.ground_items.clear()  # 零件堆顺带掉的钱药不算
	var before := inv.entries.size()
	p.pos = w.parts[0].pos
	w.step(DT, {})
	check_eq(SimBallista.carried(w, p).get("part", ""), "chassis", "走过去自动背上")
	check_eq(inv.entries.size(), before, "零件不进物品栏")
	p.pos = CENTER + Vector2(20, 0)
	w.step(DT, {})
	check_eq(w.ballista.installed, ["chassis"], "带到中央自动装上")
	check(SimBallista.carried(w, p).is_empty() and w.parts.is_empty(), "装上后零件位空了")
	var bp := w.add_hero("partner", "shaolin", "jiemai", CENTER)
	w.step(DT, {bp.id: _cmd().press("interact")})
	check(bp.state != "build", "零件不齐不能拼")


func test_build_and_interrupt() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 20))
	w.ballista.installed = SimData.BALLISTA.parts.duplicate()
	w.step(DT, {p.id: _cmd().press("interact")})
	check_eq(p.state, "build", "零件齐了按互动开始拼装")
	_run(w, 1.0, {})
	var mv := _cmd()
	mv.move = Vector2.RIGHT
	w.step(DT, {p.id: mv})
	check(p.state != "build" and w.ballista.build_t == 0.0, "走动打断拼装，进度清零")
	w.step(DT, {p.id: _cmd().press("interact")})
	_run(w, 1.0, {})
	var g := w.add_enemy("louluo", p.pos + Vector2(30, 0))
	w.damage(g, p, 50.0, {})
	g.alive = false
	check(p.state != "build" and w.events.any(func(e): return e.type == "build_broken" and e.why == "hit"), "挨打打断拼装")
	p.pos = CENTER + Vector2(0, 20)
	w.step(DT, {p.id: _cmd().press("interact")})
	_run(w, 3.05, {})
	check(w.ballista.built and w.ballista.hp == 3, "站满三秒拼好，耐久 3")


func test_mount_and_charge_tiers() -> void:
	var w := _world()
	_built(w)
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 20))
	var g := _boss(w)
	w.step(DT, {p.id: _cmd().press("interact")})
	check_eq(p.state, "mounted", "按互动上车")
	var mv := _cmd()
	mv.move = Vector2.LEFT
	var at := p.pos
	_run(w, 0.5, {p.id: mv})
	check_eq(p.pos, at, "车上不能走动")
	var radii := []
	for secs in [0.2, 0.8, 1.4]:
		var hold := _cmd()
		hold.held["attack"] = true
		hold.aim = (g.pos - CENTER).normalized()
		_run(w, secs, {p.id: hold})
		var rel := _cmd()
		rel.aim = hold.aim
		w.step(DT, {p.id: rel})
		_run(w, 1.0, {})
		radii.append(g.breaches[-1].r if not g.breaches.is_empty() else 0.0)
	check_eq(radii, SimData.BALLISTA.breach_radius, "蓄力三档打出三种大小的裂口：%s" % [radii])
	check(g.breaches[0].off.y > 0.0, "裂口在弩车那一侧（金刚朝弩车的一面）")
	w.step(DT, {p.id: _cmd().press("interact")})
	check(p.state == "idle" and w.ballista.rider == -1, "再按互动下车")


func test_armor_and_breach_damage() -> void:
	var w := _world()
	var g := _boss(w, Vector2(960, 300))
	var below := w.add_hero("player", "shaolin", "jiemai", g.pos + Vector2(0, 40))
	var above := w.add_hero("player", "shaolin", "jiemai", g.pos + Vector2(0, -40))
	var hp := g.hp
	w.damage(below, g, 100.0, {"skill": true})
	check(is_equal_approx(hp - g.hp, 1.0), "没裂口：铁甲减伤 99%%（100 只剩 %.1f）" % (hp - g.hp))
	SimBallista.add_breach(w, g, g.pos + Vector2(0, 200), 2)
	hp = g.hp
	w.damage(below, g, 100.0, {"skill": true})
	check(is_equal_approx(hp - g.hp, 100.0), "从裂口一侧打：吃满")
	hp = g.hp
	w.damage(above, g, 100.0, {"skill": true})
	check(is_equal_approx(hp - g.hp, 1.0), "从背面打：裂口不在命中点，照样减伤")
	_run(w, SimData.BALLISTA.breach_time + 0.1, {})
	check(g.breaches.is_empty(), "裂口 20 秒后合上")


func test_durability_break_and_rescatter() -> void:
	var w := _world()
	_built(w)
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 20))
	w.step(DT, {p.id: _cmd().press("interact")})
	SimBallista.damage(w, "charge")
	SimBallista.damage(w, "charge")
	check(w.ballista.built and w.ballista.hp == 1, "扣两次还剩 1")
	SimBallista.damage(w, "throw")
	check(not w.ballista.built and w.ballista.installed.is_empty(), "耐久扣完散架")
	check(p.state == "idle" and w.ballista.rider == -1, "散架时操弩者被摔下来")
	check_eq(w.parts.size(), 3, "三样零件重新散出来")
	var names := w.parts.map(func(q): return q.part)
	names.sort()
	var want: Array = SimData.BALLISTA.parts.duplicate()
	want.sort()
	check_eq(names, want, "底盘、弓臂、绞盘各一")
	check(w.parts.all(func(q): return q.pos in SPOTS), "散到关卡给的场边位置")
	var w2 := _world()
	_built(w2)
	SimBallista.damage(w2, "x")
	SimBallista.damage(w2, "x")
	SimBallista.damage(w2, "x")
	check(w2.parts.map(func(q): return q.pos) == w.parts.map(func(q): return q.pos), "同种子散落位置一致（联机可复现）")


func test_charge_hits_ballista_and_deflect() -> void:
	var w := _world()
	_built(w)
	w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(300, 0))
	var g := _boss(w, CENTER + Vector2(0, -300))
	g.timers["charge"] = 0.0
	w.step(DT, {})
	check(g.state == "windup" and g.atk_id == "charge", "冲撞预警")
	check(g.facing.dot(Vector2.DOWN) > 0.99, "冲撞朝弩车")
	_run(w, SimData.ENEMIES.jingang.attacks.charge.tele + 1.0, {})
	check_eq(w.ballista.hp, 2, "没撞偏：撞上弩车扣 1 耐久")
	var w2 := _world()
	_built(w2)
	var a := w2.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, -100))
	var b := w2.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(40, -100))
	var g2 := _boss(w2, CENTER + Vector2(0, -300))
	g2.timers["charge"] = 0.0
	w2.step(DT, {})
	var press := _cmd().press("combo")
	press.point = a.pos
	press.has_point = true
	w2.step(DT, {a.id: press})
	w2.step(DT, {a.id: _cmd(), b.id: _cmd().press("combo")})
	_run(w2, 0.6, {})
	check(w2.events.any(func(e): return e.type == "deflect") or g2.state == "stagger", "预警期间合击成立：冲撞被撞偏")
	_run(w2, 3.0, {})
	check_eq(w2.ballista.hp, 3, "撞偏后弩车没事")


func test_quake_dodge() -> void:
	var w := _world()
	var a := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var b := w.add_hero("partner", "shaolin", "tiyunzong", CENTER + Vector2(300, 0))
	var g := _boss(w, CENTER + Vector2(0, -400))
	g.timers["quake"] = 0.0
	w.step(DT, {})
	check_eq(g.atk_id, "quake", "踏地震预警")
	check(SimEnemies.in_zone(g.atk, g.pos, g.facing, b.pos, b.radius), "全场都在范围里")
	_run(w, SimData.ENEMIES.jingang.attacks.quake.tele - 0.2, {})
	var hp_a := a.hp
	var hp_b := b.hp
	w.step(DT, {a.id: _cmd().press("dodge")})
	_run(w, 0.3, {})
	check_eq(a.hp, hp_a, "翻滚的无敌时间躲过踏地震")
	check(b.hp < hp_b, "站着不动挨震")


func test_grab_throw_into_ballista() -> void:
	var w := _world()
	_built(w)
	var rider := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(0, 20))
	w.step(DT, {rider.id: _cmd().press("interact")})
	var g := _boss(w, CENTER + Vector2(0, -150))
	var v := w.add_hero("player", "shaolin", "jiemai", g.pos + Vector2(0, 50))
	g.timers["grab"] = 0.0
	w.step(DT, {})
	check(g.atk_id == "grab" and g.target_id == v.id, "抓最近的、不在车上的人")
	_run(w, SimData.ENEMIES.jingang.attacks.grab.tele + 0.05, {})
	check_eq(v.state, "thrown", "被抓住扔出去")
	_run(w, 0.6, {})
	check_eq(w.ballista.hp, 2, "落点砸中弩车扣 1 耐久")
	check(v.state != "thrown", "落地")


func test_chest_quality_weights() -> void:
	var r := RandomNumberGenerator.new()
	r.seed = 99
	var n := {"magic": 0, "rare": 0}
	var bases := {}
	for i in 1000:
		var it := SimItems.roll_chest(r)
		n[it.quality] = n.get(it.quality, 0) + 1
		bases[it.base] = true
	check_eq(n.size(), 2, "只出魔法、稀有：%s" % [n])
	check(n.magic > 540 and n.magic < 660, "魔法约六成（%d / 1000）" % n.magic)
	check(bases.size() == SimItems.droppable_bases().size() and not bases.has("chui"), "底子随机，能掉的底子都能出（不出起始锤子）")
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var j := w.add_hero("partner", "shaolin", "jiemai", CENTER)
	var chest := w.add_interactable("chest", CENTER + Vector2(10, 0))
	w.step(DT, {j.id: _cmd().press("interact")})
	check(chest.on and w.ground_items.is_empty(), "没物品栏的 AI 开不了")
	w.step(DT, {p.id: _cmd().press("interact")})
	check(not chest.on, "玩家开过就熄")
	check(w.ground_items.size() == 1 or w.inventories[p.id].entries.size() > 0, "得一件装备")


func test_jingang_drops_accessory() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER)
	var g := _boss(w)
	w.damage(p, g, 99999.0, {"bolt": 2})
	check_eq(g.state, "sit", "金刚倒下")
	var acc := w.ground_items.filter(func(q): return q.coins == 0 and SimItems.is_equipment(q.item))
	check(acc.size() == 1 and SimItems.slot_type(acc[0].item) == "accessory", "金刚掉一件饰品底子")


func test_three_ai_vs_jingang() -> void:
	# 三个 AI（一个代玩家）从捡零件打起：只证明能打完、弩车 / 撞偏都用上，不代表真人难度
	var w := _world()
	w.formation_enabled = true
	var p := w.add_hero("player", "shaolin", "jiemai", CENTER + Vector2(0, 120))
	var j := w.add_hero("partner", "shaolin", "jiemai", CENTER + Vector2(-40, 130))
	var a := w.add_hero("ally", "shaolin", "jiemai", CENTER + Vector2(40, 130))
	var piles := [["chassis", Vector2(420, 420)], ["arm", Vector2(1500, 420)], ["winch", Vector2(1500, 820)]]
	for pr in piles:
		SimBallista.bind_pile(w, w.add_enemy("pile", pr[1]), pr[0])
	var g := w.add_enemy("jingang", Vector2(960, 300))
	g.state = "chase"
	var ais := [SimPartnerAI.new(w, p.id, j.id), SimPartnerAI.new(w, j.id, p.id), SimPartnerAI.new(w, a.id, p.id)]
	ais[0].porter = true
	ais[0].may_ride = true
	ais[1].may_ride = true
	ais[2].porter = true
	var secs := 0.0
	var stats := {"deflect": 0, "bolt_fire": 0, "ballista_built": 0, "ballista_break": 0, "hero_down": 0,
		"charge": 0, "combo_invite": 0, "combo_freeze": 0, "combo_broken": 0, "combo_timeout": 0, "ballista_hit": 0}
	var dist_sum := 0.0
	var dist_n := 0
	var crowd_t := 0.0
	while secs < 400.0 and g.state != "sit":
		w.step(DT, {p.id: ais[0].command(DT), j.id: ais[1].command(DT), a.id: ais[2].command(DT)})
		# 不在车上、手上没事的队友 AI（净心、韩青）离弩车多远；90 像素内算扎堆
		if w.ballista.built:
			for h in [j, a]:
				if h.alive and h.state != "mounted" and h.state != "build" and SimBallista.carried(w, h).is_empty():
					var d: float = h.pos.distance_to(w.ballista.center)
					dist_sum += d
					dist_n += 1
					if d < 90.0:
						crowd_t += DT
		for e in w.events:
			if stats.has(e.type):
				stats[e.type] += 1
			if e.type == "telegraph" and e.atk == "charge":
				stats.charge += 1
			if e.type == "hero_down":
				var f := w.fighter(e.id)
				f.alive = true
				f.state = "idle"
				f.hp = f.max_hp
		w.events.clear()
		secs += DT
	var avg_d := dist_sum / maxf(1.0, dist_n)
	print("      三个 AI 对铁甲金刚：%.0f 秒，结果 %s，%s，金刚血 %d；队友离弩车平均 %.0f 像素，扎堆 %.1f 秒" % [secs, g.state, stats, g.hp, avg_d, crowd_t])
	check(avg_d > 180.0, "不操弩的队友不围着弩车（平均 %.0f 像素，要 > 180）" % avg_d)
	check(crowd_t < secs * 0.15, "队友在弩车 90 像素内的时间不到一成半（%.1f / %.0f 秒）" % [crowd_t, secs])
	check(g.state == "sit", "四百秒内打完金刚")
	check(stats.ballista_built >= 1 and stats.bolt_fire >= 3, "拼好弩车并发射")
