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
})({"root":"#generator-layout-grid","tiles":":scope>*","toolbar":".layout-toolbar","prefix":'hp33120a-'+document.body.dataset.view,"breakpoint":700});
