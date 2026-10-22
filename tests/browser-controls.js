async (page, base) => {
  const context=await page.context().browser().newContext({viewport:{width:844,height:390},isMobile:true,hasTouch:true,deviceScaleFactor:2});
  const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
  try {
    await p.goto(base + '?debug');await p.locator('#bStart').tap();
    const initial=await p.evaluate(()=>__duko.G.p.x),cdp=await context.newCDPSession(p);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:1,x:80,y:270}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:1,x:125,y:270}]});
    const r=await p.locator('#bAtk').boundingBox();
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:1,x:125,y:270},{id:2,x:r.x+r.width/2,y:r.y+r.height/2}]});
    await p.waitForTimeout(100);
    const during=await p.evaluate(()=>({x:__duko.G.p.x,attackCd:__duko.G.p.atkCd,viewport:[innerWidth,innerHeight]}));
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    const end=await p.evaluate(()=>__duko.G.p.x);await p.waitForTimeout(120);const stopped=await p.evaluate(()=>__duko.G.p.x);
    if(!(during.x>initial&&during.attackCd>0&&Math.abs(stopped-end)<1))throw Error(JSON.stringify({initial,during,end,stopped}));
    await p.locator('#bMap').tap();await p.locator('#tabSkills').tap();
    await p.evaluate(()=>document.querySelector('.atlas-card').scrollTop=0);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{id:3,x:450,y:325}]});
    for(let i=1;i<=8;i++){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:3,x:450,y:325-i*22}]});await p.waitForTimeout(20);}
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    if(await p.evaluate(()=>document.querySelector('.atlas-card').scrollTop)<20)throw Error('手机手记不能原生滑动，第三招不可浏览');
    await p.getByRole('button',{name:'装入 I 槽',exact:true}).last().tap();
    if(await p.evaluate(()=>__duko.G.chapter.skills[1])!=='sweep')throw Error('触控换招失败');
    await p.locator('#atlasClose').tap();
    const layout=await p.evaluate(()=>['bSk','bSk2','bDg','bAtk','bMap'].map(id=>{const e=document.getElementById(id),r=e.getBoundingClientRect();return {id,visible:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,minTouch:Math.min(r.width,r.height)};}));
    if(layout.some(r=>!r.visible||r.minTouch<44))throw Error('存在越界或过小的按键：'+JSON.stringify(layout));
    if(errors.length)throw Error(errors.join('\n'));
    return {simultaneousTouchMoveAttack:true,stopsOnRelease:true,nativeAtlasScroll:true,touchEquip:true,viewport:during.viewport,layout,errors};
  }finally{await context.close();}
}
