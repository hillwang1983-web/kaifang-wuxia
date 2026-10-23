import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { once } from 'node:events';
import { createQingshiServer } from '../portal-integration/server.mjs';
const server = createQingshiServer(new URL('../原型/V0.4/',import.meta.url)); server.listen(0, '127.0.0.1'); await once(server, 'listening');
const base = `http://127.0.0.1:${server.address().port}/qingshi-v04/`;
const browser = await chromium.launch({ headless: true});
test.after(async () => { await browser.close(); await new Promise(r => server.close(r)); });
async function pageFor(t, debug = true) {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true }); t.after(() => context.close());
  const page = await context.newPage(), errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base + (debug ? '?debug' : '')); await page.locator('#bStart').tap(); return { page, context, errors };
}
const snapshot = page => page.evaluate(() => structuredClone(__duko.G));

test('默认入口不开放调试对象，沿用V0.4存档键且不触及V0.3存档', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 } }); t.after(() => context.close());
  await context.addInitScript(() => {
    localStorage.setItem('duko-save-v3', '旧存档保护哨兵'); window.storageAccess = [];
    for (const key of ['getItem', 'setItem', 'removeItem']) {
      const old = Storage.prototype[key]; Storage.prototype[key] = function(...args) { storageAccess.push([key, args[0]]); return old.apply(this, args); };
    }
  });
  const page = await context.newPage(); await page.goto(base); await page.locator('#bStart').click();
  assert.equal(await page.evaluate(() => typeof __duko), 'undefined');
  const access = await page.evaluate(() => storageAccess); assert.ok(access.some(a => a[1] === 'qingshi-chapter-v04'));
  assert.ok(access.every(a => a[1] !== 'duko-save-v3'));
});

test('按住普攻自动三段，原地出剑不位移，一剑只结算一次并有命中停顿', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d = __duko, p = d.G.p; p.x = 900; p.y = 870; p.face = 0;
    const e = d.G.enemies[0]; Object.assign(e, { x: 980, y: 870, hp: 500, maxHp: 500, state: 'idle', hostile: true, alive: true, hx: 980, hy: 870 });
    for (const other of d.G.enemies.slice(1)) other.hostile = false;
    const origin = { x: p.x, y: p.y }; d.attack(); d.step(.01, 6);
    const after = { hp: e.hp, stop: d.G.hitstop, age: d.G.swings[0].age, fx: structuredClone(d.G.fx) }; d.step(.005, 2);
    const frozen = d.G.swings[0].age === after.age && JSON.stringify(d.G.fx) === JSON.stringify(after.fx);
    d.step(.01, 15);
    return { origin, position: { x: d.G.p.x, y: d.G.p.y }, hp: e.hp, firstHp: after.hp, stop: after.stop, frozen };
  });
  assert.equal(result.firstHp, 480); assert.equal(result.hp, 480); assert.ok(result.stop > 0); assert.equal(result.frozen, true); assert.deepEqual(result.position, result.origin);
  await page.keyboard.down('j');
  try{await page.waitForFunction(()=>__duko.G.combatSerial>=4,{}, {timeout:2500});}finally{await page.keyboard.up('j');}
  assert.ok((await snapshot(page)).combatSerial >= 4); assert.deepEqual(errors, []);
});

test('双指移动出剑与取消输入、暂停后不补动作，身法耗尽不可连闪', async t => {
  const { page, context, errors } = await pageFor(t), cdp = await context.newCDPSession(page);
  const before = await snapshot(page), r = await page.locator('#bAtk').boundingBox();
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ id: 1, x: 80, y: 260 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ id: 1, x: 120, y: 260 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ id: 1, x: 120, y: 260 }, { id: 2, x: r.x + r.width / 2, y: r.y + r.height / 2 }] });
  await page.waitForTimeout(400); const during = await snapshot(page);
  assert.ok(during.p.x > before.p.x + 10); assert.ok(during.combatSerial > 0);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchCancel', touchPoints: [] }); const release = await snapshot(page); await page.waitForTimeout(200);
  assert.equal((await snapshot(page)).p.x, release.p.x);
  await page.locator('#bPause').tap(); const paused = await snapshot(page); await page.waitForTimeout(100); assert.equal((await snapshot(page)).time, paused.time);
  await page.locator('#bResume').tap(); await page.waitForTimeout(50); assert.equal((await snapshot(page)).combatSerial, paused.combatSerial);
  const stamina = await page.evaluate(() => { const d = __duko; d.G.p.sp = 20; d.G.p.dgCd = 0; d.G.p.dodge = 0; d.dodge(); return d.G.p.dodge; });
  assert.equal(stamina, 0); assert.deepEqual(errors, []);
});

test('移动中挥剑固定本剑起点，闪避取消未完成的挥剑', async t => {
  const { page, errors } = await pageFor(t);
  await page.evaluate(() => {
    const d = __duko; Object.assign(d.G.p, { x: 900, y: 870, face: 0 });
    const e = d.G.enemies[0]; Object.assign(e, { x: 1035, y: 870, hx: 1035, hy: 870, hp: 500, maxHp: 500, hostile: true, state: 'windup', t: 0,
      atk: { shape: 'cone', tele: 1, range: 74, half: .9, dmg: 9, rec: .55, inter: true } });
    for (const other of d.G.enemies.slice(1)) other.hostile = false;
  });
  await page.keyboard.down('d');
  const result = await page.evaluate(() => {
    const d = __duko; Object.assign(d.G.p, { x: 900, y: 870 }); d.attack(); d.step(.01, 18);
    const before = { hp: d.G.enemies[0].hp, x: d.G.p.x, anchor: d.G.swings[0].x };
    d.dodge(); return { ...before, swings: d.G.swings.length, dodge: d.G.p.dodge };
  });
  await page.keyboard.up('d'); assert.ok(result.x > 905); assert.equal(result.anchor, 900); assert.equal(result.hp, 500);
  assert.equal(result.swings, 0); assert.ok(result.dodge > 0); assert.deepEqual(errors, []);
});

test('剑气按真实弹体移动、穿透只命中一次，原有三招可换装且不清技能冷却', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d = __duko; d.G.p.x = 900; d.G.p.y = 870; d.G.p.face = 0;
    const e = d.G.enemies[0]; Object.assign(e, { x: 1060, y: 870, hx: 1060, hy: 870, hp: 500, maxHp: 500, hostile: true, state: 'idle' });
    for (const other of d.G.enemies.slice(1)) other.hostile = false;
    d.skill(0); d.step(.01, 6); const first = d.G.qi[0]?.x; d.step(.01, 40);
    return { first, remaining: d.G.qi.map(s => s.x), hp: e.hp, cooldown: d.G.chapter.cooldowns[0], mp: d.G.p.mp, skills: Object.keys(QingShiChapter.SKILLS) };
  });
  assert.ok(result.first > 900); assert.equal(result.hp, 456); assert.ok(result.cooldown > 2); assert.ok(result.mp < 90);
  for (const skill of ['qi', 'thrust', 'break', 'sweep']) assert.ok(result.skills.includes(skill)); assert.deepEqual(errors, []);
});

test('剑气遇掩体消散，贯穿击杀的事务替换状态后不重击、不重复回气', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d = __duko; d.G.p.x = 870; d.G.p.y = 906; d.G.p.face = 0;
    const e = d.G.enemies[0]; Object.assign(e, { x: 1010, y: 906, hx: 1010, hy: 906, hp: 500, maxHp: 500, hostile: true, state: 'idle' });
    for (const other of d.G.enemies.slice(1)) other.hostile = false;
    d.skill(0); d.step(.01, 45); const blockedHp = e.hp;
    d.G.p.x = 900; d.G.p.y = 870; d.G.p.face = 0; d.G.p.mp = 100; d.G.orn = '回气'; d.G.chapter.cooldowns[0] = 0;
    for (let i = 0; i < 2; i++) Object.assign(d.G.enemies[i], { x: 1010 + i * 55, y: 870, hx: 1010 + i * 55, hy: 870, hp: 40, state: 'idle', hostile: true, alive: true });
    d.skill(0); d.step(.01, 110);
    return { blockedHp, hp: d.G.enemies.slice(0, 2).map(e => e.hp), returned: d.G.stats.qiBack, defeatedReceipts: Object.keys(d.G.receipts).filter(k => k.startsWith('defeat:')).length };
  });
  assert.equal(result.blockedHp, 500); assert.deepEqual(result.hp, [0, 0]); assert.equal(result.returned, 18); assert.equal(result.defeatedReceipts, 2); assert.deepEqual(errors, []);
});

test('章节任务、剑饰与地图照常工作，刷新恢复新版进度且不继承未完成剑光', async t => {
  const { page, errors } = await pageFor(t);
  await page.evaluate(() => {
    const d = __duko; Object.assign(d.G.p, d.locations.NPCS[0]); d.interact(); d.doAct('accept');
    if (d.G.dlg?.opts.some(o => o.key === 'close')) d.doAct('close');
    Object.assign(d.G.p, d.locations.CRATE); d.interact();
    Object.assign(d.G.p, d.locations.NPCS[3]); d.interact(); d.doAct('craft_ps');
  });
  assert.equal((await snapshot(page)).orn, '破势'); assert.equal((await snapshot(page)).f.accepted, true);
  await page.reload(); await page.locator('#bStart').tap(); const g = await snapshot(page);
  assert.equal(g.orn, '破势'); assert.equal(g.f.accepted, true); assert.equal(g.swings.length, 0); assert.equal(g.qi.length, 0);
  await page.locator('#bMap').tap(); await page.locator('#tabSkills').tap(); assert.ok((await page.locator('#atlasBody').innerText()).includes('松风剑气')); assert.deepEqual(errors, []);
});

test('试玩记录只按主动施放记命中或空挥，普攻不污染，取消只结算一次', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d = __duko; Object.assign(d.G.p, { x: 900, y: 870, face: 0 });
    const e = d.G.enemies[0]; Object.assign(e, { x: 980, y: 870, hx: 980, hy: 870, hp: 500, maxHp: 500, state: 'idle', hostile: true });
    for (const other of d.G.enemies.slice(1)) other.hostile = false;
    d.attack(); d.step(.01, 60); const ordinary = structuredClone(d.G.playtest.combat);
    d.G.p.face = 0; d.skill(0); d.step(.01, 110); const hit = structuredClone(d.G.playtest.combat);
    for (const foe of d.G.enemies) foe.hostile = false;
    d.G.chapter.cooldowns[0] = 0; d.G.p.mp = 100; d.skill(0); d.step(.01, 110);
    const miss = structuredClone(d.G.playtest.combat);
    d.G.chapter.cooldowns[0] = 0; d.G.p.mp = 100; d.skill(0); d.dodge(); d.step(.01, 80);
    return { ordinary, hit, miss, canceled: d.G.playtest.combat, build: d.recordPayload().build };
  });
  assert.equal(result.ordinary.casts, 0); assert.equal(result.ordinary.hits, 0);
  assert.equal(result.hit.casts, 1); assert.equal(result.hit.hits, 1); assert.equal(result.hit.misses, 0);
  assert.equal(result.miss.casts, 2); assert.equal(result.miss.hits, 1); assert.equal(result.miss.misses, 1);
  assert.equal(result.canceled.casts, 3); assert.equal(result.canceled.hits, 1); assert.equal(result.canceled.misses, 2);
  assert.equal(result.build, 'V0.4-songfeng-clear1-20261023'); assert.deepEqual(errors, []);
});

test('回澜斩跨帧扫过的扇区不漏判，同一目标与回气只结算一次', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d=__duko,results=[];
    for(const dt of [.01,.05]){
      Object.assign(d.G.p,{x:900,y:870,face:0,mp:100,sp:100,dodge:0});d.G.orn='回气';d.G.chapter.skills[0]='sweep';d.G.chapter.cooldowns[0]=0;
      const e=d.G.enemies[0],x=900+Math.cos(Math.PI/9)*100,y=870+Math.sin(Math.PI/9)*100;
      Object.assign(e,{x,y,hx:x,hy:y,hp:500,maxHp:500,state:'windup',t:0,atk:{tele:100,inter:false},hostile:true,alive:true});
      for(const other of d.G.enemies.slice(1))other.hostile=false;
      const before={...d.G.playtest.combat};d.skill(0);d.step(dt,Math.ceil(1/dt));
      results.push({hp:d.G.enemies[0].hp,hits:d.G.playtest.combat.hits-before.hits,returned:d.G.playtest.combat.qiReturned-before.qiReturned});
    }
    return results;
  });
  for(const r of result){assert.equal(r.hp,478);assert.equal(r.hits,1);assert.equal(r.returned,18);} assert.deepEqual(errors,[]);
});

test('存档副本与败退将未完成施放归为空挥，存档不改变仍飞行的实时剑气', async t => {
  const { page, errors } = await pageFor(t);
  const result = await page.evaluate(() => {
    const d=__duko;Object.assign(d.G.p,{x:900,y:870,face:0,mp:100});
    for(const e of d.G.enemies)e.hostile=false;
    d.skill(0);d.step(.01,8);const liveBefore={...d.G.playtest.combat};
    d.commit('test-pending','保存检查',()=>{});
    const saved=d.loadSave().G,liveAfter={...d.G.playtest.combat},pending=d.G.qi.length;
    d.respawn();return {saved:saved.playtest.combat,savedPending:saved.qi.length+saved.swings.length,liveBefore,liveAfter,pending,respawned:d.G.playtest.combat,pendingAfter:d.G.qi.length+d.G.swings.length};
  });
  assert.equal(result.saved.casts,1);assert.equal(result.saved.hits,0);assert.equal(result.saved.misses,1);assert.equal(result.savedPending,0);
  assert.deepEqual(result.liveAfter,result.liveBefore);assert.equal(result.liveAfter.misses,0);assert.equal(result.pending,1);
  assert.equal(result.respawned.misses,1);assert.equal(result.pendingAfter,0);assert.deepEqual(errors,[]);
});

test('声音默认关闭，主动开启后产生声音，暂停与关闭清除声音', async t => {
  const context=await browser.newContext({viewport:{width:844,height:390}});t.after(()=>context.close());
  await context.addInitScript(()=>{
    window.audioAudit={created:0,started:0,stopped:0};const Original=window.AudioContext;
    window.AudioContext=class extends Original{
      constructor(...args){super(...args);audioAudit.created++;}
      createOscillator(){return wrap(super.createOscillator());}
      createBufferSource(){return wrap(super.createBufferSource());}
    };
    function wrap(source){for(const [method,key] of [['start','started'],['stop','stopped']]){const original=source[method].bind(source);source[method]=(...args)=>{audioAudit[key]++;return original(...args);};}return source;}
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.locator('#bStart').click();await page.keyboard.press('j');await page.waitForTimeout(300);
  assert.equal((await page.evaluate(()=>audioAudit)).created,0);
  await page.locator('#bSound').click();await page.keyboard.down('j');await page.waitForTimeout(400);await page.keyboard.up('j');
  const active=await page.evaluate(()=>audioAudit);assert.equal(active.created,1);assert.ok(active.started>0);
  await page.locator('#bPause').click();const paused=await page.evaluate(()=>audioAudit);await page.waitForTimeout(350);
  assert.equal((await page.evaluate(()=>audioAudit)).started,paused.started);assert.ok(paused.stopped>=paused.started);
  await page.locator('#bResume').click();await page.locator('#bSound').click();const muted=await page.evaluate(()=>audioAudit);
  await page.keyboard.press('j');await page.waitForTimeout(300);assert.equal((await page.evaluate(()=>audioAudit)).started,muted.started);assert.deepEqual(errors,[]);
});

test('发布白名单与HEAD生效，不提供测试、源服务与备份', async () => {
  for(const route of ['game.js','combat-render.mjs','songfeng-render.mjs','songfeng-feedback.mjs','songfeng-ui.css']){
    const response=await fetch(base+route);assert.equal(response.status,200);assert.equal(response.headers.get('cache-control'),'no-store');
    const head=await fetch(base+route,{method:'HEAD'});assert.equal(head.status,200);assert.equal(await head.text(),'');assert.equal(head.headers.get('content-length'),response.headers.get('content-length'));
  }
  for(const route of ['server.mjs','README.md','验收/验收记录.md','../V0.4/game.js','部署/保护基线位置.txt'])assert.equal((await fetch(base+route)).status,404);
  assert.equal((await fetch(base,{method:'POST',body:'test'})).status,405);assert.equal((await (await fetch(base+'healthz')).json()).service,'qingshi-v04');
});

test('普攻与剑气同帧击杀触发事务后，只发射一枚剑气且后方目标只受一次伤害', async t => {
 const {page,errors}=await pageFor(t);
 const result=await page.evaluate(()=>{
  const d=__duko;Object.assign(d.G.p,{x:900,y:870,face:0,mp:100});
  for(const e of d.G.enemies)e.hostile=false;
  for(let i=0;i<2;i++)Object.assign(d.G.enemies[i],{x:980+i*80,y:870,hx:980+i*80,hy:870,hp:i?500:20,maxHp:500,state:'windup',atk:{tele:100,inter:false},hostile:true,alive:true});
  d.attack();d.skill(0);let maxShots=0;for(let i=0;i<130;i++){d.step(.01,1);maxShots=Math.max(maxShots,d.G.qi.length);}
  return {maxShots,hp:d.G.enemies.slice(0,2).map(e=>e.hp),combat:d.G.playtest.combat};
 });
 assert.equal(result.maxShots,1);assert.deepEqual(result.hp,[0,456]);assert.equal(result.combat.casts,1);assert.equal(result.combat.hits,1);assert.equal(result.combat.misses,0);assert.deepEqual(errors,[]);
});

test('既有V0.4旧结构存档保留位置、物品、任务和携带武学，补齐渲染临时状态',async t=>{
 const {page,context,errors}=await pageFor(t);
 const legacy=await page.evaluate(()=>{
  const g=structuredClone(__duko.G);g.p.x=700;g.p.y=750;g.inv.coin=77;g.f.accepted=true;g.chapter.skills=['thrust','sweep'];
  delete g.swings;delete g.qi;delete g.combatSerial;delete g.manualPaused;delete g.p.sp;for(const e of g.enemies)delete e.maxHp;return g;
 });
 await context.addInitScript(g=>localStorage.setItem('qingshi-chapter-v04',JSON.stringify({v:4,at:Date.now(),G:g})),legacy);
 await page.reload();assert.equal(await page.locator('#bStart').innerText(),'继续');await page.locator('#bStart').tap();
 const g=await snapshot(page);assert.equal(g.p.x,700);assert.equal(g.p.y,750);assert.equal(g.inv.coin,77);assert.equal(g.f.accepted,true);assert.deepEqual(g.chapter.skills,['thrust','sweep']);
 assert.equal(g.p.sp,100);assert.deepEqual(g.swings,[]);assert.deepEqual(g.qi,[]);assert.deepEqual(errors,[]);
});
