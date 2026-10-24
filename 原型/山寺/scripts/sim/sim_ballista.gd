## 弩车（规格书第八节机关术）：零件、拼装、上下车、蓄力发射、裂口、耐久与散架。
## 状态全在 SimWorld.ballista / parts / pile_parts 里，只有这里改它们：以后联机由服务端跑这一份，
## 客户端只读。谁拼、谁坐都一样——任何英雄（真人、AI、以后的联机玩家）都只通过 SimCommand 操作。
##   零件：可破坏物打碎后掉在地上，走过去自动拿起（每人一格零件位，不进物品栏），带到中央自动装上
##   拼装：三样装齐后在中央按互动，读条 3 秒；走动、闪避、出手、挨打都会打断
##   上下车：拼好后按互动上车（不能走动）、再按下车；车上按闪避是跳车翻滚
##   发射：按住普攻蓄力、松开发射，三档；弩箭打在铁甲上留下裂口，裂口处的伤害不吃铁甲减免
##   耐久 3：被冲撞或被扔过来的人砸中扣 1，扣完散架，三样零件随机散到场边
class_name SimBallista
extends RefCounted

const B := SimData.BALLISTA
const SEAT := Vector2(0, 18)     # 操弩者坐在弩车后方（画面下方）
const MAX_BREACHES := 3


## 关卡调用：在 center 摆弩车底座；spots 是散架后零件可能落到的位置（至少三处）
static func setup(w: SimWorld, center: Vector2, spots: Array) -> void:
	w.ballista = {"center": center, "installed": [], "built": false, "hp": 0, "rider": -1,
		"build_by": -1, "build_t": 0.0, "charge_t": 0.0, "charging": false, "aim": Vector2.UP,
		"spots": spots.duplicate(), "shots": 0, "breaks": 0}


## 指定某个零件堆打碎后掉哪样零件
static func bind_pile(w: SimWorld, pile: SimFighter, part: String) -> void:
	w.pile_parts[pile.id] = part


static func spawn_part(w: SimWorld, part: String, at: Vector2) -> Dictionary:
	var p := {"id": w._take_id(), "part": part, "pos": at, "carrier": -1}
	w.parts.append(p)
	w.emit("part_drop", {"part": part, "pos": at})
	return p


## 英雄身上背着的零件；没有返回空字典
static func carried(w: SimWorld, f: SimFighter) -> Dictionary:
	for p in w.parts:
		if p.carrier == f.id:
			return p
	return {}


static func seat(w: SimWorld) -> Vector2:
	return w.ballista.center + SEAT


static func charge_tier(charge_t: float) -> int:
	return 0 if charge_t < B.charge_steps[0] else (1 if charge_t < B.charge_steps[1] else 2)


## 可破坏物碎了：掉关卡指定的零件，以及掉落表里按 part_chance 掷出的零件
static func on_destroyed(w: SimWorld, e: SimFighter, rolled: Array) -> void:
	if w.ballista.is_empty():
		return
	var list := rolled.duplicate()
	if w.pile_parts.has(e.id):
		list.append(w.pile_parts[e.id])
		w.pile_parts.erase(e.id)
	for i in list.size():
		spawn_part(w, list[i], w._drop_spot(e.pos + Vector2(0, 14), i + 1))


# ---------- 每帧 ----------

## 英雄这一帧和弩车有关的操作；返回真表示这一帧被弩车占用（在车上、拼装中），世界不再处理走动和出手
static func hero_step(w: SimWorld, f: SimFighter, cmd: SimCommand, dt: float) -> bool:
	var b := w.ballista
	if f.state == "mounted":
		if b.rider != f.id:
			f.state = "idle"
			return false
		if cmd.is_pressed("interact") or cmd.is_pressed("dodge"):
			dismount(w, f)
			cmd.pressed.erase("interact")
			return false  # 闪避照常处理：跳车翻滚
		f.pos = seat(w)
		if cmd.aim.length() > 0.2:
			b.aim = cmd.aim.normalized()
		elif not b.charging:
			var t := _auto_target(w, b.center)
			if t:
				b.aim = (t.pos - b.center).normalized()
		f.facing = b.aim
		if cmd.is_held("attack"):
			if not b.charging:
				b.charging = true
				b.charge_t = 0.0
				w.emit("ballista_charge", {"id": f.id})
			b.charge_t = minf(B.max_charge, b.charge_t + dt)
		elif b.charging:
			fire(w, f)
		return true
	if f.state == "build":
		if b.build_by != f.id:
			f.state = "idle"
			return false
		if cmd.move.length() > 0.1 or cmd.is_pressed("dodge") or cmd.is_pressed("attack") or cmd.is_pressed("cancel"):
			cancel_build(w, f, "moved")
			return false
		b.build_t += dt
		if b.build_t >= B.build_time:
			_finish_build(w, f)
		return true
	if cmd.is_pressed("interact") and f.pos.distance_to(b.center) <= B.reach and f.state != "dodge" and f.state != "thrown":
		if not b.built and b.installed.size() < B.parts.size():
			# 零件不齐：提示一下，互动键留给身边别的东西（掉落、箱子）
			w.emit("deny", {"id": f.id, "skill": "ballista", "why": "parts", "have": b.installed.size()})
			return false
		cmd.pressed.erase("interact")
		if b.built:
			var rider := w.fighter(b.rider)
			if rider and rider.kind != "player" and f.kind == "player":
				dismount(w, rider)  # 真人要上车：AI 让座
			if b.rider == -1:
				mount(w, f)
		elif b.installed.size() == B.parts.size() and b.build_by == -1:
			f.state = "build"
			f.moving = false
			b.build_by = f.id
			b.build_t = 0.0
			w.emit("build_start", {"id": f.id})
		return f.state == "mounted" or f.state == "build"
	return false


## 世界每帧调用：零件跟着背的人走、碰到就拿、带到中央就装；倒下的人丢下零件、跳下弩车；裂口计时
static func step(w: SimWorld, dt: float) -> void:
	var b := w.ballista
	for p in w.parts:
		if p.carrier == -1:
			continue
		var c := w.fighter(p.carrier)
		if c == null or not c.alive:
			p.carrier = -1
			w.emit("part_drop", {"part": p.part, "pos": p.pos})
		else:
			p.pos = c.pos
	var rider := w.fighter(b.rider)
	if b.rider != -1 and (rider == null or not rider.alive):
		b.rider = -1
		b.charging = false
	for h in w.heroes():
		if h.state == "mounted" or h.state == "build" or h.state == "thrown":
			continue
		var mine := carried(w, h)
		if mine.is_empty():
			for p in w.parts:
				if p.carrier == -1 and p.pos.distance_to(h.pos) <= B.carry_reach + h.radius:
					p.carrier = h.id
					w.emit("part_pickup", {"id": h.id, "part": p.part, "pos": p.pos})
					break
		elif not b.built and h.pos.distance_to(b.center) <= B.reach and not (mine.part in b.installed):
			b.installed.append(mine.part)
			w.parts.erase(mine)
			w.emit("part_install", {"id": h.id, "part": mine.part, "have": b.installed.size()})
	for e in w.foes():
		if e.breaches.is_empty():
			continue
		for br in e.breaches:
			br.t -= dt
		e.breaches = e.breaches.filter(func(br): return br.t > 0.0)


# ---------- 拼装、上下车、发射 ----------

static func cancel_build(w: SimWorld, f: SimFighter, why: String) -> void:
	var b := w.ballista
	if b.build_by == f.id:
		b.build_by = -1
		b.build_t = 0.0
	if f.state == "build":
		f.state = "idle"
	w.emit("build_broken", {"id": f.id, "why": why})


static func _finish_build(w: SimWorld, f: SimFighter) -> void:
	var b := w.ballista
	b.built = true
	b.hp = B.hp
	b.build_by = -1
	b.build_t = 0.0
	f.state = "idle"
	w.emit("ballista_built", {"id": f.id, "pos": b.center})


static func mount(w: SimWorld, f: SimFighter) -> void:
	var b := w.ballista
	b.rider = f.id
	b.charging = false
	b.charge_t = 0.0
	f.state = "mounted"
	f.moving = false
	f.pos = seat(w)
	w.emit("mount", {"id": f.id})


static func dismount(w: SimWorld, f: SimFighter) -> void:
	var b := w.ballista
	if b.rider == f.id:
		b.rider = -1
		b.charging = false
		b.charge_t = 0.0
	if f.state == "mounted":
		f.state = "idle"
	w.emit("dismount", {"id": f.id})


static func fire(w: SimWorld, f: SimFighter) -> void:
	var b := w.ballista
	var tier := charge_tier(b.charge_t)
	b.charging = false
	b.charge_t = 0.0
	b.shots += 1
	var dir: Vector2 = b.aim
	w.projectiles.append({"owner": f.id, "pos": b.center + dir * 20.0, "vel": dir * B.bolt_speed,
		"life": B.bolt_range / B.bolt_speed, "dmg": B.bolt_dmg[tier], "hit": [], "skill": "bolt", "bolt": tier,
		"opts": {"bolt": tier, "skill": true, "heavy": true, "dir": dir}})
	w.emit("bolt_fire", {"id": f.id, "pos": b.center, "dir": dir, "tier": tier})


## 车上没给瞄准方向：自动朝带铁甲的敌人（没有就最近的敌人）
static func _auto_target(w: SimWorld, from: Vector2) -> SimFighter:
	var best: SimFighter = null
	for e in w.foes():
		var k: Dictionary = SimData.ENEMIES[e.kind]
		if k.get("prop", false):
			continue
		if best == null or k.has("armor_cut") or e.pos.distance_to(from) < best.pos.distance_to(from):
			best = e
			if k.has("armor_cut"):
				break
	return best


# ---------- 裂口与铁甲 ----------

## 打在 target 身上的那一点：从 from 方向看过去的体表
static func hit_point(target: SimFighter, from: Vector2) -> Vector2:
	var to := from - target.pos
	return target.pos if to.length() < 0.5 else target.pos + to.normalized() * target.radius


## 弩箭命中：在命中点留一道裂口（相对本体的位置，跟着本体走），最多三道，多了顶掉最旧的
static func add_breach(w: SimWorld, target: SimFighter, from: Vector2, tier: int) -> void:
	var off := hit_point(target, from) - target.pos
	target.breaches.append({"off": off, "r": B.breach_radius[tier], "t": B.breach_time, "tier": tier})
	if target.breaches.size() > MAX_BREACHES:
		target.breaches.pop_front()
	w.emit("breach", {"id": target.id, "pos": target.pos + off, "tier": tier})


## 从 from 打过来，命中点有没有落在裂口上
static func in_breach(target: SimFighter, from: Vector2) -> bool:
	var p := hit_point(target, from)
	for br in target.breaches:
		if (target.pos + br.off).distance_to(p) <= br.r + 6.0:
			return true
	return false


# ---------- 耐久与散架 ----------

static func damage(w: SimWorld, cause: String) -> void:
	var b := w.ballista
	if b.is_empty() or not b.built:
		return
	b.hp -= 1
	w.emit("ballista_hit", {"cause": cause, "hp": b.hp, "pos": b.center})
	if b.hp <= 0:
		_break_apart(w)


static func _break_apart(w: SimWorld) -> void:
	var b := w.ballista
	var rider := w.fighter(b.rider)
	if rider:
		dismount(w, rider)
	b.built = false
	b.hp = 0
	b.installed = []
	b.breaks += 1
	# 三样零件随机散到场边（洗牌用世界的随机数，联机时各端一致）
	var spots: Array = b.spots.duplicate()
	for i in range(spots.size() - 1, 0, -1):
		var j := w.rng.randi_range(0, i)
		var tmp = spots[i]
		spots[i] = spots[j]
		spots[j] = tmp
	w.emit("ballista_break", {"pos": b.center})
	for i in B.parts.size():
		spawn_part(w, B.parts[i], spots[i % spots.size()])


## 被铁甲金刚扔出去的人落地：落点砸在弩车上就扣耐久
static func on_land(w: SimWorld, f: SimFighter) -> void:
	var b := w.ballista
	if not b.is_empty() and b.built and f.pos.distance_to(b.center) <= 40.0:
		damage(w, "throw")
