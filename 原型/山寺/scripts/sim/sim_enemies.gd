## 敌人行为：喽啰与玄诚。状态机沿用 V0.4：追击 → 预警（红区）→ 出手 → 收招；
## 玄诚带架势，阶段二（半血）加入两秒读条的重击，必须用截脉或合击打断，否则全场重伤。
class_name SimEnemies
extends RefCounted


static func step(w: SimWorld, e: SimFighter, dt: float) -> void:
	e.moving = false
	if not e.alive or e.state == "sit" or e.state == "wait" or e.state == "dead":
		return
	var k: Dictionary = SimData.ENEMIES[e.kind]
	if k.get("prop", false):
		return
	if e.kind == "dulao":
		_dulao(w, e, k, dt)
		return
	if e.kind == "jingang":
		_jingang(w, e, k, dt)
		return
	var target := _nearest_hero(w, e)
	if e.kind == "xuancheng":
		_boss_phase(w, e, k, dt)
	match e.state:
		"stagger":
			if e.stagger_t <= 0.0:
				e.state = "chase"
		"flinch":
			e.t += dt
			if e.t >= 0.18:
				e.state = "chase"
		"idle":
			if target and target.pos.distance_to(e.pos) < k.aggro:
				e.state = "chase"
				e.in_combat = true
		"chase":
			if target == null:
				return
			e.in_combat = true
			var to := target.pos - e.pos
			var d := to.length()
			e.facing = to.normalized()
			if e.plan == "":
				e.plan = _pick(w, e, k, d)
			var a: Dictionary = k.attacks[e.plan]
			if a.shape == "field":
				_begin(w, e, e.plan, a, "cast")
			elif d <= a.reach and d >= a.get("min_dist", 0.0) * 0.7:
				if e.kind == "louluo" and _busy_mates(w, e) >= 2:
					return  # 同时出刀的喽啰不超过两个，其余在外圈等
				_begin(w, e, e.plan, a, "windup")
			elif a.has("min_dist") and d < a.min_dist * 0.7:
				e.plan = "sweep"
			elif e.root_t <= 0.0:
				w._move(e, w.steer(e.pos, target.pos) * e.speed * (1.0 - e.slow) * dt)
				e.moving = true
		"windup":
			e.t += dt
			if e.t >= e.atk.tele:
				if e.atk.shape == "line":
					e.state = "dash"
					e.t = 0.0
					e.dash_hit = false
				else:
					_strike(w, e)
		"dash":
			e.t += dt
			w._move(e, e.facing * (e.atk.range / 0.25) * dt)
			for h in w.heroes():
				if not e.dash_hit and h.pos.distance_to(e.pos) < e.radius + h.radius + 6.0:
					e.dash_hit = true
					_hit_hero(w, e, h)
			if e.t >= 0.25:
				_end_attack(w, e)
		"cast":
			e.t += dt
			if e.t >= e.atk.cast:
				w.emit("heavy_release", {"id": e.id, "pos": e.pos})
				for h in w.heroes():
					w.damage(e, h, e.atk.dmg, {"unavoidable": true, "heavy": true})
				_recover(e)
		"recover":
			e.t += dt
			if e.t >= e.atk.get("rec", 0.5):
				e.state = "chase"
				e.atk = {}
				e.atk_id = ""


static func _boss_phase(w: SimWorld, e: SimFighter, k: Dictionary, dt: float) -> void:
	if e.phase == 1 and e.hp <= e.max_hp * k.phase2_at:
		e.phase = 2
		e.heavy_timer = 2.5
		w.emit("phase2", {"id": e.id})
	if e.phase == 2 and e.heavy_timer > 0.0:
		e.heavy_timer -= dt


static func _pick(w: SimWorld, e: SimFighter, k: Dictionary, d: float) -> String:
	if e.kind != "xuancheng":
		return "slash"
	if e.phase == 2 and e.heavy_timer <= 0.0:
		e.heavy_timer = k.heavy_every
		return "heavy"
	if d > 140.0 and w.rng.randf() < 0.5:
		return "dash"
	return "sweep"


static func _begin(w: SimWorld, e: SimFighter, id: String, a: Dictionary, state: String) -> void:
	e.state = state
	e.t = 0.0
	e.atk = a
	e.atk_id = id
	e.plan = ""
	e.read = false
	w.emit("cast_start" if state == "cast" else "telegraph", {"id": e.id, "atk": id, "pos": e.pos})


static func _strike(w: SimWorld, e: SimFighter) -> void:
	var a := e.atk
	w.emit("strike", {"id": e.id, "atk": e.atk_id, "pos": e.pos, "dir": e.facing})
	var evaded := false
	var touched := false
	for h in w.heroes():
		if in_zone(a, e.pos, e.facing, h.pos, h.radius):
			touched = true
			if h.inv_t > 0.0:
				evaded = true
			_hit_hero(w, e, h)
	var k: Dictionary = SimData.ENEMIES[e.kind]
	# 看破：预警末段闪避——无论硬闪还是闪出范围——带架势的敌人失衡
	if k.stance and (e.read or evaded) and (evaded or not touched):
		w.stagger(e, k.stance_break)
		return
	_end_attack(w, e)


static func _hit_hero(w: SimWorld, e: SimFighter, h: SimFighter) -> void:
	if h.inv_t > 0.0:
		w.emit("evade", {"id": h.id, "pos": h.pos, "from": e.id})
		return
	w.damage(e, h, e.atk.dmg, {"heavy": e.atk_id != "slash"})


static func _end_attack(w: SimWorld, e: SimFighter) -> void:
	if e.state == "stagger":
		return
	_recover(e)


static func _recover(e: SimFighter) -> void:
	e.state = "recover"
	e.t = 0.0


static func _busy_mates(w: SimWorld, e: SimFighter) -> int:
	var n := 0
	for o in w.foes():
		if o != e and o.kind == e.kind and (o.state == "windup" or o.state == "recover"):
			n += 1
	return n


static func _nearest_hero(w: SimWorld, e: SimFighter) -> SimFighter:
	var best: SimFighter = null
	for h in w.heroes():
		if best == null or h.pos.distance_to(e.pos) < best.pos.distance_to(e.pos):
			best = h
	return best


## 预警区判定：cone 扇形、circle 圆、line 直线冲刺、field 全场读条、quake 全场踏地震（可闪）、spot 落点圆（point 为落点）
static func in_zone(a: Dictionary, origin: Vector2, face: Vector2, p: Vector2, r: float, point := Vector2.INF) -> bool:
	match a.shape:
		"field", "quake":
			return true
		"spot":
			return point != Vector2.INF and point.distance_to(p) <= a.radius + r
		"circle":
			return origin.distance_to(p) <= a.range + r
		"cone":
			return SimWorld._in_cone(origin, face, p, r, a.range, a.half)
		"line":
			var to := p - origin
			var along := to.dot(face)
			return along >= -r and along <= a.range + r and absf(to.cross(face)) <= a.width + r
	return false


## 毒姥（Boss 二，规格书第六节）：本体带毒罩（减伤 95%），不追人，守在出生点附近；
## 开战 10 秒后毒雾从边缘向内压（毒罩被震碎时暂停），阵法 / 合击圈里净化；
## 毒蛊：点一名英雄脚下，0.8 秒红区预警后留毒池 15 秒；摄魂指：读条 1.5 秒，点名定身 3 秒（截脉可解）。
static func _dulao(w: SimWorld, e: SimFighter, k: Dictionary, dt: float) -> void:
	if e.state == "idle":
		e.state = "chase"
	e.in_combat = true
	var ft: float = e.timers.get("fight", 0.0) + dt
	e.timers["fight"] = ft
	if ft >= k.fog_delay:
		if w.fog.is_empty():
			w.fog = {"center": e.home, "r": k.fog_max, "r_max": k.fog_max, "r_min": k.fog_min, "pct": k.fog_pct, "tick": 0.0}
			w.emit("fog_start", {"id": e.id, "pos": e.home})
		# 毒雾一直往里压到只剩中心一小块；毒罩被震碎时暂停，只有阵法 / 合击圈里是净的
		var span: float = w.fog.r_max - w.fog.r_min
		if e.ward_t <= 0.0:
			w.fog.r = maxf(w.fog.r_min, w.fog.r - span / k.fog_shrink * dt)
		# 收口：压到最小圈后一直没人破罩，最后一圈也吞掉；破一次罩就重新计时
		if e.ward_t > 0.0:
			e.timers["fog_min_t"] = 0.0
		elif w.fog.r <= w.fog.r_min + 0.5 or w.fog.get("closing", false):
			e.timers["fog_min_t"] = e.timers.get("fog_min_t", 0.0) + dt
			if e.timers.fog_min_t >= k.fog_close_after:
				if not w.fog.get("closing", false):
					w.fog["closing"] = true
					w.emit("fog_close", {"id": e.id})
				w.fog.r = maxf(0.0, w.fog.r - k.fog_min / k.fog_close_time * dt)
				w.fog.r_min = minf(w.fog.r_min, w.fog.r)
	match e.state:
		"flinch":
			e.t += dt
			if e.t >= 0.18:
				e.state = "chase"
		"stagger":
			if e.stagger_t <= 0.0:
				e.state = "chase"
		"chase":
			var to_home := e.home - e.pos
			if to_home.length() > 30.0 and e.root_t <= 0.0:
				w._move(e, to_home.normalized() * e.speed * dt)
				e.moving = true
			e.timers["gu"] = e.timers.get("gu", 2.0) - dt
			e.timers["soul"] = e.timers.get("soul", 7.0) - dt
			var targets := w.heroes()
			if targets.is_empty():
				return
			var tgt: SimFighter = targets[w.rng.randi_range(0, targets.size() - 1)]
			e.facing = (tgt.pos - e.pos).normalized()
			if e.timers.soul <= 0.0:
				e.timers["soul"] = k.soul_every
				e.target_id = tgt.id
				_begin(w, e, "soul", k.attacks.soul, "cast")
			elif e.timers.gu <= 0.0:
				e.timers["gu"] = k.gu_every
				e.aim_point = tgt.pos + Vector2(w.rng.randf_range(-24.0, 24.0), w.rng.randf_range(-16.0, 16.0))
				_begin(w, e, "gu", k.attacks.gu, "windup")
		"windup":
			e.t += dt
			if e.t >= e.atk.tele:
				w.pools.append({"owner": e.id, "team": SimFighter.FOES, "pos": e.aim_point, "radius": e.atk.radius,
					"t": e.atk.pool_time, "dps": e.atk.pool_dps, "slow": 0.0, "tick": 0.0, "skill": "gu"})
				w.emit("strike", {"id": e.id, "atk": "gu", "pos": e.aim_point, "dir": e.facing})
				_recover(e)
		"cast":
			e.t += dt
			if e.t >= e.atk.cast:
				var victim := w.fighter(e.target_id)
				if victim and victim.alive:
					victim.root_t = maxf(victim.root_t, e.atk.root)
					w.emit("rooted", {"id": victim.id, "pos": victim.pos, "by": e.id})
				_recover(e)
		"recover":
			e.t += dt
			if e.t >= e.atk.get("rec", 0.5):
				e.state = "chase"
				e.atk = {}
				e.atk_id = ""


## 铁甲金刚（Boss 三，规格书第六节）：慢步逼近最近的人；铁甲减伤由世界按裂口结算。
## 冲撞：每 25 秒一次，朝弩车（没拼好就朝最近的人）预警 2.5 秒后直冲，撞上弩车扣 1 耐久；
##   预警期间合击 / 阵法成立就被撞偏（SimWorld.deflect_charges）。
## 踏地震：全场冲击波，0.8 秒预警，翻滚 / 梯云纵的无敌时间能躲。
## 抓人：抓最近的、不在弩车上的人，往弩车扔；落点砸在弩车上扣 1 耐久。
static func _jingang(w: SimWorld, e: SimFighter, k: Dictionary, dt: float) -> void:
	if e.state == "idle":
		e.state = "chase"
	e.in_combat = true
	# 狂暴：开战太久还没打下来，踏地震变密、变重
	e.timers["fight"] = e.timers.get("fight", 0.0) + dt
	if e.timers.fight >= k.enrage_at and not e.timers.get("enraged", false):
		e.timers["enraged"] = true
		e.timers["quake"] = minf(e.timers.get("quake", 0.0), 1.0)
		w.emit("enrage", {"id": e.id, "pos": e.pos})
	# 计时不论在做什么都走（失衡、收招时也走），到点了等回到追击再出手：冲撞稳定每 25 秒一次
	for key in ["charge", "quake", "grab"]:
		e.timers[key] = float(e.timers.get(key, {"charge": k.first_charge, "quake": 6.0, "grab": 10.0}[key])) - dt
	match e.state:
		"stagger":
			if e.stagger_t <= 0.0:
				e.state = "chase"
		"chase":
			# 追最近的、不在弩车上的人（小说里它追净心）；只剩操弩者时才去找车上的人
			var target := _grab_target(w, e)
			if target == null:
				target = _nearest_hero(w, e)
			if target == null:
				return
			var b := w.ballista
			if e.timers.charge <= 0.0:
				e.timers["charge"] = k.charge_every
				var at: Vector2 = b.center if not b.is_empty() and b.built else target.pos
				e.facing = (at - e.pos).normalized()
				e.aim_point = at
				e.timers["dash_len"] = clampf(e.pos.distance_to(at) + 30.0, 120.0, k.attacks.charge.range)
				_begin(w, e, "charge", k.attacks.charge, "windup")
				return
			if e.timers.quake <= 0.0:
				e.timers["quake"] = k.enrage_quake_every if e.timers.get("enraged", false) else k.quake_every
				_begin(w, e, "quake", k.attacks.quake, "windup")
				return
			var victim := _grab_target(w, e)
			var goal := target
			if e.timers.grab <= 0.0 and victim:
				goal = victim
				if victim.pos.distance_to(e.pos) <= k.attacks.grab.range + victim.radius:
					e.timers["grab"] = k.grab_every
					e.target_id = victim.id
					e.facing = (victim.pos - e.pos).normalized()
					_begin(w, e, "grab", k.attacks.grab, "windup")
					return
			var to := goal.pos - e.pos
			e.facing = to.normalized()
			if to.length() > e.radius + goal.radius + 20.0 and e.root_t <= 0.0:
				w._move(e, w.steer(e.pos, goal.pos) * e.speed * (1.0 - e.slow) * dt)
				e.moving = true
		"windup":
			e.t += dt
			if e.t < e.atk.tele:
				return
			match e.atk_id:
				"charge":
					e.state = "dash"
					e.t = 0.0
					e.timers["hit_ids"] = []
					w.emit("strike", {"id": e.id, "atk": "charge", "pos": e.pos, "dir": e.facing})
				"quake":
					w.emit("quake", {"id": e.id, "pos": e.pos})
					var mult: float = k.enrage_mult if e.timers.get("enraged", false) else 1.0
					for h in w.heroes():
						if h.inv_t > 0.0:
							w.emit("evade", {"id": h.id, "pos": h.pos, "from": e.id})
						else:
							w.damage(e, h, e.atk.dmg * mult, {"heavy": true})
					_recover(e)
				"grab":
					_grab(w, e)
					_recover(e)
		"dash":
			e.t += dt
			w._move(e, e.facing * float(e.timers.dash_len) / e.atk.dash_time * dt)
			var hit_ids: Array = e.timers.hit_ids
			for h in w.heroes():
				if not (h.id in hit_ids) and h.pos.distance_to(e.pos) < e.radius + h.radius + 6.0:
					hit_ids.append(h.id)
					_hit_hero(w, e, h)
			var b := w.ballista
			if not b.is_empty() and b.built and e.pos.distance_to(b.center) < e.radius + 28.0:
				SimBallista.damage(w, "charge")
				_recover(e)
			elif e.t >= e.atk.dash_time:
				_recover(e)
		"recover":
			e.t += dt
			if e.t >= e.atk.get("rec", 0.5):
				e.state = "chase"
				e.atk = {}
				e.atk_id = ""


## 抓人的目标：最近的、不在弩车上的英雄
static func _grab_target(w: SimWorld, e: SimFighter) -> SimFighter:
	var best: SimFighter = null
	for h in w.heroes():
		if h.state == "mounted":
			continue
		if best == null or h.pos.distance_to(e.pos) < best.pos.distance_to(e.pos):
			best = h
	return best


## 抓住就往弩车扔（没拼好就往外甩）；闪掉了或已经跑出范围就落空
static func _grab(w: SimWorld, e: SimFighter) -> void:
	var a := e.atk
	var v := w.fighter(e.target_id)
	if v == null or not v.alive or v.state == "mounted" or v.pos.distance_to(e.pos) > a.range + v.radius:
		w.emit("grab_miss", {"id": e.id, "pos": e.pos})
		return
	if v.inv_t > 0.0:
		w.emit("evade", {"id": v.id, "pos": v.pos, "from": e.id})
		return
	w.damage(e, v, a.dmg, {"heavy": true})
	if not v.alive:
		return
	var b := w.ballista
	var dir := (v.pos - e.pos).normalized()
	var dist: float = a.throw
	if not b.is_empty() and b.built:
		dir = (b.center - v.pos).normalized()
		dist = minf(a.throw, v.pos.distance_to(b.center))
	if v.state == "build":
		SimBallista.cancel_build(w, v, "grab")
	v.state = "thrown"
	v.active_skill = ""
	v.dodge_dir = dir
	v.dodge_t = 0.45
	v.timers["throw_v"] = dist / 0.45
	w.emit("grab", {"id": e.id, "victim": v.id, "pos": v.pos, "dir": dir})

