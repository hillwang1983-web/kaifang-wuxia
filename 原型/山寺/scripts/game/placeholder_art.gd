## 美术未到之前的占位场景：按美术说明的配色用色块拼出来，运行时生成贴图。
## 藏经阁（规格书第六节，Boss 二）：下半回廊（过渡段），中间门洞，上半藏经阁大厅，四周书架。
class_name PlaceholderArt
extends RefCounted

const NIGHT := Color("#1C2233")
const STONE := Color("#6E6A5E")
const STONE_DARK := Color("#55524A")
const WOOD := Color("#3B2A20")
const SCROLL := Color("#C9A66B")
const MIST := Color("#4C6B55")
const LAMP := Color("#FFC83D")


static func _rect(img: Image, r: Rect2i, c: Color) -> void:
	img.fill_rect(r, c)


## 一排书架：暗木框 + 隔板上的卷轴
static func _shelf(img: Image, r: Rect2i) -> void:
	_rect(img, r, WOOD)
	var y := r.position.y + 6
	while y < r.end.y - 6:
		var x := r.position.x + 4
		while x < r.end.x - 6:
			_rect(img, Rect2i(x, y, 4, 10), SCROLL if (x / 4 + y) % 3 != 0 else SCROLL.darkened(0.3))
			x += 7
		_rect(img, Rect2i(r.position.x, y + 11, r.size.x, 2), WOOD.darkened(0.4))
		y += 16


static func cangjingge() -> Texture2D:
	var img := Image.create(1920, 1080, false, Image.FORMAT_RGB8)
	img.fill(NIGHT)
	# 大厅地面：青灰石板
	_rect(img, Rect2i(240, 120, 1440, 600), STONE_DARK)
	for y in range(120, 720, 40):
		for x in range(240, 1680, 64):
			_rect(img, Rect2i(x + (32 if (y / 40) % 2 else 0), y, 62, 38), STONE if (x + y) % 3 else STONE.darkened(0.08))
	# 四周书架（墙）
	_shelf(img, Rect2i(240, 100, 1440, 100))
	_shelf(img, Rect2i(240, 200, 60, 500))
	_shelf(img, Rect2i(1620, 200, 60, 500))
	# 大厅里的书架岛与散落经卷（碰撞在关卡里）
	_shelf(img, Rect2i(380, 620, 60, 50))
	_shelf(img, Rect2i(1480, 620, 60, 50))
	# 正中的蒲团与地上的经卷
	for i in 6:
		_rect(img, Rect2i(880 + i * 26, 260 + (i % 2) * 8, 16, 6), SCROLL)
	# 门洞与回廊
	_rect(img, Rect2i(900, 700, 120, 80), STONE_DARK)
	_rect(img, Rect2i(240, 700, 660, 80), WOOD.darkened(0.3))
	_rect(img, Rect2i(1020, 700, 660, 80), WOOD.darkened(0.3))
	_rect(img, Rect2i(600, 780, 720, 300), STONE_DARK)
	for y in range(780, 1080, 40):
		for x in range(600, 1320, 64):
			_rect(img, Rect2i(x + (32 if (y / 40) % 2 else 0), y, 62, 38), STONE.darkened(0.05))
	# 回廊柱子
	for p in [Vector2i(640, 820), Vector2i(1240, 820)]:
		_rect(img, Rect2i(p, Vector2i(40, 40)), WOOD)
	# 油灯
	for p in [Vector2i(320, 240), Vector2i(1590, 240), Vector2i(320, 660), Vector2i(1590, 660), Vector2i(880, 740), Vector2i(1030, 740)]:
		_rect(img, Rect2i(p, Vector2i(8, 8)), LAMP)
	# 地面边缘一圈雾绿：说明这里的毒雾会从四边压进来
	_rect(img, Rect2i(240, 700, 1440, 4), MIST)
	return ImageTexture.create_from_image(img)
