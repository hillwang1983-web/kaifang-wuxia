## 美术未到之前的占位场景：按美术说明的配色用色块拼出来，运行时生成贴图。
## 藏经阁（规格书第六节，Boss 二）：下半回廊（过渡段），中间门洞，上半藏经阁大厅，四周书架。
## 大雄宝殿（Boss 三）：下半寺后院子（过渡段），中间殿门，上半大殿：空佛龛、四根朱红殿柱、青砖地。
## 出身开场（960×540 单屏）：现代车间、沈家卧房、铁匠铺、茶馆后台；地面都在 (150,170)–(810,470)，门在下边正中。
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


## 单屏屋子的共用骨架：墙、地板、下边正中的门
static func _room(floor_col: Color, wall_col: Color) -> Image:
	var img := Image.create(960, 540, false, Image.FORMAT_RGB8)
	img.fill(NIGHT)
	_rect(img, Rect2i(150, 90, 660, 80), wall_col)
	_rect(img, Rect2i(130, 90, 20, 400), wall_col.darkened(0.2))
	_rect(img, Rect2i(810, 90, 20, 400), wall_col.darkened(0.2))
	_rect(img, Rect2i(150, 170, 660, 300), floor_col)
	for y in range(170, 470, 30):
		_rect(img, Rect2i(150, y, 660, 1), floor_col.darkened(0.15))
	_rect(img, Rect2i(130, 470, 700, 20), wall_col.darkened(0.2))
	_rect(img, Rect2i(440, 470, 80, 20), floor_col.lightened(0.1))  # 门
	return img


## 现代车间（四条共用的十秒）：灰水泥地、机床、配电箱
static func workshop() -> Texture2D:
	var img := _room(Color("#5E6266"), Color("#3A3F44"))
	_rect(img, Rect2i(380, 220, 200, 90), Color("#6F7F8C"))     # 机床
	_rect(img, Rect2i(400, 200, 60, 20), Color("#8A98A3"))
	_rect(img, Rect2i(700, 110, 50, 70), Color("#C9B04A"))      # 配电箱
	_rect(img, Rect2i(715, 125, 20, 6), Color("#FF3B3B"))
	for x in range(170, 800, 120):
		_rect(img, Rect2i(x, 100, 60, 8), Color("#E8E2D2"))    # 日光灯
	return ImageTexture.create_from_image(img)


## 沈家卧房：雕花床（左，枕头）、屏风、香几
static func shenjia_room() -> Texture2D:
	var img := _room(Color("#6B4A36"), Color("#8C6A4A"))
	_rect(img, Rect2i(160, 180, 140, 70), Color("#7A2E22"))     # 床
	_rect(img, Rect2i(170, 190, 40, 20), Color("#E8E2D2"))      # 枕头
	_rect(img, Rect2i(560, 110, 120, 60), Color("#C9A66B"))     # 屏风
	_rect(img, Rect2i(720, 380, 60, 40), WOOD)                  # 香几
	return ImageTexture.create_from_image(img)


## 铁匠铺：炉子、铁砧、墙上的图纸（朱砂圈）
static func forge() -> Texture2D:
	var img := _room(Color("#4A4440"), Color("#3B2A20"))
	_rect(img, Rect2i(170, 110, 90, 80), Color("#55524A"))      # 炉
	_rect(img, Rect2i(190, 140, 50, 30), Color("#FF8A3C"))
	_rect(img, Rect2i(440, 110, 80, 56), Color("#E8E2D2"))      # 图纸
	_rect(img, Rect2i(470, 120, 20, 36), Color("#4E6B58"))
	_rect(img, Rect2i(476, 128, 8, 8), Color("#C0392B"))        # 朱砂圈
	_rect(img, Rect2i(300, 360, 50, 24), Color("#2B2B2B"))      # 铁砧
	_rect(img, Rect2i(306, 384, 38, 20), Color("#55524A"))
	_rect(img, Rect2i(290, 395, 30, 6), Color("#5A1E1A"))       # 地上没擦干的血
	return ImageTexture.create_from_image(img)


## 茶馆后台：妆台铜镜、衣箱、通往台口的帘子（台口在右上，银子落在那里）
static func backstage() -> Texture2D:
	var img := _room(Color("#5A3F29"), Color("#7A2E22"))
	_rect(img, Rect2i(180, 110, 80, 50), WOOD)                  # 妆台
	_rect(img, Rect2i(200, 100, 36, 30), Color("#C9A66B"))     # 铜镜
	_rect(img, Rect2i(600, 110, 120, 60), Color("#8C3B2E"))     # 台口帘子
	_rect(img, Rect2i(630, 180, 10, 6), Color("#E8E2D2"))       # 银子
	_rect(img, Rect2i(700, 380, 80, 50), Color("#3B2A20"))      # 衣箱
	return ImageTexture.create_from_image(img)

