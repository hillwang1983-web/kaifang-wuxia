## 一名角色在一帧里的操作指令。真人输入、AI 净心、以后的联机客户端都只产出它，
## 世界只认指令推进——这就是规格书第四节要求的「搭档接口」：响应合击的可以是真人，也可以是 AI。
class_name SimCommand
extends RefCounted

## 动作名：attack skill_1 skill_2 skill_3 utility combo dodge cancel interact
var move := Vector2.ZERO
## 瞄准方向（单位向量；零向量表示没给，按面向或自动找目标）
var aim := Vector2.ZERO
## 合击光圈 / 落点类瞄准的世界坐标（has_point 为真时有效）
var point := Vector2.ZERO
var has_point := false
var pressed := {}
var held := {}
var released := {}


func press(action: String) -> SimCommand:
	pressed[action] = true
	held[action] = true
	return self


func is_pressed(action: String) -> bool:
	return pressed.has(action)


func is_held(action: String) -> bool:
	return held.has(action)


func is_released(action: String) -> bool:
	return released.has(action)
