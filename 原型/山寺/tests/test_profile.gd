## 存档与武功熟练度壳（规格书第三节：只存储和显示，不影响战斗）。用临时存档路径，不碰真存档。
extends "res://tests/test_case.gd"


func test_study_ticks_one_skill() -> void:
	var p := Profile.new()
	p.study("luohanquan")
	for i in 600:
		p.tick_study(1.0 / 60.0)  # 10 秒
	check_eq(p.proficiency.get("luohanquan", 0), 2, "每 5 秒 +1，十秒涨 2")
	p.study("jinzhongzhao")
	p.tick_study(5.0)
	check_eq(p.proficiency.get("luohanquan", 0), 2, "换参悟别的武功，原来的不再涨")
	check_eq(p.proficiency.get("jinzhongzhao", 0), 1, "一次只参悟一门")
	p.study("")
	p.tick_study(30.0)
	check_eq(p.proficiency.get("jinzhongzhao", 0), 1, "停止参悟后不涨")


func test_save_roundtrip() -> void:
	var old := Profile.path
	Profile.path = "user://shansi_test_profile.json"
	Profile.wipe()
	var p := Profile.new()
	var inv := SimInventory.new()
	inv.coins = 12
	var pill := SimItems.make_consumable("pill", 3)
	pill.uid = 5
	inv.add(pill)
	p.inventory = inv.to_dict()
	p.proficiency = {"luohanquan": 4}
	p.study("luohanquan")
	p.save()
	var back := Profile.load_or_new()
	check(back.exists, "读回存档")
	check_eq(SimInventory.from_dict(back.inventory).count("pill"), 3, "丹药读回")
	check_eq(SimInventory.from_dict(back.inventory).coins, 12, "金钱读回")
	check_eq(back.proficiency.get("luohanquan", 0), 4, "熟练度读回")
	check_eq(back.studying, "luohanquan", "参悟中读回")
	check(back.runs is Array, "预留多局字段")
	Profile.wipe()
	Profile.path = old
