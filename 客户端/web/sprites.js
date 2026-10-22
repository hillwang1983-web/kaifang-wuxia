"use strict";
// 人物精灵：按"层 × 调色板套"从网关按需取小图集（网关第一次被请求时用 build_sprites.py 从 role\*.mrg 生成），
// 再加简单的行走 / 站立动画。规则来自 动作表\动作表说明.md：动作 7 = 站立（150ms/帧）、1 = 行走（100ms/帧），每方向 8 帧循环；
// 方向 0..7 = 上、左上、左、左下、下(面向镜头)、右下、右、右上；文件帧号 = 方向*每方向帧数 + 帧号；
// 角色坐标是脚下的点，画点 y = y - 56 + 帧的 oy，x = x + 帧的 ox。
// 每个角色画哪些层由网关算好（look = {model, layers:[{l, s, alpha?}...]}，已经是叠放顺序），这里只负责取图和画。
const Sprites = (() => {
  const TAN22_5 = 0.41421356237;
  const SPEED = 200;                       // 行走速度 px/s —— 原版是路径逐点走，速度没追到，这里是自拟值
  const TICK = { 7: 150, 1: 100 };

  // 位移 -> 方向（loginp.exe 0x767994，和 动作表\actiontable.js 同一套）。mx,my = 屏幕坐标位移，y 向下。
  function dirFromMove(mx, my) {
    const X = -mx, Y = my, sg = (v) => (v > 0 ? 1 : v === 0 ? 0 : -1);
    const i1 = sg(TAN22_5 * X - Y), i2 = sg(X - TAN22_5 * Y), i3 = sg(X + TAN22_5 * Y), i5 = sg(Y + TAN22_5 * X);
    let s = 0;
    if (i5 >= 0 && i3 < 0) s = 1;
    if (i1 < 1 && i5 < 0) s = 2;
    if (i2 < 1 && i1 > 0) s = 3;
    if (i3 < 1 && i2 > 0) s = 4;
    if (i5 < 1 && i3 > 0) s = 5;
    if (i1 >= 0 && i5 > 0) s = 6;
    if (i2 >= 0 && i1 < 0) s = 7;
    return (s + 4) % 8;
  }

  const cache = {};                        // "模型/层_套" -> { state: loading|ready|missing, data, img }
  function layer(model, l, s) {
    const key = model + "/" + l + "_" + s;
    if (cache[key]) return cache[key];
    const st = cache[key] = { state: "loading" };
    fetch("/sprites/" + key + ".json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((data) => {
      st.data = data;
      return new Promise((res, rej) => { const im = new Image(); im.onload = () => { st.img = im; res(); }; im.onerror = rej; im.src = "/sprites/" + key + ".png"; });
    }).then(() => { st.state = "ready"; }).catch(() => { st.state = "missing"; });
    return st;
  }
  // 身体层（不是阴影的第一层）已经能画了吗
  function ready(look) {
    const body = look && look.layers && look.layers.find((e) => !e.alpha);
    return !!body && layer(look.model, body.l, body.s).state === "ready";
  }

  // 一个角色：当前位置 (x,y) 朝目标 (tx,ty) 走；没有目标距离就站立
  class Actor {
    constructor(x, y) { this.x = this.tx = x; this.y = this.ty = y; this.dir = 4; this.frame = 0; this.last = 0; this.cp = 7; }
    goto(x, y) { this.tx = x; this.ty = y; }
    snap(x, y) { this.x = this.tx = x; this.y = this.ty = y; }
    update(now, dt) {
      const dx = this.tx - this.x, dy = this.ty - this.y, d = Math.hypot(dx, dy);
      let cp = 7;
      if (d > 0.5) {
        cp = 1;
        const step = Math.max(SPEED, d / 1.5) * dt;       // 很远的移动（点击远处 / 传送后的补位）最多走 1.5 秒
        this.dir = dirFromMove(dx, dy);
        if (step >= d) { this.x = this.tx; this.y = this.ty; } else { this.x += dx / d * step; this.y += dy / d * step; }
      }
      if (cp !== this.cp) { this.cp = cp; this.frame = 0; this.last = now; }
      else if (now - this.last > TICK[cp]) { this.last = now; this.frame = (this.frame + 1) % 8; }
    }
  }

  // 画一个角色；(px,py) 是屏幕上脚下的点，s 是缩放。没取到的层先跳过（取到后下一帧自然出现）
  function draw(ctx, look, actor, px, py, s) {
    for (const e of look.layers) {
      const L = layer(look.model, e.l, e.s);
      if (L.state !== "ready") continue;
      const A = L.data.cps[actor.cp];
      const fr = A && A.frames[actor.dir * A.fpd + actor.frame];
      if (!fr) continue;
      const [x, y, w, h, ox, oy] = fr;
      if (e.alpha) ctx.globalAlpha = e.alpha;
      ctx.drawImage(L.img, x, y, w, h, px + ox * s, py + (-56 + oy) * s, w * s, h * s);
      ctx.globalAlpha = 1;
    }
  }

  // ---- NPC / 怪物精灵（web/sprites/npc/<精灵号>.json + _<页>.png；S 站立 / A 攻击，8 方向，文件帧号 = 方向*每方向帧数 + 帧号）
  const ncache = {};
  function npcLoad(id) {
    if (ncache[id]) return ncache[id];
    const st = ncache[id] = { state: "loading" };
    fetch("/sprites/npc/" + id + ".json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }).then((data) => {
      st.data = data;
      const bots = []; for (const f of ((data.cps.S || {}).frames || [])) if (f) bots.push(f[5] + f[3]);
      bots.sort((a, b) => a - b); st.base = bots.length ? bots[bots.length >> 1] : 60;     // 脚底相对原点的位置（取中位数，动画里不抖）
      return Promise.all(data.pages.map((p) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = "/sprites/npc/" + p; })));
    }).then((imgs) => { st.imgs = imgs; st.state = "ready"; }).catch(() => { st.state = "missing"; });
    return st;
  }
  const npcReady = (id) => !!id && npcLoad(id).state === "ready";
  // 画一个 NPC / 怪物：(px,py) = 脚下；kind "S" 站立 / "A" 攻击；frame 从 0 递增（自动取模）
  function drawNpc(ctx, id, kind, dir, frame, px, py, s) {
    const N = npcLoad(id); if (N.state !== "ready") return false;
    const A = N.data.cps[kind] || N.data.cps.S; if (!A) return false;
    const fr = A.frames[(dir & 7) * A.fpd + (frame % A.fpd)] || A.frames[(dir & 7) * A.fpd];
    if (!fr) return false;
    const [x, y, w, h, ox, oy, pg] = fr;
    ctx.drawImage(N.imgs[pg], x, y, w, h, px + ox * s, py + (oy - N.base) * s, w * s, h * s);
    return true;
  }
  const npcFrames = (id, kind) => { const N = ncache[id]; const A = N && N.data && (N.data.cps[kind] || N.data.cps.S); return A ? A.fpd : 1; };
  return { Actor, draw, ready, dirFromMove, npcReady, drawNpc, npcFrames };
})();
