## 战斗世界：每帧吃各英雄的 SimCommand 推进，不依赖场景树，浏览器、Node 测试式的无界面测试、
## 以后的联机服务端跑的是同一份。画面只读状态和 events，不改世界。
class_name SimWorld
extends RefCounted

const P := SimData.PLAYER

var fighters: Array[SimFighter] = []
var projectiles: Array = []   # {owner, pos, vel, life, dmg, hit}
var pools: Array = []         # {owner, pos, radius, t, dps, slow, tick}
var interactables: Array = [] # {id, kind, pos, on}
var events: Array = []        # 给画面 / 剧情的一次性事件，消费方读完自己清空
var time := 0.0
var freeze_t := 0.0           # 合击成立定格，期间世界不动
var bounds := PackedVector2Array()  # 可走区域多边形；空 = 不限制
var rng := RandomNumberGenerator.new()
var combo: SimCombo
var _next_id := 1


func _init(seed_value := 1) -> void:
	rng.seed = seed_value
	combo = SimCombo.new(self)


# ---------- 建角色 ----------

func add_hero(kind: String, sect: String, utility: String, at: Vector2) -> SimFighter:
	var f := SimFighter.new()
	f.id = _take_id()
	f.kind = kind
	f.team = SimFighter.HEROES
	f.sect = sect
	f.skills = SimData.SECTS[sect].skills.duplicate()
	f.utility = utility
	f.name = "净心" if kind == "partner" else "你"
	f.pos = at
	f.radius = P.radius
	f.speed = P.speed
	f.max_hp = SimData.PARTNER.hp if kind == "partner" else P.hp
	f.hp = f.max_hp
	f.max_qi = P.qi
	f.qi = f.max_qi
	f.sp = P.sp
	f.dmg_scale = SimData.PARTNER.dmg_scale if kind == "partner" else 1.0
	fighters.append(f)
	return f


func add_enemy(kind: String, at: Vector2, waiting := false) -> SimFighter:
	var k: Dictionary = SimData.ENEMIES[kind]
	var f := SimFighter.new()
	f.id = _take_id()
	f.kind = kind
	f.team = SimFighter.FOES
	f.name = k.name
	f.pos = at
	f.home = at
	f.radius = k.radius
	f.speed = k.speed
	f.max_hp = k.hp
	f.hp = f.max_hp
	f.facing = Vector2.DOWN
	f.state = "wait" if waiting else "idle"
	fighters.append(f)
	return f


func add_interactable(kind: String, at: Vector2) -> Dictionary:
	var it := {"id": _take_id(), "kind": kind, "pos": at, "on": true}
	interactables.append(it)
	return it


func fighter(fid: int) -> SimFighter:
	for f in fighters:
		if f.id == fid:
			return f
	return null


func heroes() -> Array[SimFighter]:
	var out: Array[SimFighter] = []
	for f in fighters:
		if f.is_hero() and f.alive:
			out.append(f)
	return out


func foes() -> Array[SimFighter]:
	var out: Array[SimFighter] = []
	for f in fighters:
		if not f.is_hero() and f.active():
			out.append(f)
	return out


func in_combat() -> bool:
	return foes().any(func(f): return f.in_combat)


func emit(type: String, data := {}) -> void:
	data["type"] = type
	data["time"] = time
	events.append(data)


func _take_id() -> int:
	_next_id += 1
	return _next_id - 1


# ---------- 每帧推进 ----------

func step(dt: float, commands: Dictionary) -> void:
	if freeze_t > 0.0:
		freeze_t -= dt
		if freeze_t <= 0.0:
			combo.on_freeze_end()
		return
	time += dt
	for f in fighters:
		_tick(f, dt)
	_apply_pools(dt)
	for f in fighters:
		if f.is_hero() and f.alive:
			var cmd: SimCommand = commands.get(f.id, SimCommand.new())
			_hero_step(f, cmd, dt)
	for f in fighters:
		if not f.is_hero():
			SimEnemies.step(self, f, dt)
	_step_projectiles(dt)
	combo.step(dt, commands)
	_separate()


func _tick(f: SimFighter, dt: float) -> void:
	for k in f.cooldowns.keys():
		f.cooldowns[k] = maxf(0.0, f.cooldowns[k] - dt)
	f.atk_cd = maxf(0.0, f.atk_cd - dt)
	f.dodge_cd = maxf(0.0, f.dodge_cd - dt)
	f.inv_t = maxf(0.0, f.inv_t - dt)
	f.root_t = maxf(0.0, f.root_t - dt)
	f.stagger_t = maxf(0.0, f.stagger_t - dt)
	f.hurt_t = maxf(0.0, f.hurt_t - dt)
	f.flash_t = maxf(0.0, f.flash_t - dt)
	f.swing_t = maxf(0.0, f.swing_t - dt)
	f.slow = 0.0
	if f.combo_t > 0.0:
		f.combo_t -= dt
		if f.combo_t <= 0.0:
			f.combo_idx = -1
	if f.shield_t > 0.0:
		f.shield_t -= dt
		if f.shield_t <= 0.0:
			f.shield = 0.0
	if f.poison_t > 0.0 and f.active():
		var before := f.poison_t
		f.poison_t = maxf(0.0, f.poison_t - dt)
		# 每 0.5 秒结一次毒伤，免得事件刷屏
		if floori(before / 0.5) != floori(f.poison_t / 0.5):
			damage(fighter(f.poison_owner), f, SimData.PASSIVE.poison_dps * 0.5, {"dot": true})
	if f.is_hero() and f.alive:
		f.sp = minf(P.sp, f.sp + P.sp_regen * dt)
		var regen: float = P.qi_regen_combat if in_combat() else P.qi_regen_idle
		f.qi = minf(f.max_qi, f.qi + regen * dt)


# ---------- 英雄 ----------

func _hero_step(f: SimFighter, cmd: SimCommand, dt: float) -> void:
	if cmd.is_pressed("cancel") and (f.state == "charge" or f.state == "aim"):
		f.state = "idle"
		f.active_skill = ""
		emit("cancel", {"id": f.id})
	if cmd.is_pressed("dodge"):
		_try_dodge(f, cmd)
	if cmd.is_pressed("interact"):
		_interact(f)
	match f.state:
		"dodge":
			_move(f, f.dodge_dir * P.dodge_speed * dt)
			f.dodge_t -= dt
			if f.dodge_t <= 0.0:
				f.state = "idle"
			return
		"skill":
			_skill_sequence(f, dt)
			return
	# 走动：蓄力时减速，被定身不动
	var spd := f.speed * (0.5 if f.state == "charge" else 1.0) * (1.0 - f.slow)
	f.moving = cmd.move.length() > 0.1 and f.root_t <= 0.0
	if f.moving:
		_move(f, cmd.move.limit_length(1.0) * spd * dt)
		if f.state == "idle" or f.state == "attack":
			f.facing = cmd.move.normalized()
	if f.state == "attack" and f.swing_t <= 0.0:
		f.state = "idle"
	if cmd.is_pressed("attack") and (f.state == "idle" or f.state == "attack") and f.atk_cd <= 0.0:
		_attack(f, cmd)
	for i in 3:
		_skill_input(f, f.skills[i], "skill_%d" % (i + 1), cmd, dt)
	if f.utility != "" and cmd.is_pressed("utility") and (f.state == "idle" or f.state == "attack"):
		_begin_skill(f, f.utility, cmd)


func _try_dodge(f: SimFighter, cmd: SimCommand) -> void:
	if f.dodge_cd > 0.0 or f.sp < P.dodge_cost or f.state == "dodge" or f.root_t > 0.0:
		return
	if f.state == "charge" or f.state == "aim" or f.state == "skill":
		f.active_skill = ""
	var dir := cmd.move.normalized() if cmd.move.length() > 0.2 else f.facing
	f.state = "dodge"
	f.dodge_dir = dir
	f.dodge_t = P.dodge_time
	f.inv_t = P.dodge_inv
	f.dodge_cd = P.dodge_cd
	f.sp -= P.dodge_cost
	f.swing_t = 0.0
	emit("dodge", {"id": f.id, "pos": f.pos})
	# V0.4 规则：带架势的敌人出手前 0.5 秒内闪避，算看破这一招
	for e in foes():
		var k: Dictionary = SimData.ENEMIES[e.kind]
		if k.stance and e.state == "windup" and e.t >= e.atk.tele - k.read_window \
				and e.pos.distance_to(f.pos) < e.atk.range + 60.0:
			e.read = true


## 站在 at 能够着的、还亮着的可交互物；没有返回空字典
func interactable_near(at: Vector2) -> Dictionary:
	for it in interactables:
		if it.on and it.pos.distance_to(at) < 44.0:
			return it
	return {}


func _interact(f: SimFighter) -> void:
	var it := interactable_near(f.pos)
	if not it.is_empty():
		it.on = false
		emit("interact", {"id": f.id, "kind": it.kind, "target": it.id, "pos": it.pos})


func _attack(f: SimFighter, cmd: SimCommand) -> void:
	f.combo_idx = (f.combo_idx + 1) % 3 if f.combo_t > 0.0 else 0
	var a: Dictionary = SimData.ATTACKS[f.sect][f.combo_idx]
	f.atk_cd = a.cd
	f.combo_t = P.combo_window
	f.state = "attack"
	f.swing_t = 0.24 if f.combo_idx < 2 else 0.35
	f.swing_kind = "atk%d" % (f.combo_idx + 1)
	f.facing = _auto_aim(f, cmd, a.range + 40.0)
	var n := 0
	for e in foes():
		if _in_cone(f.pos, f.facing, e.pos, e.radius, a.range, a.half):
			n += 1
			damage(f, e, a.dmg, {"heavy": f.combo_idx == 2, "dir": f.facing})
	if n > 0:
		f.qi = minf(f.max_qi, f.qi + P.qi_on_hit)
	emit("swing", {"id": f.id, "combo": f.combo_idx + 1, "hits": n})


func _skill_input(f: SimFighter, skill: String, action: String, cmd: SimCommand, dt: float) -> void:
	var s: Dictionary = SimData.SKILLS[skill]
	if cmd.is_pressed(action) and (f.state == "idle" or f.state == "attack"):
		_begin_skill(f, skill, cmd)
		return
	if f.active_skill != skill:
		return
	if f.state == "charge":
		f.charge_t = minf(s.max_charge, f.charge_t + dt)
		if cmd.aim.length() > 0.2:
			f.aim_dir = cmd.aim.normalized()
			f.facing = f.aim_dir
		if not cmd.is_held(action):
			_cast(f, skill, f.charge_t / s.max_charge)
	elif f.state == "aim":
		if cmd.aim.length() > 0.2:
			f.aim_dir = cmd.aim.normalized()
		f.facing = f.aim_dir
		if s.has("reach"):
			var target: Vector2 = cmd.point if cmd.has_point else f.pos + f.aim_dir * s.reach * 0.7
			var off: Vector2 = (target - f.pos).limit_length(s.reach)
			f.aim_point = f.pos + off
			if off.length() > 4.0:
				f.aim_dir = off.normalized()
		if not cmd.is_held(action):
			_cast(f, skill, 1.0)


func _begin_skill(f: SimFighter, skill: String, cmd: SimCommand) -> void:
	var s: Dictionary = SimData.SKILLS[skill]
	if f.cd_of(skill) > 0.0:
		emit("deny", {"id": f.id, "skill": skill, "why": "cd"})
		return
	if f.qi < s.cost:
		emit("deny", {"id": f.id, "skill": skill, "why": "qi"})
		return
	match s.mode:
		"tap":
			f.facing = _auto_aim(f, cmd, s.get("range", 120.0) + 40.0)
			_cast(f, skill, 1.0)
		"charge":
			f.state = "charge"
			f.active_skill = skill
			f.charge_t = 0.0
			f.aim_dir = _auto_aim(f, cmd, s.get("range", 120.0) + 40.0)
		"aim":
			f.state = "aim"
			f.active_skill = skill
			f.aim_dir = _auto_aim(f, cmd, s.get("range", s.get("reach", 120.0)) + 40.0)
			f.aim_point = f.pos + f.aim_dir * s.get("reach", 0.0) * 0.7


## 出招。charge 为蓄力比例（0–1），非蓄力招式为 1。free 为合击落空后的退化招式：不耗内力、不进冷却。
func cast_skill(f: SimFighter, skill: String, charge := 1.0, free := false) -> void:
	_cast(f, skill, charge, free)


func _cast(f: SimFighter, skill: String, charge: float, free := false) -> void:
	var s: Dictionary = SimData.SKILLS[skill]
	if not free:
		f.qi -= s.cost
		f.cooldowns[skill] = s.cd
	f.state = "idle"
	f.active_skill = ""
	f.swing_t = 0.3
	f.swing_kind = skill
	var opts := {"skill": true, "dir": f.facing, "skill_id": skill}
	if f.primed and s.sect != "":
		opts["stagger"] = SimData.PASSIVE.shaolin_stagger
		f.primed = false
		f.passive_fill = 0.0
		emit("primed_used", {"id": f.id})
	emit("skill", {"id": f.id, "skill": skill, "pos": f.pos, "dir": f.facing, "charge": charge})
	match skill:
		"luohanquan":
			f.state = "skill"
			f.active_skill = skill
			f.skill_hits_left = s.hits
			f.skill_hit_t = 0.0
			f.set_meta("skill_opts", opts)
			_move(f, f.facing * s.lunge)
		"jinzhongzhao":
			f.shield = lerpf(s.shield_min, s.shield_max, charge)
			f.shield_t = s.shield_time
		"dalijingangzhang":
			f.facing = f.aim_dir
			opts["dir"] = f.aim_dir
			opts["knockback"] = s.knockback
			opts["heavy"] = true
			for e in foes():
				if _in_cone(f.pos, f.aim_dir, e.pos, e.radius, s.range, s.half):
					damage(f, e, s.dmg, opts)
		"dushazhang":
			projectiles.append({"owner": f.id, "pos": f.pos + f.facing * 14.0, "vel": f.facing * s.speed,
				"life": s.range / s.speed, "dmg": s.dmg, "hit": [], "skill": skill, "opts": opts})
		"huagongsan":
			pools.append({"owner": f.id, "pos": f.aim_point, "radius": s.radius, "t": s.time,
				"dps": s.dps, "slow": s.slow, "tick": 0.0, "skill": skill})
		"shehunshu":
			f.facing = f.aim_dir
			var target := _first_in_line(f.pos, f.aim_dir, s.range, s.width)
			if target:
				opts["root"] = s.root if charge >= 0.95 else 0.0
				damage(f, target, s.dmg * (0.5 + 0.5 * charge), opts)
				emit("beam", {"id": f.id, "from": f.pos, "to": target.pos})
			else:
				emit("beam", {"id": f.id, "from": f.pos, "to": f.pos + f.aim_dir * s.range})
		"tiyunzong":
			var dir := f.facing
			var from := f.pos
			for i in 11:
				_move(f, dir * s.blink / 11.0)
			f.inv_t = maxf(f.inv_t, s.inv)
			emit("blink", {"id": f.id, "from": from, "to": f.pos})
		"yungong":
			heal(f, s.heal)
			for h in heroes():
				if h != f and h.pos.distance_to(f.pos) <= s.share_range:
					heal(h, s.share_heal)
					h.qi = minf(h.max_qi, h.qi + s.share_qi)
					emit("share", {"from": f.id, "to": h.id})
		"jiemai":
			var target := _jiemai_target(f, s.range)
			if target:
				f.facing = (target.pos - f.pos).normalized()
				opts["interrupt"] = true
				damage(f, target, s.dmg, opts)


func _skill_sequence(f: SimFighter, dt: float) -> void:
	var s: Dictionary = SimData.SKILLS[f.active_skill]
	f.skill_hit_t -= dt
	if f.skill_hit_t > 0.0:
		return
	if f.skill_hits_left <= 0:
		f.state = "idle"
		f.active_skill = ""
		return
	f.skill_hits_left -= 1
	f.skill_hit_t = s.interval
	var opts: Dictionary = f.get_meta("skill_opts", {"skill": true})
	opts["heavy"] = f.skill_hits_left == 0
	f.swing_t = 0.12
	for e in foes():
		if _in_cone(f.pos, f.facing, e.pos, e.radius, s.range, s.half):
			damage(f, e, s.dmg, opts)
	emit("punch", {"id": f.id, "n": s.hits - f.skill_hits_left})
	opts.erase("stagger")  # 积内力的硬直只给第一拳
	f.set_meta("skill_opts", opts)


func heal(f: SimFighter, amount: float) -> void:
	var before := f.hp
	f.hp = minf(f.max_hp, f.hp + amount)
	emit("heal", {"id": f.id, "pos": f.pos, "amount": roundi(f.hp - before)})


# ---------- 伤害、打断、失衡 ----------

## 结算一次伤害。opts：skill 招式（不吃架势减半）、heavy 重击反馈、dir 方向、knockback 击退、
## interrupt 能打断读条（截脉 / 合击）、stagger 附带硬直、root 定身、dot 持续伤害、unavoidable 闪避也躲不开。
func damage(src: SimFighter, target: SimFighter, amount: float, opts := {}) -> float:
	if target == null or not target.active():
		return 0.0
	if target.inv_t > 0.0 and not opts.get("unavoidable", false) and not opts.get("dot", false):
		emit("evade", {"id": target.id, "pos": target.pos})
		return 0.0
	var amt := amount * (src.dmg_scale if src else 1.0)
	var k: Dictionary = SimData.ENEMIES.get(target.kind, {})
	var guarded: bool = k.get("stance", false) and target.state != "stagger" and not opts.get("skill", false) and not opts.get("dot", false)
	if guarded:
		amt *= k.stance_cut
	if target.shield > 0.0:
		var absorbed := minf(target.shield, amt)
		target.shield -= absorbed
		amt -= absorbed
		if absorbed > 0.0:
			emit("shield_hit", {"id": target.id, "pos": target.pos})
	target.hp -= amt
	target.flash_t = 0.12
	emit("hit", {"id": target.id, "src": src.id if src else -1, "pos": target.pos, "amount": roundi(amt),
		"heavy": opts.get("heavy", false) or opts.get("skill", false), "guarded": guarded,
		"dot": opts.get("dot", false), "dir": opts.get("dir", Vector2.ZERO)})
	if target.is_hero():
		_hero_hurt(target, amt, src)
	else:
		_foe_hurt(src, target, opts)
	if opts.get("knockback", 0.0) > 0.0 and src and target.active() and not k.get("stance", false):
		_move(target, (target.pos - src.pos).normalized() * opts.knockback)
	if target.hp <= 0.0:
		_down(target)
	return amt


func _hero_hurt(f: SimFighter, amt: float, src: SimFighter) -> void:
	f.hurt_t = 0.25
	if f.state == "charge":  # 金钟罩、摄魂术蓄力会被打断
		f.state = "idle"
		f.active_skill = ""
		emit("charge_broken", {"id": f.id})
	if src and amt > 0.0:
		_move(f, (f.pos - src.pos).normalized() * P.hurt_knockback)
	if f.sect == "shaolin" and not f.primed:
		f.passive_fill += amt
		if f.passive_fill >= SimData.PASSIVE.shaolin_fill:
			f.primed = true
			emit("primed", {"id": f.id})
	combo.on_hero_hit(f, amt)


func _foe_hurt(src: SimFighter, e: SimFighter, opts: Dictionary) -> void:
	var k: Dictionary = SimData.ENEMIES[e.kind]
	e.in_combat = true
	if e.state == "idle":
		e.state = "chase"
	if src and src.is_hero() and src.sect == "xiepai" and not opts.get("dot", false):
		e.poison_stacks += 1
		if e.poison_stacks >= SimData.PASSIVE.poison_stacks:
			e.poison_stacks = 0
			e.poison_t = SimData.PASSIVE.poison_time
			e.poison_owner = src.id
			emit("poison_burst", {"id": e.id, "pos": e.pos})
	if opts.get("root", 0.0) > 0.0:
		e.root_t = maxf(e.root_t, opts.root)
		emit("rooted", {"id": e.id, "pos": e.pos})
	var interrupting: bool = opts.get("interrupt", false)
	# 喽啰的出刀预兆，任何招式都能打断；玄诚只认截脉与合击
	if not k.stance and opts.get("skill", false) and e.state == "windup":
		interrupting = true
	if interrupting and (e.state == "windup" or e.state == "cast"):
		interrupt(e, src)
	elif opts.get("stagger", 0.0) > 0.0:
		stagger(e, opts.stagger)
	elif k.flinch and e.state != "windup" and e.state != "dash" and e.state != "stagger":
		e.state = "flinch"
		e.t = 0.0


func interrupt(e: SimFighter, src: SimFighter) -> void:
	var k: Dictionary = SimData.ENEMIES[e.kind]
	emit("interrupt", {"id": e.id, "pos": e.pos, "by": src.id if src else -1, "was": e.atk_id})
	if k.stance:
		stagger(e, k.stance_break)
	else:
		e.state = "flinch"
		e.t = 0.0
		e.atk = {}
		e.atk_id = ""


## 失衡：带架势的敌人此时吃满普攻伤害（V0.4 规则）
func stagger(e: SimFighter, secs: float) -> void:
	e.state = "stagger"
	e.stagger_t = maxf(e.stagger_t, secs)
	e.atk = {}
	e.atk_id = ""
	e.plan = ""
	emit("stagger", {"id": e.id, "pos": e.pos, "secs": secs})


func _down(f: SimFighter) -> void:
	f.hp = 0.0
	if f.kind == "xuancheng":
		f.state = "sit"
		f.atk = {}
		emit("boss_sit", {"id": f.id, "pos": f.pos})
	else:
		f.alive = false
		f.state = "dead"
		emit("hero_down" if f.is_hero() else "kill", {"id": f.id, "pos": f.pos})


# ---------- 飞行物、毒池 ----------

func _step_projectiles(dt: float) -> void:
	for pr in projectiles:
		pr.life -= dt
		pr.pos += pr.vel * dt
		if not _inside(pr.pos):
			pr.life = 0.0
			continue
		for e in foes():
			if e.id in pr.hit or e.pos.distance_to(pr.pos) > e.radius + 8.0:
				continue
			pr.hit.append(e.id)
			pr.life = 0.0
			damage(fighter(pr.owner), e, pr.dmg, pr.opts)
			break
	projectiles = projectiles.filter(func(pr): return pr.life > 0.0)


func _apply_pools(dt: float) -> void:
	for pool in pools:
		pool.t -= dt
		pool.tick += dt
		var ticking: bool = pool.tick >= 0.5
		if ticking:
			pool.tick -= 0.5
		for e in foes():
			if e.pos.distance_to(pool.pos) <= pool.radius + e.radius:
				e.slow = maxf(e.slow, pool.slow)
				if ticking:
					damage(fighter(pool.owner), e, pool.dps * 0.5, {"dot": true})
	pools = pools.filter(func(p): return p.t > 0.0)


# ---------- 几何与移动 ----------

func _move(f: SimFighter, delta: Vector2) -> void:
	if delta == Vector2.ZERO:
		return
	var to := f.pos + delta
	if _inside(to):
		f.pos = to
	elif _inside(Vector2(to.x, f.pos.y)):
		f.pos.x = to.x
	elif _inside(Vector2(f.pos.x, to.y)):
		f.pos.y = to.y


func _inside(p: Vector2) -> bool:
	return bounds.is_empty() or Geometry2D.is_point_in_polygon(p, bounds)


func _separate() -> void:
	var live := fighters.filter(func(f): return f.alive and f.state != "dodge")
	for i in live.size():
		for j in range(i + 1, live.size()):
			var a: SimFighter = live[i]
			var b: SimFighter = live[j]
			var d := a.pos.distance_to(b.pos)
			var need := a.radius + b.radius
			if d < need and d > 0.01:
				var push := (b.pos - a.pos) / d * (need - d) * 0.5
				_move(a, -push)
				_move(b, push)


static func _in_cone(origin: Vector2, dir: Vector2, p: Vector2, r: float, rng_: float, half: float) -> bool:
	var to := p - origin
	var d := to.length()
	if d > rng_ + r:
		return false
	return d <= r or absf(dir.angle_to(to)) <= half


func _first_in_line(origin: Vector2, dir: Vector2, length: float, width: float) -> SimFighter:
	var best: SimFighter = null
	var best_d := INF
	for e in foes():
		var to := e.pos - origin
		var along := to.dot(dir)
		var across := absf(to.cross(dir))
		if along >= -e.radius and along <= length + e.radius and across <= width + e.radius and along < best_d:
			best = e
			best_d = along
	return best


## 自动朝向：给了瞄准方向就用；否则找射程内最近的敌人；再否则按当前面向。
func _auto_aim(f: SimFighter, cmd: SimCommand, reach: float) -> Vector2:
	if cmd.aim.length() > 0.2:
		return cmd.aim.normalized()
	var best: SimFighter = null
	for e in foes():
		var d := e.pos.distance_to(f.pos)
		if d <= reach and (best == null or d < best.pos.distance_to(f.pos)):
			best = e
	return (best.pos - f.pos).normalized() if best else f.facing


## 截脉优先打正在读条 / 出招预兆的敌人
func _jiemai_target(f: SimFighter, reach: float) -> SimFighter:
	var best: SimFighter = null
	var best_score := INF
	for e in foes():
		var d := e.pos.distance_to(f.pos)
		if d > reach + e.radius:
			continue
		var score := d - (1000.0 if e.state == "cast" or e.state == "windup" else 0.0)
		if score < best_score:
			best = e
			best_score = score
	return best
