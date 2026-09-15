'use strict';
async function load(){
  const response=await fetch('/api/knowledge/godot/unreachable');
  const data=await response.json();
  if(!response.ok) throw new Error(data.reason||'Unable to load scenes');
  const items=data.items||[];
  document.getElementById('status').textContent=`${items.length} scenes · revision ${data.revision||'unknown'}`;
  const box=document.getElementById('scene-list'); const filter=document.getElementById('scene-filter');
  const render=()=>{box.replaceChildren(); const selected=filter.value;
    const shown=items.filter(item=>selected==='all'||(selected==='parse-error'&&item.parse_error)||(selected==='with-scripts'&&Object.values(item.external_resources||{}).some(path=>/\.(cs|gd)$/.test(path))));
    shown.forEach(item=>{const row=document.createElement('details');row.className='scene-tree-row';const summary=document.createElement('summary');const link=document.createElement('a');link.href='/knowledge/?scene='+encodeURIComponent(item.path);link.textContent=item.path;link.title=item.description||'Static Godot scene';summary.append(link);row.append(summary);const root=(item.nodes||[])[0];const meta=document.createElement('p');meta.textContent=`${item.classification||'unknown'} · ${root?root.type:'no root'} · ${(item.nodes||[]).length} nodes${item.parse_error?' · '+item.parse_error:''}`;row.append(meta);const scripts=Object.values(item.external_resources||{}).filter(path=>/\.(cs|gd)$/.test(path));if(scripts.length){const p=document.createElement('p');p.textContent='Scripts: '+scripts.join(', ');row.append(p)}box.append(row)});
    if(!shown.length) box.textContent='No matching unconfirmed scenes.';
  }; filter.addEventListener('change',render); render();
}
load().catch(error=>document.getElementById('status').textContent=error.message);
