## 装备与掉落（规格书第七节）：品质权重、种子复现、词缀规则、格子物品栏、装备生效、敌人掉落、丹药。
extends "res://tests/test_case.gd"

const DT := 1.0 / 60.0


func _rng(seed_value: int) -> RandomNumberGenerator:
	var r := RandomNumberGenerator.new()
	r.seed = seed_value
	return r


func test_quality_weights() -> void:
	var r := _rng(1)
	var n := {"normal": 0, "magic": 0, "rare": 0}
	for i in 20000:
		n[SimItems.roll_quality(r)] += 1
	# 5:4:1 → 50% / 40% / 10%，两万次允许 ±1.5 个百分点
	check(absf(n.normal / 20000.0 - 0.5) < 0.015, "普通约五成：%s" % n)
	check(absf(n.magic / 20000.0 - 0.4) < 0.015, "魔法约四成：%s" % n)
	check(absf(n.rare / 20000.0 - 0.1) < 0.015, "稀有约一成：%s" % n)


func test_affix_rules() -> void:
	var r := _rng(2)
	for i in 500:
		var base_id: String = SimItems.data().bases.keys()[i % 8]
		var it := SimItems.roll_equipment(r, base_id)
		var rng_: Array = SimItems.data().quality[it.quality].affixes
		check(it.affixes.size() >= rng_[0] and it.affixes.size() <= rng_[1], "%s 词缀条数 %d 合乎品质" % [it.quality, it.affixes.size()])
		var seen := {}
		for a in it.affixes:
			check(not seen.has(a.id), "同一件不出重复词缀")
			seen[a.id] = true
			check(SimItems.slot_type(it) in SimItems.data().affixes[a.id].slots, "词缀 %s 允许出在 %s" % [a.id, SimItems.slot_type(it)])
			var t: Array = SimItems.data().affixes[a.id].tiers[a.tier - 1]
			check(a.value >= t[0] and a.value <= t[1], "词缀数值落在档位区间")
		for k in it.stats:
			var b: Array = SimItems.base(base_id).stats[k]
			check(it.stats[k] >= b[0] and it.stats[k] <= b[1], "底子属性落在区间")
		if it.quality == "normal":
			check(it.affixes.is_empty(), "普通无词缀")


func test_seed_reproducible() -> void:
	var a := SimItems.roll_drops(_rng(42), "xuancheng")
	var b := SimItems.roll_drops(_rng(42), "xuancheng")
	check_eq(JSON.stringify(a), JSON.stringify(b), "同种子掉落一模一样")
	# 整个世界：同种子打同样的仗，掉落也一样
	var drops := []
	for k in 2:
		var w := SimWorld.new(99)
		var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
		var b1 := w.add_enemy("xuancheng", Vector2(200, 100))
		var m := w.add_enemy("louluo", Vector2(300, 100))
		w.damage(p, m, 999, {"skill": true})
		w.damage(p, b1, 99999, {"skill": true})
		drops.append(JSON.stringify(w.ground_items))
	check_eq(drops[0], drops[1], "同种子的世界掉落一致")


func test_enemy_drops() -> void:
	var r := _rng(3)
	for i in 200:
		var d := SimItems.roll_drops(r, "louluo")
		check(d.coins >= 5 and d.coins <= 15, "喽啰掉 5–15 金钱")
		for it in d.items:
			check_eq(it.base, "pill", "喽啰只掉丹药，不掉装备")
		var bd := SimItems.roll_drops(r, "xuancheng")
		check_eq(bd.items.size(), 1, "玄诚必掉一件")
		check_eq(SimItems.slot_type(bd.items[0]), "weapon", "玄诚掉的是武器底子")


func _item(base_id: String, uid: int) -> Dictionary:
	var it := SimItems.roll_equipment(_rng(uid), base_id, "normal")
	it.uid = uid
	return it


func test_inventory_grid() -> void:
	var inv := SimInventory.new()
	var gun := _item("gun", 1)       # 1×3
	var armor := _item("pijia", 2)   # 2×2
	check(inv.add(gun), "能放下武器")
	check_eq(inv.entries[1].pos, Vector2i(0, 0), "第一件放左上角")
	check(inv.add(armor), "能放下防具")
	check_eq(inv.entries[2].pos, Vector2i(1, 0), "防具挨着放")
	check(not inv.move(1, Vector2i(9, 4)), "越界放不下（1×3 在第 5 行起会出界）")
	check(inv.move(1, Vector2i(9, 3)), "贴底边正好放得下")
	check(not inv.move(2, Vector2i(9, 0)), "2×2 放在最右一列会出界")
	# 叠堆：丹药一格叠到 20
	var p1 := SimItems.make_consumable("pill", 15)
	p1.uid = 3
	var p2 := SimItems.make_consumable("pill", 8)
	p2.uid = 4
	inv.add(p1)
	inv.add(p2)
	check_eq(inv.count("pill"), 23, "丹药总数")
	check_eq(inv.entries[3].item.count, 20, "第一格叠满 20")
	check(inv.entries.has(4) and inv.entries[4].item.count == 3, "余下 3 颗另起一格")
	# 交换：把武器拖到防具身上，两件换位
	inv.move(1, Vector2i(0, 0))
	var armor_pos: Vector2i = inv.entries[2].pos
	check(inv.move(1, armor_pos), "拖到另一件上就交换")
	check_eq(inv.entries[1].pos, armor_pos, "武器到了防具原来的位置")
	check(inv.entries[2].pos != armor_pos, "防具挪开了")
	# 塞满后放不下
	var full := SimInventory.new()
	var n := 0
	while full.add(_item("pijia", 100 + n)):
		n += 1
	check_eq(n, 15, "10×6 能放 15 件 2×2 防具")


func test_equip_applies_stats() -> void:
	var w := SimWorld.new(5)
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	var inv := w.player_inventory()
	var armor := _item("pijia", 0)
	armor.affixes = [{"id": "move_speed", "tier": 3, "value": 10.0}, {"id": "max_qi", "tier": 1, "value": 20.0}]
	var weapon := _item("gun", 0)
	weapon.affixes = [{"id": "atk", "tier": 3, "value": 10.0}]
	inv.add(w.stamp(armor))
	inv.add(w.stamp(weapon))
	check(w.inv_equip(p, armor.uid), "装上防具")
	check(w.inv_equip(p, weapon.uid), "装上武器")
	check_eq(p.max_hp, 1000.0 + armor.stats.max_hp, "生命上限加上皮甲")
	check_eq(p.hp, p.max_hp, "加上限时当前生命一起加")
	check_eq(p.max_qi, 220.0, "内力上限 +20")
	check(is_equal_approx(p.speed, 140.0 * 1.1), "移速 +10%")
	var m := w.add_enemy("louluo", Vector2(140, 100))
	w.step(DT, {p.id: SimCommand.new().press("attack")})
	var expect: float = (30.0 + weapon.stats.atk_flat) * 1.1
	check(is_equal_approx(m.max_hp - m.hp, expect) or is_equal_approx(m.max_hp - m.hp, expect * 1.5), "普攻 =（30 + 武器攻击）×1.1：实际 %s，期望 %s" % [m.max_hp - m.hp, expect])
	check(w.inv_unequip(p, "armor"), "卸下防具")
	check_eq(p.max_hp, 1000.0, "卸下后生命上限回到 1000")


func test_pickup_and_pill() -> void:
	var w := SimWorld.new(6)
	var p := w.add_hero("player", "shaolin", "jiemai", Vector2(100, 100))
	var m := w.add_enemy("louluo", Vector2(110, 100))
	w.damage(p, m, 999, {"skill": true})
	check(not w.ground_items.is_empty(), "喽啰倒下有掉落")
	w.step(DT, {p.id: SimCommand.new()})
	var inv := w.player_inventory()
	check(inv.coins >= 5, "走过去自动捡钱")
	var pill := SimItems.make_consumable("pill", 2)
	inv.add(w.stamp(pill))
	p.hp = 500.0
	w.step(DT, {p.id: SimCommand.new().press("potion")})
	check_eq(p.hp, 800.0, "丹药回 300")
	check_eq(inv.count("pill"), 1, "吃掉一颗，剩一颗")
	w.step(DT, {p.id: SimCommand.new().press("potion")})
	check_eq(p.hp, 800.0, "丹药有冷却，连按不重复吃")


func test_inventory_save_roundtrip() -> void:
	var inv := SimInventory.new()
	inv.coins = 37
	inv.add(_item("dao", 7))
	var y := _item("yupei", 8)
	inv.add(y)
	inv.equip(8, "acc1")
	var back := SimInventory.from_dict(JSON.parse_string(JSON.stringify(inv.to_dict())))
	check_eq(back.coins, 37, "金钱读回")
	check(back.entries.has(7), "格子里的刀读回")
	check_eq(back.entries[7].pos, inv.entries[7].pos, "位置读回")
	check(back.equipped.acc1 != null and int(back.equipped.acc1.uid) == 8, "装备栏读回")
