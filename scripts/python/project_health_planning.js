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
    const hasProgress = Boolean(document.getElementById('mvg-committed-progress'));
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
