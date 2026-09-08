'use strict';
const el = id => document.getElementById(id);
const pretty = value => JSON.stringify(value, null, 2);
let token = '', currentPage = 1;
async function api(path, body) {
  const response = await fetch('/api/knowledge/' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Project-Health-Token': token}, body: JSON.stringify(body)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.reason || 'Request failed');
  return result;
}
async function run(action) {
  el('message').textContent = 'Working… main scan may take several minutes.';
  document.querySelectorAll('button').forEach(x => x.disabled = true);
  try { await action(); el('message').textContent = 'Ready. Results are bound to the displayed main snapshot.'; }
  catch(error) { el('message').textContent = error.message; }
  finally { document.querySelectorAll('button').forEach(x => x.disabled = x.dataset.disabled === 'true'); }
}
function button(text, action) { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.onclick = () => run(action); return b; }
function sourceLink(path) {
  const a = document.createElement('a'); a.href = '/api/knowledge/source?path=' + encodeURIComponent(path); a.textContent = path;
  a.onclick = event => {event.preventDefault(); run(async () => {const s = await api('source?path=' + encodeURIComponent(path)); show(path + ' @ ' + s.revision.slice(0,12), s.content);});};
  return a;
}
function show(title, body) { el('detail-title').textContent = title; el('detail-body').textContent = typeof body === 'string' ? body : pretty(body); el('detail-links').replaceChildren(); if (!el('detail').open) el('detail').showModal(); }
function pager(id, page) {
  const box = el(id); box.replaceChildren();
  for (const [label, destination] of [['First',1],['Previous',page.page-1],['Next',page.page+1],['Last',page.pages]]) {
    const b = button(label, () => loadTasks(destination));
    b.dataset.disabled = String(destination < 1 || destination > page.pages || destination === page.page); b.disabled = b.dataset.disabled === 'true'; box.append(b);
  }
  const label = document.createElement('span'); label.textContent = `Page ${page.page} / ${page.pages} · ${page.total} tasks · 20 per page`; box.append(label);
  const input = document.createElement('input'); input.type = 'number'; input.min = '1'; input.max = String(page.pages); input.value = String(page.page); input.setAttribute('aria-label','Jump to page');
  const jump = () => {const p = Number(input.value); if (!Number.isInteger(p) || p < 1 || p > page.pages) throw new Error('Page is out of range'); return loadTasks(p);};
  input.onkeydown = e => {if(e.key === 'Enter') run(jump);}; box.append(input,button('Go',jump));
}
async function loadTasks(page=1) {
  const result = await api('tasks?page=' + page); currentPage = result.page; el('tasks').replaceChildren();
  for (const task of result.items) {
    const row = document.createElement('tr');
    for (const key of ['id','title','status','dependencies','recommendedSubtasks','godot']) {
      const td = document.createElement('td');
      if (key === 'id') td.append(button(String(task.id),async () => {
        const detail = await api('task?id=' + encodeURIComponent(task.id)); show('Task ' + task.id, detail);
        for (const item of [...detail.godot.scenes, ...detail.godot.candidates]) { const p=document.createElement('p'); p.append(sourceLink(item.scene)); if(item.script) {p.append(' → ',sourceLink(item.script));} el('detail-links').append(p); }
        el('detail-links').append(button('Verify this task runtime', async()=>{await api('runtime',{task_id:task.id});await loadStatus();}));
      }));
      else if (key === 'godot') {
        const reason = task.godot.runtime_evidence?.reason;
        td.textContent = task.godot.status + (task.godot.runtime_status ? ` · ${task.godot.runtime_status}` : '') + (reason ? ` · ${reason}` : '');
      } else td.textContent = typeof task[key] === 'object' ? pretty(task[key]) : String(task[key] ?? '—');
      row.append(td);
    }
    el('tasks').append(row);
  }
  pager('pager-top',result); pager('pager-bottom',result);
}
async function loadStatus() {
  const state = await api('status'); el('revision').textContent = state.revision ? `${state.branch} @ ${state.revision} | scanned ${state.scanned_at}` : 'No successful local scan yet.';
  el('publication').textContent = `Published KCP pointer matches scan: ${state.publication.matches_scan}. ${state.publication.note}`;
  if (!el('config').value.trim()) el('config').value = pretty(await api('config')); el('summary').replaceChildren();
  for(const [key,value] of Object.entries({total:state.summary.total,...state.summary.statuses,...state.summary.godot})) {const d=document.createElement('div');d.className='metric';d.textContent=key+': '+value;el('summary').append(d);}
  el('gdds').replaceChildren();
  for(const file of state.gdd_files) {const p=document.createElement('p'); if(file.available) p.append(sourceLink(file.path)); else p.textContent=file.path+' — missing or unsupported at main';el('gdds').append(p);}
  await loadTasks(currentPage);
}
async function search(target) {
  const result = await api('query',{query:el('query').value,consumer:el('consumer').value,...(target ? {target} : {})});
  el('results').hidden=false; el('queries').textContent='Executed queries: '+result.queries.join(' | ');
  el('knowledge').replaceChildren(); for(const hit of result.knowledge) {const p=document.createElement('p');p.append(sourceLink(hit.path),` · line ${hit.line_start} · ${hit.matched_query}`);el('knowledge').append(p);}
  el('supplements').replaceChildren();for(const hit of result.gdd_supplements) el('supplements').append(sourceLink(hit.path));
  el('targets').replaceChildren();el('target-count').textContent=`${result.impact_target_total} candidate targets; showing at most 80. ${result.impact_skipped_methods.length} unsupported method signatures omitted (details in evidence JSON). Narrow the query if needed. Select one to analyze.`;
  for(const hit of result.impact_targets) el('targets').append(button(hit.type+' · '+hit.id,()=>search({type:hit.type,id:hit.id})));
  el('preview').textContent=pretty(result);
}
el('close-detail').onclick=()=>el('detail').close();
el('scan').onclick=()=>run(async()=>{const config=JSON.parse(el('config').value);await api('config',config);await api('scan',{});currentPage=1;await loadStatus();});
el('runtime').onclick=()=>run(async()=>{await api('runtime',{});await loadStatus();});
el('save-config').onclick=()=>run(async()=>{await api('config',JSON.parse(el('config').value));el('publication').textContent='Configuration saved. Scan main to apply it; displayed results still use the previous configuration.';});
el('query-form').onsubmit=e=>{e.preventDefault();run(()=>search());};
run(async()=>{token=(await api('session')).token;await loadStatus();});
