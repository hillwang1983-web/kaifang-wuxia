import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const release = await import('../scripts/update-preview.mjs');
function fixture(t) {
  const home = mkdtempSync(join(tmpdir(), 'qingshi-release-test-'));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  for (const path of ['app', '.candidate', 'logs']) mkdirSync(join(home, path));
  writeFileSync(join(home, 'app/game.js'), 'old');
  writeFileSync(join(home, '.candidate/game.js'), 'new');
  writeFileSync(join(home, 'runtime-manifest.json'), '{"commit":"old"}');
  writeFileSync(join(home, 'logs/keep'), 'keep');
  return home;
}
test('成功发布保存旧资源和清单备份', async t => {
  assert.equal(typeof release.publishRelease, 'function');
  const home = fixture(t); let restarts = 0;
  const result = await release.publishRelease({ home, stage: join(home, '.candidate'), manifest: { commit: 'new' }, restart: () => { restarts++; }, verify: async () => {} });
  assert.equal(readFileSync(join(home, 'app/game.js'), 'utf8'), 'new');
  assert.equal(readFileSync(join(result.backup, 'app/game.js'), 'utf8'), 'old');
  assert.equal(readFileSync(join(result.backup, 'runtime-manifest.json'), 'utf8'), '{"commit":"old"}');
  assert.equal(restarts, 1);
  assert.equal(readFileSync(join(home, 'logs/keep'), 'utf8'), 'keep');
});
test('新版本健康失败则回退资源和清单，重新启动旧服务并非零报错', async t => {
  assert.equal(typeof release.publishRelease, 'function');
  const home = fixture(t); let restarts = 0, checks = 0;
  await assert.rejects(release.publishRelease({ home, stage: join(home, '.candidate'), manifest: { commit: 'bad' }, restart: () => { restarts++; }, verify: async () => { if (++checks === 1) throw Error('hash mismatch'); } }), /hash mismatch.*已回退/);
  assert.equal(readFileSync(join(home, 'app/game.js'), 'utf8'), 'old');
  assert.equal(readFileSync(join(home, 'runtime-manifest.json'), 'utf8'), '{"commit":"old"}');
  assert.equal(restarts, 2); assert.equal(checks, 2);
});
test('并发锁存在时不触碰当前运行资源', async t => {
  assert.equal(typeof release.withLock, 'function');
  const home = fixture(t); mkdirSync(join(home, '.update-lock'));
  await assert.rejects(release.withLock(home, async () => assert.fail('must not run')), /正在更新/);
  assert.equal(readFileSync(join(home, 'app/game.js'), 'utf8'), 'old');
  assert.ok(existsSync(join(home, '.update-lock')));
});
test('测试失败时停止，发布回调不会运行', async () => {
  assert.equal(typeof release.testThenPublish, 'function');
  let published = false;
  await assert.rejects(release.testThenPublish(async () => { throw Error('tests failed'); }, async () => { published = true; }), /tests failed/);
  assert.equal(published, false);
});

// 公网的真实登录页用 form action 区分游戏，并不显示游戏中文名。
test('公网检查接受带游戏路由的通用登录页，并核对鉴权拦截', async t => {
  const { createServer } = await import('node:http');
  const { once } = await import('node:events');
  const server = createServer((req, res) => {
    if (req.url === '/healthz') { res.end(JSON.stringify({ service: 'game-portal' })); return; }
    if (req.url === '/login?game=qingshi-v04') { res.end('<form action="/login?game=qingshi-v04" method="post"></form>'); return; }
    res.writeHead(303, { location: '/login?game=qingshi-v04' }); res.end();
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  await release.verifyPublic('http://127.0.0.1:' + server.address().port);
});
test('本机校验拒绝旧提交和资源字节不匹配', async t => {
  const { createServer } = await import('node:http');
  const { once } = await import('node:events');
  const server = createServer((req, res) => {
    res.end(req.url === '/healthz' ? JSON.stringify({ service: 'qingshi-v04', commit: 'old' }) : 'wrong bytes');
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = 'http://127.0.0.1:' + server.address().port;
  await assert.rejects(release.verifyLocal({ commit: 'new' }, base), /版本不符/);
  await assert.rejects(release.verifyLocal({ commit: 'old', files: { 'public/index.html': 'not-the-hash' } }, base), /资源哈希不符/);
});
test('发布目录带上素材，按发布结构启动的服务通过全部资源与素材哈希校验', async t => {
  const { once } = await import('node:events');
  const { fileURLToPath, pathToFileURL } = await import('node:url');
  const stage = mkdtempSync(join(tmpdir(), 'qingshi-stage-test-'));
  t.after(() => rmSync(stage, { recursive: true, force: true }));
  const files = release.stageRelease(fileURLToPath(new URL('..', import.meta.url)), stage, 'abc123');
  const art = Object.keys(files).filter(name => name.startsWith('public/assets/na/'));
  assert.ok(art.includes('public/assets/na/chars/player.png') && art.includes('public/assets/na/tiles/floor.png'), '清单缺少素材');
  assert.ok(existsSync(join(stage, 'public/assets/na/boss/idle.png')));
  for(const name of ['songfeng-ui.css','combat-render.mjs','songfeng-render.mjs','songfeng-feedback.mjs','songfeng-music.mjs','world-art.mjs','assets/songfeng/world-atlas.png'])assert.ok(files['public/'+name],name);
  const { createQingshiServer } = await import(pathToFileURL(join(stage, 'lib/server.mjs')).href);
  const server = createQingshiServer(pathToFileURL(join(stage, 'public') + '/'), { commit: 'abc123' });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = 'http://127.0.0.1:' + server.address().port;
  await release.verifyLocal({ commit: 'abc123', files }, base);
  const broken = { ...files, 'public/assets/na/chars/player.png': 'not-the-hash' };
  await assert.rejects(release.verifyLocal({ commit: 'abc123', files: broken }, base), /素材哈希不符：assets\/na\/chars\/player\.png/);
  await assert.rejects(release.verifyLocal({commit:'abc123',files:{...files,'public/world-art.mjs':'wrong'}},base),/资源哈希不符：world-art/);
  await assert.rejects(release.verifyLocal({commit:'abc123',files:{...files,'public/assets/songfeng/world-atlas.png':'wrong'}},base),/素材哈希不符：assets\/songfeng/);
});

test('回退校验兼容只有四个静态资源的旧运行清单',async t=>{
 const {createServer}=await import('node:http'),{once}=await import('node:events'),{createHash}=await import('node:crypto');
 const files=Object.fromEntries(['index.html','chapter.js','playtest.js','game.js'].map(name=>['public/'+name,createHash('sha256').update(name).digest('hex')]));
 const requests=[],server=createServer((req,res)=>{requests.push(req.url);if(req.url==='/healthz'){res.end(JSON.stringify({service:'qingshi-v04',commit:'legacy'}));return;}
  const name=req.url==='/qingshi-v04/'?'index.html':req.url.slice('/qingshi-v04/'.length);if(files['public/'+name])res.end(name);else res.writeHead(404).end();});
 server.listen(0,'127.0.0.1');await once(server,'listening');t.after(()=>new Promise(r=>server.close(r)));
 await release.verifyLocal({commit:'legacy',files},'http://127.0.0.1:'+server.address().port);assert.equal(requests.some(p=>p.endsWith('.mjs')||p.endsWith('.css')),false);
});
