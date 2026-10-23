import { advanceHeroMotion, advanceEnemyMotion, sampleHeroPose, blendPose, paintHero, paintEnemy, paintSlash, paintQi, paintShard } from './songfeng-render.mjs';
import { kickCamera, advanceCamera } from './songfeng-feedback.mjs';

export const skillHead = p => 1 - Math.pow(1 - Math.max(0, Math.min(1, (p - .16) / .7)), 2.2);
export function skillBladePoint(skill, t) {
  if (skill === 'thrust') return [32 + 78 * Math.sin(Math.PI * t), 0];
  if (skill === 'break') { const a = -1.4 + t * 2.65; return [34 + Math.cos(a) * 66, Math.sin(a) * 82]; }
  if (skill === 'sweep') { const a = t * Math.PI * 2 - .7; return [104 * Math.cos(a), 104 * Math.sin(a)]; }
  return [34 + t * 48, 32 - t * 60];
}
export function sampleSkillPose(face, skill, p) {
  const head = skillHead(p), point = skillBladePoint(skill, head), f = Math.cos(face), d = Math.sin(face);
  const tip = { x: f * point[0] - d * point[1] * .84, y: -18 + d * point[0] + f * point[1] * .84 };
  const angle = Math.atan2(tip.y + 18, tip.x), drive = Math.sin(Math.PI * Math.max(0, Math.min(1, p)));
  const pose = { ...sampleHeroPose(face), face: skill === 'sweep' ? face + head * Math.PI * 2 - .7 : face,
    tip, angle, hand: { x: tip.x - Math.cos(angle) * 55, y: tip.y - Math.sin(angle) * 55 },
    lean: (skill === 'thrust' ? 6 : skill === 'break' ? 4 : 2) * drive,
    crouch: (skill === 'break' ? 4 : 2) * drive, twist: (skill === 'sweep' ? .42 : .25) * Math.sin(head * Math.PI), stance: 4 * drive };
  return p < .16 ? blendPose(sampleHeroPose(face), pose, Math.max(0, p / .16)) : pose;
}
function paintSkill(c, s, px, py) {
  const p = s.age / s.duration; if (p <= .16 || p >= 1) return;
  const head = skillHead(p), tail = Math.max(0, head - (s.skill === 'sweep' ? .72 : .55));
  const width = s.skill === 'thrust' ? 5 : s.skill === 'break' ? 14 : s.skill === 'sweep' ? 11 : 6;
  const tint = s.skill === 'break' ? '#edca83' : s.skill === 'qi' ? '#a5e8d6' : '#c3e5cc';
  const left = [], right = [];
  for (let i = 0; i <= 30; i++) {
    const u = i / 30, t = tail + (head - tail) * u, point = skillBladePoint(s.skill, t);
    const a = skillBladePoint(s.skill, Math.max(0, t - .002)), b = skillBladePoint(s.skill, Math.min(1, t + .002));
    const dx = b[0] - a[0], dy = b[1] - a[1], n = Math.hypot(dx, dy) || 1, w = width * Math.pow(Math.sin(Math.PI * u), .7);
    left.push([point[0] - dy / n * w, point[1] + dx / n * w]); right.push([point[0] + dy / n * w, point[1] - dx / n * w]);
  }
  c.save(); c.translate(s.x - px, s.y - py - 18); c.rotate(s.face); c.scale(1, .84);
  c.globalAlpha *= Math.min(1, (p - .16) * 16, (1 - p) * 5);
  c.fillStyle = tint; c.beginPath(); [...left, ...right.reverse()].forEach(([x, y], i) => i ? c.lineTo(x, y) : c.moveTo(x, y)); c.closePath(); c.fill();
  c.strokeStyle = '#fffbe5'; c.lineWidth = 1.5; c.beginPath();
  for (let i = 0; i <= 30; i++) { const point = skillBladePoint(s.skill, tail + (head - tail) * i / 30); i ? c.lineTo(...point) : c.moveTo(...point); }
  c.stroke(); const tip = skillBladePoint(s.skill, head); c.fillStyle = '#fff8d5'; c.fillRect(tip[0] - 2, tip[1] - 2, 4, 4); c.restore();
}

// 章节使用 3 世界单位/像素；只在画笔边界换算，碰撞与任务坐标仍使用原单位。
export function createChapterCombatRenderer() {
  const heroMotion = {}, enemyMotion = new Map(), enemies = new Map(), strikes = new Map(), camera = {};
  let clock = -1, serial = 0, lastReal = 0;
  const heroState = {};
  function reset() { for (const key of Object.keys(heroMotion)) delete heroMotion[key]; enemyMotion.clear(); enemies.clear(); strikes.clear(); camera.strength = 0; }
  function prepare(G, paused, now) {
    if (G.time < clock || G.combatSerial < serial) reset(); clock = G.time; serial = G.combatSerial;
    const live = new Set();
    for (const s of G.swings) {
      live.add(s.id); if (!strikes.has(s.id)) strikes.set(s.id, {});
      Object.assign(strikes.get(s.id), s, { combo: s.visualCombo || s.combo });
    }
    for (const id of strikes.keys()) if (!live.has(id)) strikes.delete(id);
    Object.assign(heroState, { elapsed: G.time, paused, hitstop: G.hitstop, p: { ...G.p, walk: G.p.an, flash: G.p.hurt },
      stats: { attacks: G.combatSerial }, swings: [...strikes.values()],
      fx: G.fx.filter(f => f.type === 'songfengSpark').map(f => ({ kind: 'spark', x: f.x, y: f.y, face: f.face, heavy: f.heavy, life: f.dur - f.t, max: f.dur })) });
    advanceHeroMotion(heroMotion, heroState);
    const current=G.swings.at(-1);
    if(current?.skill){heroMotion.pose=sampleSkillPose(current.face,current.skill,current.age/current.duration);heroMotion.skillPose=heroMotion.pose;}
    else if(current)heroMotion.skillPose=null;
    else if(heroMotion.skillPose&&heroMotion.recovery<.16)heroMotion.pose=blendPose(heroMotion.skillPose,sampleHeroPose(heroMotion.face),heroMotion.recovery/.16);
    else heroMotion.skillPose=null;
    if(current){heroMotion.anchor={x:current.x,y:current.y};}
    const fade=current?1:Math.max(0,1-heroMotion.recovery/.16);
    heroMotion.offset=heroMotion.anchor?{x:(heroMotion.anchor.x-G.p.x)*fade,y:(heroMotion.anchor.y-G.p.y)*fade}:{x:0,y:0};
    const ids = new Set();
    for (const e of G.enemies) if (e.alive) {
      ids.add(e.id); if (!enemies.has(e.id)) { enemies.set(e.id, {}); enemyMotion.set(e.id, {}); }
      const proxy = enemies.get(e.id), archer = e.kind === 'archer';
      const mode = e.state === 'windup' ? 'windup' : ['recover', 'dash'].includes(e.state) ? 'recover' : 'idle';
      const timer = mode === 'windup' ? (archer ? .75 : .62) * Math.max(0, 1 - e.t / e.atk.tele) : (archer ? 1.15 : .72) - e.t;
      Object.assign(proxy, { id: e.id, type: archer ? 'archer' : 'melee', x: e.x, y: e.y, face: e.face, attackFace: e.face,
        maxHp: e.maxHp, hp: e.state === 'down' ? 1 : e.hp, mode, timer, flash: e.flash, walk: e.an,
        stagger: ['flinch', 'stagger'].includes(e.state) ? (e.sfHeavy ? .43 : .23) * Math.min(1, Math.max(0, 1 - e.t / (e.state === 'flinch' ? (archer ? .3 : .18) : .9))) : 0,
        dead: e.state === 'dying' ? e.dieT / .6 * .7 : 0 });
      advanceEnemyMotion(enemyMotion.get(e.id), heroState, proxy);
    }
    for (const id of enemies.keys()) if (!ids.has(id)) { enemies.delete(id); enemyMotion.delete(id); }
    const shake = advanceCamera(camera, paused ? 0 : Math.max(0, now - lastReal)); lastReal = now;
    return shake;
  }
  return {
    reset, prepare, impact: event => kickCamera(camera, event),
    hero(c, G, unit) {
      c.save(); c.translate(G.p.x / unit, G.p.y / unit); c.scale(1 / unit, 1 / unit);
      const pose=heroMotion.pose, offset=heroMotion.offset;
      paintHero(c, { ...heroState.p, x: 0, y: 0 }, {...pose,hand:{x:pose.hand.x+offset.x,y:pose.hand.y+offset.y},tip:{x:pose.tip.x+offset.x,y:pose.tip.y+offset.y}});
      for (const s of G.swings) {
        if (s.skill) paintSkill(c, s, G.p.x, G.p.y);
        else paintSlash(c, s.x-G.p.x, s.y-G.p.y, s.face, s.age / s.duration, s.combo);
      }
      c.restore();
    },
    enemy(c, e, unit) {
      const motion = enemyMotion.get(e.id); if (!motion) return;
      const pose = e.state === 'down' ? { ...motion.pose, crouch: 8, lean: 0 } : motion.pose;
      const scale = e.kind === 'boss' ? 1.7 : e.kind === 'captain' ? 1.35 : 1;
      c.save(); c.translate(e.x / unit, e.y / unit); c.scale(scale / unit, scale / unit);
      paintEnemy(c, { ...enemies.get(e.id), x: 0, y: 0 }, pose);
      if (pose.strikeProgress !== null && e.kind !== 'archer') paintSlash(c, 0, 0, e.face, pose.strikeProgress, 1, true);
      c.restore();
    },
    effects(c, G, unit) {
      c.save(); c.scale(1 / unit, 1 / unit);
      for (const shot of G.qi) paintQi(c, shot, .8 - shot.life);
      for (const f of G.fx) if (f.type === 'songfengSpark') {
        const p = f.t / f.dur, burst = (f.heavy ? 31 : 21) * (p < .12 ? .7 + p * 2.5 : Math.sin(Math.PI * (.12 + p * .88)));
        c.save(); c.translate(f.x, f.y); c.rotate(f.face); c.globalAlpha = Math.min(1, (1 - p) * 2.5);
        c.fillStyle = '#fff8d5'; c.beginPath(); c.moveTo(-burst, 0); c.lineTo(-3, -3); c.lineTo(0, -burst * .65); c.lineTo(3, -3);
        c.lineTo(burst, 0); c.lineTo(3, 3); c.lineTo(0, burst * .65); c.lineTo(-3, 3); c.fill();
        for (let j = 0; j < (f.heavy ? 10 : 7); j++) {
          const a = j * 2.4, r = 8 + p * (f.heavy ? 66 : 46);
          paintShard(c, Math.cos(a) * r, Math.sin(a) * r * .7 + p * p * 13, a, (1 - p) * 10 + 2, j % 2 ? '#ecc176' : '#f5ffe1');
        }
        c.restore();
      }
      c.restore();
    },
  };
}
