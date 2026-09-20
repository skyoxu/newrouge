'use strict';
const el = id => document.getElementById(id);
let graphState = null;
const nodeCategory = type => {
  const groups = { 'Containers': ['Container', 'BoxContainer', 'MarginContainer', 'CenterContainer', 'GridContainer', 'FlowContainer', 'ScrollContainer', 'PanelContainer', 'SplitContainer', 'TabContainer'], 'Display': ['Label', 'RichTextLabel', 'TextureRect', 'ColorRect', 'ProgressBar', 'TextureProgressBar', 'Line2D'], 'Interaction': ['Button', 'TextureButton', 'OptionButton', 'MenuButton', 'ItemList', 'Tree', 'CodeEdit', 'Slider'], 'Dialogs and menus': ['Popup', 'Dialog', 'FileDialog', 'Window'], 'Audio and timing': ['AudioStream', 'Timer'], 'Base and layout': ['Node', 'Control', 'CanvasLayer'] };
  return Object.entries(groups).find(([, names]) => names.some(name => type === name || type.includes(name)))?.[0] || 'Other';
};
const dictionaryDescription = (path, fallback = '') => graphState?.data_dictionary?.entries?.[path]?.description || fallback;
const isImagePath = path => /\.(png|jpe?g|webp|svg|gif)$/i.test(path);
const resourceControl = path => {
  if (isImagePath(path)) {
    const wrapper = document.createElement('span'); wrapper.className = 'image-reference';
    const link = document.createElement('a'); link.textContent = path; link.target = '_blank'; link.rel = 'noopener'; link.href = `/api/knowledge/image?path=${encodeURIComponent(path)}&revision=${encodeURIComponent(graphState?.revision || '')}`; link.title = 'Open image';
    const preview = document.createElement('span'); preview.className = 'image-preview'; preview.hidden = true; const image = document.createElement('img'); image.alt = path; preview.append(image); wrapper.append(link, preview);
    const show = () => { preview.hidden = false; if (!image.src) image.src = link.href; }; wrapper.onmouseenter = show; wrapper.onmouseleave = () => { preview.hidden = true; }; link.onfocus = show; wrapper.onfocusout = () => { preview.hidden = true; }; return wrapper;
  }
  const link = document.createElement('a'); link.textContent = path; link.title = path; link.target = '_blank'; link.rel = 'noopener'; link.href = `/api/knowledge/source?path=${encodeURIComponent(path)}`; return link;
};
const referenceKind = reference => {
  const target = reference.target || '';
  const suffix = target.split('.').pop()?.toLowerCase();
  if (reference.kind === 'config-reference') return 'Configuration files';
  if (suffix === 'tscn') return 'Scene files';
  if (['gd', 'cs'].includes(suffix)) return 'Dispatched scripts';
  if (['png', 'jpg', 'jpeg', 'webp', 'svg', 'gif', 'wav', 'ogg', 'mp3'].includes(suffix)) return 'Assets';
  return 'Other referenced files';
};
const appendReferenceTree = (host, source, depth = 0, visited = new Set()) => {
  if (visited.has(source)) return;
  if (depth > 2) {
    const truncated = document.createElement('p'); truncated.className = 'scene-reference-truncated';
    truncated.textContent = 'More dependencies not expanded.'; truncated.title = source; host.append(truncated); return;
  }
  const nextVisited = new Set(visited); nextVisited.add(source);
  const references = [...(graphState.edges || []), ...(graphState.code_references || [])]
    .filter(edge => edge.source === source && edge.target)
    .reduce((map, edge) => map.set(edge.target, edge), new Map());
  if (!references.size) { const empty = document.createElement('p'); empty.textContent = 'No referenced files found'; host.append(empty); return; }
  const groups = new Map();
  for (const [target, reference] of references) { const kind = referenceKind(reference); if (!groups.has(kind)) groups.set(kind, []); groups.get(kind).push([target, reference]); }
  for (const [kind, entries] of groups) {
    const group = document.createElement('details'); group.className = kind === 'Assets' ? 'scene-script-assets' : 'scene-script-reference-group'; group.open = kind !== 'Assets';
    const summary = document.createElement('summary'); summary.textContent = `${kind} (${entries.length})`; group.append(summary);
    for (const [target, reference] of entries) {
      const item = document.createElement('p'); item.append(resourceControl(target)); item.title = target; group.append(item);
      const description = dictionaryDescription(target, '') || reference.dictionary?.description;
      if (description) { const note = document.createElement('p'); note.className = 'scene-dictionary-description'; note.textContent = `Data dictionary: ${description}`; group.append(note); }
      if (['.gd', '.cs'].includes(target.slice(target.lastIndexOf('.')).toLowerCase())) {
        const nested = document.createElement('details'); nested.className = 'scene-dispatched-script'; nested.open = true;
        const nestedSummary = document.createElement('summary'); nestedSummary.textContent = `Dispatches from ${target.split('/').pop()}`; nested.append(nestedSummary);
        appendReferenceTree(nested, target, depth + 1, nextVisited); group.append(nested);
      }
    }
    host.append(group);
  }
};
window.openScenePreview = path => {
  const scene = graphState.nodes[path] || {};
  el('scene-preview-title').textContent = path.split('/').pop();
  el('scene-preview-title').title = path;
  const body = el('scene-preview-body'); body.replaceChildren();
  const p = document.createElement('p'); p.textContent = `${scene.description || 'Godot scene'} · ${scene.classification || 'unknown'}`; body.append(p);
  const functional = scene.functional_summary || {};
  const sceneMeaning = document.createElement('p'); sceneMeaning.className = 'scene-dictionary-description'; sceneMeaning.textContent = `Data dictionary: ${dictionaryDescription(path, 'No dictionary description available.')}`; body.append(sceneMeaning);
  const trace = graphState?.design_trace?.[path];
  if (trace) {
    const traceDetail = document.createElement('details'); traceDetail.open = true; traceDetail.className = 'scene-design-trace';
    const traceTitle = document.createElement('summary'); traceTitle.textContent = 'Trace to design'; traceDetail.append(traceTitle);
    const note = document.createElement('p'); note.textContent = 'Navigation only. Scene/static/runtime evidence is not acceptance proof.'; traceDetail.append(note);
    const rows = [
      ['Tasks', (trace.tasks || []).map(item => item.task_id + (item.title ? ' · ' + item.title : ''))],
      ['Capabilities', trace.capabilities || []],
      ['Requirements', trace.requirements || []],
      ['GDD source blocks', trace.source_blocks || []],
      ['Evidence levels', trace.evidence_levels || []],
    ];
    for (const [label, values] of rows) {
      const line = document.createElement('p');
      line.textContent = label + ': ' + (values.length ? values.join(', ') : 'unmapped');
      traceDetail.append(line);
    }
    body.append(traceDetail);
  }
  if (functional.scripts?.length) {
    const heading = document.createElement('h3'); heading.textContent = `Attached scripts (${functional.scripts.length})`; body.append(heading);
    for (const script of functional.scripts) {
      const detail = document.createElement('details'); detail.open = true;
      const title = document.createElement('summary'); title.textContent = script; title.title = script; detail.append(title);
      const meaning = document.createElement('p'); meaning.className = 'scene-dictionary-description'; meaning.textContent = dictionaryDescription(script, 'No dictionary description available.'); detail.append(meaning);
      const content = document.createElement('div');
      appendReferenceTree(content, script);
      detail.append(content);
      body.append(detail);
    }
  }
  if (functional.functions?.length) { const detail = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = `Functions (${functional.functions.length})`; detail.append(heading); for (const name of functional.functions) { const item = document.createElement('p'); item.textContent = name; detail.append(item); const description = functional.function_descriptions?.[name]; if (description) { const note = document.createElement('p'); note.className = 'scene-dictionary-description'; note.textContent = `Data dictionary: ${description}`; detail.append(note); } } body.append(detail); }
  if (functional.events?.length) { const heading = document.createElement('h3'); heading.textContent = 'Published events'; body.append(heading); for (const event of functional.events) { const item = document.createElement('p'); item.textContent = event; body.append(item); const description = functional.event_descriptions?.[event]; if (description) { const note = document.createElement('p'); note.className = 'scene-dictionary-description'; note.textContent = `Data dictionary: ${description}`; body.append(note); } } }
  if ((scene.nodes || []).length) {
    const heading = document.createElement('h3'); heading.textContent = `Nodes (${scene.nodes.length})`; body.append(heading);
    const grouped = new Map(); for (const node of scene.nodes) { const key = nodeCategory(node.type || ''); if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(node); }
    for (const [category, categoryNodes] of grouped) {
      const group = document.createElement('details'); group.className = 'scene-node-category'; const groupTitle = document.createElement('summary'); groupTitle.textContent = `${category} (${categoryNodes.length})`; group.append(groupTitle); body.append(group);
      for (const node of categoryNodes) {
      const detail = document.createElement('details'); const title = document.createElement('summary');
      title.textContent = `${node.parent || '.'}/${node.name || '(unnamed)'} (${node.type || 'inherited'})`; detail.append(title);
      const nodeKey = `${path}::${node.parent || '.'}/${node.name || '(unnamed)'}`; const nodeMeaning = document.createElement('p'); nodeMeaning.className = 'scene-dictionary-description'; nodeMeaning.textContent = dictionaryDescription(nodeKey, 'No dictionary description available.'); detail.append(nodeMeaning);
      const lines = [];
      if (node.instance) lines.push(`Instanced scene: ${node.instance}`);
      if (node.resources?.length) {
        const resources = [...new Set(node.resources)];
        const resourceHeading = document.createElement('p'); resourceHeading.textContent = 'Resources:'; detail.append(resourceHeading);
        for (const resource of resources) {
          const item = document.createElement('p'); item.append(resourceControl(resource)); item.title = resource; detail.append(item);
          const resourceDescription = dictionaryDescription(resource, '');
          if (resourceDescription) { const note = document.createElement('p'); note.className = 'scene-dictionary-description'; note.textContent = `Data dictionary: ${resourceDescription}`; detail.append(note); }
        }
      }
      if (node.parse_error) lines.push(`Parse issue: ${node.parse_error}`);
      if (lines.length) { const content = document.createElement('p'); content.textContent = lines.join(' · '); detail.append(content); }
      group.append(detail);
      }
    }
  }
  const jumps = (graphState.edges || []).filter(edge => ['script-reference', 'event-route'].includes(edge.kind) && edge.source === path);
  if (jumps.length) { const heading = document.createElement('h3'); heading.textContent = 'Scenes referenced by attached scripts'; body.append(heading); for (const edge of jumps) { const item = document.createElement('p'); item.className = edge.evidence_level === 'effective' ? 'scene-evidence-effective' : 'scene-evidence-possible'; item.title = edge.evidence || ''; item.textContent = `${edge.target.split('/').pop()} · ${edge.evidence_level === 'effective' ? 'effective' : 'possible'} · line ${edge.line}`; body.append(item); } }
  if (scene.knowledge_context?.length) { const heading = document.createElement('h3'); heading.textContent = 'Knowledge base tasks'; body.append(heading); const verified = scene.knowledge_context.filter(entry => entry.level === 'verified'); const candidates = scene.knowledge_context.filter(entry => entry.level !== 'verified'); for (const entry of [...verified, ...candidates.slice(0, 10)]) { const item = document.createElement('p'); item.className = entry.level === 'verified' ? 'scene-evidence-effective' : 'scene-evidence-possible'; item.textContent = `Task ${entry.task_id}: ${entry.title} · ${entry.status} · ${entry.level}`; item.title = entry.witness || entry.source || entry.evidence || ''; body.append(item); } if (candidates.length > 10) { const note = document.createElement('p'); note.textContent = `${candidates.length - 10} additional candidate task links are hidden.`; body.append(note); } }
  el('scene-preview').showModal();
};
async function loadGraph() {
  const response = await fetch('/api/knowledge/scene-graph'); graphState = await response.json(); if (!response.ok) throw new Error(graphState.reason || 'Unable to load scene graph');
  const nodes = graphState.nodes || {}; const edges = graphState.edges || []; const box = el('scene-graph'); box.replaceChildren();
  if (!graphState.main_scene || !nodes[graphState.main_scene]) { box.textContent = 'No configured main scene is available.'; return; }
  const nodePaths = new Map(); let sequence = 0; const stack = new Set(); const expanded = new Set();
  const related = path => edges.filter(item => item.source === path && nodes[item.target]).sort((left, right) => { const rank = edge => edge.kind === 'packed_scene' ? 0 : edge.evidence_level === 'effective' ? 1 : 2; return rank(left) - rank(right) || left.target.localeCompare(right.target); });
  const build = (path, level = 'effective') => { const htmlId = `scene-node-${sequence++}`; nodePaths.set(htmlId, path); if (stack.has(path)) return { text: { name: `${path.split('/').pop()} (cycle)` }, HTMLclass: 'shared', HTMLid: htmlId }; if (expanded.has(path)) return { text: { name: `${path.split('/').pop()} (shared reference)` }, HTMLclass: 'shared', HTMLid: htmlId }; stack.add(path); expanded.add(path); const children = []; const childPaths = new Set(); for (const edge of related(path)) { const child = edge.target; if (!childPaths.has(child)) { childPaths.add(child); children.push(build(child, edge.evidence_level === 'effective' ? 'effective' : 'possible')); } } stack.delete(path); return { text: { name: path.split('/').pop() }, HTMLclass: level, HTMLid: htmlId, children }; };
  new Treant({ chart: { container: '#scene-graph', rootOrientation: 'NORTH', levelSeparation: 55, siblingSeparation: 35, subTeeSeparation: 45, connectors: { type: 'step', style: { 'stroke-width': 2, stroke: '#7aaeb5' } } }, nodeStructure: build(graphState.main_scene) });
  nodePaths.forEach((path, htmlId) => { const node = box.querySelector(`#${htmlId}`); if (node) { node.title = path; node.dataset.scenePath = path; node.setAttribute('aria-label', path); node.tabIndex = 0; node.addEventListener('click', () => window.openScenePreview(path)); node.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); window.openScenePreview(path); } }); } });
  el('scene-status').textContent = `${Object.keys(nodes).length} scenes · ${Object.values(nodes).filter(n => n.classification === 'confirmed-reachable').length} confirmed reachable · Treant tree layout · revision ${graphState.revision || 'snapshot'}`;
  if (structureButton.getAttribute('aria-pressed') === 'true') renderStructure();
}
el('scene-graph-refresh').onclick = () => loadGraph().catch(error => { el('scene-status').textContent = error.message; });
el('scene-probe').onclick = async () => { el('scene-status').textContent = 'Restarting deterministic probe...'; const session = await (await fetch('/api/knowledge/session')).json(); const response = await fetch('/api/knowledge/scan', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Origin': location.origin, 'X-Project-Health-Token': session.token }, body: '{}' }); if (!response.ok) throw new Error('Probe failed'); await loadGraph(); };
loadGraph().catch(error => { el('scene-status').textContent = error.message; });

const graphHost = el('scene-graph');
const structureHost = document.createElement('div'); structureHost.id = 'scene-structure'; structureHost.hidden = true; graphHost.parentNode.insertBefore(structureHost, graphHost.nextSibling);
const structureToolbar = document.createElement('div'); structureToolbar.className = 'scene-composition-toolbar'; structureToolbar.hidden = true;
const includeUnreachable = document.createElement('input'); includeUnreachable.type='checkbox'; includeUnreachable.id='include-unreachable';
const includeUnreachableLabel = document.createElement('label'); includeUnreachableLabel.htmlFor='include-unreachable'; includeUnreachableLabel.textContent=' Include resources not found by route tree';
const includeUnreachableHelp = document.createElement('span'); includeUnreachableHelp.className='field-help'; includeUnreachableHelp.textContent='Include resources outside the route tree.';
const structureType = document.createElement('select'); structureType.setAttribute('aria-label', 'Resource type');
[['scene','Scenes'],['script','Scripts'],['config','Configuration files'],['image','Images'],['audio','Audio'],['other','Other assets'],['all','All resources']].forEach(([value,label]) => { const option=document.createElement('option'); option.value=value; option.textContent=label; structureType.append(option); });
const firstPage = document.createElement('button'); firstPage.type='button'; firstPage.textContent='First';
const previousPage = document.createElement('button'); previousPage.type='button'; previousPage.textContent='Previous';
const nextPage = document.createElement('button'); nextPage.type='button'; nextPage.textContent='Next';
const lastPage = document.createElement('button'); lastPage.type='button'; lastPage.textContent='Last';
const pageInput = document.createElement('input'); pageInput.type='number'; pageInput.min='1'; pageInput.value='1'; pageInput.setAttribute('aria-label','Page number'); pageInput.style.width='5em';
const pageInfo = document.createElement('span'); pageInfo.className='scene-composition-page-info';
structureToolbar.append(structureType, includeUnreachable, includeUnreachableLabel, includeUnreachableHelp, firstPage, previousPage, pageInput, nextPage, lastPage, pageInfo); structureHost.parentNode.insertBefore(structureToolbar, structureHost);
structureToolbar.style.display='none'; structureToolbar.style.alignItems='center'; structureToolbar.style.flexWrap='nowrap'; structureToolbar.style.gap='8px'; structureToolbar.style.overflowX='auto'; structureToolbar.style.whiteSpace='nowrap';
includeUnreachableLabel.style.margin='0'; includeUnreachableHelp.style.marginRight='12px';
let structurePage = 1; const structurePageSize = 20;
const graphButton = document.createElement('button'); graphButton.type = 'button'; graphButton.textContent = 'Scene route tree'; graphButton.setAttribute('aria-pressed', 'true');
const structureButton = document.createElement('button'); structureButton.type = 'button'; structureButton.textContent = 'Scene composition'; structureButton.setAttribute('aria-pressed', 'false');
el('scene-graph-refresh').parentNode.insertBefore(structureButton, el('scene-graph-refresh')); el('scene-graph-refresh').parentNode.insertBefore(graphButton, structureButton);
function compositionResources() {
  const resources = new Map(); const add = (path, type, meta={}) => {
    if (!path || /^SubResource\(/.test(path) || /^ExtResource\(/.test(path)) return;
    const existing=resources.get(path); const mergedTasks=[...(existing?.tasks || []), ...(meta.tasks || [])];
    const origins = [...(existing?.origins || []), ...(meta.origins || [])];
    resources.set(path, {...existing, path, type: existing?.type || type, ...meta, origins: [...new Set(origins)], tasks: [...new Map(mergedTasks.map(task => [task.id + ':' + (task.relation || ''), task])).values()]});
  };
  const dictionary = graphState?.data_dictionary?.entries || {};
  const taskByPath = new Map();
  for (const [script, links] of Object.entries(graphState?.script_task_context || {})) {
    taskByPath.set(script, links.map(link => ({id: String(link.task_id), relation: link.relation, level: link.level, scene: link.scene})));
  }
  for (const scene of Object.values(graphState?.nodes || {})) for (const entry of scene.knowledge_context || []) {
    if (entry.task_id) taskByPath.set(scene.path, [...(taskByPath.get(scene.path) || []), {id: String(entry.task_id), relation: 'direct-scene', level: entry.level}]);
  }
  const routeTreeScenes = new Set();
  const nodes = graphState?.nodes || {};
  const pendingScenes = graphState?.main_scene && nodes[graphState.main_scene] ? [graphState.main_scene] : [];
  const edgesBySource = new Map();
  for (const edge of graphState?.edges || []) {
    if (!edge.source || !edge.target || !nodes[edge.target]) continue;
    if (!edgesBySource.has(edge.source)) edgesBySource.set(edge.source, []);
    edgesBySource.get(edge.source).push(edge.target);
  }
  while (pendingScenes.length) {
    const scenePath = pendingScenes.pop();
    if (routeTreeScenes.has(scenePath)) continue;
    routeTreeScenes.add(scenePath);
    for (const target of edgesBySource.get(scenePath) || []) pendingScenes.push(target);
  }
  for (const scene of Object.values(graphState?.nodes || {})) {
    if (!includeUnreachable.checked && !routeTreeScenes.has(scene.path)) continue;
    add(scene.path, 'scene', {nodes: scene.nodes?.length || 0, scripts: scene.functional_summary?.scripts?.length || 0, tasks: taskByPath.get(scene.path) || [], origins: [routeTreeScenes.has(scene.path) ? 'route tree' : 'unreachable candidate']});
    for (const script of scene.functional_summary?.scripts || []) add(script, 'script', {tasks: taskByPath.get(scene.path) || [], origins: ['attached to scene']});
    for (const config of scene.functional_summary?.config_references || []) add(config, 'config', {tasks: taskByPath.get(scene.path) || [], origins: ['scene script reference']});
    for (const node of scene.nodes || []) for (const resource of node.resources || []) {
      const suffix=resource.split('.').pop()?.toLowerCase(); const type=['png','jpg','jpeg','webp','svg','gif'].includes(suffix)?'image':['wav','ogg','mp3'].includes(suffix)?'audio':['json','csv','cfg','ini','yaml','yml','tres','res'].includes(suffix)?'config':'other'; add(resource,type,{tasks: taskByPath.get(scene.path) || [], origins: ['node resource']});
    }
  }
  // Build a bounded dependency closure from scripts attached to route-reachable
  // scenes. This preserves indirect config/assets referenced by dispatched code.
  const referencesBySource = new Map();
  for (const ref of graphState?.code_references || []) {
    if (!ref.source || !ref.target) continue;
    if (!referencesBySource.has(ref.source)) referencesBySource.set(ref.source, []);
    referencesBySource.get(ref.source).push(ref);
  }
  const pending = [...resources.values()].filter(item => item.type === 'script').map(item => item.path);
  const visitedSources = new Set();
  while (pending.length) {
    const source = pending.shift(); if (visitedSources.has(source)) continue; visitedSources.add(source);
    for (const ref of referencesBySource.get(source) || []) {
      const suffix=ref.target.split('.').pop()?.toLowerCase();
      const type=['gd','cs'].includes(suffix)?'script':['json','csv','cfg','ini','yaml','yml','tres','res'].includes(suffix)?'config':['png','jpg','jpeg','webp','svg','gif'].includes(suffix)?'image':['wav','ogg','mp3'].includes(suffix)?'audio':'other';
      add(ref.target,type,{origins: [ref.classification === 'dynamic-candidate' ? 'dynamic candidate' : 'script reference']});
      if (type === 'script') pending.push(ref.target);
    }
  }
  const reachableFiles = new Set(resources.keys());
  for (const path of graphState?.file_manifest || []) {
    const suffix=path.split('.').pop()?.toLowerCase();
    const type=suffix==='tscn'?'scene':['gd','cs'].includes(suffix)?'script':['json','csv','cfg','ini','yaml','yml','tres','res'].includes(suffix)?'config':['png','jpg','jpeg','webp','svg','gif'].includes(suffix)?'image':['wav','ogg','mp3'].includes(suffix)?'audio':'other';
    if (['scene','script','config','image','audio','other'].includes(type) && !/[{}]/.test(path) && !/log/i.test(path) && (includeUnreachable.checked || reachableFiles.has(path))) add(path,type,{origins: ['file manifest']});
  }
  for (const item of resources.values()) {
    item.tasks = item.tasks || taskByPath.get(item.path) || [];
    item.description = dictionary[item.path]?.description || `Indexed ${item.type} resource ${item.path.split('/').pop()}; available from the local project snapshot.`;
    item.confidence = item.origins?.includes('route tree') ? 'confirmed' : item.origins?.includes('dynamic candidate') ? 'candidate' : item.origins?.includes('file manifest') ? 'unconfirmed' : 'inferred';
  }
  return [...resources.values()].sort((a,b)=>a.path.localeCompare(b.path));
}
function renderStructure() {
  const all=compositionResources(); const type=structureType.value; const filtered=type==='all'?all:all.filter(item=>item.type===type); const pages=Math.max(1,Math.ceil(filtered.length/structurePageSize)); structurePage=Math.min(Math.max(1,structurePage),pages); pageInput.value=structurePage; pageInfo.textContent=`Page ${structurePage} / ${pages} · ${filtered.length} resources`;
  structureHost.replaceChildren(); const scroll=document.createElement('div'); scroll.className='table-scroll'; const table=document.createElement('table'); table.className='scene-composition-table'; const header=document.createElement('thead'); header.innerHTML='<tr><th>Name</th><th>Type</th><th>Details</th><th>Source</th><th>Confidence</th><th>Task IDs</th><th>Data dictionary</th></tr>'; table.append(header); const tbody=document.createElement('tbody'); const start=(structurePage-1)*structurePageSize;
  for(const item of filtered.slice(start,start+structurePageSize)){ const row=document.createElement('tr'); row.dataset.resourcePath=item.path; row.dataset.resourceType=item.type; row.title=item.path; const name=document.createElement('td'); const label=document.createElement('button'); label.type='button'; label.textContent=item.path.split('/').pop(); label.title=item.path; if(item.type==='scene') label.onclick=()=>window.openScenePreview(item.path); else if(item.type==='image') label.onclick=()=>window.open(`/api/knowledge/image?path=${encodeURIComponent(item.path)}&revision=${encodeURIComponent(graphState?.revision || '')}`,'_blank','noopener'); else label.onclick=()=>window.open(`/api/knowledge/source?path=${encodeURIComponent(item.path)}`,'_blank','noopener'); name.append(label); const kind=document.createElement('td'); kind.textContent=item.type; const meta=document.createElement('td'); meta.textContent=item.nodes ? `${item.nodes} nodes · ${item.scripts} scripts` : ''; const origin=document.createElement('td'); origin.textContent=(item.origins||[]).join(', '); const confidence=document.createElement('td'); confidence.textContent=item.confidence; const tasks=document.createElement('td'); const taskLinks=item.tasks||[]; const verified=taskLinks.filter(task=>task.level==='verified'); const candidates=taskLinks.filter(task=>task.level!=='verified'); const shown=[...verified,...candidates.slice(0,3)]; tasks.textContent=shown.map(task=>`${task.id} (${task.relation === 'scene-inherited' ? 'inherited' : task.level})`).join(', ') || '-'; if(candidates.length>3) tasks.title=`${candidates.length - 3} additional candidate task links are hidden.`; const description=document.createElement('td'); description.textContent=item.description; row.append(name,kind,meta,origin,confidence,tasks,description); tbody.append(row); }
  table.append(tbody); scroll.append(table); structureHost.append(scroll); if(!filtered.length) structureHost.textContent='No resources in this category.';
  firstPage.disabled=previousPage.disabled=structurePage<=1; nextPage.disabled=lastPage.disabled=structurePage>=pages;
}
const setView = view => { const graphVisible = view === 'graph'; graphHost.style.display = graphVisible ? '' : 'none'; structureHost.style.display = graphVisible ? 'none' : ''; structureToolbar.style.display = graphVisible ? 'none' : 'flex'; graphHost.hidden = !graphVisible; structureHost.hidden = graphVisible; graphButton.setAttribute('aria-pressed', String(graphVisible)); structureButton.setAttribute('aria-pressed', String(!graphVisible)); el('scene-status').textContent = graphVisible ? 'Scene route tree view · snapshot data' : 'Scene composition view · snapshot data'; };
structureButton.onclick = () => { structurePage=1; renderStructure(); setView('structure'); structureToolbar.hidden=false; };
graphButton.onclick = () => { structureToolbar.hidden=true; setView('graph'); };
structureType.onchange=()=>{structurePage=1;renderStructure();}; firstPage.onclick=()=>{structurePage=1;renderStructure();}; previousPage.onclick=()=>{structurePage--;renderStructure();}; nextPage.onclick=()=>{structurePage++;renderStructure();}; lastPage.onclick=()=>{structurePage=Number.MAX_SAFE_INTEGER;renderStructure();}; pageInput.onchange=()=>{structurePage=Math.max(1,Number(pageInput.value)||1);renderStructure();};
includeUnreachable.onchange=()=>{structurePage=1;renderStructure();};
