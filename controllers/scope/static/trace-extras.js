'use strict';
let referenceCapture=null,historyFrames=[],dragCursor=-1;
function note(message){$('status').textContent=message}
function recordHistory(records){
 const mode=appearance.persistenceMode;
 if(mode==='off')return;
 const now=Date.now();
 historyFrames.push({records,at:now});
 const maxAge=mode==='last20'?Infinity:Number(mode)*1000;
 historyFrames=historyFrames.filter(item=>now-item.at<=maxAge).slice(-20);
}
function currentView(records){
 if(!scopeState||!records||!records.length)return null;
 let secDiv=Number(scopeState.timebase),base=Math.min(...records.map(r=>r.rows[0][0])),zoom=appearance.zoomEnabled?Number(appearance.viewXZoom):1;
 let full=10*secDiv,width=full/zoom;
 return {start:base+(full-width)*(appearance.zoomEnabled?Number(appearance.viewXPan)/100:0),end:base+(full-width)*(appearance.zoomEnabled?Number(appearance.viewXPan)/100:0)+width};
}
function drawGhost(ctx,records,alpha,dashed){
 const view=currentView(lastRecords||records),g=viewport;
 if(!view)return;
 ctx.save();ctx.beginPath();ctx.rect(g.x,g.y,g.w,g.h);ctx.clip();
 ctx.globalAlpha=alpha;ctx.lineWidth=dashed?2:1;
 ctx.setLineDash(dashed?[6,5]:[]);
 for(const rec of records){
  if(!appearance[rec.channel==='CH2'?'showCH2':'showCH1'])continue;
  const key=rec.channel.toLowerCase(),scale=Number(scopeState[key+'_scale']),pos=Number(scopeState[key+'_position']),offset=Number(scopeState[key+'_offset']);
  if(!(scale>0))continue;
  ctx.strokeStyle=dashed?appearance.referenceColor:channelColor(rec.channel);
  const min=new Float64Array(g.w).fill(Infinity),max=new Float64Array(g.w).fill(-Infinity);
  for(const [t,v] of rec.rows){
   let x=Math.floor((t-view.start)/(view.end-view.start)*g.w);
   if(x<0||x>=g.w)continue;
   let div=((v-offset)/scale+pos)*(appearance.zoomEnabled?Number(appearance.viewYZoom):1)+(appearance.zoomEnabled?Number(appearance.viewYPan):0);
   min[x]=Math.min(min[x],div);max[x]=Math.max(max[x],div);
  }
  ctx.beginPath();let prev=-2;
  for(let x=0;x<g.w;x++){
   if(min[x]===Infinity)continue;
   let y=g.y+g.h/2-(min[x]+max[x])/2*g.h/8;
   if(x-prev>1)ctx.moveTo(g.x+x,y);else ctx.lineTo(g.x+x,y);
   if(!dashed&&min[x]!==max[x]){
    ctx.moveTo(g.x+x,g.y+g.h/2-min[x]*g.h/8);
    ctx.lineTo(g.x+x,g.y+g.h/2-max[x]*g.h/8);
    ctx.moveTo(g.x+x,y);
   }
   prev=x;
  }
  ctx.stroke();
 }
 ctx.restore();
}
function cursorValues(){
 const view=currentView(lastRecords),key=appearance.cursorChannel.toLowerCase();
 if(!view||!scopeState)return null;
 const zoom=appearance.zoomEnabled?Number(appearance.viewYZoom):1;
 const pan=appearance.zoomEnabled?Number(appearance.viewYPan):0;
 const pos=Number(scopeState[key+'_position']),scale=Number(scopeState[key+'_scale']),offset=Number(scopeState[key+'_offset']);
 const read=(prefix)=>{
  let x=Number(appearance[prefix+'x']),y=Number(appearance[prefix+'y']);
  return {x,y,t:view.start+x*(view.end-view.start),v:((4-y*8-pan)/zoom-pos)*scale+offset};
 };
 return [read('cursor1'),read('cursor2')];
}
function drawCursors(ctx){
 const g=viewport,positions=cursorValues(),readout=$('cursorReadout');
 readout.hidden=!appearance.cursorsEnabled;
 if(!appearance.cursorsEnabled)return;
 if(!positions){readout.textContent='Read a waveform to use the cursors.';return}
 const colors=[appearance.cursorAColor,appearance.cursorBColor];
 ctx.save();ctx.beginPath();ctx.rect(g.x,g.y,g.w,g.h);ctx.clip();
 for(let i=0;i<2;i++){
  let p=positions[i],x=g.x+p.x*g.w,y=g.y+p.y*g.h;
  ctx.strokeStyle=colors[i];ctx.lineWidth=1.5;ctx.setLineDash(i===0?[]:[6,4]);
  ctx.beginPath();ctx.moveTo(x,g.y);ctx.lineTo(x,g.y+g.h);ctx.moveTo(g.x,y);ctx.lineTo(g.x+g.w,y);ctx.stroke();
  ctx.setLineDash([]);ctx.fillStyle=colors[i];ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fill();
  canvasLabel(ctx,i===0?'A':'B',Math.min(x+7,g.x+g.w-19),Math.max(y-8,g.y+20),colors[i],16);
 }
 ctx.restore();
 const [a,b]=positions,dt=Math.abs(b.t-a.t),dv=Math.abs(b.v-a.v);
 readout.textContent='Cursor '+appearance.cursorChannel+'\n'+
  'A · '+displayNumber(a.t,'s')+' · '+displayNumber(a.v,'V')+'\n'+
  'B · '+displayNumber(b.t,'s')+' · '+displayNumber(b.v,'V')+'\n'+
  'Difference · Δt '+displayNumber(dt,'s')+' · ΔV '+displayNumber(dv,'V')+
  (dt>0?' · 1/Δt '+displayNumber(1/dt,'Hz'):'');
}
const drawWithoutExtras=draw;
draw=function(records,sequence){
 drawWithoutExtras(records,sequence);
 const ctx=$('trace').getContext('2d'),now=Date.now(),mode=appearance.persistenceMode;
 if(mode!=='off'){
  const maxAge=mode==='last20'?Infinity:Number(mode)*1000;
  historyFrames=historyFrames.filter(item=>now-item.at<=maxAge).slice(-20);
  for(let i=0;i<historyFrames.length-1;i++){
   const item=historyFrames[i],age=now-item.at;
   let fade=mode==='last20'?(i+1)/historyFrames.length:Math.max(0,1-age/maxAge);
   drawGhost(ctx,item.records,.08+.18*fade,false);
  }
 }
 if(appearance.showReference&&referenceCapture)drawGhost(ctx,referenceCapture.records,Number(appearance.referenceOpacity)/100,true);
 drawCursors(ctx);
 if($('freezeEnabled').checked)canvasLabel(ctx,'FROZEN',665,22,foreground(),16);
};
function pointerCoords(event){
 const canvas=$('trace'),rect=canvas.getBoundingClientRect();
 const scale=Math.min(rect.width/canvas.width,rect.height/canvas.height);
 const x=(event.clientX-rect.left-(rect.width-canvas.width*scale)/2)/scale;
 const y=(event.clientY-rect.top-(rect.height-canvas.height*scale)/2)/scale;
 return {x:(x-viewport.x)/viewport.w,y:(y-viewport.y)/viewport.h};
}
const clamp01=x=>Math.max(0,Math.min(1,x));
function moveCursor(event){
 if(dragCursor<0)return;
 const point=pointerCoords(event),key='cursor'+(dragCursor+1);
 appearance[key+'x']=clamp01(point.x).toFixed(4);
 appearance[key+'y']=clamp01(point.y).toFixed(4);
 if(lastRecords&&scopeState)draw(lastRecords,traceUpdates);
}
$('trace').addEventListener('pointerdown',event=>{
 if(!appearance.cursorsEnabled||!lastRecords)return;
 const p=pointerCoords(event);
 if(p.x<0||p.x>1||p.y<0||p.y>1)return;
 const score=i=>{
  let dx=p.x-Number(appearance['cursor'+i+'x']),dy=p.y-Number(appearance['cursor'+i+'y']);
  return dx*dx+dy*dy;
 };
 dragCursor=score(1)<=score(2)?0:1;
 $('trace').setPointerCapture(event.pointerId);
 moveCursor(event);event.preventDefault();
});
$('trace').addEventListener('pointermove',moveCursor);
function finishCursor(event){
 if(dragCursor<0)return;
 dragCursor=-1;
 try{localStorage.setItem('scopeTraceAppearance.v1',JSON.stringify(appearance))}catch(e){}
 if($('trace').hasPointerCapture(event.pointerId))$('trace').releasePointerCapture(event.pointerId);
}
$('trace').addEventListener('pointerup',finishCursor);
$('trace').addEventListener('pointercancel',finishCursor);
$('captureReference').onclick=()=>{
 if(!lastRecords||!scopeState){note('Read a waveform before capturing a reference.');return}
 referenceCapture={records:lastRecords,scopeTimebase:scopeState.timebase,at:new Date().toLocaleTimeString()};
 appearance.showReference=true;syncAppearance();syncExtras();
 note('Reference captured at '+referenceCapture.at+'. Dashed traces are the saved record.');
};
$('clearReference').onclick=()=>{referenceCapture=null;if(lastRecords)draw(lastRecords,traceUpdates);note('Reference cleared.')};
$('clearPersistence').onclick=()=>{historyFrames=[];if(lastRecords)draw(lastRecords,traceUpdates);note('Persistence history cleared.')};
$('freezeEnabled').addEventListener('change',()=>{
 $('settings').disabled=$('freezeEnabled').checked;
 if(lastRecords)draw(lastRecords,traceUpdates);
 note($('freezeEnabled').checked?'Waveform frozen; uncheck Freeze waveform to resume.':'Waveform resumed.');
});
async function fullscreenToggle(){
 const enabled=$('fullscreenEnabled');
 try{
  if(enabled.checked){
   if(!$('trace').requestFullscreen)throw Error('Fullscreen unavailable in this browser');
   await $('trace').requestFullscreen();
  }else if(document.fullscreenElement)await document.exitFullscreen();
 }catch(e){enabled.checked=false;$('errors').textContent='Fullscreen: '+e.message}
}
$('fullscreenEnabled').addEventListener('change',fullscreenToggle);
document.addEventListener('fullscreenchange',()=>{$('fullscreenEnabled').checked=document.fullscreenElement===$('trace')});
function presets(){
 try{const value=JSON.parse(localStorage.getItem('scopeTracePresets.v1')||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{}}catch(e){return {}}
}
const builtins={
 'Bench':{},
 'High contrast':{background:'#f5f6f7',gridColor:'#738590',centerColor:'#536770',
  colorCH1:'#cc1d2d',colorCH2:'#155fcb',showMajor:true,showMinor:false,centerHorizontalTicks:true,centerVerticalTicks:true},
 'Minimal':{showMajor:false,showMinor:false,showTicks:false,showMeasurements:false,showHeader:false,showFooter:false,
  showChannelMarkers:false,showTriggerTime:false,showTriggerLevel:false,centerHorizontal:false,centerVertical:false,
  centerHorizontalTicks:false,centerVerticalTicks:false}
};
function refreshPresetList(selectValue){
 const el=$('presetSelect'),selected=selectValue||el.value;el.replaceChildren();
 for(const name of Object.keys(builtins)){
  const option=document.createElement('option');option.value='builtin:'+name;option.textContent=name+' (built in)';el.appendChild(option)
 }
 for(const name of Object.keys(presets()).sort()){
  const option=document.createElement('option');option.value='saved:'+name;option.textContent=name;el.appendChild(option)
 }
 if([...el.options].some(option=>option.value===selected))el.value=selected;
}
$('savePreset').onclick=()=>{
 const name=$('presetName').value.trim().slice(0,30);
 if(!/^[\w][\w .-]{0,29}$/.test(name)){$('errors').textContent='Preset name: use letters, numbers, spaces, dots, hyphens, or underscores.';return}
 const all=presets();
 if(!Object.hasOwn(all,name)&&Object.keys(all).length>=8){$('errors').textContent='You can save up to eight presets. Delete one first.';return}
 all[name]={...appearance};
 try{localStorage.setItem('scopeTracePresets.v1',JSON.stringify(all))}
 catch(e){$('errors').textContent='Preset could not be saved in this browser.';return}
 refreshPresetList('saved:'+name);note('Saved display preset: '+name);$('errors').textContent='';
};
$('loadPreset').onclick=()=>{
 const value=$('presetSelect').value,[source,name]=value.split(':',2);
 const chosen=source==='builtin'?builtins[name]:presets()[name];
 if(!chosen){$('errors').textContent='That preset is unavailable.';return}
 appearance={...appearanceDefaults,...chosen};
 try{localStorage.setItem('scopeTraceAppearance.v1',JSON.stringify(appearance))}catch(e){}
 syncAppearance();syncExtras();note('Loaded display preset: '+name);
};
$('deletePreset').onclick=()=>{
 const value=$('presetSelect').value;
 if(!value.startsWith('saved:')){$('errors').textContent='Built-in presets cannot be deleted.';return}
 const name=value.slice(6),all=presets();delete all[name];
 try{localStorage.setItem('scopeTracePresets.v1',JSON.stringify(all))}catch(e){}
 refreshPresetList('builtin:Bench');note('Deleted preset: '+name);$('errors').textContent='';
};
function syncExtras(){
 $('trace').classList.toggle('cursor-active',appearance.cursorsEnabled);
 $('cursorReadout').hidden=!appearance.cursorsEnabled;
 $('presetTools').hidden=!appearance.showPresetTools;
 for(const id of ['viewXZoom','viewXPan','viewYZoom','viewYPan'])$(id).disabled=!appearance.zoomEnabled;
 if(lastRecords&&scopeState)draw(lastRecords,traceUpdates);
}
$('appearancePanel').addEventListener('input',event=>{
 if(event.target.id==='fullscreenEnabled'||event.target.id==='freezeEnabled')return;
 syncExtras();
});
$('resetAppearance').addEventListener('click',()=>{historyFrames=[];syncExtras()});
refreshPresetList('builtin:Bench');
syncExtras();
