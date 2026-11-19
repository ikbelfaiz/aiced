import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('dashboard shows published rows only and hides failed source data', async ({ page }) => {
  await page.route('**/api/imports/context/', route => route.fulfill({ json: {
    organizations: [{ id: 'synthetic-org', name: 'Organisation synthétique', upload: true, approve: false, policy_manage: false }],
    templates: {}, mode: 'immutable_snapshots_only',
  } }));
  await page.route(url => url.pathname === '/api/imports/synthetic-org/batches/', route => route.fulfill({ json: {
    count: 2, next: null, previous: null, results: [
      { id: 'published-batch', status: 'published', template: 'legal', source_as_of: '2026-01-01', data_scope: 'synthetic', published_rows: 1, published_at: '2026-01-02T10:00:00Z' },
      { id: 'staged-batch', status: 'staged', template: 'physical', source_as_of: '2026-01-01', data_scope: 'synthetic', published_rows: 0 },
    ],
  } }));
  await page.route('**/api/imports/synthetic-org/batches/published-batch/**', route => route.fulfill({ json: {
    batch: { id: 'published-batch', status: 'published' }, headers: ['Identifiant', 'Nom'],
    count: 2, next: null, previous: null, history: [],
    results: [
      { id: 'valid-row', number: 2, cells: { '1': 'SYNTH-VALID', '2': 'Publié' }, errors: [], warnings: [], normalized_dates: {} },
      { id: 'rejected-row', number: 3, cells: { '1': 'SYNTH-REJECTED', '2': 'Rejeté' }, errors: ['Identifiant invalide'], warnings: [], normalized_dates: {} },
    ],
  } }));
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe', { exact: true }).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  const panel = page.getByRole('region', { name: 'Données importées publiées' });
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Personnes physiques', { exact: false })).toHaveCount(0);
  await panel.getByRole('button', { name: /Personnes morales/ }).click();
  await expect(panel.getByText('SYNTH-VALID')).toBeVisible();
  await expect(panel.getByText('SYNTH-REJECTED')).toHaveCount(0);
  await page.unroute('**/api/imports/synthetic-org/batches/published-batch/**');
  await page.route('**/api/imports/synthetic-org/batches/published-batch/**', route => route.fulfill({ status: 503, json: {} }));
  await panel.getByRole('button', { name: /Personnes morales/ }).click();
  // Switching pages triggers a fresh read; failed reads never display cached rows.
  await page.reload();
  await panel.getByRole('button', { name: /Personnes morales/ }).click();
  await expect(panel.getByText('Lignes inaccessibles')).toBeVisible();
  await expect(panel.getByText('SYNTH-VALID')).toHaveCount(0);
});

test('dashboard reads a reviewer-published synthetic workbook from the real API', async ({ page, browser }) => {
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated test stack only');
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe', { exact: true }).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Tableau de bord', exact: true })).toBeVisible();
  const context = await (await page.request.get('/api/imports/context/')).json();
  const organization = context.organizations.find((item: { upload: boolean }) => item.upload).id;
  const root = `/api/imports/${organization}/`;
  const csrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const upload = await page.request.post(root + 'upload/?source_as_of=2026-02-20&snapshot_kind=partial&date_format=ISO&data_scope=synthetic', {
    headers: { 'X-CSRFToken': csrf, 'Content-Type': 'application/octet-stream' },
    data: await readFile('../.local/ui-review/synthetic-review-legal.xlsx'),
  });
  expect(upload.status()).toBe(201);
  const batch = await upload.json();
  const reviewContext = await browser.newContext({ baseURL: process.env.AICED_E2E_URL });
  try {
    const reviewer = await reviewContext.newPage();
    await reviewer.goto('/connexion');
    await reviewer.getByLabel('Identifiant professionnel').fill('synthetic.reviewer.a');
    await reviewer.getByLabel('Mot de passe', { exact: true }).fill(process.env.AICED_E2E_PASSWORD!);
    await reviewer.getByRole('button', { name: 'Connexion', exact: true }).click();
    await expect(reviewer.getByRole('heading', { name: 'Tableau de bord', exact: true })).toBeVisible();
    const reviewCsrf = (await (await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    expect((await reviewer.request.post(root + `batches/${batch.id}/publish/`, { headers: { 'X-CSRFToken': reviewCsrf }, data: {} })).status()).toBe(200);
  } finally { await reviewContext.close(); }
  const preview = await (await page.request.get(root + `batches/${batch.id}/`)).json();
  const sourceKey = preview.results[0].cells['2'];
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Données importées publiées' });
  await panel.getByRole('button', { name: /Personnes morales · situation 2026-02-20/ }).first().click();
  await expect(panel.getByText(sourceKey, { exact: true })).toBeVisible();
});
