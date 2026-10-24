## 音效与音乐（规格书第三节验收：每招独立音效）。全部由程序合成（正弦 / 方波 / 锯齿 / 噪声叠几层、加包络），
## 不用外部音频文件，没有版权问题；美术 / 音频以后交正式音效，按名字换成文件即可（见 RECIPES 的键名）。
## 三条总线：音乐 Music、音效 SFX、界面 UI，音量在暂停菜单调，存在存档的 settings 里。
## 只读世界事件，不改世界。
class_name Sfx
extends Node

const RATE := 22050
const BUSES := ["Music", "SFX", "UI"]
## 界面类声音走 UI 总线，其余走 SFX
const UI_SOUNDS := ["chime", "join", "coin", "pickup", "buzz", "chest", "tick"]

## 每层 [波形, 起始频率, 结束频率, 时长, 音量, 起始时刻]；波形 sine / square / saw / noise
const RECIPES := {
	# 普攻：棍是闷的破风，刀是带金属声的短促破风
	"staff": [["noise", 0, 0, 0.12, 0.35, 0.0], ["sine", 300, 120, 0.08, 0.3, 0.0]],
	"blade": [["noise", 0, 0, 0.09, 0.3, 0.0], ["sine", 1300, 650, 0.06, 0.2, 0.0]],
	# 命中：轻、重、架住（玄诚架势）、打在铁甲上
	"hit": [["noise", 0, 0, 0.08, 0.5, 0.0], ["sine", 170, 60, 0.12, 0.55, 0.0]],
	"hit_heavy": [["noise", 0, 0, 0.15, 0.6, 0.0], ["sine", 120, 40, 0.26, 0.8, 0.0]],
	"hit_guard": [["square", 700, 650, 0.06, 0.18, 0.0], ["noise", 0, 0, 0.05, 0.3, 0.0]],
	"hit_armor": [["sine", 900, 880, 0.28, 0.28, 0.0], ["sine", 1350, 1340, 0.2, 0.16, 0.0], ["noise", 0, 0, 0.04, 0.3, 0.0]],
	"evade": [["noise", 0, 0, 0.16, 0.25, 0.0], ["sine", 600, 950, 0.1, 0.1, 0.0]],
	# 少林三招
	"luohanquan": [["sine", 220, 80, 0.1, 0.55, 0.0], ["noise", 0, 0, 0.06, 0.35, 0.0]],
	"jinzhongzhao": [["sine", 440, 438, 0.7, 0.3, 0.0], ["sine", 660, 655, 0.6, 0.15, 0.0], ["sine", 880, 875, 0.4, 0.08, 0.0]],
	"dalijingangzhang": [["sine", 95, 38, 0.38, 0.8, 0.0], ["noise", 0, 0, 0.26, 0.4, 0.0]],
	# 邪派三招
	"dushazhang": [["noise", 0, 0, 0.2, 0.22, 0.0], ["sine", 520, 240, 0.2, 0.22, 0.0]],
	"huagongsan": [["noise", 0, 0, 0.5, 0.22, 0.0], ["sine", 230, 170, 0.45, 0.12, 0.0]],
	"shehunshu": [["saw", 300, 900, 0.4, 0.14, 0.0], ["sine", 880, 440, 0.4, 0.1, 0.0]],
	# 通用技
	"tiyunzong": [["noise", 0, 0, 0.18, 0.28, 0.0], ["sine", 800, 1600, 0.15, 0.12, 0.0]],
	"yungong": [["sine", 330, 660, 0.5, 0.2, 0.0], ["sine", 495, 990, 0.5, 0.1, 0.0]],
	"jiemai": [["sine", 1800, 1200, 0.08, 0.3, 0.0], ["square", 900, 880, 0.05, 0.1, 0.0]],
	# 打断、合击、阵法
	"clang": [["sine", 1000, 990, 0.4, 0.3, 0.0], ["sine", 1500, 1490, 0.3, 0.2, 0.0], ["noise", 0, 0, 0.05, 0.4, 0.0]],
	"chime": [["sine", 880, 880, 0.3, 0.25, 0.0], ["sine", 1320, 1320, 0.3, 0.2, 0.12]],
	"join": [["sine", 1320, 1330, 0.15, 0.22, 0.0], ["sine", 1760, 1760, 0.12, 0.12, 0.06]],
	"gong": [["sine", 110, 108, 1.0, 0.5, 0.0], ["sine", 220, 218, 0.8, 0.25, 0.0], ["noise", 0, 0, 0.1, 0.3, 0.0]],
	"gong_big": [["sine", 82, 80, 1.4, 0.6, 0.0], ["sine", 164, 162, 1.2, 0.3, 0.0], ["sine", 247, 245, 1.0, 0.15, 0.0], ["noise", 0, 0, 0.15, 0.35, 0.0]],
	# 敌人：预警、玄诚、毒姥、铁甲金刚
	"warn": [["square", 520, 520, 0.07, 0.1, 0.0]],
	"boom": [["sine", 62, 28, 0.7, 0.9, 0.0], ["noise", 0, 0, 0.4, 0.5, 0.0]],
	"dash": [["noise", 0, 0, 0.3, 0.3, 0.0], ["sine", 150, 90, 0.3, 0.3, 0.0]],
	"squelch": [["noise", 0, 0, 0.2, 0.3, 0.0], ["sine", 300, 100, 0.2, 0.3, 0.0]],
	"soul": [["saw", 200, 120, 1.2, 0.1, 0.0], ["sine", 400, 380, 1.2, 0.1, 0.0]],
	"glass": [["noise", 0, 0, 0.3, 0.4, 0.0], ["sine", 2000, 1500, 0.3, 0.2, 0.0], ["sine", 2600, 2500, 0.25, 0.15, 0.05]],
	"roar": [["saw", 90, 70, 0.8, 0.22, 0.0], ["noise", 0, 0, 0.8, 0.14, 0.0]],
	"twang": [["square", 220, 110, 0.25, 0.22, 0.0], ["noise", 0, 0, 0.08, 0.3, 0.0]],
	"crack": [["noise", 0, 0, 0.1, 0.5, 0.0], ["sine", 700, 300, 0.2, 0.3, 0.0]],
	"crash": [["noise", 0, 0, 0.6, 0.55, 0.0], ["sine", 120, 50, 0.5, 0.5, 0.0]],
	# 杂项
	"coin": [["sine", 1500, 1500, 0.08, 0.2, 0.0], ["sine", 2000, 2000, 0.1, 0.18, 0.06]],
	"pickup": [["sine", 700, 1000, 0.1, 0.2, 0.0]],
	"buzz": [["square", 150, 150, 0.12, 0.12, 0.0]],
	"gulp": [["sine", 300, 500, 0.15, 0.3, 0.0]],
	"down": [["sine", 200, 60, 0.6, 0.4, 0.0]],
	"kill": [["noise", 0, 0, 0.2, 0.3, 0.0], ["sine", 180, 60, 0.2, 0.3, 0.0]],
	"hiss": [["noise", 0, 0, 0.4, 0.22, 0.0]],
	"tick": [["square", 300, 300, 0.04, 0.08, 0.0]],
	"chest": [["sine", 660, 660, 0.2, 0.2, 0.0], ["sine", 990, 990, 0.3, 0.18, 0.1], ["sine", 1320, 1320, 0.4, 0.15, 0.2]],
}

static var _cache := {}
var world: SimWorld
var me_id := -1
var hints_muted := false     # 本局关闭合击提示：不响邀请提示音
var _players: Array[AudioStreamPlayer] = []
var _music: AudioStreamPlayer
var _next := 0
var _guide_n := -1          # 加强引导中的邀请编号：没响应前每秒再响一次提示音
var _guide_t := 0.0
var _guided := 0


static func ensure_buses() -> void:
	for b in BUSES:
		if AudioServer.get_bus_index(b) == -1:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b)
			AudioServer.set_bus_send(i, "Master")


## settings: {music, sfx, ui} 线性 0–1
static func apply_volumes(settings: Dictionary) -> void:
	ensure_buses()
	for pair in [["Music", "music"], ["SFX", "sfx"], ["UI", "ui"]]:
		var v := clampf(float(settings.get(pair[1], 0.8)), 0.0, 1.0)
		var i := AudioServer.get_bus_index(pair[0])
		AudioServer.set_bus_volume_db(i, linear_to_db(maxf(v, 0.0001)))
		AudioServer.set_bus_mute(i, v <= 0.001)


static func stream(sound: String) -> AudioStreamWAV:
	if not _cache.has(sound):
		_cache[sound] = synth(RECIPES[sound], false)
	return _cache[sound]


## 合成：各层按线性扫频与「快起、指数衰减」的包络叠加，16 位单声道
static func synth(layers: Array, loop: bool, length := 0.0) -> AudioStreamWAV:
	var dur := length
	for l in layers:
		dur = maxf(dur, float(l[5]) + float(l[3]))
	var n := int(dur * RATE)
	var buf := PackedByteArray()
	buf.resize(n * 2)
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(str(layers))
	for i in n:
		var t := float(i) / RATE
		var s := 0.0
		for l in layers:
			var lt := t - float(l[5])
			var ld: float = l[3]
			if lt < 0.0 or lt > ld:
				continue
			var env: float = minf(1.0, lt / 0.005) * (1.0 if loop else pow(1.0 - lt / ld, 2.0))
			var f0: float = l[1]
			var f1: float = l[2]
			var ph := TAU * (f0 * lt + (f1 - f0) * lt * lt / (2.0 * ld))
			var w := 0.0
			match l[0]:
				"sine":
					w = sin(ph)
				"square":
					w = 1.0 if sin(ph) >= 0.0 else -1.0
				"saw":
					w = 2.0 * fposmod(ph / TAU, 1.0) - 1.0
				"noise":
					w = rng.randf_range(-1.0, 1.0)
			s += w * env * float(l[4])
		buf.encode_s16(i * 2, int(clampf(s, -1.0, 1.0) * 32000.0))
	var st := AudioStreamWAV.new()
	st.format = AudioStreamWAV.FORMAT_16_BITS
	st.mix_rate = RATE
	st.stereo = false
	st.data = buf
	if loop:
		st.loop_mode = AudioStreamWAV.LOOP_FORWARD
		st.loop_end = n
	return st


func _ready() -> void:
	ensure_buses()
	for i in 10:
		var p := AudioStreamPlayer.new()
		p.bus = "SFX"
		add_child(p)
		_players.append(p)


func play(sound: String, volume_db := 0.0) -> void:
	if not RECIPES.has(sound):
		return
	var p := _players[_next]
	_next = (_next + 1) % _players.size()
	p.stream = stream(sound)
	p.bus = "UI" if sound in UI_SOUNDS else "SFX"
	p.volume_db = volume_db
	p.pitch_scale = randf_range(0.95, 1.05)
	p.play()


## 背景：低频持续音加一点风声，八秒一循环（音乐总线；正式配乐以后换文件）
func play_music() -> void:
	if _music:
		return
	_music = AudioStreamPlayer.new()
	_music.bus = "Music"
	if not _cache.has("_drone"):
		_cache["_drone"] = synth([["sine", 55, 55, 8.0, 0.14, 0.0], ["sine", 82.5, 82.5, 8.0, 0.08, 0.0], ["noise", 0, 0, 8.0, 0.015, 0.0]], true)
	_music.stream = _cache["_drone"]
	add_child(_music)
	_music.play()


func _process(dt: float) -> void:
	if _guide_n < 0 or world == null:
		return
	var inv := world.combo.invite
	if inv.is_empty() or inv.n != _guide_n or me_id in inv.responders or hints_muted:
		_guide_n = -1
		return
	_guide_t -= dt
	if _guide_t <= 0.0:
		_guide_t = 1.0
		play("chime", -3.0)


## 世界事件 → 声音
func handle(events: Array) -> void:
	for e in events:
		var f: SimFighter = world.fighter(e.get("id", -1)) if world else null
		match e.type:
			"swing":
				play("blade" if f and (f.sect == "xiepai") else "staff", -2.0 if e.id != me_id else 0.0)
			"skill":
				play(e.skill)
			"punch":
				play("luohanquan", -4.0)
			"hit":
				if e.dot or e.amount <= 0:
					continue
				var sound := "hit_armor" if e.get("armored", false) else ("hit_guard" if e.guarded else ("hit_heavy" if e.heavy else "hit"))
				play(sound, 0.0 if e.id == me_id or e.src == me_id else -5.0)
			"evade":
				play("evade")
			"interrupt", "deflect":
				play("clang")
			"combo_invite":
				if not (hints_muted and e.id != me_id):
					play("chime")
					if e.id != me_id and _guided < 2:
						_guided += 1
						_guide_n = world.combo.invite.get("n", -1)
						_guide_t = 1.0
			"combo_join":
				play("join")
			"combo_freeze":
				play("gong_big" if e.kind == "formation" else "gong")
			"telegraph":
				play("roar" if e.atk == "charge" else "warn", -3.0)
			"cast_start":
				play("soul" if f and f.kind == "dulao" else "warn")
			"strike":
				match e.atk:
					"sweep", "slash":
						play("staff", -3.0)
					"dash", "charge":
						play("dash")
					"gu":
						play("squelch")
			"heavy_release", "quake":
				play("boom")
			"ward_break":
				play("glass")
			"bolt_fire":
				play("twang")
			"breach":
				play("crack")
			"ballista_break":
				play("crash")
			"ballista_hit", "grab":
				play("hit_heavy")
			"part_pickup", "part_install", "build_start", "mount":
				play("pickup")
			"ballista_built":
				play("chest")
			"pickup":
				play("coin" if e.has("coins") else "pickup")
			"chest":
				play("chest")
			"pill":
				play("gulp")
			"deny":
				if e.id == me_id:
					play("buzz")
			"hero_down":
				play("down")
			"kill":
				play("kill", -4.0)
			"interact":
				play("hiss")
