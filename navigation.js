/* Rebuild only cross-instrument links; retain view, documentation and layout controls. */
(function () {
  function render() {
    const cfg = window.fischerSuite;
    const nav = document.querySelector('nav[aria-label="Instrument navigation"], .suite-topbar');
    if (!cfg || !nav) return;
    if(cfg.current==='auto') cfg.current=nav.matches('nav[aria-label="Instrument navigation"]')?'meter':'supply';
    // Cached Classic templates can adopt the reviewed CSS without a controller restart.
    if(document.head && cfg.current==='supply' && document.getElementById('classic-layout-grid') && !document.getElementById('classic-mobile-width-stylesheet')){
      const style=document.createElement('link');style.id='classic-mobile-width-stylesheet';
      style.rel='stylesheet';style.href='/static/classic-mobile-fix.css?v=1';document.head.append(style);
    }

    nav.querySelectorAll('a').forEach(a => {
      const u = new URL(a.href, location.href);
      if (a.id === 'suiteLink' || /Tektronix|HP supply|HP 6033A|HP 34401A/i.test(a.textContent) ||
          (cfg.current !== 'meter' && u.pathname.startsWith('/multimeter/'))) a.remove();
    });
    nav.querySelectorAll('.suite-tool-links').forEach(g => { if (!g.children.length) g.remove(); });
    const host = location.hostname;
    const origin = (port, protocol=location.protocol) => protocol+'//'+host+(port?':'+port:'');
    const targets = {
      meter: ['HP 34401A', (cfg.meterPort ? origin(cfg.meterPort,'http:') : cfg.current==='scope'?origin(cfg.basePort):location.origin)+'/multimeter/classic'],
      supply: ['HP 6033A', (cfg.basePort ? origin(cfg.basePort) : origin(null))+'/'],
      scope: ['Tektronix', origin(8081,'http:')+'/']
    };
    const group = document.createElement('div'); group.className='suite-tool-links';
    group.setAttribute('aria-label','Other installed instruments');
    cfg.instruments.filter(k=>k!==cfg.current).forEach(k=>{
      if (!targets[k]) return;
      const a=document.createElement('a'); a.className='suite-tool-link';
      const record=cfg.records?.[k];
      a.textContent=targets[k][0];
      a.href=record?origin(record.port,record.scheme+':')+(k==='meter'?'/multimeter/classic':'/'):targets[k][1];
      group.append(a);
    });
    const add=document.createElement('a');add.className='suite-tool-link';add.textContent='Add instruments';add.href='/api/suite/manager';group.append(add);
    if (cfg.firmwareUpdater) {
      const firmware = document.createElement('a');
      firmware.className = 'suite-tool-link';
      firmware.textContent = 'USB-GPIB Firmware';
      firmware.href = '/gpib-firmware';
      group.append(firmware);
    }
    if(cfg.current==='meter') nav.prepend(group); // Keep the title in the middle grid column even when meter-only.
    else if(group.children.length) nav.append(group);
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',render,{once:true});
  else render();
})();
