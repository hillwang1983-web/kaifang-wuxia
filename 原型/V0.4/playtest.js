/* 本地试玩记录。没有网络传输；性能只统计本页会话的实际前台帧。 */
(function(root){
  'use strict';
  function createSampler(){
    const groups=new Map();let hidden=false,skipResume=false;
    const bucket=()=>({frames:0,durationMs:0,max:0,over100:0,over200:0,bins:new Map()});
    function add(ms,mode='idle'){
      if(hidden)return;
      if(skipResume){skipResume=false;return;}
      if(!Number.isFinite(ms)||ms<=0)return;
      for(const key of ['all',mode]){
        if(!groups.has(key))groups.set(key,bucket());const b=groups.get(key);
        b.frames++;b.durationMs+=ms;b.max=Math.max(b.max,ms);if(ms>100)b.over100++;if(ms>200)b.over200++;
        const bin=Math.ceil(ms);b.bins.set(bin,(b.bins.get(bin)||0)+1);
      }
    }
    function stats(mode='all'){
      const b=groups.get(mode);if(!b?.frames)return null;
      const rank=Math.ceil(b.frames*.95);let count=0,p95=0;
      for(const [bin,n]of [...b.bins].sort((a,b)=>a[0]-b[0])){count+=n;if(count>=rank){p95=bin;break;}}
      return {frames:b.frames,durationMs:b.durationMs,fps:1000*b.frames/b.durationMs,p95,p95ResolutionMs:1,max:b.max,over100:b.over100,over200:b.over200};
    }
    return {add,stats,visibility(value){if(hidden&&!value)skipResume=true;hidden=value;}};
  }
  function ensure(state,{debug=false,fresh=false,now=new Date().toISOString()}={}){
    if(!state.playtest)state.playtest={schema:1,coverage:fresh?'fresh':'legacy',debugUsed:!!debug,startedAt:now,baseline:{activeSeconds:state.time||0,inventory:{...state.inv}},profile:{operator:'未声明',source:'未填写',experience:'未填写',device:'',power:'未记录',difficulty:'',observation:'',nextTry:''},prompts:[],events:[],combat:{casts:0,hits:0,misses:0,noMp:0,interrupts:0,counters:0,qiReturned:0,windups:0,heavyWindups:0,dodges:0,evades:0},battles:[]};
    if(debug)state.playtest.debugUsed=true;
    return state.playtest;
  }
  function event(state,type,data={}){
    const r=ensure(state);r.events.push({seq:r.events.length+1,at:new Date().toISOString(),activeSeconds:Math.round((state.time||0)*100)/100,type,data});
  }
  function transaction(state,label,before,after){
    const delta={};for(const k of new Set([...Object.keys(before),...Object.keys(after)])){const d=Number(after[k]||0)-Number(before[k]||0);if(d)delta[k]=d;}
    event(state,'transaction',{label,before:{...before},after:{...after},delta});
  }
  const api={createSampler,ensure,event,transaction};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.QingShiPlaytest=api;
})(globalThis);
