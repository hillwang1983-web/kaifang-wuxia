import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { pathToFileURL } from 'node:url';

test('山寺发布包限定导出文件、正确提供 WASM 类型并验证运行提交和全部资源', async t => {
  const { stageShansi, verifyShansi } = await import('../scripts/build-shansi-preview.mjs');
  const root = mkdtempSync(join(tmpdir(), 'shansi-test-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const web = join(root, 'web'), app = join(root, 'app'); mkdirSync(web);
  for (const name of ['index.html', 'index.js', 'index.wasm', 'index.pck', 'index.png']) writeFileSync(join(web, name), name);
  writeFileSync(join(web, 'secret.key'), 'do not publish');
  const manifest = stageShansi(web, app, 'abc123');
  assert.equal(manifest.files['public/secret.key'], undefined);
  const { createShansiServer } = await import(pathToFileURL(join(app, 'lib/shansi-server.mjs')));
  const server = createShansiServer(pathToFileURL(join(app, 'public') + '/'), { commit: 'abc123' });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = 'http://127.0.0.1:' + server.address().port;
  const response = await fetch(base + '/index.wasm');
  assert.equal(response.headers.get('content-type'), 'application/wasm');
  assert.equal(await response.text(), 'index.wasm');
  for (const path of ['/secret.key', '/server.mjs', '/%2e%2e/server.mjs']) assert.equal((await fetch(base + path)).status, 404);
  assert.equal((await fetch(base + '/', { method: 'POST', body: 'x' })).status, 405);
  await verifyShansi(manifest, base, app);
  await assert.rejects(verifyShansi({ ...manifest, commit: 'old' }, base, app), /提交号/);
  writeFileSync(join(app, 'lib/shansi-server.mjs'), 'changed');
  await assert.rejects(verifyShansi(manifest, base, app), /哈希/);
  assert.equal(readFileSync(join(app, 'public/index.pck'), 'utf8'), 'index.pck');
});

test('Godot 即使返回零也拒绝脚本错误和未到结算的冒烟结果', async () => {
  const { checkGodotResult } = await import('../scripts/build-shansi-preview.mjs');
  assert.throws(() => checkGodotResult({ status: 1, stdout: '', stderr: '' }), /退出码/);
  assert.throws(() => checkGodotResult({ status: 0, stdout: 'SCRIPT ERROR: broken', stderr: '' }), /SCRIPT ERROR/);
  assert.throws(() => checkGodotResult({ status: 0, stdout: 'started', stderr: '' }, '自动试玩结算'), /结算/);
  checkGodotResult({ status: 0, stdout: '自动试玩结算', stderr: '' }, '自动试玩结算');
});
