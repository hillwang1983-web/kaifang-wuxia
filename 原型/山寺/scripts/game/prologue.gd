## 出身开场（规格书第九节、第十节第八到十周）：现代车间十秒（四条共用）→ 附身醒来 → 该出身的开场演出，
## 教学三项（移动、普攻、一次闪避）嵌在里面、由在场 NPC 引导 → 拿到线索（交互）→ 出门，接山门前的进寺段。
## 四条出身共用这一个关卡，差别只在布局（下面 LAYOUTS）和台词（data/story.json）。郎中线就在原来的茶棚，
## 净心从开场就在。整段开场可以从暂停菜单「跳过开场」。出身不改任何战斗数值。
class_name Prologue
extends LevelBase

const MODERN_SECS := 10.0
## 茶棚（郎中线，按 env_chapeng_v01 描的）：茶棚前空地 + 右上山路；泥炉、两张桌凳、两根棚柱挖掉
const CHAPENG_FLOOR := [Vector2(70, 250), Vector2(110, 200), Vector2(180, 165), Vector2(460, 150), Vector2(560, 190),
	Vector2(700, 182), Vector2(745, 120), Vector2(790, 62), Vector2(862, 62), Vector2(835, 180), Vector2(785, 250),
	Vector2(765, 330), Vector2(705, 420), Vector2(668, 530), Vector2(440, 530), Vector2(420, 460),
	Vector2(330, 360), Vector2(230, 305), Vector2(120, 292)]
const CHAPENG_BLOCKS := [
	[Vector2(80, 168), Vector2(166, 168), Vector2(166, 236), Vector2(80, 236)],
	[Vector2(208, 196), Vector2(318, 196), Vector2(318, 252), Vector2(208, 252)],
	[Vector2(316, 168), Vector2(446, 168), Vector2(446, 230), Vector2(316, 230)],
	[Vector2(196, 140), Vector2(214, 140), Vector2(214, 214), Vector2(196, 214)],
	[Vector2(432, 108), Vector2(450, 108), Vector2(450, 192), Vector2(432, 192)],
]
const JINGXIN_AT := Vector2(560, 300)
## 三间屋子（沈家卧房、铁匠铺、茶馆后台）共用一块单屏地面；郎中线用茶棚的地面与遮挡
const ROOM_FLOOR := [Vector2(150, 170), Vector2(810, 170), Vector2(810, 470), Vector2(150, 470)]
## 每条出身：start 出生点；move 教学走到的位置；prop 教学打碎的东西；trainer 教闪避的在场 NPC 站位；
## info 线索（交互）的位置；exit 出口；npcs 只站着的人 [名字, 位置, 衣色]；trainer_look 引导人的衣色
const LAYOUTS := {
	"shenjia": {"start": Vector2(300, 300), "move": Vector2(660, 240), "prop": ["crate", Vector2(470, 220)],
		"trainer": Vector2(720, 260), "trainer_look": Color("#6B5A48"), "info": Vector2(230, 220), "exit": Vector2(480, 455),
		"npcs": []},
	"tiejiang": {"start": Vector2(300, 300), "move": Vector2(660, 240), "prop": ["crate", Vector2(470, 220)],
		"trainer": Vector2(720, 260), "trainer_look": Color("#7A6E62"), "info": Vector2(480, 185), "exit": Vector2(480, 455),
		"npcs": []},
	"xiban": {"start": Vector2(300, 300), "move": Vector2(660, 240), "prop": ["crate", Vector2(470, 220)],
		"trainer": Vector2(720, 260), "trainer_look": Color("#8C3B2E"), "info": Vector2(640, 190), "exit": Vector2(480, 455),
		"npcs": []},
	"langzhong": {"start": Vector2(540, 400), "move": Vector2(500, 300), "prop": ["jar", Vector2(620, 250)],
		"trainer": Vector2(700, 230), "trainer_look": Color("#2B2328"), "info": Vector2(380, 280), "exit": Vector2(812, 96),
		"npcs": [["阿萝", Vector2(380, 280), Color("#7A6E62")], ["师父", Vector2(440, 250), Color("#5A4A40")]]},
}

var layout: Dictionary
var trainer: SimFighter
var prop: SimFighter
var _modern_t := 0.0
var _clock := 0.0          # 开场用时（游戏时间），给结算和代玩计时
var _bark_i := 0


func _ready() -> void:
	if origin == "":
		origin = "langzhong"
	layout = LAYOUTS[origin]
	map_size = Vector2(960, 540)
	world = SimWorld.new(Time.get_ticks_msec())
	var langzhong := origin == "langzhong"
	world.bounds = PackedVector2Array(floor_of(origin))
	if langzhong:
		for b in CHAPENG_BLOCKS:
			world.blockers.append(PackedVector2Array(b))
	me = world.add_hero("player", sect, utility, layout.start)
	me.facing = Vector2.UP
	if langzhong:
		# 郎中线：净心从开场就在棚外蹲着，说上话之后同行（规格书第九节）
		jingxin = world.add_hero("partner", "shaolin", "", JINGXIN_AT)
		jingxin.facing = Vector2.DOWN
	prop = world.add_enemy(layout.prop[0], layout.prop[1], true)
	trainer = world.add_enemy("trainer", layout.trainer, true)
	trainer.name = Story.tutorial(origin, "dodge").who
	trainer.facing = Vector2.LEFT
	skippable = true
	build_scene(PlaceholderArt.workshop())
	partner_active = false
	if hud.mobile:
		world.bounds = mobile_bounds(floor_of(origin))  # 单屏：人不走到摇杆、按键底下（#28）
	view.trainer_look = layout.trainer_look
	stage = "modern"
	hud.objectives = []
	hud.toast("%s跳过开场" % ("暂停键里可以" if hud.mobile else "Esc 暂停菜单里可以"), MODERN_SECS)
	for line in Story.modern():
		hud.bark(line.who, line.text, MODERN_SECS / Story.modern().size())


## 现代十秒之后：白光一闪，换成出身的屋子，放上在场的人，开始醒来的对话
func _wake() -> void:
	stage = "wake"
	view.background = _room_texture()
	if origin == "langzhong":
		view.foreground = UiKit.tex("res://assets/env/env_chapeng_front_v01.png")
	view.flash = 0.6
	view.npcs = layout.npcs.map(func(n): return {"name": n[0], "pos": n[1], "robe": n[2], "hair": Color("#2B2320")})
	me.pos = layout.start
	camera.reset_smoothing()
	say(Story.wake(origin))


static func floor_of(id: String) -> Array:
	return CHAPENG_FLOOR if id == "langzhong" else ROOM_FLOOR


func _room_texture() -> Texture2D:
	match origin:
		"shenjia":
			return PlaceholderArt.shenjia_room()
		"tiejiang":
			return PlaceholderArt.forge()
		"xiban":
			return PlaceholderArt.backstage()
	return UiKit.tex("res://assets/env/env_chapeng_v01.png")


func _on_dialogue_done() -> void:
	match stage:
		"wake":
			_step("t_move")
		"info":
			_step("leave")


## 教学与流程的每一步：在场 NPC 说一句（字幕，不挡操作），任务栏换目标
func _step(s: String) -> void:
	stage = s
	match s:
		"t_move":
			_npc_says("move")
			hud.objectives = ["走到发光的地方（%s）" % ("左摇杆" if hud.mobile else "WASD / 方向键")]
			view.markers = [{"pos": layout.move}]
			_snap("open")
		"t_attack":
			view.markers = [{"pos": prop.pos}]
			prop.state = "idle"
			_npc_says("attack")
			hud.objectives = ["打碎它（%s）" % ("点「普攻」" if hud.mobile else "左键 / J")]
		"t_dodge":
			view.markers = []
			trainer.state = "chase"
			_npc_says("dodge")
			hud.objectives = ["看准红区，出手前翻滚躲开（%s）" % ("点「闪避」" if hud.mobile else "空格")]
		"t_info":
			trainer.state = "wait"
			trainer.atk = {}
			trainer.atk_id = ""
			view.markers = [{"pos": layout.info}]
			hud.objectives = ["%s（%s）" % [Story.origin(origin).info_hint, "点「交谈」" if hud.mobile else "E"]]
			hud.toast("躲得好！", 1.5)
		"info":
			view.markers = []
			hud.objectives = []
			interact_hint([])
			say(Story.info(origin))
		"leave":
			var line := Story.leave(origin)
			hud.bark(line.who, line.text, 3.0)
			hud.objectives = ["出门，去慈云寺"]
			view.markers = [{"pos": layout.exit}]
			_give_start_weapon()
			if jingxin:
				partner_active = true


func _npc_says(step: String) -> void:
	var line := Story.tutorial(origin, step)
	hud.bark(line.who, line.text, 3.5)


## 铁匠之子的起始武器是锤子（规格书第九节）；锤子没有属性，只是身份。背包里已有就不重复给
func _give_start_weapon() -> void:
	var hammer := SimItems.start_weapon(origin)
	var inv: SimInventory = world.inventories.get(me.id)
	if hammer.is_empty() or inv == null or inv.entries.values().any(func(e): return e.item.base == hammer.base):
		return
	if inv.add(world.stamp(hammer)) and inv.equipped.get("weapon") == null:
		world.inv_equip(me, int(hammer.uid), "weapon")
	hud.toast("拿上了爹的锤子", 2.0)
	_dirty = true


func after_step(dt: float) -> void:
	_clock += dt
	match stage:
		"modern":
			_modern_t += dt
			if _modern_t >= MODERN_SECS:
				_wake()
		"t_move":
			if me.pos.distance_to(layout.move) < 30.0:
				_step("t_attack")
		"t_attack":
			if not prop.alive:
				_step("t_dodge")
		"t_info":
			var near = interact_hint([[layout.info, Story.origin(origin).info_hint]])
			var pressed := Input.is_action_just_pressed("interact") or hud.touch_held.has("interact")
			if near != null and (pressed or (autoplay and me.pos.distance_to(layout.info) < 30.0)):
				_step("info")
		"leave":
			if me.pos.distance_to(layout.exit) < 36.0:
				_finish(false)


func level_events(events: Array) -> void:
	if stage != "t_dodge":
		return
	for e in events:
		# 教闪避：引导人出手时人在无敌里（翻滚硬闪），或者预警中翻滚出了范围，都算学会
		if (e.type == "evade" and e.id == me.id) or (e.type == "dodge" and e.id == me.id and trainer.state == "windup"):
			_step("t_info")
			return


## 代玩：每一步直奔目标；教闪避时等红区快落下再翻滚
func auto_command() -> SimCommand:
	var cmd := SimCommand.new()
	match stage:
		"t_move":
			walk_to(cmd, layout.move)
		"t_attack":
			if me.pos.distance_to(prop.pos) > 40.0:
				walk_to(cmd, prop.pos)
			else:
				cmd.aim = (prop.pos - me.pos).normalized()
				if me.atk_cd <= 0.0:
					cmd.press("attack")
		"t_dodge":
			if trainer.state == "windup" and trainer.t >= trainer.atk.tele - 0.25:
				cmd.move = (me.pos - trainer.pos).normalized()
				cmd.press("dodge")
		"t_info":
			walk_to(cmd, layout.info)
		"leave":
			walk_to(cmd, layout.exit)
	return cmd


## 开场演出是纯剧情段：对话停住世界（整段开场可以从暂停菜单跳过）
func dialogue_blocks() -> bool:
	return true


## 跳过开场（暂停菜单 / 开发开关 skipintro）：直接接山门前，锤子照给
func skip_intro() -> void:
	if stage == "end":
		return
	_give_start_weapon()
	_finish(true)


func _finish(skipped: bool) -> void:
	stage = "end"
	save_profile()
	done.emit({"origin": origin, "skipped": skipped, "secs": _clock})


func retry() -> void:
	revive(me, layout.start, 1.0)
	camera.reset_smoothing()


func _snap(shot_name: String) -> void:
	if get_parent() and get_parent().has_method("snap"):
		get_parent().snap(shot_name)
