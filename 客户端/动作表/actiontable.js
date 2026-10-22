// 金庸群侠传角色动作表 —— 网页端使用示例/小库（ES module，浏览器和 node 都能 import）
// 配套数据: action_table.web.json（路径相对该 JSON）。说明见 动作表说明.md 第 9 节。

const TAN22_5 = 0.41421356237;

/** 位移 -> 方向 0..7 (0=上,1=左上,2=左,3=左下,4=下,5=右下,6=右,7=右上)。mx,my 为屏幕坐标位移(y向下)。 */
export function dirFromMove(mx, my) {
  const X = -mx, Y = my;
  const sg = (v) => (v > 0 ? 1 : v === 0 ? 0 : -1);
  const i1 = sg(TAN22_5 * X - Y), i2 = sg(X - TAN22_5 * Y);
  const i3 = sg(X + TAN22_5 * Y), i5 = sg(Y + TAN22_5 * X);
  let s = 0;                                   // 与 loginp.exe 0x767994 同序: 后面的条件覆盖前面的
  if (i5 >= 0 && i3 < 0) s = 1;
  if (i1 < 1 && i5 < 0) s = 2;
  if (i2 < 1 && i1 > 0) s = 3;
  if (i3 < 1 && i2 > 0) s = 4;
  if (i5 < 1 && i3 > 0) s = 5;
  if (i1 >= 0 && i5 > 0) s = 6;
  if (i2 >= 0 && i1 < 0) s = 7;
  return (s + 4) % 8;
}

/** 读取 JSON（浏览器 fetch / node fs 都行，传入已解析对象也行） */
export async function loadJson(url) {
  if (typeof url === 'object') return url;
  const r = await fetch(url);
  return r.json();
}

/** 把 atlas.json 建成索引: index.get('M50000|7') -> 按文件帧号索引的数组 */
export function buildAtlasIndex(atlas) {
  const index = new Map();
  for (const im of atlas.images) {
    if (im.kind !== 'cp') continue;
    const m = /^ROLE\\(.+)\.CP(\d+)$/i.exec(im.name);
    if (!m) continue;
    const key = m[1].toUpperCase() + '|' + m[2];
    let arr = index.get(key);
    if (!arr) index.set(key, (arr = []));
    arr[im.frame] = im;                         // im: {page,x,y,w,h,ox,oy,frame}
  }
  return index;
}

/** 按 0x5253c8 的折叠规则把想要的 cp 折成该模型真正会去读的 cp */
export function resolveCp(table, modelId, cp) {
  const m = table.models.find((x) => x.model === modelId);
  const series = m ? m.series : '';
  for (const r of table.cpFallbackRules) {
    const c = r.if;
    if (c.modelNotIn && c.modelNotIn.includes(modelId)) continue;
    if (c.seriesNotIn && c.seriesNotIn.includes(series)) continue;
    if (c.modelIn && !c.modelIn.includes(modelId)) continue;
    if (c.seriesIn && !c.seriesIn.includes(series)) continue;
    const to = r.map[String(cp)];
    if (to !== undefined) cp = to;
  }
  return cp;
}

/** 取某层某帧: layer 如 'M50000'/'M5MA01'/'B50S'; dir 0..7; f 方向内帧号; framesPerDir 来自 model.cps[cp] */
export function getFrame(index, layer, cp, dir, f, framesPerDir) {
  const arr = index.get(layer.toUpperCase() + '|' + cp);
  if (!arr) return null;
  return arr[dir * framesPerDir + f] || null;   // 空帧(w=h=0)在 atlas 里没有 -> null
}

/** 世界场景里一个角色的动画状态机（与 0x768370 / 0x76ca9c / 0x769fa4 一致） */
export class Actor {
  constructor(table, modelId) {
    this.t = table; this.model = modelId;
    this.dir = 4; this.state = 0;               // 0 站立 1 行走
    this.mounted = false; this.attacking = false;
    this.frame = 0; this.last = 0;
  }
  setState(state, now) {                         // = SetState(state,0,100,8): 只有状态变化才重置帧
    if (state !== this.state) { this.state = state; this.frame = 0; this.last = now; }
  }
  attack(now) { this.attacking = true; this.frame = 0; this.last = now; }  // 起始重置点原版未追, 这里自定
  actionName() {
    if (!this.mounted && this.attacking) return 'attack';
    const base = this.state === 1 ? 'walk' : 'idle';
    return this.mounted ? (base === 'walk' ? 'ride_move' : 'ride_idle') : base;
  }
  update(now) {                                  // now: ms
    const a = this.t.actions[this.actionName()];
    const interval = a.intervalMs;
    if (now - this.last > interval) {
      this.last = now;
      this.frame = (this.frame + 1) % a.loopFrames;
      if (this.actionName() === 'attack' && this.frame === 0) this.attacking = false; // 原版: 帧==7 时清标志
    }
    return { cp: resolveCp(this.t, this.model, a.cp), dir: this.dir, frame: this.frame };
  }
}

/** 一帧里要画哪些层(按顺序)。equip: 装备层名数组(最多3个槽, 如 ['M5MA01','M5PA01','M5WA01']) */
export function layersToDraw(table, modelId, equip) {
  const m = table.models.find((x) => x.model === modelId);
  const order = (modelId >= 3 && modelId <= 9) ? table.layerOrder.models3to9 : table.layerOrder.default;
  const out = [];
  if (m.shadowLayer) out.push({ layer: m.shadowLayer, shadow: true });
  for (const k of order) {
    if (k === 0) out.push({ layer: m.bodyLayer });
    else if (equip[k - 1]) out.push({ layer: equip[k - 1] });
  }
  return out;
}

/** 画点修正 */
export function drawY(table, modelId, y) {
  const d = table.drawOffsetY;
  const extra = { 3: d.model3, 4: d.model4, 129: d.model129, 130: d.model130 }[modelId] ?? d.default;
  return y + extra + d.base;
}

/** 浏览器里画一个角色的一帧 (ctx: CanvasRenderingContext2D, pages: {'atlas_0.png': Image}) */
export function drawActor(ctx, table, indexByLayer, pages, actor, equip, x, y, now) {
  const st = actor.update(now);
  const m = table.models.find((q) => q.model === actor.model);
  const fpd = m.cps[st.cp];
  if (!fpd) return;
  const yy = drawY(table, actor.model, y);
  for (const L of layersToDraw(table, actor.model, equip)) {
    const im = getFrame(indexByLayer, L.layer, st.cp, st.dir, st.frame, fpd);
    if (!im) continue;
    if (L.shadow) ctx.globalAlpha = 0.5;
    ctx.drawImage(pages[im.page], im.x, im.y, im.w, im.h, x + im.ox, yy + im.oy, im.w, im.h);
    ctx.globalAlpha = 1;
  }
}
