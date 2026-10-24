// 使用真实导出包、独立内存账号库与看板源码的 Web 验收；不打开生产账号库。
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { randomBytes, scryptSync } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { resolve, join } from 'node:path';
import { parseArgs } from 'node:util';
const { values } = parseArgs({ options: { release: { type:'string' }, gateway: { type:'string' }, output: { type:'string' } } });
if (!values.release || !values.gateway || !values.output) throw Error('需要 --release 发布包 --gateway 看板源码目录 --output 日志目录');
const release = resolve(values.release), gateway = resolve(values.gateway), output = resolve(values.output);
mkdirSync(output, {recursive:true});
const { SQLiteStore } = await import(pathToFileURL(join(gateway,'src/sqlite.mjs')));
const { createPortalServer } = await import(pathToFileURL(join(gateway,'src/portal.mjs')));
const { portalGames } = await import(pathToFileURL(join(gateway,'src/portal-config.mjs')));
const { PUBLIC_ORIGIN } = await import(pathToFileURL(join(gateway,'src/gateway.mjs')));
const { createShansiServer } = await import(pathToFileURL(release + '/app/lib/shansi-server.mjs'));
const manifest = JSON.parse(readFileSync(release + '/runtime-manifest.json'));
const backend = createShansiServer(pathToFileURL(release + '/app/public/'), manifest);
const DB = SQLiteStore.memory();
const salt = randomBytes(16).toString('hex'), password = 'Synthetic browser password';
const hash = scryptSync(password, Buffer.from(salt, 'hex'), 32, { N:32768, r:8, p:3, maxmem:64*1024*1024 }).toString('hex');
DB.sql.prepare('INSERT INTO accounts(id,username,password_salt,password_hash) VALUES(?,?,?,?)').run('71988402-1bf9-43e7-a6fc-5ef23d6930ab', 'browser-tester', salt, hash);
backend.listen(0,'127.0.0.1'); await once(backend,'listening');
const portal = createPortalServer({DB, games:portalGames({SHANSI_ORIGIN:'http://127.0.0.1:'+backend.address().port,QINGSHI_ORIGIN:'http://127.0.0.1:8793'})});
let base;
portal.prependListener('request',req=>{
 if(req.headers.origin!==base)return;
 req.headers.origin=PUBLIC_ORIGIN;
 for(let i=0;i<req.rawHeaders.length;i+=2)if(req.rawHeaders[i].toLowerCase()==='origin')req.rawHeaders[i+1]=PUBLIC_ORIGIN;
});
portal.listen(0,'127.0.0.1'); await once(portal,'listening');base='http://127.0.0.1:'+portal.address().port;
const browser=await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1280,height:720}});
const logs=[],errors=[],responses=[]; let loginLogs=[];
page.on('console',message=>{logs.push({type:message.type(),text:message.text()});console.log(message.type()+': '+message.text());});
page.on('pageerror',e=>errors.push(e.message));
page.on('response',r=>{if(r.url().includes('/shansi/'))responses.push({url:r.url().split('?')[0],status:r.status(),type:r.headers()['content-type']});});
try{
 await page.goto(base+'/login?game=shansi');
 await page.getByLabel('用户名').fill('browser-tester');await page.getByLabel('密码',{exact:true}).fill(password);
 await page.getByRole('button',{name:'登 录',exact:true}).click();
 await page.waitForURL(base+'/?game=shansi');
 assert.equal(await page.getByRole('button',{name:'进入山寺',exact:true}).count(),1);
 assert.equal(await page.getByRole('button',{name:'踏入青石渡',exact:true}).count(),1);
 await page.screenshot({path:join(output,'board-local.png'),fullPage:true});
 loginLogs=logs.splice(0); console.log('LOGIN CONSOLE',JSON.stringify(loginLogs));
 await page.getByRole('button',{name:'进入山寺',exact:true}).click();
 await page.waitForURL(base+'/shansi/');
 await page.waitForFunction(()=>!document.querySelector('#status'),{},{timeout:90000});
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 await page.screenshot({path:join(output,'shansi-title.png')});
 assert.deepEqual(errors,[]);
 assert.equal(logs.filter(x=>x.type==='error').length,0);
 assert.ok(responses.some(x=>x.url.endsWith('/index.wasm')&&x.status===200&&x.type==='application/wasm'));
 assert.ok(responses.some(x=>x.url.endsWith('/index.pck')&&x.status===200));
 console.log('BROWSER START PASS');
 await page.goto(base+'/shansi/?auto');
 await page.waitForFunction(()=>!document.querySelector('#status'),{},{timeout:90000});
 // 三段完整流程约需 200 游戏秒，给浏览器软渲染留出余量，仍保留有界超时。
 const until=Date.now()+600000;
 while(!logs.some(x=>x.text.includes('自动试玩结算'))){
  if(Date.now()>until)throw Error('Web 自动通关未到结算（等待上限 600 秒）');
  await new Promise(r=>setTimeout(r,1000));
 }
 assert.deepEqual(errors,[]);assert.equal(logs.filter(x=>x.type==='error').length,0);
 await page.screenshot({path:join(output,'shansi-settlement.png')});
 console.log('BROWSER SETTLEMENT PASS');
}finally{
 writeFileSync(join(output,'browser-evidence.json'),JSON.stringify({commit:manifest.commit,loginLogs,logs,errors,responses},null,2));
 await browser.close();await new Promise(r=>portal.close(r));DB.close();await new Promise(r=>backend.close(r));
}
