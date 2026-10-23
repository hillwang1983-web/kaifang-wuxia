async (page, base) => {
  const browser=page.context().browser();
  const results=[];
  for(const scenario of ['A-public','A-public-docs','B-peace','B-mediate-fight','leave','leave-no-clues']){
    const context=await browser.newContext({viewport:{width:1200,height:800}});
    const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
    try {
      await p.goto(base + '?debug');await p.locator('#bStart').click();
      const result=await p.evaluate(scenario=>{
        const d=window.__duko,C=window.QingShiChapter;
        const check=(ok,msg)=>{if(!ok)throw Error(scenario+': '+msg);};
        check(!!d?.G.chapter,'V0.4 章节尚未加载');
        function close(){if(d.G.dlg){const opts=d.G.dlg.opts;if(opts.some(o=>o.key==='close'))d.doAct('close');else if(opts.some(o=>o.key==='finish'))d.doAct('finish');}}
        function go(pos){close();d.G.p.x=pos.x;d.G.p.y=pos.y;d.interact();}
        const L=d.locations;
        go(L.NPCS[0]);d.doAct('accept');check(d.G.f.accepted,'接药任务');
        go(L.CRATE);check(d.G.inv.wood===2,'一次材料领取');
        go(L.NPCS[3]);d.doAct('craft_ps');close();check(d.G.orn==='破势','制作剑饰');
        if(!['A-public-docs','leave-no-clues'].includes(scenario)){go(L.NPCS[1]);d.doAct('clue_witness');check(d.G.chapter.clues.includes('witness'),'许舟证词');}
        // 实际查看物件，调用真实战斗/交涉，不直接写剧情旗标。
        if(!['B-mediate-fight','leave-no-clues'].includes(scenario)){go({x:939,y:540});d.doAct('clue_cart');check(d.G.chapter.clues.includes('cart'),'货车残单');}
        const boss=d.G.enemies[2];go(boss);
        if(scenario.startsWith('A-public')){
          d.doAct('fight');
          for(let n=0;n<40&&!d.G.f.branch;n++){const b=d.G.enemies[2];d.G.p.x=b.x-55;d.G.p.y=b.y;d.G.p.face=0;d.G.p.atkCd=0;d.attack();d.step(.01,50);}
          check(d.G.f.branch==='A','武力取药');
        }else{
          d.doAct('ask');close();for(const h of L.HERBS)go(h);
          go(d.G.enemies[2]);d.doAct('trade');check(d.G.f.branch==='B','交换取药');d.doAct('buy_boss');close();check(d.G.f.bought,'一次购买');
        }
        if(!['B-mediate-fight','leave-no-clues'].includes(scenario)){go(L.LEDGER_POS);d.doAct('clue_ledger');}
        const expected=scenario==='A-public-docs'?2:scenario==='B-mediate-fight'?1:scenario==='leave-no-clues'?0:3;check(d.G.chapter.clues.length===expected,'线索数量');
        go(L.NPCS[0]);d.doAct(scenario.startsWith('leave')?'give_quiet':'give_tell');d.doAct('finish');
        check(d.G.f.delivered&&!d.G.inv.med,'交药唯一、进入第二幕');
        const before=d.G.inv.coin;
        go(L.NPCS[0]);d.doAct('decide_'+(scenario.startsWith('A-public')?'public':scenario.startsWith('B-')?'mediate':'leave'));d.doAct('confirm_decision');
        check(!!d.G.chapter.decision,'决定已保存');
        if(scenario==='leave'){go(L.NPCS[2]);d.doAct('supply');check(d.G.chapter.supplied,'补给到账');}
        go(L.FINAL_POS);d.doAct(scenario==='B-peace'?'final_peace':'final_start');
        if(scenario!=='B-peace'){
          check(d.G.enemies.some(e=>e.final),'不同最终遭遇已生成');
          for(let n=0;n<150&&!d.G.chapter.finalResolved;n++){
            const e=d.G.enemies.find(e=>e.final&&e.hostile&&e.hp>0);if(!e)break;
            d.G.p.x=e.x-50;d.G.p.y=e.y;d.G.p.face=0;d.G.p.atkCd=0;d.attack();d.step(.01,50);d.updateChapter(0);
          }
        }
        check(d.G.chapter.finalResolved,'最终对峙可结算');check(d.G.inv.coin===before+25,'结局只加 25 铜钱');
        const persisted=d.loadSave();check(persisted.G.chapter.finalResolved,'最终状态已写盘');
        const coin=d.G.inv.coin;const duplicate=d.commit('chapter:result','重复结算',s=>C.act(s,'resolve','victory'));
        check(d.G.inv.coin===coin,'重试不会重复领奖');
        return {scenario,ending:d.G.chapter.ending,peace:d.G.chapter.peaceful,coin,clues:d.G.chapter.clues.length,branch:d.G.f.branch,duplicate:duplicate.dup||false};
      },scenario);
      await p.reload();
      const recovered=await p.evaluate(()=>({ending:window.__duko.G.chapter.ending,coin:window.__duko.G.inv.coin}));
      if(recovered.ending!==result.ending||recovered.coin!==result.coin)throw Error('刷新后结局或资源丢失');
      if(errors.length)throw Error(errors.join('\n'));results.push({...result,reload:true});
    } finally {await context.close();}
  }
  return results;
}
