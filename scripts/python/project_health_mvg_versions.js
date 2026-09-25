/* Read-only main snapshot navigation; render all repository text with textContent. */
(() => {
  const get = id => document.getElementById(id);
  const item = (tag, content, parent) => { const node = document.createElement(tag); node.textContent = String(content ?? ''); parent.append(node); return node; };
  const source = (path, parent) => { const link = item('a', path, parent); link.href = '/api/knowledge/source?path=' + encodeURIComponent(path); link.target = '_blank'; link.rel = 'noopener'; return link; };
  const list = (label, values, parent, links = false) => {
    const group = document.createElement('details'); group.open = false;
    item('summary', `${label} (${values.length})`, group);
    for (const value of values) { const line = document.createElement('p'); if (links && value.includes('/')) source(value, line); else item('span', value, line); group.append(line); }
    parent.append(group);
  };
  let overview;
  function render() {
    const version = overview.versions.find(row => row.id === get('mvg-version-select').value);
    const manifest = overview.manifests.find(row => row.path === get('mvg-manifest-select').value);
    const details = get('mvg-version-detail'); const flows = get('mvg-flow-detail'); details.replaceChildren(); flows.replaceChildren();
    if (version) {
      const heading = item('h3', version.gdd_path, details); heading.title = version.id;
      item('p', `GDD content SHA-256: ${version.gdd_sha256} · Chapter 3 trace: ${version.mapping} · main revision: ${overview.revision}`, details);
      source(version.gdd_path, details);
      if (version.mapping !== 'traced') item('p', 'Registered GDD candidate. Chapter 3 consumption and downstream ownership are not established in the published main topology.', details);
      list('Taskmaster primary IDs', version.tasks.map(task => `${task.id} · ${task.status || 'unknown'} · ${task.title || ''}`), details);
      for (const [key, label] of [['overlays', 'Overlay references'], ['contracts', 'Contract references'], ['adrs', 'ADR references']]) list(label, version.references[key] || [], details, key !== 'adrs');
      const scenes = document.createElement('details'); item('summary', `Statically attached scenes (${version.scenes.length})`, scenes);
      for (const scene of version.scenes) {
        const row = document.createElement('details'); item('summary', `${scene.path} · ${scene.classification || 'unknown'}`, row);
        item('p', 'Declared task association and verified static script attachment; this does not prove a runtime route.', row);
        const open = item('button', 'Open scene details', row); open.type = 'button';
        open.addEventListener('click', () => { if (window.openScenePreview) window.openScenePreview(scene.path); });
        list('Nodes', scene.nodes, row); list('Node resources', scene.resources, row, true); scenes.append(row);
      }
      details.append(scenes);
    }
    if (!manifest) { item('p', 'No MVG manifest in the scanned main snapshot.', flows); return; }
    const coverage = manifest.coverage || {};
    item('p', `${manifest.mvg_id} · ${coverage.mode || 'unknown'} · ${manifest.evidence.status} · blocking tasks: ${(coverage.blocking_task_ids || []).join(', ') || 'none'}`, flows);
    item('p', `Runtime evidence: ${manifest.evidence.reason || manifest.evidence.run_id || 'none'} · manifest SHA-256: ${manifest.sha256}`, flows);
    if (coverage.blocking_task_ids?.length) item('p', 'The manifest declares blocking tasks. Full playable scope is not cleared by a partial run.', flows);
    for (const flow of manifest.flows) {
      const row = document.createElement('details');
      item('summary', `${flow.id} · tasks ${flow.task_ids.join(', ') || 'unmapped'} · ${flow.version_ids.length ? flow.version_ids.length + ' traced version(s)' : 'no traced version'}`, row);
      item('p', flow.outcome, row);
      item('p', 'Related versions: ' + (flow.version_ids.join(' · ') || 'not mapped; cumulative flow remains in scope'), row);
      item('p', 'Tests: ' + (flow.test_ids.join(', ') || 'none declared'), row);
      for (const handoff of flow.handoffs || []) {
        const block = document.createElement('p'); item('strong', `Task ${handoff.producer_task} → ${handoff.consumer_task} · owner ${handoff.owner_task} · `, block);
        item('span', `${handoff.behavior || ''} · contract: `, block);
        if (handoff.contract_ref) source(handoff.contract_ref, block); else item('span', 'unmapped', block);
        item('span', ` · tests: ${(handoff.test_ids || []).join(', ') || 'none'}`, block); row.append(block);
      }
      flows.append(row);
    }
    list('Declared tests and evidence levels', manifest.tests.map(test => `${test.id} · ${test.evidence_level || test.state || 'unclassified'} · ${test.path || ''}`), flows);
    item('p', 'Human playcheck: verify the selected flow in Godot, the handoff behavior, save/continue or return path, and any dynamic routes. Static reachability and automated success do not establish subjective playability.', flows);
  }
  async function load() {
    get('mvg-status').textContent = 'Loading version evidence...';
    const response = await fetch('/api/knowledge/mvg-overview'); const payload = await response.json();
    if (!response.ok) throw new Error(payload.reason || 'Unable to load MVG evidence');
    overview = payload;
    for (const [id, rows, value, label] of [['mvg-version-select', payload.versions, 'id', 'gdd_path'], ['mvg-manifest-select', payload.manifests, 'path', 'mvg_id']]) {
      const selector = get(id); const previous = selector.value; selector.replaceChildren();
      for (const row of rows) { const option = item('option', row[label] + (value === 'id' ? ' @' + row.gdd_sha256.slice(0, 12) : ''), selector); option.value = row[value]; }
      if (rows.some(row => row[value] === previous)) selector.value = previous;
    }
    get('mvg-status').textContent = `${payload.versions.length} registered GDD candidates · ${payload.versions.filter(row => row.mapping === 'traced').length} traced · ${payload.manifests.length} cumulative MVG manifests · ${payload.topology_fresh ? 'fresh topology' : 'topology unavailable or stale'}. Historical GDD revisions require published provenance.`;
    render();
  }
  get('mvg-version-select').addEventListener('change', render);
  get('mvg-manifest-select').addEventListener('change', render);
  get('mvg-refresh').addEventListener('click', () => load().catch(error => { get('mvg-status').textContent = error.message; }));
  load().catch(error => { get('mvg-status').textContent = error.message; });
})();
