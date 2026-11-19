'use strict';
const $=id=>document.getElementById(id);
const buttons=[
 ['DC V','function',{function:'dcv'},244,432,110,76,'dcv'],['AC V','function',{function:'acv'},398,432,110,76,'acv'],
 ['Ω 2W','function',{function:'ohm2'},552,432,110,76,'ohm2'],['Frequency','function',{function:'freq'},706,432,110,76,'freq'],
 ['Continuity','function',{function:'continuity'},860,432,110,76,'continuity'],['Null','math',{mode:'null'},1014,432,110,76],
 ['Min / Max','math',{mode:'minmax'},1168,432,110,76],['Range down','range',{direction:'down'},552,570,110,76],
 ['Range up','range',{direction:'up'},706,570,110,76],['Auto range','range',{direction:'auto'},860,570,110,76],
 ['Single','single',{},1014,570,110,76],['Shift / Local','shift',{},1168,570,110,76],
 ['Left / Fewer digits','web-fewer',{},244,570,110,76],['Right / More digits','web-more',{},398,570,110,76]
];
const secondary=[['DC I','dci'],['AC I','aci'],['Ω 4W','ohm4'],['Period','period'],['Diode','diode']];
const extras=[...secondary.map(([label,fn])=>[label,'function',{function:fn}]),['Math off','math',{mode:'off'}],
 ['dB','math',{mode:'db'}],['dBm','math',{mode:'dbm'}],['DC ratio','function',{function:'ratio'}],['Limit test','math',{mode:'limit'}],
 ['4½ digits','digits',{digits:4}],['5½ digits','digits',{digits:5}],['6½ digits','digits',{digits:6}]];
let shifted=false, busy=false, lastState=null, lastContact=0, auth='', actionError='';
const shifts={
 0:['function',{function:'dci'},'DC current'],1:['function',{function:'aci'},'AC current'],
 2:['function',{function:'ohm4'},'Four-wire resistance'],3:['function',{function:'period'},'Period'],
 4:['function',{function:'diode'},'Diode test'],5:['math',{mode:'db'},'Toggle dB (voltage only)'],
 6:['math',{mode:'dbm'},'Toggle dBm (voltage only)'],7:['digits',{digits:4},'4½-digit shortcut'],
 8:['digits',{digits:5},'5½-digit shortcut'],9:['digits',{digits:6},'6½-digit shortcut'],
 10:['web-auto-hold',{},'Toggle web Auto / stable reading Hold (web equivalent)'],
 11:['local',{},'Addressed Go To Local; stops web polling first'],
 12:['menu-toggle',{},'Open/close web menu (not the physical menu)'],
 13:['menu-recall',{},'Recall last web menu item (not the physical menu)']
};
buttons[9][0]='Auto / Man';buttons[9][2]={direction:'toggle'};
function setShift(on){shifted=on;$('shift-indicator').hidden=!on;document.querySelectorAll('[data-shift]').forEach(el=>{el.classList.toggle('active',on);el.setAttribute('aria-pressed',on)})}
function createButton(spec,hotspot=false,index=-1){
 const [label,action,data,x,y,w,h,fn]=spec,b=document.createElement('button');
 b.type='button';b.textContent=hotspot?'':label;
 const primary=index===12?'Fewer web display digits; integration unchanged':index===13?'More web display digits; integration unchanged':index===7?'Lower range / web menu level down':index===8?'Higher range / web menu level up':index===9?'Toggle autorange/manual / web menu Enter':index===11?'Select the next blue secondary function':label;
 b.title=`Primary: ${primary}. Shift: ${shifts[index]?.[2]||'not assigned'}.`;
 b.setAttribute('aria-label',label);b.setAttribute('aria-description',b.title);
 b.addEventListener('mouseenter',()=>{$('button-help').textContent=b.title});b.addEventListener('focus',()=>{$('button-help').textContent=b.title});
 if(fn)b.dataset.function=fn;
 if(action==='shift')b.dataset.shift='true';
 if(hotspot){const cx=([174,283,391,499,607,713,821])[index<7?index:({7:2,8:3,9:4,10:5,11:6,12:0,13:1})[index]];b.className='hotspot';b.style.cssText=`left:${cx/1257*100}%;top:${(index<7?304:398)/528*100}%;width:${76/1257*100}%;height:${52/528*100}%`}
 b.addEventListener('click',()=>{
  if(action==='shift'){if(shifted){setShift(false);act('local',{})}else setShift(true);return}
  if(window.meterMenu?.isOpen()&&((!shifted&&[7,8,12,13].includes(index))||index===9)){setShift(false);window.meterMenu.navigate(({7:'down',8:'up',9:'enter',12:'left',13:'right'})[index]);return}
  const alt=shifted?shifts[index]:null;setShift(false);
  const selected=alt?alt[0]:action,payload=alt?alt[1]:data;
  if(selected==='menu-toggle'){window.meterMenu.toggle();return}
  if(selected==='menu-recall'){window.meterMenu.recall();return}
  if(selected==='web-fewer'||selected==='web-more'){act('web-digits',{digits:Math.max(4,Math.min(6,(lastState?.display_digits||6)+(selected==='web-more'?1:-1)))});return}
  act(selected,payload)
 });return b;
}
buttons.forEach((b,i)=>{$('controls').append(createButton(b,false,i));if($('hotspots'))$('hotspots').append(createButton(b,true,i))});
extras.forEach(b=>$('extra-controls').append(createButton(b)));
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>act(b.dataset.action,{})));
function describe(c){if(!c)return 'No configuration readback.';return `${c.function.toUpperCase()} · ${c.autorange===true?'AUTO':c.range!==undefined?'Range '+c.range:'Fixed range'} · Trigger ${c.trigger_source}, ${c.sample_count} sample · ${c.nplc!==undefined?c.nplc+' PLC · ':''}Math ${c.math_enabled?c.math:'OFF'}`}
function render(s){
 lastState=s;window.meterChart?.update(s);const preview=$('preview').checked;
 const age=s.sample_time?Math.max(0,Date.now()/1000-s.sample_time):null;
 const held=s.source==='held'&&s.polling;
 const stale=age!==null&&(!s.polling||(!held&&age>4)||Date.now()-lastContact>4000);
 const kind=preview?'preview':stale?'stale':s.source;
 $('data-source').className='badge '+kind;
 $('data-source').textContent=preview?'ILLUSTRATIVE PREVIEW · NOT LIVE':kind==='live'?'LIVE · '+age.toFixed(1)+' s ago':kind==='stale'?'LAST READING · '+age.toFixed(1)+' s ago':'DISCONNECTED · NO LIVE DATA';
 $('reading').textContent=preview?'+10.00000 V':s.reading==='—'?'—':s.reading+' '+s.unit;
 $('annunciators').textContent=preview?'ILLUSTRATIVE · SAMPLE DATA':kind==='stale'?'STALE · NOT A CURRENT MEASUREMENT':kind==='live'?describe(s.configuration):'NO LIVE DATA';
 const display=document.querySelector('.display,.modern-reading');display.classList.toggle('stale',kind==='stale');
 $('identity').textContent=s.identity?'Verified identity: '+s.identity:'Identity has not been verified.';
 $('configuration').textContent=describe(s.configuration);$('error').textContent=actionError||s.error||'';
 if(s.identity&&!s.error&&s.sample_time===null&&!s.local_requested){$('data-source').textContent='CONNECTED - NO MEASUREMENT';$('annunciators').textContent='IDENTITY VERIFIED - ACQUISITION PAUSED'}
 if(s.source==='waiting_hold'){$('data-source').textContent='WEB HOLD - WAITING FOR STABILITY';$('annunciators').textContent='Waiting for three stable readings'}
 if(s.local_requested){$('data-source').textContent='LOCAL REQUESTED - POLLING PAUSED';$('annunciators').textContent='No meter queries until an explicit new command'}
 if(held&&!stale){$('data-source').textContent='WEB HOLD - captured '+age.toFixed(1)+' s ago';$('annunciators').textContent='WEB STABLE READING HOLD'}
 $('acquisition-state').textContent=`Web acquisition: ${s.acquisition||'manual'} / Web display: ${s.display_digits||6}½ digits`;
 $('verification-state').textContent=s.read_only?'Read-only verification: measurement and setting commands are currently blocked.':'Test build: see the button-support page for hardware verification status.';
 if($('mobile-reading')){$('mobile-reading').textContent=$('reading').textContent;$('mobile-source').textContent=$('data-source').textContent}
 const t=s.stats;$('stats').textContent=t.count?`${t.count} readings · Min ${t.min} · Max ${t.max} · Mean ${t.mean}`:'No samples collected.';
 document.querySelectorAll('[data-function]').forEach(b=>{const active=b.dataset.function===s.configuration?.function;b.classList.toggle('active',active);b.setAttribute('aria-pressed',active)});
 // Preview mode cannot send hardware commands or leave acquisition running unnoticed.
 document.querySelectorAll('button').forEach(b=>{if(!b.classList.contains('layout-ui')&&!['size','appearance-reset','chart-clear'].includes(b.id))b.disabled=busy||preview});
}
async function act(action,data){
 if(busy||$('preview').checked)return;
 busy=true;actionError='';if(lastState)render(lastState);
 try{
  let headers={'Content-Type':'application/json'};if(auth)headers.Authorization='Basic '+auth;
  let response=await fetch('/api/control/meter/'+action,{method:'POST',headers,body:JSON.stringify(data),signal:AbortSignal.timeout(11000)});
  if(response.status===401){auth=await login();if(!auth)return;headers.Authorization='Basic '+auth;response=await fetch('/api/control/meter/'+action,{method:'POST',headers,body:JSON.stringify(data),signal:AbortSignal.timeout(11000)})}
  const result=await response.json();if(!response.ok)throw Error(result.error||'Meter request failed');lastContact=Date.now();render(result);
  if(action==='local')$('button-help').textContent='Addressed Go To Local acknowledged by adapter. Polling is paused. No readable local-mode status exists; verify the front panel. A new explicit meter command can return it to remote.';
  if(action==='math')window.meterMenu?.setRecall(({NULL:'null-offset',AVER:'minmax',DB:'db-reference',DBM:'dbm-reference'})[result.configuration?.math]);
 }catch(e){actionError=e.message;$('error').textContent=e.message}
 finally{busy=false;if(lastState)render(lastState);await refresh()}
}
function login(){return new Promise(resolve=>{const d=$('login-dialog');d.addEventListener('close',()=>{const result=d.returnValue==='login'?btoa($('login-user').value+':'+$('login-password').value):'';$('login-password').value='';resolve(result)},{once:true});d.showModal()})}
$('show-password').addEventListener('change',()=>{$('login-password').type=$('show-password').checked?'text':'password'});
async function refresh(){try{const r=await fetch('/api/multimeter/status',{cache:'no-store',signal:AbortSignal.timeout(3000)});if(!r.ok)throw Error('Status unavailable');const s=await r.json();lastContact=Date.now();render(s)}catch(e){if(lastState)render(lastState);$('error').textContent='Controller connection lost. Displayed readings are not current.'}}
$('guides').checked=localStorage.getItem('hp34401a-guides')==='true';
function guides(){if($('panel'))$('panel').classList.toggle('guides',$('guides').checked);localStorage.setItem('hp34401a-guides',$('guides').checked)}
$('guides').addEventListener('change',guides);guides();
$('size').addEventListener('click',()=>{const small=$('panel')?.classList.toggle('half');$('size').textContent=small?'Full size':'Half size'});
$('preview').addEventListener('change',async()=>{if($('preview').checked){$('preview').checked=false;await act('pause',{});$('preview').checked=true}if(lastState)render(lastState)});
refresh();setInterval(()=>{if(!document.hidden)refresh()},1500);setInterval(()=>{if(lastState)render(lastState)},1000);

const appearanceDefaults={font:'consolas',color:'#62ded0',transparent:true};
const displayFonts={consolas:'Consolas, monospace',courier:'"Courier New", monospace',system:'system-ui, sans-serif',arial:'Arial, sans-serif'};
let appearance={...appearanceDefaults};
try{const saved=JSON.parse(localStorage.getItem('hp34401a-appearance')||'{}');if(Object.hasOwn(displayFonts,saved.font))appearance.font=saved.font;if(/^#[0-9a-f]{6}$/i.test(saved.color))appearance.color=saved.color;if(typeof saved.transparent==='boolean')appearance.transparent=saved.transparent}catch{}
function applyAppearance(save=false){
 document.documentElement.style.setProperty('--reading-font',displayFonts[appearance.font]);
 document.documentElement.style.setProperty('--reading-color',appearance.color);
 document.body.classList.toggle('transparent-reading',appearance.transparent);
 $('display-font').value=appearance.font;$('display-color').value=appearance.color;$('display-transparent').checked=appearance.transparent;
 if(save){try{localStorage.setItem('hp34401a-appearance',JSON.stringify(appearance))}catch{$('error').textContent='Appearance updated, but browser storage is unavailable.'}}
}
$('display-font').addEventListener('change',()=>{appearance.font=$('display-font').value;applyAppearance(true)});
$('display-color').addEventListener('input',()=>{appearance.color=$('display-color').value;applyAppearance(true)});
$('display-transparent').addEventListener('change',()=>{appearance.transparent=$('display-transparent').checked;applyAppearance(true)});
$('appearance-reset').addEventListener('click',()=>{appearance={...appearanceDefaults};applyAppearance(true)});
applyAppearance();

// Cosmetic preference only; live/stale/preview labels remain on the reading.
const statusBoxToggle=$('show-status-box');
try{statusBoxToggle.checked=localStorage.getItem('hp34401a-show-status')!=='false'}catch{}
function applyStatusBox(){
 document.body.classList.toggle('hide-status-box',!statusBoxToggle.checked);
 try{localStorage.setItem('hp34401a-show-status',String(statusBoxToggle.checked))}catch{}
}
statusBoxToggle.addEventListener('change',applyStatusBox);
applyStatusBox();

(function(){
 const toggle=$('show-live-chart'),section=$('live-chart-section'),canvas=$('live-chart'),ctx=canvas.getContext('2d');
 let points=[],key=null,lastTime=null,current=null;
 try{toggle.checked=localStorage.getItem('hp34401a-chart')==='true'}catch{}
 const fmt=n=>n===0?'0':Math.abs(n)>=1e5||Math.abs(n)<.001?n.toExponential(3):Number(n.toPrecision(6)).toString();
 function draw(){
  if(section.hidden||!ctx)return;
  const width=Math.max(260,canvas.clientWidth),height=Math.max(180,canvas.clientHeight),dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,width,height);ctx.font='12px system-ui';ctx.fillStyle='#becbd1';
  const unit=current?.unit||'',preview=$('preview').checked,age=current?.sample_time?Date.now()/1000-current.sample_time:Infinity;
  $('chart-status').textContent=preview?'ILLUSTRATIVE PREVIEW — chart paused; measured history only':current?.error?'ACQUISITION ERROR — retained measured history':current?.source==='held'?'WEB HOLD — retained measured history':current?.polling&&age<5?'LIVE — measured samples':points.length?'PAUSED / STALE — retained measured history':'Waiting for measured readings. Click Start live updates to record.';
  if(!points.length){ctx.fillText('No measured samples yet',20,40);$('chart-summary').textContent='';return}
  const values=points.filter(p=>Number.isFinite(p.v)).map(p=>p.v);
  if(!values.length){ctx.fillText('Overload — no numeric samples to plot',20,40);return}
  let low=Math.min(...values),high=Math.max(...values);
  const pad=(high-low)*.08||Math.max(Math.abs(high)*.005,1e-9);low-=pad;high+=pad;
  const left=88,right=width-16,top=24,bottom=216;
  const first=points[0].t,last=points[points.length-1].t,span=Math.max(last-first,1);
  const x=t=>left+(t-first)/span*(right-left),y=v=>bottom-(v-low)/(high-low)*(bottom-top);
  ctx.strokeStyle='#536068';ctx.lineWidth=1;ctx.fillStyle='#becbd1';
  for(let i=0;i<=4;i++){const v=low+(high-low)*i/4,py=y(v);ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();ctx.fillText(fmt(v),4,py+4)}
  ctx.fillText(unit,left,14);ctx.fillText('0 s',left,bottom+22);
  ctx.textAlign='right';ctx.fillText((last-first).toFixed(1)+' s elapsed',right,bottom+22);ctx.textAlign='left';
  const color=getComputedStyle(document.documentElement).getPropertyValue('--reading-color').trim()||'#62ded0';
  ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=2;ctx.beginPath();let previous=null;
  for(const p of points){
   if(!Number.isFinite(p.v)){previous=null;continue}
   if(!previous||p.t-previous.t>10)ctx.moveTo(x(p.t),y(p.v));else ctx.lineTo(x(p.t),y(p.v));previous=p;
  }ctx.stroke();
  for(const p of points){if(Number.isFinite(p.v)){ctx.beginPath();ctx.arc(x(p.t),y(p.v),2,0,Math.PI*2);ctx.fill()}}
  const text=values.length+' samples · Minimum '+fmt(Math.min(...values))+' '+unit+' · Maximum '+fmt(Math.max(...values))+' '+unit+' · Latest '+fmt(values[values.length-1])+' '+unit;
  $('chart-summary').textContent=text;canvas.setAttribute('aria-label',text);
 }
 function update(s){
  current=s;
  if(!toggle.checked){return}
  const c=s.configuration||{},next=JSON.stringify([c.function,s.unit,c.math_enabled,c.math,c.math_reference]);
  if(key!==next){points=[];lastTime=null;key=next}
  if(!$('preview').checked&&s.sample_time&&s.sample_time!==lastTime){
   lastTime=s.sample_time;
   if(Number.isFinite(s.value)||s.reading==='OVLD'){
    points.push({t:s.sample_time,v:Number.isFinite(s.value)?s.value:null});if(points.length>300)points.shift()
   }
  }
  draw();
 }
 function visibility(){section.hidden=!toggle.checked;try{localStorage.setItem('hp34401a-chart',String(toggle.checked))}catch{}if(current)update(current);else draw()}
 toggle.addEventListener('change',visibility);
 $('chart-clear').addEventListener('click',()=>{points=[];lastTime=current?.sample_time||null;draw()});
 $('display-color').addEventListener('input',draw);
 new ResizeObserver(draw).observe(canvas);
 window.meterChart={update};visibility();if(lastState)update(lastState);
})();

const dmmMain=document.querySelector('main'),dmmToolbar=dmmMain.querySelector('.toolbar'),dmmGrid=document.createElement('div');dmmGrid.id='meter-layout-grid';dmmGrid.className='meter-grid';dmmToolbar.after(dmmGrid);const dmmTiles=[...dmmMain.children].filter(n=>n.tagName==='SECTION'||n.id==='panel-wrap');dmmTiles.forEach((n,i)=>{n.dataset.tileId=n.id||'section-'+i;if(!n.id)n.id=n.dataset.tileId;dmmGrid.append(n);if(n.id==='panel-wrap'){const mobile=dmmMain.querySelector('.mobile-reading');if(mobile)n.append(mobile)}});const dmmBar=dmmMain.querySelector('.layout-toolbar');dmmBar.classList.add('suite-layoutbar');dmmToolbar.append(dmmBar);
(function(config){
 const $=id=>document.getElementById(id);
 let grid=document.querySelector(config.root);
 const tiles=[...grid.querySelectorAll(config.tiles)],names={};
 tiles.forEach((tile,i)=>{
  tile.dataset.tileId=tile.id||(config.prefix==='hp6033a-modern'?'tile-'+(i+1):'tile-'+i);
  names[tile.dataset.tileId]=config.names?.[i]||(tile.id==='panel-wrap'?'Classic front panel':null)||tile.getAttribute('aria-label')||tile.querySelector('h1,h2,summary')?.textContent||'Section '+(i+1);
  tile.classList.add('meter-tile');tile.dataset.defaultSpan=config.prefix==='tek'?(tile.classList.contains('wide')?7:tile.classList.contains('narrow')?5:tile.classList.contains('full')?12:6):12;
 });
 grid.classList.add('suite-grid');
 const bar=document.querySelector(config.toolbar);
 bar.innerHTML='<button id="layout-customize" class="layout-ui" type="button" aria-pressed="false">Customize layout</button><button id="layout-reset" class="layout-ui" type="button" hidden>Reset layout</button><button id="layout-show-all" class="layout-ui" type="button" hidden>Show all boxes</button><span id="layout-note" hidden>Drag a handle or use arrows to move. Set a width or drag the bottom-right corner to resize. Saved in this browser.</span>';
 const emit=name=>document.dispatchEvent(new CustomEvent('suite-layout-'+name));
 let editing=false,drag=null,resize=null;
 const mode=window.matchMedia('(max-width:'+config.breakpoint+'px)');
 const storageKey=()=> 'fischer-suite-layout-v1-'+config.prefix+'-'+(mode.matches?'mobile':'desktop');
 const button=(text,label,fn)=>{const b=document.createElement('button');b.type='button';b.className='layout-ui';b.textContent=text;b.setAttribute('aria-label',label);b.addEventListener('click',fn);return b};
 function save(){try{localStorage.setItem(storageKey(),JSON.stringify([...grid.children].filter(n=>tiles.includes(n)).map(n=>({id:n.dataset.tileId,width:Number(n.dataset.tileWidth)||12,height:Number(n.dataset.tileHeight)||0,hidden:n.dataset.userHidden==='true'}))))}catch{$('layout-note').textContent='Layout updated, but browser storage is unavailable.'}emit('save')}
 function applySize(tile,width,height){
  tile.dataset.tileWidth=width;tile.dataset.tileHeight=height;tile.style.setProperty('--tile-span',width);
  tile.style.minHeight=height?height+'px':'';
  const canvas=tile.querySelector('canvas');if(canvas&&height)canvas.style.height=Math.max(150,height-200)+'px';else if(canvas)canvas.style.height='';
  const select=tile.querySelector('.tile-width');if(![...select.options].some(o=>Number(o.value)===width)){const o=document.createElement('option');o.value=width;o.textContent='Default';select.append(o)}select.value=width;const visibility=tile.querySelector('.tile-visibility');if(visibility)visibility.textContent=tile.dataset.userHidden==='true'?'Show':'Hide';
 }
 function restore(){
  let saved=[];try{saved=JSON.parse(localStorage.getItem(storageKey())||'[]')}catch{}
  if(!Array.isArray(saved))saved=[];
  if(!saved.length){
   try{
    if(config.prefix.startsWith('hp34401a-')){saved=JSON.parse(localStorage.getItem('hp34401a-layout-v1-'+config.prefix.replace('hp34401a-','')+'-'+(mode.matches?'mobile':'desktop'))||'[]')}else if(config.prefix==='hp6033a-modern'){
     const oldKey='hp6033a-layout-'+(mode.matches?'mobile':'desktop'),order=JSON.parse(localStorage.getItem(oldKey)||'[]'),widths=JSON.parse(localStorage.getItem(oldKey+'-widths')||'{}'),hidden=JSON.parse(localStorage.getItem(oldKey+'-visibility')||'{}');
     saved=[...new Set([...order,...tiles.map(n=>n.dataset.tileId)])].map(id=>({id,width:widths[id]==='half'?6:12,hidden:hidden[id]===true,height:0}));
    }else if(config.prefix==='tek'){
     const order=JSON.parse(localStorage.getItem('fischer-tek-layout-v2')||'[]'),sizes=JSON.parse(localStorage.getItem('fischer-tek-panel-sizes-v1')||'{}');
     saved=[...new Set([...order,...tiles.map(n=>n.dataset.tileId)])].map(id=>({id,width:sizes[id]?.width==='half'?6:sizes[id]?.width==='full'?12:Number(tiles.find(n=>n.dataset.tileId===id)?.dataset.defaultSpan)||12,height:sizes[id]?.height||0}));
    }
   }catch{}
  }
  const used=new Set();
  for(const entry of saved){const tile=tiles.find(n=>n.dataset.tileId===entry.id);if(!tile||used.has(tile))continue;used.add(tile);grid.insertBefore(tile,grid.querySelector(':scope>footer'));tile.dataset.userHidden=String(entry.hidden===true);applySize(tile,[4,5,6,7,8,12].includes(entry.width)?entry.width:12,Number.isFinite(entry.height)?Math.max(0,Math.min(1200,entry.height)):0)}
  tiles.filter(n=>!used.has(n)).forEach(n=>{grid.insertBefore(n,grid.querySelector(':scope>footer'));n.dataset.userHidden='false';applySize(n,Number(n.dataset.defaultSpan)||12,0)});
 }
 function move(tile,delta){
  const visible=tiles.filter(n=>n.parentElement===grid).sort((a,b)=>[...grid.children].indexOf(a)-[...grid.children].indexOf(b)).filter(n=>!n.hidden&&n.dataset.userHidden!=='true'),index=visible.indexOf(tile),other=visible[index+delta];
  if(!other)return;
  if(delta<0)grid.insertBefore(tile,other);else grid.insertBefore(tile,other.nextSibling);
  save();tile.querySelector('.tile-drag').focus();
 }
 tiles.forEach(tile=>{
  const name=names[tile.dataset.tileId],tools=document.createElement('div');tools.className='tile-tools';
  const handle=button('☰ '+name,'Drag '+name+' to move',()=>{});handle.classList.add('tile-drag');
  handle.addEventListener('pointerdown',e=>{if(!editing||e.button!==0)return;e.preventDefault();handle.setPointerCapture(e.pointerId);drag={tile,handle,x:e.clientX,y:e.clientY,target:null,after:false};tile.classList.add('tile-moving')});
  handle.addEventListener('pointermove',e=>{
   if(!drag||drag.handle!==handle||Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<8)return;
   tiles.forEach(n=>n.classList.remove('tile-target'));
   const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('.meter-tile');
   drag.target=target&&target!==tile?target:null;
   if(drag.target){const r=target.getBoundingClientRect();drag.after=e.clientY>r.top+r.height/2;target.classList.add('tile-target')}
   if(e.clientY<70)window.scrollBy(0,-18);else if(e.clientY>window.innerHeight-70)window.scrollBy(0,18);
  });
  function drop(e){if(!drag||drag.handle!==handle)return;if(e.type!=='pointercancel'&&drag.target)grid.insertBefore(tile,drag.after?drag.target.nextSibling:drag.target);tiles.forEach(n=>n.classList.remove('tile-target','tile-moving'));drag=null;save()}
  handle.addEventListener('pointerup',drop);handle.addEventListener('pointercancel',drop);
  const up=button('↑','Move '+name+' earlier',()=>move(tile,-1)),down=button('↓','Move '+name+' later',()=>move(tile,1));
  const widthLabel=document.createElement('label');widthLabel.textContent='Width ';
  const select=document.createElement('select');select.className='tile-width';select.setAttribute('aria-label',name+' width');
  for(const [v,label] of [[12,'Full'],[8,'Two thirds'],[6,'Half'],[4,'One third']]){const o=document.createElement('option');o.value=v;o.textContent=label;select.append(o)}
  select.addEventListener('change',()=>{applySize(tile,Number(select.value),Number(tile.dataset.tileHeight)||0);save()});widthLabel.append(select);
  const visibility=button('Hide','Hide or show '+name,()=>{tile.dataset.userHidden=String(tile.dataset.userHidden!=='true');visibility.textContent=tile.dataset.userHidden==='true'?'Show':'Hide';save()});
  visibility.classList.add('tile-visibility');tools.append(handle,up,down,widthLabel,visibility);tile.prepend(tools);
  const grip=button('↘','Resize '+name+'; arrow keys adjust width and height',()=>{});grip.classList.add('tile-resize');tile.append(grip);
  grip.addEventListener('pointerdown',e=>{if(!editing||e.button!==0)return;e.preventDefault();grip.setPointerCapture(e.pointerId);const r=tile.getBoundingClientRect();resize={tile,x:e.clientX,y:e.clientY,width:r.width,height:r.height}});
  grip.addEventListener('pointermove',e=>{if(!resize||resize.tile!==tile)return;const desired=(resize.width+e.clientX-resize.x)/grid.clientWidth*12;const widths=[4,6,8,12];const width=mode.matches?Number(tile.dataset.tileWidth)||12:widths.reduce((a,b)=>Math.abs(b-desired)<Math.abs(a-desired)?b:a);applySize(tile,width,Math.max(100,Math.min(1200,Math.round(resize.height+e.clientY-resize.y))))});
  const end=()=>{if(resize?.tile===tile){resize=null;save()}};grip.addEventListener('pointerup',end);grip.addEventListener('pointercancel',end);
  grip.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();let width=Number(tile.dataset.tileWidth)||12,height=Number(tile.dataset.tileHeight)||tile.offsetHeight;const widths=[4,6,8,12];if(e.key==='ArrowLeft')width=widths[Math.max(0,widths.indexOf(width)-1)];if(e.key==='ArrowRight')width=widths[Math.min(3,widths.indexOf(width)+1)];if(e.key==='ArrowUp')height-=40;if(e.key==='ArrowDown')height+=40;applySize(tile,width,Math.max(100,Math.min(1200,height)));save()});
 });
 $('layout-customize').addEventListener('click',()=>{
  editing=!editing;document.body.classList.toggle('layout-editing',editing);$('layout-customize').textContent=editing?'Save layout':'Customize layout';$('layout-customize').setAttribute('aria-pressed',String(editing));$('layout-reset').hidden=!editing;$('layout-show-all').hidden=!editing;$('layout-note').hidden=!editing;if(!editing)save();
 });
 $('layout-reset').addEventListener('click',()=>{try{localStorage.removeItem(storageKey())}catch{}tiles.forEach(n=>{grid.insertBefore(n,grid.querySelector(':scope>footer'));n.dataset.userHidden='false';applySize(n,Number(n.dataset.defaultSpan)||12,0)});emit('reset');save()});
 $('layout-show-all').addEventListener('click',()=>{tiles.forEach(n=>{n.dataset.userHidden='false';const b=n.querySelector('.tile-visibility');if(b)b.textContent='Hide'});emit('showall');save()});mode.addEventListener('change',()=>{restore();emit('load')});restore();
})({"root":"#meter-layout-grid","tiles":":scope>*","toolbar":".layout-toolbar","prefix":'hp34401a-'+document.body.dataset.view,"breakpoint":700});(function(){const host=location.hostname;document.querySelectorAll('.suite-topbar a,nav[aria-label="Instrument navigation"] a').forEach(a=>a.classList.add('suite-tool-link'));const tekTitle=document.querySelector('.suite-topbar h1');if(tekTitle?.textContent.includes('Tektronix')){const back=document.getElementById('suiteLink');if(back){back.textContent='HP 6033A';back.href=location.protocol+'//'+host+'/'}const meter=document.createElement('a');meter.href=location.protocol+'//'+host+'/multimeter/classic';meter.textContent='HP 34401A';meter.className='suite-tool-link';document.querySelector('.suite-topbar').insertBefore(meter,document.querySelector('.suite-topbar .suite-layoutbar'))}const meterNav=document.querySelector('nav[aria-label="Instrument navigation"]');if(meterNav){const supply=meterNav.querySelector('a'),group=document.createElement('div');group.className='suite-tool-links';supply.before(group);group.append(supply);const tek=document.createElement('a');tek.href='http://'+host+':8081/';tek.textContent='Tektronix TDS 3032B';tek.className='suite-tool-link';group.append(tek)}})();