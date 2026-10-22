import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFileSync } from 'node:fs';
import { createQingshiServer } from './server.mjs';

test('Qingshi serves only release assets under its prefix, GET/HEAD and health', async t => {
  const server = createQingshiServer(new URL('../原型/V0.4/', import.meta.url));
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = 'http://127.0.0.1:' + server.address().port;
  for (const file of ['index.html', 'chapter.js', 'playtest.js', 'game.js']) {
    const path = file === 'index.html' ? '' : file + '?v=release';
    const response = await fetch(base + '/qingshi-v04/' + path);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), file.endsWith('.js') ? /javascript/ : /text\/html/);
    assert.equal(await response.text(), readFileSync(new URL('../原型/V0.4/' + file, import.meta.url), 'utf8'));
    const head = await fetch(base + '/qingshi-v04/' + path, { method: 'HEAD' });
    assert.equal(head.status, 200); assert.equal(await head.text(), '');
  }
  for (const file of ['assets/na/chars/player.png', 'assets/na/tiles/floor.png', 'assets/na/boss/idle.png']) {
    const response = await fetch(base + '/qingshi-v04/' + file);
    assert.equal(response.status, 200, file);
    assert.equal(response.headers.get('content-type'), 'image/png');
    assert.deepEqual(Buffer.from(await response.arrayBuffer()), readFileSync(new URL('../原型/V0.4/' + file, import.meta.url)));
  }
  assert.equal((await (await fetch(base + '/healthz')).json()).service, 'qingshi-v04');
  for (const path of ['/', '/qingshi-v04/README.md', '/qingshi-v04/assets/na/chars/', '/qingshi-v04/assets/',  '/qingshi-v04/../game.js', '/qingshi-v04/%2e%2e/game.js', '/qingshi-v04/server.mjs', '/qingshi-v04/试玩记录/']) {
    assert.equal((await fetch(base + path)).status, 404, path);
  }
  assert.equal((await fetch(base + '/qingshi-v04/', { method: 'POST', body: 'x' })).status, 405);
});
