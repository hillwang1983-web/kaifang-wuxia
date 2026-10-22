async (page, base) => {
  const context=await page.context().browser().newContext();const p=await context.newPage();
  const errors=[];p.on('pageerror',e=>errors.push(e.message));
  try {
    await p.goto(base + '?debug');await p.locator('#bStart').click();
    const before=await p.evaluate(()=>{
      const d=window.__duko;const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
      // 建立章节检查点 fixture；不把该测试当作自然剧情通关证据。
      d.commit('fixture','恢复测试起点',s=>{s.f.branch='B';s.f.delivered=true;s.chapter.decision='leave';return {ok:true};});
      d.G.p.x=d.locations.FINAL_POS.x;d.G.p.y=d.locations.FINAL_POS.y;d.interact();
      const count=d.G.enemies.length,set=Storage.prototype.setItem;
      try{Storage.prototype.setItem=()=>{throw Error('quota');};d.doAct('final_start');}finally{Storage.prototype.setItem=set;}
      assert(!d.G.chapter.finalStarted&&d.G.enemies.length===count,'写盘失败仍生成了最终遭遇');
      d.doAct('final_start');assert(d.G.chapter.finalStarted,'无法重试开启最终战');
      const e=d.G.enemies.find(e=>e.final),id=e.id;
      for(let i=0;i<30&&d.G.enemies.find(x=>x.id===id).hostile;i++){const foe=d.G.enemies.find(x=>x.id===id);Object.assign(d.G.p,{x:foe.x-50,y:foe.y,face:0,atkCd:0});d.attack();}
      assert(!d.G.enemies.find(x=>x.id===id).hostile,'无法击退一名拦路人');
      const total=d.G.enemies.length;d.hurtPlayer(1000,d.G.p.x-15,d.G.p.y);d.step(.05,45);
      assert(d.G.p.hp>0&&d.G.f.defeats===1,'败退未恢复');
      assert(d.G.chapter.finalStarted&&!d.G.chapter.finalResolved,'败退重置了章节');
      assert(!d.G.enemies.find(x=>x.id===id).hostile,'已击退的人在败退时重生');
      assert(d.G.enemies.length===total,'败退重复生成敌人');
      return {deadId:id,total,decision:d.G.chapter.decision,coin:d.G.inv.coin,defeats:d.G.f.defeats};
    });
    await p.reload();await p.locator('#bStart').click();
    const after=await p.evaluate(before=>{
      const d=window.__duko;const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
      assert(d.G.chapter.decision===before.decision&&d.G.chapter.finalStarted,'刷新丢失抉择或最终战');
      assert(d.G.enemies.length===before.total,'刷新重复刷怪');
      assert(!d.G.enemies.find(e=>e.id===before.deadId).alive,'刷新复活已击退的最终敌人');
      assert(d.G.inv.coin===before.coin,'刷新重复发钱');
      return {finalFoes:d.G.enemies.filter(e=>e.final&&e.hostile).length,defeats:d.G.f.defeats,hp:d.G.p.hp};
    },before);
    if(errors.length)throw Error(errors.join('\n'));
    return {failedStartRolledBack:true,checkpointReload:true,defeatedFoeStayedDefeated:true,...after,errors};
  }finally{await context.close();}
}
