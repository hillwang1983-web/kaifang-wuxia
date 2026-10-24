## 世界里的一个角色：玩家、AI 净心、喽啰或玄诚。只存状态，不含行为。
class_name SimFighter
extends RefCounted

const HEROES := 0
const FOES := 1

var id := 0
var kind := ""        # player / partner / ally / louluo / xuancheng / dulao / jingang / 可破坏物
var team := HEROES
var name := ""
var sect := ""        # 英雄：shaolin / xiepai
var skills: Array = []  # 三主动
var utility := ""
var pos := Vector2.ZERO
var facing := Vector2.RIGHT
var radius := 12.0
var speed := 140.0
var hp := 0.0
var max_hp := 0.0
var qi := 0.0
var max_qi := 0.0
var sp := 0.0
var alive := true
var dmg_scale := 1.0
var moving := false
var stats := {}          # 装备带来的属性合计（SimItems.totals），由世界 refresh_stats 写入
var base_hp := 0.0
var base_qi := 0.0
var base_speed := 0.0

## 状态机。英雄：idle attack dodge charge aim skill mounted（在弩车上）build（拼弩车）thrown（被金刚扔出）；敌人：idle chase windup dash recover cast stagger flinch sit
var state := "idle"
var t := 0.0

# 英雄战斗计时
var atk_cd := 0.0
var combo_idx := -1
var combo_t := 0.0
var swing_t := 0.0       # 普攻 / 出招的挥动剩余时间（画面用）
var swing_kind := ""
var dodge_t := 0.0
var dodge_cd := 0.0
var dodge_dir := Vector2.ZERO
var inv_t := 0.0
var cooldowns := {}
var active_skill := ""   # 正在蓄力 / 瞄准 / 连击的招式
var charge_t := 0.0
var aim_dir := Vector2.RIGHT
var aim_point := Vector2.ZERO
var skill_hits_left := 0
var skill_hit_t := 0.0
var shield := 0.0
var shield_t := 0.0
var passive_fill := 0.0  # 少林积内力
var primed := false      # 少林积满：下一招附带硬直

# 受到的效果
var poison_stacks := 0
var poison_t := 0.0
var poison_owner := -1
var root_t := 0.0
var slow := 0.0
var stagger_t := 0.0
var hurt_t := 0.0
var flash_t := 0.0

# 敌人
var atk := {}
var atk_id := ""
var plan := ""
var read := false        # 预警末段被闪避看破
var home := Vector2.ZERO
var phase := 1
var heavy_timer := 0.0
var dash_hit := false
var ward_t := 0.0         # 毒姥：毒罩被震碎后还剩几秒（≤0 为罩着）
var target_id := -1      # 点名招式的目标（摄魂指）
var timers := {}         # Boss 自己的计时（毒蛊、摄魂指、开战时长……）；英雄被扔出时存飞行速度
var breaches: Array = []  # 铁甲金刚身上的裂口 {off 相对本体的位置, r, t, tier}
var in_combat := false
var combat_t := 0.0      # 离上次交手的时间


func is_hero() -> bool:
	return team == HEROES


## 能打、能被打：坐地（玄诚落败）和待命（剧情没放出来）都不算
func active() -> bool:
	return alive and state != "sit" and state != "wait"


func stat(key: String) -> float:
	return float(stats.get(key, 0.0))


func cd_of(skill: String) -> float:
	return cooldowns.get(skill, 0.0)


func casting() -> bool:
	return state == "cast"
