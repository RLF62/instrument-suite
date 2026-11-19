const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
const part=(start,end)=>{const a=html.indexOf(start),b=html.indexOf(end,a);assert(a>=0&&b>a);return html.slice(a,b)};
const taskCode=part('async function task(fn)','async function refreshAll(');
const pollCode=part('let lastMeasurement=0,nextScreenAt=0,nextStatusAt=0;','\ndisableControls();');
const imageCode=part('function releaseImagesAfterPaint(', 'async function task(fn)');
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function base(){
 const nodes={auto:{checked:true},measureAuto:{checked:false},originalImage:{checked:false},
  screenStatus:{textContent:''},effectStatus:{textContent:''},screen:{src:'blob:old'}};
 const events=[],frames=[],revoked=[];
 class FakeImage{async decode(){this.decoded=true;events.push('decoded:'+this.src)}}
 function screenNode(src){return {src,replaceWith(img){assert(img.decoded,'A frame must decode before it replaces the visible image');events.push('swap:'+img.src);nodes.screen=screenNode(img.src)}}}
 nodes.screen=screenNode('blob:old');
 let urls=0;
 const ctx={console,Promise,Date,AbortController,Image:FakeImage,
  URL:{createObjectURL(){return 'blob:new'+(++urls)},revokeObjectURL(url){revoked.push(url)}},
  document:{hidden:false},setTimeout(){return 1},setInterval(){return 1},updateFreshness(){},clearTimeout(){},requestAnimationFrame(fn){frames.push(fn)},
  busy:false,online:true,backgroundJob:null,backgroundAbort:null,foregroundQueue:Promise.resolve(),
  pendingActions:0,actionEpoch:0,screenGeneration:0,screenURL:'blob:old',originalScreenURL:'blob:old-original',
  originalCapturePath:'/old',currentEffect:'old effect',
  disableCalls:0,disableControls(){ctx.disableCalls++},
  notify(message){events.push('notice:'+message)},$:id=>nodes[id],readAppearance:async()=>{},
  markImageSuccess(){},markImageFailure(){},
  fetch:async()=>({ok:true,headers:{get:k=>k==='X-Original-Capture'?'/original':'channel-trace-colors'},blob:async()=>({})})
 };
 vm.createContext(ctx);vm.runInContext(taskCode+imageCode,ctx);
 return {ctx,nodes,events,frames,revoked};
}
(async()=>{
 const a=base(),gate=defer();let controlsRead=0,screenReads=0;
 a.ctx.readState=async()=>controlsRead++;
 a.ctx.readAcquisition=async opts=>assert(opts.background);
 a.ctx.readScreen=async opts=>{assert(opts.background);screenReads++;await gate.promise};
 a.ctx.readMeasurements=async()=>assert.fail('Measurement auto-refresh is off');
 vm.runInContext(pollCode,a.ctx);
 const polling=a.ctx.poll();await settle();
 assert.equal(screenReads,1);assert.equal(controlsRead,0);
 assert.equal(a.ctx.busy,false);assert.equal(a.ctx.disableCalls,0,'Background refresh must not disable controls');
 let acted=false;await a.ctx.task(async()=>{acted=true});
 assert(acted,'User action must run without waiting for the background frame');
 gate.resolve();await polling;
 console.log('PASS image-only polling leaves controls available and prioritizes user actions');

 const b=base(),hold=defer(),order=[];
 const first=b.ctx.task(async()=>{order.push('first:start');await hold.promise;order.push('first:end')});
 const second=b.ctx.task(async()=>order.push('second'));
 await settle();assert.deepEqual(order,['first:start']);hold.resolve();await Promise.all([first,second]);
 assert.deepEqual(order,['first:start','first:end','second']);assert.equal(b.ctx.busy,false);
 await b.ctx.task(async()=>{throw Error('expected failure')});
 let recovered=false;await b.ctx.task(async()=>recovered=true);assert(recovered);
 console.log('PASS foreground actions queue without drops and recover from errors');

 const c=base();await c.ctx.readScreen({background:true});
 assert.equal(c.nodes.screen.src,'blob:new1');assert.equal(c.revoked.length,0,'Old image must remain valid through the swap');
 c.frames.shift()();assert.equal(c.revoked.length,0);c.frames.shift()();
 assert.deepEqual(c.revoked,['blob:old','blob:old-original']);
 console.log('PASS decoded image commits before old URLs are released after paint');

 const d=base(),network=defer();d.ctx.fetch=()=>network.promise;
 const background=d.ctx.readScreen({background:true});
 await d.ctx.task(async()=>{});
 network.resolve({ok:true,headers:{get:()=>'/original'},blob:async()=>({})});
 await background;assert.equal(d.nodes.screen.src,'blob:old');assert.deepEqual(d.revoked,['blob:new1']);
 console.log('PASS superseded background frames cannot overwrite a user action');

 const e=base();e.nodes.originalImage.checked=true;await e.ctx.readScreen({background:true});
 assert.equal(e.nodes.screen.src,'blob:new2');assert.equal(e.ctx.originalScreenURL,'blob:new2');
 assert.match(e.nodes.effectStatus.textContent,/Original/);
 const f=base();f.nodes.originalImage.checked=true;let calls=0;
 f.ctx.fetch=async()=>{if(++calls===2)throw Error('original unavailable');return {ok:true,headers:{get:()=>'/original'},blob:async()=>({})}};
 await f.ctx.readScreen({background:true});
 assert.equal(f.nodes.screen.src,'blob:old');assert.equal(f.ctx.screenURL,'blob:old');
 assert.deepEqual(f.revoked,['blob:new1']);assert.match(f.nodes.screenStatus.textContent,/last image retained/);
 console.log('PASS original-view loading and failures retain the last valid frame');
 const quality={Date};vm.createContext(quality);vm.runInContext(part('function freshnessText(', 'function updateFreshness('),quality);
 const now=Date.now(),stamp=now-5000;
 assert.equal(quality.freshnessText(stamp,false,true,now).stale,false);
 assert.equal(quality.freshnessText(stamp,true,false,now).stale,true);
 assert.equal(quality.freshnessText(now-31000,false,true,now).stale,true);
 assert.equal(quality.freshnessText(now-31000,false,false,now).stale,false);
 assert.match(quality.freshnessText(stamp,true,true,now).text,/Last successful update/);
 console.log('PASS freshness distinguishes retained failed readings, delayed updates and manual snapshots');
 console.log('6 refresh regression checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
