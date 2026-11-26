'use strict';
// Story 4.7 stage-true planning panel: exercises the real project_health_planning.js in node:vm.
// This proves the UI interaction contract only; it is not Godot gameplay or Reward pilot evidence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../../..');
const source = name => fs.readFileSync(path.join(root, 'scripts/python', name), 'utf8');

class Element {
  constructor(tag = 'div', id = '') {
    this.tag = tag; this.tagName = tag.toUpperCase(); this.id = id; this.parentNode = null;
    this.children = []; this.dataset = {}; this.listeners = {};
    this.disabled = false; this.inert = false; this._value = ''; this.textContent = ''; this.attributes = {}; this.style = {};
    this.classList = {add() {}};
  }
  get value() { return this._value || (this.tag === 'select' ? this.children[0]?.value || '' : ''); }
  set value(value) { this._value = value; }
  append(...nodes) {
    for (const node of nodes) {
      if (node && typeof node === 'object') node.parentNode = this;
      this.children.push(node);
    }
  }
  replaceChildren(...nodes) { this.children = []; this._value = ''; this.append(...nodes); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  closest(selector) {
    let cur = this;
    while (cur) {
      if (selector === '[data-knowledge-readonly]' && (cur.attributes?.['data-knowledge-readonly'] !== undefined || cur.dataset?.knowledgeReadonly !== undefined)) {
        return cur;
      }
      cur = cur.parentNode;
    }
    return null;
  }
  querySelectorAll(selector) {
    const tags = new Set(selector.split(',').map(s => s.trim().toLowerCase()));
    return walk(this).filter(node => tags.has(node.tag));
  }
}
const walk = (node, out = []) => { out.push(node); for (const child of node.children || []) if (child instanceof Element) walk(child, out); return out; };
const texts = node => walk(node).map(item => item.textContent).join('\n');
const settle = async () => { for (let i = 0; i < 20; i++) await new Promise(resolve => setImmediate(resolve)); };
const response = (payload, code = 200) => ({ok: code < 400, status: code, json: async () => payload});

function harness(fetch, {elementsById = {}} = {}) {
  const body = new Element('body');
  const context = {document: {
    body,
    querySelector() { return null; },
    getElementById(id) { return Object.prototype.hasOwnProperty.call(elementsById, id) ? elementsById[id] : new Element(); },
    createElement: tag => new Element(tag), createTextNode: text => ({textContent: text})},
  window: {location: {search: ''}, setInterval(cb) { this.interval = cb; return 1; }, clearInterval() {}, addEventListener() {}},
  URLSearchParams, fetch, setTimeout: callback => callback()};
  vm.createContext(context);
  vm.runInContext(source('project_health_planning.js'), context);
  return context;
}

const diag = (code, entity, expected, actual, resumeRef) => ({reason_code: code, stage: 'target', entity_id: entity,
  expected, actual, resume_ref: resumeRef});
const blocked3c = diag('required_governance_missing', 'docs/planning/b-route/catalog.v1.json',
  'formally adopted 3B plan in catalog.v1.json', {valid_plans: 0}, 'docs/planning/b-route/catalog.v1.json');
const blocked6 = diag('missing_required_field', 'task_id', 'explicit Taskmaster task_id evaluated by the Story 3.12 unified gate', null, null);
function stateFixture({allow6 = false, allow3c = false, mode = 'attempt'} = {}) {
  return {
    schema_version: 'newrouge.b-route-planning-page.v1', ok: true, status: 'partial_planning', mode,
    provenance: {mode, authority_ref: 'local-workspace', is_main_fact: mode === 'main', dirty_workspace: true, can_advance_canonical: false},
    planning_completeness: 'partial_planning', planning_complete: false, partial_planning: true,
    stage_gates: {
      stage_3a_sources: {allowed: true, requires_tasks: false, requires_chapter5_readiness: false, diagnostics: []},
      stage_3b_planning: {allowed: true, requires_tasks: false, requires_chapter5_readiness: false, diagnostics: []},
      stage_3c_tasks: {allowed: allow3c, diagnostics: allow3c ? [] : [blocked3c]},
      stage_6_implement: {allowed: allow6, diagnostics: allow6 ? [] : [blocked6]},
    },
    coordinator_progress: {
      committed_prefix: {partial_planning: true, planning_complete: false, runtime_verified: false,
        runs: [{family: 'mvg-planning', run_id: 'run-ok', selected: 1, total: 3, partial_planning: true}]},
      candidate_states: [{candidate_id: 'cand-1', run_id: 'run-ok', status: 'candidate_in_progress', adopted: false}],
      budget_summary: {budget_exhausted: true, exhausted_runs: ['run-budget']},
      revoked_runs: [{run_id: 'run-revoked', revoked: true, recoverable: false, reasons: ['epoch_invalidated']}],
      recoverable_operations: [{kind: 'planner_run', run_id: 'run-ok', resume_ref: 'logs/ci/mvg-planning/run-ok/run.json',
        original_locator: 'logs/ci/mvg-planning/run-ok/run.json'}],
      planner_runs: [
        {family: 'mvg-planning', run_id: 'run-ok', recoverable: true, revoked: false, budget_exhausted: false},
        {family: 'capability-planning', run_id: 'run-budget', recoverable: false, revoked: false, budget_exhausted: true},
        {family: 'mvg-planning', run_id: 'run-revoked', recoverable: false, revoked: true, budget_exhausted: false},
      ],
    },
    diagnostics: [blocked3c],
    runtime_verified: false, ui_contract_only_not_godot_gameplay: true,
  };
}

async function diagnosticsAndModes() {
  const context = harness(async () => response({}));
  const sample = diag('invalid_argument', 'task_id', {nested: [1, 2]}, null, 'logs/ci/run/report.json');
  const node = context.window.formatBRouteDiagnostic(sample);
  assert.equal(node.textContent, 'invalid_argument | target | task_id | {"nested":[1,2]} | null | logs/ci/run/report.json');
  assert.equal(node.dataset.reasonCode, 'invalid_argument');
  assert.equal(node.children.length, 0, 'Diagnostics use textContent only');
  assert.equal(context.window.bRouteModeFor({identity: 'main', view: 'stable'}), 'main');
  for (const view of ['attempt', 'stable', 'stabilized']) assert.equal(context.window.bRouteModeFor({identity: 'workspace', view}), view);
  assert.equal(context.window.bRouteModeFor({identity: 'workspace', view: 'bogus'}), 'attempt');
}

async function operationLockInertsStagePanelControls() {
  // Topology HTML must NOT wrap #b-route-stage-panel with data-knowledge-readonly.
  const html = source('project_health_topology.html');
  assert.ok(html.includes('<section id="b-route-stage-panel" aria-label="B-route stage actions">'));
  assert.ok(!html.includes('<section id="b-route-stage-panel" data-knowledge-readonly'));
  let active = true;
  const main = new Element('main');
  const section = new Element('section', 'b-route-stage-panel');
  const host = new Element('div', 'b-route-stage-host');
  section.append(host);
  main.append(section);
  const context = harness(async url => {
    if (url.endsWith('/operation')) return response({active, action: 'b-route-planning:3b_mvg'});
    return response(stateFixture());
  }, {elementsById: {'b-route-stage-panel': section, 'mvg-committed-progress': null}});
  const panel = context.window.mountBRouteStagePanel({host, getMode: () => 'attempt'});
  await settle();
  context.window.installKnowledgeOperationLock({root: main});
  await settle();
  const interactive = main.querySelectorAll('button, select, input, textarea');
  assert.ok(interactive.length >= 10, 'Stage panel mounts interactive buttons, inputs and selects');
  assert.ok(interactive.every(ctrl => ctrl.inert === true), 'All stage-panel controls become inert while operation is active');
  assert.equal(panel.controls.diagnostics.closest('[data-knowledge-readonly]') !== null, true, 'Diagnostics remain readonly-marked');
  active = false;
  await context.window.interval();
  await settle();
  assert.ok(interactive.every(ctrl => ctrl.inert === false), 'All stage-panel controls unlock when operation finishes');
}

async function stageTrueButtonsFilterForwardingAndResume() {
  const gets = []; const posts = [];
  let allow3c = false;
  const context = harness(async (url, options) => {
    if (url.endsWith('/session')) return response({token: 'verified'});
    if (options?.method === 'POST') {
      posts.push({headers: options.headers, body: JSON.parse(options.body)});
      return response({schema_version: 'newrouge.b-route-planning-page.v1', ok: false, status: 'blocked', action: 'x',
        recommendation_only: true, diagnostics: [blocked6], original_locator: 'logs/ci/a.json', resume_ref: 'logs/ci/a.json'}, 422);
    }
    gets.push(url);
    const qs = new URLSearchParams(url.split('?')[1] || '');
    const allow6 = qs.get('task_id') === '7';
    return response(stateFixture({allow6, allow3c, mode: qs.get('mode') || 'attempt'}));
  });
  let mode = 'attempt';
  const host = new Element();
  const panel = context.window.mountBRouteStagePanel({host, getMode: () => mode});
  await settle();
  const c = panel.controls;
  assert.ok(gets[0].startsWith('/api/knowledge/b-route-planning?mode=attempt'));
  // 3A and 3B are enabled without Tasks or Chapter 5 readiness; 3C and Chapter 6 execution stay gated.
  assert.equal(c.run3a.disabled, false); assert.equal(c.start3b.disabled, false);
  assert.equal(c.preview3c.disabled, true); assert.equal(c.compile3c.disabled, true);
  assert.equal(c.execute6.disabled, true); assert.equal(c.inspect6.disabled, false);
  assert.equal(c.resume3b.disabled, true, 'Resume needs a selected recoverable run');
  const progress = texts(c.progress);
  assert.ok(progress.includes('partial_planning: committed prefix only; not planning_complete; runtime not verified'));
  assert.ok(progress.includes('candidate_in_progress (not adopted)'));
  assert.ok(progress.includes('adopted false'));
  assert.ok(progress.includes('revoked (not recoverable): run-revoked'));
  assert.ok(progress.includes('budget exhausted (not recoverable): run-budget'));
  assert.ok(!/planning_complete true|runtime PASS|passed|adopted true/i.test(progress), 'Prefix/candidates never render as complete or green');
  // Verbatim six-field diagnostics and the honest UI-contract notice.
  assert.equal(c.diagnostics.children[0].textContent, context.window.bRouteDiagnosticText(blocked3c));
  assert.equal(c.gateDiagnostics.stage_3c_tasks.children[0].textContent, context.window.bRouteDiagnosticText(blocked3c));
  assert.equal(c.gateDiagnostics.stage_6_implement.children[0].dataset.reasonCode, 'missing_required_field');
  assert.equal(c.notice.textContent, 'UI contract view: automated actions follow B-route gates; this page does not certify Godot gameplay or Reward pilot acceptance.');
  assert.equal(texts(c.locators).includes('original_locator logs/ci/mvg-planning/run-ok/run.json'), true);
  // No Task origin switch or B-origin delete controls exist anywhere in the panel.
  const buttons = walk(host).filter(node => node.tag === 'button');
  assert.ok(buttons.length >= 9);
  assert.ok(buttons.every(button => !/switch|delete|origin|reset budget/i.test(button.textContent)));
  // Budget-exhausted and revoked runs never enable resume; a recoverable run does.
  for (const [value, disabled] of [['capability-planning:run-budget', true], ['mvg-planning:run-revoked', true], ['mvg-planning:run-ok', false]]) {
    c.runSelect.value = value; c.runSelect.listeners.change();
    assert.equal(c.resume3b.disabled, disabled, value);
  }
  c.runSelect.value = 'capability-planning:run-budget'; c.runSelect.listeners.change();
  assert.equal(await c.resume3b.onclick(), null, 'Disabled resume never sends a request');
  assert.equal(posts.length, 0);
  // start3b prepare forwards planning_contract.
  c.planning_contract.value = 'logs/ci/contracts/c1.json';
  await c.start3b.onclick();
  assert.deepEqual(posts[0].body, {action: '3b_capability', invocation_mode: 'new', stage: 'prepare',
    planning_contract: 'logs/ci/contracts/c1.json', mode: 'attempt'});
  assert.equal(posts[0].headers['X-Project-Health-Token'], 'verified');
  // resume3b forwards selected stage + prepared_ref + planning_profile.
  c.runSelect.value = 'mvg-planning:run-ok'; c.runSelect.listeners.change();
  c.stage3b.value = 'generate';
  c.prepared_ref.value = 'logs/ci/b-route-planning-input/r0/prepared.json';
  c.planning_profile.value = 'mvg_3b';
  await c.resume3b.onclick();
  assert.deepEqual(posts[1].body, {action: '3b_mvg', invocation_mode: 'resume', run_id: 'run-ok', stage: 'generate',
    prepared_ref: 'logs/ci/b-route-planning-input/r0/prepared.json', planning_profile: 'mvg_3b', mode: 'attempt'});
  assert.equal(c.result.dataset.result, 'failed');
  assert.equal(c.actionDiagnostics.children[0].textContent, context.window.bRouteDiagnosticText(blocked6));
  assert.ok(c.actionLocator.textContent.includes('original_locator logs/ci/a.json'));
  // 3b_adoption recover-inspect.
  c.operation_id.value = 'op-adopt-1';
  c.stageAdoption.value = 'recover-inspect';
  await c.runAdoption.onclick();
  assert.deepEqual(posts[2].body, {action: '3b_adoption', stage: 'recover-inspect', operation_id: 'op-adopt-1', mode: 'attempt'});
  // 3c_task_compile prepare forwards request_ref when 3C unlocked.
  allow3c = true;
  await c.refreshState.onclick();
  assert.equal(c.compile3c.disabled, false);
  c.request_ref.value = 'logs/ci/3c/req.json';
  c.stageCompile3c.value = 'prepare';
  await c.compile3c.onclick();
  assert.deepEqual(posts[3].body, {action: '3c_task_compile', stage: 'prepare', operation_id: 'op-adopt-1',
    request_ref: 'logs/ci/3c/req.json', mode: 'attempt'});
  // 3A prepare uses the real CLI stage names.
  c.run_id.value = 'run-3a'; c.scope_id.value = 'scope-1';
  await c.run3a.onclick();
  assert.deepEqual(posts[4].body, {action: '3a_sources', stage: 'prepare', run_id: 'run-3a', scope_id: 'scope-1', mode: 'attempt'});
  // Dynamic refresh() forwards task_id/run_id/operation_id query params and enables Execute Chapter 6.
  c.task_id.value = '7';
  await c.task_id.listeners.change();
  const lastGet = gets.at(-1);
  assert.ok(lastGet.includes('task_id=7'), 'refresh forwards task_id query param');
  assert.ok(lastGet.includes('run_id=run-3a'), 'refresh forwards run_id query param');
  assert.ok(lastGet.includes('operation_id=op-adopt-1'), 'refresh forwards operation_id query param');
  assert.equal(c.execute6.disabled, false, 'Entering task_id dynamically unlocks Execute Chapter 6 from server gate');
  c.subAction6.value = 'route';
  await c.inspect6.onclick();
  assert.deepEqual(posts[5].body, {action: 'chapter6', sub_action: 'route', recommendation_only: true, task_id: 7, mode: 'attempt'});
  mode = 'main';
  await panel.refresh();
  assert.ok(gets.at(-1).startsWith('/api/knowledge/b-route-planning?mode=main'));
  assert.ok(c.identity.textContent.includes('is_main_fact true'));
  await c.execute6.onclick();
  assert.deepEqual(posts[6].body, {action: 'chapter6', sub_action: 'execute', recommendation_only: false, task_id: 7, mode: 'main'});
  for (const body of posts.map(post => post.body)) {
    for (const forbidden of ['allow_unready', 'draft', 'reset_budget', 'switch_task_origin', 'delete_b_origin', 'summary_override']) {
      assert.equal(Object.prototype.hasOwnProperty.call(body, forbidden), false, forbidden);
    }
  }
}

async function knowledgePageModeAndTokenParity() {
  const calls = [];
  const controls = {};
  const context = {
    document: {
      querySelector() { return null; },
      querySelectorAll() { return []; },
      getElementById(id) {
        if (!controls[id]) {
          const el = new Element(id === 'detail' ? 'dialog' : 'div', id);
          el.showModal = () => { el.open = true; };
          el.close = () => { el.open = false; };
          controls[id] = el;
        }
        return controls[id];
      },
      createElement: tag => new Element(tag),
      createTextNode: text => ({textContent: text}),
    },
    Node: Element,
    location: {pathname: '/knowledge/', search: ''},
    URLSearchParams,
    setInterval() { return 1; },
    fetch: async (url, options) => {
      calls.push({url, options});
      if (url.endsWith('/session')) return response({token: 'fresh-tok'});
      if (url.endsWith('/b-route-planning')) return response({ok: true, status: 'ok', diagnostics: []});
      return response({});
    },
  };
  vm.createContext(context);
  // Load functions without running the boot IIFE at the final line.
  const src = source('project_health_knowledge.js').replace(/^run\(async\(\)=>\{[\s\S]*$/m, '');
  vm.runInContext(src, context);
  context.renderBRouteIdentity({
    task: {id: 12},
    b_route_identity: {
      task: {governed: true, planning_state: '3b_adopted'},
      planning_completeness: 'partial_planning',
      provenance: {mode: 'workspace_preview'},
    },
  });
  const detailText = texts(controls['detail-links']);
  assert.ok(detailText.includes('workspace_preview'), 'Displayed mode matches provenance.mode');
  // Invoke bRoutePageCheck with empty token: must fetch /session first and send matching mode.
  await context.bRoutePageCheck(12, 'gate', 'workspace_preview');
  assert.ok(calls.some(c => c.url.endsWith('/session')), 'Fetches /api/knowledge/session when token is empty');
  const postCall = calls.find(c => c.url.endsWith('/b-route-planning'));
  assert.equal(postCall.options.headers['X-Project-Health-Token'], 'fresh-tok');
  assert.deepEqual(JSON.parse(postCall.options.body), {
    action: 'chapter6', sub_action: 'gate', task_id: 12, mode: 'workspace_preview', recommendation_only: true,
  });
}

async function progressSummaryForScenes() {
  const context = harness(async () => response({}));
  const host = new Element();
  const summary = context.window.renderBRouteProgressSummary({partial_planning: false, coordinator_progress: {
    committed_prefix: {partial_planning: false, runs: []}, candidate_states: [], budget_summary: {budget_exhausted: false}, revoked_runs: []}}, host);
  assert.deepEqual({...summary}, {partial: false, candidates: 0, budgetExhausted: false});
  assert.ok(texts(host).includes('budget: no exhausted planner run'));
}

(async () => {
  await diagnosticsAndModes();
  await operationLockInertsStagePanelControls();
  await stageTrueButtonsFilterForwardingAndResume();
  await knowledgePageModeAndTokenParity();
  await progressSummaryForScenes();
  console.log('B-route planning page UI: stage-true gating, lock inert, filter forwarding, prefix/candidate honesty, new vs resume, verbatim diagnostics passed (UI contract only).');
})().catch(error => { console.error(error); process.exitCode = 1; });
