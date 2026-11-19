'use strict';
(()=>{
const groups=[
 ['Measurement',[
 ['ac-filter','AC filter',3,[3,20,200]],['input-r','Automatic DC input resistance',0,[0,1]],['autozero','Autozero',1,[0,1]],
 ['web-digits','Web display digits',6,[4,5,6]],['terminals','Front/Rear selector readback',null,null]]],
 ['Math',[
 ['null-offset','Null offset',0,'number'],['db-reference','dB reference',0,'number'],['dbm-reference','dBm reference Ω',600,[50,75,93,110,124,125,135,150,250,300,500,600,800,900,1000,1200,8000]],
 ['minmax','Instrument Min/Max/Mean/Count',null,null],['limit-low','Lower limit',0,'number'],['limit-high','Upper limit',1,'number']]],
 ['Trigger',[
 ['trigger-source','Trigger source','IMM',['IMM','BUS','EXT']],['trigger-delay','Trigger delay seconds',0,'number'],['trigger-auto-delay','Automatic trigger delay',1,[0,1]],
 ['sample-count','Samples per trigger',1,'number'],['trigger-count','Trigger count',1,'number'],['hold-band','Web Hold stability band %',.1,[.01,.1,1,10]]]],
 ['System',[
 ['beeper','Beeper',1,[0,1]],['display','Instrument display',1,[0,1]],['error','Read oldest error (consumes it)',null,null],['revision','Instrument identity / revision',null,null],['scpi-version','SCPI version',null,null]]]
];
let open=false,level=0,category=0,index=0,last='ac-filter';
const item=()=>groups[category][1][index];
function renderMenu(){
 const categories=$('menu-category'),items=$('menu-item'),select=$('menu-value-select'),input=$('menu-value-number');
 categories.replaceChildren();items.replaceChildren();select.replaceChildren();
 groups.forEach(([name],i)=>categories.add(new Option(name,i,i===category,i===category)));
 groups[category][1].forEach((entry,i)=>items.add(new Option(entry[1],i,i===index,i===index)));
 const entry=item();select.hidden=!Array.isArray(entry[3]);input.hidden=entry[3]!=='number';
 if(Array.isArray(entry[3]))entry[3].forEach(v=>select.add(new Option(String(v),String(v),v===entry[2],v===entry[2])));
 input.value=entry[2]??'';$('menu-apply').disabled=entry[3]===null;
 $('menu-level').textContent=['Category','Command','Value'][level]+' level - WEB MENU';
 $('menu-note').textContent=entry[0]==='dbm-reference'?'Stored in the meter’s non-volatile memory.':entry[0]==='terminals'?'Physical selector: readback only.':entry[0].startsWith('web-')||entry[0]==='hold-band'?'Web equivalent; the meter’s physical menu is not operated.':'Apply/Enter sends this documented setting and reads back the result.';
}
function show(on,recall){open=on;$('web-menu').hidden=!open;if(recall){groups.forEach((g,c)=>{const i=g[1].findIndex(x=>x[0]===recall);if(i>=0){category=c;index=i}});level=1}renderMenu();if(on)$('menu-category').focus()}
function result(){if(lastState?.menu_result)$('menu-result').textContent=JSON.stringify(lastState.menu_result.value??lastState.menu_result,null,2)}
async function read(){const key=item()[0];if(['web-digits','hold-band'].includes(key)){$('menu-result').textContent=String(key==='web-digits'?lastState?.display_digits:lastState?.hold_band);return}await act('menu-read',{item:key});result()}
async function apply(){
 const entry=item();if(entry[3]===null){await read();return}
 let value=Array.isArray(entry[3])?$('menu-value-select').value:$('menu-value-number').value;if(entry[0]!=='trigger-source')value=Number(value);
 const action=entry[0]==='web-digits'?'web-digits':entry[0]==='hold-band'?'hold-band':'menu-set';
 await act(action,action==='web-digits'?{digits:value}:action==='hold-band'?{value}:{item:entry[0],value});
 if(!actionError){last=entry[0];result();$('button-help').textContent='Web menu edit applied; instrument values were read back where applicable.';show(false)}
}
async function navigate(key){
 if(key==='enter'){await apply();return}
 if(key==='down'||key==='up'){level=Math.max(0,Math.min(2,level+(key==='down'?1:-1)));$('menu-level').textContent=['Category','Command','Value'][level]+' level - WEB MENU';return}
 const step=key==='right'?1:-1;
 if(level===0){category=(category+step+groups.length)%groups.length;index=0;renderMenu()}
 else if(level===1){const n=groups[category][1].length;index=(index+step+n)%n;renderMenu()}
 else if(!$('menu-value-select').hidden){const s=$('menu-value-select');s.selectedIndex=(s.selectedIndex+step+s.options.length)%s.options.length}
 else if(!$('menu-value-number').hidden)$('menu-value-number').value=Number($('menu-value-number').value)+step;
}
$('menu-category').addEventListener('change',()=>{category=Number($('menu-category').value);index=0;level=0;renderMenu()});
$('menu-item').addEventListener('change',()=>{index=Number($('menu-item').value);level=1;renderMenu()});
$('menu-read').addEventListener('click',read);$('menu-apply').addEventListener('click',apply);$('menu-close').addEventListener('click',()=>show(false));
$('open-menu').addEventListener('click',()=>show(!open));
document.querySelectorAll('[data-menu-nav]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.menuNav)));
window.meterMenu={isOpen:()=>open,toggle:()=>show(!open),recall:()=>show(true,last),navigate,setRecall:key=>{if(key)last=key}};
renderMenu();
})();


/* HP 34401A branding: refresh head metadata for already-running template workers. */
(function () {
  function meterBranding() {
    if (!document.body || !['classic','modern'].includes(document.body.dataset.view)) return;
    const base='/multimeter/assets/';
    const links=[
      ['icon','image/x-icon',null,'icons/favicon.ico'],
      ['icon','image/png','16x16','icons/icon-16.png'],
      ['icon','image/png','32x32','icons/icon-32.png'],
      ['icon','image/png','192x192','icons/icon-192.png'],
      ['apple-touch-icon',null,'180x180','icons/icon-180.png'],
      ['manifest',null,null,'manifest.webmanifest']
    ];
    document.head.querySelectorAll('link[rel="icon"],link[rel="apple-touch-icon"],link[rel="manifest"]').forEach(el=>el.remove());
    for (const [rel,type,sizes,path] of links) {
      const el=document.createElement('link');el.rel=rel;el.href=base+path+'?v=hp34401a-branding-1';
      if(type)el.type=type;if(sizes)el.sizes=sizes;document.head.append(el);
    }
    let title=document.head.querySelector('meta[name="apple-mobile-web-app-title"]');
    if(!title){title=document.createElement('meta');title.name='apple-mobile-web-app-title';document.head.append(title);}
    title.content='HP 34401A';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',meterBranding,{once:true});
  else meterBranding();
})();
