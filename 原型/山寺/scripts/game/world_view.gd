## 把 SimWorld 画出来。角色、特效的美术还没交，先用代码画的占位形体（按美术说明的阵营配色）；
## 预警红区、读条、合击光圈、瞄准指示器是正式表现。只读世界，不改世界。
class_name WorldView
extends Node2D

const SKIN := Color("#E8C39E")
const HAIR := Color("#2B2320")
const WOOD := Color("#5A3F29")
const STEEL := Color("#C9C2B2")
const BLOOD_TEXT := Color("#F08A6A")
const TEAL := Color("#7FD0BE")

var world: SimWorld
var me_id := -1
var background: Texture2D
var effects: Array = []        # {kind, pos, t, dur, ...}
var trails := {}               # fighter id -> [{pos, t}]
var hitstop := 0.0             # 由关卡读走：命中停顿
var shake := 0.0


func consume_events() -> void:
	for e in world.events:
		_on_event(e)
	world.events.clear()


func _process(dt: float) -> void:
	for fx in effects:
		fx.t += dt
	effects = effects.filter(func(fx): return fx.t < fx.dur)
	for id in trails.keys():
		var list: Array = trails[id]
		for tr in list:
			tr.t -= dt
		trails[id] = list.filter(func(tr): return tr.t > 0.0)
	if world:
		for f in world.fighters:
			if f.alive and (f.state == "dodge" or f.inv_t > 0.0 and f.is_hero()):
				var list: Array = trails.get(f.id, [])
				if list.is_empty() or list[-1].pos.distance_to(f.pos) > 14.0:
					list.append({"pos": f.pos, "t": 0.22})
					if list.size() > 6:
						list.pop_front()
				trails[f.id] = list
	queue_redraw()


func _fx(kind: String, pos: Vector2, dur: float, extra := {}) -> void:
	var fx := {"kind": kind, "pos": pos, "t": 0.0, "dur": dur}
	fx.merge(extra)
	effects.append(fx)


func _text(pos: Vector2, s: String, color: Color, big := false) -> void:
	_fx("text", pos + Vector2(randf_range(-6, 6), -40), 0.9, {"s": s, "color": color, "big": big})


func _sect_color(f: SimFighter) -> Color:
	return UiKit.PURPLE if f and f.sect == "xiepai" else UiKit.QI


func _on_event(e: Dictionary) -> void:
	var f: SimFighter = world.fighter(e.get("id", -1))
	match e.type:
		"swing":
			_fx("swing", f.pos, 0.16, {"dir": f.facing, "r": SimData.ATTACKS[f.sect][e.combo - 1].range,
				"color": _sect_color(f), "heavy": e.combo == 3, "id": f.id})
		"punch":
			_fx("burst", f.pos + f.facing * 36.0, 0.18, {"color": UiKit.QI, "r": 10.0 + 4.0 * e.n})
			hitstop = maxf(hitstop, 0.03)
		"skill":
			match e.skill:
				"dalijingangzhang":
					_fx("palm", f.pos, 0.35, {"dir": e.dir, "r": SimData.SKILLS.dalijingangzhang.range})
					shake = maxf(shake, 2.0)
				"jinzhongzhao":
					_fx("ring", f.pos + Vector2(0, -16), 0.4, {"color": UiKit.QI, "r": 30.0})
				"yungong":
					_fx("rise", f.pos, 0.8, {"color": UiKit.GOLD_WHITE})
		"hit":
			var hero: bool = f and f.is_hero()
			var col := BLOOD_TEXT if hero else (UiKit.QI if e.heavy else UiKit.TEXT)
			if e.dot:
				col = UiKit.POISON
			elif e.guarded:
				col = UiKit.MUTED
			if e.amount > 0:
				_text(e.pos, ("-%d" % e.amount) + ("（架）" if e.guarded else ""), col, e.heavy)
			if not e.dot:
				_fx("spark", e.pos + Vector2(0, -16), 0.22, {"color": UiKit.GOLD_WHITE if e.heavy else UiKit.TEXT})
				hitstop = maxf(hitstop, 0.1 if e.heavy else 0.05)
				shake = maxf(shake, 2.0 if e.heavy or hero else 1.0)
		"evade":
			_text(e.pos, "闪过", TEAL)
		"interrupt":
			_text(e.pos, "打断！", BLOOD_TEXT, true)
			_fx("ring", e.pos + Vector2(0, -16), 0.35, {"color": Color("#BFE8FF"), "r": 28.0})
			hitstop = maxf(hitstop, 0.12)
		"stagger":
			_text(e.pos + Vector2(0, -16), "失衡！", UiKit.QI, true)
		"kill":
			_fx("burst", e.pos + Vector2(0, -12), 0.4, {"color": UiKit.MUTED, "r": 22.0})
		"poison_burst":
			_fx("burst", e.pos + Vector2(0, -12), 0.4, {"color": UiKit.POISON, "r": 20.0})
			_text(e.pos, "毒发", UiKit.POISON)
		"primed":
			if f:
				_text(f.pos, "内力满：下一招带硬直", UiKit.QI)
		"deny":
			if e.id == me_id:
				_text(f.pos, "内力不足" if e.why == "qi" else "还在冷却", UiKit.MUTED)
		"beam":
			_fx("beam", e.from, 0.25, {"to": e.to})
		"blink":
			_fx("blink", e.from, 0.3, {"to": e.to})
		"heal":
			if e.amount > 0:
				_text(e.pos, "+%d" % e.amount, UiKit.POISON)
		"rooted":
			_text(e.pos, "定身", UiKit.PURPLE)
		"strike":
			if e.atk != "slash":
				shake = maxf(shake, 2.0)
		"heavy_release":
			_fx("shock", e.pos, 0.6, {})
			shake = maxf(shake, 4.0)
			hitstop = maxf(hitstop, 0.15)
		"combo_burst":
			_fx("combo", e.point, 0.6, {"r": e.radius, "level": e.level})
			shake = maxf(shake, 3.0)
		"interact":
			_fx("burst", e.pos + Vector2(0, -26), 0.5, {"color": UiKit.MUTED, "r": 14.0})
		"shield_hit":
			_fx("ring", e.pos + Vector2(0, -16), 0.2, {"color": UiKit.QI, "r": 24.0})


# ---------- 绘制 ----------

func _draw() -> void:
	if world == null:
		return
	if background:
		draw_texture(background, Vector2.ZERO)
	for pool in world.pools:
		_ellipse(pool.pos, pool.radius, Color(UiKit.PURPLE, 0.28))
		_ellipse(pool.pos, pool.radius * 0.7, Color(UiKit.POISON, 0.22))
		_ellipse_line(pool.pos, pool.radius, Color(UiKit.DARK_PURPLE, 0.9))
	for f in world.foes():
		if f.state == "windup":
			_telegraph(f)
	_draw_combo()
	_draw_aim()
	for it in world.interactables:
		_torch(it)
	for id in trails:
		var f: SimFighter = world.fighter(id)
		if f == null:
			continue
		for tr in trails[id]:
			_body(f, tr.pos, Color(1, 1, 1, tr.t / 0.22 * 0.35))
	var list := world.fighters.filter(func(f): return f.alive or f.kind == "partner")
	list.sort_custom(func(a, b): return a.pos.y < b.pos.y)
	for f in list:
		_fighter(f)
	for pr in world.projectiles:
		draw_circle(pr.pos + Vector2(0, -16), 5.0, UiKit.PURPLE)
		draw_circle(pr.pos + Vector2(0, -16) - pr.vel.normalized() * 6.0, 3.0, Color(UiKit.POISON, 0.7))
	for fx in effects:
		_effect(fx)


func _ellipse(c: Vector2, r: float, color: Color, squash := 0.55) -> void:
	var pts := PackedVector2Array()
	for i in 24:
		var a := TAU * i / 24.0
		pts.append(c + Vector2(cos(a) * r, sin(a) * r * squash))
	draw_colored_polygon(pts, color)


func _ellipse_line(c: Vector2, r: float, color: Color, squash := 0.55, width := 1.0) -> void:
	var pts := PackedVector2Array()
	for i in 25:
		var a := TAU * i / 24.0
		pts.append(c + Vector2(cos(a) * r, sin(a) * r * squash))
	draw_polyline(pts, color, width)


func _cone_points(origin: Vector2, dir: Vector2, r: float, half: float) -> PackedVector2Array:
	var pts := PackedVector2Array([origin])
	var base := dir.angle()
	for i in 17:
		var a := base - half + 2.0 * half * i / 16.0
		pts.append(origin + Vector2(cos(a), sin(a) * 0.75) * r)
	return pts


## 预警红区：半透明警示红，越接近出手越亮，边缘亮一圈（美术说明第七节）
func _telegraph(e: SimFighter) -> void:
	var a := e.atk
	var p: float = clampf(e.t / a.tele, 0.0, 1.0)
	var fill := Color(UiKit.WARN, 0.18 + 0.32 * p)
	var edge := Color(UiKit.WARN, 0.55 + 0.45 * p)
	match a.shape:
		"cone":
			var pts := _cone_points(e.pos, e.facing, a.range, a.half)
			draw_colored_polygon(pts, fill)
			pts.append(pts[0])
			draw_polyline(pts, edge, 1.0)
		"line":
			var side: Vector2 = e.facing.orthogonal() * a.width
			var far: Vector2 = e.facing * a.range
			var poly := PackedVector2Array([e.pos + side, e.pos + far + side, e.pos + far - side, e.pos - side])
			draw_colored_polygon(poly, fill)
			poly.append(poly[0])
			draw_polyline(poly, edge, 1.0)
		"circle":
			_ellipse(e.pos, a.range, fill, 0.75)
			_ellipse_line(e.pos, a.range, edge, 0.75)


func _draw_combo() -> void:
	var c := world.combo
	for id in c.preview:
		var pt: Vector2 = c.preview[id]
		_ellipse_line(pt, c.radius(), Color(UiKit.QI, 0.8), 0.55, 2.0)
		_ellipse(pt, c.radius(), Color(UiKit.QI, 0.12))
	if not c.invite.is_empty():
		var pt: Vector2 = c.invite.point
		var blink := 0.6 + 0.4 * sin(world.time * 12.0)
		draw_texture_rect(UiKit.ui("heji_ground"), Rect2(pt - Vector2(c.radius(), c.radius() * 0.55), Vector2(c.radius() * 2, c.radius() * 1.1)), false, Color(1, 1, 1, blink))
		var ratio: float = c.invite.t / SimData.COMBO.window
		var pts := PackedVector2Array()
		for i in 41:
			var a := -PI / 2.0 + TAU * ratio * i / 40.0
			pts.append(pt + Vector2(cos(a), sin(a) * 0.55) * (c.radius() + 4.0))
		if pts.size() > 1:
			draw_polyline(pts, UiKit.CAST, 2.0)


## 本地玩家的蓄力进度 / 瞄准指示器
func _draw_aim() -> void:
	var f := world.fighter(me_id)
	if f == null or not f.alive:
		return
	if f.state == "charge":
		var s: Dictionary = SimData.SKILLS[f.active_skill]
		var ratio: float = f.charge_t / s.max_charge
		var center := f.pos + Vector2(0, -16)
		draw_arc(center, 22, 0, TAU, 32, Color(0, 0, 0, 0.4), 4.0)
		draw_arc(center, 22, -PI / 2, -PI / 2 + TAU * ratio, 32, UiKit.GOLD_WHITE if ratio >= 1.0 else _sect_color(f), 4.0)
		if f.active_skill == "shehunshu":
			draw_line(f.pos + Vector2(0, -16), f.pos + Vector2(0, -16) + f.aim_dir * s.range, Color(UiKit.PURPLE, 0.5), 2.0)
	elif f.state == "aim":
		var s: Dictionary = SimData.SKILLS[f.active_skill]
		if f.active_skill == "huagongsan":
			var tex := UiKit.ui("aim_spot")
			draw_texture_rect(tex, Rect2(f.aim_point - Vector2(s.radius, s.radius * 0.66), Vector2(s.radius * 2, s.radius * 1.33)), false)
			draw_line(f.pos, f.aim_point, Color(UiKit.PURPLE, 0.4), 1.0)
		else:
			var pts := _cone_points(f.pos, f.aim_dir, s.range, s.half)
			draw_colored_polygon(pts, Color(UiKit.QI, 0.16))
			pts.append(pts[0])
			draw_polyline(pts, Color(UiKit.QI, 0.85), 1.0)


func _torch(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	draw_rect(Rect2(p + Vector2(-2, -34), Vector2(4, 34)), WOOD)
	draw_rect(Rect2(p + Vector2(-4, -36), Vector2(8, 4)), Color("#3B2A20"))
	if it.on:
		var flick := sin(world.time * 14.0 + p.x) * 2.0
		draw_circle(p + Vector2(0, -42 + flick * 0.3), 6.0 + flick * 0.3, Color("#FF8A3C"))
		draw_circle(p + Vector2(0, -44), 3.0, Color("#FFF3C4"))
		draw_circle(p + Vector2(0, -40), 26.0, Color(1.0, 0.6, 0.2, 0.08))
		var me := world.fighter(me_id)
		if me and me.pos.distance_to(p) < 44.0:
			UiKit.text(self, p + Vector2(-20, -66), "E 熄灭" if not _mobile() else "点交谈熄灭", 12, UiKit.TEXT)
	else:
		draw_circle(p + Vector2(0, -40), 2.0, Color(0.5, 0.5, 0.5, 0.6))


func _mobile() -> bool:
	var hud := get_tree().get_first_node_in_group("hud") as Hud
	return hud != null and hud.mobile


func _fighter(f: SimFighter) -> void:
	_ellipse(f.pos, f.radius + 2, Color(0, 0, 0, 0.35), 0.45)
	if f.primed:
		_ellipse_line(f.pos, f.radius + 6, Color(UiKit.QI, 0.5 + 0.4 * sin(world.time * 8.0)), 0.45, 1.0)
	if f.root_t > 0.0:
		_ellipse_line(f.pos, f.radius + 8, UiKit.PURPLE, 0.45, 2.0)
	var tint := Color.WHITE
	if not f.alive:
		tint = Color(0.6, 0.6, 0.6, 0.6)
	_body(f, f.pos, tint)
	if f.shield > 0.0:
		var c := f.pos + Vector2(0, -18)
		draw_circle(c, 22.0, Color(UiKit.QI, 0.12))
		draw_arc(c, 22.0, 0, TAU, 32, Color(UiKit.QI, 0.7), 1.0)
	if f.state == "cast":
		var c := f.pos + Vector2(0, -28)
		draw_arc(c, 30.0 + 4.0 * sin(world.time * 16.0), 0, TAU, 32, UiKit.CAST, 2.0)
		UiKit.text(self, f.pos + Vector2(-6, -86), "!", 24, UiKit.CAST)
	if f.state == "stagger":
		for i in 3:
			var a := world.time * 6.0 + TAU * i / 3.0
			draw_circle(f.pos + Vector2(cos(a) * 12.0, -52 + sin(a) * 4.0), 2.0, UiKit.QI)
	if f.poison_stacks > 0 or f.poison_t > 0.0:
		for i in (3 if f.poison_t > 0 else f.poison_stacks):
			draw_circle(f.pos + Vector2(-6 + i * 6, 4), 2.5, UiKit.POISON)
	if f.kind == "louluo" and f.alive and f.hp < f.max_hp:
		draw_rect(Rect2(f.pos + Vector2(-14, -48), Vector2(28, 3)), Color(0, 0, 0, 0.6))
		draw_rect(Rect2(f.pos + Vector2(-14, -48), Vector2(28 * f.hp / f.max_hp, 3)), UiKit.HEALTH)


## 占位人形：脚底在 at。按身份配色：少林褐红短褂土黄束带、邪派墨黑暗紫衣纹毒绿滚边、
## 净心光头褐红僧袍、喽啰墨黑蒙面、玄诚高一号僧袍外罩墨黑半臂。
func _body(f: SimFighter, at: Vector2, tint: Color) -> void:
	var scale := 1.3 if f.kind == "xuancheng" else (0.95 if f.kind == "partner" else 1.0)
	var flash := f.flash_t > 0.0
	var robe := UiKit.MONK
	var trim := UiKit.SASH
	var head_hair := HAIR
	match f.kind:
		"player":
			if f.sect == "xiepai":
				robe = UiKit.CULT
				trim = UiKit.PURPLE
		"partner":
			head_hair = SKIN
		"louluo":
			robe = UiKit.CULT
			trim = UiKit.DARK_PURPLE
		"xuancheng":
			trim = UiKit.CULT
			head_hair = Color("#5A4A40")
	if flash:
		robe = UiKit.GOLD_WHITE
		trim = UiKit.GOLD_WHITE
	robe *= tint
	trim *= tint
	var sit := f.state == "sit"
	var h := 24.0 * scale
	var w := 14.0 * scale
	var top := at + Vector2(-w / 2.0, -h - (0.0 if not sit else -10.0 * scale))
	if f.state == "dodge":
		top.y += 6
	draw_rect(Rect2(top, Vector2(w, h if not sit else h * 0.6)), robe)
	if f.kind == "xuancheng":
		draw_rect(Rect2(top, Vector2(3 * scale, h * 0.8)), trim)
		draw_rect(Rect2(top + Vector2(w - 3 * scale, 0), Vector2(3 * scale, h * 0.8)), trim)
	else:
		draw_rect(Rect2(top + Vector2(0, h * 0.45), Vector2(w, 2 * scale)), trim)
	if f.kind == "player" and f.sect == "xiepai":
		draw_rect(Rect2(top + Vector2(0, h - 2), Vector2(w, 2)), UiKit.POISON * tint)
	var head := top + Vector2(w / 2.0, -5 * scale)
	draw_circle(head, 6.0 * scale, SKIN * tint if not flash else UiKit.GOLD_WHITE)
	if head_hair != SKIN:
		draw_rect(Rect2(head + Vector2(-6, -6) * scale, Vector2(12, 5) * scale), head_hair * tint)
	if f.kind == "louluo":
		draw_rect(Rect2(head + Vector2(-6, 0) * scale, Vector2(12, 5) * scale), UiKit.CULT * tint)
	# 眼睛示意朝向
	if not sit:
		draw_rect(Rect2(head + f.facing * 3.0 * scale + Vector2(-1, -1), Vector2(2, 2)), Color(0.1, 0.08, 0.08) * tint)
	_weapon(f, head + Vector2(0, 10 * scale), scale, tint)


func _weapon(f: SimFighter, hand: Vector2, scale: float, tint: Color) -> void:
	if f.state == "sit":
		draw_line(hand + Vector2(-16, 14), hand + Vector2(16, 14), WOOD * tint, 2.0)
		return
	var staff := f.kind != "louluo" and not (f.kind == "player" and f.sect == "xiepai")
	var length := (34.0 if staff else 18.0) * scale
	var dir := f.facing
	if f.state == "cast":
		dir = Vector2(0.2, -1).normalized()
	elif f.swing_t > 0.0:
		dir = f.facing.rotated(-1.2 + 2.4 * (1.0 - f.swing_t / 0.3))
	elif f.state == "windup":
		dir = f.facing.rotated(2.4)  # 起手：棍头后拉
	var from := hand - dir * (length * 0.35 if staff else 2.0)
	draw_line(from, from + dir * length, (WOOD if staff else STEEL) * tint, 2.0 if staff else 2.0)


func _effect(fx: Dictionary) -> void:
	var k: float = fx.t / fx.dur
	match fx.kind:
		"text":
			var a := 1.0 - maxf(0.0, k - 0.6) / 0.4
			UiKit.text(self, fx.pos + Vector2(-10, -24 * k), fx.s, 24 if fx.big else 12, Color(fx.color, a))
		"swing":
			var f := world.fighter(fx.id)
			var origin: Vector2 = (f.pos if f else fx.pos) + Vector2(0, -12)
			var pts := _cone_points(origin, fx.dir, fx.r, 1.0 if not fx.heavy else 1.4)
			draw_colored_polygon(pts, Color(fx.color, 0.35 * (1.0 - k)))
		"palm":
			var pts := _cone_points(fx.pos + Vector2(0, -10), fx.dir, fx.r * (0.6 + 0.4 * k), 0.6)
			draw_colored_polygon(pts, Color(UiKit.QI, 0.5 * (1.0 - k)))
			draw_circle(fx.pos + fx.dir * fx.r * k + Vector2(0, -16), 10.0 * (1.0 - k) + 4.0, Color(UiKit.GOLD_WHITE, 1.0 - k))
		"burst":
			for i in 8:
				var a := TAU * i / 8.0
				draw_circle(fx.pos + Vector2(cos(a), sin(a)) * fx.r * k, 2.0, Color(fx.color, 1.0 - k))
		"spark":
			draw_line(fx.pos + Vector2(-8, -8) * (1 - k), fx.pos + Vector2(8, 8) * (1 - k), Color(fx.color, 1 - k), 2.0)
			draw_line(fx.pos + Vector2(8, -8) * (1 - k), fx.pos + Vector2(-8, 8) * (1 - k), Color(fx.color, 1 - k), 2.0)
		"ring":
			draw_arc(fx.pos, fx.r * (0.5 + 0.5 * k), 0, TAU, 32, Color(fx.color, 1.0 - k), 2.0)
		"rise":
			for i in 6:
				draw_circle(fx.pos + Vector2(-12 + i * 5, -10 - 30 * k - (i % 2) * 6), 1.5, Color(fx.color, 1.0 - k))
		"beam":
			draw_line(fx.pos + Vector2(0, -16), fx.to + Vector2(0, -16), Color(UiKit.PURPLE, 1.0 - k), 3.0)
			draw_line(fx.pos + Vector2(0, -16), fx.to + Vector2(0, -16), Color(UiKit.GOLD_WHITE, 0.6 * (1.0 - k)), 1.0)
		"blink":
			draw_line(fx.pos + Vector2(0, -14), fx.to + Vector2(0, -14), Color(UiKit.GOLD_WHITE, 0.5 * (1.0 - k)), 6.0)
		"shock":
			_ellipse_line(fx.pos, 40.0 + 600.0 * k, Color(UiKit.GOLD_WHITE, 1.0 - k), 0.55, 3.0)
		"combo":
			var r: float = fx.r * (0.6 + 0.6 * k)
			_ellipse(fx.pos, r, Color(UiKit.GOLD_WHITE, 0.35 * (1.0 - k)))
			_ellipse_line(fx.pos, r, Color(UiKit.QI, 1.0 - k), 0.55, 3.0)
			var rays: int = [2, 4, 8][fx.level]
			for i in rays:
				var a := TAU * i / rays + k
				draw_line(fx.pos + Vector2(0, -12), fx.pos + Vector2(cos(a), sin(a) * 0.55) * r * 1.4 + Vector2(0, -12), Color(UiKit.GOLD_WHITE, 1.0 - k), 2.0)
