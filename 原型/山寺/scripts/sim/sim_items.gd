## 物品 = 底子 + 品质 + 词缀（规格书第七节，暗黑二式）。数值全在 res://data/items.json。
## 物品是普通 Dictionary，便于存档和以后联机下发：
##   {uid, base, quality, stats: {属性: 数值}, affixes: [{id, tier, value}], count}
## 生成只用传进来的随机数发生器，同一个种子结果可复现（掉落由世界生成，表现层只显示）。
class_name SimItems
extends RefCounted

const DATA_PATH := "res://data/items.json"
const EQUIP_SLOTS := {"weapon": "weapon", "armor": "armor", "acc1": "accessory", "acc2": "accessory"}

static var _data := {}


static func data() -> Dictionary:
	if _data.is_empty():
		_data = JSON.parse_string(FileAccess.get_file_as_string(DATA_PATH))
	return _data


static func base(id: String) -> Dictionary:
	var d := data()
	return d.bases.get(id, d.consumables.get(id, {}))


static func is_equipment(item: Dictionary) -> bool:
	return data().bases.has(item.base)


static func slot_type(item: Dictionary) -> String:
	return base(item.base).get("slot", "")


static func size_of(item: Dictionary) -> Vector2i:
	var s: Array = base(item.base).size
	return Vector2i(int(s[0]), int(s[1]))


static func stack_max(item: Dictionary) -> int:
	return int(base(item.base).get("stack", 1))


## 按权重抽一个键
static func _weighted(rng: RandomNumberGenerator, weights: Dictionary) -> String:
	var total := 0.0
	for k in weights:
		total += float(weights[k])
	var r := rng.randf() * total
	for k in weights:
		r -= float(weights[k])
		if r < 0.0:
			return k
	return weights.keys()[-1]


static func roll_quality(rng: RandomNumberGenerator, weights := {}) -> String:
	if weights.is_empty():
		for q in data().quality:
			weights[q] = data().quality[q].weight
	return _weighted(rng, weights)


static func _roll_value(rng: RandomNumberGenerator, lo: float, hi: float) -> float:
	# 整数区间取整数，带小数的区间取到 0.5
	if is_equal_approx(lo, roundf(lo)) and is_equal_approx(hi, roundf(hi)):
		return float(rng.randi_range(int(lo), int(hi)))
	return snappedf(rng.randf_range(lo, hi), 0.5)


## 生成一件装备。quality 留空按 5:4:1 抽。词缀同一条不重复。
static func roll_equipment(rng: RandomNumberGenerator, base_id: String, quality := "") -> Dictionary:
	var b := base(base_id)
	if quality == "":
		quality = roll_quality(rng)
	var item := {"uid": 0, "base": base_id, "quality": quality, "stats": {}, "affixes": [], "count": 1}
	for k in b.stats:
		item.stats[k] = _roll_value(rng, b.stats[k][0], b.stats[k][1])
	var range_: Array = data().quality[quality].affixes
	var n := rng.randi_range(int(range_[0]), int(range_[1]))
	var pool := []
	for a in data().affixes:
		if b.slot in data().affixes[a].slots:
			pool.append(a)
	var tier_w := {}
	for i in data().tier_weights.size():
		tier_w[str(i)] = data().tier_weights[i]
	for i in mini(n, pool.size()):
		var a: String = pool.pop_at(rng.randi_range(0, pool.size() - 1))
		var tier := int(_weighted(rng, tier_w))
		var t: Array = data().affixes[a].tiers[tier]
		item.affixes.append({"id": a, "tier": tier + 1, "value": _roll_value(rng, t[0], t[1])})
	return item


static func make_consumable(base_id: String, count := 1) -> Dictionary:
	return {"uid": 0, "base": base_id, "quality": "normal", "stats": {}, "affixes": [], "count": count}


## 某个槽位能出的底子
static func bases_for_slot(slot: String) -> Array:
	var out := []
	for k in data().bases:
		if data().bases[k].slot == slot:
			out.append(k)
	out.sort()
	return out


## 敌人掉落：{"coins": n, "items": [...]}。喽啰掉丹药与金钱，不掉装备；玄诚必掉一件武器底子。
static func roll_drops(rng: RandomNumberGenerator, kind: String) -> Dictionary:
	var out := {"coins": 0, "items": []}
	var d: Dictionary = data().drops.get(kind, {})
	if d.has("coin"):
		out.coins = rng.randi_range(int(d.coin[0]), int(d.coin[1]))
	if d.has("pill_chance") and rng.randf() < float(d.pill_chance):
		out.items.append(make_consumable("pill"))
	if d.has("slot"):
		var options := bases_for_slot(d.slot)
		out.items.append(roll_equipment(rng, options[rng.randi_range(0, options.size() - 1)]))
	return out


## 一组装备的属性合计（底子属性 + 词缀，同名相加）
static func totals(items: Array) -> Dictionary:
	var out := {}
	for it in items:
		if it == null:
			continue
		for k in it.stats:
			out[k] = out.get(k, 0.0) + float(it.stats[k])
		for a in it.affixes:
			out[a.id] = out.get(a.id, 0.0) + float(a.value)
	return out


# ---------- 显示用（表现层读） ----------

static func display_name(item: Dictionary) -> String:
	var n: String = base(item.base).name
	if item.get("count", 1) > 1:
		n += " ×%d" % item.count
	return n


static func quality_name(item: Dictionary) -> String:
	return data().quality[item.quality].name


static func quality_color(item: Dictionary) -> Color:
	return Color(data().quality[item.quality].color)


static func stat_line(key: String, value: float) -> String:
	var s: Dictionary = data().stats[key]
	return s.name + " " + (s.fmt % value)


## 悬停说明：名称行之外的若干行
static func describe(item: Dictionary) -> Array:
	var lines := []
	var b := base(item.base)
	if is_equipment(item):
		lines.append({"weapon": "兵器", "armor": "防具", "accessory": "饰品"}.get(b.slot, "") + " · " + quality_name(item))
		for k in item.stats:
			lines.append(stat_line(k, item.stats[k]))
		for a in item.affixes:
			lines.append("◆ " + stat_line(a.id, a.value) + "（%d档）" % a.tier)
	elif item.base == "pill":
		lines.append("服用回复生命 %d · 可叠 %d" % [b.heal, b.stack])
	return lines
