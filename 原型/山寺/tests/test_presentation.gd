## 表现层（规格书第三、四、五节）：帧动画按登记读图与回落、每招独立音效与特效、音量总线、
## 手柄按键提示按 Xbox / PS 切换、本局关闭合击提示不影响合击本身。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0


func _world() -> SimWorld:
	var w := SimWorld.new(3)
	w.bounds = PackedVector2Array([Vector2(0, 0), Vector2(1920, 0), Vector2(1920, 1080), Vector2(0, 1080)])
	return w


func test_sprite_lib_reads_delivered_strips() -> void:
	var idle := SpriteLib.strip("chr_shaolin", "idle", "down")
	check(idle != null, "少林待机条已入库，能读到")
	check_eq(idle.get_width() / 48, 4, "少林待机 4 帧")
	check_eq(SpriteLib.strip("chr_shaolin", "walk", "left").get_width() / 48, 6, "少林行走 6 帧")
	check_eq(SpriteLib.resolve("chr_shaolin", "atk1", "down")[0], "idle", "少林普攻还没交：回落到待机")
	check_eq(SpriteLib.resolve("npc_jingxin", "atk2", "up")[0], "atk", "净心普攻二段用他的一段式普攻")
	check_eq(SpriteLib.resolve("npc_jingxin", "roll", "left")[0], "roll", "净心翻滚已入库")
	check(SpriteLib.resolve("boss_dulao", "idle", "down").is_empty(), "毒姥还没交图：画代码占位")
	check_eq(SpriteLib.dir_for(Vector2.RIGHT), "right", "朝右用左侧镜像")
	check_eq(SpriteLib.dir_for(Vector2(0.2, -1)), "up", "朝上")
	for k in SpriteLib.data().sets:
		var s: Dictionary = SpriteLib.data().sets[k]
		check(s.frame.size() == 2 and s.anchor.size() == 2, "%s 登记了帧尺寸与锚点" % k)


func test_sprite_actions_follow_state() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	check_eq(SpriteLib.action_for(p), "idle", "站着：待机")
	p.moving = true
	check_eq(SpriteLib.action_for(p), "walk", "走动：行走")
	p.state = "dodge"
	check_eq(SpriteLib.action_for(p), "roll", "闪避：翻滚")
	p.state = "idle"
	p.hurt_t = 0.2
	check_eq(SpriteLib.action_for(p), "hit", "挨打：受击")
	p.alive = false
	check_eq(SpriteLib.action_for(p), "down", "倒下")


func test_every_move_has_its_own_sound() -> void:
	var seen := {}
	for s in SimData.SKILLS:
		check(Sfx.RECIPES.has(s), "%s 有音效" % s)
		var key := str(Sfx.RECIPES.get(s, []))
		check(not seen.has(key), "%s 的音效和 %s 不一样" % [s, seen.get(key, "")])
		seen[key] = s
	for k in ["staff", "blade", "gong", "gong_big", "chime", "boom", "soul", "squelch", "roar", "twang", "crack", "glass"]:
		check(Sfx.RECIPES.has(k), "%s 有音效（普攻 / 合击 / 阵法 / Boss 招式）" % k)
	var wav := Sfx.stream("luohanquan")
	check(wav.data.size() > 1000, "程序合成出了音频数据")


func test_audio_buses_and_volume() -> void:
	Sfx.apply_volumes({"music": 0.5, "sfx": 0.0, "ui": 1.0})
	for b in Sfx.BUSES:
		check(AudioServer.get_bus_index(b) != -1, "有 %s 总线" % b)
	check(AudioServer.is_bus_mute(AudioServer.get_bus_index("SFX")), "音效拉到 0 就静音")
	check(is_equal_approx(AudioServer.get_bus_volume_db(AudioServer.get_bus_index("UI")), 0.0), "界面音量 1 = 0 dB")


func test_every_move_has_its_own_effect() -> void:
	var view := WorldView.new()
	for sect in ["shaolin", "xiepai"]:
		for skill in SimData.SECTS[sect].skills + SimData.UTILITIES:
			var w := _world()
			var p := w.add_hero("player", sect, "jiemai", Vector2(500, 500))
			w.add_enemy("louluo", Vector2(540, 500))
			view.world = w
			view.effects.clear()
			w.cast_skill(p, skill, 1.0, true)
			for i in 30:
				w.step(DT, {})
			for e in w.events:
				view._on_event(e)
			var shown := not view.effects.is_empty() or not w.pools.is_empty() or p.shield > 0.0
			check(shown, "%s · %s 有自己的特效" % [sect, skill])
	view.free()


func test_pad_prompts_switch() -> void:
	check_eq(UiKit.pad_kind("PS5 Controller"), "ps", "PS5 手柄认作 PS")
	check_eq(UiKit.pad_kind("DualSense Wireless Controller"), "ps", "DualSense 认作 PS")
	check_eq(UiKit.pad_kind("Xbox Series Controller"), "xbox", "Xbox 手柄")
	var old := UiKit.device
	UiKit.device = "ps"
	check_eq(UiKit.key("attack"), "×", "PS：普攻 ×")
	UiKit.device = "xbox"
	check_eq(UiKit.key("combo"), "RT", "Xbox：合击 RT")
	UiKit.device = "kb"
	check_eq(UiKit.key("combo"), "F", "键鼠：合击 F")
	UiKit.device = old


func test_muted_hints_keep_combo_working() -> void:
	var w := _world()
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(500, 500))
	var j := w.add_hero("partner", "shaolin", "jiemai", Vector2(700, 500))
	w.combo.muted[p.id] = true
	var press := SimCommand.new().press("combo")
	press.point = Vector2(600, 500)
	press.has_point = true
	w.step(DT, {j.id: press})
	w.step(DT, {j.id: SimCommand.new()})
	check(not w.combo.invite.is_empty(), "关了提示照样收到邀请")
	w.step(DT, {p.id: SimCommand.new().press("combo")})
	check(w.freeze_t > 0.0, "关了提示照样能按合击键响应")
