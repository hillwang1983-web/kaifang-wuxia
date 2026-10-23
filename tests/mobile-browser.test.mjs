import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFileSync } from 'node:fs';
import { createQingshiServer } from '../portal-integration/server.mjs';

import { chromium } from 'playwright';
const server = createQingshiServer(new URL('../原型/V0.4/', import.meta.url));
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const base = 'http://127.0.0.1:' + server.address().port + '/qingshi-v04/';
let browser;
try { browser = await chromium.launch({ headless: true }); }
catch (error) { server.close(); throw error; }
test.after(async () => { await browser.close(); await new Promise(resolve => server.close(resolve)); });

test('battle touches cancel native zoom defaults without swallowing menu clicks', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage();
  await page.goto(base); await page.locator('#bStart').tap();
  const defaults = await page.evaluate(() => Object.fromEntries(['bAtk', 'bSk', 'bSk2', 'bDg', 'stickzone', 'cv', 'bMap'].map(id => {
    const event = new Event('touchend', { bubbles: true, cancelable: true });
    document.getElementById(id).dispatchEvent(event); return [id, event.defaultPrevented];
  })));
  assert.equal(defaults.bMap, false, 'map still relies on its normal click');
  for (const id of ['bAtk', 'bSk', 'bSk2', 'bDg', 'stickzone', 'cv']) assert.equal(defaults[id], true, id);
  const before = await page.evaluate(() => visualViewport.scale), cdp = await context.newCDPSession(page);
  const box = await page.locator('#bAtk').boundingBox();
  for (let i = 0; i < 8; i++) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: box.x + box.width / 2, y: box.y + box.height / 2, id: 1 }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(70);
  }
  assert.equal(await page.evaluate(() => visualViewport.scale), before);
  await page.locator('#bMap').tap(); assert.equal(await page.locator('#atlas').isVisible(), true);
});

test('unsupported iPhone fullscreen shows visible home-screen instructions at start', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close());
  await context.addInitScript(() => {
    for (const name of ['requestFullscreen', 'webkitRequestFullscreen', 'webkitRequestFullScreen']) Object.defineProperty(Element.prototype, name, { configurable: true, value: undefined });
  });
  const page = await context.newPage(); await page.goto(base); await page.locator('#bFull').tap();
  assert.equal(await page.locator('#fullHint').isVisible(), true);
  assert.match(await page.locator('#fullHint').innerText(), /Chrome.*分享.*添加到主屏幕/);
  assert.equal(await page.locator('meta[name="apple-mobile-web-app-capable"]').getAttribute('content'), 'yes');
});

test('rejected native fullscreen requests show readable feedback instead of a hidden toast', async t => {
  const context = await browser.newContext(); t.after(() => context.close());
  await context.addInitScript(() => {
    Element.prototype.requestFullscreen = () => Promise.reject(new Error('Browser denied request'));
  });
  const page = await context.newPage(); await page.goto(base); await page.locator('#bFull').click();
  await page.locator('#fullHint').waitFor({ state: 'visible' });
  assert.match(await page.locator('#fullHint').innerText(), /未能进入全屏/);
});

test('supported browser enters and exits real fullscreen from a user click', async t => {
  const context = await browser.newContext(); t.after(() => context.close());
  const page = await context.newPage(); await page.goto(base); await page.locator('#bFull').click();
  await page.waitForFunction(() => !!document.fullscreenElement);
  await page.locator('#bFull').click(); await page.waitForFunction(() => !document.fullscreenElement);
});

test('home-screen standalone mode is recognized without requesting fullscreen again', async t => {
  const context = await browser.newContext(); t.after(() => context.close());
  await context.addInitScript(() => Object.defineProperty(navigator, 'standalone', { value: true }));
  const page = await context.newPage(); await page.goto(base);
  assert.match(await page.locator('#bFull').innerText(), /桌面模式/);
  assert.equal(await page.locator('#bFull').isDisabled(), true);
});

test('zoom protection preserves simultaneous controls and native journal scrolling', async t => {
  const context = await browser.newContext(); t.after(() => context.close());
  const page = await context.newPage();
  const source = readFileSync(new URL('./browser-controls.js', import.meta.url), 'utf8');
  const run = new Function('return (' + source + ')')();
  const result = await run(page, base);
  assert.equal(result.simultaneousTouchMoveAttack, true);
  assert.equal(result.stopsOnRelease, true);
  assert.equal(result.nativeAtlasScroll, true);
  assert.equal(result.touchEquip, true);
});

test('home-screen content opts into the full screen beneath the status bar', async t => {
  const context = await browser.newContext(); t.after(() => context.close());
  const page = await context.newPage(); await page.goto(base);
  assert.equal(await page.locator('meta[name="apple-mobile-web-app-status-bar-style"]').getAttribute('content', { timeout: 10000 }), 'black-translucent');
});

test('game and canvas follow visual viewport resize without relying on window resize', async t => {
  const context = await browser.newContext({ viewport: { width: 874, height: 464 }, isMobile: true, hasTouch: true });
  t.after(() => context.close());
  // Geometry fixture: iOS can report a layout viewport taller than its visible viewport.
  await context.addInitScript(() => {
    window.testViewportGap = 62;
    Object.defineProperty(window.visualViewport, 'height', { get: () => innerHeight - window.testViewportGap });
  });
  const page = await context.newPage(); await page.goto(base); await page.locator('#bStart').tap();
  const geometry = () => page.evaluate(() => {
    const app = document.getElementById('app'), cv = document.getElementById('cv'), r = app.getBoundingClientRect();
    const controls = ['bAtk', 'bSk', 'bSk2', 'bDg', 'bMap'].map(id => {
      const b = document.getElementById(id).getBoundingClientRect(); return { id, bottom: b.bottom, right: b.right };
    });
    return { top: r.top, left: r.left, height: r.height, width: r.width, canvasHeight: cv.height, visibleHeight: visualViewport.height, controls };
  });
  let size = await geometry();
  assert.equal(size.height, 402, 'must not use the stale 464px layout height: '+JSON.stringify(size));
  assert.equal(size.top, 0); assert.equal(size.left, 0);
  assert.equal(size.canvasHeight, Math.round(size.height * await page.evaluate(() => Math.min(2, devicePixelRatio))));
  assert.ok(size.controls.every(c => c.bottom <= size.visibleHeight && c.right <= size.width));
  await page.evaluate(() => { window.testViewportGap = 98; visualViewport.dispatchEvent(new Event('resize')); });
  size = await geometry(); assert.equal(size.height, 366, 'visible viewport event must resize the game');
  await page.evaluate(() => { window.testViewportGap = 0; });
  await page.setViewportSize({ width: 402, height: 874 });
  await page.waitForFunction(() => document.getElementById('app').clientHeight === 874);
  await page.setViewportSize({ width: 874, height: 402 });
  await page.waitForFunction(() => document.getElementById('app').clientHeight === 402);
  size = await geometry(); assert.equal(size.height, 402); assert.equal(size.top, 0);
});

test('landscape touch controls preserve notch and home-indicator margins', async t => {
  const context = await browser.newContext({ viewport: { width: 874, height: 402 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage(); await page.goto(base); await page.locator('#bStart').tap();
  await page.evaluate(() => {
    document.documentElement.style.setProperty('--sl', '59px');
    document.documentElement.style.setProperty('--sr', '59px');
    document.documentElement.style.setProperty('--sb', '21px');
  });
  const positions = await page.evaluate(() => ['bAtk', 'bSk', 'bSk2', 'bDg', 'bMap'].map(id => {
    const r = document.getElementById(id).getBoundingClientRect();
    return { id, right: r.right, bottom: r.bottom };
  }));
  assert.ok(positions.every(r => r.right <= 874 - 59 && r.bottom <= 402 - 21), JSON.stringify(positions));
});

test('touch attacks stay in place without stick input, including after releasing the stick (#4)', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage();
  await page.goto(base + '?debug'); await page.locator('#bStart').tap();
  const cdp = await context.newCDPSession(page), box = await page.locator('#bAtk').boundingBox();
  const at = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const pos = () => page.evaluate(() => [__duko.G.p.x, __duko.G.p.y]);
  const tapAttack = async (times) => {
    for (let i = 0; i < times; i++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ id: 2, ...at }] });
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
      await page.waitForTimeout(260);
    }
  };
  const start = await pos(); await tapAttack(6);
  assert.deepEqual(await pos(), start, 'two full three-hit combos must not move the player');
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ id: 1, x: 80, y: 270 }] });
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ id: 1, x: 125, y: 270 }] });
  await page.waitForTimeout(150);
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await page.waitForTimeout(80); const released = await pos();
  assert.ok(released[0] > start[0], 'stick should still move the player');
  await tapAttack(3);
  assert.deepEqual(await pos(), released, 'attacks after releasing the stick keep no leftover movement');
});

test('double taps on HUD info under the minimap are blocked from zooming without swallowing single taps or button clicks (#9)', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage();
  await page.goto(base); await page.locator('#bStart').tap();
  await page.evaluate(() => {
    window.tapLog = [];
    addEventListener('touchend', e => tapLog.push(e.defaultPrevented));
    addEventListener('dblclick', e => tapLog.push('dbl:' + e.defaultPrevented));
  });
  const cdp = await context.newCDPSession(page);
  const center = async (selector) => {
    const b = await page.locator(selector).first().boundingBox(), x = b.x + b.width / 2, y = b.y + b.height / 2;
    assert.ok(await page.evaluate(([s, x, y]) => document.elementFromPoint(x, y)?.closest(s) !== null, [selector, x, y]), selector + ' is the tap target');
    return { x, y };
  };
  const tap = async (p, id) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ id, ...p }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  };
  const scale = await page.evaluate(() => visualViewport.scale);
  // 铜钱信息条：真实触摸，单击放行、快速的第二下被拦
  const chip = await center('#res .chip:not(button)');
  await page.waitForTimeout(500); await page.evaluate(() => { tapLog.length = 0; });
  await tap(chip, 1); await page.waitForTimeout(500); await tap(chip, 2); await page.waitForTimeout(80); await tap(chip, 3); await page.waitForTimeout(150);
  assert.deepEqual(await page.evaluate(() => tapLog.filter(v => typeof v === 'boolean')), [false, false, true], 'coin chip');
  // 小地图正下方 .songfeng-tools 的空白边距只有约 10px，真实触摸会被浏览器吸附到小地图按钮，这里直接在该元素上派发
  const gap = await page.evaluate(async () => {
    const el = document.querySelector('.songfeng-tools'), end = () => { const e = new TouchEvent('touchend', { bubbles: true, cancelable: true }); el.dispatchEvent(e); return e.defaultPrevented; };
    await new Promise(r => setTimeout(r, 500)); const first = end(); await new Promise(r => setTimeout(r, 80)); return [first, end()];
  });
  assert.deepEqual(gap, [false, true], 'gap under the minimap');
  assert.equal(await page.evaluate(() => visualViewport.scale), scale);
  const sound = await center('#bSound'), before = await page.locator('#bSound span').innerText();
  await tap(sound, 4); await page.waitForTimeout(80); await tap(sound, 5); await page.waitForTimeout(150);
  assert.equal(await page.locator('#bSound span').innerText(), before, 'both quick taps on a button still click (toggled on then off)');
  await page.evaluate(() => { tapLog.length = 0; document.querySelector('.songfeng-tools').dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true })); });
  assert.deepEqual(await page.evaluate(() => tapLog), ['dbl:true']);
  await page.locator('#bMap').tap(); assert.equal(await page.locator('#atlas').isVisible(), true);
});

test('quest panel opens briefly on start and on objective change, then collapses to one line; tapping reopens it (#13)', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage();
  await page.clock.install();
  await page.goto(base + '?debug'); await page.locator('#bStart').tap();
  const state = () => page.evaluate(() => ({ collapsed: document.getElementById('quest').classList.contains('collapsed'), detail: getComputedStyle(document.getElementById('qs')).display !== 'none', h: Math.round(document.getElementById('quest').getBoundingClientRect().height) }));
  await page.clock.runFor(1000);
  const open = await state(); assert.equal(open.collapsed, false); assert.equal(open.detail, true);
  await page.clock.runFor(6000);
  const shut = await state(); assert.equal(shut.collapsed, true); assert.equal(shut.detail, false); assert.ok(shut.h < open.h, 'collapsed panel is shorter');
  assert.match(await page.locator('#qt').innerText(), /\S/, 'current objective title stays visible');
  const before = await page.evaluate(() => [__duko.G.p.x, __duko.G.p.y]);
  await page.locator('#quest').tap(); await page.clock.runFor(200);
  assert.equal((await state()).collapsed, false, 'tap reopens');
  assert.deepEqual(await page.evaluate(() => [__duko.G.p.x, __duko.G.p.y]), before, 'tapping the panel does not move the player');
  await page.clock.runFor(9000); assert.equal((await state()).collapsed, true);
  await page.evaluate(() => { __duko.G.f.accepted = true; }); await page.clock.runFor(200);
  assert.equal((await state()).collapsed, false, 'objective change reopens');
  await page.clock.runFor(7000); assert.equal((await state()).collapsed, true);
  await page.reload(); await page.locator('#bStart').tap(); await page.clock.runFor(1000);
  assert.equal((await state()).collapsed, false, 'after reload it opens briefly again');
  await page.clock.runFor(6500); assert.equal((await state()).collapsed, true, 'and does not stay open');
});

test('the small talk marker stays on its NPC when the camera is clamped at the map edge (#17)', async t => {
  const context = await browser.newContext({ viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true });
  t.after(() => context.close()); const page = await context.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(base + '?debug'); await page.locator('#bStart').tap();
  const check = (placement) => page.evaluate(async (placement) => {
    const d = __duko, G = d.G, npc = placement === 'edge' ? [...d.NPCS].sort((a, b) => a.x - b.x)[0] : d.NPCS.find(n => n.x > 900) || d.NPCS[1];
    for (const e of G.enemies) e.alive = false;
    G.p.x = npc.x + 40; G.p.y = npc.y;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const el = document.getElementById('nearTalk'), app = document.getElementById('app').getBoundingClientRect();
    const { ox, oy, Z, U } = d.CAM, vw = app.width;
    return { name: npc.name, hidden: el.hidden, text: el.textContent, left: parseFloat(el.style.left), top: parseFloat(el.style.top),
      expectX: (npc.x / U - ox) * Z, expectY: (npc.y / U - oy) * Z + 4, oldX: vw / 2 + (npc.x - G.p.x) / U * Z };
  }, placement);
  const edge = await check('edge');
  assert.equal(edge.hidden, false, 'marker shows near ' + edge.name); assert.match(edge.text, new RegExp(edge.name));
  assert.ok(Math.abs(edge.left - edge.expectX) < 2 && Math.abs(edge.top - edge.expectY) < 2, JSON.stringify(edge));
  assert.ok(Math.abs(edge.oldX - edge.expectX) > 20, 'scenario really clamps the camera: ' + JSON.stringify(edge));
  const mid = await check('middle');
  assert.equal(mid.hidden, false); assert.ok(Math.abs(mid.left - mid.expectX) < 2 && Math.abs(mid.top - mid.expectY) < 2, JSON.stringify(mid));
  assert.deepEqual(errors, []);
});

test('start / continue card fits common landscape phones and scrolls with a fade on tiny ones (#18)', async t => {
  const open = async (viewport, mobile = true) => {
    const context = await browser.newContext({ viewport, isMobile: mobile, hasTouch: mobile });
    t.after(() => context.close());
    await context.addInitScript(() => { Object.defineProperty(navigator, 'standalone', { get: () => true }); });
    const page = await context.newPage(); await page.goto(base);
    await page.locator('#bStart').click(); await page.waitForTimeout(200); await page.reload(); await page.waitForTimeout(300);
    assert.equal(await page.locator('#bStart').innerText(), '继续'); return page;
  };
  const measure = page => page.evaluate(() => {
    const card = document.querySelector('#start .songfeng-intro'), c = card.getBoundingClientRect();
    const buttons = [...card.querySelectorAll('.row button:not([hidden])')].map(b => b.getBoundingClientRect());
    return { scroll: card.scrollHeight, client: card.clientHeight, more: card.classList.contains('more'), hScroll: document.documentElement.scrollWidth > innerWidth,
      buttonsInside: buttons.every(r => r.left >= c.left - 1 && r.right <= c.right + 1), font: parseFloat(getComputedStyle(card.querySelector('.songfeng-intro-body p:nth-of-type(2)')).fontSize),
      keyboardRow: getComputedStyle(card.querySelector('.keys dd.kb')).display };
  });
  for (const viewport of [{ width: 844, height: 390 }, { width: 852, height: 340 }, { width: 740, height: 360 }, { width: 667, height: 375 }]) {
    const m = await measure(await open(viewport));
    assert.ok(m.scroll <= m.client + 1, JSON.stringify({ viewport, m })); assert.equal(m.more, false);
    assert.equal(m.hScroll, false); assert.ok(m.buttonsInside); assert.ok(m.font >= 12); assert.equal(m.keyboardRow, 'none', 'touch devices hide the keyboard row');
  }
  const tiny = await open({ width: 568, height: 320 }), before = await measure(tiny);
  assert.ok(before.scroll > before.client && before.more, 'tiny screens scroll and show the fade: ' + JSON.stringify(before));
  const after = await tiny.evaluate(async () => {
    const card = document.querySelector('#start .songfeng-intro'); card.scrollTop = card.scrollHeight;
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    const last = document.querySelector('.songfeng-separate').getBoundingClientRect(), c = card.getBoundingClientRect();
    return { more: card.classList.contains('more'), lastVisible: last.bottom <= c.bottom + 1, startVisible: !document.getElementById('start').hidden };
  });
  assert.deepEqual(after, { more: false, lastVisible: true, startVisible: true }, 'scrolling reaches the end without starting the game');
  const desktop = await measure(await open({ width: 1280, height: 720 }, false));
  assert.notEqual(desktop.keyboardRow, 'none', 'desktop keeps the keyboard row'); assert.ok(desktop.scroll <= desktop.client + 1);
});
