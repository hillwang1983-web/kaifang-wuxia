import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const assets = ['index.html', 'chapter.js', 'playtest.js', 'game.js', 'songfeng-ui.css', 'combat-render.mjs', 'songfeng-render.mjs', 'songfeng-feedback.mjs', 'world-art.mjs'];
// 发布目录包含历史CC0素材与松风原创图集，保持旧版可回退。
const artDirs = ['assets/na', 'assets/songfeng'];
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const readJSON = path => JSON.parse(readFileSync(path, 'utf8'));
function run(command, args, cwd) { execFileSync(command, args, { cwd, stdio: 'inherit' }); }
function git(repo, args) { return execFileSync('git', args, { cwd: repo, encoding: 'utf8' }).trim(); }

export async function withLock(home, task) {
  const lock = join(home, '.update-lock');
  try { mkdirSync(lock); }
  catch (error) { if (error.code === 'EEXIST') throw Error('该试玩正在更新；若上次进程异常退出，请确认无更新进程后再移除 .update-lock'); throw error; }
  try { return await task(); }
  finally { rmSync(lock, { recursive: true, force: true }); }
}

export async function testThenPublish(test, publish) { await test(); return publish(); }

// 组装发布目录：public/ 放游戏资源与美术目录，lib/ 放服务库；返回每个文件的哈希
export function stageRelease(source, stage, commit) {
  mkdirSync(join(stage, 'public')); mkdirSync(join(stage, 'lib'));
  for (const name of assets) copyFileSync(join(source, '原型/V0.4', name), join(stage, 'public', name));
  for(const artDir of artDirs)cpSync(join(source, '原型/V0.4', artDir), join(stage, 'public', artDir), { recursive: true });
  copyFileSync(join(source, 'portal-integration/server.mjs'), join(stage, 'lib/server.mjs'));
  writeFileSync(join(stage, 'server.mjs'), `import { createQingshiServer } from './lib/server.mjs';\nconst server = createQingshiServer(new URL('./public/', import.meta.url), { commit: '${commit}' });\nserver.once('error', error => { console.error(error.message); process.exitCode = 1; });\nserver.listen(8793, '127.0.0.1');\nfor (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => server.close());\n`);
  // A source without commit-aware health cannot produce a verifiable release.
  if (!readFileSync(join(stage, 'lib/server.mjs'), 'utf8').includes('release.commit')) throw Error('远端版本缺少提交号健康检查支持，请先合入发布脚本 PR');
  const art = artDirs.flatMap(artDir=>readdirSync(join(stage,'public',artDir),{recursive:true,withFileTypes:true}).filter(entry=>entry.isFile())
    .map(entry=>'public/'+relative(join(stage,'public'),join(entry.parentPath,entry.name)).split(sep).join('/'))).sort();
  return Object.fromEntries(['server.mjs', 'lib/server.mjs', ...assets.map(name => 'public/' + name), ...art].map(name => [name, hash(readFileSync(join(stage, name)))]));
}

export async function publishRelease({ home, stage, manifest, restart, verify }) {
  const app = join(home, 'app'), manifestPath = join(home, 'runtime-manifest.json');
  const backups = join(home, 'backups'); mkdirSync(backups, { recursive: true });
  const backup = mkdtempSync(join(backups, new Date().toISOString().replaceAll(':', '-') + '-'));
  const oldManifest = readJSON(manifestPath);
  copyFileSync(manifestPath, join(backup, 'runtime-manifest.json'));
  renameSync(app, join(backup, 'app'));
  try {
    renameSync(stage, app);
    writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
    await restart(); await verify(manifest);
    return { backup };
  } catch (error) {
    try {
      if (existsSync(app)) renameSync(app, join(backup, 'failed-app'));
      renameSync(join(backup, 'app'), app);
      copyFileSync(join(backup, 'runtime-manifest.json'), manifestPath);
      await restart(); await verify(oldManifest);
    } catch (rollback) { throw Error(`${error.message}；回退检查失败：${rollback.message}；恢复资料：${backup}`); }
    throw Error(`${error.message}；已回退并验证旧服务；资料：${backup}`);
  }
}

export async function verifyLocal(manifest, base = 'http://127.0.0.1:8793') {
  const response = await fetch(base + '/healthz', { signal: AbortSignal.timeout(3000) });
  if (response.status !== 200) throw Error('本机健康接口不是 200');
  const health = await response.json();
  if (health.service !== 'qingshi-v04' || (manifest.commit ? health.commit !== manifest.commit : health.version !== manifest.version)) throw Error('本机运行版本不符');
  // 回退到只有四个资源的旧版时，新增模块按该次发布清单决定是否校验。
  for (const name of assets.filter((name,i)=>i<4||manifest.files?.['public/'+name]!==undefined)) {
    const response = await fetch(base + '/qingshi-v04/' + (name === 'index.html' ? '' : name), { signal: AbortSignal.timeout(3000) });
    if (response.status !== 200 || hash(Buffer.from(await response.arrayBuffer())) !== manifest.files['public/' + name]) throw Error('资源哈希不符：' + name);
  }
  for (const [path, digest] of Object.entries(manifest.files || {})) {
    if (!artDirs.some(dir=>path.startsWith('public/'+dir+'/'))) continue;
    const response = await fetch(base + '/qingshi-v04/' + encodeURI(path.slice('public/'.length)), { signal: AbortSignal.timeout(3000) });
    if (response.status !== 200 || hash(Buffer.from(await response.arrayBuffer())) !== digest) throw Error('素材哈希不符：' + path.slice('public/'.length));
  }
}

export async function verifyPublic(base) {
  const health = await fetch(base + '/healthz', { signal: AbortSignal.timeout(15000), redirect: 'manual' });
  if (health.status !== 200 || (await health.json()).service !== 'game-portal') throw Error('公网看板健康检查失败');
  for (const path of ['/qingshi-v04/', '/qingshi-v04/game.js']) {
    const response = await fetch(base + path, { signal: AbortSignal.timeout(15000), redirect: 'manual' });
    if (response.status !== 303 || response.headers.get('location') !== '/login?game=qingshi-v04') throw Error('公网试玩登录拦截异常：' + path);
  }
  const login = await fetch(base + '/login?game=qingshi-v04', { signal: AbortSignal.timeout(15000) });
  if (login.status !== 200 || !(await login.text()).includes('action="/login?game=qingshi-v04"')) throw Error('公网试玩登录入口缺失');
  return '公网看板健康、青石渡登录入口和未登录资源拦截通过；未执行公网登录后试玩';
}

async function main() {
  const { values } = parseArgs({ options: { remote: { type: 'string', default: 'origin' }, branch: { type: 'string', default: 'main' }, config: { type: 'string' }, 'check-only': { type: 'boolean', default: false } } });
  const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const config = readJSON(values.config ? resolve(values.config) : join(repo, '.preview-deploy.local.json'));
  const home = resolve(config.serviceHome);
  if (process.platform !== 'darwin') throw Error('发布脚本当前仅支持已配置 launchd 的 macOS 主机');
  if (!lstatSync(join(home, 'app')).isDirectory() || lstatSync(join(home, 'app')).isSymbolicLink()) throw Error('服务 app 必须是现有普通目录');
  const service = `gui/${process.getuid()}/${config.launchLabel}`;
  const publicOrigin = new URL(config.publicOrigin).origin;
  if (!publicOrigin.startsWith('https://')) throw Error('公网地址必须使用 HTTPS');
  await withLock(home, async () => {
    run('git', ['fetch', '--', values.remote], repo);
    const commit = git(repo, ['rev-parse', '--verify', `refs/remotes/${values.remote}/${values.branch}^{commit}`]);
    console.log(`更新来源：${values.remote}/${values.branch} @ ${commit}`);
    const source = mkdtempSync(join(tmpdir(), 'qingshi-source-'));
    let stage;
    try {
      const archive = execFileSync('git', ['archive', commit], { cwd: repo, maxBuffer: 64 * 1024 * 1024 });
      execFileSync('tar', ['-xf', '-', '-C', source], { input: archive });
      for (const file of ['package-lock.json', 'portal-integration/server.mjs', ...assets.map(name => '原型/V0.4/' + name), ...artDirs.map(dir=>'原型/V0.4/'+dir)]) {
        if (!existsSync(join(source, file))) throw Error('该分支缺少 V0.4 发布文件：' + file);
      }
      await testThenPublish(async () => {
        run('npm', ['ci'], source);
        run('npx', ['--no-install', 'playwright', 'install', 'chromium'], source);
        run('npm', ['run', 'test:all'], source);
      }, async () => {
        if (values['check-only']) { console.log('CHECK ONLY：测试通过，未发布。'); return; }
        execFileSync('launchctl', ['print', service]);
        const plist = join(process.env.HOME, 'Library/LaunchAgents', config.launchLabel + '.plist');
        const args = JSON.parse(execFileSync('plutil', ['-extract', 'ProgramArguments', 'json', '-o', '-', plist], { encoding: 'utf8' }));
        if (!args.includes(join(home, 'app/server.mjs'))) throw Error('LaunchAgent 与发布目录不匹配');
        await verifyPublic(publicOrigin);
        stage = mkdtempSync(join(home, '.candidate-'));
        const files = stageRelease(source, stage, commit);
        run(process.execPath, ['--check', join(stage, 'server.mjs')], repo);
        const manifest = { version: 'git-' + commit.slice(0, 12), commit, remote: values.remote, branch: values.branch, builtAt: new Date().toISOString(), files };
        const verify = async expected => {
          let failure;
          for (let attempt = 0; attempt < 30; attempt++) {
            try { await verifyLocal(expected); failure = null; break; }
            catch (error) { failure = error; await sleep(500); }
          }
          if (failure) throw failure;
          await verifyPublic(publicOrigin);
        };
        const result = await publishRelease({ home, stage, manifest, restart: () => run('launchctl', ['kickstart', '-k', service], repo), verify });
        stage = null;
        const receipt = { ...manifest, backup: result.backup, finishedAt: new Date().toISOString(), tests: 'npm ci + npm run test:all exit 0', publicEvidence: '公网入口及鉴权检查通过；精确资源版本由本机提交号与四个资源哈希验证' };
        writeFileSync(join(home, 'last-update.json'), JSON.stringify(receipt, null, 2) + '\n');
        console.log(`发布成功：${commit}\n备份：${result.backup}\n公网看板：${publicOrigin}\n记录：${join(home, 'last-update.json')}`);
      });
    } finally {
      rmSync(source, { recursive: true, force: true });
      if (stage) rmSync(stage, { recursive: true, force: true });
    }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error('更新失败：' + error.message); process.exitCode = 1; });
}
