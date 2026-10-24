## AI 净心：和真人一样只产出 SimCommand（规格书第四节「搭档接口」的 AI 实现）。
## 会跟随、普攻、看红区闪避；玩家发合击邀请时走进光圈响应；
## 玄诚读条重击时自己发合击邀请，等玩家按合击键或走进光圈——打断要靠两人配合，不替玩家包办。
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
		if _react <= 0.0:
			cmd.move = (inv.point - me.pos).limit_length(1.0)
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
			cmd.move = to.normalized()
		else:
			cmd.aim = to.normalized()
			_attack_hold -= dt
			if _attack_hold <= 0.0 and me.atk_cd <= 0.0:
				_attack_hold = 0.15
				cmd.press("attack")
	elif leader:
		var to := leader.pos - me.pos
		if to.length() > A.follow:
			cmd.move = to.normalized() * clampf((to.length() - A.follow) / 40.0, 0.3, 1.0)
	return cmd


func _threat(me: SimFighter) -> SimFighter:
	for e in w.foes():
		if e.state == "windup" and e.atk.get("shape", "") != "field" \
				and SimEnemies.in_zone(e.atk, e.pos, e.facing, me.pos, me.radius) \
				and e.atk.tele - e.t < 0.45:
			return e
	return null


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
