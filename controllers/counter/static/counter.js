'use strict';
document.getElementById('suite-home').href=location.protocol+'//'+location.hostname+':8080/';
const $ = id => document.getElementById(id);
const view = location.pathname === '/modern' ? 'modern' : 'classic';
document.body.classList.toggle('modern',view==='modern');
document.querySelector('[data-view="'+view+'"]').setAttribute('aria-current','page');
$('half').onclick=()=>{document.body.classList.toggle('half');$('half').textContent=document.body.classList.contains('half')?'Full size':'Half size';draw()};
const colorPicker=$('modern-text-color');
const colorKey='hp5385a-modern-display-color';
try{const saved=localStorage.getItem(colorKey);if(/^#[0-9a-fA-F]{6}$/.test(saved||''))colorPicker.value=saved}catch{}
function setDisplayColor(){document.querySelector('.modern-display .reading').style.setProperty('--counter-text-color',colorPicker.value)}
colorPicker.addEventListener('input',()=>{setDisplayColor();try{localStorage.setItem(colorKey,colorPicker.value)}catch{}});
setDisplayColor();
const history=[];let busy=false,lastKind='',nextPoll=0;
function annunciator(name,on){document.querySelectorAll('[data-ann="'+name+'"]').forEach(el=>{el.classList.toggle('active',!!on);if(el.classList.contains('annunciator'))el.setAttribute('aria-hidden',on?'false':'true')})}

function report(message,error=false){$('status').hidden=!error&&message.startsWith('Live');$('status').textContent=message;$('status').classList.toggle('error',error);$('badge').textContent=error?'DISCONNECTED · NO LIVE DATA':message.startsWith('Live')?'LIVE · '+(lastKind==='period'?'PERIOD':'FREQUENCY'):'WAITING · NO LIVE DATA'}
function paint(state){document.querySelectorAll('button[data-control]').forEach(b=>b.classList.toggle('active',state[b.dataset.control]===b.dataset.value))}
function draw(){
 const canvas=$('chart'),rect=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;
 if(!rect.width)return;canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
 const c=canvas.getContext('2d');c.scale(dpr,dpr);let w=rect.width,h=rect.height;
 c.fillStyle='#172126';c.fillRect(0,0,w,h);c.strokeStyle='#405760';c.lineWidth=1;
 for(let i=1;i<4;i++){let y=i*h/4;c.beginPath();c.moveTo(45,y);c.lineTo(w-10,y);c.stroke()}
 const values=history.filter(x=>x.kind===lastKind).slice(-120);if(!values.length){c.fillStyle='#9eb3bc';c.fillText('Waiting for live readings',50,h/2);$('chart-count').textContent='Waiting for readings';return}
 let min=Math.min(...values.map(x=>x.value)),max=Math.max(...values.map(x=>x.value));if(min===max){let pad=Math.abs(min)*.000001||1;min-=pad;max+=pad}
 c.fillStyle='#aac5c8';c.font='12px system-ui';c.fillText(max.toPrecision(7),4,18);c.fillText(min.toPrecision(7),4,h-8);
 c.strokeStyle='#86e2be';c.lineWidth=2;c.beginPath();
 values.forEach((p,i)=>{let x=50+(w-65)*(values.length===1?.5:i/(values.length-1)),y=12+(h-28)*(1-(p.value-min)/(max-min));if(i)c.lineTo(x,y);else c.moveTo(x,y)});c.stroke();
 $('chart-count').textContent=values.length+' readings · '+(lastKind==='period'?'seconds':'Hz')+' · latest '+new Date(values.at(-1).time).toLocaleTimeString();
}
new ResizeObserver(draw).observe($('chart'));
for(const event of ['save','load','reset','showall'])document.addEventListener('suite-layout-'+event,()=>requestAnimationFrame(draw));
$('clear-chart').onclick=()=>{history.length=0;draw()};
async function refresh(manual=false){
 if(busy||(!manual&&Date.now()<nextPoll))return;busy=true;annunciator('addr',true);annunciator('gate',true);
 try{
  let r=await fetch('/api/counter/reading',{cache:'no-store'}),data=await r.json();
  if(!r.ok)throw Error(data.error||'Read failed');
  if(Number.isInteger(data.status_byte))annunciator('rem',!(data.status_byte&16));
  if(data.ready===false){nextPoll=Date.now()+15000;$('display').textContent='--------';$('modern-reading').textContent='--------';$('unit').textContent='';$('modern-unit').textContent='';report(data.error||data.message||'Waiting for counter data (status '+data.status_byte+')',!!data.error);return}
  nextPoll=0;if(!Number.isFinite(data.value))throw Error('Invalid instrument reading');
  lastKind=data.kind;let value=Number(data.value).toLocaleString('en-US',{maximumFractionDigits:9});
  $('display').textContent=value;$('modern-reading').textContent=value;$('unit').textContent=data.unit;$('modern-unit').textContent=data.unit;
  history.push({value:data.value,kind:data.kind,time:Date.now()});if(history.length>240)history.shift();draw();report('Live');
 }catch(e){nextPoll=Date.now()+15000;report(e.message,true)}finally{busy=false;setTimeout(()=>{annunciator('addr',false);annunciator('gate',false)},650)}
}
async function command(control,value){
 if(busy)return;busy=true;annunciator('addr',true);if(control==='reset')annunciator('gate',true);report('Sending '+control+'…');
 try{let r=await fetch('/api/control/counter',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({control,value})}),d=await r.json();if(!r.ok)throw Error(d.error||'Command failed');paint(d.state);annunciator('rem',true);nextPoll=0;if(control==='mode'){$('display').textContent='--------';$('modern-reading').textContent='--------';$('unit').textContent='';$('modern-unit').textContent=''}report('Sent '+d.result.command)}
 catch(e){report(e.message,true)}finally{busy=false;setTimeout(()=>{annunciator('addr',false);annunciator('gate',false)},650)}
 setTimeout(refresh,1600);
}
document.querySelectorAll('button[data-control]').forEach(b=>b.onclick=()=>command(b.dataset.control,b.dataset.value));
$('read-now').onclick=()=>refresh(true);
fetch('/api/counter/state').then(r=>r.json()).then(d=>paint(d.state)).catch(()=>{});
refresh();setInterval(refresh,3000);
