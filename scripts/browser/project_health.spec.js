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
