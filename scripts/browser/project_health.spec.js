const { test, expect } = require('@playwright/test');

const base = () => process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767';

const syntheticGraph = () => ({
  revision: 'synthetic-revision',
  main_scene: 'Game.Godot/Scenes/Test/Main.tscn',
  nodes: {
    'Game.Godot/Scenes/Test/Main.tscn': {
      path: 'Game.Godot/Scenes/Test/Main.tscn', classification: 'confirmed-reachable',
      nodes: [], knowledge_context: [], functional_summary: { scripts: [], config_references: [] }
    },
    'Game.Godot/Scenes/Test/Deep.tscn': {
      path: 'Game.Godot/Scenes/Test/Deep.tscn', classification: 'unreachable-candidate',
      nodes: [], knowledge_context: [], functional_summary: { scripts: [], config_references: [] }
    },
    'Game.Godot/Scenes/Test/Outside.tscn': {
      path: 'Game.Godot/Scenes/Test/Outside.tscn', classification: 'unreachable-candidate',
      nodes: [], knowledge_context: [], functional_summary: { scripts: [], config_references: [] }
    }
  },
  edges: [{
    source: 'Game.Godot/Scenes/Test/Main.tscn', target: 'Game.Godot/Scenes/Test/Deep.tscn',
    evidence_level: 'possible', kind: 'scene-reference'
  }],
  code_references: [],
  script_task_context: {},
  data_dictionary: { entries: {} },
  file_manifest: [
    'Game.Godot/Scenes/Test/Main.tscn',
    'Game.Godot/Scenes/Test/Deep.tscn',
    'Game.Godot/Scenes/Test/Outside.tscn'
  ]
});

test.describe('project health Godot scene graph', () => {
  test('renders graph controls and supports graph refresh', async ({ page }) => {
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/');
    await expect(page.getByRole('heading', { name: 'Godot scene graph' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Scene graph' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Scan local main' })).toBeVisible();
  });

  test('opens dedicated recursive scene graph and scene preview dialog', async ({ page }) => {
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/scenes');
    await expect(page.getByRole('heading', { name: 'Godot scene graph' })).toBeVisible();
    await expect(page.locator('#scene-graph')).toBeVisible();
    const scenes = page.locator('[data-scene-path]');
    await expect(scenes.first()).toBeVisible();
    await scenes.first().click();
    await expect(page.locator('#scene-preview')).toBeVisible();
  });

  test('renders route tree nodes with scene path metadata', async ({ page }) => {
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/scenes');
    const sceneNode = page.locator('[data-scene-path]').first();
    await expect(sceneNode).toBeVisible();
    await expect(sceneNode).toHaveAttribute('aria-label', /\.tscn$/);
  });

  test('supports composition type filtering and pagination controls', async ({ page }) => {
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/scenes');
    await expect(page.locator('#scene-status')).toContainText('scenes');
    await page.getByRole('button', { name: 'Scene composition' }).click();
    await expect(page.locator('#scene-structure')).toBeVisible();
    await expect(page.locator('.scene-composition-table thead')).toContainText('Data dictionary');
    await expect(page.locator('#include-unreachable')).toBeVisible();
    await page.locator('select[aria-label="Resource type"]').selectOption('script');
    await expect(page.locator('tr[data-resource-type="script"]').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Next' })).toBeVisible();
  });

  test('refreshes scene composition after a delayed graph response', async ({ page }) => {
    let releaseGraphResponse;
    const graphResponseReleased = new Promise(resolve => { releaseGraphResponse = resolve; });
    await page.route('**/api/knowledge/scene-graph', async route => {
      await graphResponseReleased;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticGraph())
      });
    });

    const baseUrl = process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767';
    await page.goto(baseUrl + '/knowledge/scenes');
    await page.getByRole('button', { name: 'Scene composition' }).click();
    await expect(page.locator('#scene-structure')).toContainText('No resources in this category.');

    releaseGraphResponse();

    await expect(page.locator('tr[data-resource-type="scene"]').first()).toBeVisible();
  });

  test('keeps the route tree active after a delayed graph response', async ({ page }) => {
    let releaseGraphResponse;
    const graphResponseReleased = new Promise(resolve => { releaseGraphResponse = resolve; });
    await page.route('**/api/knowledge/scene-graph', async route => {
      await graphResponseReleased;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticGraph())
      });
    });

    const baseUrl = process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767';
    await page.goto(baseUrl + '/knowledge/scenes');
    await expect(page.getByRole('button', { name: 'Scene route tree' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('.scene-composition-toolbar')).toBeHidden();

    releaseGraphResponse();

    await expect(page.locator('[data-scene-path]').first()).toBeVisible();
    await expect(page.locator('.scene-composition-toolbar')).toBeHidden();
  });

  test('opens separate GDD version and MVG scope panels from the scene view switcher', async ({ page }) => {
    await page.route('**/api/knowledge/mvg-overview', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        revision: 'main-revision', topology_fresh: true,
        versions: [{ id: 'gdd@hash', gdd_path: 'docs/gdd/test.md', gdd_sha256: 'a'.repeat(64), mapping: 'traced', tasks: [], references: {}, scenes: [], scene_candidates: [{ path: 'Game.Godot/Scenes/Candidate.tscn', classification: 'unreachable-candidate', nodes: [], resources: [], evidence_sources: ['Tests.Godot/tests/Integration/test_candidate.gd'] }] }],
        manifests: [{ path: 'docs/testing/mvg/test.json', mvg_id: 'test-scope', sha256: 'sha256:test', coverage: { mode: 'pilot', blocking_task_ids: [] }, evidence: { status: 'not_verified' }, flows: [], tests: [] }]
      })
    }));
    await page.goto(base() + '/knowledge/scenes');
    await expect(page.locator('#mvg-versions')).toBeHidden();
    await page.getByRole('button', { name: 'GDD versions and MVG' }).click();
    await expect(page.locator('#scene-graph')).toBeHidden();
    await expect(page.locator('#mvg-versions')).toBeVisible();
    await expect(page.locator('#gdd-version-panel')).toContainText('docs/gdd/test.md');
    await expect(page.locator('#gdd-version-panel')).toContainText('Candidate scenes (1)');
    await expect(page.locator('#gdd-version-panel')).toContainText('Game.Godot/Scenes/Candidate.tscn');
    await expect(page.locator('#mvg-scope-panel')).toContainText('test-scope');
    await expect(page.locator('#mvg-scope-help-toggle')).toBeVisible();
    await expect(page.locator('#mvg-scope-help')).toBeHidden();
    await page.locator('#mvg-scope-help-toggle').click();
    await expect(page.locator('#mvg-scope-help')).toBeVisible();
    await expect(page.locator('#mvg-scope-help')).toContainText('累计的 MVG');
    await page.locator('#mvg-scope-help-toggle').click();
    await expect(page.locator('#mvg-scope-help')).toBeHidden();
    await page.getByRole('button', { name: 'Scene route tree' }).click();
    await expect(page.locator('#mvg-versions')).toBeHidden();
  });

  test('runs selected MVG scope from the main revision shown on the page', async ({ page }) => {
    await page.route('**/api/knowledge/mvg-overview', route => route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({revision: 'a'.repeat(40), topology_fresh: true, versions: [], manifests: [
        {path: 'docs/testing/mvg/m1-critical.json', mvg_id: 'm1-critical', sha256: 'sha256:test', coverage: {mode: 'critical', blocking_task_ids: []}, evidence: {status: 'not_verified'}, flows: [], tests: []},
        {path: 'docs/testing/mvg/reward-pilot.json', mvg_id: 'reward-pilot', sha256: 'sha256:pilot', coverage: {mode: 'pilot', blocking_task_ids: []}, evidence: {status: 'not_verified'}, flows: [], tests: []},
        {path: 'docs/testing/mvg/m1-full.json', mvg_id: 'm1-full', sha256: 'sha256:full', coverage: {mode: 'full', blocking_task_ids: []}, evidence: {status: 'not_verified'}, flows: [], tests: []}
      ]})
    }));
    await page.route('**/api/knowledge/session', route => route.fulfill({
      status: 200, contentType: 'application/json', body: JSON.stringify({token: 'test-token'})
    }));
    let requestBody;
    await page.route('**/api/knowledge/mvg-run', async route => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({status: 404, contentType: 'application/json', body: JSON.stringify({reason: 'Not found'})});
    });
    await page.goto(base() + '/knowledge/scenes');
    await page.getByRole('button', {name: 'GDD versions and MVG'}).click();
    await expect(page.locator('#mvg-run')).toHaveText('Run m1-critical on main');
    await page.locator('#mvg-manifest-select').selectOption('docs/testing/mvg/reward-pilot.json');
    await expect(page.locator('#mvg-run')).toHaveText('Run reward-pilot on main');
    await page.locator('#mvg-run').click();
    await expect(page.locator('#mvg-status')).toContainText('reward-pilot cannot start');
    await expect(page.locator('#mvg-run')).toBeEnabled();
    expect(requestBody).toEqual({revision: 'a'.repeat(40), manifest: 'docs/testing/mvg/reward-pilot.json'});
    await page.locator('#mvg-manifest-select').selectOption('docs/testing/mvg/m1-full.json');
    await expect(page.locator('#mvg-run')).toHaveText('Run m1-full on main');
  });

  test('shows the full route-tree closure by default and adds outside scenes only on request', async ({ page }) => {
    await page.route('**/api/knowledge/scene-graph', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(syntheticGraph())
    }));

    const baseUrl = base();
    const deepScenePath = 'Game.Godot/Scenes/Test/Deep.tscn';
    const outsideScenePath = 'Game.Godot/Scenes/Test/Outside.tscn';

    await page.goto(baseUrl + '/knowledge/scenes');
    await expect(page.locator('#scene-status')).toContainText('scenes');
    await page.getByRole('button', { name: 'Scene composition' }).click();

    const deepRouteScene = page.locator(`tr[data-resource-path="${deepScenePath}"]`);
    const outsideRouteScene = page.locator(`tr[data-resource-path="${outsideScenePath}"]`);

    await expect(deepRouteScene).toBeVisible();
    await expect(outsideRouteScene).toHaveCount(0);

    await page.locator('#include-unreachable').check();
    await expect(outsideRouteScene).toBeVisible();
  });

  test('opens dedicated unconfirmed scene page and filters entries', async ({ page }) => {
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/scenes/unreachable');
    await expect(page.getByRole('heading', { name: 'Unconfirmed Godot scenes' })).toBeVisible();
    await expect(page.locator('#scene-filter')).toBeVisible();
    await page.locator('#scene-filter').selectOption('with-scripts');
    await expect(page.locator('#scene-list')).toBeVisible();
  });

  test('restart probe posts to scan endpoint', async ({ page }) => {
    await page.route('**/api/knowledge/scan', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
    });
    await page.goto((process.env.PROJECT_HEALTH_URL || 'http://127.0.0.1:8767') + '/knowledge/scenes');
    const request = page.waitForRequest(request => request.url().endsWith('/api/knowledge/scan') && request.method() === 'POST');
    await page.locator('#scene-probe').click();
    await request;
  });
});


test.describe('project health semantic topology', () => {
  test('renders legacy main topology and keeps workspace identity explicit', async ({ page }) => {
    await page.route('**/api/knowledge/topology?mode=main', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: false,
        fresh: false,
        identity: { kind: 'main', revision: 'main-revision' },
        status: 'legacy_unmapped',
        reason: 'topology unavailable',
        nodes: { source_blocks: [], requirements: [], capabilities: [], tasks: [], acceptance: [] },
        edges: [], task_trace: {}, summary: {}, problems: []
      })
    }));
    await page.route('**/api/knowledge/topology?mode=workspace', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: true,
        fresh: true,
        identity: { kind: 'workspace', revision: 'workspace:test' },
        status: 'fresh',
        nodes: { source_blocks: [], requirements: [], capabilities: [], tasks: [], acceptance: [] },
        edges: [], task_trace: {}, summary: {}, problems: []
      })
    }));

    await page.goto(base() + '/knowledge/topology');
    await expect(page.getByRole('heading', { name: 'Design → Delivery Topology' })).toBeVisible();
    await expect(page.locator('#topology-status')).toContainText('main');
    await expect(page.locator('#topology-status')).toContainText('topology unavailable');

    await page.locator('#topology-identity').selectOption('workspace');
    await expect(page.locator('#topology-status')).toContainText('workspace:test');
  });

  test('switches workspace attempt, latest successful, and Chapter 5 stabilized independently', async ({ page }) => {
    await page.route('**/api/knowledge/topology?mode=workspace&view=attempt', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: true,
        fresh: false,
        identity: { kind: 'workspace', revision: 'workspace:attempt', trigger_run_id: 'run-fail' },
        workspace_view: 'last_attempt',
        status: 'concern',
        nodes: { source_blocks: [], requirements: [], capabilities: [], tasks: [], acceptance: [] },
        edges: [], task_trace: {}, summary: {}, problems: [{ kind: 'orphan_delivery_requirements', count: 1 }]
      })
    }));
    await page.route('**/api/knowledge/topology?mode=workspace&view=stable', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: true,
        fresh: true,
        identity: { kind: 'workspace', revision: 'workspace:stable', trigger_run_id: 'run-pass' },
        workspace_view: 'latest_successful',
        status: 'passed',
        nodes: { source_blocks: [], requirements: [], capabilities: [], tasks: [], acceptance: [] },
        edges: [], task_trace: {}, summary: {}, problems: []
      })
    }));
    await page.route('**/api/knowledge/topology?mode=workspace&view=stabilized', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: true,
        fresh: true,
        identity: { kind: 'workspace', revision: 'workspace:chapter5', trigger_run_id: 'run-ch5' },
        workspace_view: 'stabilized',
        status: 'passed',
        chapter_run: { source: 'chapter5', reconciliation_status: 'stabilized', readiness: 'READY' },
        nodes: { source_blocks: [], requirements: [], capabilities: [], tasks: [], acceptance: [] },
        edges: [], task_trace: {}, summary: { chapter5_reconciliation_status: 'stabilized', chapter5_readiness: 'READY' }, problems: []
      })
    }));

    await page.goto(base() + '/knowledge/topology?mode=workspace&view=attempt');
    await expect(page.locator('#workspace-view-label')).toBeVisible();
    await expect(page.locator('#topology-status')).toContainText('workspace:attempt');
    await expect(page.locator('#topology-problems')).toContainText('orphan_delivery_requirements');

    await page.locator('#workspace-view').selectOption('stable');
    await expect(page.locator('#topology-status')).toContainText('workspace:stable');
    await expect(page.locator('#topology-problems')).not.toContainText('orphan_delivery_requirements');

    await page.locator('#workspace-view').selectOption('stabilized');
    await expect(page.locator('#topology-status')).toContainText('workspace:chapter5');
    await expect(page.locator('#topology-summary')).toContainText('chapter5_reconciliation_status: stabilized');
  });

  test('scene preview exposes design trace as navigation only', async ({ page }) => {
    const graph = syntheticGraph();
    graph.design_trace = {
      'Game.Godot/Scenes/Test/Main.tscn': {
        tasks: [{ task_id: '7', title: 'Test task', status: 'pending' }],
        capabilities: ['CAP-TEST'],
        requirements: ['FR-TEST-001'],
        source_blocks: ['SB-GDD-001'],
        evidence_levels: ['static_attached'],
        semantic_claim: 'navigation_only'
      }
    };
    await page.route('**/api/knowledge/scene-graph', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(graph)
    }));

    await page.goto(base() + '/knowledge/scenes');
    const scene = page.locator('[data-scene-path="Game.Godot/Scenes/Test/Main.tscn"]').first();
    await expect(scene).toBeVisible();
    await scene.click();
    await expect(page.locator('#scene-preview')).toBeVisible();
    await expect(page.locator('#scene-preview')).toContainText('Trace to design');
    await expect(page.locator('#scene-preview')).toContainText('FR-TEST-001');
    await expect(page.locator('#scene-preview')).toContainText('not acceptance proof');
    const requirementLink = page.locator('#scene-preview a[data-topology-kind="requirement"][data-topology-id="FR-TEST-001"]');
    await expect(requirementLink).toBeVisible();
    await expect(requirementLink).toHaveAttribute('href', /\/knowledge\/topology\?.*focus=requirement%3AFR-TEST-001/);
    await expect(page.locator('#scene-preview a[data-topology-kind="task"][data-topology-id="7"]')).toBeVisible();
    await expect(page.locator('#scene-preview a[data-topology-kind="capability"][data-topology-id="CAP-TEST"]')).toBeVisible();
    await expect(page.locator('#scene-preview a[data-topology-kind="source_block"][data-topology-id="SB-GDD-001"]')).toBeVisible();
  });


  test('renders acceptance nodes and uses backend orphan semantics', async ({ page }) => {
    await page.route('**/api/knowledge/topology?mode=main', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema_version: 'newrouge.semantic-topology-view.v1',
        available: true,
        fresh: true,
        identity: { kind: 'main', revision: 'main-revision' },
        status: 'fresh',
        nodes: {
          source_blocks: [{ block_id: 'SB-1', source_path: 'docs/gdd/a.md', line_start: 1, line_end: 1 }],
          requirements: [{
            requirement_id: 'FR-ORPHAN',
            source_block_ids: ['SB-1'],
            topology_states: ['orphan'],
            sink_resolved: false
          }],
          capabilities: [{ capability_id: 'CAP-ORPHAN', requirement_ids: ['FR-ORPHAN'] }],
          tasks: [{ task_id: '7', title: 'Task 7', status: 'pending' }],
          acceptance: [{
            acceptance_id: 'AC-T7-abc',
            task_id: '7',
            statement: 'Must work',
            topology_origin: 'unmapped'
          }]
        },
        edges: [{
          source_type: 'requirement', source_id: 'FR-ORPHAN',
          target_type: 'capability', target_id: 'CAP-ORPHAN',
          relation: 'grouped_by'
        }],
        task_trace: {
          '7': {
            source_blocks: ['SB-1'], requirements: ['FR-ORPHAN'],
            capabilities: ['CAP-ORPHAN'], acceptance: ['AC-T7-abc']
          }
        },
        summary: { orphan_requirements: 1, acceptance_with_semantic_origin: 0 },
        problems: []
      })
    }));

    await page.goto(base() + '/knowledge/topology?mode=main&focus=acceptance%3AAC-T7-abc');
    const acceptance = page.locator('details[data-topology-kind="acceptance"][data-topology-id="AC-T7-abc"]');
    await expect(acceptance).toBeVisible();
    await expect(acceptance).toHaveJSProperty('open', true);

    await page.locator('#filter-state').selectOption('orphan');
    const orphan = page.locator('details[data-topology-kind="requirement"][data-topology-id="FR-ORPHAN"]');
    await expect(orphan).toBeVisible();
    await expect(page.locator('details[data-topology-kind="capability"]')).toHaveCount(0);
  });

  test('shows Chinese state labels and filters normal nodes with contextual help', async ({ page }) => {
    await page.route('**/api/knowledge/topology?mode=main', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        available: true,
        fresh: true,
        identity: { kind: 'main', revision: 'main-revision' },
        status: 'fresh',
        nodes: {
          requirements: [{ requirement_id: 'FR-NORMAL', topology_states: [], sink_resolved: true }],
          capabilities: [{ capability_id: 'CAP-NORMAL' }]
        },
        edges: [],
        summary: {},
        problems: []
      })
    }));

    await page.goto(base() + '/knowledge/topology?mode=main');
    const state = page.locator('#filter-state');
    await expect(state.locator('option')).toHaveText(['全部', '正常', '孤立', '未解决', '过期']);
    await state.selectOption('normal');
    await expect(page.locator('#filter-state-help')).toHaveText('正常：拓扑新鲜，且节点没有孤立、未解决或过期标记。');
    await expect(page.locator('details[data-topology-id="FR-NORMAL"]')).toBeVisible();
    await expect(page.locator('details[data-topology-id="CAP-NORMAL"]')).toBeVisible();
  });
});
