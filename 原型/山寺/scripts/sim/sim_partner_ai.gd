## AI 队友（净心、第三人，以及开发用的代玩）：和真人一样只产出 SimCommand（规格书第四节「搭档接口」的 AI 实现）。
## 会跟随、普攻、看红区闪避、走出毒池、待在毒雾安全圈里；有人被定身就用截脉解穴；
## 玩家发合击 / 阵法邀请时走进光圈响应；玄诚读条重击时、毒姥罩着毒罩时自己发邀请，
## 等玩家按合击键或走进光圈——打断和破罩要靠大家配合，不替玩家包办。
## 大雄宝殿（弩车）：porter 去捡零件、送到中央，零件齐了就拼；may_ride 在没人坐时上车打几发再让出来
## （真人走过来要坐会让座）；金刚预警冲撞时发合击邀请等大家来撞偏；没有裂口时不去硬砍铁甲，有裂口就绕到裂口那一侧打。
class_name SimPartnerAI
extends RefCounted

const A := SimData.PARTNER

var w: SimWorld
var me_id := 0
var leader_id := 0
var _react := -1.0          # 看到邀请后的反应倒计时
var _invite_seen := -1
var _dodge_wait := -1.0
var _release_combo := false
var _invite_cool := 8.0
var _attack_hold := 0.0
var porter := false         # 弩车：负责捡零件、送零件
var may_ride := false       # 弩车：没人坐时可以上车
var _ride_shots := 0
var _ride_rest := 0.0


func _init(world: SimWorld, me: int, leader: int) -> void:
	w = world
	me_id = me
	leader_id = leader


func command(dt: float) -> SimCommand:
	var cmd := SimCommand.new()
	var me := w.fighter(me_id)
	if me == null or not me.alive or w.freeze_t > 0.0:
		return cmd
	if _release_combo:
		_release_combo = false
		cmd.released["combo"] = true
		return cmd
	var leader := w.fighter(leader_id)
	_invite_cool = maxf(0.0, _invite_cool - dt)

	# 1. 响应玩家的合击邀请：反应一下，然后走进光圈
	var inv := w.combo.invite
	if not inv.is_empty() and inv.from != me_id:
		if _invite_seen != inv.n:
			_invite_seen = inv.n
			_react = w.rng.randf_range(A.invite_react[0], A.invite_react[1])
		_react -= dt
		if _react <= 0.0 and not (me_id in inv.responders):
			if me.state == "mounted" or me.state == "build":
				cmd.press("combo")  # 走不开：在原地按合击键响应
				return cmd
			cmd.move = w.steer(me.pos, inv.point) if me.pos.distance_to(inv.point) > 4.0 else Vector2.ZERO
			return cmd

	# 1.5 有人被定身：用截脉解穴（自己被定身也解自己）
	if me.utility == "jiemai" and me.cd_of("jiemai") <= 0.0:
		for h in w.heroes():
			if h.root_t > 0.4 and (h == me or h.pos.distance_to(me.pos) <= SimData.SKILLS.jiemai.range):
				cmd.press("utility")
				return cmd

	# 1.6 弩车：车上瞄准蓄力、送零件、拼装、上车（踏地震 / 冲撞的闪避在后面的红区规则里）
	if not w.ballista.is_empty() and _threat(me) == null and _ballista(me, cmd, dt):
		return cmd

	# 1.8 站在敌人的毒池里：走出去
	var pool := _bad_pool(me)
	if not pool.is_empty():
		cmd.move = (me.pos - pool.pos).normalized()
		return cmd

	# 2. 看红区闪避
	var threat := _threat(me)
	if threat:
		if _dodge_wait < 0.0:
			_dodge_wait = A.react if w.rng.randf() < A.dodge_chance else 99.0
		_dodge_wait -= dt
		if _dodge_wait <= 0.0:
			_dodge_wait = 99.0
			cmd.move = (me.pos - threat.pos).normalized().rotated(0.6)
			cmd.press("dodge")
			return cmd
	else:
		_dodge_wait = -1.0

	# 2.5 毒雾：离安全圈边缘太近就往圈中心（或净化区）走
	if not w.fog.is_empty() and (w.in_fog(me.pos) or me.pos.distance_to(w.fog.center) > w.fog.r - 28.0):
		var safe: Vector2 = w.fog.center
		for z in w.safe_zones:
			if z.pos.distance_to(me.pos) < safe.distance_to(me.pos):
				safe = z.pos
		cmd.move = w.steer(me.pos, safe)
		return cmd

	# 2.8 毒姥罩着毒罩：发阵法 / 合击邀请去破罩（光圈摆在大家中间、往雾心偏一点）
	var warded := _warded_foe()
	if warded and inv.is_empty() and w.combo.cd <= 0.0 and _invite_cool <= 0.0 and w.heroes().size() >= 2:
		_invite_cool = 7.0
		var spot := _party_center()
		if not w.fog.is_empty():
			spot = spot.lerp(w.fog.center, 0.3)
		cmd.press("combo")
		cmd.point = spot
		cmd.has_point = true
		_release_combo = true
		return cmd

	# 3. 自己发合击邀请：玄诚读条重击时，或战斗中隔一阵子
	var boss := _casting_boss()
	if inv.is_empty() and w.combo.cd <= 0.0 and leader and leader.alive:
		var want := boss != null and boss.t >= 0.3
		var armored := _armored_foe()
		if armored and armored.state == "windup" and armored.atk_id == "charge" and armored.t >= 0.15:
			want = true  # 金刚预警冲撞：发邀请等大家来撞偏
			boss = null
		elif not want and _invite_cool <= 0.0 and w.in_combat() and armored == null:
			want = true
		if want:
			_invite_cool = A.invite_every
			var spot := (boss.pos if boss else _target_of(me).pos if _target_of(me) else me.pos)
			if armored:
				spot = _party_center()
			cmd.press("combo")
			cmd.point = spot
			cmd.has_point = true
			_release_combo = true
			return cmd

	# 4. 打：贴近目标普攻；没有目标就跟着玩家
	var target := _target_of(me)
	if target and SimData.ENEMIES[target.kind].has("armor_cut"):
		_fight_armored(me, target, cmd, dt)
	elif target:
		var to := target.pos - me.pos
		var reach: float = SimData.ATTACKS[me.sect][0].range - 14.0
		if to.length() > reach:
			cmd.move = w.steer(me.pos, target.pos)
		else:
			cmd.aim = to.normalized()
			_attack_hold -= dt
			if _attack_hold <= 0.0 and me.atk_cd <= 0.0:
				_attack_hold = 0.15
				cmd.press("attack")
	elif leader:
		var to := leader.pos - me.pos
		if to.length() > A.follow:
			cmd.move = w.steer(me.pos, leader.pos) * clampf((to.length() - A.follow) / 40.0, 0.3, 1.0)
	return cmd


func _threat(me: SimFighter) -> SimFighter:
	for e in w.foes():
		if e.state == "windup" and e.atk.get("shape", "") != "field" \
				and SimEnemies.in_zone(e.atk, e.pos, e.facing, me.pos, me.radius, e.aim_point) \
				and e.atk.tele - e.t < 0.45:
			return e
	return null


func _bad_pool(me: SimFighter) -> Dictionary:
	for p in w.pools:
		if p.get("team", SimFighter.HEROES) == SimFighter.FOES and p.pos.distance_to(me.pos) <= p.radius + me.radius + 4.0:
			return p
	return {}


func _warded_foe() -> SimFighter:
	for e in w.foes():
		if SimData.ENEMIES[e.kind].has("ward_cut") and e.ward_t <= 0.0 and e.in_combat:
			return e
	return null


func _party_center() -> Vector2:
	var sum := Vector2.ZERO
	var hs := w.heroes()
	for h in hs:
		sum += h.pos
	return sum / maxf(1.0, hs.size())


func _casting_boss() -> SimFighter:
	for e in w.foes():
		if e.state == "cast":
			return e
	return null


## 优先打玩家附近最近的敌人
func _target_of(me: SimFighter) -> SimFighter:
	var leader := w.fighter(leader_id)
	var anchor := leader.pos if leader and leader.alive else me.pos
	var best: SimFighter = null
	for e in w.foes():
		if e.in_combat or e.pos.distance_to(anchor) < 200.0:
			if best == null or e.pos.distance_to(anchor) < best.pos.distance_to(anchor):
				best = e
	return best


# ---------- 大雄宝殿：弩车 ----------

## 返回真表示这一帧在忙弩车的事
func _ballista(me: SimFighter, cmd: SimCommand, dt: float) -> bool:
	var b := w.ballista
	_ride_rest = maxf(0.0, _ride_rest - dt)
	if me.state == "build":
		return true  # 站着别动，等读条
	if me.state == "mounted":
		var leader := w.fighter(leader_id)
		var wants := leader != null and leader.alive and leader.kind == "player" and leader.pos.distance_to(b.center) < SimData.BALLISTA.reach + 20.0
		if _ride_shots >= 4 or wants:
			_ride_shots = 0
			_ride_rest = 8.0
			cmd.press("interact")
			return true
		var foe := _armored_foe()
		if foe:
			cmd.aim = (foe.pos - b.center).normalized()
		# 蓄到第三档再松手（AI 只打满档，不抢真人的节奏）
		if b.charging and b.charge_t >= SimData.BALLISTA.charge_steps[1] + 0.05:
			_ride_shots += 1
		else:
			cmd.held["attack"] = true
		return true
	var mine := SimBallista.carried(w, me)
	if not b.built and not mine.is_empty():
		cmd.move = w.steer(me.pos, b.center)
		return true
	if not b.built and b.installed.size() == SimData.BALLISTA.parts.size() and b.build_by == -1:
		if me.pos.distance_to(b.center) > SimData.BALLISTA.reach - 12.0:
			cmd.move = w.steer(me.pos, b.center)
		else:
			cmd.press("interact")
		return true
	if porter and not b.built and mine.is_empty():
		var part := _loose_part(me)
		if not part.is_empty():
			cmd.move = w.steer(me.pos, part.pos)
			return true
		var pile := _part_pile(me)
		if pile:
			var to := pile.pos - me.pos
			if to.length() > SimData.ATTACKS[me.sect][0].range - 20.0:
				cmd.move = w.steer(me.pos, pile.pos)
			else:
				cmd.aim = to.normalized()
				if me.atk_cd <= 0.0:
					cmd.press("attack")
			return true
	if may_ride and b.built and b.rider == -1 and _ride_rest <= 0.0:
		if me.pos.distance_to(b.center) > SimData.BALLISTA.reach - 12.0:
			cmd.move = w.steer(me.pos, b.center)
		else:
			cmd.press("interact")
		return true
	return false


## 没人背的零件里离自己最近、且别的英雄没在去捡的
func _loose_part(me: SimFighter) -> Dictionary:
	var best := {}
	for p in w.parts:
		if p.carrier != -1:
			continue
		if best.is_empty() or p.pos.distance_to(me.pos) < best.pos.distance_to(me.pos):
			best = p
	return best


## 还没打碎、带零件的零件堆
func _part_pile(me: SimFighter) -> SimFighter:
	var best: SimFighter = null
	for id in w.pile_parts:
		var f := w.fighter(id)
		if f and f.alive and (best == null or f.pos.distance_to(me.pos) < best.pos.distance_to(me.pos)):
			best = f
	return best


func _armored_foe() -> SimFighter:
	for e in w.foes():
		if SimData.ENEMIES[e.kind].has("armor_cut"):
			return e
	return null


## 打铁甲：有裂口就绕到最大那道裂口的一侧再出手；没有裂口不硬砍——
## 弩车拼好了就把金刚往远离弩车的方向引（小说：「你负责拦住它，我负责射」），否则在一旁游走等弩箭
func _fight_armored(me: SimFighter, e: SimFighter, cmd: SimCommand, dt: float) -> void:
	var best := {}
	for br in e.breaches:
		if best.is_empty() or br.r > best.r:
			best = br
	var reach: float = SimData.ATTACKS[me.sect][0].range - 18.0
	if best.is_empty():
		var b := w.ballista
		if not b.is_empty() and b.built:
			var out: Vector2 = (e.pos - b.center).normalized() if e.pos.distance_to(b.center) > 1.0 else Vector2.UP
			var lure: Vector2 = b.center + out * 340.0
			if w.walkable(lure) and me.pos.distance_to(lure) > 20.0:
				cmd.move = w.steer(me.pos, lure)
				return
		var away := me.pos - e.pos
		if away.length() < 110.0:
			cmd.move = w.steer(me.pos, e.pos + away.normalized() * 130.0)
		return
	var dir: Vector2 = best.off.normalized()
	var spot: Vector2 = e.pos + dir * (e.radius + reach * 0.6)
	if me.pos.distance_to(spot) > 14.0 and (me.pos - e.pos).normalized().dot(dir) < 0.85:
		cmd.move = w.steer(me.pos, spot)
		return
	if (me.pos - e.pos).length() > e.radius + reach:
		cmd.move = w.steer(me.pos, spot)
		return
	cmd.aim = (e.pos - me.pos).normalized()
	_attack_hold -= dt
	if _attack_hold <= 0.0 and me.atk_cd <= 0.0:
		_attack_hold = 0.15
		cmd.press("attack")

