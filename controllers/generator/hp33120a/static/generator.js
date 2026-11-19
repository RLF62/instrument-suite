'use strict';
const $=id=>document.getElementById(id);
let configuration=null,busy=false,auth='',simulated=false,previewSweep=false,sweepAnimationStart=performance.now(),simulationTimer=0;
const frequencyPairs=[['frequency','frequency-unit'],['sweep-start','sweep-start-unit'],['sweep-stop','sweep-stop-unit']];
const cleanNumber=value=>Number(Number(value).toPrecision(12));
function frequencyHz(inputId,unitId){return cleanNumber(Number($(inputId).value)*Number($(unitId).value))}
function formatFrequency(value){const hz=Number(value),factor=Math.abs(hz)>=1e6?1e6:Math.abs(hz)>=1e3?1e3:1;return `${cleanNumber(hz/factor).toLocaleString()} ${factor===1e6?'MHz':factor===1e3?'kHz':'Hz'}`}
function updateStagedFrequency(){const readout=$('knob-staged-frequency');if(readout)readout.textContent=formatFrequency(frequencyHz('frequency','frequency-unit'))}
const sweepFrequencyPairs=[['sweep-start','sweep-start-unit'],['sweep-stop','sweep-stop-unit']];
function validateSweepFrequency(inputId,unitId){const input=$(inputId);input.setCustomValidity(frequencyHz(inputId,unitId)>=.01?'':'Frequency must be at least 0.01 Hz.')}
const sweepIncrement=document.createElement('select');sweepIncrement.id='sweep-increment';
for(const value of [1000000,100000,10000,1000,100,10,1,.1,.01,.001]){const option=document.createElement('option');option.value=String(value);option.textContent=formatFrequency(value);sweepIncrement.append(option)}
sweepIncrement.value='10';
const sweepIncrementLabel=document.createElement('label');sweepIncrementLabel.textContent='Sweep increment';sweepIncrementLabel.append(sweepIncrement);
$('sweep-spacing').closest('label').after(sweepIncrementLabel);
function updateSweepIncrement(){const hz=Number(sweepIncrement.value);for(const [inputId,unitId] of sweepFrequencyPairs){$(inputId).step=String(hz/Number($(unitId).value));$(inputId).min='0';validateSweepFrequency(inputId,unitId)}}
sweepIncrement.addEventListener('change',updateSweepIncrement);
$('sweep-start-unit').addEventListener('change',updateSweepIncrement);$('sweep-stop-unit').addEventListener('change',updateSweepIncrement);
updateSweepIncrement();
$('sweep-ack').closest('label').remove();
$('sweep-run-ack').closest('label').remove();
function setFrequencyValue(inputId,unitId,hz){const factor=Math.abs(hz)>=1e6?1e6:Math.abs(hz)>=1e3?1e3:1;$(unitId).value=String(factor);$(unitId).dataset.factor=String(factor);$(inputId).value=cleanNumber(Number(hz)/factor)}
const sweepPresets={audio:{label:'Audio · 20 Hz–20 kHz · 10 s',start:20,stop:20000,time:10,spacing:'LOG',increment:10},fast:{label:'Fast audio · 20 Hz–20 kHz · 2 s',start:20,stop:20000,time:2,spacing:'LOG',increment:10},low:{label:'Low frequency · 1 Hz–1 kHz · 10 s',start:1,stop:1000,time:10,spacing:'LOG',increment:1},wide:{label:'Wide · 1 kHz–1 MHz · 10 s',start:1000,stop:1000000,time:10,spacing:'LOG',increment:1000}};
const sweepPreset=document.createElement('select');sweepPreset.id='sweep-preset';
for(const [value,label] of [['','Choose a preset…'],...Object.entries(sweepPresets).map(([key,p])=>[key,p.label]),['custom','Custom · saved in this browser']]){const option=document.createElement('option');option.value=value;option.textContent=label;sweepPreset.append(option)}
const sweepPresetLabel=document.createElement('label');sweepPresetLabel.textContent='Sweep preset';sweepPresetLabel.append(sweepPreset);
const saveSweepPreset=document.createElement('button');saveSweepPreset.type='button';saveSweepPreset.textContent='Save current as Custom';sweepPresetLabel.append(saveSweepPreset);
const sweepPresetBaseLabels=new Map([...sweepPreset.options].map(o=>[o.value,o.textContent.split(' · ')[0]]));
function refreshSweepPresetLabel(){if(!sweepPreset.value)return;const option=sweepPreset.selectedOptions[0],base=sweepPresetBaseLabels.get(sweepPreset.value)||'Custom',start=frequencyHz('sweep-start','sweep-start-unit'),stop=frequencyHz('sweep-stop','sweep-stop-unit'),time=cleanNumber(Number($('sweep-time').value)),spacing=$('sweep-spacing').value==='LOG'?'Log':'Linear',increment=Number(sweepIncrement.value);option.textContent=`${base} · ${formatFrequency(start)}–${formatFrequency(stop)} · ${time} s · ${spacing} · ${formatFrequency(increment)} step`}
sweepIncrementLabel.before(sweepPresetLabel);
function stageSweepPreset(p){setFrequencyValue('sweep-start','sweep-start-unit',p.start);setFrequencyValue('sweep-stop','sweep-stop-unit',p.stop);$('sweep-time').value=p.time;$('sweep-spacing').value=p.spacing;if([...sweepIncrement.options].some(o=>Number(o.value)===Number(p.increment)))sweepIncrement.value=String(p.increment);updateSweepIncrement();$('sweep-settings').dispatchEvent(new Event('input',{bubbles:true}))}
sweepPreset.addEventListener('change',()=>{if(!sweepPreset.value)return;let p=sweepPresets[sweepPreset.value];if(sweepPreset.value==='custom')try{p=JSON.parse(localStorage.getItem('hp33120a-sweep-custom')||'null')}catch{}if(!p){$('error').textContent='No Custom sweep has been saved yet.';sweepPreset.value='';return}stageSweepPreset(p)});
saveSweepPreset.addEventListener('click',()=>{const p={start:frequencyHz('sweep-start','sweep-start-unit'),stop:frequencyHz('sweep-stop','sweep-stop-unit'),time:Number($('sweep-time').value),spacing:$('sweep-spacing').value,increment:Number(sweepIncrement.value)};try{localStorage.setItem('hp33120a-sweep-custom',JSON.stringify(p));sweepPreset.value='custom';refreshSweepPresetLabel();$('sweep-note').textContent='Custom sweep preset saved in this browser, including spacing and increment.'}catch{$('error').textContent='Browser storage is unavailable; Custom preset was not saved.'}});
function syncFrequencyLimits(){const max=['TRI','RAMP'].includes($('function').value)?100000:15000000;for(const [inputId,unitId] of frequencyPairs){const factor=Number($(unitId).value);$(inputId).min=inputId==='frequency'?0.0001/factor:0;$(inputId).max=max/factor;if(inputId!=='frequency')validateSweepFrequency(inputId,unitId)}}
function bindFrequencyUnit(inputId,unitId){const unit=$(unitId);unit.dataset.factor=unit.value;unit.addEventListener('change',()=>{const oldFactor=Number(unit.dataset.factor||1),newFactor=Number(unit.value);$(inputId).value=cleanNumber(Number($(inputId).value)*oldFactor/newFactor);unit.dataset.factor=unit.value;syncFrequencyLimits();updateSimulation();updateStagedFrequency()})}
frequencyPairs.forEach(pair=>bindFrequencyUnit(...pair));
sweepFrequencyPairs.forEach(([inputId,unitId])=>$(inputId).addEventListener('input',()=>validateSweepFrequency(inputId,unitId)));
function updateSimulation(){
 const canvas=$('sim-wave');if(!canvas)return;
 clearTimeout(simulationTimer);
 const verified=configuration;
 const fn=verified?.function||'SIN';let hz=Number(verified?.frequency)||0,cycles=2.5;
 const activeSweep=Boolean(verified?.sweep&&verified?.modes?.SWE==='1');
 if(activeSweep){
  const start=Number(verified.sweep.start),stop=Number(verified.sweep.stop),duration=Math.max(.001,Number(verified.sweep.time)||10),phase=((performance.now()-sweepAnimationStart)/1000%duration)/duration;
  hz=verified.sweep.spacing==='LOG'&&start>0&&stop>0?start*Math.pow(stop/start,phase):start+(stop-start)*phase;
  const low=Math.min(start,stop),high=Math.max(start,stop);
  const density=low>0&&high>low?Math.log(Math.max(low,Math.min(high,hz))/low)/Math.log(high/low):0;
  cycles=1.25+Math.max(0,Math.min(1,density))*4.75;
 }
 $('sim-function').textContent={SIN:'SINE',SQU:'SQUARE',TRI:'TRIANGLE',RAMP:'RAMP'}[fn]||fn;
 $('sim-frequency').textContent=verified?formatFrequency(hz):'—';
 const label=document.querySelector('.sim-readout small');if(label)label.textContent=verified?(activeSweep?'VERIFIED SWEEP READBACK':'VERIFIED INSTRUMENT READBACK'):'NO VERIFIED READBACK';
 const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height,mid=h/2,amp=h*.31;
 ctx.clearRect(0,0,w,h);ctx.fillStyle='#07110f';ctx.fillRect(0,0,w,h);
 ctx.strokeStyle='rgba(98,222,208,.14)';ctx.lineWidth=1;
 for(let x=0;x<=w;x+=w/6){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke()}
 for(let y=0;y<=h;y+=h/4){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke()}
 ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--reading-color').trim()||'#62ded0';ctx.lineWidth=3;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();
 for(let x=0;x<=w;x++){const phase=(x/w)*cycles*2*Math.PI;let v=0;
  if(fn==='SQU')v=Math.sin(phase)>=0?1:-1;
  else if(fn==='TRI')v=2/Math.PI*Math.asin(Math.sin(phase));
  else if(fn==='RAMP')v=2*((phase/(2*Math.PI))-Math.floor(.5+phase/(2*Math.PI)));
  else v=Math.sin(phase);
  const y=mid-v*amp;if(x===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)
 }
 ctx.stroke();
 if(activeSweep)simulationTimer=setTimeout(updateSimulation,80);
}

function loadState(){const high=$('load').value==='INF';$('load-toggle').textContent=high?'Stage 50 Ω':'Stage High Z';$('load-state').textContent=`Current assumption: ${configuration?(configuration.load==='INF'?'HIGH Z':'50 Ω'):'unknown'} · staged: ${high?'HIGH Z':'50 Ω'}. Source impedance is always 50 Ω. Apply uses the entered Vpp/offset for the selected assumption; it does not preserve physical voltage when the assumption changes. A physical high-Z load with 50 Ω configured sees approximately twice the indicated voltage; a physical 50 Ω load with HIGH Z configured sees approximately half.`}
function enable(){
 loadState();
 $('apply').disabled=busy;
 $('copy-readback').disabled=busy||!configuration;
 const runReady=!busy&&configuration?.sweep;
 $('sweep-start-button').disabled=!runReady||configuration.modes.SWE!=='0';
 $('sweep-stop-button').disabled=busy;
 $('sweep-apply').disabled=busy;
 document.querySelectorAll('[data-action]').forEach(b=>b.disabled=busy);
}
function render(s){
 simulated=s.source==='simulated'; configuration=s.configuration||null;
 const sourceBadge=$('data-source');
 sourceBadge.hidden=Boolean(configuration&&!simulated);
 sourceBadge.textContent=simulated?'SIMULATED · NO HARDWARE':s.source==='unknown'?'OUTPUT STATE UNKNOWN':'NO CONFIGURATION READBACK';
 sourceBadge.className='badge '+(simulated?'preview':'stale');
 $('reading').textContent=configuration?formatFrequency(configuration.frequency):'—';
 $('annunciators').textContent=configuration?`${configuration.function} · ${configuration.amplitude} ${configuration.unit} · ${configuration.offset} V offset · ${configuration.load==='50'?'50 Ω':'HIGH Z'} assumed load`:'NO CONFIGURATION READBACK';
 if($('mobile-reading')){$('mobile-reading').textContent=$('reading').textContent;$('mobile-source').textContent=$('annunciators').textContent}
 $('sweep-readback').textContent=configuration?.sweep?`${configuration.function} · ${configuration.amplitude} ${configuration.unit} · ${configuration.offset} V offset · configured load assumption ${configuration.load==='50'?'50 Ω':'HIGH Z'} (not measured)\n${formatFrequency(configuration.sweep.start)} → ${formatFrequency(configuration.sweep.stop)} · ${configuration.sweep.time} s · ${configuration.sweep.spacing} · sweep ${configuration.modes.SWE==='1'?'ON':'OFF'}`:'Read sweep configuration; no verified sweep setup.';
 $('identity').textContent=configuration?.identity||s.identity||'Identity not verified.';
 $('configuration').textContent=configuration?`${$('annunciators').textContent}\nTrigger: ${configuration.trigger}; modes: ${Object.entries(configuration.modes).map(([k,v])=>k+' '+(v==='1'?'ON':'OFF')).join(', ')}; duty: ${configuration.duty}%`:'No configuration readback.';
 $('error').textContent=s.error||''; updateSimulation();enable();
}
function login(){return new Promise(resolve=>{const d=$('login-dialog');d.addEventListener('close',()=>{const value=d.returnValue==='login'?btoa($('login-user').value+':'+$('login-password').value):'';$('login-password').value='';resolve(value)},{once:true});d.showModal()})}
async function act(action,data={}){
 if(busy)return;busy=true;enable();$('error').textContent='';
 try{
  const headers={'Content-Type':'application/json'};if(auth)headers.Authorization='Basic '+auth;
  const send=()=>fetch('/api/control/generator/'+action,{method:'POST',headers,body:JSON.stringify(data),signal:AbortSignal.timeout(43000)});
  let response=await send();
  // A gateway 401 occurs before dispatch; all other failures are never retried.
  if(response.status===401){auth=await login();if(!auth)return;headers.Authorization='Basic '+auth;response=await send()}
  const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');render(result);
  $('staged-note').textContent=action==='apply'?'Apply completed; settings read back. Staged fields remain editable.':'Review staged values before Apply. Reading configuration never changes the staged fields.';
 }catch(e){configuration=null;$('data-source').textContent='OUTPUT STATE UNKNOWN';$('reading').textContent='—';$('annunciators').textContent='NO VERIFIED READBACK';$('configuration').textContent='Configuration invalidated.';if($('mobile-reading')){$('mobile-reading').textContent='—';$('mobile-source').textContent='OUTPUT STATE UNKNOWN'};$('error').textContent=e.message+' No automatic retry. Review the error before another Apply.'}
 finally{busy=false;if(!configuration)$('sweep-readback').textContent='UNKNOWN — read sweep configuration';enable()}
}
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>act(b.dataset.action)));
$('settings').addEventListener('input',()=>{updateStagedFrequency();previewSweep=false;$('staged-note').textContent='Staged changes only — click Apply when ready.';updateSimulation();enable()});
$('function').addEventListener('change',syncFrequencyLimits);syncFrequencyLimits();updateStagedFrequency();
$('settings').addEventListener('submit',e=>{e.preventDefault();previewSweep=false;updateSimulation();const settings={function:$('function').value,load:$('load').value};settings.frequency=frequencyHz('frequency','frequency-unit');for(const key of ['amplitude','offset'])settings[key]=Number($(key).value);act('apply',{settings,expected_token:configuration?.configuration_token||configuration?.token||null,confirm_output_change:true})});
$('copy-readback').addEventListener('click',()=>{if(!configuration)return;if(configuration.unit!=='VPP'||!['SIN','SQU','TRI','RAMP'].includes(configuration.function)){$('error').textContent='Copy requires a supported waveform in Vpp. Review and enter staged settings explicitly.';return}for(const key of ['function','amplitude','offset','load'])$(key).value=configuration[key];setFrequencyValue('frequency','frequency-unit',configuration.frequency);syncFrequencyLimits();updateStagedFrequency();enable()});
const fonts={monospace:'Consolas,monospace',courier:'"Courier New",monospace',system:'system-ui,sans-serif'},simulationSizes=new Set(['normal','large','xlarge']);
function appearance(save=true){document.documentElement.style.setProperty('--reading-font',fonts[$('display-font').value]);document.documentElement.style.setProperty('--reading-color',$('display-color').value);document.documentElement.dataset.simSize=$('simulation-size').value;updateSimulation();if(save)try{localStorage.setItem('hp33120a-appearance',JSON.stringify({font:$('display-font').value,color:$('display-color').value,simulationSize:$('simulation-size').value}))}catch{}}
try{const a=JSON.parse(localStorage.getItem('hp33120a-appearance')||'{}');if(fonts[a.font])$('display-font').value=a.font;if(/^#[0-9a-f]{6}$/i.test(a.color))$('display-color').value=a.color;if(simulationSizes.has(a.simulationSize))$('simulation-size').value=a.simulationSize}catch{}
$('display-font').addEventListener('change',()=>appearance());$('display-color').addEventListener('input',()=>appearance());$('simulation-size').addEventListener('change',()=>appearance());$('appearance-reset').addEventListener('click',()=>{$('display-font').value='monospace';$('display-color').value='#62ded0';$('simulation-size').value='xlarge';appearance()});appearance(false);
// Cached application state only: this endpoint never contacts an instrument.
fetch('/api/generator/status',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Status unavailable');return r.json()}).then(render).catch(e=>{$('error').textContent=e.message});

if($('hotspots')){
 const staged=[['Sine','SIN',11.6,55.8],['Square','SQU',19.9,55.8],['Triangle','TRI',28.2,55.8],['Ramp','RAMP',36.5,55.8],['Frequency','frequency',11.6,74],['Amplitude','amplitude',19.9,74],['Offset','offset',28.2,74]];
 const arrowSteps={frequency:[1000,100,10,1,.1,.01,.001],amplitude:[10,1,.1,.01,.001],offset:[10,1,.1,.01,.001]};
 const arrowPosition={frequency:3,amplitude:2,offset:2};let arrowTarget='frequency';
 const increment=$('knob-increment');
 const selectArrowTarget=target=>{if(!arrowSteps[target])return;arrowTarget=target;document.querySelectorAll('.hotspot[data-stage-target]').forEach(h=>h.classList.toggle('active',h.dataset.stageTarget===target));const steps=arrowSteps[target],step=steps[arrowPosition[target]],unit=target==='frequency'?'Hz':'V';if(increment.dataset.target!==target){increment.replaceChildren(...steps.map((value,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`${value} ${unit}`;return option}));increment.dataset.target=target}increment.value=String(arrowPosition[target]);$('staged-note').textContent=`Knob controls ${target} in ${step} ${unit} increments. Left/Right also change the increment; Up/Down stage one step.`};
 increment.addEventListener('change',()=>{arrowPosition[arrowTarget]=Number(increment.value);selectArrowTarget(arrowTarget)});
 for(const [label,target,x,y] of staged){const b=document.createElement('button');b.type='button';b.className='hotspot';b.setAttribute('aria-label','Stage '+label);b.title='Stage '+label+' — does not send an instrument command';b.style.cssText=`left:${x}%;top:${y}%;width:6.4%;height:11%`;
 b.dataset.stageTarget=target;b.addEventListener('click',()=>{if(['SIN','SQU','TRI','RAMP'].includes(target)){$('function').value=target;$('function').dispatchEvent(new Event('change'));$('function').dispatchEvent(new Event('input',{bubbles:true}))}else{selectArrowTarget(target);$(target).focus();$(target).scrollIntoView({block:'center'})}});$('hotspots').append(b)}
 for(const target of Object.keys(arrowSteps))$(target).addEventListener('focus',()=>selectArrowTarget(target));
 const arrows=[['Up',71.0,50.3,4.4,8.4],['Down',71.0,61.6,4.4,7.4],['Right',71.0,72.0,4.4,7.4],['Left',71.0,82.2,4.4,8.2]];
 for(const [direction,x,y,w,h] of arrows){const b=document.createElement('button');b.type='button';b.className='hotspot arrow-hotspot';b.setAttribute('aria-label','Stage Arrow '+direction);b.title=`${direction} - stage only; no instrument command`;b.style.cssText=`left:${x}%;top:${y}%;width:${w}%;height:${h}%`;b.addEventListener('click',()=>{const steps=arrowSteps[arrowTarget];if(direction==='Left')arrowPosition[arrowTarget]=Math.max(0,arrowPosition[arrowTarget]-1);else if(direction==='Right')arrowPosition[arrowTarget]=Math.min(steps.length-1,arrowPosition[arrowTarget]+1);else{const input=$(arrowTarget),step=steps[arrowPosition[arrowTarget]],delta=direction==='Up'?step:-step,min=Number(input.min),max=Number(input.max),next=Math.min(max,Math.max(min,Number(input.value)+delta));input.value=cleanNumber(next);input.dispatchEvent(new Event('input',{bubbles:true}))}selectArrowTarget(arrowTarget)});$('hotspots').append(b)}
 const enterApply=document.createElement('button');
 enterApply.id='front-panel-enter-apply';enterApply.type='button';enterApply.className='hotspot apply-hotspot';enterApply.setAttribute('aria-label','Apply waveform now');enterApply.title='Enter Number — Apply waveform now and verify instrument readback';enterApply.style.cssText='left:53.25%;top:74%;width:6.4%;height:11%';enterApply.addEventListener('click',()=>{if(!busy)$('settings').requestSubmit($('apply'))});$('hotspots').append(enterApply);
 const knob=document.createElement('button');
 knob.id='tuning-knob';knob.type='button';knob.className='tuning-knob';knob.setAttribute('role','slider');knob.setAttribute('aria-label','Tuning knob. Rotate clockwise to increase the selected staged value and counterclockwise to decrease it.');knob.title='Turn to adjust the selected staged value - Apply is still required';
 $('panel').append(knob);
 const lipRepair=document.createElement('span');lipRepair.className='case-lip-repair';lipRepair.setAttribute('aria-hidden','true');
 $('panel').append(lipRepair);
 let knobRotation=0,pointerAngle=null,angleRemainder=0,activePointerId=null;
 const paintKnob=ticks=>{if(!ticks)return;knobRotation+=ticks*8;knob.style.setProperty('--knob-angle',knobRotation+'deg');const input=$(arrowTarget),step=arrowSteps[arrowTarget][arrowPosition[arrowTarget]],min=Number(input.min),max=Number(input.max),next=Math.min(max,Math.max(min,Number(input.value)+(ticks*step)));input.value=cleanNumber(next);input.dispatchEvent(new Event('input',{bubbles:true}));selectArrowTarget(arrowTarget)};
 const knobAngleAt=e=>{const rect=knob.getBoundingClientRect(),cx=rect.left+rect.width/2,cy=rect.top+rect.height/2,dx=e.clientX-cx,dy=e.clientY-cy;if(Math.hypot(dx,dy)<Math.min(rect.width,rect.height)*.18)return null;return Math.atan2(dy,dx)*180/Math.PI};
 const endKnobGesture=()=>{pointerAngle=null;angleRemainder=0;activePointerId=null;knob.classList.remove('dragging')};
 knob.addEventListener('pointerdown',e=>{if(!e.isPrimary)return;const angle=knobAngleAt(e);if(angle===null)return;pointerAngle=angle;angleRemainder=0;activePointerId=e.pointerId;try{knob.setPointerCapture(e.pointerId)}catch{}knob.classList.add('dragging');e.preventDefault();e.stopPropagation()});
 knob.addEventListener('pointermove',e=>{
  if(pointerAngle===null||e.pointerId!==activePointerId)return;const angle=knobAngleAt(e);if(angle===null)return;
  let delta=angle-pointerAngle;if(delta>180)delta-=360;if(delta<-180)delta+=360;pointerAngle=angle;angleRemainder+=delta;
  const ticks=Math.trunc(angleRemainder/7);if(ticks){angleRemainder-=ticks*7;paintKnob(ticks)}e.preventDefault();e.stopPropagation();
 });
 knob.addEventListener('pointerup',e=>{if(e.pointerId===activePointerId)endKnobGesture()});
 knob.addEventListener('pointercancel',endKnobGesture);knob.addEventListener('lostpointercapture',endKnobGesture);
 knob.addEventListener('wheel',e=>{e.preventDefault();paintKnob(e.deltaY<0?1:-1)},{passive:false});
 knob.addEventListener('keydown',e=>{if(e.key==='ArrowUp'||e.key==='ArrowRight'){e.preventDefault();paintKnob(1)}else if(e.key==='ArrowDown'||e.key==='ArrowLeft'){e.preventDefault();paintKnob(-1)}});
 selectArrowTarget('frequency');
 $('guides').addEventListener('change',()=>{$('panel').classList.toggle('guides',$('guides').checked)});
 $('size').addEventListener('click',()=>{const half=$('panel').classList.toggle('half');$('size').textContent=half?'Full size':'Half size'});
}

$('sweep-settings').addEventListener('input',()=>{previewSweep=true;sweepAnimationStart=performance.now();refreshSweepPresetLabel();$('sweep-note').textContent='Staged sweep settings only — display remains on verified instrument readback.';updateSimulation();enable()});
$('sweep-settings').addEventListener('submit',e=>{e.preventDefault();const settings={spacing:$('sweep-spacing').value};settings.start=frequencyHz('sweep-start','sweep-start-unit');settings.stop=frequencyHz('sweep-stop','sweep-stop-unit');settings.time=Number($('sweep-time').value);act('sweep_apply',{settings,expected_token:configuration?.token||null,confirm_output_change:true}).then(()=>{$('sweep-note').textContent=configuration?.sweep?'Sweep parameters read back; sweep remains OFF.':'Setup unverified; read sweep configuration.'})});

$('load-toggle').addEventListener('click',()=>{$('load').value=$('load').value==='50'?'INF':'50';$('load').dispatchEvent(new Event('input',{bubbles:true}))});

for(const mode of ['start','stop'])$('sweep-'+mode+'-button').addEventListener('click',()=>{if(mode==='start'&&!configuration?.sweep){$('error').textContent='Apply or read sweep setup before Start.';return}act('sweep_'+mode,{expected_token:configuration?(mode==='stop'?configuration.stop_token:configuration.token):null,confirm_output_change:true}).then(()=>{$('sweep-note').textContent=configuration?.sweep?(configuration.modes.SWE==='1'?'Sweep ON read back — repeating continuously; no automatic stop.':'Sweep OFF read back — signal may remain active.'):'Sweep/output state UNKNOWN — read configuration; physically isolate output if needed.'})});
