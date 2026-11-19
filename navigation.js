/* Shared instrument header. Dashboard panels and controls are left in place. */
(function () {
  function render() {
    const cfg=window.fischerSuite;
    if(!cfg || !Array.isArray(cfg.instruments))return;
    const pathname=location.pathname;
    if(pathname.startsWith('/docs') || pathname.startsWith('/api/') || pathname==='/setup' || pathname.startsWith('/gpib-firmware'))return;
    let current=cfg.current;
    if(current==='auto')current=pathname.startsWith('/multimeter/')?'meter':pathname.startsWith('/generator/')?'generator':'supply';
    const titles={supply:'HP 6033A POWER SUPPLY',meter:'HP 34401A MULTIMETER',scope:'TEKTRONIX TDS 3032B',generator:'HP 33120A FUNCTION GENERATOR',counter:'HP 5385A FREQUENCY COUNTER'};
    if(!titles[current])return;
    const nav=document.querySelector('nav[aria-label="Instrument navigation"], nav.suite-topbar, nav[aria-label="Instrument suite"], body > nav, header nav');
    if(!nav)return;
    const classic=pathname==='/classic-dual' || pathname==='/classic' || /\/(?:multimeter|generator)\/classic/.test(pathname);
    const paths={
      supply:classic?'/classic-dual':'/',
      meter:classic?'/multimeter/classic':'/multimeter/modern',
      generator:classic?'/generator/classic':'/generator/modern',
      scope:'/',
      counter:classic?'/classic':'/modern'
    };
    const docs={supply:'/docs/',meter:'/multimeter/assets/docs/index.html',scope:'/docs/',generator:'/generator/assets/docs.html',counter:'/docs/'};
    const viewPaths={supply:['/classic-dual','/'],meter:['/multimeter/classic','/multimeter/modern'],generator:['/generator/classic','/generator/modern'],counter:['/classic','/modern']};
    const originFor=record=>record.scheme+'://'+location.hostname+(record.port?':'+record.port:'');
    const left=document.createElement('div');left.className='suite-unified-links';
    for(const tool of cfg.instruments){
      if(tool===current || !titles[tool])continue;
      const rec=cfg.records?.[tool];
      if(!rec)continue;
      const a=document.createElement('a');a.href=originFor(rec)+paths[tool];
      a.textContent={supply:'HP 6033A',meter:'HP 34401A',scope:'Tektronix',generator:'HP 33120A',counter:'HP 5385A'}[tool];
      left.append(a);
    }
    const add=document.createElement('a');add.href='/api/suite/manager';add.textContent='Add instruments';left.append(add);
    const home=document.createElement('a');home.textContent='Suite Home';home.href=location.protocol+'//'+location.hostname+':8080/';
    const name=document.createElement('strong');name.textContent=titles[current];
    const right=document.createElement('div');right.className='suite-unified-actions';right.append(home);
    const actions=viewPaths[current];
    if(actions){
      for(const [i,label] of ['Classic','Modern'].entries()){
        const a=document.createElement('a');a.href=actions[i];a.textContent=label;
        if(pathname===actions[i])a.setAttribute('aria-current','page');
        right.append(a);
      }
    }else if(current==='scope'){
      const setup=document.createElement('a');setup.href='/setup';setup.textContent='Setup';right.append(setup);
    }

    const documentation=document.createElement('a');documentation.href=docs[current];documentation.textContent='Documentation';right.append(documentation);
    const scopeStatus=current==='scope' && !document.querySelector('.suite-unified-status')?document.getElementById('connection'):null;
    const scopeHeader=current==='scope'?nav.closest('header'):null;
    const supplyHeader=current==='supply' && pathname==='/'?document.querySelector('main.wrap > header.head'):null;
    const supplyStatus=supplyHeader?.querySelector('#mode_badge')||null;
    nav.replaceChildren(left,name,right);
    nav.className='suite-unified-nav';
    nav.setAttribute('aria-label','Instrument navigation');
    if((current==='meter'||current==='generator') && nav.parentElement!==document.body){
      document.body.insertBefore(nav,document.body.firstChild);
    }
    if(scopeHeader){
      document.body.insertBefore(nav,document.body.firstChild);
      scopeHeader.hidden=true;scopeHeader.style.display='none';
    }
    if(current==='supply' && pathname==='/' && supplyHeader){
      document.body.insertBefore(nav,document.body.firstChild);
      supplyHeader.hidden=true;supplyHeader.style.display='none';
    }
    if(scopeStatus || supplyStatus){
      const status=document.createElement('div');status.className='suite-unified-status';
      if(scopeStatus)status.append(scopeStatus);
      if(supplyStatus)status.append(supplyStatus);
      nav.after(status);
    }
    if(!document.getElementById('suite-unified-style')){
      const style=document.createElement('style');style.id='suite-unified-style';
      style.textContent=`
      .suite-unified-nav{box-sizing:border-box!important;position:sticky!important;top:0!important;z-index:1000!important;left:50%!important;transform:translateX(-50%)!important;width:100vw!important;max-width:none!important;display:grid!important;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr)!important;align-items:center!important;gap:16px!important;min-height:76px!important;margin:0 0 14px!important;padding:14px max(20px,2vw)!important;background:#1e2226!important;border-top:2px solid #d0d6d9!important;border-bottom:1px solid #394550!important;border-radius:0!important;color:#f2f6f8!important;font:14px system-ui,sans-serif!important}
      body>.suite-unified-nav{left:0!important;transform:none!important;width:100%!important;margin-left:0!important;margin-right:0!important}
      .suite-unified-nav>strong{grid-column:2!important;text-align:center!important;white-space:nowrap!important;letter-spacing:.04em!important;font:700 15px system-ui,sans-serif!important;color:#f2f6f8!important}
      .suite-unified-links,.suite-unified-actions{display:flex!important;align-items:center!important;gap:8px!important;flex-wrap:wrap!important}
      .suite-unified-links{grid-column:1!important;justify-content:flex-start!important;justify-self:start!important;margin-left:0!important}
      .suite-unified-actions{grid-column:3!important;justify-content:flex-end!important;justify-self:end!important;margin-right:0!important}
      .suite-unified-nav a{display:inline-flex!important;align-items:center!important;min-height:40px!important;padding:7px 12px!important;border:1px solid #466b71!important;border-radius:5px!important;background:transparent!important;color:#a7e9eb!important;text-decoration:none!important;font:13px system-ui,sans-serif!important;white-space:nowrap!important}
      .suite-unified-nav a[aria-current="page"]{background:#31494f!important;border-color:#8de0e6!important;color:#fff!important}
      .suite-unified-nav a:hover{background:#2b4348!important}
      .suite-unified-status{text-align:center!important;margin:8px auto 15px!important}
      .suite-unified-status>*{display:inline-block!important}
      @media(min-width:1350px){body>.suite-unified-nav{display:flex!important;justify-content:center!important;align-items:center!important}.suite-unified-nav>.suite-unified-links{position:absolute!important;left:max(20px,1.5vw)!important;top:50%!important;transform:translateY(-50%)!important;justify-content:flex-start!important;margin:0!important}.suite-unified-nav>.suite-unified-actions{position:absolute!important;right:max(20px,1.5vw)!important;top:50%!important;transform:translateY(-50%)!important;justify-content:flex-end!important;margin:0!important}.suite-unified-nav>strong{position:relative!important;margin:0!important}}
            @media(max-width:1349px){.suite-unified-nav{display:flex!important;flex-direction:column!important;align-items:stretch!important}.suite-unified-nav>strong{align-self:center!important;white-space:normal!important}.suite-unified-nav>.suite-unified-links{align-self:stretch!important;justify-content:flex-start!important}.suite-unified-nav>.suite-unified-actions{align-self:stretch!important;justify-content:flex-end!important}}
      `;
      document.head.append(style);
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});
  else render();
})();
