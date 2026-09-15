const { test, expect } = require('@playwright/test');

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
