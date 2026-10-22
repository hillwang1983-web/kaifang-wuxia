import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
import { createQingshiServer } from '../portal-integration/server.mjs';

const server = createQingshiServer(new URL('../原型/V0.4/', import.meta.url));
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const base = 'http://127.0.0.1:' + server.address().port + '/qingshi-v04/';
let browser;
try { browser = await chromium.launch({ headless: true }); }
catch (error) { server.close(); throw error; }
test.after(async () => { await browser.close(); await new Promise(resolve => server.close(resolve)); });

for (const name of ['acceptance', 'recovery', 'safety', 'polish', 'normal-input', 'controls']) {
  test('V0.4 browser: ' + name, async () => {
    const context = await browser.newContext();
    try {
      const page = await context.newPage();
      const source = readFileSync(new URL('./browser-' + name + '.js', import.meta.url), 'utf8');
      const run = new Function('return (' + source + ')')();
      const result = await run(page, base);
      const rows = Array.isArray(result) ? result : [result];
      for (const row of rows) {
        if ('pass' in row) assert.equal(row.pass, true, JSON.stringify(row));
        if (row.errors) assert.deepEqual(row.errors, []);
      }
    } finally { await context.close(); }
  });
}
