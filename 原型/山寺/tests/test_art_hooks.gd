## 美术替换的接入点：特效、道具、场景都「有图用图、没图回落代码」，以后美术交了只放文件。
extends "res://tests/test_case.gd"


func _fake_strip(w: int, h: int, frames: int) -> ImageTexture:
	var img := Image.create(w * frames, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(1, 1, 1, 1))
	return ImageTexture.create_from_image(img)


func test_vfx_falls_back_without_art() -> void:
	VfxLib._cache.erase("luohanquan")
	check(not VfxLib.has("luohanquan"), "罗汉拳特效还没交：没图")
	var view := WorldView.new()
	check(not VfxLib.draw(view, "luohanquan", Vector2.ZERO, 0.0), "没图就返回假，画面照常画代码占位")
	check(not VfxLib.has("不存在的特效"), "没登记的名字不算有图")
	view.free()


func test_vfx_uses_art_when_delivered() -> void:
	VfxLib._cache["luohanquan"] = _fake_strip(32, 32, 3)
	check(VfxLib.has("luohanquan"), "放了图就有图")
	check_eq(VfxLib.frames("luohanquan"), 3, "帧数 = 图宽 ÷ 登记的帧宽")
	check(is_equal_approx(VfxLib.length("luohanquan"), 0.25), "单次特效时长 = 帧数 ÷ 12 fps")
	var view := WorldView.new()
	view._fx("burst", Vector2.ZERO, 0.18, {"vfx": "luohanquan", "r": 10.0})
	check(view.effects[-1].dur >= 0.25, "交了图的特效至少放完一遍（%.2f 秒）" % view.effects[-1].dur)
	view.free()
	VfxLib._cache.erase("luohanquan")


func test_every_vfx_name_is_registered() -> void:
	var src := FileAccess.get_file_as_string("res://scripts/game/world_view.gd")
	var names := {}
	var re2 := RegEx.new()
	re2.compile(r'(?:"vfx": |VfxLib\.draw\(self, )"([a-z_]+)"')
	for m in re2.search_all(src):
		names[m.get_string(1)] = true
	check(names.size() >= 20, "画面层挂了 %d 个特效名" % names.size())
	for n in names:
		check(VfxLib.data().effects.has(n), "特效名 %s 在 data/vfx.json 里登记了" % n)
	for lv in [1, 2, 3]:
		check(VfxLib.data().effects.has("moqi_lv%d" % lv), "默契剑气 %d 级登记了" % lv)
		check(VfxLib.data().effects.has("breach_lv%d" % lv), "裂口 %d 档登记了" % lv)


func test_scene_layers_and_walk_override() -> void:
	check(SceneLib.has_art("shanmen"), "山门底图已入库")
	check(SceneLib.foreground("shanmen") != null, "山门有前景遮挡层")
	check(not SceneLib.has_art("cangjingge"), "藏经阁还没交图")
	check(SceneLib.background("cangjingge") != null, "没交图时用代码占位底图")
	check(SceneLib.foreground("cangjingge") == null, "占位底图不配前景层")
	for s in ["cangjingge", "daxiongbaodian", "workshop", "shenjia", "tiejiang", "xiban"]:
		var d: Dictionary = SceneLib.data().scenes[s]
		check(d.has("bg") and d.has("size"), "%s 登记了底图名和地图尺寸（镜头边界）" % s)
		check(SceneLib.background(s) != null, "%s 有底图（真图或占位）" % s)
	check_eq(SceneLib.poly("cangjingge", "hall", Cangjingge.HALL), Cangjingge.HALL, "没有描边文件：用关卡代码里的多边形")
	SceneLib._walk["_t"] = {"floor": [[0, 0], [100, 0], [100, 50]], "blocks": [[[10, 10], [20, 10], [20, 20]]]}
	check_eq(SceneLib.poly("_t", "floor", []), [Vector2(0, 0), Vector2(100, 0), Vector2(100, 50)], "有描边文件就用它的地面")
	check_eq(SceneLib.polys("_t", "blocks", []).size(), 1, "也用它的碰撞块")
	check_eq(SceneLib.poly("_t", "hall", [Vector2.ONE]), [Vector2.ONE], "文件里没有的键仍用默认")
	SceneLib._walk.erase("_t")


func test_prop_and_icon_hooks() -> void:
	check(UiKit.art("obj", "obj_crate") == null, "木箱还没交图")
	UiKit._art["obj/obj_crate"] = _fake_strip(32, 32, 1)
	check(UiKit.art("obj", "obj_crate") != null, "交了木箱图就取得到（画面的 _obj 据此画图）")
	check(UiKit.art("obj", "obj_jar") == null, "酒坛没图：画面回落代码占位")
	UiKit._art.erase("obj/obj_crate")
	var old := UiKit.device
	UiKit.device = "ps"
	check(UiKit.pad_icon("attack") == null, "PS 按键图标没交时用文字")
	UiKit._art["ui/ui_pad_ps_cross"] = _fake_strip(24, 24, 1)
	check(UiKit.pad_icon("attack") != null, "交了 ui_pad_ps_cross 就用图标")
	UiKit._art.erase("ui/ui_pad_ps_cross")
	UiKit.device = "kb"
	check(UiKit.pad_icon("attack") == null, "键鼠不用手柄图标")
	UiKit.device = old
	for vfx in ["crate_broken", "jar_broken", "pile_break", "ballista_break", "chest_glow"]:
		check(VfxLib.data().effects[vfx].get("file", "").begins_with("obj/"), "%s 登记在 obj 文件夹" % vfx)


func test_ballista_five_directions() -> void:
	check_eq(WorldView.ballista_dir(Vector2.DOWN), "down", "朝下")
	check_eq(WorldView.ballista_dir(Vector2(-1, 1).normalized()), "downleft", "朝左下")
	check_eq(WorldView.ballista_dir(Vector2.LEFT), "left", "朝左")
	check_eq(WorldView.ballista_dir(Vector2(-1, -1).normalized()), "upleft", "朝左上")
	check_eq(WorldView.ballista_dir(Vector2.UP), "up", "朝上")
	check_eq(WorldView.ballista_dir(Vector2(1, -1).normalized()), "upleft", "朝右上：用左上镜像")
