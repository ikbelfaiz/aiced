import {test,expect,type Page} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';

async function login(page:Page,role:string){
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill(`synthetic.${role}.a`);
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
}

test('Home dashboard uses authorized persisted CRM counts and hides failed sources',async({page})=>{
  await login(page,'operator');
  const clients=await(await page.request.get('/api/clients/?page_size=1')).json();
  const opportunities=await(await page.request.get('/api/opportunities/?page_size=1')).json();
  await expect(page.getByRole('article',{name:'Clients accessibles'}).locator('strong')).toHaveText(new Intl.NumberFormat('fr-FR').format(clients.count));
  await expect(page.getByRole('region',{name:'Opportunités actuelles'})).toContainText(`${opportunities.count} opportunité(s)`);
  await expect(page.getByRole('img',{name:'Graphique des interactions enregistrées par jour'})).toBeVisible();
  await expect(page.getByText('Valorisations financières indisponibles')).toBeVisible();
  await page.route('**/api/opportunities/?page_size=1',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.getByRole('button',{name:'Actualiser',exact:true}).click();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'})).toContainText('Données indisponibles');
  await expect(page.getByRole('img',{name:'Graphique des interactions enregistrées par jour'})).toBeVisible();
  await page.unroute('**/api/opportunities/?page_size=1');
  await page.getByRole('button',{name:'Actualiser',exact:true}).click();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'})).toContainText(`${opportunities.count} opportunité(s)`);
  await page.screenshot({path:'../.local/ui-review/screens/live-dashboard-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/live-dashboard-mobile.png',fullPage:true});
});

test('Dashboard does not fetch business reports without permissions', async ({page}) => {
  const forbiddenRequests: string[] = [];
  page.on('request', request => {
    if (/\/api\/(clients\/(?:managerial-report\/|\?)|opportunities\/|campaigns\/)/.test(request.url())) forbiddenRequests.push(request.url());
  });
  await login(page, 'it');
  await expect(page.getByRole('article', {name: 'Clients accessibles'})).toContainText('Accès non autorisé');
  expect(forbiddenRequests).toEqual([]);
});

test('All three synthetic workbooks use fixed configurations and independent review', async ({page, browser}) => {
  test.setTimeout(120000);
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated stack only.');
  await login(page, 'operator');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const org = context.organizations.find((item: {upload: boolean}) => item.upload).id;
  const root = `/api/imports/${org}/`;
  const csrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const reviewerContext = await browser.newContext({baseURL: process.env.AICED_E2E_URL});
  const reviewer = await reviewerContext.newPage();
  const manifest = [];
  try {
    await login(reviewer, 'reviewer');
    expect((await page.request.post(root + 'policies/', {headers: {'X-CSRFToken': csrf}, data: {}})).status()).toBe(405);
    for (const template of ['physical', 'legal', 'accounts']) {
      await page.goto('/gestion-donnees');
      await page.getByLabel('Usage d\u00e9clar\u00e9 du fichier').selectOption('synthetic');
      await page.getByLabel('Date de situation source', {exact: true}).fill('2026-03-01');
      await page.getByLabel('Fichier XLSX', {exact: true}).setInputFiles(`../.local/ui-review/synthetic-review-${template}.xlsx`);
      const response = page.waitForResponse(r => r.url().includes('/upload/') && r.request().method() === 'POST');
      await page.getByRole('button', {name: 'Valider et pr\u00e9visualiser'}).click();
      const uploaded = await response;
      expect([200, 201]).toContain(uploaded.status());
      const batches = await (await page.request.get(root + 'batches/')).json();
      const batch = batches.results.find((item: {template: string; source_as_of: string; data_scope: string}) =>
        item.template === template && item.source_as_of === '2026-03-01' && item.data_scope === 'synthetic');
      expect(batch.template).toBe(template);
      expect(batch.rejected).toBe(0);
      expect((await page.request.post(root + `batches/${batch.id}/publish/`, {headers: {'X-CSRFToken': csrf}, data: {}})).status()).toBe(403);
      await reviewer.goto('/gestion-donnees');
      await reviewer.getByRole('button', {name: `Examiner le lot ${batch.id}`, exact: true}).click();
      await reviewer.getByRole('button', {name: 'Examiner la publication'}).click();
      await expect(reviewer.getByText(/Configuration fixe :/)).toBeVisible();
      await reviewer.getByRole('button', {name: 'Confirmer la publication'}).click();
      await expect(reviewer.getByRole('region', {name: '\u00c9tat de publication'})).toContainText('Publication enregistr\u00e9e');
      if (template !== 'accounts') await expect(reviewer.getByRole('status').filter({hasText: 'Synchronisation terminée'})).toBeVisible({timeout: 30000});
      manifest.push({template, batch_id: batch.id});
    }
    await writeFile('../.local/compose-test/import-dashboard-manifest.json', JSON.stringify(manifest, null, 2));
  } finally { await reviewerContext.close(); }
});

test('Published synthetic workbook history remains visible on a fresh browser visit', async ({page}) => {
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated stack only.');
  const manifest = JSON.parse(await readFile('../.local/compose-test/import-dashboard-manifest.json', 'utf8'));
  await login(page, 'reviewer');
  for (const item of manifest) {
    await page.goto('/gestion-donnees');
    await page.getByRole('button', {name: `Examiner le lot ${item.batch_id}`, exact: true}).click();
    await expect(page.getByRole('region', {name: '\u00c9tat de publication'})).toContainText('1 snapshot(s) conserv\u00e9(s)');
    await expect(page.getByRole('button', {name: 'Examiner la publication'})).toBeDisabled();
  }
});

test('Synthetic imported client displays published source fields', async ({page}) => {
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated stack only.');
  const manifest = JSON.parse(await readFile('../.local/compose-test/import-dashboard-manifest.json', 'utf8'));
  await login(page, 'operator');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const org = context.organizations[0].id;
  const batch = manifest.find((item: {template: string}) => item.template === 'physical');
  const imported = await (await page.request.get(`/api/imports/${org}/batches/${batch.batch_id}/`)).json();
  const sourceId = imported.results[0].cells['2'];
  const clients = await (await page.request.get('/api/clients/?search=PERSONNE%20SYNTHETIQUE&page_size=50')).json();
  let clientId = '';
  for (const client of clients.results) {
    const source = await (await page.request.get(`/api/clients/${client.id}/synthetic-import/`)).json();
    if (source.source?.source_id === sourceId) { clientId = client.id; break; }
  }
  expect(clientId).not.toBe('');
  await page.goto(`/clients/${clientId}`);
  await expect(page.getByRole('heading', {name: 'Import synthétique · lecture seule'})).toBeVisible();
  await expect(page.getByText(sourceId, {exact: false}).first()).toBeVisible();
});

test('Synthetic account appears under its client', async ({page}) => {
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'), 'Isolated stack only.');
  const manifest = JSON.parse(await readFile('../.local/compose-test/background-sync-manifest.json', 'utf8'));
  await login(page, 'operator');
  await page.goto(`/clients/${manifest.client_id}`);
  await expect(page.getByRole('heading', {name: 'Import synthétique · lecture seule'})).toBeVisible();
  await expect(page.getByText(`TEST · Compte ${manifest.account_id}`, {exact: false})).toBeVisible();
});

test('Examiner immediately focuses visible import details on desktop and mobile', async ({page}) => {
  await login(page, 'reviewer');
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: 844});
    await page.goto('/gestion-donnees');
    const examine = page.getByRole('button', {name: /^Examiner le lot /}).first();
    await expect(examine).toBeVisible();
    await examine.click();
    const review = page.getByRole('region', {name: 'Examen de l’import'});
    await expect(review).toBeFocused();
    await expect.poll(async () => (await review.boundingBox())!.y).toBeLessThan(422);
    await expect(review.getByRole('heading', {name: 'Prévisualisation du lot'})).toBeVisible();
    await expect(review.getByRole('region', {name: 'État de publication'})).toBeVisible();
    await page.screenshot({path: `../.local/ui-review/screens/import-review-${width}.png`});
  }
});


test('A failed review refresh blocks publication until details recover', async ({page,browser}) => {
  await login(page, 'reviewer');
  const context = await (await page.request.get('/api/imports/context/')).json();
  const organization = context.organizations.find((item: {approve:boolean}) => item.approve).id;
  for (const scope of ['operational', 'synthetic']) {
    const response = await page.request.get(`/api/imports/${organization}/policies/?view=${scope}`);
    expect(response.status()).toBe(200);
    for (const rule of await response.json()) {
      expect(rule.data_scope).toBe(scope);
      expect(rule.approved_at).toBeTruthy();
      expect(rule.revoked_at).toBeNull();
    }
  }

  const uploaderContext = await browser.newContext({baseURL:process.env.AICED_E2E_URL});
  let batchId: string;
  try {
    const uploader = await uploaderContext.newPage();
    await login(uploader, 'operator');
    const csrf = (await (await uploader.request.get('/api/auth/csrf/')).json()).csrfToken;
    // The publication scenario already publishes this workbook for March 1 and 2.
    // Use another source date to exercise a fresh actionable staging record.
    const response = await uploader.request.post(`/api/imports/${organization}/upload/?template=legal&source_as_of=2026-03-03&snapshot_kind=partial&date_format=ISO&data_scope=synthetic`, {
      headers: {'X-CSRFToken':csrf, 'Content-Type':'application/octet-stream'},
      data: await readFile('../.local/ui-review/synthetic-review-legal.xlsx'),
    });
    expect(response.status()).toBe(201);
    batchId = (await response.json()).id;
  } finally { await uploaderContext.close(); }
  await page.goto('/gestion-donnees');
  await page.getByRole('button', {name: `Examiner le lot ${batchId}`}).click();
  const review = page.getByRole('region', {name: 'Examen de l’import'});
  await expect(review.getByRole('heading', {name: 'Prévisualisation du lot'})).toBeVisible();
  await expect(review.getByRole('button', {name: 'Examiner la publication'})).toBeEnabled();
  const details = /\/api\/imports\/[^/]+\/batches\/[^/]+\//;
  await page.route(details, route => route.fulfill({status:503, contentType:'application/json', body:JSON.stringify({detail:'Synthetic dependency unavailable'})}));
  await page.getByRole('button', {name: 'Actualiser', exact:true}).click();
  await expect(review.getByRole('heading', {name: 'Prévisualisation inaccessible'})).toBeVisible();
  await expect(review.getByRole('button', {name: 'Examiner la publication'})).toBeDisabled();
  await page.unroute(details);
  await review.getByRole('button', {name: 'Réessayer'}).click();
  await expect(review.getByRole('heading', {name: 'Prévisualisation inaccessible'})).toHaveCount(0);
  await expect(review.getByRole('table')).toBeVisible();
  await expect(review.getByRole('button', {name: 'Examiner la publication'})).toBeEnabled();
});
