import {test, expect, type Page} from '@playwright/test';
import {readFile} from 'node:fs/promises';

async function login(page: Page, role: string) {
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill(`synthetic.${role}.a`);
  await page.getByLabel('Mot de passe', {exact: true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button', {name: 'Connexion', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Tableau de bord', exact: true})).toBeVisible();
}

test('reviewed operational physical import appears in clients and dashboard', async ({page, browser}) => {
  test.setTimeout(120000);
  test.skip(!process.env.AICED_E2E_ISOLATED || !process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated synthetic database only');
  const expected = JSON.parse(await readFile('../.local/compose-test/import-dashboard-expected.json', 'utf8'));
  const email = expected.physical.cells['15'];
  await login(page, 'operator');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const org = context.organizations.find((value: {upload: boolean}) => value.upload).id;
  const before = await (await page.request.get('/api/clients/?page_size=1')).json();
  const csrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const root = `/api/imports/${org}/`;
  const upload = await page.request.post(root + 'upload/?source_as_of=2026-03-01&snapshot_kind=partial&date_format=DMY&data_scope=operational', {
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/octet-stream'},
    data: await readFile('../.local/ui-review/synthetic-review-physical.xlsx'),
  });
  expect(upload.status()).toBe(201);
  const batch = await upload.json();
  const reviewerContext = await browser.newContext({baseURL: process.env.AICED_E2E_URL});
  try {
    const reviewer = await reviewerContext.newPage();
    await login(reviewer, 'reviewer');
    const token = (await (await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    expect((await reviewer.request.post(root + `batches/${batch.id}/publish/`, {headers: {'X-CSRFToken': token}, data: {}})).status()).toBe(200);
  } finally { await reviewerContext.close(); }
  await expect.poll(async () => {
    const response = await page.request.get(`/api/clients/operational-import-jobs/${batch.id}/?organization_id=${org}`);
    return response.ok() ? (await response.json()).status : `http-${response.status()}`;
  }, {timeout: 45000}).toBe('complete');
  let found = '';
  await expect.poll(async () => {
    const list = await (await page.request.get('/api/clients/?search=PERSONNE%20SYNTHETIQUE&page_size=50')).json();
    for (const client of list.results) {
      const response = await page.request.get(`/api/clients/${client.id}/workspace/`);
      if (response.ok() && (await response.json()).crm.email === email) { found = client.id; return true; }
    }
    return false;
  }, {timeout: 45000}).toBe(true);
  await page.goto(`/clients/${found}`);
  await expect(page.getByText(email, {exact: true})).toBeVisible();
  await expect(page.getByText('2000-01-02', {exact: true})).toBeVisible();
  await page.goto('/');
  const count = (await (await page.request.get('/api/clients/?page_size=1')).json()).count;
  expect(count).toBeGreaterThan(before.count);
  await expect(page.getByRole('article', {name: 'Clients accessibles'}).locator('strong')).toHaveText(new Intl.NumberFormat('fr-FR').format(count));
  const accountUpload = await page.request.post(root + 'upload/?source_as_of=2026-03-01&snapshot_kind=partial&date_format=DMY&data_scope=operational', {
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/octet-stream'},
    data: await readFile('../.local/ui-review/synthetic-review-accounts.xlsx'),
  });
  expect(accountUpload.status()).toBe(201);
  const accountBatch = await accountUpload.json();
  const accountReview = await browser.newContext({baseURL: process.env.AICED_E2E_URL});
  try {
    const reviewer = await accountReview.newPage();
    await login(reviewer, 'reviewer');
    const token = (await (await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    expect((await reviewer.request.post(root + `batches/${accountBatch.id}/publish/`, {headers: {'X-CSRFToken': token}, data: {}})).status()).toBe(200);
  } finally { await accountReview.close(); }
  await expect.poll(async () => {
    const response = await page.request.get(`/api/clients/operational-import-jobs/${accountBatch.id}/?organization_id=${org}`);
    return response.ok() ? (await response.json()).status : `http-${response.status()}`;
  }, {timeout: 45000}).toBe('complete');
  await page.goto(`/clients/${found}`);
  await expect(page.getByText(`Compte ${expected.accounts.cells['5']}`, {exact: true})).toBeVisible();
});

test('reviewed operational company appears in the client list', async ({page, browser}) => {
  test.setTimeout(120000);
  test.skip(!process.env.AICED_E2E_ISOLATED || !process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated synthetic database only');
  const expected = JSON.parse(await readFile('../.local/compose-test/import-dashboard-expected.json', 'utf8'));
  const name = expected.legal.cells['4'];
  await login(page, 'operator');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const org = context.organizations.find((value: {upload: boolean}) => value.upload).id;
  const csrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const root = `/api/imports/${org}/`;
  const upload = await page.request.post(root + 'upload/?source_as_of=2026-03-01&snapshot_kind=partial&date_format=DMY&data_scope=operational', {
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/octet-stream'},
    data: await readFile('../.local/ui-review/synthetic-review-legal.xlsx'),
  });
  expect(upload.status()).toBe(201);
  const batch = await upload.json();
  const reviewContext = await browser.newContext({baseURL: process.env.AICED_E2E_URL});
  try {
    const reviewer = await reviewContext.newPage();
    await login(reviewer, 'reviewer');
    const token = (await (await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    expect((await reviewer.request.post(root + `batches/${batch.id}/publish/`, {headers: {'X-CSRFToken': token}, data: {}})).status()).toBe(200);
  } finally { await reviewContext.close(); }
  await expect.poll(async () => {
    const response = await page.request.get(`/api/clients/operational-import-jobs/${batch.id}/?organization_id=${org}`);
    return response.ok() ? (await response.json()).status : `http-${response.status()}`;
  }, {timeout: 45000}).toBe('complete');
  let found = '';
  await expect.poll(async () => {
    const list = await (await page.request.get(`/api/clients/?search=${encodeURIComponent(name)}&page_size=50`)).json();
    const client = list.results.find((item: {display_name: string}) => item.display_name === name);
    if (client) { found = client.id; return true; }
    return false;
  }, {timeout: 45000}).toBe(true);
  await page.goto(`/clients/${found}`);
  await expect(page.getByRole('heading', {name, exact: true})).toBeVisible();
  await expect(page.getByText('+21611111111', {exact: true})).toBeVisible();
});

test('a source row without a name is shown by its source identifier', async ({page, browser}) => {
  test.setTimeout(120000);
  test.skip(!process.env.AICED_E2E_ISOLATED || !process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated synthetic database only');
  const expected = JSON.parse(await readFile('../.local/compose-test/import-dashboard-expected.json', 'utf8'));
  const sourceId = expected.physical_no_name.cells['2'];
  await login(page, 'operator');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const org = context.organizations.find((value: {upload: boolean}) => value.upload).id;
  const csrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const root = `/api/imports/${org}/`;
  const upload = await page.request.post(root + 'upload/?source_as_of=2026-03-01&snapshot_kind=partial&date_format=DMY&data_scope=operational', {
    headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/octet-stream'},
    data: await readFile('../.local/ui-review/synthetic-review-physical-no-name.xlsx'),
  });
  expect(upload.status()).toBe(201);
  const batch = await upload.json();
  const reviewContext = await browser.newContext({baseURL: process.env.AICED_E2E_URL});
  try {
    const reviewer = await reviewContext.newPage();
    await login(reviewer, 'reviewer');
    const token = (await (await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    expect((await reviewer.request.post(root + `batches/${batch.id}/publish/`, {headers: {'X-CSRFToken': token}, data: {}})).status()).toBe(200);
  } finally { await reviewContext.close(); }
  let found = '';
  await expect.poll(async () => {
    const list = await (await page.request.get(`/api/clients/?search=${encodeURIComponent(sourceId)}&page_size=50`)).json();
    const client = list.results.find((item: {display_name: string}) => item.display_name === `Identifiant source · ${sourceId}`);
    if (client) { found = client.id; return true; }
    return false;
  }, {timeout: 45000}).toBe(true);
  await page.goto(`/clients/${found}`);
  await expect(page.getByText('2000-01-02', {exact: true})).toBeVisible();
});
