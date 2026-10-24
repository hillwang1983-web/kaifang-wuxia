## 美术未到之前的占位场景：按美术说明的配色用色块拼出来，运行时生成贴图。
## 藏经阁（规格书第六节，Boss 二）：下半回廊（过渡段），中间门洞，上半藏经阁大厅，四周书架。
## 大雄宝殿（Boss 三）：下半寺后院子（过渡段），中间殿门，上半大殿：空佛龛、四根朱红殿柱、青砖地。
class_name PlaceholderArt
extends RefCounted

const NIGHT := Color("#1C2233")
const STONE := Color("#6E6A5E")
const STONE_DARK := Color("#55524A")
const WOOD := Color("#3B2A20")
const SCROLL := Color("#C9A66B")
const MIST := Color("#4C6B55")
const LAMP := Color("#FFC83D")
const PILLAR := Color("#7A2E22")
const BRONZE := Color("#4E6B58")


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


static func daxiongbaodian() -> Texture2D:
	var img := Image.create(1920, 1080, false, Image.FORMAT_RGB8)
	img.fill(NIGHT)
	# 大殿地面：青砖，正中一道浅色御路通向佛龛
	_rect(img, Rect2i(240, 110, 1440, 680), STONE_DARK)
	for y in range(110, 790, 40):
		for x in range(240, 1680, 64):
			_rect(img, Rect2i(x + (32 if (y / 40) % 2 else 0), y, 62, 38), STONE if (x + y) % 3 else STONE.darkened(0.1))
	_rect(img, Rect2i(920, 220, 80, 560), STONE.lightened(0.08))
	# 殿墙与空佛龛（台基碰撞在关卡里）
	_rect(img, Rect2i(240, 90, 1440, 80), WOOD)
	_rect(img, Rect2i(240, 170, 60, 610), WOOD.darkened(0.2))
	_rect(img, Rect2i(1620, 170, 60, 610), WOOD.darkened(0.2))
	_rect(img, Rect2i(820, 150, 280, 70), WOOD.lightened(0.1))
	_rect(img, Rect2i(840, 120, 240, 40), Color("#8C6A2E"))
	# 四根朱红殿柱
	for p in [Vector2i(600, 320), Vector2i(1280, 320), Vector2i(600, 600), Vector2i(1280, 600)]:
		_rect(img, Rect2i(p, Vector2i(40, 40)), PILLAR)
		_rect(img, Rect2i(p + Vector2i(0, 36), Vector2i(40, 4)), PILLAR.darkened(0.4))
	# 殿中央弩车底座的位置：一圈浅色砖
	for i in 12:
		var a := TAU * i / 12.0
		_rect(img, Rect2i(960 + int(cos(a) * 46) - 3, 620 + int(sin(a) * 26) - 2, 6, 4), STONE.lightened(0.2))
	# 殿门与院子
	_rect(img, Rect2i(900, 780, 120, 60), STONE_DARK)
	_rect(img, Rect2i(240, 780, 660, 60), PILLAR.darkened(0.45))
	_rect(img, Rect2i(1020, 780, 660, 60), PILLAR.darkened(0.45))
	_rect(img, Rect2i(600, 840, 720, 240), STONE_DARK)
	for y in range(840, 1080, 40):
		for x in range(600, 1320, 64):
			_rect(img, Rect2i(x + (32 if (y / 40) % 2 else 0), y, 62, 38), STONE.darkened(0.05))
	# 殿内长明灯
	for p in [Vector2i(320, 200), Vector2i(1590, 200), Vector2i(320, 740), Vector2i(1590, 740), Vector2i(880, 800), Vector2i(1030, 800)]:
		_rect(img, Rect2i(p, Vector2i(8, 8)), LAMP)
	return ImageTexture.create_from_image(img)

