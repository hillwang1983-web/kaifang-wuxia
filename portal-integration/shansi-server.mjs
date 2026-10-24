import http from 'node:http';
import { readdirSync, readFileSync } from 'node:fs';

// 导出包只允许顶层 Web 资源，不提供工程源码、目录列表或任意路径读取。
export const webAsset = /^index(?:\.(?:html|js|wasm|pck|png|audio\.worklet\.js|audio\.position\.worklet\.js)|\.icon\.png|\.apple-touch-icon\.png)$/;
const types = { html: 'text/html; charset=utf-8', js: 'text/javascript; charset=utf-8', wasm: 'application/wasm', pck: 'application/octet-stream', png: 'image/png' };

export function createShansiServer(root, release) {
  const routes = new Map(readdirSync(root).filter(name => webAsset.test(name)).map(name => {
    const body = readFileSync(new URL(name, root));
    return ['/' + name, { body, type: types[name.split('.').at(-1)] }];
  }));
  routes.set('/', routes.get('/index.html'));
  routes.set('/healthz', { body: Buffer.from(JSON.stringify({ ok: true, service: 'shansi', commit: release.commit })), type: 'application/json' });
  return http.createServer((req, res) => {
    const headers = { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' };
    if (!['GET', 'HEAD'].includes(req.method)) { req.resume(); res.writeHead(405, { ...headers, allow: 'GET, HEAD' }).end(); return; }
    const asset = routes.get(req.url.split('?')[0]);
    if (!asset) { res.writeHead(404, headers).end(); return; }
    res.writeHead(200, { ...headers, 'content-type': asset.type, 'content-length': asset.body.length });
    res.end(req.method === 'HEAD' ? undefined : asset.body);
  });
}
