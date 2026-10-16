'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../../..');
const source = name => fs.readFileSync(path.join(root, 'scripts/python', name), 'utf8');

class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.listeners = {};
    this.disabled = false; this._value = ''; this.textContent = ''; this.attributes = {}; this.style = {};
    this.classList = {add() {}};
  }
  get value() { return this._value || (this.tag === 'select' ? this.children[0]?.value || '' : ''); }
  set value(value) { this._value = value; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._value = ''; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  insertAdjacentHTML() {}
  closest() { return null; }
  showModal() { this.open = true; }
  scrollIntoView() {}
}

function harness(fetch) {
  const controls = {};
  const context = {document: {
    querySelector() { return null; },
    getElementById(id) { return controls[id] ||= new Element(id.includes('select') ? 'select' : 'div'); },
    createElement: tag => new Element(tag), createTextNode: text => ({textContent: text}),
  }, window: {location: {search: '', pathname: '/knowledge/topology'},
    setInterval(callback) { this.interval = callback; return 1; }, clearInterval() {}, addEventListener() {}},
  history: {replaceState(_state, _title, url) { context.window.location.search = url.slice(url.indexOf('?')); }},
  URLSearchParams, fetch, setTimeout: callback => callback()};
  vm.createContext(context);
  vm.runInContext(source('project_health_planning.js'), context);
  return {context, controls};
}
const response = (payload, code = 200) => ({ok: code < 400, status: code, json: async () => payload});
const completed = {job_id: 'fixture', status: 'completed', revision: 'a'.repeat(40),
  message: 'Capability generated: 2 capabilities · main aaaaaaaaaaaa · local planning result'};
const settle = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };

async function compactResults() {
  const calls = []; let poll = 0;
  const {context} = harness(async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/session')) return response({token: 'verified'});
    if (options?.method === 'POST') return response({...completed, status: 'queued', stage: 'prepare'}, 202);
    return response(poll++ ? completed : {...completed, status: 'running', stage: 'review'});
  });
  const button = new Element('button'), status = new Element(); let refreshed = 0;
  await context.window.knowledgePlanning({action: 'capability', button, status, refresh: async () => {
    assert.equal(button.disabled, true); status.textContent = 'Load would overwrite status'; refreshed++;
  }});
  assert.equal(refreshed, 1); assert.equal(button.disabled, false);
  assert.equal(status.textContent, completed.message); assert.equal(status.dataset.result, 'success');
  assert.equal(calls[1][1].headers['X-Project-Health-Token'], 'verified');
  assert.equal(JSON.parse(calls[1][1].body).action, 'capability');
  assert.equal(poll, 2);
  context.fetch = async url => response(url.endsWith('/session') ? {token: 'verified'} : {
    status: 'failed', message: 'Chapter 5 is not ready\n' + 'detail '.repeat(1000),
  });
  await context.window.knowledgePlanning({action: 'mvg', button, status, refresh: async () => refreshed++});
  assert.equal(refreshed, 1); assert.equal(status.dataset.result, 'failed');
  assert.ok(status.textContent.startsWith('Chapter 5 is not ready '));
  assert.ok(status.textContent.length <= 360); assert.equal(status.textContent.includes('\n'), false);
  context.fetch = async url => response(url.endsWith('/session') ? {token: 'verified'} : completed);
  await context.window.knowledgePlanning({action: 'capability', button, status, refresh: async () => { throw Error('stale revision'); }});
  assert.ok(status.textContent.includes('Data refresh failed: stale revision'));
  assert.equal(status.dataset.result, 'failed'); assert.equal(button.disabled, false);
  context.fetch = async url => response(url.endsWith('/session') ? {token: 'verified'} : {reason: 'Another operation is running'}, url.endsWith('/session') ? 200 : 409);
  await context.window.knowledgePlanning({action: 'capability', button, status, refresh: async () => refreshed++});
  assert.equal(status.textContent, 'Another operation is running'); assert.equal(refreshed, 1);
}

async function topologyButton() {
  const generated = {available: true, fresh: true, planning_result: true, planning_job_id: 'fixture',
    identity: {kind: 'main', revision: completed.revision}, summary: {}, edges: [], nodes: {
      capabilities: [{capability_id: 'CAP-NEW-1'}, {capability_id: 'CAP-NEW-2'}],
      source_blocks: [{source_path: 'docs/gdd/relay.md'}],
  }};
  const calls = [];
  const {context, controls} = harness(async (url, options) => {
    calls.push(url);
    if (url.endsWith('/session')) return response({token: 'verified'});
    if (options?.method === 'POST') return response(completed);
    if (url.startsWith('/api/knowledge/planning-source')) return response({revision: completed.revision, content: 'Committed source'});
    return response(generated);
  });
  vm.runInContext(source('project_health_topology.js').replace(/^load\(\)\.catch.*$/m, ''), context);
  context.window.location.search = '?mode=workspace&view=attempt';
  controls['topology-identity'].value = 'workspace'; controls['filter-state'].value = 'orphan';
  controls['filter-source'].value = 'old source';
  await controls['capability-generate'].onclick();
  assert.equal(controls['topology-identity'].value, 'main');
  assert.equal(controls['filter-kind'].value, 'capability');
  assert.equal(controls['filter-state'].value, ''); assert.equal(controls['filter-source'].value, '');
  assert.equal(controls['topology-nodes'].children.length, 2);
  assert.equal(controls['topology-status'].dataset.result, 'success');
  assert.equal(controls['topology-status'].textContent, completed.message);
  controls['filter-kind'].listeners.input();
  assert.equal(controls['topology-status'].textContent, completed.message);
  await context.openSource({source_path: 'docs/gdd/relay.md'});
  assert.ok(calls.some(url => url.startsWith('/api/knowledge/planning-source?job_id=fixture')));
  assert.equal(controls['topology-source-body'].textContent, 'Committed source');
}

async function mvgButton() {
  let generated = false; let request;
  const manifest = {path: 'docs/testing/mvg/m1-full.json', mvg_id: 'm1-full', coverage: {},
    evidence: {status: 'not_verified'}, sha256: 'fixture', tests: [], flows: []};
  const {context, controls} = harness(async (url, options) => {
    if (url.endsWith('/session')) return response({token: 'verified'});
    if (options?.method === 'POST') {
      request = JSON.parse(options.body); generated = true;
      return response({...completed, message: 'MVG generated: 1 flow · local planning result'});
    }
    return response({revision: completed.revision, versions: [], topology_fresh: true, manifests: [{...manifest,
      planning_result: generated, flows: generated ? [{id: 'new-flow', task_ids: [7, 42], version_ids: [], test_ids: [], handoffs: []}] : []}]});
  });
  vm.runInContext(source('project_health_mvg_versions.js'), context);
  await settle();
  assert.equal(controls['mvg-run'].disabled, false);
  await controls['mvg-generate'].listeners.click();
  assert.equal(request.action, 'mvg'); assert.equal(request.manifest, manifest.path);
  assert.equal(controls['mvg-manifest-select'].value, manifest.path);
  assert.equal(controls['mvg-run'].disabled, true);
  assert.equal(controls['scene-status'].dataset.result, 'success');
  assert.equal(controls['scene-status'].textContent, 'MVG generated: 1 flow · local planning result');
  const flow = controls['mvg-flow-detail'].children.find(node => node.tag === 'details');
  assert.ok(flow.children[0].textContent.includes('new-flow'));
  assert.equal(controls['mvg-generate'].disabled, false); assert.equal(controls['mvg-manifest-select'].disabled, false);
}

async function slowCommittedProgressAndClear() {
  let finishProgress; let progressCalls = 0;
  const {context, controls} = harness(async (url, options) => {
    if (url.endsWith('/mvg-progress')) {
      progressCalls++;
      return new Promise(resolve => { finishProgress = resolve; });
    }
    if (url.endsWith('/session')) return response({token: 'verified'});
    if (options?.method === 'POST') return response({epoch: 1, completed: 0});
    return response({revision: completed.revision, versions: [], manifests: []});
  });
  vm.runInContext(source('project_health_mvg_versions.js'), context);
  await settle();
  context.window.interval(); context.window.interval();
  assert.equal(progressCalls, 1, 'Slow verification must stay single-flight');
  finishProgress(response({epoch: 0, completed: 1, total: 2, status: 'partial_planning',
    items: [{capability_id: 'CAP-a', provenance: 'new'}]}));
  await settle();
  assert.ok(controls['mvg-progress-status'].textContent.startsWith('1/2'));
  assert.equal(controls['mvg-progress-items'].children.length, 1);
  context.window.interval();
  await settle();
  const clear = controls['mvg-clear'].listeners.click();
  await settle();
  finishProgress(response({epoch: 0, completed: 1, total: 2, status: 'partial_planning',
    items: [{capability_id: 'CAP-old', provenance: 'new'}]}));
  await clear; await settle();
  assert.ok(controls['mvg-progress-status'].textContent.startsWith('0 completed'));
  assert.equal(controls['mvg-progress-items'].children.length, 0);
}

async function operationLockPreservesBusinessState() {
  let active = true;
  const {context} = harness(async () => response({active, action: 'planning-mvg'}));
  const generate = new Element('button'), run = new Element('button'), select = new Element('select');
  generate.disabled = true; run.disabled = true; select.disabled = true;
  const root = {querySelectorAll: () => [generate, run, select]};
  context.document.body = new Element('body');
  context.window.installKnowledgeOperationLock({root});
  await settle();
  assert.equal(generate.inert, true); assert.equal(root.inert, false);
  // The handler finishes before the next operation poll observes inactivity.
  generate.disabled = false; select.disabled = false;
  active = false; await context.window.interval();
  assert.equal(generate.inert, false); assert.equal(select.inert, false);
  assert.equal(generate.disabled, false); assert.equal(select.disabled, false);
  assert.equal(run.disabled, true, 'The planning-result runtime prohibition must survive unlock');
}

async function committedProgressPreservesExpandedDetails() {
  let epoch = 0, count = 1;
  const {context, controls} = harness(async url => {
    if (url.endsWith('/mvg-progress')) return response({epoch, completed: count, total: 3,
      status: 'partial_planning', sha256: `epoch-${epoch}-count-${count}`,
      items: [{capability_id: 'CAP-a', provenance: 'new'}],
      proposal: {manifest_candidate: {flows: [{id: 'flow-a', outcome: 'Observe outcome'}]}}});
    return response({revision: completed.revision, versions: [], manifests: []});
  });
  vm.runInContext(source('project_health_mvg_versions.js'), context);
  await settle();
  const display = controls['mvg-progress-items'];
  const flow = display.children.find(row => row.tag === 'details');
  flow.open = true;
  const complete = display.children.at(-1); complete.open = true;
  await context.window.refreshMvgProgress();
  assert.equal(display.children.find(row => row.tag === 'details'), flow,
    'Identical progress must retain the same DOM and text selection');
  count = 2;
  await context.window.refreshMvgProgress();
  assert.equal(display.children.find(row => row.tag === 'details').open, true,
    'New checkpoints must retain expanded flow details');
  assert.equal(display.children.at(-1).open, true);
  epoch = 1;
  await context.window.refreshMvgProgress();
  assert.notEqual(display.children.find(row => row.tag === 'details').open, true,
    'A new clear epoch must not inherit old expanded state');
}

(async () => { await compactResults(); await topologyButton(); await mvgButton(); await slowCommittedProgressAndClear(); await operationLockPreservesBusinessState(); await committedProgressPreservesExpandedDetails();
  console.log('Planning frontend: authenticated polling, compact failures, both refreshed views and source provenance passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
