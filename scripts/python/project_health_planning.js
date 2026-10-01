'use strict';
// Both pages use the same authenticated async job and compact result contract.
window.knowledgePlanning = async function ({action, manifest, button, status, refresh}) {
  const message = (text, state) => {
    status.textContent = String(text || 'Planning failed').replace(/\s+/g, ' ').slice(0, 360);
    status.dataset.result = state;
  };
  button.disabled = true;
  message(`Generating ${action === 'capability' ? 'Capability' : 'MVG'} from committed main...`, 'running');
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
      message(`${action === 'capability' ? 'Capability' : 'MVG'} · ${result.stage || 'prepare'} · main ${(result.revision || '').slice(0, 12)}`, 'running');
      await new Promise(resolve => setTimeout(resolve, 2000));
      const poll = await fetch('/api/knowledge/planning?job_id=' + encodeURIComponent(result.job_id), {cache: 'no-store'});
      result = await poll.json();
      if (!poll.ok) throw new Error(result.reason || 'Unable to read planning result');
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
