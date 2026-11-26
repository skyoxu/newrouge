'use strict';
window.installKnowledgeOperationLock = function ({root = document.querySelector('main')} = {}) {
  if (!root || document.querySelector('[data-knowledge-operation-lock]')) return;
  const overlay = document.createElement('div');
  overlay.dataset.knowledgeOperationLock = 'true';
  overlay.hidden = true;
  overlay.setAttribute('role', 'status');
  overlay.setAttribute('aria-live', 'polite');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:1000;background:#132d42cc;color:white;display:none;place-items:center;padding:24px';
  const card = document.createElement('div');
  card.style.cssText = 'width:min(520px,100%);background:#fff;color:#192c3b;border:2px solid #17899a;border-radius:8px;padding:24px;box-shadow:0 18px 48px #0006';
  const title = document.createElement('strong'); title.textContent = 'Operation in progress';
  const detail = document.createElement('p'); detail.style.marginBottom = '0';
  card.append(title, detail); overlay.append(card); document.body.append(overlay);
  const update = state => {
    const active = Boolean(state?.active);
    const hasProgress = Boolean(document.getElementById('mvg-committed-progress') || document.getElementById('b-route-stage-panel'));
    root.inert = active && !hasProgress;
    if (hasProgress) {
      for (const control of root.querySelectorAll('button, select, input, textarea')) {
        if (control.closest('[data-knowledge-readonly]')) continue;
        // Inert blocks interaction independently of the owner's disabled
        // state; asynchronous completion can safely update business rules.
        control.inert = active;
      }
    }
    overlay.hidden = !active || hasProgress;
    overlay.style.display = active && !hasProgress ? 'grid' : 'none';
    if (active) {
      const action = state.action || 'Another operation';
      detail.textContent = `${action} is running. This page is locked until it finishes.`;
    }
  };
  const poll = async () => {
    try {
      const response = await fetch('/api/knowledge/operation', {cache: 'no-store'});
      if (response.ok) update(await response.json());
    } catch (_) { /* keep the current lock state during transient disconnects */ }
  };
  poll();
  const timer = window.setInterval(poll, 1000);
  window.addEventListener('pagehide', () => window.clearInterval(timer), {once: true});
};

// Both pages use the same authenticated async job and compact result contract.
window.knowledgePlanning = async function ({action, manifest, button, status, refresh}) {
  const message = (text, state) => {
    status.textContent = String(text || 'Planning failed').replace(/\s+/g, ' ').slice(0, 360);
    status.dataset.result = state;
  };
  let activeJobId = null;
  const cancelButton = document.createElement('button');
  cancelButton.type = 'button';
  cancelButton.textContent = 'Cancel planning';
  cancelButton.hidden = true;
  cancelButton.dataset.knowledgeCancel = 'true';
  cancelButton.setAttribute('aria-label', 'Cancel the active planning job');
  cancelButton.style.cssText = 'position:fixed;right:24px;bottom:24px;z-index:1100';
  // The page lock makes <main> inert while a job runs.  Keep cancellation as
  // a body-level control so the operator can stop a long model invocation.
  if (document.body && typeof document.body.append === 'function') {
    document.body.append(cancelButton);
  } else if (typeof button.insertAdjacentElement === 'function') {
    button.insertAdjacentElement('afterend', cancelButton);
  }
  cancelButton.onclick = async () => {
    if (!activeJobId || cancelButton.disabled) return;
    cancelButton.disabled = true;
    try {
      const sessionResponse = await fetch('/api/knowledge/session', {cache: 'no-store'});
      if (!sessionResponse.ok) throw new Error('Unable to start a verified session');
      const session = await sessionResponse.json();
      const response = await fetch('/api/knowledge/planning-cancel', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Project-Health-Token': session.token},
        body: JSON.stringify({job_id: activeJobId})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.reason || result.message || 'Unable to cancel planning');
      message('Cancellation requested; waiting for the current stage to stop.', 'cancelling');
    } catch (error) {
      message(error.message, 'failed');
      cancelButton.disabled = false;
    }
  };
  button.disabled = true;
  cancelButton.hidden = false;
  message(`Generating ${action === 'capability' ? 'Capability' : 'MVG'} from local inputs...`, 'running');
  try {
    const sessionResponse = await fetch('/api/knowledge/session', {cache: 'no-store'});
    if (!sessionResponse.ok) throw new Error('Unable to start a verified session');
    const session = await sessionResponse.json();
    const response = await fetch('/api/knowledge/planning', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Project-Health-Token': session.token},
      body: JSON.stringify({action, ...(manifest ? {manifest} : {})})
    });
    let result = await response.json();
    if (response.status === 404) throw new Error('Planning API unavailable. Restart the Project Health service and reload this page.');
    if (!response.ok) throw new Error(result.reason || result.message || 'Unable to start planning');
    activeJobId = result.job_id || null;
    while (result.status === 'queued' || result.status === 'running' || result.status === 'cancelling') {
      message(`${action === 'capability' ? 'Capability' : 'MVG'} · ${result.stage || 'prepare'} · local ${(result.revision || '').slice(0, 12)}`, 'running');
      await new Promise(resolve => setTimeout(resolve, 2000));
      const poll = await fetch('/api/knowledge/planning?job_id=' + encodeURIComponent(result.job_id), {cache: 'no-store'});
      result = await poll.json();
      if (!poll.ok) throw new Error(result.reason || 'Unable to read planning result');
      if (action === 'mvg' && window.refreshMvgProgress) await window.refreshMvgProgress();
    }
    if (result.status === 'recoverable') {
      // Candidate and review artifacts are durable.  Keep the result visible
      // as operator-recoverable. Generate always starts a fresh run; only
      // explicit CLI/run-id recovery may resume this retained evidence.
      message(`${result.message || 'Planning can be resumed'}. Generate starts a fresh run; retained evidence requires explicit operator recovery.`, 'recoverable');
      return;
    }
    if (result.status !== 'completed') throw new Error(result.message || 'Planning failed');
    try {
      await refresh(result);
    } catch (error) {
      message(`${result.message}. Data refresh failed: ${error.message}`, 'failed');
      return;
    }
    // Render/load may also update the status; the final action result wins.
    message(result.message, 'success');
  } catch (error) {
    message(error.message, 'failed');
  } finally {
    activeJobId = null;
    cancelButton.hidden = true;
    cancelButton.disabled = false;
    button.disabled = false;
  }
};

// B-route stage-true planning panel (Story 4.7). Every repository or service
// string is rendered with textContent; diagnostics are shown verbatim and
// never converted into commands or semantic findings.
window.B_ROUTE_HONEST_NOTICE = 'UI contract view: automated actions follow B-route gates; this page does not certify Godot gameplay or Reward pilot acceptance.';
window.B_ROUTE_DIAGNOSTIC_FIELDS = ['reason_code', 'stage', 'entity_id', 'expected', 'actual', 'resume_ref'];
window.bRouteDiagnosticText = function (diag) {
  const value = item => (item === null || item === undefined) ? 'null' : (typeof item === 'string' ? item : JSON.stringify(item));
  return window.B_ROUTE_DIAGNOSTIC_FIELDS.map(field => value(diag ? diag[field] : null)).join(' | ');
};
window.formatBRouteDiagnostic = function (diag) {
  const node = document.createElement('p');
  node.className = 'b-route-diagnostic';
  node.dataset.reasonCode = String(diag?.reason_code ?? '');
  node.dataset.stage = String(diag?.stage ?? '');
  node.textContent = window.bRouteDiagnosticText(diag);
  return node;
};
window.bRouteModeFor = function ({identity, view} = {}) {
  if (identity === 'main') return 'main';
  return ['attempt', 'stable', 'stabilized'].includes(view) ? view : 'attempt';
};
window.loadBRoutePlanningState = async function ({mode = 'workspace_preview', params = {}} = {}) {
  const query = new URLSearchParams({mode});
  for (const [key, value] of Object.entries(params || {})) if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  const response = await fetch('/api/knowledge/b-route-planning?' + query.toString(), {cache: 'no-store'});
  const payload = await response.json();
  if (response.status === 404) throw new Error('B-route planning API unavailable. Restart the Project Health service and reload this page.');
  return payload;
};
window.invokeBRoutePlanningAction = async function (request) {
  const sessionResponse = await fetch('/api/knowledge/session', {cache: 'no-store'});
  if (!sessionResponse.ok) throw new Error('Unable to start a verified session');
  const session = await sessionResponse.json();
  const response = await fetch('/api/knowledge/b-route-planning', {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Project-Health-Token': session.token},
    body: JSON.stringify(request)
  });
  const payload = await response.json();
  return {status: response.status, payload};
};
window.renderBRouteProgressSummary = function (state, host) {
  const add = (tag, text, key) => { const node = document.createElement(tag); node.textContent = String(text ?? ''); if (key) node.dataset.bRoute = key; host.append(node); return node; };
  const progress = state?.coordinator_progress || {};
  const prefix = progress.committed_prefix || {};
  const runs = prefix.runs || [];
  const partial = Boolean(state?.partial_planning || prefix.partial_planning);
  if (partial) add('p', 'partial_planning: committed prefix only; not planning_complete; runtime not verified', 'partial');
  for (const run of runs) add('p', `committed prefix · ${run.family} · ${run.run_id} · ${run.selected}/${run.total ?? '?'} checkpoints · planning_complete false`, 'prefix-run');
  const candidates = progress.candidate_states || [];
  if (candidates.length) add('p', `candidate_in_progress (not adopted): ${candidates.length} uncommitted candidate(s)`, 'candidates');
  for (const candidate of candidates) add('p', `${candidate.status} · ${candidate.run_id} · ${candidate.candidate_id} · adopted false`, 'candidate');
  const budget = progress.budget_summary || {};
  add('p', budget.budget_exhausted ? `budget exhausted (not recoverable): ${(budget.exhausted_runs || []).join(', ')}` : 'budget: no exhausted planner run', 'budget');
  for (const run of progress.revoked_runs || []) add('p', `revoked (not recoverable): ${run.run_id || run.job_id} · ${(run.reasons || []).join(', ')}`, 'revoked');
  return {partial, candidates: candidates.length, budgetExhausted: Boolean(budget.budget_exhausted)};
};
window.loadBRouteObservability = async function ({params = {}} = {}) {
  const query = new URLSearchParams();
  for (const key of ['operation_id', 'run_id', 'scope_id', 'flow_id', 'stage', 'task_id', 'baseline_ref']) {
    const value = params ? params[key] : undefined;
    if (value !== undefined && value !== null && value !== '') query.set(key, String(value));
  }
  const suffix = query.toString() ? '?' + query.toString() : '';
  const response = await fetch('/api/knowledge/b-route-observability' + suffix, {cache: 'no-store'});
  const payload = await response.json();
  if (response.status === 404) throw new Error('B-route observability API unavailable. Restart the Project Health service and reload this page.');
  return payload;
};
window.renderBRouteObservability = function (obs, host) {
  if (!host) return null;
  host.replaceChildren();
  const add = (tag, text, key) => {
    const node = document.createElement(tag);
    node.textContent = String(text ?? '');
    if (key) node.dataset.bRouteObs = key;
    host.append(node);
    return node;
  };
  const hasTiming = Boolean(obs && typeof obs.timing_and_cost_summary === 'object' && obs.timing_and_cost_summary !== null);
  const timing = hasTiming ? obs.timing_and_cost_summary : null;
  const active = hasTiming ? (timing.observed_active_elapsed_seconds ?? 'unknown') : 'unknown';
  const wall = hasTiming ? (timing.paused_or_wall_clock_seconds ?? 'unknown') : 'unknown';
  const unmeasured = hasTiming ? (timing.unmeasured_event_count ?? 'unknown') : 'unknown';
  const reserved = hasTiming ? (timing.reserved_request_budget ?? 'unknown') : 'unknown';
  const actual = hasTiming ? (timing.observed_actual_dispatches ?? 'unknown') : 'unknown';
  const reservedOnly = hasTiming ? (timing.reserved_only_not_dispatched ?? 'unknown') : 'unknown';
  const billed = hasTiming ? (timing.billed_cost ?? 'unknown') : 'unknown';
  add('p', `timing · observed_active_elapsed_seconds ${active} · paused_or_wall_clock_seconds ${wall} (not active) · unmeasured ${unmeasured}`, 'timing');
  add('p', `budget · reserved_request_budget ${reserved} · observed_actual_dispatches ${actual} · reserved_only_not_dispatched ${reservedOnly} · billed_cost ${billed}`, 'budget');
  const hasReuse = Boolean(obs && typeof obs.reuse_breakdown === 'object' && obs.reuse_breakdown !== null);
  if (hasReuse) {
    const reuse = obs.reuse_breakdown;
    const counts = reuse.counts || {};
    add('p', `reuse (cross_class_proof_allowed ${reuse.cross_class_proof_allowed === true}) · planning_adoption_reuse ${counts.planning_adoption_reuse ?? (reuse.planning_adoption_reuse || []).length} · apply_idempotent_noop ${counts.apply_idempotent_noop ?? (reuse.apply_idempotent_noop || []).length} · runtime_build_and_test_reuse ${counts.runtime_build_and_test_reuse ?? (reuse.runtime_build_and_test_reuse || []).length}`, 'reuse');
  } else {
    add('p', 'reuse · unknown', 'reuse');
  }
  const hasStopLoss = Boolean(obs && typeof obs.stop_loss_signals === 'object' && obs.stop_loss_signals !== null);
  if (hasStopLoss) {
    const stopLoss = obs.stop_loss_signals;
    add('p', `stop_loss_signals · active ${stopLoss.active_count ?? 'unknown'} · rerun_guard ${(stopLoss.rerun_guard || []).length} · llm_retry ${(stopLoss.llm_retry_stop_loss || []).length} · sc_test_retry ${(stopLoss.sc_test_retry_stop_loss || []).length} · waste ${(stopLoss.waste_signals || []).length} · deterministic_stop_loss ${(stopLoss.deterministic_stop_loss || []).length} · no_progress_retries ${(stopLoss.no_progress_retries || []).length}`, 'stop-loss');
  } else {
    add('p', 'stop_loss_signals · unknown', 'stop-loss');
  }
  const hasQualityFloor = Boolean(obs && typeof obs.quality_floor === 'object' && obs.quality_floor !== null);
  if (hasQualityFloor) {
    const qf = obs.quality_floor;
    add('p', `quality_floor · violated ${qf.violated === true} · process_metrics_can_offset ${qf.process_metrics_can_offset === true}`, 'quality-floor');
  } else {
    add('p', 'quality_floor · unknown', 'quality-floor');
  }
  for (const diag of obs?.diagnostics || []) {
    const node = document.createElement('p');
    node.className = 'b-route-diagnostic';
    node.dataset.diagnosticCategory = String(diag?.diagnostic_category ?? '');
    node.dataset.reasonCode = String(diag?.reason_code ?? '');
    node.dataset.stage = String(diag?.stage ?? '');
    node.textContent = `[${String(diag?.diagnostic_category ?? 'unknown')}] ${window.bRouteDiagnosticText(diag)}`;
    host.append(node);
  }
  return {
    active,
    wall,
    reserved,
    actual,
    billed,
    diagnosticsCount: (obs?.diagnostics || []).length,
  };
};
window.mountBRouteStagePanel = function ({host, getMode = () => 'workspace_preview', onRefresh = null, getParams = () => ({})} = {}) {
  if (!host) return null;
  let state = null;
  let busy = false;
  const controls = {};
  const FILTER_FIELDS = ['scope_id', 'flow_id', 'capability_id', 'task_id', 'run_id', 'operation_id'];
  const make = (tag, text, parent, key) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (key) node.dataset.bRoute = key;
    parent.append(node);
    return node;
  };
  const markReadonly = node => { node.setAttribute('data-knowledge-readonly', 'true'); node.dataset.knowledgeReadonly = 'true'; return node; };
  const field = (name, label, parent, placeholder = '') => {
    const wrapper = make('label', label + ' ', parent);
    const input = document.createElement('input');
    input.dataset.bRouteField = name; input.placeholder = placeholder;
    wrapper.append(input); controls[name] = input; return input;
  };
  const value = name => String(controls[name]?.value || '').trim();
  const optional = (request, name) => { const text = value(name); if (text) request[name] = text; return request; };
  const addOptionals = (request, names) => names.reduce((acc, name) => optional(acc, name), request);
  function collectFilterParams() {
    const params = {...(getParams() || {})};
    for (const name of FILTER_FIELDS) {
      const text = value(name);
      if (text) params[name] = text;
    }
    return params;
  }
  function selectedRun() {
    const id = controls.runSelect?.value || '';
    return (state?.coordinator_progress?.planner_runs || []).find(run => `${run.family}:${run.run_id}` === id) || null;
  }
  function resumeAllowed(run) {
    return Boolean(run && run.recoverable === true && run.revoked !== true && run.budget_exhausted !== true);
  }
  function syncButtons() {
    const gates = state?.stage_gates || {};
    const allowed = key => gates[key]?.allowed === true;
    const lock = busy || !state;
    controls.refreshState.disabled = busy;
    controls.run3a.disabled = lock || !allowed('stage_3a_sources');
    controls.start3b.disabled = lock || !allowed('stage_3b_planning');
    controls.resume3b.disabled = lock || !resumeAllowed(selectedRun());
    controls.runAdoption.disabled = lock;
    controls.preview3c.disabled = lock || !allowed('stage_3c_tasks');
    controls.compile3c.disabled = lock || !allowed('stage_3c_tasks');
    controls.inspect6.disabled = lock;
    controls.execute6.disabled = lock || !allowed('stage_6_implement');
  }
  function renderDiagnostics(target, diagnostics) {
    target.replaceChildren();
    for (const diag of diagnostics || []) target.append(window.formatBRouteDiagnostic(diag));
  }
  function render() {
    const provenance = state?.provenance || {};
    controls.identity.textContent = `identity ${provenance.mode || state?.mode || 'unknown'} · ${provenance.authority_ref || 'no authority ref'} · is_main_fact ${provenance.is_main_fact === true} · dirty_workspace ${provenance.dirty_workspace === true} · can_advance_canonical ${provenance.can_advance_canonical === true} · ${state?.planning_completeness || 'unknown'}`;
    controls.progress.replaceChildren();
    window.renderBRouteProgressSummary(state, controls.progress);
    const runs = state?.coordinator_progress?.planner_runs || [];
    const previous = controls.runSelect.value;
    controls.runSelect.replaceChildren();
    const none = document.createElement('option'); none.value = ''; none.textContent = 'No run selected'; controls.runSelect.append(none);
    for (const run of runs) {
      const option = document.createElement('option');
      option.value = `${run.family}:${run.run_id}`;
      option.textContent = `${run.family} · ${run.run_id} · ${run.revoked ? 'revoked' : run.budget_exhausted ? 'budget exhausted' : run.recoverable ? 'recoverable' : 'not recoverable'}`;
      controls.runSelect.append(option);
    }
    if (runs.some(run => `${run.family}:${run.run_id}` === previous)) controls.runSelect.value = previous;
    const gates = state?.stage_gates || {};
    for (const [key, target] of Object.entries(controls.gateDiagnostics)) renderDiagnostics(target, gates[key]?.diagnostics);
    for (const [key, target] of Object.entries(controls.gateStatus)) target.textContent = gates[key]?.allowed === true ? 'allowed' : 'blocked';
    renderDiagnostics(controls.diagnostics, state?.diagnostics);
    controls.locators.replaceChildren();
    for (const op of state?.coordinator_progress?.recoverable_operations || []) {
      make('p', `${op.kind} · ${op.run_id || op.operation_id || op.job_id || op.path || ''} · resume_ref ${op.resume_ref || 'none'} · original_locator ${op.original_locator || 'none'}`, controls.locators, 'locator');
    }
    syncButtons();
  }
  async function refresh() {
    try {
      state = await window.loadBRoutePlanningState({mode: getMode(), params: collectFilterParams()});
      render();
      if (controls.observability?.open) await refreshObservability();
    } catch (error) {
      controls.result.textContent = error.message;
      controls.result.dataset.result = 'failed';
    }
    return state;
  }
  async function invoke(request) {
    if (busy) return null;
    busy = true; syncButtons();
    controls.result.textContent = `${request.action}${request.stage ? ' · ' + request.stage : ''} running...`;
    controls.result.dataset.result = 'running';
    let outcome = null;
    try {
      outcome = await window.invokeBRoutePlanningAction({...request, mode: getMode()});
      const payload = outcome.payload || {};
      controls.result.textContent = `${payload.action || request.action} · ${payload.status || 'unknown'} · recommendation_only ${payload.recommendation_only === true} · runtime_verified false`;
      controls.result.dataset.result = payload.ok ? 'success' : 'failed';
      renderDiagnostics(controls.actionDiagnostics, payload.diagnostics || []);
      if (outcome.status === 409) controls.result.textContent = payload.reason || 'Another operation is running';
      controls.actionLocator.textContent = payload.original_locator ? `original_locator ${payload.original_locator} · resume_ref ${payload.resume_ref || 'none'}` : '';
    } catch (error) {
      controls.result.textContent = error.message; controls.result.dataset.result = 'failed';
    } finally {
      busy = false;
    }
    await refresh();
    if (onRefresh) await onRefresh(outcome);
    return outcome;
  }
  host.replaceChildren();
  const statusBox = markReadonly(make('div', undefined, host, 'readonly-status'));
  controls.identity = make('p', 'Loading B-route stage state...', statusBox, 'identity');
  controls.progress = make('div', undefined, statusBox, 'progress');
  const shared = make('div', undefined, host); shared.className = 'row';
  field('scope_id', 'Scope', shared, 'scope-id');
  field('flow_id', 'Flow', shared, 'flow-id');
  field('capability_id', 'Capability', shared, 'CAP-...');
  field('run_id', 'Run', shared, 'run-id');
  field('attempt_id', 'Attempt', shared, 'attempt-1');
  field('task_id', 'Task', shared, 'Task ID');
  field('plan_id', 'Plan', shared, 'plan-id');
  field('operation_id', 'Operation', shared, 'operation-id');
  field('audit_ref', 'Audit ref', shared, 'logs/ci/.../report.json');
  controls.refreshState = make('button', 'Inspect / Refresh State (read-only)', shared, 'refresh-state');
  controls.refreshState.type = 'button';
  controls.refreshState.onclick = () => refresh();
  for (const name of FILTER_FIELDS) controls[name].addEventListener('change', () => refresh());
  const stageInputs = make('div', undefined, host); stageInputs.className = 'row';
  field('planning_contract', 'Planning contract', stageInputs, 'logs/ci/.../contract.json');
  field('prepared_ref', 'Prepared ref', stageInputs, 'logs/ci/.../prepared.json');
  field('planning_profile', 'Planning profile', stageInputs, 'capability_3b|mvg_3b');
  field('request_ref', 'Request ref', stageInputs, 'logs/ci/.../request.json');
  field('accounted', 'Accounted ref', stageInputs, 'logs/ci/.../account/report.json');
  field('prepared', '3A prepared', stageInputs, 'logs/ci/.../prepared.json');
  field('candidate', '3A candidate', stageInputs, 'logs/ci/.../candidate.json');
  field('runner', 'Runner', stageInputs, 'scripts/python/...');
  field('expected_model', 'Expected model', stageInputs, 'model-id');
  controls.gateDiagnostics = {}; controls.gateStatus = {};
  const stageSection = (key, title) => {
    const box = make('details', undefined, host, key); box.open = true;
    const summary = make('summary', title + ' · ', box);
    controls.gateStatus[key] = make('span', 'loading', summary);
    const row = make('div', undefined, box); row.className = 'row';
    controls.gateDiagnostics[key] = markReadonly(make('div', undefined, box, 'gate-diagnostics'));
    return row;
  };
  const row3a = stageSection('stage_3a_sources', 'Stage 3A · Source accounting / audit (no Tasks or readiness required)');
  controls.stage3a = make('select', undefined, row3a, 'stage-3a');
  for (const stage of ['prepare', 'account', 'audit', 'verify']) { const option = make('option', stage, controls.stage3a); option.value = stage; }
  controls.run3a = make('button', 'Run 3A stage', row3a, 'run-3a'); controls.run3a.type = 'button';
  controls.run3a.onclick = () => {
    const stage = controls.stage3a.value || 'prepare';
    const extra = stage === 'account' ? ['prepared', 'candidate']
      : (stage === 'audit' || stage === 'verify') ? ['accounted', 'audit_ref', 'runner', 'expected_model'] : [];
    return invoke(addOptionals({action: '3a_sources', stage}, ['run_id', 'scope_id', 'attempt_id', ...extra]));
  };
  const row3b = stageSection('stage_3b_planning', 'Stage 3B · Formal semantic planning --input-stage 3b (no Tasks or readiness required)');
  controls.planner = make('select', undefined, row3b, 'planner');
  for (const [valueText, label] of [['3b_capability', 'Capability'], ['3b_mvg', 'MVG']]) { const option = make('option', label, controls.planner); option.value = valueText; }
  controls.stage3b = make('select', undefined, row3b, 'stage-3b');
  for (const stage of ['prepare', 'generate', 'review', 'status', 'verify-selection']) { const option = make('option', stage, controls.stage3b); option.value = stage; }
  controls.start3b = make('button', 'Start New 3B Run', row3b, 'start-3b'); controls.start3b.type = 'button';
  controls.start3b.onclick = () => {
    const stage = ['prepare', 'generate'].includes(controls.stage3b.value) ? controls.stage3b.value : 'prepare';
    const fields = stage === 'prepare' ? ['run_id', 'planning_contract'] : ['run_id', 'prepared_ref', 'planning_profile', 'runner'];
    return invoke(addOptionals({action: controls.planner.value || '3b_capability', invocation_mode: 'new', stage}, fields));
  };
  controls.runSelect = make('select', undefined, row3b, 'run-select');
  controls.runSelect.addEventListener('change', syncButtons);
  controls.resume3b = make('button', 'Resume Selected Run (preserves budget)', row3b, 'resume-3b'); controls.resume3b.type = 'button';
  controls.resume3b.onclick = () => {
    const run = selectedRun();
    if (!resumeAllowed(run)) return null;
    const stage = ['generate', 'review', 'status', 'verify-selection'].includes(controls.stage3b.value) ? controls.stage3b.value : 'status';
    const fields = ['generate', 'review'].includes(stage) ? ['prepared_ref', 'planning_profile', 'runner'] : ['prepared_ref', 'planning_profile'];
    return invoke(addOptionals({action: run.family === 'mvg-planning' ? '3b_mvg' : '3b_capability', invocation_mode: 'resume', run_id: run.run_id, stage}, fields));
  };
  controls.stageAdoption = make('select', undefined, row3b, 'stage-adoption');
  for (const stage of ['inspect', 'prepare', 'reserve', 'apply', 'verify', 'publish', 'recover-inspect', 'recover']) {
    const option = make('option', stage, controls.stageAdoption); option.value = stage;
  }
  controls.runAdoption = make('button', 'Run 3B adoption', row3b, 'run-adoption'); controls.runAdoption.type = 'button';
  controls.runAdoption.onclick = () => {
    const stage = controls.stageAdoption.value || 'inspect';
    const fields = stage === 'prepare' ? ['operation_id', 'request_ref'] : ['operation_id'];
    return invoke(addOptionals({action: '3b_adoption', stage}, fields));
  };
  const row3c = stageSection('stage_3c_tasks', 'Stage 3C · Task preview / compile (requires an adopted 3B plan)');
  controls.preview3c = make('button', 'Preview 3C Task changes', row3c, 'preview-3c'); controls.preview3c.type = 'button';
  controls.preview3c.onclick = () => invoke(addOptionals({action: '3c_task_preview'}, ['plan_id', 'run_id', 'audit_ref', 'scope_id']));
  controls.stageCompile3c = make('select', undefined, row3c, 'stage-compile-3c');
  for (const stage of ['prepare', 'inspect', 'recover-inspect', 'recover']) { const option = make('option', stage, controls.stageCompile3c); option.value = stage; }
  controls.compile3c = make('button', 'Compile 3C Tasks', row3c, 'compile-3c'); controls.compile3c.type = 'button';
  controls.compile3c.onclick = () => {
    const stage = controls.stageCompile3c.value || 'prepare';
    const fields = stage === 'prepare' ? ['operation_id', 'request_ref'] : ['operation_id'];
    return invoke(addOptionals({action: '3c_task_compile', stage}, fields));
  };
  const row6 = stageSection('stage_6_implement', 'Stage 6 · Task gate (Story 3.12 unified gate)');
  const taskRequest = extra => { const request = {action: 'chapter6', ...extra}; const id = value('task_id'); if (id) request.task_id = /^[1-9][0-9]*$/.test(id) ? Number(id) : id; return request; };
  controls.subAction6 = make('select', undefined, row6, 'sub-action-6');
  for (const subAction of ['gate', 'resume', 'route']) { const option = make('option', subAction, controls.subAction6); option.value = subAction; }
  controls.inspect6 = make('button', 'Inspect recommendation (read-only)', row6, 'inspect-6'); controls.inspect6.type = 'button';
  controls.inspect6.onclick = () => invoke(taskRequest({sub_action: controls.subAction6.value || 'gate', recommendation_only: true}));
  controls.execute6 = make('button', 'Execute Chapter 6', row6, 'execute-6'); controls.execute6.type = 'button';
  controls.execute6.onclick = () => invoke(taskRequest({sub_action: 'execute', recommendation_only: false}));
  const diagBox = markReadonly(make('div', undefined, host, 'readonly-diagnostics'));
  make('h3', 'Diagnostics (verbatim: reason_code | stage | entity_id | expected | actual | resume_ref)', diagBox);
  controls.diagnostics = make('div', undefined, diagBox, 'diagnostics');
  controls.locators = make('div', undefined, diagBox, 'locators');
  controls.result = make('p', '', diagBox, 'result'); controls.result.setAttribute('role', 'status');
  controls.actionDiagnostics = make('div', undefined, diagBox, 'action-diagnostics');
  controls.actionLocator = make('p', '', diagBox, 'action-locator');
  controls.notice = make('p', window.B_ROUTE_HONEST_NOTICE, diagBox, 'notice');
  const obsBox = markReadonly(make('details', undefined, host, 'observability'));
  obsBox.setAttribute('data-b-route-observability', 'true');
  obsBox.dataset.bRouteObservability = 'true';
  obsBox.open = false;
  make('summary', 'Process Observability & Unified Diagnostics (read-only)', obsBox);
  controls.observabilityBody = make('div', undefined, obsBox, 'observability-body');
  controls.observability = obsBox;
  async function refreshObservability() {
    try {
      const obsPayload = await window.loadBRouteObservability({params: collectFilterParams()});
      window.renderBRouteObservability(obsPayload, controls.observabilityBody);
      return obsPayload;
    } catch (error) {
      controls.observabilityBody.replaceChildren();
      make('p', error.message, controls.observabilityBody, 'observability-error');
      return null;
    }
  }
  obsBox.addEventListener('toggle', () => { if (obsBox.open) refreshObservability(); });
  syncButtons();
  const panel = {refresh, refreshObservability, invoke, controls, state: () => state, syncButtons, selectedRun};
  host.bRoutePanel = panel;
  refresh();
  return panel;
};
