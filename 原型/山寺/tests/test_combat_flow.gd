## 收尾修复（规格书第四、九节）：副本内对话不暂停世界、不吞战斗输入；合击 / 阵法定格可跳过且结果不变、可关。
## 对话那两项直接把山门关卡挂进场景树跑物理帧，用一个子类把玩家指令换成测试给的。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0


class ScriptedShanmen extends Shanmen:
	var next := SimCommand.new()

	func player_command() -> SimCommand:
		var c := next
		next = SimCommand.new()
		return c


func _shanmen() -> ScriptedShanmen:
	var lv := ScriptedShanmen.new()
	lv.setup("shaolin", "jiemai")
	lv.profile = Profile.new()   # 不传存档路径就不写盘
	tree.root.add_child(lv)
	return lv


func test_dungeon_dialogue_does_not_pause() -> void:
	var lv := _shanmen()
	check(lv.dialogue.visible and not lv.dialogue.blocking, "山门开场对话开着，而且是不阻塞的小框")
	var t0 := lv.world.time
	for i in 30:
		lv._physics_process(DT)
	check(lv.world.time > t0 + 0.4, "对话开着时世界照常走（%.2f 秒）" % (lv.world.time - t0))
	check(lv.hud.visible, "对话开着时战斗界面照常显示")
	lv.next = SimCommand.new().press("attack")
	lv._physics_process(DT)
	check_eq(lv.me.state, "attack", "对话开着时能普攻")
	for i in 30:
		lv._physics_process(DT)
	var dodge := SimCommand.new().press("dodge")
	dodge.move = Vector2.RIGHT
	lv.next = dodge
	lv._physics_process(DT)
	check_eq(lv.me.state, "dodge", "对话开着时能闪避")
	check(lv.dialogue.visible, "出手、闪避不会把对话翻掉")
	lv.free()


func test_dialogue_mini_box_reads_itself() -> void:
	var d := DialogueBox.new()
	tree.root.add_child(d)
	d.open([{"who": "净心", "text": "师父。"}, {"who": "", "text": "第二行"}], false)
	check_eq(d.mouse_filter, Control.MOUSE_FILTER_IGNORE, "不阻塞的对话不吃鼠标（点别处就是普攻）")
	for i in 60 * 3:
		d._process(DT)
	check_eq(d.index, 1, "每行到时自动往下翻")
	d.open([{"who": "", "text": "开场"}], true)
	for i in 60 * 10:
		d._process(DT)
	check(d.visible, "阻塞的开场对话不自动翻")
	d.free()


func test_swallow_only_eats_confirm_keys() -> void:
	var lv := _shanmen()
	lv.dialogue.hide()
	lv._swallow_t = 0.15
	var c := SimCommand.new().press("attack").press("dodge").press("skill_1")
	lv.next = c
	lv._physics_process(DT)
	check(not c.is_pressed("attack") and c.is_pressed("dodge") and c.is_pressed("skill_1"), "刚关掉阻塞界面：只吞确认键，闪避和技能留着")
	lv.free()


func _combo_world() -> Array:
	var w := SimWorld.new(77)
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(1920, 0), Vector2(1920, 1080), Vector2(0, 1080)])
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(500, 500))
	var j := w.add_hero("partner", "shaolin", "jiemai", Vector2(540, 500))
	var x := w.add_enemy("xuancheng", Vector2(560, 470))
	x.state = "chase"
	var press := SimCommand.new().press("combo")
	press.point = Vector2(540, 480)
	press.has_point = true
	w.step(DT, {p.id: press})
	w.step(DT, {p.id: SimCommand.new()})
	w.step(DT, {p.id: SimCommand.new(), j.id: SimCommand.new().press("combo")})
	return [w, x]


func test_freeze_skip_keeps_result() -> void:
	var full := _combo_world()
	var fast := _combo_world()
	check(full[0].freeze_t > 0.0 and fast[0].freeze_t > 0.0, "合击成立、进入定格")
	fast[0].freeze_t = 0.0001  # 关卡里按键 / 点屏幕跳过就是这么做的
	var steps_full := 0
	while full[0].freeze_t > 0.0:
		full[0].step(DT, {})
		steps_full += 1
	fast[0].step(DT, {})
	check(steps_full > 20, "不跳过要等定格走完（%d 帧）" % steps_full)
	check_eq(fast[1].hp, full[1].hp, "跳过定格：伤害一样")
	check_eq(fast[1].state, full[1].state, "跳过定格：失衡 / 打断一样")
	check_eq(fast[0].combo.moqi, full[0].combo.moqi, "跳过定格：默契一样")


func test_freeze_setting_saved() -> void:
	var p := Profile.new()
	check(p.settings.get("freeze", false), "合击定格默认开")
	check(not LevelBase.freeze_skip_pressed(), "没按键时不跳过")
