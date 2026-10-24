import { spawnSync, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { webAsset } from '../portal-integration/shansi-server.mjs';
import { archiveSource } from './update-preview.mjs';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

export function checkGodotResult(result, marker) {
  const log = (result.stdout || '') + (result.stderr || '');
  if (result.error || result.status !== 0) throw Error('Godot 退出码异常：' + result.status + ' ' + (result.error?.message || ''));
  if (/(?:SCRIPT ERROR|^ERROR:)/m.test(log)) throw Error('Godot SCRIPT ERROR/ERROR，停止发布');
  if (marker && !log.includes(marker)) throw Error('Godot 未完成：' + marker);
}

export function importShansi(project, run) {
  // 全新归档尚无字体缓存；只在临时副本首次导入时取消主题的前置加载。
  // 测试、通关和导出前按字节恢复原设置，仍严格检查全部引擎错误。
  const path = join(project, 'project.godot'), original = readFileSync(path);
  try {
    writeFileSync(path, original.toString().replace(/^theme\/custom=.*$/m, 'theme/custom=""'));
    run(['--import']);
  } finally { writeFileSync(path, original); }
}

export function stageShansi(web, app, commit, source = repo) {
  mkdirSync(join(app, 'public'), { recursive: true }); mkdirSync(join(app, 'lib'));
  const names = readdirSync(web).filter(name => webAsset.test(name)).sort();
  for (const required of ['index.html', 'index.js', 'index.wasm', 'index.pck']) if (!names.includes(required)) throw Error('缺少导出文件：' + required);
  for (const name of names) copyFileSync(join(web, name), join(app, 'public', name));
  copyFileSync(join(source, 'portal-integration/shansi-server.mjs'), join(app, 'lib/shansi-server.mjs'));
  writeFileSync(join(app, 'server.mjs'), `import { createShansiServer } from './lib/shansi-server.mjs';
const server = createShansiServer(new URL('./public/', import.meta.url), { commit: ${JSON.stringify(commit)} });
server.once('error', error => { console.error(error); process.exitCode = 1; });
server.listen(8797, '127.0.0.1');
for (const signal of ['SIGTERM', 'SIGINT']) process.once(signal, () => server.close());
`);
  const files = Object.fromEntries(['server.mjs', 'lib/shansi-server.mjs', ...names.map(n => 'public/' + n)].map(name => [name, hash(readFileSync(join(app, name)))]));
  return { service: 'shansi', commit, engine: '4.7.2.stable', builtAt: new Date().toISOString(), files };
}

export async function verifyShansi(manifest, base, app) {
  const health = await fetch(base + '/healthz', { signal: AbortSignal.timeout(5000) });
  const body = await health.json();
  if (health.status !== 200 || !body.ok || body.service !== 'shansi' || body.commit !== manifest.commit) throw Error('山寺运行提交号不符');
  for (const [name, digest] of Object.entries(manifest.files)) {
    if (hash(readFileSync(join(app, name))) !== digest) throw Error('山寺磁盘哈希不符：' + name);
    if (!name.startsWith('public/')) continue;
    const response = await fetch(base + '/' + name.slice(7), { signal: AbortSignal.timeout(30000) });
    if (response.status !== 200 || hash(Buffer.from(await response.arrayBuffer())) !== digest) throw Error('山寺 HTTP 哈希不符：' + name);
  }
}

async function main() {
  const { values } = parseArgs({ options: { godot: { type: 'string', default: process.env.GODOT || 'godot' }, output: { type: 'string' }, commit: { type: 'string', default: 'HEAD' } } });
  if (!values.output) throw Error('必须用 --output 指定新的发布包目录');
  const commit = execFileSync('git', ['rev-parse', '--verify', values.commit + '^{commit}'], { cwd: repo, encoding: 'utf8' }).trim();
  const version = execFileSync(values.godot, ['--version'], { encoding: 'utf8' }).trim();
  if (!version.startsWith('4.7.2.stable.')) throw Error('需要 Godot 4.7.2 stable 和同版本 Web 导出模板');
  const output = resolve(values.output);
  mkdirSync(output); // 已有目录拒绝覆盖。
  const source = mkdtempSync(join(tmpdir(), 'shansi-build-'));
  try {
    archiveSource(repo, commit, source);
    const project = join(source, '原型/山寺'), web = join(source, 'web'); mkdirSync(web);
    const run = (args, marker) => {
      const result = spawnSync(values.godot, ['--headless', '--path', project, ...args], { encoding: 'utf8', timeout: 180000, maxBuffer: 16 * 1024 * 1024 });
      process.stdout.write(result.stdout || ''); process.stderr.write(result.stderr || ''); checkGodotResult(result, marker);
    };
    importShansi(project, run);
    run(['--script', 'res://tests/run_tests.gd'], '失败 0 项');
    run(['--', 'auto', 'quit'], '自动试玩结算');
    run(['--export-release', 'Web', join(web, 'index.html')]);
    const manifest = stageShansi(web, join(output, 'app'), commit, source);
    writeFileSync(join(output, 'runtime-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    console.log('山寺构建成功：' + commit + '\n发布包：' + output);
  } finally { rmSync(source, { recursive: true, force: true }); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => { console.error(error.message); process.exitCode = 1; });
