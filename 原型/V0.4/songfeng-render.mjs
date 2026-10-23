const rect = (c, x, y, w, h, color) => { c.fillStyle = color; c.fillRect(Math.round(x), Math.round(y), w, h); };
const ellipse = (c, x, y, rx, ry, color) => { c.fillStyle = color; c.beginPath(); c.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2); c.fill(); };
const poly = (c, points, color) => { c.fillStyle = color; c.beginPath(); points.forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y)); c.closePath(); c.fill(); };
const clamp = (x, a, b) => a > b ? (a + b) / 2 : Math.max(a, Math.min(b, x));

// 三条不同的剑尖轨迹；只用于表现，不参与命中与位移计算。
const swordPaths = [
  [[5, -22], [38, -118], [150, -60], [75, 65]],
  [[6, 28], [86, 78], [148, 10], [45, -57]],
  [[12, -76], [79, -63], [119, 12], [94, 72]],
];
export function swordPoint(combo, t) {
  const p = swordPaths[combo - 1], u = 1 - t;
  return [0, 1].map(axis => .86 * (u * u * u * p[0][axis] + 3 * u * u * t * p[1][axis] + 3 * u * t * t * p[2][axis] + t * t * t * p[3][axis]));
}
export const swingHead = progress => 1 - Math.pow(1 - clamp((progress - .08) / .77, 0, 1), 2.2);
const arrowLift = 12;
const smooth = value => { const t = clamp(value, 0, 1); return t * t * (3 - 2 * t); };
const angleDelta = (from, to) => Math.atan2(Math.sin(to - from), Math.cos(to - from));

function blendPose(from, to, t) {
  const pose = { ...to, hand: { x: from.hand.x + (to.hand.x - from.hand.x) * t, y: from.hand.y + (to.hand.y - from.hand.y) * t } };
  for (const key of ['lean', 'crouch', 'twist', 'stance']) pose[key] = from[key] + (to[key] - from[key]) * t;
  pose.angle = from.angle + angleDelta(from.angle, to.angle) * t;
  const length = pose.bladeLength + 3;
  pose.tip = { x: pose.hand.x + Math.cos(pose.angle) * length, y: pose.hand.y + Math.sin(pose.angle) * length };
  return pose;
}

export function sampleHeroPose(face, strike) {
  const idle = { face, lean: 0, crouch: 0, twist: 0, stance: 0, bladeLength: 52,
    hand: { x: Math.cos(face) * 12, y: -23 + Math.sin(face) * 6 }, angle: face + .55 };
  idle.tip = { x: idle.hand.x + Math.cos(idle.angle) * 55, y: idle.hand.y + Math.sin(idle.angle) * 55 };
  if (!strike) return idle;
  const p = clamp(strike.progress, 0, 1), direction = strike.face, heavy = strike.combo === 3;
  const prepare = Math.sin(Math.PI * clamp(p / .35, 0, 1)), drive = Math.sin(Math.PI * clamp((p - .18) / .82, 0, 1));
  const point = swordPoint(strike.combo, swingHead(Math.max(.18, p)));
  const tip = { x: Math.cos(direction) * point[0] - Math.sin(direction) * point[1] * .84,
    y: -18 + Math.sin(direction) * point[0] + Math.cos(direction) * point[1] * .84 };
  const angle = Math.atan2(tip.y + 18, tip.x);
  const pose = { face, bladeLength: 52, tip, angle,
    hand: { x: tip.x - Math.cos(angle) * 55, y: tip.y - Math.sin(angle) * 55 },
    lean: -prepare * 2 + drive * (heavy ? 5 : 3), crouch: prepare * (heavy ? 3.5 : 1.6) + drive * 1.3,
    twist: (strike.combo === 2 ? -1 : 1) * (-prepare * .24 + drive * .28), stance: (prepare + drive) * (heavy ? 5 : 2.5) };
  if (p < .18) {
    const ready = blendPose(idle, pose, smooth(p / .18));
    for (const key of ['lean', 'crouch', 'twist', 'stance']) ready[key] = pose[key];
    return ready;
  }
  return pose;
}

export function advanceHeroMotion(motion, g) {
  const swing = g.swings.at(-1);
  if (motion.elapsed === undefined || g.elapsed < motion.elapsed || g.stats.attacks < motion.attacks) {
    motion.face = swing?.face ?? g.p.face; motion.pose = sampleHeroPose(motion.face);
    motion.swing = null; motion.lastStrike = null; motion.recovery = .16; motion.elapsed = g.elapsed;
  }
  const dt = clamp(g.elapsed - motion.elapsed, 0, .05); motion.elapsed = g.elapsed; motion.attacks = g.stats.attacks;
  if (g.paused || (g.hitstop > 0 && motion.swing === (swing ?? null) && motion.age === swing?.age)) return motion.pose;
  const target = swing?.face ?? g.p.face;
  motion.face += angleDelta(motion.face, target) * (1 - Math.exp(-dt * 28));
  if (swing) {
    const progress = swing.age / (swing.combo === 3 ? .35 : .24);
    if (motion.swing !== swing) { motion.windupFrom = motion.pose; motion.swing = swing; }
    motion.lastStrike = { face: swing.face, combo: swing.combo, progress: 1 }; motion.recovery = 0;
    const pose = sampleHeroPose(motion.face, { ...motion.lastStrike, progress });
    motion.pose = progress < .18 ? blendPose(motion.windupFrom, pose, smooth(progress / .18)) : pose;
  } else if (motion.lastStrike && motion.recovery < .16) {
    motion.recovery = Math.min(.16, motion.recovery + dt);
    motion.pose = blendPose(sampleHeroPose(motion.face, motion.lastStrike), sampleHeroPose(motion.face), smooth(motion.recovery / .16));
  } else motion.pose = sampleHeroPose(motion.face);
  motion.age = swing?.age; return motion.pose;
}

function blendEnemyPose(from, to, t) {
  return { ...blendPose(from, to, t), offHand: { x: from.offHand.x + (to.offHand.x - from.offHand.x) * t,
    y: from.offHand.y + (to.offHand.y - from.offHand.y) * t } };
}

// 全部进度读取现有前摇、收招、硬直和死亡计时，不另起一套战斗时钟。
export function sampleEnemyPose(e, face = e.face) {
  const attacking = e.mode === 'windup' || e.mode === 'recover', direction = attacking ? e.attackFace : face;
  const f = Math.cos(direction), d = Math.sin(direction), archer = e.type === 'archer';
  const idle = { face, lean: 0, crouch: 0, twist: 0, stance: 0, bladeLength: 38, angle: direction + .55,
    hand: { x: f * 12, y: -23 + d * 6 }, offHand: { x: -13, y: -16 },
    hitX: 0, hitY: 0, roll: 0, fall: 0, alpha: 1, draw: 0, strikeProgress: null };
  idle.tip = { x: idle.hand.x + Math.cos(idle.angle) * 41, y: idle.hand.y + Math.sin(idle.angle) * 41 };
  if (archer) {
    const pull = e.mode === 'windup' ? smooth((.75 - e.timer) / .6) : 0;
    const age = e.mode === 'recover' ? 1.15 - e.timer : 0, settle = 1 - smooth((age - .16) / .32);
    const draw = e.mode === 'recover' ? Math.sin(age * 95) * Math.exp(-age * 30) * .2 : pull;
    const grip = e.mode === 'recover' ? 12 + (-16 - Math.sin(Math.PI * clamp(age / .2, 0, 1)) * 9) * settle : 12 - pull * 16;
    return { ...idle, angle: direction, draw, lean: -pull * 2 - (e.mode === 'recover' ? settle : 0),
      crouch: pull * 1.5, stance: attacking ? 3 : 0, twist: pull * .2,
      hand: { x: f * 18, y: -10 - arrowLift + d * 18 }, offHand: { x: f * grip, y: -10 - arrowLift + d * grip } };
  }
  const strike = progress => {
    const point = swordPoint(1, swingHead(progress));
    const tip = { x: f * point[0] * .74 - d * point[1] * .6, y: -18 + d * point[0] * .74 + f * point[1] * .6 };
    const angle = Math.atan2(tip.y + 18, tip.x), drive = Math.sin(Math.PI * (progress - .18) / .82);
    return { ...idle, tip, angle, hand: { x: tip.x - Math.cos(angle) * 41, y: tip.y - Math.sin(angle) * 41 },
      lean: 2 + drive * 3, crouch: 1.5, twist: .32 * drive, stance: 4, strikeProgress: progress };
  };
  if (e.mode === 'windup') {
    const q = clamp(1 - e.timer / .62, 0, 1);
    const raised = { ...idle, hand: { x: -f * 14 - d * 12, y: -35 - d * 9 - f * 9 },
      angle: direction - 1.7, lean: -3, crouch: 3, twist: -.32, stance: 4 };
    const pose = blendEnemyPose(idle, raised, smooth(q / .55));
    return { ...blendEnemyPose(pose, strike(.42), smooth((q - .8) / .2)), strikeProgress: null };
  }
  if (e.mode === 'recover') {
    const age = .72 - e.timer;
    if (age <= .22) return strike(.42 + .58 * clamp(age / .22, 0, 1));
    return { ...blendEnemyPose(strike(1), idle, smooth((age - .22) / .25)), strikeProgress: null };
  }
  return idle;
}

export function advanceEnemyMotion(motion, g, e) {
  if (motion.entity !== e || g.elapsed < motion.elapsed) {
    Object.assign(motion, { entity: e, face: e.face, hp: e.maxHp, elapsed: g.elapsed, walk: e.walk,
      hitFace: e.face + Math.PI, heavy: false, hitPose: null, fallPose: null, pose: sampleEnemyPose(e), gait: 0 });
  }
  const dt = clamp(g.elapsed - motion.elapsed, 0, .05); motion.elapsed = g.elapsed;
  if (g.paused || (g.hitstop > 0 && e.hp === motion.hp && e.stagger === motion.stagger && e.dead === motion.dead)) return motion.pose;
  if (e.hp < motion.hp) {
    const spark = g.fx.filter(f => f.kind === 'spark' && Math.hypot(f.x - e.x, f.y + 15 - e.y) < 32)
      .sort((a, b) => Math.hypot(a.x - e.x, a.y + 15 - e.y) - Math.hypot(b.x - e.x, b.y + 15 - e.y))[0];
    motion.hitFace = spark?.face ?? motion.hitFace; motion.heavy = spark?.heavy ?? false;
    motion.hitPose = motion.pose;
    if (e.hp <= 0) motion.fallPose = motion.pose;
  }
  motion.hp = e.hp; motion.stagger = e.stagger; motion.dead = e.dead;
  const locked = e.mode === 'windup' || e.mode === 'recover';
  motion.face += angleDelta(motion.face, locked ? e.attackFace : e.face) * (1 - Math.exp(-dt * 22));
  const walking = e.hp > 0 && e.mode === 'idle' && e.stagger <= 0 && e.walk > motion.walk;
  motion.gait += ((walking ? Math.sin(e.walk * 19) : 0) - motion.gait) * (1 - Math.exp(-dt * 24)); motion.walk = e.walk;
  let pose = sampleEnemyPose(e, motion.face);
  if (e.hp <= 0) {
    const age = .7 - e.dead, fall = smooth((age - .06) / .34), sign = Math.cos(motion.hitFace) < 0 ? -1 : 1;
    pose = { ...(motion.fallPose || pose), strikeProgress: null, draw: 0, gait: 0, fall,
      crouch: 5 * smooth(age / .13), roll: sign * fall * 1.48,
      hitX: Math.cos(motion.hitFace) * 6 * fall, hitY: Math.sin(motion.hitFace) * 5 * fall,
      alpha: smooth(e.dead / .16) };
  } else if (e.stagger > 0 && motion.hitPose) {
    const remaining = clamp(e.stagger / (motion.heavy ? .43 : .23), 0, 1), kick = Math.pow(remaining, .65);
    pose = blendEnemyPose(motion.hitPose, pose, smooth((1 - remaining - .2) / .8));
    pose = { ...pose, strikeProgress: null, gait: 0, lean: -kick * 4, crouch: pose.crouch + kick * 3,
      hitX: Math.cos(motion.hitFace) * kick * (motion.heavy ? 5 : 3), hitY: Math.sin(motion.hitFace) * kick * 2,
      roll: Math.cos(motion.hitFace) * kick * .14 };
  }
  motion.pose = { ...pose, gait: pose.gait ?? motion.gait }; return motion.pose;
}

function bladeRibbon(c, combo, tail, head, width, color) {
  if (head <= tail) return;
  const left = [], right = [];
  for (let i = 0; i <= 22; i++) {
    const u = i / 22, t = tail + (head - tail) * u, point = swordPoint(combo, t);
    const ahead = swordPoint(combo, Math.min(1, t + .002)), behind = swordPoint(combo, Math.max(0, t - .002));
    const dx = ahead[0] - behind[0], dy = ahead[1] - behind[1], length = Math.hypot(dx, dy) || 1;
    const taper = Math.pow(Math.sin(Math.PI * u), .7) * (.38 + .62 * u) * width;
    left.push([point[0] - dy / length * taper, point[1] + dx / length * taper]);
    right.push([point[0] + dy / length * taper, point[1] - dx / length * taper]);
  }
  poly(c, [...left, ...right.reverse()], color);
}

function sword(c, x, y, angle, length = 38) {
  c.save(); c.translate(x, y); c.rotate(angle);
  rect(c, -8, -2, 12, 4, '#543d2c'); rect(c, 0, -7, 4, 14, '#ddb96d');
  poly(c, [[4, -3], [length - 5, -3], [length + 3, 0], [length - 5, 3], [4, 3]], '#eaf6db');
  rect(c, 5, 0, length - 9, 2, '#81b4b3'); c.restore();
}

function person(c, e, pose) {
  const archer = e.type === 'archer', f = Math.cos(pose.face), d = Math.sin(pose.face), gait = pose.gait;
  const coat = archer ? '#8d713c' : '#964e3d', light = archer ? '#b29a59' : '#c47752', dark = archer ? '#53452e' : '#593d32';
  const hipX = pose.twist * 4, hipY = -12 + pose.crouch, chestX = hipX + f * pose.lean + gait, chestY = -28 + pose.crouch;
  const shoulders = [{ x: chestX - 9 + pose.twist * 7, y: chestY + pose.twist * 5 },
    { x: chestX + 9 + pose.twist * 7, y: chestY - pose.twist * 5 }];
  c.save(); c.translate(Math.round(e.x), Math.round(e.y)); c.globalAlpha *= pose.alpha;
  ellipse(c, pose.hitX * .5, 1 + pose.hitY, 16 + pose.fall * 11, 6, '#253f3060');
  if (pose.fall > .65 && pose.fall < 1) {
    for (let i = 0; i < 5; i++) ellipse(c, (i - 2) * (8 + pose.fall * 9), 3 + Math.sin(i * 4) * 3, 3, 1.5, '#cdb98170');
  }
  c.translate(pose.hitX, pose.hitY); c.rotate(pose.roll);
  const feet = [{ x: -8 - f * pose.stance, y: gait * 4 }, { x: 8 + f * pose.stance, y: -gait * 4 }];
  for (let i = 0; i < 2; i++) {
    const foot = feet[i], hip = hipX + (i ? 4 : -4), kneeX = (hip + foot.x) / 2 + pose.crouch * (i ? 1 : -1);
    poly(c, [[hip - 3, hipY], [hip + 3, hipY], [kneeX + 3, -6 + pose.crouch * .3],
      [foot.x + 3, foot.y], [foot.x - 3, foot.y], [kneeX - 3, -6 + pose.crouch * .3]], i ? '#293e33' : '#18312e');
    rect(c, foot.x - 4, foot.y - 2, 9, 4, '#111f23'); rect(c, foot.x - 3, foot.y - 2, 6, 1, '#6f7561');
  }
  const lag = -pose.twist * 13 - f * pose.lean * .8 - gait * 1.6;
  poly(c, [[chestX - 11, chestY - 1], [chestX + 10, chestY - 1], [hipX + 15 + lag, -7 + pose.crouch],
    [hipX + 4 + lag, -10 + pose.crouch], [hipX - 13 + lag, -6 + pose.crouch]], dark);
  arm(c, shoulders[0], pose.offHand, -5 - pose.twist * 8, false, [dark, coat]);
  const weaponBehind = d < -.45 && pose.hand.y < -25;
  const weapon = () => {
    arm(c, shoulders[1], pose.hand, 4 + pose.twist * 12, true, [light, coat]);
    if (!archer) sword(c, pose.hand.x, pose.hand.y, pose.angle, pose.bladeLength);
    else {
      c.save(); c.translate(pose.hand.x, pose.hand.y); c.rotate(pose.angle);
      c.strokeStyle = '#e6c386'; c.lineWidth = 3; c.beginPath(); c.moveTo(-3, -19); c.quadraticCurveTo(13, 0, -3, 19); c.stroke();
      const pull = e.mode === 'windup' ? 6 + pose.draw * 16 : pose.draw * 22;
      c.strokeStyle = '#ede0b3'; c.lineWidth = 1; c.beginPath(); c.moveTo(-3, -19); c.lineTo(-pull, 0); c.lineTo(-3, 19); c.stroke();
      rect(c, 2, -4, 4, 8, '#694b31');
      if (e.mode === 'windup' && e.hp > 0 && e.stagger <= 0) {
        rect(c, -pull, -1, pull + 7, 2, '#e7d399'); poly(c, [[9, 0], [3, -3], [3, 3]], '#fff2c4');
        rect(c, -pull, -3, 5, 2, '#b84c34');
      }
      c.restore();
    }
  };
  if (weaponBehind) weapon();
  poly(c, [[shoulders[0].x, chestY - 3], [shoulders[1].x, chestY - 3], [hipX + 10, hipY], [hipX - 10, hipY]], coat);
  poly(c, [[shoulders[0].x + 2, chestY - 2], [chestX - 2, chestY - 2], [hipX - 2, hipY - 2], [hipX - 8, hipY - 2]], light);
  poly(c, [[chestX - 4, chestY - 2], [chestX + 3, chestY - 2], [hipX + 1, hipY], [hipX - 3, hipY]], '#d3bb85');
  rect(c, hipX - 11, hipY - 1, 23, 4, '#d4a05a'); rect(c, hipX - 1, hipY, 4, 6, '#f4d895');
  const headX = chestX - pose.twist * 4 + f, headY = -42 + pose.crouch - Math.abs(gait) * .5;
  rect(c, headX - 8, headY - 1, 17, 17, '#142c2b'); rect(c, headX - 10, headY + 2, 20, 9, '#172c2a');
  if (d > -.42) {
    rect(c, headX - 6 + f * 3, headY + 6, Math.abs(f) > .65 ? 9 : 13, 9, '#e5c79b');
    rect(c, headX + f * 5 - 2, headY + 8, 2, 2, '#26332c');
    if (Math.abs(f) <= .65) rect(c, headX + 4, headY + 8, 2, 2, '#26332c');
  } else rect(c, headX - 6, headY + 2, 13, 11, '#203e38');
  rect(c, headX - 8, headY - 1, 14, 4, '#35504a'); rect(c, headX - 3, headY - 9, 8, 8, '#162b2a');
  rect(c, headX - 2, headY - 8, 5, 2, '#416057'); rect(c, headX - 9, headY + 3, 19, 3, '#d19d58');
  poly(c, [[headX - 8, headY + 5], [headX - 18 + lag, headY + 10], [headX - 21 + lag, headY + 18],
    [headX - 14 + lag, headY + 14], [headX - 7, headY + 9]], '#bf7c48');
  if (!weaponBehind) weapon();
  if (e.flash > 0 && e.hp > 0) { c.globalAlpha *= Math.min(.55, e.flash * 5); rect(c, chestX - 7, chestY, 14, 14, '#fff4ce'); }
  c.restore();
}

function arm(c, shoulder, hand, bend, light, colors) {
  const dx = hand.x - shoulder.x, dy = hand.y - shoulder.y, length = Math.hypot(dx, dy) || 1;
  const elbow = { x: shoulder.x + dx * .48 - dy / length * bend, y: shoulder.y + dy * .48 + dx / length * bend };
  const segment = (a, b, width, color) => {
    const x = b.x - a.x, y = b.y - a.y, n = Math.hypot(x, y) || 1, nx = -y / n * width, ny = x / n * width;
    poly(c, [[a.x + nx, a.y + ny], [b.x + nx, b.y + ny], [b.x - nx, b.y - ny], [a.x - nx, a.y - ny]], color);
  };
  segment(shoulder, elbow, 3.5, colors?.[0] ?? (light ? '#4c7e85' : '#173d4a'));
  segment(elbow, hand, 2.8, colors?.[1] ?? (light ? '#315d6b' : '#204957'));
  rect(c, hand.x - 2, hand.y - 2, 5, 5, '#dfbc92');
}

function hero(c, entity, pose, ghost = false) {
  const colors=entity.palette||{coat:'#285867',light:'#4a7d83',dark:'#163746',scarf:'#d4cfad'};
  const face = pose.face, forward = Math.cos(face), down = Math.sin(face), side = Math.abs(forward);
  const gait = entity.moving ? Math.sin(entity.walk * 19) : 0;
  const width = 10 - side * 2.5, sway = gait * 1.1;
  const hipX = pose.twist * 4, hipY = -12 + pose.crouch;
  const chestX = hipX + forward * pose.lean + sway, chestY = -27 + pose.crouch;
  const leftShoulder = { x: chestX - width + pose.twist * 8, y: chestY + 1 + pose.twist * 6 };
  const rightShoulder = { x: chestX + width + pose.twist * 8, y: chestY + 1 - pose.twist * 6 };
  const hand = pose.hand, leftHand = { x: chestX - 14 - forward * pose.lean * .7, y: -16 + pose.crouch - pose.twist * 14 + gait * 2 };
  c.save(); c.translate(Math.round(entity.x), Math.round(entity.y));
  if (ghost) c.globalAlpha *= .24;
  if (!ghost) ellipse(c, 0, 1, 16, 6, '#253f3060');
  // 脚底留在角色锚点附近，只有站幅与屈膝变化，不伪造向前位移。
  const feet = [{ x: -8 - forward * pose.stance, y: gait * 4 - down * pose.stance * .4 },
    { x: 8 + forward * pose.stance, y: -gait * 4 + down * pose.stance * .4 }];
  for (let i = 0; i < 2; i++) {
    const f = feet[i], hip = hipX + (i ? 4 : -4);
    poly(c, [[hip - 3, hipY - 1], [hip + 3, hipY - 1], [f.x + 3, f.y], [f.x - 3, f.y]], i ? '#25444b' : '#18313a');
    rect(c, f.x - 4, f.y - 2, 9, 4, '#13282e'); rect(c, f.x - 3, f.y - 2, 6, 1, '#607773');
  }
  const lag = -pose.twist * 13 - forward * pose.lean * .65 - gait * 1.4;
  poly(c, [[chestX - 10, chestY - 3], [chestX + 10, chestY - 3], [hipX + 15 + lag, -7 + pose.crouch],
    [hipX + 4 + lag, -10 + pose.crouch], [hipX - 11 + lag, -5 + pose.crouch]], colors.dark);
  arm(c, leftShoulder, leftHand, -5, false,entity.palette?[colors.dark,colors.coat]:undefined);
  const weaponBehind = down < -.45 && hand.y < -27;
  const drawWeapon = () => {
    arm(c, rightShoulder, hand, pose.twist * 18 + (down < -.45 ? -4 : 4), true,entity.palette?[colors.light,colors.coat]:undefined);
    if(entity.sword!==false)sword(c, hand.x, hand.y, pose.angle, pose.bladeLength);
  };
  if (weaponBehind) drawWeapon();
  // 腰带与肩线反向扭转，头部做小幅反向补偿，保持像素轮廓。
  poly(c, [[leftShoulder.x, chestY - 4], [rightShoulder.x, chestY - 4], [hipX + width, hipY], [hipX - width, hipY]], colors.coat);
  poly(c, [[leftShoulder.x + 2, chestY - 3], [chestX - 1, chestY - 3], [hipX - 2, hipY - 2], [hipX - width + 2, hipY - 2]], colors.light);
  poly(c, [[chestX - 4, chestY - 3], [chestX + 3, chestY - 3], [hipX + 1, hipY - 1], [hipX - 3, hipY - 1]], '#d2d7b9');
  rect(c, hipX - width - 1, hipY - 1, width * 2 + 2, 4, '#d8bb76');
  rect(c, hipX - 1, hipY, 4, 6, '#f0d99c');
  const headX = chestX - pose.twist * 5 + forward * 1.5, headY = -41 + pose.crouch - Math.abs(gait) * .4;
  rect(c, headX - 8, headY - 2, 16, 16, '#172e30'); rect(c, headX - 10, headY + 1, 19, 8, '#213f3d');
  if (down > -.45) {
    rect(c, headX - 6 + forward * 3, headY + 5, side > .7 ? 9 : 13, 9, '#dfc397');
    rect(c, headX + forward * 5 - 2, headY + 7, 2, 2, '#203632');
    if (side < .7) rect(c, headX + 4, headY + 7, 2, 2, '#203632');
  } else rect(c, headX - 6, headY + 1, 12, 10, '#284942');
  rect(c, headX - 8, headY - 2, 13, 4, '#3d5b53'); rect(c, headX - 3, headY - 9, 7, 8, '#1a302e');
  rect(c, headX - 2, headY - 8, 5, 2, '#56756a'); rect(c, headX - 9, headY + 2, 18, 3, '#ded9b6');
  const scarf = -forward * 11 + lag * .65;
  poly(c, [[headX - 6, headY + 3], [headX - 9 + scarf, headY + 8], [headX - 12 + scarf, headY + 16],
    [headX - 5 + scarf, headY + 12], [headX - 3, headY + 6]], colors.scarf);
  if (!weaponBehind) drawWeapon();
  if (entity.flash > 0 && !ghost) { c.globalAlpha *= .65; rect(c, chestX - 7, chestY, 14, 14, '#fff4d0'); }
  c.restore();
}

function cSpark(c, x, y, angle, length, color) {
  c.save(); c.translate(x, y); c.rotate(angle);
  poly(c, [[-length, 0], [0, -1.6], [length * .45, 0], [0, 1.6]], color); c.restore();
}

function slash(c, x, y, face, progress, combo, enemy = false) {
  if (progress <= .18 || progress >= 1) return;
  const head = swingHead(progress), tail = Math.max(0, head - .72), heavy = combo === 3;
  const alpha = Math.min(1, (progress - .18) * 12, (1 - progress) * 4.5);
  const width = enemy ? 8 : heavy ? 18 : combo === 2 ? 11 : 13;
  const tint = enemy ? '#e9ae72' : heavy ? '#edca83' : combo === 2 ? '#a3e4dd' : '#9bcfa7';
  c.save(); c.translate(x, y - 18); c.rotate(face); c.scale(enemy ? .74 : 1, enemy ? .6 : .84); c.globalAlpha *= alpha;
  // 薄的外层余光、带粗细变化的刃面和一道亮锋，收成两端尖细的笔触。
  c.save(); c.globalAlpha *= .16;
  bladeRibbon(c, combo, tail, head, width * 1.65, tint); c.restore();
  c.save(); c.globalAlpha *= .72;
  bladeRibbon(c, combo, tail, head, width, tint); c.restore();
  const a = swordPoint(combo, tail), b = swordPoint(combo, head);
  const edge = c.createLinearGradient(a[0], a[1], b[0], b[1]);
  edge.addColorStop(0, '#d9ffe000'); edge.addColorStop(.3, enemy ? '#ffe8bf' : '#f2ffed'); edge.addColorStop(1, '#fffbe4');
  bladeRibbon(c, combo, tail + (head - tail) * .08, head, width * .5, edge);
  c.save(); c.translate(0, -2); bladeRibbon(c, combo, Math.max(tail, head - .43), head, 1.2, '#ffffff'); c.restore();
  // 侧后方的细残影断开，避免连击叠成一块白色圆盘。
  for (let j = 0; j < 3; j++) {
    c.save(); c.translate(-4 - j * 4, (combo === 2 ? 1 : -1) * (7 + j * 5)); c.globalAlpha *= .33 - j * .08;
    bladeRibbon(c, combo, Math.max(0, tail - .05), Math.max(0, head - .08 - j * .05), 1.5 + j * .3, tint); c.restore();
  }
  if (!enemy) {
    const tip = swordPoint(combo, head);
    c.save(); c.translate(tip[0], tip[1]); c.rotate(heavy ? -.65 : .5);
    poly(c, [[-9, 0], [-2, -2], [0, -7], [2, -2], [13, 0], [2, 2], [0, 7], [-2, 2]], '#fffbe1'); c.restore();
    for (let j = 0; j < (heavy ? 8 : 5); j++) {
      const t = Math.max(tail, head - .08 - j * .055), point = swordPoint(combo, t);
      const drift = (progress + j * .13) % 1;
      rect(c, point[0] - drift * 15, point[1] + Math.sin(j * 3.7) * (5 + drift * 17), j % 3 ? 2 : 3, 2, j % 2 ? '#f4deb0' : '#eeffe9');
    }
    if (heavy && progress > .36) {
      c.save(); c.globalAlpha *= (1 - progress) * .7;
      poly(c, [[24, -50], [91, 35], [118, 79], [77, 43]], '#ffedb2');
      poly(c, [[42, 54], [85, 17], [115, -8], [91, 27]], '#fffbe4'); c.restore();
    }
  }
  c.restore();
}

function swordQi(c, shot, time) {
  c.save(); c.translate(shot.x, shot.y - 12); c.rotate(Math.atan2(shot.vy, shot.vx));
  c.globalAlpha *= Math.min(1, shot.life / .12);
  // 飞行剑气以尖锋领头，后部散成细流；其位置仍取实际弹体中心。
  for (let j = 0; j < 4; j++) {
    const y = (j - 1.5) * 9, pulse = Math.sin(time * 26 - j * 2) * 3;
    poly(c, [[-102 - j * 8, y + pulse], [-28, y - 2], [13, 0], [-31, y + 2]], j % 2 ? '#e9f9c05c' : '#bcf8da8a');
  }
  c.fillStyle = '#92d8bd78'; c.beginPath(); c.moveTo(48, 0); c.quadraticCurveTo(8, -24, -28, -41);
  c.quadraticCurveTo(-7, 0, -28, 41); c.quadraticCurveTo(8, 24, 48, 0); c.fill();
  c.fillStyle = '#eaffdc'; c.beginPath(); c.moveTo(45, 0); c.quadraticCurveTo(5, -15, -22, -32);
  c.quadraticCurveTo(0, 0, -22, 32); c.quadraticCurveTo(5, 15, 45, 0); c.fill();
  poly(c, [[-40, 0], [20, -3], [51, 0], [20, 3]], '#fff9dd');
  for (let j = 0; j < 6; j++) {
    const phase = (time * 2.4 + j / 6) % 1;
    rect(c, 10 - phase * 115, Math.sin(j * 8.3) * (8 + phase * 19), 3, 2, j % 2 ? '#ebd58aa0' : '#ddffeac0');
  }
  c.restore();
}


export { blendPose, hero as paintHero, person as paintEnemy, slash as paintSlash, swordQi as paintQi, cSpark as paintShard };
