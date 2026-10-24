## 茶棚（任务节点 0）：开场旁白 → 自己走到棚外蹲着的净心身边说话（看血书）→ 沿山路往右上走，净心跟上。
## 规格书第九节的教学三项嵌在这里：移动、闪避（普攻在山门第一场战斗里教）。
class_name Chapeng
extends LevelBase

## 可走地面（按 env_chapeng_v01 描的）：茶棚前空地 + 右上山路
const FLOOR := [Vector2(70, 250), Vector2(110, 200), Vector2(180, 165), Vector2(460, 150), Vector2(560, 190),
	Vector2(700, 182), Vector2(745, 120), Vector2(790, 62), Vector2(862, 62), Vector2(835, 180), Vector2(785, 250),
	Vector2(765, 330), Vector2(705, 420), Vector2(668, 530), Vector2(440, 530), Vector2(420, 460),
	Vector2(330, 360), Vector2(230, 305), Vector2(120, 292)]
## 泥炉、两张桌凳、两根棚柱
const BLOCKS := [
	[Vector2(80, 168), Vector2(166, 168), Vector2(166, 236), Vector2(80, 236)],
	[Vector2(208, 196), Vector2(318, 196), Vector2(318, 252), Vector2(208, 252)],
	[Vector2(316, 168), Vector2(446, 168), Vector2(446, 230), Vector2(316, 230)],
	[Vector2(196, 140), Vector2(214, 140), Vector2(214, 214), Vector2(196, 214)],
	[Vector2(432, 108), Vector2(450, 108), Vector2(450, 192), Vector2(432, 192)],
]
const START := Vector2(520, 500)
const JINGXIN_AT := Vector2(560, 300)
const EXIT := Vector2(812, 96)


func _ready() -> void:
	map_size = Vector2(960, 540)
	world = SimWorld.new(Time.get_ticks_msec())
	world.bounds = PackedVector2Array(FLOOR)
	for b in BLOCKS:
		world.blockers.append(PackedVector2Array(b))
	me = world.add_hero("player", sect, utility, START)
	me.facing = Vector2.UP
	jingxin = world.add_hero("partner", "shaolin", "", JINGXIN_AT)
	jingxin.facing = Vector2.DOWN
	partner_active = false   # 说上话之前他一直蹲着
	build_scene("res://assets/env/env_chapeng_v01.png", "res://assets/env/env_chapeng_front_v01.png")
	if hud.mobile:
		world.bounds = mobile_bounds(FLOOR)  # 单屏地图：手机上人不走到摇杆、按键底下（#28）
	hud.objectives = ["走到棚外的少年僧身边", "和他说话"]
	say(Story.chapeng_intro(sect))


func auto_command() -> SimCommand:
	var cmd := SimCommand.new()
	if stage == "find":
		if me.pos.distance_to(jingxin.pos) < 40.0:
			cmd.press("interact")
		else:
			walk_to(cmd, jingxin.pos)
	elif stage == "leave":
		walk_to(cmd, EXIT)
	return cmd


func after_step(_dt: float) -> void:
	if stage == "find":
		var near = interact_hint([[jingxin.pos, "说话"]])
		if near != null and (Input.is_action_just_pressed("interact") or hud.touch_held.has("interact") or autoplay):
			if autoplay and me.pos.distance_to(jingxin.pos) >= 40.0:
				return
			hud.can_talk = false
			view.hint_text = ""
			stage = "talk"
			hud.objectives = []
			say(Story.chapeng_talk())
	elif stage == "leave":
		interact_hint([])
		if me.pos.distance_to(EXIT) < 40.0:
			stage = "end"
			done.emit({})


func _on_dialogue_done() -> void:
	match stage:
		"intro":
			stage = "find"
			tip("move", "WASD / 方向键移动；走到净心身边按 E 说话" if not hud.mobile else "左摇杆移动；走到净心身边点「交谈」", 5.0)
		"talk":
			stage = "leave"
			partner_active = true
			hud.objectives = ["沿山路往右上走，去慈云寺"]
			tip("dodge", "山路上试试闪避：%s，翻滚有一瞬间刀枪不入" % ("空格" if not hud.mobile else "点「闪避」"), 5.0)


func retry() -> void:
	revive(me, START, 1.0)
	camera.reset_smoothing()
