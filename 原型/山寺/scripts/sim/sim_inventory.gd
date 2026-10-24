## 格子物品栏 10×6 + 装备栏四格（武器、防具、饰品两格）+ 金钱。规格书第七节。
## 武器占 1×3、防具 2×2、饰品 1×1、丹药 1×1 可叠 20。只管格子规则，不碰画面。
class_name SimInventory
extends RefCounted

const W := 10
const H := 6

var entries := {}     # uid -> {"item": 物品, "pos": Vector2i}
var equipped := {"weapon": null, "armor": null, "acc1": null, "acc2": null}
var coins := 0


func item(uid: int) -> Dictionary:
	if entries.has(uid):
		return entries[uid].item
	for s in equipped:
		if equipped[s] != null and equipped[s].uid == uid:
			return equipped[s]
	return {}


## 放得下吗：不出界、不和别的物品重叠（ignore 里的 uid 不算）
func fits(size: Vector2i, pos: Vector2i, ignore := []) -> bool:
	if pos.x < 0 or pos.y < 0 or pos.x + size.x > W or pos.y + size.y > H:
		return false
	return occupants(Rect2i(pos, size), ignore).is_empty()


func occupants(r: Rect2i, ignore := []) -> Array:
	var out := []
	for uid in entries:
		if uid in ignore:
			continue
		var e: Dictionary = entries[uid]
		if Rect2i(e.pos, SimItems.size_of(e.item)).intersects(r):
			out.append(uid)
	return out


func at_cell(cell: Vector2i) -> int:
	var o := occupants(Rect2i(cell, Vector2i.ONE))
	return o[0] if not o.is_empty() else -1


func first_fit(size: Vector2i, ignore := []) -> Vector2i:
	for y in H:
		for x in W:
			if fits(size, Vector2i(x, y), ignore):
				return Vector2i(x, y)
	return Vector2i(-1, -1)


## 收进物品栏：能叠先叠，再找第一个放得下的位置。返回是否全部收下。
func add(it: Dictionary) -> bool:
	var cap := SimItems.stack_max(it)
	if cap > 1:
		for uid in entries:
			var e: Dictionary = entries[uid]
			if e.item.base == it.base and e.item.count < cap:
				var moved := mini(cap - e.item.count, it.count)
				e.item.count += moved
				it.count -= moved
				if it.count <= 0:
					return true
	var pos := first_fit(SimItems.size_of(it))
	if pos.x < 0:
		return false
	entries[it.uid] = {"item": it, "pos": pos}
	return true


## 把格子里的物品挪到 pos；目标处正好压着另一件时两件交换位置（换得下才换）
func move(uid: int, pos: Vector2i) -> bool:
	if not entries.has(uid):
		return false
	var e: Dictionary = entries[uid]
	var size := SimItems.size_of(e.item)
	if fits(size, pos, [uid]):
		e.pos = pos
		return true
	if pos.x < 0 or pos.y < 0 or pos.x + size.x > W or pos.y + size.y > H:
		return false
	var others := occupants(Rect2i(pos, size), [uid])
	if others.size() != 1:
		return false
	var other: Dictionary = entries[others[0]]
	# 同类可叠：直接叠上去
	var cap := SimItems.stack_max(e.item)
	if cap > 1 and other.item.base == e.item.base and other.item.count < cap:
		var moved := mini(cap - other.item.count, e.item.count)
		other.item.count += moved
		e.item.count -= moved
		if e.item.count <= 0:
			entries.erase(uid)
		return true
	var old: Vector2i = e.pos
	var other_old: Vector2i = other.pos
	var other_size := SimItems.size_of(other.item)
	# 交换：自己放到 pos，对方挪到自己原来的位置（放不下就找空位，再不行就都不动）
	e.pos = pos
	other.pos = Vector2i(-99, -99)
	var spot: Vector2i = old if fits(other_size, old, [others[0]]) else first_fit(other_size, [others[0]])
	if spot.x < 0:
		e.pos = old
		other.pos = other_old
		return false
	other.pos = spot
	return true


func take(uid: int) -> Dictionary:
	if not entries.has(uid):
		return {}
	var it: Dictionary = entries[uid].item
	entries.erase(uid)
	return it


func count(base_id: String) -> int:
	var n := 0
	for uid in entries:
		if entries[uid].item.base == base_id:
			n += entries[uid].item.count
	return n


func consume(base_id: String, n := 1) -> bool:
	if count(base_id) < n:
		return false
	for uid in entries.keys():
		var e: Dictionary = entries[uid]
		if e.item.base != base_id:
			continue
		var used := mini(n, e.item.count)
		e.item.count -= used
		n -= used
		if e.item.count <= 0:
			entries.erase(uid)
		if n <= 0:
			break
	return true


## 装备：类型要对得上；槽里原来有东西就换下来放回该物品原来的位置（放不下找空位，再不行就不换）
func equip(uid: int, slot: String) -> bool:
	if not entries.has(uid) or not SimItems.EQUIP_SLOTS.has(slot):
		return false
	var it: Dictionary = entries[uid].item
	if SimItems.slot_type(it) != SimItems.EQUIP_SLOTS[slot]:
		return false
	var old_pos: Vector2i = entries[uid].pos
	entries.erase(uid)
	var prev = equipped[slot]
	if prev != null:
		var size := SimItems.size_of(prev)
		var spot := old_pos if fits(size, old_pos) else first_fit(size)
		if spot.x < 0:
			entries[uid] = {"item": it, "pos": old_pos}
			return false
		entries[prev.uid] = {"item": prev, "pos": spot}
	equipped[slot] = it
	return true


## 卸下到 pos（给 -1 就找第一个空位）
func unequip(slot: String, pos := Vector2i(-1, -1)) -> bool:
	var it = equipped.get(slot)
	if it == null:
		return false
	var size := SimItems.size_of(it)
	var spot := pos if pos.x >= 0 and fits(size, pos) else first_fit(size)
	if spot.x < 0:
		return false
	equipped[slot] = null
	entries[it.uid] = {"item": it, "pos": spot}
	return true


## 给某件格子里的装备挑一个能装的槽（饰品先空的那格）
func slot_for(it: Dictionary) -> String:
	match SimItems.slot_type(it):
		"weapon":
			return "weapon"
		"armor":
			return "armor"
		"accessory":
			return "acc1" if equipped.acc1 == null or equipped.acc2 != null else "acc2"
	return ""


func equipped_items() -> Array:
	return equipped.values().filter(func(v): return v != null)


func max_uid() -> int:
	var m := 0
	for uid in entries:
		m = maxi(m, uid)
	for v in equipped_items():
		m = maxi(m, v.uid)
	return m


# ---------- 存档 ----------

func to_dict() -> Dictionary:
	var list := []
	for uid in entries:
		list.append({"item": entries[uid].item, "x": entries[uid].pos.x, "y": entries[uid].pos.y})
	return {"coins": coins, "grid": list, "equipped": equipped.duplicate(true)}


static func from_dict(d: Dictionary) -> SimInventory:
	var inv := SimInventory.new()
	inv.coins = int(d.get("coins", 0))
	for e in d.get("grid", []):
		var it: Dictionary = e.item
		it.uid = int(it.uid)
		it.count = int(it.get("count", 1))
		inv.entries[it.uid] = {"item": it, "pos": Vector2i(int(e.x), int(e.y))}
	var eq: Dictionary = d.get("equipped", {})
	for s in inv.equipped:
		var v = eq.get(s)
		if v is Dictionary:
			v.uid = int(v.uid)
			inv.equipped[s] = v
	return inv
