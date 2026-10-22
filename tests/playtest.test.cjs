const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const target='../原型/V0.4/playtest.js';
const P=fs.existsSync(require('node:path').join(__dirname,target))?require(target):{};
test('试玩模块存在',()=>assert.equal(typeof P.createSampler,'function'));
test('前台1500毫秒长帧必须计入最大值与停顿次数',()=>{
  const p=P.createSampler();p.add(16,'combat');p.add(1500,'combat');const s=p.stats();
  assert.equal(s.frames,2);assert.equal(s.max,1500);assert.equal(s.over100,1);assert.equal(s.over200,1);assert.equal(s.durationMs,1516);
});
test('只排除已知后台与恢复跨界帧，之后的前台长帧仍计入',()=>{
  const p=P.createSampler();p.add(20,'move');p.visibility(true);p.add(5000,'move');p.visibility(false);p.add(4000,'move');p.add(1200,'combat');
  assert.equal(p.stats().frames,2);assert.equal(p.stats().max,1200);assert.equal(p.stats('move').frames,1);assert.equal(p.stats('combat').frames,1);
});
test('超过旧环形容量后样本量与超阈值次数仍属于同一会话',()=>{
  const p=P.createSampler();p.add(1200,'combat');for(let i=0;i<18050;i++)p.add(16.3,'combat');
  const s=p.stats('combat');assert.equal(s.frames,18051);assert.equal(s.over200,1);assert.equal(s.max,1200);assert.equal(s.p95,17);assert.equal(s.p95ResolutionMs,1);
});
test('没有样本的战斗段不伪装成总体性能',()=>{const p=P.createSampler();p.add(16,'menu');assert.equal(p.stats('combat'),null);assert.equal(p.stats().frames,1);});
test('新局、历史档与调试来源不混淆，调试污染不可逆',()=>{
  const s={time:0};P.ensure(s,{fresh:true,debug:false,now:'2026-10-22T13:00:00Z'});assert.equal(s.playtest.coverage,'fresh');assert.equal(s.playtest.debugUsed,false);
  P.ensure(s,{debug:true});P.ensure(s,{debug:false});assert.equal(s.playtest.debugUsed,true);
  const legacy={time:600};P.ensure(legacy,{fresh:false,debug:false});assert.equal(legacy.playtest.coverage,'legacy');assert.equal(legacy.playtest.events.length,0);
});
test('事务记录保存资源前后差额，失败动作不补造成功事件',()=>{
  const s={time:12};P.ensure(s,{fresh:true});P.transaction(s,'制作剑饰',{coin:30,wood:2,iron:1},{coin:25,wood:0,iron:0});
  const e=s.playtest.events[0];assert.equal(e.type,'transaction');assert.equal(e.activeSeconds,12);assert.deepEqual(e.data.delta,{coin:-5,wood:-2,iron:-1});assert.equal(e.data.label,'制作剑饰');
});
