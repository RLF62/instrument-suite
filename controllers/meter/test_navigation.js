const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/navigation.js','utf8');
function links(current,instruments,href='http://controller:8082/multimeter/classic') {
  let groups=[];
  const nav={querySelectorAll:()=>[],matches:()=>current==='meter',append:g=>groups.push(g),prepend:g=>groups.push(g)};
  const document={readyState:'complete',querySelector:()=>nav,createElement:()=>({children:[],setAttribute(){},append(a){this.children.push(a)}})};
  vm.runInNewContext(source,{document,URL,location:new URL(href),window:{fischerSuite:{current,instruments}}});
  return groups.flatMap(g=>g.children).filter(a=>a.textContent!=='Add instruments').map(a=>({text:a.textContent,href:a.href}));
}
test('meter only advertises no other instruments',()=>assert.deepEqual(links('meter',['meter']),[]));
test('meter and supply has no scope link',()=>assert.deepEqual(links('meter',['meter','supply']),[{text:'HP 6033A',href:'http://controller/'}]));
test('all tools retain the correct scope HTTP port from HTTPS',()=>{
 const result=links('meter',['meter','supply','scope'],'https://controller/multimeter/classic');
 assert.deepEqual(result,[{text:'HP 6033A',href:'https://controller/'},{text:'Tektronix',href:'http://controller:8081/'}]);
});
test('scope links to base meter dashboard rather than scope port',()=>{
 const result=links('scope',['meter','supply','scope'],'http://controller:8081/');
 assert.equal(result[0].href,'http://controller/multimeter/classic');
});
test('meter links to the generator Classic view',()=>{
 const result=links('meter',['meter','generator']);
 assert.deepEqual(result,[{text:'HP 33120A',href:'http://controller:8082/generator/classic'}]);
});
test('changing selection removes all unselected destinations',()=>assert.deepEqual(links('supply',['supply']),[]));
