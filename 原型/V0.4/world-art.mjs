import { paintHero, sampleHeroPose, paintEnemy, sampleEnemyPose } from './songfeng-render.mjs';

export const WORLD_STYLE = 'songfeng-world-20261023';
const palette = {
  xia: { coat:'#285867', light:'#4a7d83', dark:'#163746', scarf:'#d4cfad' },
  shen: { coat:'#d9ddc1', light:'#f2ead0', dark:'#668e7f', scarf:'#589181' },
  xu: { coat:'#536f68', light:'#8ba191', dark:'#304e4b', scarf:'#c3ae77' },
  lu: { coat:'#79594e', light:'#ab8270', dark:'#4b4140', scarf:'#d1b987' },
  zhou: { coat:'#6f7465', light:'#a9ab8d', dark:'#454c43', scarf:'#ad8252' },
  boss: { coat:'#85604d', light:'#bd9364', dark:'#4a4237', scarf:'#d6b570' },
  bandit: { coat:'#964e3d', light:'#c47752', dark:'#593d32', scarf:'#bf7c48' },
};
const rect=(c,x,y,w,h,color)=>{c.fillStyle=color;c.fillRect(x,y,w,h);};
function poly(c,points,color){c.fillStyle=color;c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fill();}
function ellipse(c,x,y,rx,ry,color){c.fillStyle=color;c.beginPath();c.ellipse(x,y,rx,ry,0,0,Math.PI*2);c.fill();}
const seed=(x,y)=>{let n=(Math.imul(x+117,374761393)^Math.imul(y+91,668265263))>>>0;return()=>{n=(Math.imul(n,1664525)+1013904223)>>>0;return n/4294967296;};};
const canvas=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;};
const group=k=>['shore','plank'].includes(k)?'water':k;

export function createWorldArt(){
  const tiles=new Map();
  function tile(c,r,wf,kindAt){
    const k=kindAt(c,r),key=c+','+r+','+(group(k)==='water'?wf:0);if(tiles.has(key))return tiles.get(key);
    const image=canvas(16,16),g=image.getContext('2d'),rnd=seed(c,r);
    rect(g,0,0,16,16,'#819a5d');
    for(let i=0;i<16;i++)rect(g,rnd()*16,rnd()*16,1+rnd()*3,1+rnd()*2,['#758e53','#91a96a','#6f8d57'][i%3]);
    if(['dirt','camp','stone'].includes(k)){
      rect(g,0,0,16,16,k==='stone'?'#7e8f7f':k==='camp'?'#b3a079':'#c4aa76');
      if(k==='stone'){
        for(let y=0;y<16;y+=8)for(let x=-8;x<16;x+=12){const sx=x+((y/8+r)%2)*6;
          poly(g,[[sx+1,y+1],[sx+11,y],[sx+12,y+6],[sx+2,y+7]],rnd()>.5?'#a9b2a0':'#929e8d');
          rect(g,sx+2,y+1,8,1,'#bdc4ad');
        }
      }else for(let i=0;i<12;i++)rect(g,rnd()*16,rnd()*16,1+rnd()*2,1,i%3?'#b8a072':'#d0b784');
      for(const [dc,dr] of [[0,-1],[0,1],[-1,0],[1,0]])if(['grass','dark'].includes(kindAt(c+dc,r+dr))){
        for(let i=0;i<16;i++){const depth=1+Math.floor(rnd()*4),x=dc<0?0:dc>0?16-depth:i,y=dr<0?0:dr>0?16-depth:i;
          rect(g,x,y,dc?depth:1,dr?depth:1,i%3?'#819a5d':'#96aa67');}
      }
    }else if(group(k)==='water'){
      rect(g,0,0,16,16,'#477c7d');
      for(let i=0;i<5;i++){const x=(rnd()*18+wf*2)%16,y=rnd()*16;rect(g,x,y,2+rnd()*5,1,i%2?'#699b95':'#3c7275');}
      if(k==='shore'){rect(g,0,11,16,5,'#97a77e');for(let i=0;i<16;i++)rect(g,i,9+Math.floor(rnd()*3),1,2,'#b8bd8e');}
      if(k==='plank'){rect(g,0,0,16,16,'#745e43');for(let y=0;y<16;y+=4){rect(g,0,y,16,1,'#b09b69');rect(g,2,y+1,12,1,'#907b55');}}
    }else{
      if(rnd()<.22){const x=2+rnd()*10,y=3+rnd()*9;rect(g,x,y,1,3,'#537f53');rect(g,x-2,y+1,1,2,'#5f8753');rect(g,x+2,y+2,1,2,'#acc378');}
      if(k==='dark')rect(g,0,0,16,16,'#284f4288');
    }
    tiles.set(key,image);return image;
  }
  function npc(c,id,dir,x,y,time=0,frame='idle'){
    const face={down:Math.PI/2,up:-Math.PI/2,left:Math.PI,right:0}[dir]??Math.PI/2;
    if(id==='boss'||id==='bandit'){const e={x:0,y:0,face,type:'melee',mode:'idle',timer:0,hp:100,maxHp:100,stagger:0,flash:0};c.save();c.translate(x,y);const scale=(id==='boss'?1.7:1)/3;c.scale(scale,scale);paintEnemy(c,e,{...sampleEnemyPose(e),gait:frame==='idle'?0:Math.sin(time*12)});c.restore();return;}
    const pose=sampleHeroPose(face),colors=palette[id]||palette.xia;
    pose.lean=Math.sin(time*1.7+(id.charCodeAt(0)%7))*.7;pose.hand={x:15,y:-15};pose.angle=-.9;
    c.save();c.translate(x,y);c.scale(1/3,1/3);
    paintHero(c,{x:0,y:0,moving:frame!=='idle',walk:time,palette:colors,sword:false},pose);
    if(id==='xu'){
      poly(c,[[-20,-41],[0,-57],[21,-41],[14,-37],[-15,-37]],'#bda873');
      poly(c,[[-18,-41],[0,-53],[1,-41]],'#d5c38d');rect(c,-19,-41,39,3,'#7a7952');
      rect(c,-18,-20,2,25,'#84734d');
    }else if(id==='shen'){
      ellipse(c,-9,-8,6,5,'#697b51');rect(c,-12,-12,6,6,'#a2af77');rect(c,-10,-19,1,7,'#698649');
      rect(c,-10,-45,18,3,'#d6ddbf');
    }else if(id==='zhou'){
      poly(c,[[-7,-26],[7,-26],[10,-5],[-11,-5]],'#836847');rect(c,-6,-22,12,2,'#c0a278');
      rect(c,15,-21,3,16,'#a98653');rect(c,10,-26,14,7,'#566b65');rect(c,11,-26,11,2,'#a5b1a0');
      rect(c,-9,-45,18,4,'#956d46');
    }else if(id==='lu'){
      rect(c,10,-16,12,16,'#d1bf8c');rect(c,12,-15,2,14,'#8c7753');rect(c,16,-12,4,1,'#7a755a');
      rect(c,-8,-45,17,5,'#394f47');rect(c,-6,-49,12,5,'#394f47');
    }
    c.restore();
  }
  function portrait(c,id){
    c.width=76;c.height=76;const g=c.getContext('2d');g.imageSmoothingEnabled=false;
    rect(g,0,0,76,76,'#203e35');ellipse(g,38,38,35,35,'#405b45');ellipse(g,25,19,23,18,'#74846a40');
    g.save();g.translate(38,125);g.scale(id==='boss'?6/1.7:6,id==='boss'?6/1.7:6);npc(g,id,'down',0,0,0);g.restore();
    g.strokeStyle='#b6aa77';g.lineWidth=2;g.strokeRect(2,2,72,72);
  }
  async function props(url,sizes){
    const atlas=new Image();atlas.src=url;await atlas.decode();
    const order=['house','home','home2','forge','tree','tree2','bigtree','bamboo','rock','boulder','tent','tent2','boat','lantern','fence','reed','barrel','board','cart','sign','wood','herb','dummy','firepit'];
    // 生成图集的行距并非等分；逐件记录实际留白边界，避免裁断屋檐或树冠。
    const frames=[
      [0,0,275,290],[280,0,235,290],[520,0,225,290],[750,0,274,290],
      [0,298,270,284],[275,298,220,284],[495,298,315,284],[810,298,214,284],
      [0,585,220,217],[220,585,270,217],[495,585,250,217],[750,585,274,223],
      [0,808,285,198],[290,802,195,204],[490,808,250,198],[750,808,274,198],
      [0,1018,240,224],[245,1018,245,224],[495,1018,250,224],[750,1018,274,224],
      [0,1243,240,293],[245,1243,245,293],[495,1243,250,293],[750,1243,274,293],
    ],out={};
    order.forEach((name,i)=>{
      const [x,y,w0,h0]=frames[i],cell=canvas(w0,h0),g=cell.getContext('2d');g.drawImage(atlas,x,y,w0,h0,0,0,w0,h0);
      const d=g.getImageData(0,0,cell.width,cell.height).data;let left=cell.width,top=cell.height,right=0,bottom=0;
      for(let y=0;y<cell.height;y++)for(let x=0;x<cell.width;x++)if(d[(y*cell.width+x)*4+3]>32){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);}
      if(left>right)throw Error('场景素材缺失：'+name);
      const [w,h]=sizes[name]||({wood:[24,16],herb:[16,16],dummy:[20,26],firepit:[32,28],bamboo:[32,40]})[name];
      const result=canvas(w*4,h*4),p=result.getContext('2d'),scale=Math.min(result.width/(right-left+1),result.height/(bottom-top+1));
      result.logicalWidth=w;result.logicalHeight=h;p.imageSmoothingEnabled=true;p.imageSmoothingQuality='high';
      const dw=(right-left+1)*scale,dh=(bottom-top+1)*scale;p.drawImage(cell,left,top,right-left+1,bottom-top+1,(result.width-dw)/2,result.height-dh,dw,dh);out[name]=result;
    });
    out.rock2=out.rock;out.boulder2=out.boulder;out.stump=out.wood;out.bush=canvas(64,64);out.bush.logicalWidth=16;out.bush.logicalHeight=16;out.bush.getContext('2d').drawImage(out.tree2,0,0,64,64);out.dummyHit=out.dummy;
    return out;
  }
  return {tile,npc,portrait,props};
}
