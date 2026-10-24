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
	check_eq(SpriteLib.resolve("chr_shaolin", "atk2", "down")[0], "atk2", "少林普攻二段已入库")
	check_eq(SpriteLib.resolve("chr_shaolin", "luohanquan", "left")[0], "atk3", "罗汉拳还没交：用普攻第三段代替")
	check_eq(SpriteLib.resolve("chr_shaolin", "jinzhongzhao", "up")[0], "atk1", "金钟罩还没交：用普攻一段代替")
	check_eq(SpriteLib.resolve("chr_shaolin", "dushazhang", "up")[0], "idle", "替代链都没有：回落到待机")
	check_eq(SpriteLib.resolve("npc_jingxin", "atk2", "up")[0], "atk", "净心普攻二段用他的一段式普攻")
	check_eq(SpriteLib.resolve("npc_jingxin", "roll", "left")[0], "roll", "净心翻滚已入库")
	check(SpriteLib.resolve("boss_dulao", "idle", "down").is_empty(), "毒姥还没交图：画代码占位")
	check_eq(SpriteLib.resolve("npc_louluo", "slash", "left")[0], "atk", "喽啰出刀用 atk（起手 2 + 出手 2）")
	check_eq(int(SpriteLib.data().sets.npc_louluo.windup.atk), 2, "喽啰出刀登记了起手帧数")
	check_eq(SpriteLib.resolve("boss_xuancheng", "sweep", "down")[0], "sweep", "玄诚横扫已入库")
	check_eq(SpriteLib.resolve("boss_xuancheng", "stagger", "left")[0], "stagger", "玄诚失衡用自己的动作条")
	check_eq(SpriteLib.resolve("npc_louluo", "stagger", "left")[0], "hit", "没有失衡条的退回受击")
	check(SpriteLib.data().sets.boss_xuancheng.windup_loop.has("heavy"), "玄诚重击读条期间循环蓄力帧")
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


## 玄诚横扫：起手 0–2，预警期间停在第 2 帧（剪影最清楚），出手后接 3–7；重击：读条两秒里 0–3 循环，砸地后接 4–8
func test_xuancheng_phases_follow_telegraph() -> void:
	var w := _world()
	var x := w.add_enemy("xuancheng", Vector2(500, 500))
	var set_: Dictionary = SpriteLib.data().sets.boss_xuancheng
	x.state = "windup"
	x.atk_id = "sweep"
	check_eq(SpriteLib.frame_of(x, set_, "sweep", 8, 0.1), 1, "横扫起手第 0.1 秒在第 1 帧")
	check_eq(SpriteLib.frame_of(x, set_, "sweep", 8, 0.7), 2, "横扫预警后段停在起手末帧（第 2 帧）")
	x.state = "recover"
	check_eq(SpriteLib.frame_of(x, set_, "sweep", 8, 0.0), 3, "出手瞬间从第 3 帧开始")
	check_eq(SpriteLib.frame_of(x, set_, "sweep", 8, 2.0), 7, "收招停在最后一帧")
	x.state = "cast"
	x.atk_id = "heavy"
	check_eq(SpriteLib.frame_of(x, set_, "heavy", 9, 0.5), 2, "重击读条循环蓄力帧（0.5 秒 = 第 6 帧 → 循环到第 2 帧）")
	check(SpriteLib.frame_of(x, set_, "heavy", 9, 1.9) < 4, "读条两秒内一直在蓄力帧里")
	x.state = "recover"
	check_eq(SpriteLib.frame_of(x, set_, "heavy", 9, 0.0), 4, "砸地从第 4 帧开始")

