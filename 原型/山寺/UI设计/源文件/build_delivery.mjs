import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const root=path.dirname(fileURLToPath(import.meta.url));
const src=path.join(root,'source');
const out=process.argv[2]||path.join(root,'delivery');
const ui=path.join(out,'UI设计'), assets=path.join(out,'assets');
for(const d of [ui,path.join(ui,'切图'),path.join(ui,'预览2倍'),path.join(assets,'ui'),path.join(assets,'ico'),path.join(assets,'por'),path.join(assets,'vfx')])fs.mkdirSync(d,{recursive:true});
const font=path.join(src,'font.ttf');
const G='#FFD24A', W='#FFF3C4', B='#15121A', M='#AAA59C', P='#9B4DFF';
const magick=(...a)=>execFileSync('magick',a.map(String),{maxBuffer:8e6});
const files=[];
function register(p,w,h,role){files.push({path:path.relative(out,p).split(path.sep).join('/'),width:w,height:h,role});return p;}
class Board{
 constructor(w,h,bg='none'){this.w=w;this.h=h;this.a=bg.endsWith?.('.png')?[bg]:['-size',`${w}x${h}`,`xc:${bg}`];this.a.push('+antialias','-font',font);}
 shape(s,f,stroke='none',width=1){this.a.push('-fill',f,'-stroke',stroke,'-strokewidth',width,'-draw',s);return this;}
 rect(x,y,w,h,f,stroke='none'){return this.shape(`rectangle ${x},${y} ${x+w-1},${y+h-1}`,f,stroke);}
 panel(x,y,w,h,border=G,fill='rgba(21,18,26,0.87)'){return this.shape(`polygon ${x+3},${y} ${x+w-4},${y} ${x+w-1},${y+3} ${x+w-1},${y+h-4} ${x+w-4},${y+h-1} ${x+3},${y+h-1} ${x},${y+h-4} ${x},${y+3}`,fill,border);}
 txt(x,y,s,size=12,color=W,anchor='start'){const width=[...s].reduce((n,c)=>n+(c.codePointAt(0)>255?size:size/2),0);x=Math.round(x-(anchor==='middle'?width/2:anchor==='end'?width:0));this.a.push('-gravity','None','-fill',color,'-stroke','none','-pointsize',size,'-draw',`text ${x},${y} '${s}'`);return this;}
 img(p,x,y){this.a.push(p,'-gravity','NorthWest','-geometry',`+${x}+${y}`,'-compose','Over','-composite');return this;}
 circle(x,y,r,fill,stroke='none',sw=1){return this.shape(`circle ${x},${y} ${x+r},${y}`,fill,stroke,sw);}
 bar(x,y,w,h,ratio,color){this.rect(x,y,w,h,'#242028','#6C5B3B');return this.rect(x+1,y+1,Math.max(1,Math.round((w-2)*ratio)),h-2,color);}
 save(p,role='UI切图'){magick(...this.a,'-strip',`PNG32:${p}`);return register(p,this.w,this.h,role);}
}
const tex=(name,w,h,paint,dir='ui')=>{const b=new Board(w,h);paint(b);return b.save(path.join(assets,dir,`${name}_v01.png`));};
const effect=(name,b)=>{const p=b.save(path.join(ui,`${name}_v01.png`),'界面效果图');magick(p,'-filter','point','-resize','200%',path.join(ui,'预览2倍',`${name}_v01_2x.png`));return p;};
const blank=()=>new Board(960,540,B);
const background=()=>new Board(960,540,path.join(src,'background_youth.png'));
const menuBackground=()=>new Board(960,540,path.join(src,'background_empty.png')).rect(0,0,960,540,'rgba(21,18,26,0.4)');
const crop=(file,box,size,name,colors=17)=>{const [x,y,w,h]=box;const p=path.join(assets,name);magick(path.join(src,file),'-crop',`${w}x${h}+${x}+${y}`,'+repage','-channel','A','-threshold','80%','+channel','-trim','+repage','-filter','point','-resize',`${size-4}x${size-4}`,'+dither','-colors',colors,'-channel','A','-threshold','50%','+channel','-gravity','center','-background','none','-extent',`${size}x${size}`,'-strip',`PNG32:${p}`);register(p,size,size,'透明图标/头像');return p;};

// 九技能套图逐个提取；切图没有文字、冷却数字或状态遮罩。
const skillNames=['luohanquan','jinzhongzhao','dalijingangzhang','dushazhang','huagongsan','shehunshu','tiyunzong','yungong','jiemai'];
const boxes=[[79,70,334,331],[461,70,333,332],[842,71,333,332],[79,444,334,333],[460,444,334,333],[842,445,334,333],[78,820,335,335],[459,820,334,336],[840,820,337,337]];
const icons={};
skillNames.forEach((n,i)=>icons[n]=crop('icons_grid.png',boxes[i],64,`ico/ico_skill_${n}_v01.png`,8));
['attack','dodge','talk'].forEach((n,i)=>icons[n]=crop('buttons_strip.png',[[143,109,514,503],[832,109,505,503],[1517,109,508,503]][i],64,`ico/ico_btn_${n}_v01.png`,8));
icons.heji=crop('combo_icon.png',[0,0,64,64],64,'ico/ico_skill_heji_v01.png',8);
const portraits={};
for(const [who,expressions] of [['jingxin',['normal','sad']],['xuancheng',['cold','smile']]]){
 expressions.forEach((e,i)=>portraits[`${who}_${e}`]=crop(`${who}_strip.png`,[i*887,0,887,887],96,`por/por_${who}_${e}_v01.png`,17));
}
const menuArt=[];
for(const [i,box] of [[0,[49,43,687,939]],[1,[707,59,749,923]]]){
 const [x,y,w,h]=box,p=path.join(src,`faction_${i}.png`);
 const mask=path.join(src,`faction_mask_${i}.png`),clean=path.join(src,`faction_clean_${i}.png`);
 magick(path.join(src,'factions_strip.png'),'-alpha','extract','-threshold','80%','-define','connected-components:area-threshold=5000','-define',`connected-components:keep=${i+1}`,'-define','connected-components:mean-color=true','-connected-components','8',mask);
 magick(path.join(src,'factions_strip.png'),mask,'-compose','CopyOpacity','-composite',clean);
 magick(clean,'-crop',`${w}x${h}+${x}+${y}`,'+repage','-channel','A','-threshold','80%','+channel','-trim','+repage','-filter','point','-resize','176x224','+dither','-colors','17','-channel','A','-threshold','50%','+channel','-background','none','-gravity','center','-extent','192x224',`PNG32:${p}`);
 const exported=path.join(assets,'ui',`ui_faction_${i?'xiepai':'shaolin'}_v01.png`);fs.copyFileSync(p,exported);register(exported,192,224,'门派选择插图');menuArt.push(exported);
}
const playerPreview=path.join(src,'player_preview_48x64.png');
magick(path.join(src,'faction_0.png'),'-trim','+repage','-filter','point','-resize','39x52','+dither','-colors','17','-channel','A','-threshold','50%','+channel','-gravity','center','-background','none','-extent','48x64',playerPreview);
magick(path.join(src,'background_empty.png'),'-fill','rgba(28,34,51,0.30)','-draw','ellipse 487,330 12,3 0,360',playerPreview,'-geometry','+456+275','-composite',path.join(src,'background_youth.png'));

// 所有框体为空框；血量、名字、倒计时、文字、填充与遮罩由程序单独绘制。
tex('ui_bossbar',448,88,b=>{b.panel(0,0,448,88);b.bar(16,31,416,11,0,'#242028');b.bar(16,67,416,6,0,'#242028');});
tex('ui_selfbar',224,108,b=>{b.panel(0,0,224,108);[33,55,77].forEach(y=>b.bar(56,y,152,11,0,'#242028'));});
tex('ui_partybar',196,88,b=>{b.panel(0,0,196,88);b.bar(12,32,172,9,0,'#242028');b.bar(12,49,172,5,0,'#242028');});
for(let lv=1;lv<=3;lv++)tex(`ui_moqi_lv${lv}`,48,12,b=>{for(let i=0;i<3;i++)b.circle(6+i*14,6,2,i<lv?G:'#48423C');});
for(const [n,c] of [['health','#D9534F'],['qi',G],['dex','#C8C8C8'],['cast','#FFC83D']])tex(`ui_fill_${n}`,1,1,b=>b.rect(0,0,1,1,c));
tex('ui_heji_invite',248,52,b=>b.panel(0,0,248,52));
tex('ui_dialog',928,132,b=>b.panel(0,0,928,132).rect(16,16,96,96,'rgba(21,18,26,0.6)','#8E7846'));
tex('ui_taskbar',184,80,b=>b.panel(0,0,184,80));
tex('ui_pause',320,352,b=>b.panel(0,0,320,352));
tex('ui_tooltip',280,64,b=>b.panel(0,0,280,64));
for(const [name,fill,border] of [['normal','rgba(21,18,26,0.88)',G],['pressed','rgba(216,166,74,0.4)',W],['disabled','rgba(21,18,26,0.75)','#665F53']]){
 tex(`ui_button_${name}`,220,44,b=>b.panel(0,0,220,44,border,fill));
 tex(name==='normal'?'ui_btn_base':`ui_btn_${name}`,64,64,b=>b.circle(32,32,30,fill,border));
}
tex('ui_skill_disabled',64,64,b=>b.circle(32,32,30,'rgba(21,18,26,0.72)'));
tex('ui_skill_cooldown',64,64,b=>b.shape('path "M32,32 L32,1 A31,31 0 1,1 8,52 Z"','rgba(21,18,26,0.75)'));
tex('ui_stick_base',128,128,b=>b.circle(64,64,62,'rgba(21,18,26,0.65)',G).circle(64,64,42,'none','#6C5B3B'));
tex('ui_stick_knob',56,56,b=>b.circle(28,28,26,'rgba(216,166,74,0.5)',G));
tex('ui_stick_knob_pressed',56,56,b=>b.circle(28,28,26,'rgba(216,166,74,0.75)',W));
tex('ui_charge',96,96,b=>b.circle(48,48,44,'none','#6C5B3B',2));
tex('ui_charge_progress',96,96,b=>b.shape('path "M48,4 A44,44 0 1,1 4,48"','none',G,3));
tex('ui_aim_arrow',128,128,b=>b.shape('polygon 64,4 92,42 74,42 74,112 54,112 54,42 36,42','rgba(255,210,74,0.35)',G));
tex('ui_aim_spot',96,64,b=>b.shape('ellipse 48,32 44,24 0,360','rgba(255,210,74,0.12)',G).shape('line 40,32 56,32 line 48,24 48,40','none',G));
tex('ui_heji_countdown',48,48,b=>b.shape('path "M24,2 A22,22 0 1,1 2,24"','none','#FFC83D',2));
tex('ui_heji_ground',96,96,b=>b.shape('ellipse 48,54 44,26 0,360','rgba(255,210,74,0.15)',G).shape('ellipse 48,54 34,18 0,360','none',W));

function button(b,x,y,label,selected=false,disabled=false,w=220){b.panel(x,y,w,44,disabled?'#665F53':selected?W:G,selected?'rgba(216,166,74,0.32)':'rgba(21,18,26,0.88)').txt(x+w/2,y+30,label,24,disabled?'#665F53':W,'middle');}
function icon(b,name,x,y,size=64){let p=icons[name];if(size!==64){const q=path.join(src,`scaled_${name}_${size}.png`);if(!fs.existsSync(q))magick(p,'-filter','point','-resize',`${size}x${size}!`,q);p=q;}b.img(p,x,y);}
function bars(b,mobile=false){
 const [sx,sy,sw,sh]=mobile?[24,16,184,76]:[16,416,224,108];b.panel(sx,sy,sw,sh).txt(sx+12,sy+20,'你 · 少林',12,G);
 const hp=[['生命',.82,'#D9534F'],['内力',.7,G],['身法',.8,'#C8C8C8']];
 hp.forEach((s,i)=>{const y=sy+(mobile?29:33)+i*(mobile?14:22);b.txt(sx+12,y+10,s[0]);b.bar(sx+56,y,sw-72,mobile?9:11,s[1],s[2]);if(!mobile)b.txt(sx+132,y+10,['820 / 1000','140 / 200','80 / 100'][i],12,B,'middle');});
 const py=mobile?100:16,pw=mobile?184:196,ph=mobile?76:88;b.panel(mobile?24:16,py,pw,ph).txt(mobile?36:28,py+21,'净心',12,G);
 b.bar(mobile?36:28,py+31,pw-24,9,.8,'#D9534F');
 if(!mobile){b.txt(200,py+21,'480 / 600',12,W,'end').bar(28,py+49,172,5,.65,G).txt(28,py+77,'默契',12,M).img(path.join(assets,'ui','ui_moqi_lv2_v01.png'),81,py+65).txt(192,py+77,'二级',12,G,'end');}
 else b.bar(36,py+47,160,5,.65,G).txt(36,py+67,'默契',12,M).img(path.join(assets,'ui','ui_moqi_lv2_v01.png'),84,py+55).txt(196,py+67,'二级',12,G,'end');
 const bx=mobile?240:256,bw=mobile?464:448;b.panel(bx,16,bw,88).txt(bx+16,37,'玄诚 · 叛僧教头').txt(bx+bw-16,37,'1520 / 2400',12,W,'end').bar(bx+16,47,bw-32,11,.633,'#D9534F').txt(bx+16,74,'重击蓄力',12,'#FFC83D').txt(bx+bw-16,74,'1.2 / 2.0 秒',12,'#FFC83D','end').bar(bx+16,83,bw-32,6,.6,'#FFC83D');
 const qx=mobile?752:760;b.panel(qx,112,184,80).txt(qx+14,133,'当前目标',12,G).txt(qx+14,157,'◆ 打断玄诚重击').txt(qx+14,181,'◆ 与净心完成合击');
 b.panel(356,360,248,52).img(path.join(assets,'ui','ui_heji_countdown_v01.png'),360,362).txt(410,381,'合击邀请',12,G).txt(410,401,mobile?'轻触响应 · 2.4 秒':'C 响应 · 2.4 秒');
 if(mobile)b.panel(892,16,44,44).txt(914,43,'Ⅱ',12,W,'middle');else b.panel(904,16,40,28).txt(924,35,'ESC',12,W,'middle');
}
const skillKeys=['attack','luohanquan','jinzhongzhao','dalijingangzhang','jiemai','heji','dodge'];
const skillLabels=['普攻','罗汉拳','金钟罩','大力金刚掌','截脉','合击','闪避'];
function hud(mode='pc'){
 const b=background();bars(b,mode==='mobile');
 if(mode==='mobile'){
  b.img(path.join(assets,'ui','ui_stick_base_v01.png'),62,336).img(path.join(assets,'ui','ui_stick_knob_v01.png'),98,372);
  const poses=[[824,458,80],[704,354,64],[784,354,64],[864,354,64],[744,458,64],[664,458,64],[904,458,64]];
  poses.forEach(([x,y,s],i)=>{icon(b,skillKeys[i],x-s/2,y-s/2,s);b.rect(x-32,y+s/2+2,64,17,'rgba(21,18,26,0.7)').txt(x,y+s/2+16,skillLabels[i],12,W,'middle');});
  b.img(path.join(assets,'ui','ui_skill_cooldown_v01.png'),752,322).txt(784,364,'5',24,W,'middle');
 }else{
  const keys=mode==='xbox'?['X','Y','RB','RT','LB','LT','A']:mode==='ps'?['□','△','R1','R2','L1','L2','×']:['鼠左','Q','E','R','F','C','Space'];
  [326,418,510,602,694,786,878].forEach((x,i)=>{b.rect(x-20,422,40,16,'rgba(21,18,26,0.92)',i===4?G:'#8E7846').txt(x,435,keys[i],12,W,'middle');icon(b,skillKeys[i],x-32,446);b.rect(x-42,513,84,19,'rgba(21,18,26,0.85)').txt(x,527,skillLabels[i],12,W,'middle');});
  b.img(path.join(assets,'ui','ui_skill_cooldown_v01.png'),478,446).txt(510,487,'5',24,W,'middle');
  b.panel(768,16,124,28).txt(830,35,mode==='pc'?'键鼠 / 手柄':mode==='xbox'?'手柄 · Xbox':'手柄 · PS',12,G,'middle');
 }
 return b;
}

const start=menuBackground();start.panel(48,40,336,456).txt(216,140,'山寺归僧',36,G,'middle').txt(216,176,'慈云寺 · 山门风波',12,W,'middle');button(start,106,234,'开始游戏',true);button(start,106,294,'继续游戏',false,true);start.txt(216,390,'声音：开启',12,W,'middle').txt(216,452,'确认：Enter / A / ×',12,M,'middle');effect('01_开始界面',start);
const faction=menuBackground().txt(480,72,'选择门派',24,G,'middle');
for(let i=0;i<2;i++){const x=i?512:96;faction.panel(x,112,352,336,i?G:W).txt(x+176,151,i?'邪派':'少林',24,i?P:G,'middle').img(menuArt[i],x+80,166).txt(x+176,416,i?'刀 · 中距施毒，控场牵制':'棍 · 近身强攻，蓄力护体',12,W,'middle');}button(faction,370,466,'确认门派',true);effect('02_门派选择',faction);
const choose=menuBackground().txt(480,72,'择一通用技，进入山门',24,G,'middle').txt(480,100,'仅可携带一项，确认后进入副本。',12,W,'middle');
[['tiyunzong','梯云纵','短距闪现，避开锋芒。'],['yungong','运功疗伤','自身疗伤，也可向同伴渡气。'],['jiemai','截脉','打断读条，夺回出手时机。']].forEach((s,i)=>{const x=96+i*268;choose.panel(x,132,232,304,i===2?W:G);icon(choose,s[0],x+52,160,128);choose.txt(x+116,332,s[1],24,G,'middle').txt(x+116,375,s[2],12,W,'middle');});button(choose,370,466,'确认 · 截脉',true);effect('03_通用技选择',choose);
effect('04_战斗HUD',hud());effect('04_战斗HUD_手机',hud('mobile'));effect('04_战斗HUD_Xbox',hud('xbox'));effect('04_战斗HUD_PS',hud('ps'));
const safe=hud('mobile');safe.shape('line 24,0 24,540 line 936,0 936,540','none','#4FA3FF').panel(250,116,460,82).txt(480,142,'横屏安全区与触控范围',24,G,'middle').txt(480,171,'左右至少预留 24px；按真实设备安全区再增加。',12,W,'middle');effect('04_战斗HUD_手机安全区',safe);
const pause=hud().rect(0,0,960,540,'rgba(21,18,26,0.55)').panel(320,94,320,352).txt(480,140,'暂停',24,G,'middle');button(pause,370,184,'继续游戏',true);button(pause,370,248,'声音：开启');button(pause,370,312,'返回开始');pause.txt(480,416,'Esc / B / ○ 返回',12,M,'middle');effect('05_任务与暂停',pause);
for(const [who,face,name,line] of [['jingxin','normal','净心','施主，山门就在前面。先熄灭火把，再寻机会近前。'],['xuancheng','cold','玄诚','回去。你们还没学会怎样接住这一棍。']]){
 const b=background().img(path.join(assets,'ui','ui_dialog_v01.png'),16,392).img(portraits[`${who}_${face}`],32,408).txt(152,422,name,24,G).txt(152,460,line,12,W).txt(920,507,'Enter / A / × 继续',12,M,'end');effect(`06_对话_${name}`,b);
}
const mechanisms=blank().txt(480,44,'释放机制与瞄准指示',24,G,'middle');
['点按','按住蓄力','拖动瞄准'].forEach((s,i)=>mechanisms.panel(24+i*312,80,288,420).txt(168+i*312,120,s,24,G,'middle'));
icon(mechanisms,'luohanquan',136,166);mechanisms.txt(168,302,'按下即释放',12,W,'middle').txt(168,330,'不额外显示地面指示器',12,M,'middle');
mechanisms.img(path.join(assets,'ui','ui_charge_v01.png'),432,160).img(path.join(assets,'ui','ui_charge_progress_v01.png'),432,160).txt(480,302,'蓄力环随时间推进',12,W,'middle').txt(480,330,'松开释放；可取消',12,M,'middle');
mechanisms.img(path.join(assets,'ui','ui_aim_arrow_v01.png'),728,146).img(path.join(assets,'ui','ui_aim_spot_v01.png'),744,318).txt(792,420,'方向箭头 / 目标落点',12,W,'middle');effect('07_释放机制',mechanisms);
const states=blank().txt(480,48,'按键、冷却与不可用状态',24,G,'middle');
['正常','按下','冷却','不可用'].forEach((s,i)=>{const x=126+i*236;icon(states,'jinzhongzhao',x-32,134);if(i===1)states.img(path.join(assets,'ui','ui_btn_pressed_v01.png'),x-32,134);if(i===2)states.img(path.join(assets,'ui','ui_skill_cooldown_v01.png'),x-32,134).txt(x,176,'5',24,W,'middle');if(i===3)states.img(path.join(assets,'ui','ui_skill_disabled_v01.png'),x-32,134);states.txt(x,240,s,24,i===3?M:G,'middle');});
states.txt(40,322,'默契一 / 二 / 三级',24,G);[1,2,3].forEach((lv,i)=>states.img(path.join(assets,'ui',`ui_moqi_lv${lv}_v01.png`),80+i*286,366).txt(104+i*286,420,`${['一','二','三'][i]}级`,12,W,'middle'));
effect('08_按钮与默契状态',states);
const fxPalette=path.join(src,'fx_palette.png');magick('-size','1x1',`xc:${B}`,'-size','1x1',`xc:${G}`,'-size','1x1',`xc:${W}`,'+append',fxPalette);
const freeze=path.join(assets,'vfx','vfx_heji_freeze_v01.png');magick(path.join(src,'combo_freeze.png'),'-filter','point','-resize','960x540!','+dither','-remap',fxPalette,'-strip',freeze);register(freeze,960,540,'合击成立静态定格，最长0.5秒');effect('09_合击成立定格',new Board(960,540,freeze));
const atlas=blank().txt(480,40,'第一里程碑 · 图标交付',24,G,'middle');
const atlasNames=[...skillNames,'heji','attack','dodge','talk'];atlasNames.forEach((n,i)=>{const col=i%7,row=Math.floor(i/7),x=48+col*132,y=92+row*186;icon(atlas,n,x,y);atlas.txt(x+32,y+92,[...['罗汉拳','金钟罩','大力金刚掌','毒砂掌','化功散','摄魂术','梯云纵','运功疗伤','截脉','合击','普攻','闪避','交谈']][i],12,W,'middle');});effect('10_图标总览',atlas);
// 提示气泡另作效果图，框体交给程序填字。
const tooltip=background().img(path.join(assets,'ui','ui_tooltip_v01.png'),340,210).txt(480,235,'交谈',12,G,'middle').txt(480,258,'E / A / × 靠近净心交谈',12,W,'middle');effect('11_任务提示气泡',tooltip);

// 同一资产在设计切图目录和游戏资产目录使用同一字节内容。
for(const f of files.filter(f=>f.path.startsWith('assets/'))){const dest=path.join(ui,'切图',path.basename(f.path));fs.copyFileSync(path.join(out,f.path),dest);}
for(const f of files){f.sha256=crypto.createHash('sha256').update(fs.readFileSync(path.join(out,f.path))).digest('hex');}
fs.writeFileSync(path.join(ui,'交付清单_v01.json'),JSON.stringify({date:'2026-10-24',style:'墨底金边',native:[960,540],font:'Fusion Pixel 12px',files},null,2));
fs.writeFileSync(path.join(ui,'布局参数_v01.json'),JSON.stringify({native:[960,540],colors:{panel:B,border:G,text:W,health:'#D9534F',cast:'#FFC83D'},fontSize:[12,24,36],panelOpacity:.87,border:1,desktop:{self:[16,416,224,108],party:[16,16,196,88],boss:[256,16,448,88],quest:[760,112,184,80],combo:[356,360,248,52],skillCenters:[326,418,510,602,694,786,878],skillY:478,iconSize:64},mobile:{safeInsetMinimum:24,joystick:[126,400,128,56],buttons:[[824,458,80],[704,354,64],[784,354,64],[864,354,64],[744,458,64],[664,458,64],[904,458,64]]},dialog:{rect:[16,392,928,132],portrait:[32,408,96,96],textOrigin:[152,422]},notes:['字体由程序渲染，空框不带人名/数值','冷却遮罩为样式示例，运行时按剩余比例顺时针绘制','键位为设计示意，以工程输入映射为准','手机先保持原生画面整数放大，多余空间留黑，安全区取实际设备与24px设计值的较大值','合击成立定格显示不超过0.5秒']},null,2));
console.log(JSON.stringify({output:out,files:files.length,effects:files.filter(f=>f.role==='界面效果图').length}));
