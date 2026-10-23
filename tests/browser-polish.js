async (page, base)=>{
  const context=await page.context().browser().newContext({viewport:{width:1100,height:760}});const p=await context.newPage();
  try{
    await p.goto(base + '?debug');await p.locator('#bStart').click();
    const results=await p.evaluate(()=>{
      const d=window.__duko,result=[];
      function check(name,fn){if(d.recordPayload){d.G.logOpen=true;d.recordPayload();}Object.assign(d.G,d.newGame());d.G.started=true;try{fn();result.push({name,pass:true});}catch(e){result.push({name,pass:false,error:e.message});}}
      const assert=(v,m)=>{if(!v)throw Error(m);};
      check('可见交谈标记提示点击人物并包含键盘入口',()=>{Object.assign(d.G.p,d.locations.NPCS[3]);d.step(.01);assert(!document.getElementById('nearTalk')?.hidden&&!!document.getElementById('nearTalk'),'没有人物交谈标记');assert(document.getElementById('interactT').textContent.includes('E'),'底部没有 E 提示');});
      check('再次与周砚交谈可以再次购买，独立动作不误判重复',()=>{d.G.inv.coin=100;d.openDlg('zhou');d.doAct('buy_zhou');d.doAct('close');d.openDlg('zhou');d.doAct('buy_zhou');assert(d.G.f.zhouBuys===2,'第二次购买被当作重复提交');assert(d.G.inv.coin===80,'重复动作账目不正确');});
      check('破势打断后下一次普攻有一次追击伤害',()=>{const e=d.G.enemies[0];Object.assign(e,{hp:200,x:1260,y:750,state:'windup',t:.2,atk:{inter:true}});Object.assign(d.G.p,{x:1200,y:750,face:0});d.G.orn='破势';d.skill(1);d.step(.01,20);const before=d.G.enemies[0].hp;d.G.p.atkCd=0;d.attack();d.step(.01,20);assert(before-d.G.enemies[0].hp===28,'普攻缺少 +8 追击');assert(d.G.playtest.combat.counters===1,'追击未计入记录');});
      check('战斗回内力与脱战不同',()=>{const e=d.G.enemies[0];Object.assign(e,{x:1260,y:750,state:'recover',t:0,atk:{rec:10}});Object.assign(d.G.p,{x:1200,y:750,mp:40});d.step(.05);assert(Math.abs(d.G.p.mp-40.075)<.001,'战斗仍以每秒6点自然恢复');});
      check('调试页面的导出不得宣称正常真人试玩',()=>{assert(d.G.playtest?.debugUsed===true,'未标记调试来源');assert(d.recordText().includes('调试'),'摘要没有调试来源');});
      check('突进进入木桩范围的首招也计入分段',()=>{d.G.orn='回气';Object.assign(d.G.p,{x:488,y:750,face:Math.PI});d.G.chapter.skills[0]='thrust';d.skill(0);d.step(.01,40);d.G.logOpen=true;const r=d.recordPayload();const b=r.record.battles.at(-1);assert(b?.casts===1&&b?.hits===1&&b.qiReturned===18,'首招或返还漏计');assert(b.mpBefore===100&&b.mpAfter>=94&&b.mpAfter<95,'分段初始内力不是施放前值');});
      check('页面离开时保存当前战斗分段',()=>{d.G.orn='回气';Object.assign(d.G.p,{x:388,y:750,face:Math.PI});d.skill(1);window.dispatchEvent(new Event('pagehide'));const s=d.loadSave();assert(s.G.playtest.battles.at(-1)?.casts===1,'离开页面丢失当前分段');});
      check('复制摘要包含会话和资源差额',()=>{const text=d.recordText();assert(text.includes('会话：')&&text.includes('事务差额'),'复制摘要无法核对会话或账目');});
      check('实际游戏采样入口保留前台长帧',()=>{const old=d.perfStats();d.perfRec(1500);const next=d.perfStats();assert(next.max>=1500&&next.over200===(old?.over200||0)+1,'游戏入口仍过滤前台长帧');});
      check('文档可见性事件能排除后台与恢复跨界帧',()=>{const old=d.perfStats()?.frames||0;try{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));d.perfRec(9000);Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'));d.perfRec(4000);d.perfRec(1200);assert(d.perfStats().frames===old+1,'后台或恢复间隔被计入前台');}finally{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));}});
      return result;
    });
    return {results,pass:results.every(r=>r.pass)};
  }finally{await context.close();}
}
