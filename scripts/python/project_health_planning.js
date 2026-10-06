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
    root.inert = active;
    overlay.hidden = !active;
    overlay.style.display = active ? 'grid' : 'none';
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
  button.disabled = true;
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
    while (result.status === 'queued' || result.status === 'running') {
      message(`${action === 'capability' ? 'Capability' : 'MVG'} · ${result.stage || 'prepare'} · local ${(result.revision || '').slice(0, 12)}`, 'running');
      await new Promise(resolve => setTimeout(resolve, 2000));
      const poll = await fetch('/api/knowledge/planning?job_id=' + encodeURIComponent(result.job_id), {cache: 'no-store'});
      result = await poll.json();
      if (!poll.ok) throw new Error(result.reason || 'Unable to read planning result');
    }
    if (result.status === 'recoverable') {
      // Candidate and review artifacts are durable.  Keep the result visible
      // as resumable instead of presenting a terminal failure; clicking the
      // same action again resumes from the reported stage.
      message(result.message || 'Planning can be resumed', 'recoverable');
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
    button.disabled = false;
  }
};
