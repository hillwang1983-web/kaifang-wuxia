async (page, base)=>{
  const context=await page.context().browser().newContext({viewport:{width:1100,height:760},acceptDownloads:true});const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
  const walk=async(key,ms)=>{await p.keyboard.down(key);await p.waitForTimeout(ms);await p.keyboard.up(key);};
  try{
    await p.goto(base);
    if(await p.evaluate(()=>typeof window.__duko)!=='undefined')throw Error('正常入口意外暴露调试接口');
    await p.locator('#bStart').click();
    await p.locator('#bLog').click();await p.locator('#testForm summary').click();
    await p.locator('[data-profile="operator"]').selectOption('自动化输入检查');
    await p.locator('[data-profile="source"]').selectOption('社区');
    await p.locator('[data-profile="device"]').fill('Chromium 桌面自动化输入检查；非真实手机');await p.locator('[data-profile="device"]').press('Tab');
    await p.locator('[data-profile="difficulty"]').fill('检查正常走图和周砚交互，不作为首次真人理解样本');await p.locator('[data-profile="difficulty"]').press('Tab');
    await p.locator('#logx').click();
    // 全程仅使用键盘和鼠标；不定位角色、不改资源、不跳过冷却。
    await walk('d',1450);await walk('s',800);await walk('d',280);
    await p.getByRole('button',{name:/拾取 · 木料堆/}).click();
    await walk('a',250);
    await p.getByRole('button',{name:'点击与周砚交谈',exact:true}).click();
    if(await p.locator('#dWho').textContent()!=='周砚')throw Error('人物标记没打开周砚对话');
    await p.getByRole('button',{name:/做一件「破势」/}).click();await p.getByRole('button',{name:'告辞',exact:true}).click();
    await walk('s',500);await walk('a',1330);
    await p.locator('#bSk2.hot').waitFor({state:'visible',timeout:7000});await p.keyboard.press('i');await p.waitForTimeout(130);await p.keyboard.press('j');
    await walk('d',1330);await walk('w',500);
    await p.getByRole('button',{name:'点击与周砚交谈',exact:true}).click();
    await p.getByRole('button',{name:'买一份料（10 铜钱）',exact:true}).click();
    await p.getByRole('button',{name:/做一件「回气」/}).click();await p.getByRole('button',{name:'告辞',exact:true}).click();
    await walk('s',500);await walk('a',1330);await walk('w',70);await p.keyboard.press('i');await p.waitForTimeout(200);
    await p.locator('#bLog').click();
    if(!(await p.locator('#rec').textContent()).includes('自动化输入检查'))throw Error('记录来源不正确');
    const downloadEvent=p.waitForEvent('download');await p.locator('#bExport').click();const download=await downloadEvent;
    // 下载保留在隔离浏览器的临时目录，关闭上下文后自动清理。
    if(errors.length)throw Error(errors.join('\n'));
    return {normalUrl:true,noDebugApi:true,keyboardMovement:true,clickCharacter:true,crafted:['破势','回气'],practiceOnly:true,operator:'自动化输入检查',downloadPath:await download.path(),record:await p.locator('#rec').textContent(),errors};
  }finally{await context.close();}
}
