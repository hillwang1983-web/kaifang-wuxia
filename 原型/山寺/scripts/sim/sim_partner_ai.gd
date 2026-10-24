## AI 队友（净心、第三人，以及开发用的代玩）：和真人一样只产出 SimCommand（规格书第四节「搭档接口」的 AI 实现）。
## 会跟随、普攻、看红区闪避、走出毒池、待在毒雾安全圈里；有人被定身就用截脉解穴；
## 玩家发合击 / 阵法邀请时走进光圈响应；玄诚读条重击时、毒姥罩着毒罩时自己发邀请，
## 等玩家按合击键或走进光圈——打断和破罩要靠大家配合，不替玩家包办。
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
			cmd.move = w.steer(me.pos, inv.point) if me.pos.distance_to(inv.point) > 4.0 else Vector2.ZERO
			return cmd

	# 1.5 有人被定身：用截脉解穴（自己被定身也解自己）
	if me.utility == "jiemai" and me.cd_of("jiemai") <= 0.0:
		for h in w.heroes():
			if h.root_t > 0.4 and (h == me or h.pos.distance_to(me.pos) <= SimData.SKILLS.jiemai.range):
				cmd.press("utility")
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
		if not want and _invite_cool <= 0.0 and w.in_combat():
			want = true
		if want:
			_invite_cool = A.invite_every
			var spot := (boss.pos if boss else _target_of(me).pos if _target_of(me) else me.pos)
			cmd.press("combo")
			cmd.point = spot
			cmd.has_point = true
			_release_combo = true
			return cmd

	# 4. 打：贴近目标普攻；没有目标就跟着玩家
	var target := _target_of(me)
	if target:
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
