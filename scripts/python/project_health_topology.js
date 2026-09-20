'use strict';
const byId = id => document.getElementById(id);
let topology = null;

function endpoint(edge, side) {
  const nested = edge && edge[side];
  if (nested && typeof nested === 'object') return {kind: nested.type || nested.kind || '', id: nested.id};
  return {
    kind: (edge && (edge[side + '_type'] || edge[side + '_kind'])) || '',
    id: edge && (edge[side + '_id'] !== undefined ? edge[side + '_id'] : edge[side])
  };
}

function nodeRows(state) {
  const nodes = (state && state.nodes) || {};
  return []
    .concat((nodes.source_blocks || []).map(x => Object.assign({kind: 'source_block'}, x)))
    .concat((nodes.requirements || []).map(x => Object.assign({kind: 'requirement'}, x)))
    .concat((nodes.capabilities || []).map(x => Object.assign({kind: 'capability'}, x)))
    .concat((nodes.tasks || []).map(x => Object.assign({kind: 'task'}, x)));
}

function nodeId(row) {
  return row.block_id || row.source_block_id || row.requirement_id || row.semantic_id ||
    row.capability_id || row.task_id || row.taskmaster_id || row.id || '(unnamed)';
}

function matches(row) {
  const kind = byId('filter-kind').value;
  const state = byId('filter-state').value.toLowerCase();
  const taskStatus = byId('filter-task-status').value.toLowerCase();
  const capability = byId('filter-capability').value.toLowerCase();
  const chapter = byId('filter-chapter').value.toLowerCase();
  const source = byId('filter-source').value.toLowerCase();
  if (kind && row.kind !== kind) return false;
  const blob = JSON.stringify(row).toLowerCase();
  if (taskStatus && String(row.status || '').toLowerCase() !== taskStatus) return false;
  if (capability && !blob.includes(capability)) return false;
  if (chapter && !blob.includes(chapter)) return false;
  if (source && !blob.includes(source)) return false;
  if (state === 'unresolved' && !blob.includes('unresolved')) return false;
  if (state === 'stale' && topology && topology.fresh !== false && !blob.includes('stale')) return false;
  if (state === 'orphan') {
    const id = nodeId(row);
    const linked = (topology.edges || []).some(e => endpoint(e, 'source').id == id || endpoint(e, 'target').id == id);
    if (linked) return false;
  }
  return true;
}

async function openSource(row) {
  if (!topology || topology.identity?.kind !== 'main') return;
  const path = row.source_path;
  const response = await fetch('/api/knowledge/source?path=' + encodeURIComponent(path), {cache: 'no-store'});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.reason || 'Source request failed');
  if (payload.revision !== topology.identity.revision) throw new Error('Source snapshot changed; refresh topology before reading source.');
  const start = Number(row.start_line || row.line_start || row.line || 1);
  const end = Number(row.end_line || row.line_end || start);
  const lines = String(payload.content || '').split(/\r?\n/);
  byId('topology-source-title').textContent = path + ':' + start + '-' + end;
  byId('topology-source-body').textContent = lines.slice(Math.max(0, start - 1), Math.max(start, end)).join('\n');
  byId('topology-source-preview').showModal();
}

function addNodeActions(detail, row) {
  if (row.kind === 'source_block' && row.source_path) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = topology?.identity?.kind === 'main' ? 'Open source at this revision' : 'Workspace source preview unavailable';
    button.disabled = topology?.identity?.kind !== 'main';
    button.onclick = () => openSource(row).catch(error => byId('topology-status').textContent = error.message);
    detail.append(button);
  }
  if (row.kind === 'task' && nodeId(row) !== '(unnamed)') {
    const link = document.createElement('a');
    link.href = '/api/knowledge/task?id=' + encodeURIComponent(nodeId(row));
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Open existing task detail';
    detail.append(link);
  }
}

function render() {
  const status = byId('topology-status');
  const host = byId('topology-nodes');
  const summary = byId('topology-summary');
  const edgeBody = byId('topology-edge-body');
  host.replaceChildren();
  summary.replaceChildren();
  edgeBody.replaceChildren();
  const identity = (topology && topology.identity) || {};
  if (topology && topology.available) {
    status.textContent = (identity.kind || 'unknown') + ' · ' + (identity.revision || 'no revision') + ' · ' + (topology.status || '');
  } else {
    status.textContent = (identity.kind || 'unknown') + ' · ' + ((topology && topology.reason) || 'topology unavailable');
  }
  Object.entries((topology && topology.summary) || {}).forEach(([key, value]) => {
    const card = document.createElement('span');
    card.className = 'metric';
    card.textContent = key + ': ' + value;
    summary.append(card);
  });
  nodeRows(topology).filter(matches).forEach(row => {
    const detail = document.createElement('details');
    const title = document.createElement('summary');
    title.textContent = row.kind + ' · ' + nodeId(row);
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(row, null, 2);
    detail.append(title, pre);
    addNodeActions(detail, row);
    host.append(detail);
  });
  if (!host.children.length) {
    const p = document.createElement('p');
    p.textContent = topology && topology.available ? 'No nodes match the filters.' : 'No topology artifacts are available for this identity.';
    host.append(p);
  }
  ((topology && topology.edges) || []).forEach(edge => {
    const a = endpoint(edge, 'source');
    const b = endpoint(edge, 'target');
    const tr = document.createElement('tr');
    [a.kind + ':' + a.id, edge.relation || edge.type || '', b.kind + ':' + b.id].forEach(value => {
      const td = document.createElement('td');
      td.textContent = String(value == null ? '' : value);
      tr.append(td);
    });
    edgeBody.append(tr);
  });
  byId('topology-problems').textContent = JSON.stringify((topology && topology.problems) || [], null, 2);
}

async function load() {
  const mode = byId('topology-identity').value;
  const response = await fetch('/api/knowledge/topology?mode=' + encodeURIComponent(mode), {cache: 'no-store'});
  topology = await response.json();
  if (!response.ok) throw new Error(topology.reason || 'Topology request failed');
  render();
}

['filter-kind','filter-state','filter-task-status','filter-capability','filter-chapter','filter-source']
  .forEach(id => byId(id).addEventListener('input', render));
byId('topology-identity').addEventListener('change', () => load().catch(e => byId('topology-status').textContent = e.message));
byId('topology-refresh').onclick = () => load().catch(e => byId('topology-status').textContent = e.message);
load().catch(e => byId('topology-status').textContent = e.message);
