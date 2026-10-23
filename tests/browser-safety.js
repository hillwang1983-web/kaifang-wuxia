async (page, base) => {
  const context=await page.context().browser().newContext({viewport:{width:844,height:390}});
  const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
  try {
    await p.goto(base + '?debug');await p.locator('#bStart').click();
    const results=await p.evaluate(()=>{
      const d=window.__duko,results=[];
      const reset=()=>{Object.assign(d.G,d.newGame());d.G.started=true;};
      const check=(name,fn)=>{reset();try{fn();results.push({name,pass:true});}catch(e){results.push({name,pass:false,error:e.message});}};
      const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
      function storageFailure(fn){const set=Storage.prototype.setItem;try{Storage.prototype.setItem=()=>{throw Error('quota');};fn();}finally{Storage.prototype.setItem=set;}}
      check('存档失败时包扎不半完成',()=>{d.G.f.accepted=true;d.G.p.hp=30;d.openDlg('shen');storageFailure(()=>d.doAct('heal'));assert(d.G.p.hp===30,'保存失败却恢复了生命');});
      check('存档失败时不显示交换条件已接受',()=>{d.openDlg('boss');storageFailure(()=>d.doAct('ask'));assert(!d.G.f.asked,'失败仍解锁药草');assert(d.G.dlg.opts.some(o=>o.key==='ask'),'失败却进入交换成功后的对话');});
      check('存档失败时不显示拿药成功和出售材料',()=>{d.G.f.asked=true;d.G.inv.herb=2;d.openDlg('boss');storageFailure(()=>d.doAct('trade'));assert(!d.G.inv.med,'失败发药');assert(!d.G.dlg.opts.some(o=>o.key==='buy_boss'),'失败却显示交易完成的出售选项');});
      check('普通输入不能调用当前对话没有的动作',()=>{d.openDlg('shen');d.doAct('fight');assert(!d.G.enemies[2].hostile,'沈青对话可以触发远方匪首战');});
      check('箭被木桶阻挡，人物不掉血',()=>{d.G.p.x=570;d.G.p.y=958;d.G.arrows=[{x:510,y:958,vx:310,vy:0,t:2}];d.updateChapter(.2);assert(d.G.chapter.arrowsBlocked===1,'箭没有被木桶拦下');assert(d.G.p.hp===100,'隔着木桶掉血');});
      check('同伴提供真实攻击',()=>{const e=JSON.parse(JSON.stringify(d.G.enemies[0]));Object.assign(e,{id:'test-final',kind:'guard',x:1950,y:850,hp:90,final:true});d.G.enemies.push(e);d.G.chapter.decision='public';d.G.chapter.finalStarted=true;d.G.ally={id:'xu',x:1800,y:850,cd:0,face:0};d.G.p.x=1800;d.G.p.y=850;d.updateChapter(.016);assert(e.hp===82,'同伴没造成 8 点伤害');assert(d.G.chapter.allyHits===1,'支援未计数');});
      check('切磋结算失败保留可重试状态',()=>{const e=d.G.enemies[2];Object.assign(e,{hp:0,hostile:true,spar:true});storageFailure(()=>d.kill(e));assert(d.G.f.sparWins===0,'失败计胜');assert(d.G.enemies[2].hostile&&d.G.enemies[2].spar,'保存失败却先结束了切磋');assert(!d.G.toasts.some(t=>t.text.includes('切磋赢了')),'失败仍提示拿到胜利材料');});
      check('未找到证人时结尾不虚构证词与支援',()=>{d.G.f.delivered=true;d.G.chapter.clues=['cart','ledger'];d.G.chapter.decision='public';d.G.chapter.finalStarted=d.G.chapter.finalResolved=true;d.openDlg('shen');assert(!d.G.dlg.text.includes('许舟愿意出面'),'没有证词也虚构许舟出面');assert(!d.G.dlg.text.includes('残单与证词'),'把账册虚构成证词');});
      check('通关后仍可进入承诺的切磋',()=>{d.G.f.branch='B';d.G.f.delivered=true;d.G.chapter.decision='mediate';d.G.chapter.finalStarted=d.G.chapter.finalResolved=true;d.openDlg('boss');assert(d.G.dlg.opts.some(o=>o.key==='spar'),'通关后切磋入口消失');});
      check('截流剑基础形态能打断，破势增强控制时间',()=>{const e=d.G.enemies[0];Object.assign(e,{x:1260,y:750,state:'windup',t:.2,atk:{inter:true}});Object.assign(d.G.p,{x:1200,y:750,face:0});d.skill(1);d.step(.01,20);assert(d.G.enemies[0].state==='stagger','未打断');assert(d.G.stats.interrupts===1,'未计打断');});
      check('横扫多目标只回一次气',()=>{d.G.chapter.skills[1]='sweep';d.G.orn='回气';Object.assign(d.G.p,{x:1200,y:750,face:0});d.G.enemies.slice(0,2).forEach((e,i)=>Object.assign(e,{x:1260,y:750+i*35}));d.skill(1);d.step(.01,50);assert(d.G.p.mp>=82&&d.G.p.mp<84,'多目标重复回气或没返还');assert(d.G.stats.qiBack===18,'返还量不正确');});
      check('突进不能穿过房屋',()=>{Object.assign(d.G.p,{x:570,y:270,face:0});d.G.chapter.skills[0]='thrust';d.skill(0);assert(d.G.p.x<=584.01,'突进穿墙：'+d.G.p.x);});
      check('对话开启清除未释放移动输入',()=>{const zone=document.getElementById('stickzone');zone.dispatchEvent(new PointerEvent('pointerdown',{pointerId:20,clientX:100,clientY:250,bubbles:true}));zone.dispatchEvent(new PointerEvent('pointermove',{pointerId:20,clientX:145,clientY:250,bubbles:true}));d.openDlg('shen');d.doAct('close');const x=d.G.p.x;d.step(.05,4);assert(Math.abs(d.G.p.x-x)<.01,'关闭对话后残留摇杆导致自己走动');});
      return results;
    });
    return {results,errors,pass:results.every(r=>r.pass)&&errors.length===0};
  }finally{await context.close();}
}
