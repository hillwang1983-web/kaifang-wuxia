## 双人合击、三人阵法与默契值（规格书第四节）：一人按住合击键摆光圈、松开发出邀请，
## 三秒窗口内响应者走进光圈或按下自己的合击键；人数够了就成立。绝不做「同帧同时按」。
## 合击要 1 名响应者；阵法（formation_enabled 且队里有三人以上）要 2 名。
## 阵法窗口里只等到 1 人：退化为双人合击；一个人都没等到：退化为发起者的门派招式。
## 响应者是谁不重要——真人、AI 净心、第三人、以后的联机玩家都只通过 SimCommand 响应。
class_name SimCombo
extends RefCounted

const C := SimData.COMBO

## 世界持有合击，合击只弱引用世界，免得两个 RefCounted 互相持有、永不释放
var w: SimWorld:
	get:
		return _world.get_ref()
var moqi := 0               # 默契值，局内计算，所有人共享（合击、阵法同一套）
var last_success := -999.0
var cd := 0.0
var preview := {}           # hero_id -> 光圈落点（按住合击键时）
var invite := {}            # {n, kind, need, from, point, t, level, responders}；空 = 没有邀请
var pending := {}           # 定格结束后要结算的合击 / 阵法
var muted := {}             # hero_id -> true：本局关闭合击提示（防骚扰预留，规格书第四节）
var _serial := 0
var _world: WeakRef


func _init(world: SimWorld) -> void:
	_world = weakref(world)


## 0 / 1 / 2 对应一 / 二 / 三级：零到二为一级，三到五为二级，六以上为三级
func level() -> int:
	return 0 if moqi <= 2 else (1 if moqi <= 5 else 2)


## 当前光圈半径：阵法邀请用阵法圈，否则合击圈
func radius(lv := -1, kind := "") -> float:
	var l := level() if lv < 0 else lv
	if kind == "":
		kind = invite.get("kind", "formation" if formation_ready() else "combo")
	return C.formation_radius[l] if kind == "formation" else C.radius[l]


func formation_ready() -> bool:
	return w.formation_enabled and w.heroes().size() >= 3


func step(dt: float, commands: Dictionary) -> void:
	cd = maxf(0.0, cd - dt)
	for h in w.heroes():
		var cmd: SimCommand = commands.get(h.id)
		if cmd == null:
			continue
		if not invite.is_empty():
			if h.id != invite.from and not (h.id in invite.responders) \
					and (cmd.is_pressed("combo") or h.pos.distance_to(invite.point) <= radius()):
				invite.responders.append(h.id)
				w.emit("combo_join", {"id": h.id, "have": invite.responders.size(), "need": invite.need})
				if invite.responders.size() >= invite.need:
					_succeed(invite.kind)
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
	var kind := "formation" if formation_ready() else "combo"
	invite = {"n": _serial, "kind": kind, "need": 2 if kind == "formation" else 1, "from": h.id,
		"point": point, "t": C.window, "level": level(), "responders": []}
	w.emit("combo_invite", {"id": h.id, "point": point, "window": C.window, "kind": kind})


func _succeed(kind: String) -> void:
	var lv := level()
	moqi += 1
	if w.time - last_success < C.streak_gap:
		moqi += 1
	# 默契获取加成（装备词缀）：参与者里取最高的，按概率多加一点
	var gain := 0.0
	for id in [invite.from] + invite.responders:
		var f := w.fighter(id)
		if f:
			gain = maxf(gain, f.stat("moqi_gain"))
	if gain > 0.0 and w.rng.randf() < gain / 100.0:
		moqi += 1
	last_success = w.time
	pending = {"kind": kind, "from": invite.from, "with": invite.responders.duplicate(), "point": invite.point, "level": lv}
	invite = {}
	cd = C.formation_cd if kind == "formation" else C.cd
	w.freeze_t = C.freeze
	w.emit("combo_freeze", {"kind": kind, "from": pending.from, "with": pending.with, "level": lv, "point": pending.point})


## 定格结束：光圈里的敌人吃伤害、读条被打断并失衡；附近的毒罩被震碎（阵法 10 秒、合击 5 秒）
func on_freeze_end() -> void:
	if pending.is_empty():
		return
	var lv: int = pending.level
	var kind: String = pending.kind
	var src := w.fighter(pending.from)
	var r := radius(lv, kind)
	var mult: float = C.mult[lv] * (C.formation_mult if kind == "formation" else 1.0)
	w.emit("combo_burst", {"point": pending.point, "radius": r, "level": lv, "kind": kind})
	for e in w.foes():
		if e.pos.distance_to(pending.point) <= r + e.radius:
			var boost := 1.0 + (src.stat("combo_dmg") / 100.0 if src else 0.0)
			w.damage(src, e, C.dmg * mult * boost, {"skill": true, "interrupt": true, "stagger": C.stagger,
				"heavy": true, "knockback": 30.0, "dir": (e.pos - pending.point).normalized()})
	w.break_wards(pending.point, r, C.break_formation if kind == "formation" else C.break_combo)
	pending = {}


## 窗口到了人还不够：阵法只等到一人就退化为双人合击；一个人都没等到，退化为发起者的门派招式
## （不消耗合击冷却），默契归零
func _timeout() -> void:
	if invite.kind == "formation" and invite.responders.size() >= 1:
		w.emit("formation_degrade", {"id": invite.from})
		_succeed("combo")
		return
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
