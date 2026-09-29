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
  let runInProgress = false;
  const selectedManifest = () => overview?.manifests.find(row => row.path === get('mvg-manifest-select').value);
  function updateRunButton() {
    const manifest = selectedManifest();
    const button = get('mvg-run');
    button.textContent = manifest ? `Run ${manifest.mvg_id} on main` : 'Run selected MVG on main';
    button.disabled = runInProgress || !manifest;
  }
  function renderVersion() {
    const version = overview.versions.find(row => row.id === get('mvg-version-select').value);
    const details = get('mvg-version-detail'); details.replaceChildren();
    if (version) {
      const heading = item('h3', version.gdd_path, details); heading.title = version.id;
      item('p', `GDD content SHA-256: ${version.gdd_sha256} · Chapter 3 trace: ${version.mapping} · main revision: ${overview.revision}`, details);
      source(version.gdd_path, details);
      if (version.mapping !== 'traced') item('p', 'Registered GDD candidate. Chapter 3 consumption and downstream ownership are not established in the published main topology.', details);
      list('Taskmaster primary IDs', version.tasks.map(task => `${task.id} · ${task.status || 'unknown'} · ${task.title || ''}`), details);
      for (const [key, label] of [['overlays', 'Overlay references'], ['contracts', 'Contract references'], ['adrs', 'ADR references']]) list(label, version.references[key] || [], details, key !== 'adrs');
      const renderScene = (scene, parent, candidate) => {
        const row = document.createElement('details'); item('summary', `${scene.path} · ${scene.classification || 'unknown'}`, row);
        item('p', candidate ? 'Candidate association from a task test reference; this does not prove static attachment or runtime reachability.' : 'Declared task association and verified static script attachment; this does not prove a runtime route.', row);
        if (candidate && scene.evidence_sources?.length) list('Evidence sources', scene.evidence_sources, row, true);
        const open = item('button', 'Open scene details', row); open.type = 'button';
        open.addEventListener('click', () => { if (window.openScenePreview) window.openScenePreview(scene.path); });
        list('Nodes', scene.nodes, row); list('Node resources', scene.resources, row, true);
        parent.append(row);
      };
      const scenes = document.createElement('details'); item('summary', `Verified static attachments (${version.scenes.length})`, scenes);
      for (const scene of version.scenes) {
        renderScene(scene, scenes, false);
      }
      details.append(scenes);
      const candidates = document.createElement('details'); item('summary', `Candidate scenes (${(version.scene_candidates || []).length})`, candidates);
      for (const scene of (version.scene_candidates || [])) renderScene(scene, candidates, true);
      details.append(candidates);
    }
  }
  function renderManifest() {
    const manifest = selectedManifest();
    updateRunButton();
    const flows = get('mvg-flow-detail'); flows.replaceChildren();
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
    get('gdd-version-status').textContent = `${payload.versions.length} registered GDD candidates · ${payload.versions.filter(row => row.mapping === 'traced').length} traced · ${payload.topology_fresh ? 'fresh topology' : 'topology unavailable or stale'}. Historical GDD revisions require published provenance.`;
    get('mvg-status').textContent = `${payload.manifests.length} cumulative MVG manifests · main revision ${payload.revision}.`;
    renderVersion();
    renderManifest();
  }
  get('mvg-version-select').addEventListener('change', renderVersion);
  get('mvg-manifest-select').addEventListener('change', renderManifest);
  get('mvg-scope-help').insertAdjacentHTML('beforeend', '<div class="mvg-scope-example"><strong>示例：m1-full 的 map-node-owned-flow</strong><p><strong>Flow</strong>：<code>map-node-owned-flow</code>，表示从 Map 选择节点，进入该节点所属流程，并回到 Map。</p><p><strong>Task IDs</strong>：<code>42, 60, 69, 97, 110</code>，指向 <code>.taskmaster/tasks/tasks_gameplay.json</code> 中的 Map 节点门控、路由所有权和状态验证任务。</p><p><strong>Handoff</strong>：Task <code>42 → 60</code>，owner 为 Task <code>60</code>，契约指向 <code>Game.Core/Contracts/Run/RunTransition.cs</code>；它表示可达节点被选中后交给 route owner，完成或拒绝都遵守同一边界。</p><p><strong>Outcome</strong>：<code>A reachable Map node enters its owned Combat/Event/Shop/Rest flow and returns through the route owner; blocked or illegal nodes leave progression unchanged with an explicit reason.</code>，这是该 Flow 要证明的行为结果。</p><p><strong>Evidence</strong>：指向 <code>map-route-domain</code>、<code>map-route-scene</code>、<code>map-state-scene</code> 三组测试，以及当前 main revision 上的 manifest 运行结果。</p></div>');
  get('mvg-scope-help-toggle').addEventListener('click', () => {
    const button = get('mvg-scope-help-toggle');
    const help = get('mvg-scope-help');
    const expanded = button.getAttribute('aria-expanded') === 'true';
    button.setAttribute('aria-expanded', String(!expanded));
    button.setAttribute('aria-label', expanded ? 'Show cumulative MVG scope help' : 'Hide cumulative MVG scope help');
    help.hidden = expanded;
  });
  get('mvg-refresh').addEventListener('click', () => load().catch(error => { get('mvg-status').textContent = error.message; }));
  get('mvg-run').addEventListener('click', async () => {
    const manifest = selectedManifest();
    if (!manifest || runInProgress) return;
    const button = get('mvg-run');
    runInProgress = true;
    button.disabled = true;
    get('mvg-manifest-select').disabled = true;
    get('mvg-status').textContent = `Running ${manifest.mvg_id} against the current main revision...`;
    try {
      const sessionResponse = await fetch('/api/knowledge/session', {cache: 'no-store'});
      if (!sessionResponse.ok) throw new Error('Unable to start a verified session');
      const session = await sessionResponse.json();
      const response = await fetch('/api/knowledge/mvg-run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-Project-Health-Token': session.token},
        body: JSON.stringify({revision: overview.revision, manifest: manifest.path})
      });
      const result = await response.json();
      if (response.status === 404) {
        get('mvg-status').textContent = `${manifest.mvg_id} cannot start: the Project Health service is running an older API. Restart the local service and reload this page.`;
        return;
      }
      const outcome = result.status || 'failed';
      const location = result.summary ? ` Summary: ${result.summary}` : '';
      const message = `${manifest.mvg_id} ${outcome}.${result.reason ? ' ' + result.reason : ''}${location}`;
      if (response.ok) {
        await load();
        get('mvg-status').textContent += ` ${message}`;
      } else {
        get('mvg-status').textContent = message;
      }
    } catch (error) {
      get('mvg-status').textContent = `${manifest.mvg_id} failed: ${error.message}`;
    } finally {
      runInProgress = false;
      get('mvg-manifest-select').disabled = false;
      updateRunButton();
    }
  });
  load().catch(error => { get('mvg-status').textContent = error.message; });
})();
