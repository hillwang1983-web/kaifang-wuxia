## 双人合击与默契值（规格书第四节）：一人按住合击键摆光圈、松开发出邀请，
## 三秒内任一队友走进光圈或按下自己的合击键即成立；绝不做「同帧同时按」。
## 响应者是谁不重要——真人、AI 净心、以后的联机玩家都只通过 SimCommand 响应。
class_name SimCombo
extends RefCounted

const C := SimData.COMBO

var w: SimWorld
var moqi := 0               # 默契值，局内计算，所有人共享
var last_success := -999.0
var cd := 0.0
var preview := {}           # hero_id -> 光圈落点（按住合击键时）
var invite := {}            # {from, point, t, level}；空 = 没有邀请
var pending := {}           # 定格结束后要结算的合击
var muted := {}             # hero_id -> true：本局关闭合击提示（防骚扰预留，规格书第四节）
var _serial := 0


func _init(world: SimWorld) -> void:
	w = world


## 0 / 1 / 2 对应一 / 二 / 三级：零到二为一级，三到五为二级，六以上为三级
func level() -> int:
	return 0 if moqi <= 2 else (1 if moqi <= 5 else 2)


func radius(lv := -1) -> float:
	return C.radius[level() if lv < 0 else lv]


func step(dt: float, commands: Dictionary) -> void:
	cd = maxf(0.0, cd - dt)
	for h in w.heroes():
		var cmd: SimCommand = commands.get(h.id)
		if cmd == null:
			continue
		if not invite.is_empty():
			if h.id != invite.from and (cmd.is_pressed("combo") or h.pos.distance_to(invite.point) <= radius()):
				_succeed(h)
				return
			continue
		if cmd.is_pressed("combo"):
			if cd > 0.0:
				w.emit("deny", {"id": h.id, "skill": "combo", "why": "cd"})
			elif h.state == "idle" or h.state == "attack":
				preview[h.id] = h.pos + h.facing * C.preview_default
		if preview.has(h.id):
			if cmd.is_pressed("cancel") or h.state == "dodge":
				preview.erase(h.id)
				continue
			var target: Vector2 = cmd.point if cmd.has_point else (h.pos + cmd.aim.normalized() * C.preview_default if cmd.aim.length() > 0.2 else preview[h.id])
			preview[h.id] = h.pos + (target - h.pos).limit_length(C.preview_reach)
			if not cmd.is_held("combo"):
				_open_invite(h, preview[h.id])
	if not invite.is_empty():
		invite.t -= dt
		if invite.t <= 0.0:
			_timeout()


func _open_invite(h: SimFighter, point: Vector2) -> void:
	preview.clear()
	_serial += 1
	invite = {"n": _serial, "from": h.id, "point": point, "t": C.window, "level": level()}
	w.emit("combo_invite", {"id": h.id, "point": point, "window": C.window})


func _succeed(responder: SimFighter) -> void:
	var lv := level()
	moqi += 1
	if w.time - last_success < C.streak_gap:
		moqi += 1
	last_success = w.time
	pending = {"from": invite.from, "with": responder.id, "point": invite.point, "level": lv}
	invite = {}
	cd = C.cd
	w.freeze_t = C.freeze
	w.emit("combo_freeze", {"from": pending.from, "with": responder.id, "level": lv, "point": pending.point})


## 定格结束：光圈里的敌人吃伤害、读条被打断并失衡
func on_freeze_end() -> void:
	if pending.is_empty():
		return
	var lv: int = pending.level
	var src := w.fighter(pending.from)
	var r: float = C.radius[lv]
	w.emit("combo_burst", {"point": pending.point, "radius": r, "level": lv})
	for e in w.foes():
		if e.pos.distance_to(pending.point) <= r + e.radius:
			w.damage(src, e, C.dmg * C.mult[lv], {"skill": true, "interrupt": true, "stagger": C.stagger,
				"heavy": true, "knockback": 30.0, "dir": (e.pos - pending.point).normalized()})
	pending = {}


## 无人响应：退化为发起者的门派指定招式，不消耗合击冷却；默契归零
func _timeout() -> void:
	var f := w.fighter(invite.from)
	invite = {}
	moqi = 0
	w.emit("combo_timeout", {"id": f.id if f else -1})
	if f and f.alive and (f.state == "idle" or f.state == "attack"):
		w.cast_skill(f, SimData.SECTS[f.sect].fallback, 1.0, true)


## 发起者在窗口里挨了重手（≥100）算被打断：邀请作废，默契归零
func on_hero_hit(h: SimFighter, amount: float) -> void:
	if amount < 100.0:
		return
	preview.erase(h.id)
	if not invite.is_empty() and invite.from == h.id:
		invite = {}
		moqi = 0
		w.emit("combo_broken", {"id": h.id})
