const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/index.html','utf8');
const start=html.indexOf('let currentTriggerSource='),end=html.indexOf('let measurementRows=',start);
const classes=new Map(),nodes={triggerSourceStatus:{textContent:''}};
for(const id of ['a','b','c']){nodes['reading-'+id]={classList:{toggle(k,on){classes.set(id,on)}}};nodes['trigger-'+id]={hidden:true}}
for(const n of [1,2])nodes['channel-trigger-'+n]={hidden:true};
const c={$:id=>nodes[id],measurementRows:[{id:'a',channel:'CH1'},{id:'b',channel:'CH2'},{id:'c',channel:'CH1'}]};
vm.createContext(c);vm.runInContext(html.slice(start,end),c);
for(const ch of ['CH1','CH2']){c.updateTriggerIndicators({trigger_type:'EDGE',trigger_source:ch});for(const row of c.measurementRows){assert.equal(classes.get(row.id),row.channel===ch);assert.equal(nodes['trigger-'+row.id].hidden,row.channel!==ch)}}
c.updateTriggerIndicators({trigger_type:'EDGE',trigger_source:'EXT'});assert([...classes.values()].every(v=>!v));assert.match(nodes.triggerSourceStatus.textContent,/EXT/);
c.updateTriggerIndicators({trigger_type:'PULSE',trigger_source:'CH1'});assert([...classes.values()].every(v=>!v));
c.updateTriggerIndicators({});assert([...classes.values()].every(v=>!v));assert.match(nodes.triggerSourceStatus.textContent,/unavailable/);
console.log('PASS trigger badges follow actual CH1/CH2, clear for external/complex/unavailable sources');
