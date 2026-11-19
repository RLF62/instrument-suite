const viewer=document.getElementById('viewer'),large=document.getElementById('largeImage'),caption=document.getElementById('imageCaption');
for(const button of document.querySelectorAll('[data-enlarge]'))button.addEventListener('click',()=>{const img=button.querySelector('img');large.src=img.src;large.alt=img.alt;caption.textContent=button.closest('figure').querySelector('figcaption').textContent;viewer.showModal()});
document.getElementById('closeViewer').addEventListener('click',()=>viewer.close());
viewer.addEventListener('click',event=>{if(event.target===viewer)viewer.close()});
document.getElementById('suiteLink').href=location.protocol+'//'+location.hostname+'/';
