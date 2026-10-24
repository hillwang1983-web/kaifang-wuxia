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
const BREACH := Color("#FF9A3C")    # 铁甲裂口：露出里面发光的齿轮
const BRONZE := Color("#4E6B58")    # 铁甲金刚：青铜锈绿
const PART_COLORS := {"chassis": Color("#7A5A3C"), "arm": Color("#C9A66B"), "winch": Color("#9AA3A8")}

var world: SimWorld
var me_id := -1
var background: Texture2D
var foreground: Texture2D      # 前景遮挡层（棚顶、门檐），叠在角色上面（底图 → 角色 → 前景）
var _fg_image: Image           # 前景的像素副本，用来判断角色是不是被挡住
var effects: Array = []        # {kind, pos, t, dur, ...}
var trails := {}               # fighter id -> [{pos, t}]
var npcs: Array = []           # 剧情里只站着的人（阿萝等）{pos, name, robe, hair}
var hint_pos := Vector2.ZERO   # 关卡设置的互动提示（如「E 交谈」），hint_text 为空不画
var hint_text := ""
var markers: Array = []        # 开场教学：地上发光的目标点 {pos}
var flash := 0.0               # 附身醒来的白光，按秒淡出
var trainer_look := Color("#6B5A48")  # 开场引导人（教闪避的在场 NPC）的衣色
var hitstop := 0.0             # 由关卡读走：命中停顿
var _anim := {}                # fighter id -> {action, t}：帧动画的当前动作与已播时长
var hints_muted := false       # 本局关闭合击提示：不画引导光路
var guide_invites := 2         # AI 发的前两次合击邀请加强引导（规格书第四节：新手五分钟内自发打出第一次合击）
var _guided := {}              # 已经加强引导过的邀请编号
var shake := 0.0


func consume_events() -> void:
	for e in world.events:
		_on_event(e)
	world.events.clear()


func _process(dt: float) -> void:
	flash = maxf(0.0, flash - dt)
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
			var act := SpriteLib.action_for(f)
			var a: Dictionary = _anim.get(f.id, {})
			if a.get("action", "") != act:
				_anim[f.id] = {"action": act, "t": 0.0}
			else:
				a.t += dt
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
				"jiemai":
					_fx("needle", f.pos, 0.25, {"dir": e.dir})
				"dushazhang":
					_fx("burst", f.pos + e.dir * 16.0 + Vector2(0, -16), 0.25, {"color": UiKit.PURPLE, "r": 12.0})
				"huagongsan":
					_fx("burst", f.pos + Vector2(0, -16), 0.3, {"color": UiKit.POISON, "r": 10.0})
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
			match e.atk:
				"sweep", "slash":
					_fx("slash", e.pos, 0.2, {"dir": e.dir, "r": 70.0 if e.atk == "sweep" else 50.0})
				"dash", "charge":
					_fx("dust", e.pos, 0.6, {"dir": e.dir})
				"gu":
					_fx("burst", e.pos, 0.45, {"color": UiKit.POISON, "r": 30.0})
		"cast_start":
			if f and f.kind == "dulao":
				_fx("ring", f.pos + Vector2(0, -24), 0.6, {"color": UiKit.PURPLE, "r": 40.0})
		"heavy_release":
			_fx("shock", e.pos, 0.6, {})
			shake = maxf(shake, 4.0)
			hitstop = maxf(hitstop, 0.15)
		"combo_burst":
			_fx("formation" if e.get("kind", "") == "formation" else "combo", e.point, 0.8 if e.get("kind", "") == "formation" else 0.6,
				{"r": e.radius, "level": e.level})
			shake = maxf(shake, 3.0)
		"interact":
			_fx("burst", e.pos + Vector2(0, -26), 0.5, {"color": UiKit.MUTED, "r": 14.0})
		"shield_hit":
			_fx("ring", e.pos + Vector2(0, -16), 0.2, {"color": UiKit.QI, "r": 24.0})
		"quake":
			_fx("shock", e.pos, 0.7, {})
			shake = maxf(shake, 5.0)
			hitstop = maxf(hitstop, 0.1)
		"bolt_fire":
			shake = maxf(shake, 1.0 + e.tier)
		"breach":
			_fx("burst", e.pos + Vector2(0, -30), 0.5, {"color": BREACH, "r": 18.0 + 8.0 * e.tier})
			_text(e.pos + Vector2(0, -20), ["小裂口", "裂口", "大裂口"][e.tier], BREACH, e.tier == 2)
			hitstop = maxf(hitstop, 0.08 + 0.04 * e.tier)
		"deflect":
			_text(e.pos + Vector2(0, -30), "撞偏！", UiKit.QI, true)
			_fx("ring", e.pos + Vector2(0, -30), 0.5, {"color": UiKit.GOLD_WHITE, "r": 60.0})
			shake = maxf(shake, 4.0)
		"ballista_hit":
			_text(e.pos + Vector2(0, -20), "弩车 -1", BLOOD_TEXT, true)
			shake = maxf(shake, 3.0)
		"ballista_break":
			_fx("burst", e.pos + Vector2(0, -16), 0.6, {"color": WOOD, "r": 50.0})
		"part_install", "ballista_built":
			_fx("ring", world.ballista.center + Vector2(0, -10), 0.4, {"color": UiKit.QI, "r": 40.0})
		"grab":
			_text(e.pos, "被抓！", BLOOD_TEXT)
		"chest":
			_fx("burst", e.pos + Vector2(0, -20), 0.6, {"color": UiKit.QI, "r": 30.0})


# ---------- 绘制 ----------

func _draw() -> void:
	if world == null:
		return
	if background:
		draw_texture(background, Vector2.ZERO)
	for pool in world.pools:
		var foe_pool: bool = pool.get("team", SimFighter.HEROES) == SimFighter.FOES
		var bubble := 0.06 * sin(world.time * 6.0 + pool.pos.x)
		_ellipse(pool.pos, pool.radius, Color(UiKit.POISON if foe_pool else UiKit.PURPLE, 0.30 + bubble))
		_ellipse(pool.pos, pool.radius * 0.7, Color(UiKit.PURPLE if foe_pool else UiKit.POISON, 0.22))
		_ellipse_line(pool.pos, pool.radius, Color(UiKit.DARK_PURPLE, 0.9), 0.55, 2.0 if foe_pool else 1.0)
	for z in world.safe_zones:
		_ellipse(z.pos, z.radius, Color(UiKit.GOLD_WHITE, 0.12))
		_ellipse_line(z.pos, z.radius, Color(UiKit.QI, 0.8), 0.55, 2.0)
	for f in world.foes():
		if f.state == "windup":
			_telegraph(f)
	for m in markers:
		var pulse := 0.5 + 0.5 * sin(world.time * 5.0)
		_ellipse(m.pos, 22.0, Color(UiKit.QI, 0.12 + 0.12 * pulse), 0.55)
		_ellipse_line(m.pos, 22.0 + 4.0 * pulse, Color(UiKit.QI, 0.9), 0.55, 2.0)
	_draw_combo()
	_draw_aim()
	for it in world.interactables:
		if it.kind == "chest":
			_chest(it)
		else:
			_torch(it)
	if not world.ballista.is_empty():
		_draw_ballista()
		for pt in world.parts:
			if pt.carrier == -1:
				_part(pt.part, pt.pos, true)
	for g in world.ground_items:
		_ground_item(g)
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
	for pt in world.parts:
		if pt.carrier != -1:
			_part(pt.part, pt.pos + Vector2(0, -44), false)
	var rider := world.fighter(world.ballista.get("rider", -1)) if not world.ballista.is_empty() else null
	if rider:
		_draw_ballista_aim(rider)
	for n in npcs:
		_npc(n)
	_draw_fog()
	for pr in world.projectiles:
		if pr.has("bolt"):
			var d: Vector2 = pr.vel.normalized()
			var c: Vector2 = pr.pos + Vector2(0, -16)
			draw_line(c - d * 26.0, c, Color("#3B2A20"), 3.0 + pr.bolt)
			draw_line(c - d * 6.0, c + d * 4.0, STEEL, 3.0 + pr.bolt)
			continue
		draw_circle(pr.pos + Vector2(0, -16), 5.0, UiKit.PURPLE)
		draw_circle(pr.pos + Vector2(0, -16) - pr.vel.normalized() * 6.0, 3.0, Color(UiKit.POISON, 0.7))
	if foreground:
		draw_texture(foreground, Vector2.ZERO)
		_draw_hidden_heroes()
	if hint_text != "":
		var w := UiKit.text_width(hint_text) + 10.0
		UiKit.panel(self, Rect2(hint_pos + Vector2(-w / 2.0, -2), Vector2(w, 18)))
		UiKit.text(self, hint_pos + Vector2(-w / 2.0 + 5, -1), hint_text)
	for fx in effects:
		_effect(fx)
	if flash > 0.0:
		draw_rect(Rect2(Vector2.ZERO, Vector2(1920, 1080)), Color(1, 1, 1, minf(1.0, flash / 0.6)))


## 被棚顶 / 门檐挡住的玩家和净心，在前景上面补一层半透明剪影，免得看不见自己
func _draw_hidden_heroes() -> void:
	if _fg_image == null:
		_fg_image = foreground.get_image()
	for f in world.heroes():
		var probe := Vector2i(f.pos + Vector2(0, -18))
		if probe.x < 0 or probe.y < 0 or probe.x >= _fg_image.get_width() or probe.y >= _fg_image.get_height():
			continue
		if _fg_image.get_pixelv(probe).a > 0.5:
			_body(f, f.pos, Color(1, 1, 1, 0.5))


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
			var far: Vector2 = e.facing * float(e.timers.get("dash_len", a.range))
			var poly := PackedVector2Array([e.pos + side, e.pos + far + side, e.pos + far - side, e.pos - side])
			draw_colored_polygon(poly, fill)
			poly.append(poly[0])
			draw_polyline(poly, edge, 1.0)
		"circle":
			_ellipse(e.pos, a.range, fill, 0.75)
			_ellipse_line(e.pos, a.range, edge, 0.75)
		"spot":
			_ellipse(e.aim_point, a.radius, fill, 0.6)
			_ellipse_line(e.aim_point, a.radius, edge, 0.6, 2.0)
		"quake":
			# 全场：一圈一圈往外推的红环，越接近落地越亮
			for i in 4:
				var r := fmod(p * 900.0 + i * 240.0, 960.0) + 40.0
				_ellipse_line(e.pos, r, Color(UiKit.WARN, (0.3 + 0.6 * p) * (1.0 - r / 1000.0)), 0.55, 3.0)
			_ellipse(e.pos, 60.0 + 30.0 * p, fill, 0.55)


## 毒雾：安全圈外一圈雾绿掺暗紫（美术说明第三节），边缘亮一道毒绿；扩散时能看出圈在缩
func _draw_fog() -> void:
	if world.fog.is_empty():
		return
	var c: Vector2 = world.fog.center
	var r: float = world.fog.r
	if r < 4.0:
		# 收口吞没了整个大厅：整片雾（圈太小时画环形会退化成坏多边形）
		draw_rect(Rect2(Vector2.ZERO, Vector2(1920, 1080)), Color(UiKit.POISON.lerp(UiKit.DARK_PURPLE, 0.55), 0.4))
		return
	var n := 48
	var outer := 2400.0
	var pulse := 0.05 * sin(world.time * 2.0)
	for i in n:
		var a0 := TAU * i / n
		var a1 := TAU * (i + 1) / n
		var poly := PackedVector2Array([c + Vector2(cos(a0), sin(a0) * 0.7) * r, c + Vector2(cos(a1), sin(a1) * 0.7) * r,
			c + Vector2(cos(a1), sin(a1)) * outer, c + Vector2(cos(a0), sin(a0)) * outer])
		draw_colored_polygon(poly, Color(UiKit.POISON.lerp(UiKit.DARK_PURPLE, 0.55), 0.38 + pulse))
	_ellipse_line(c, r, Color(UiKit.POISON, 0.9), 0.7, 2.0)


## 合击光圈：美术交付的帧条（vfx_heji_ring_layout_v01.json）——展开 6 帧 0.5 秒，之后常驻 4 帧循环，
## 叠一条三秒倒计时弧（36 帧）。帧是 96×96，按当前默契等级的光圈半径缩放。
const RING_FRAME := 96.0
const RING_FPS := 12.0


func _ring_frame(sheet: String, frame: int, center: Vector2, r: float, alpha := 1.0) -> void:
	var tex := UiKit.tex("res://assets/vfx/vfx_heji_ring_%s_v01.png" % sheet)
	var count := int(tex.get_width() / RING_FRAME)
	var src := Rect2(clampi(frame, 0, count - 1) * RING_FRAME, 0, RING_FRAME, RING_FRAME)
	var size := r * 2.0 * 1.12  # 帧里的圆环约占帧宽九成
	draw_texture_rect_region(tex, Rect2(center - Vector2(size, size) / 2.0, Vector2(size, size)), src, Color(1, 1, 1, alpha))


func _draw_combo() -> void:
	var c := world.combo
	_draw_guide()
	for id in c.preview:
		_ring_frame("loop", int(world.time * RING_FPS) % 4, c.preview[id], c.radius(), 0.55)
	if not c.invite.is_empty():
		var pt: Vector2 = c.invite.point
		var elapsed: float = SimData.COMBO.window - c.invite.t
		if elapsed < 0.5:
			_ring_frame("open", int(elapsed / 0.5 * 6.0), pt, c.radius())
		else:
			_ring_frame("loop", int(world.time * RING_FPS) % 4, pt, c.radius())
		_ring_frame("countdown", int(elapsed / SimData.COMBO.window * 36.0), pt, c.radius())


## 加强引导：AI 发的前两次邀请，从玩家脚下到光圈画一道流动的金光，光圈外再套一圈呼吸光（不靠文字）
func _draw_guide() -> void:
	var inv := world.combo.invite
	var me := world.fighter(me_id)
	if hints_muted or inv.is_empty() or me == null or inv.from == me_id or me_id in inv.responders:
		return
	if not _guided.has(inv.n):
		if _guided.size() >= guide_invites:
			return
		_guided[inv.n] = true
	var to: Vector2 = inv.point
	var from := me.pos
	var n := int(from.distance_to(to) / 18.0)
	for i in n:
		var u := fmod(float(i) / maxf(1.0, n) + world.time * 0.8, 1.0)
		draw_circle(from.lerp(to, u), 3.0, Color(UiKit.GOLD_WHITE, 0.4 + 0.5 * u))
	var pulse := 0.5 + 0.5 * sin(world.time * 8.0)
	_ellipse_line(to, world.combo.radius() + 10.0 + 8.0 * pulse, Color(UiKit.QI, 0.4 + 0.5 * pulse), 0.55, 3.0)


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


## 地上的掉落：金钱是几枚铜钱，物品是按品质描边的小块，装备上方飘名字（图标美术到之前的占位）
func _ground_item(g: Dictionary) -> void:
	var p: Vector2 = g.pos
	var bob := sin(world.time * 4.0 + p.x) * 1.5
	if g.coins > 0:
		for i in 3:
			draw_circle(p + Vector2(-4 + i * 4, -4 - i * 2 + bob), 3.0, Color("#E5C15A"))
		return
	var it: Dictionary = g.item
	var col := SimItems.quality_color(it)
	_ellipse(p, 12, Color(col, 0.18 + 0.1 * sin(world.time * 5.0)), 0.5)
	var r := Rect2(p + Vector2(-6, -18 + bob), Vector2(12, 16))
	draw_rect(r, Color("#5A3F29") if SimItems.is_equipment(it) else Color("#E8E2D2"))
	draw_rect(r.grow(-0.5), col, false, 1.0)
	if SimItems.is_equipment(it):
		var label := SimItems.display_name(it)
		UiKit.text(self, p + Vector2(-UiKit.text_width(label) / 2.0, -38 + bob), label, 12, col)


func _torch(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	draw_rect(Rect2(p + Vector2(-2, -34), Vector2(4, 34)), WOOD)
	draw_rect(Rect2(p + Vector2(-4, -36), Vector2(8, 4)), Color("#3B2A20"))
	if it.on:
		var flick := sin(world.time * 14.0 + p.x) * 2.0
		draw_circle(p + Vector2(0, -42 + flick * 0.3), 6.0 + flick * 0.3, Color("#FF8A3C"))
		draw_circle(p + Vector2(0, -44), 3.0, Color("#FFF3C4"))
		draw_circle(p + Vector2(0, -40), 26.0, Color(1.0, 0.6, 0.2, 0.08))
	else:
		draw_circle(p + Vector2(0, -40), 2.0, Color(0.5, 0.5, 0.5, 0.6))


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
		var victim := world.fighter(f.target_id) if f.kind == "dulao" else null
		if victim:
			# 摄魂指：一道紫光线连到被点名的人
			draw_line(f.pos + Vector2(0, -24), victim.pos + Vector2(0, -20), Color(UiKit.PURPLE, 0.5 + 0.4 * sin(world.time * 14.0)), 2.0)
	# 毒姥的毒罩：罩着时是半透明紫绿球，被震碎时闪金屑
	if f.kind == "dulao" and f.active():
		var c := f.pos + Vector2(0, -20)
		if f.ward_t <= 0.0:
			draw_circle(c, 30.0, Color(UiKit.PURPLE, 0.16))
			draw_arc(c, 30.0, 0, TAU, 40, Color(UiKit.POISON, 0.7), 2.0)
		else:
			for i in 6:
				var a := world.time * 3.0 + TAU * i / 6.0
				draw_circle(c + Vector2(cos(a), sin(a)) * 34.0, 2.0, UiKit.QI)
	if f.state == "stagger":
		for i in 3:
			var a := world.time * 6.0 + TAU * i / 3.0
			draw_circle(f.pos + Vector2(cos(a) * 12.0, -52 + sin(a) * 4.0), 2.0, UiKit.QI)
	if f.poison_stacks > 0 or f.poison_t > 0.0:
		for i in (3 if f.poison_t > 0 else f.poison_stacks):
			draw_circle(f.pos + Vector2(-6 + i * 6, 4), 2.5, UiKit.POISON)
	if f.kind == "trainer" and f.alive:
		var w := UiKit.text_width(f.name)
		UiKit.text(self, f.pos + Vector2(-w / 2.0, -54), f.name, 12, UiKit.TEXT)
	if (f.kind == "louluo" or f.kind == "crate" or f.kind == "jar" or f.kind == "pile") and f.alive and f.hp < f.max_hp:
		draw_rect(Rect2(f.pos + Vector2(-14, -48), Vector2(28, 3)), Color(0, 0, 0, 0.6))
		draw_rect(Rect2(f.pos + Vector2(-14, -48), Vector2(28 * f.hp / f.max_hp, 3)), UiKit.HEALTH)


## 占位人形：脚底在 at。按身份配色：少林褐红短褂土黄束带、邪派墨黑暗紫衣纹毒绿滚边、
## 净心光头褐红僧袍、喽啰墨黑蒙面、玄诚高一号僧袍外罩墨黑半臂。
func _body(f: SimFighter, at: Vector2, tint: Color) -> void:
	if f.kind == "crate" or f.kind == "jar" or f.kind == "pile":
		_prop(f, at, tint)
		return
	if f.state == "thrown":
		at += Vector2(0, -24.0 * sin(PI * clampf(1.0 - f.dodge_t / 0.45, 0.0, 1.0)))
	# 美术交了动作条的角色画帧动画（受击时提亮闪白）；没有图的动作 / 角色退回下面的代码占位
	var lit := Color(2.2, 2.2, 2.2, tint.a) if f.flash_t > 0.0 else tint
	if SpriteLib.draw(self, f, at, float(_anim.get(f.id, {}).get("t", 0.0)), lit):
		if f.kind == "jingang":
			_breaches(f, at)
		return
	if f.kind == "jingang":
		_jingang(f, at, tint)
		return
	var scale := 1.3 if f.kind == "xuancheng" else (1.2 if f.kind == "dulao" else (0.95 if f.kind == "partner" else 1.0))
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
		"dulao":
			robe = UiKit.CULT
			trim = UiKit.POISON
			head_hair = Color("#E8E2D2")  # 白发
		"ally":
			robe = Color("#4A5A6B")      # 第三人（临时 AI 侠客）：青灰长衫、土黄束带
			trim = UiKit.SASH
		"trainer":
			robe = trainer_look          # 开场教闪避的在场 NPC（福伯、刘婶、班主、黑衣人）
			trim = Color("#3B2A20")
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


## 可破坏物：木箱、酒坛（美术说明第六节，图到之前的色块）
func _prop(f: SimFighter, at: Vector2, tint: Color) -> void:
	var c := (Color("#7A5A3C") if f.kind == "crate" else Color("#4A3A30")) * tint
	if f.flash_t > 0.0:
		c = UiKit.GOLD_WHITE
	if f.kind == "pile":
		# 零件堆：几块木板压着一捆铁件；带零件的堆顶上露出零件的颜色
		draw_rect(Rect2(at + Vector2(-16, -14), Vector2(32, 14)), c)
		draw_rect(Rect2(at + Vector2(-12, -24), Vector2(22, 10)), Color("#5A3F29") * tint)
		draw_line(at + Vector2(-16, -14), at + Vector2(14, -26), Color("#3B2A20") * tint, 2.0)
		var part: String = world.pile_parts.get(f.id, "")
		if part != "":
			draw_rect(Rect2(at + Vector2(-4, -30), Vector2(10, 6)), PART_COLORS[part] * tint)
		return
	if f.kind == "crate":
		draw_rect(Rect2(at + Vector2(-11, -20), Vector2(22, 20)), c)
		draw_rect(Rect2(at + Vector2(-11, -20), Vector2(22, 20)), Color("#3B2A20") * tint, false, 1.0)
		draw_line(at + Vector2(-11, -20), at + Vector2(11, 0), Color("#3B2A20") * tint, 1.0)
	else:
		draw_circle(at + Vector2(0, -9), 9.0, c)
		draw_rect(Rect2(at + Vector2(-4, -20), Vector2(8, 4)), Color("#8C3B2E") * tint)


func _npc(n: Dictionary) -> void:
	var at: Vector2 = n.pos
	_ellipse(at, 12, Color(0, 0, 0, 0.35), 0.45)
	draw_rect(Rect2(at + Vector2(-7, -24), Vector2(14, 24)), n.robe)
	draw_circle(at + Vector2(0, -29), 6.0, Color("#E0C8B0"))
	draw_rect(Rect2(at + Vector2(-6, -35), Vector2(12, 6)), n.hair)
	var w := UiKit.text_width(n.name)
	UiKit.text(self, at + Vector2(-w / 2.0, -54), n.name, 12, UiKit.TEXT)


func _weapon(f: SimFighter, hand: Vector2, scale: float, tint: Color) -> void:
	if f.state == "sit":
		draw_line(hand + Vector2(-16, 14), hand + Vector2(16, 14), WOOD * tint, 2.0)
		return
	if f.kind == "dulao":
		draw_line(hand + Vector2(10, -8), hand + Vector2(14, 22), WOOD * tint, 2.0)  # 蛇纹拐杖
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
		"needle":
			# 截脉：一道细亮的指劲往前刺，尽头一个小环
			var tip: Vector2 = fx.pos + fx.dir * 170.0 * minf(1.0, k * 3.0) + Vector2(0, -16)
			draw_line(fx.pos + Vector2(0, -16), tip, Color("#BFE8FF", 1.0 - k), 2.0)
			draw_arc(tip, 6.0 + 10.0 * k, 0, TAU, 16, Color("#BFE8FF", 1.0 - k), 1.0)
		"slash":
			# 横扫 / 劈砍：一道白色弧光
			var base: float = fx.dir.angle()
			draw_arc(fx.pos + Vector2(0, -14), fx.r * (0.8 + 0.2 * k), base - 1.1 + 2.2 * k * 0.3, base + 1.1, 20, Color(UiKit.GOLD_WHITE, 1.0 - k), 3.0)
		"dust":
			for i in 6:
				var back: Vector2 = -fx.dir * (8.0 + i * 10.0) + fx.dir.orthogonal() * (sin(i * 2.3) * 8.0)
				draw_circle(fx.pos + back, 4.0 + 6.0 * k, Color(0.55, 0.5, 0.42, 0.5 * (1.0 - k)))
		"formation":
			# 金刚伏魔圈：金色三角阵 + 外圈莲纹，比双人合击更满
			var rr: float = fx.r * (0.7 + 0.5 * k)
			_ellipse(fx.pos, rr, Color(UiKit.GOLD_WHITE, 0.3 * (1.0 - k)))
			var tri := PackedVector2Array()
			for i in 4:
				var a := -PI / 2.0 + TAU * i / 3.0 + k * 0.6
				tri.append(fx.pos + Vector2(cos(a), sin(a) * 0.55) * rr)
			draw_polyline(tri, Color(UiKit.QI, 1.0 - k), 3.0)
			for i in 8:
				var a := TAU * i / 8.0 - k * 0.4
				draw_circle(fx.pos + Vector2(cos(a), sin(a) * 0.55) * rr * 1.1, 5.0 * (1.0 - k) + 2.0, Color(UiKit.GOLD_WHITE, 1.0 - k))
			_ellipse_line(fx.pos, rr * 1.15, Color(UiKit.QI, 1.0 - k), 0.55, 3.0)
		"combo":
			var r: float = fx.r * (0.6 + 0.6 * k)
			_ellipse(fx.pos, r, Color(UiKit.GOLD_WHITE, 0.35 * (1.0 - k)))
			_ellipse_line(fx.pos, r, Color(UiKit.QI, 1.0 - k), 0.55, 3.0)
			var rays: int = [2, 4, 8][fx.level]
			for i in rays:
				var a := TAU * i / rays + k
				draw_line(fx.pos + Vector2(0, -12), fx.pos + Vector2(cos(a), sin(a) * 0.55) * r * 1.4 + Vector2(0, -12), Color(UiKit.GOLD_WHITE, 1.0 - k), 2.0)


# ---------- 大雄宝殿：弩车、零件、铁甲金刚、通关箱（美术到之前的占位形体） ----------

## 零件：底盘（木架）、弓臂（长弓）、绞盘（铁鼓）；ground 为真时在地上画光圈和名字
func _part(part: String, at: Vector2, ground: bool) -> void:
	var c: Color = PART_COLORS[part]
	var bob: float = sin(world.time * 4.0 + at.x) * 1.5 if ground else 0.0
	if ground:
		_ellipse(at, 16, Color(UiKit.QI, 0.18 + 0.1 * sin(world.time * 5.0)), 0.5)
	var o := at + Vector2(0, -12 + bob)
	match part:
		"chassis":
			draw_rect(Rect2(o + Vector2(-12, -5), Vector2(24, 10)), c)
			draw_circle(o + Vector2(-8, 6), 3.0, Color("#3B2A20"))
			draw_circle(o + Vector2(8, 6), 3.0, Color("#3B2A20"))
		"arm":
			draw_arc(o + Vector2(0, 8), 16.0, PI * 1.15, PI * 1.85, 12, c, 3.0)
		"winch":
			draw_rect(Rect2(o + Vector2(-7, -7), Vector2(14, 14)), c)
			draw_line(o + Vector2(-10, 0), o + Vector2(10, 0), Color("#55524A"), 2.0)
	if ground:
		var label: String = SimData.BALLISTA.part_names[part]
		UiKit.text(self, at + Vector2(-UiKit.text_width(label) / 2.0, -42 + bob), label, 12, UiKit.QI)


## 弩车：没拼好时是底座上装好的零件；拼好后是整车，朝瞄准方向；上方耐久格、拼装读条
func _draw_ballista() -> void:
	var b := world.ballista
	var c: Vector2 = b.center
	_ellipse_line(c, 48.0, Color(UiKit.QI, 0.25 + 0.15 * sin(world.time * 3.0)), 0.55, 1.0)
	if not b.built:
		for i in b.installed.size():
			_part(b.installed[i], c + Vector2(-22 + 22 * i, 6), false)
		if b.build_by != -1:
			var ratio: float = b.build_t / SimData.BALLISTA.build_time
			draw_arc(c + Vector2(0, -40), 16, 0, TAU, 24, Color(0, 0, 0, 0.5), 4.0)
			draw_arc(c + Vector2(0, -40), 16, -PI / 2, -PI / 2 + TAU * ratio, 24, UiKit.QI, 4.0)
		return
	var d: Vector2 = b.aim
	var side := d.orthogonal()
	var body := PackedVector2Array([c + side * 14 - d * 18, c + side * 14 + d * 10, c - side * 14 + d * 10, c - side * 14 - d * 18])
	draw_colored_polygon(body, PART_COLORS.chassis)
	draw_circle(c + side * 16 - d * 10, 5.0, Color("#3B2A20"))
	draw_circle(c - side * 16 - d * 10, 5.0, Color("#3B2A20"))
	var bend: float = 6.0 + (8.0 * b.charge_t / SimData.BALLISTA.max_charge if b.charging else 0.0)
	draw_polyline(PackedVector2Array([c + side * 26 + d * 4, c + d * (18 - bend), c - side * 26 + d * 4]), PART_COLORS.arm, 3.0)
	draw_line(c + side * 26 + d * 4, c - d * bend, Color("#E8E2D2"), 1.0)
	draw_line(c - side * 26 + d * 4, c - d * bend, Color("#E8E2D2"), 1.0)
	draw_rect(Rect2(c - d * 16 - Vector2(6, 6), Vector2(12, 12)), PART_COLORS.winch)
	draw_line(c - d * bend, c + d * 30, STEEL, 2.0)
	for i in SimData.BALLISTA.hp:
		var pip := Rect2(c + Vector2(-17 + i * 12, -46), Vector2(10, 4))
		draw_rect(pip, UiKit.QI if i < b.hp else Color(0, 0, 0, 0.5))


## 车上的人：画弩箭走向与蓄力档位（圈上三个刻度：一档、二档、满档）；队友在车上时画淡一些，看得出他瞄哪
func _draw_ballista_aim(f: SimFighter) -> void:
	var b := world.ballista
	var c: Vector2 = b.center + Vector2(0, -16)
	var tier := SimBallista.charge_tier(b.charge_t) if b.charging else -1
	var col: Color = [UiKit.TEXT, UiKit.QI, BREACH][maxi(tier, 0)]
	var mine := f.id == me_id
	draw_line(c, c + b.aim * 420.0, Color(col, (0.35 if tier < 0 else 0.7) * (1.0 if mine else 0.5)), 2.0)
	draw_circle(c + b.aim * 420.0, 4.0, Color(col, 0.7))
	if not mine and not b.charging:
		return
	var steps: Array = SimData.BALLISTA.charge_steps
	var marks := [steps[0], steps[1], SimData.BALLISTA.max_charge]
	var ratio: float = b.charge_t / SimData.BALLISTA.max_charge if b.charging else 0.0
	var ring := c + Vector2(0, -36)
	draw_arc(ring, 18, 0, TAU, 32, Color(0, 0, 0, 0.5), 4.0)
	draw_arc(ring, 18, -PI / 2, -PI / 2 + TAU * ratio, 32, col, 4.0)
	for m in marks:
		var a: float = -PI / 2 + TAU * m / SimData.BALLISTA.max_charge
		draw_circle(ring + Vector2(cos(a), sin(a)) * 18.0, 2.5, UiKit.GOLD_WHITE)


## 铁甲金刚：青铜巨人（占位色块），胸口铜镜；身上的裂口露出发光齿轮，快合上时渐暗
func _jingang(f: SimFighter, at: Vector2, tint: Color) -> void:
	var flash := f.flash_t > 0.0
	var body := (UiKit.GOLD_WHITE if flash else BRONZE) * tint
	var kneel := f.state == "sit"
	var h := 64.0 if not kneel else 40.0
	var top := at + Vector2(-24, -h)
	draw_rect(Rect2(top, Vector2(48, h)), body)
	draw_rect(Rect2(top + Vector2(-10, 6), Vector2(10, h * 0.6)), body.darkened(0.2))
	draw_rect(Rect2(top + Vector2(48, 6), Vector2(10, h * 0.6)), body.darkened(0.2))
	draw_rect(Rect2(top + Vector2(12, -18), Vector2(24, 18)), body.darkened(0.1))
	var mirror := top + Vector2(24, 18)
	draw_circle(mirror, 7.0, Color("#FFE9A8") if not kneel else Color("#55524A"))
	if not kneel:
		draw_rect(Rect2(top + Vector2(12, -12) + f.facing * 3.0, Vector2(24, 3)), UiKit.WARN)
	if f.state == "stagger":
		for i in 3:
			var a := world.time * 6.0 + TAU * i / 3.0
			draw_circle(at + Vector2(cos(a) * 18.0, -h - 26 + sin(a) * 5.0), 2.5, UiKit.QI)
	_breaches(f, at)


## 铁甲金刚身上的裂口：露出发光齿轮，快合上时渐暗（帧动画和占位形体都叠这一层）
func _breaches(f: SimFighter, at: Vector2) -> void:
	for br in f.breaches:
		var fade: float = clampf(br.t / 3.0, 0.3, 1.0)
		var bp: Vector2 = at + br.off * 1.6 + Vector2(0, -32)
		draw_circle(bp, br.r * 0.8, Color(BREACH, 0.75 * fade))
		draw_circle(bp, br.r * 0.4, Color(UiKit.GOLD_WHITE, 0.8 * fade))
		draw_arc(bp, br.r * 0.8 + 2.0, 0, TAU, 16, Color("#3B2A20"), 2.0)


func _chest(it: Dictionary) -> void:
	var p: Vector2 = it.pos
	if it.on:
		_ellipse(p, 26, Color(UiKit.QI, 0.15 + 0.1 * sin(world.time * 4.0)), 0.5)
	draw_rect(Rect2(p + Vector2(-16, -20), Vector2(32, 20)), Color("#5A3F29"))
	draw_rect(Rect2(p + Vector2(-16, -26 if it.on else -34), Vector2(32, 8)), Color("#7A5A3C"))
	draw_rect(Rect2(p + Vector2(-16, -20), Vector2(32, 20)), UiKit.QI, false, 1.0)
	draw_rect(Rect2(p + Vector2(-3, -16), Vector2(6, 6)), UiKit.QI)

