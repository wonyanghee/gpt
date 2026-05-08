import { test, expect } from '@playwright/test';

test('tab flow: ALL -> TOPS -> PANTS', async ({ page }) => {
  await page.goto('/index.html');

  await expect(page.locator('#count')).toHaveText('4 ITEMS');
  await page.getByRole('button', { name: 'TOPS' }).click();
  await expect(page.locator('#count')).toHaveText('1 ITEMS');
  await page.getByRole('button', { name: 'PANTS' }).click();
  await expect(page.locator('#count')).toHaveText('1 ITEMS');
});

test('search flow: u -> ut -> utility', async ({ page }) => {
  await page.goto('/index.html');
  const input = page.getByPlaceholder('Search artifacts');

  await input.fill('u');
  await expect(page.locator('#count')).toHaveText('3 ITEMS');
  await input.fill('ut');
  await expect(page.locator('#count')).toHaveText('2 ITEMS');
  await input.fill('utility');
  await expect(page.locator('#count')).toHaveText('1 ITEMS');
});

test('mode flow: A <-> B', async ({ page }) => {
  await page.goto('/index.html');
  await expect(page.locator('body')).not.toHaveClass(/mode-b/);

  await page.getByRole('button', { name: 'B' }).click();
  await expect(page.locator('body')).toHaveClass(/mode-b/);

  await page.getByRole('button', { name: 'A' }).click();
  await expect(page.locator('body')).not.toHaveClass(/mode-b/);
});
