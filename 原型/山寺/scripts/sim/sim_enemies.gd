## 敌人行为：喽啰与玄诚。状态机沿用 V0.4：追击 → 预警（红区）→ 出手 → 收招；
## 玄诚带架势，阶段二（半血）加入两秒读条的重击，必须用截脉或合击打断，否则全场重伤。
class_name SimEnemies
extends RefCounted


static func step(w: SimWorld, e: SimFighter, dt: float) -> void:
	e.moving = false
	if not e.alive or e.state == "sit" or e.state == "wait" or e.state == "dead":
		return
	var k: Dictionary = SimData.ENEMIES[e.kind]
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


## 预警区判定：cone 扇形、circle 圆、line 直线冲刺、field 全场
static func in_zone(a: Dictionary, origin: Vector2, face: Vector2, p: Vector2, r: float) -> bool:
	match a.shape:
		"field":
			return true
		"circle":
			return origin.distance_to(p) <= a.range + r
		"cone":
			return SimWorld._in_cone(origin, face, p, r, a.range, a.half)
		"line":
			var to := p - origin
			var along := to.dot(face)
			return along >= -r and along <= a.range + r and absf(to.cross(face)) <= a.width + r
	return false
