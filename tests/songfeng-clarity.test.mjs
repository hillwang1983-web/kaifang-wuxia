import test from 'node:test';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {once} from 'node:events';
import {writeFileSync,mkdirSync} from 'node:fs';
import {createQingshiServer} from '../portal-integration/server.mjs';
const server=createQingshiServer(new URL('../原型/V0.4/',import.meta.url));server.listen(0,'127.0.0.1');await once(server,'listening');const base=`http://127.0.0.1:${server.address().port}/qingshi-v04/`;
const browser=await chromium.launch({headless:true}),out=new URL('../test-results/songfeng-clarity/',import.meta.url);mkdirSync(out,{recursive:true});
test.after(async()=>{await browser.close();await new Promise(r=>server.close(r));});

for(const dpr of [1,2,3])test(`DPR ${dpr} 场景缓冲与屏幕像素一致，不经过低分辨率整帧放大`,async t=>{
 const context=await browser.newContext({viewport:{width:844,height:390},deviceScaleFactor:dpr,isMobile:true,hasTouch:true});t.after(()=>context.close());const page=await context.newPage();await page.goto(base+'?debug');await page.locator('#bStart').tap();
 const result=await page.evaluate(()=>({dpr:devicePixelRatio,canvas:[cv.width,cv.height],scene:[__duko.BUF.width,__duko.BUF.height],view:[innerWidth,innerHeight]}));writeFileSync(new URL(`DPR${dpr}.json`,out),JSON.stringify(result,null,2));
 assert.deepEqual(result.canvas,[844*dpr,390*dpr]);assert.deepEqual(result.scene,result.canvas);
});

test('场景贴图保留高分辨率，显示尺寸与原碰撞布局分开',async t=>{
 const context=await browser.newContext();t.after(()=>context.close());const page=await context.newPage();await page.goto(base);
 const result=await page.evaluate(async()=>{const {createWorldArt}=await import('./world-art.mjs');const p=await createWorldArt().props(new URL('./assets/songfeng/world-atlas.png',location.href).href,new Proxy({house:[64,48]},{get:(o,k)=>o[k]||[32,32]}));return {pixels:[p.house.width,p.house.height],logical:[p.house.logicalWidth,p.house.logicalHeight]};});
 assert.deepEqual(result.logical,[64,48]);assert.ok(result.pixels[0]>=192&&result.pixels[1]>=144);
});

test('闪避只画一个人物，不叠加整身残像或半透明闪烁',async t=>{
 const context=await browser.newContext();t.after(()=>context.close());const page=await context.newPage();await page.goto(base+'?debug');await page.locator('#bStart').click();
 const result=await page.evaluate(async()=>{
  const {createChapterCombatRenderer}=await import('./combat-render.mjs'),d=__duko,g=structuredClone(d.G);g.enemies=[];g.swings=[];g.qi=[];g.p.inv=0;g.p.trail=[];g.fx=[];
  const painter=createChapterCombatRenderer(),paint=()=>{const calls=[];const c=new Proxy({globalAlpha:1},{get(o,k){return k in o?o[k]:(...args)=>{calls.push([k,...args]);};},set(o,k,v){o[k]=v;return true;}});painter.prepare(g,false,0);painter.hero(c,g,3);return calls.filter(c=>c[0]==='fillRect').length;};
  const single=paint();g.p.trail=[{x:g.p.x-30,y:g.p.y,t:.2},{x:g.p.x-60,y:g.p.y,t:.1}];const withOldTrail=paint();d.dodge();d.step(.01,8);return {single,withOldTrail,generated:d.G.p.trail.length};
 });
 assert.equal(result.withOldTrail,result.single);assert.equal(result.generated,0);
});

test('移动镜头按物理像素推进，小步移动不再卡在粗像素上',async t=>{
 const context=await browser.newContext({viewport:{width:844,height:390},deviceScaleFactor:3});t.after(()=>context.close());const page=await context.newPage();await page.goto(base+'?debug');await page.locator('#bStart').click();
 const positions=await page.evaluate(()=>{
  const d=__duko,positions=[],original=CanvasRenderingContext2D.prototype.translate;
  CanvasRenderingContext2D.prototype.translate=function(x,y){if(this.canvas===d.BUF&&x<0&&y<0)positions.push(x);return original.call(this,x,y);};
  try{d.G.p.y=870;for(let i=0;i<10;i++){d.G.p.x=1000+i*.3;d.draw(5);}}finally{CanvasRenderingContext2D.prototype.translate=original;}
  return positions;
 });
 assert.ok(new Set(positions).size>=5,JSON.stringify(positions));
});
