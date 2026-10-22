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
  assert.equal(await page.locator('meta[name="apple-mobile-web-app-status-bar-style"]').getAttribute('content', { timeout: 1000 }), 'black-translucent');
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
