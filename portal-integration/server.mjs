import http from 'node:http';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve, relative, join, sep, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

export function createQingshiServer(root) {
  const routes = new Map();
  for (const name of ['index.html', 'chapter.js', 'playtest.js', 'game.js']) {
    const asset = { body: readFileSync(new URL(name, root)), type: name.endsWith('.js')
      ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8' };
    routes.set('/qingshi-v04/' + name, asset);
    if (name === 'index.html') routes.set('/qingshi-v04/', asset);
  }
  // 素材图（Ninja Adventure，CC0）：启动时列出 assets/na 下的文件，只发布这份清单
  const TYPES = { '.png': 'image/png', '.md': 'text/markdown; charset=utf-8', '.txt': 'text/plain; charset=utf-8' };
  const rootDir = fileURLToPath(root);
  for (const entry of readdirSync(new URL('assets/na/', root), { recursive: true, withFileTypes: true })) {
    if (!entry.isFile()) continue;
    const name = relative(rootDir, join(entry.parentPath, entry.name)).split(sep).join('/'), type = TYPES[extname(name)];
    if (type) routes.set('/qingshi-v04/' + encodeURI(name), { body: readFileSync(new URL(name, root)), type });
  }
  const health = { body: Buffer.from(JSON.stringify({ ok: true, service: 'qingshi-v04', version: 'V0.4-20261023-na' })), type: 'application/json' };
  routes.set('/healthz', health); routes.set('/qingshi-v04/healthz', health);
  return http.createServer((req, res) => {
    const headers = { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' };
    if (!['GET', 'HEAD'].includes(req.method)) {
      req.resume(); res.writeHead(405, { ...headers, allow: 'GET, HEAD' }); res.end(); return;
    }
    const asset = routes.get(req.url.split('?')[0]);
    if (!asset) { res.writeHead(404, headers); res.end(); return; }
    res.writeHead(200, { ...headers, 'content-type': asset.type, 'content-length': asset.body.length });
    res.end(req.method === 'HEAD' ? undefined : asset.body);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createQingshiServer(new URL('../原型/V0.4/', import.meta.url));
  server.once('error', error => { console.error(error.message); process.exitCode = 1; });
  server.listen(8793, '127.0.0.1', () => console.log('Qingshi V0.4 listening on 127.0.0.1:8793.'));
  const stop = () => server.close();
  process.once('SIGTERM', stop); process.once('SIGINT', stop);
}
