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
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toHaveText(String(opportunities.count));
  await expect(page.getByRole('img',{name:'Graphique quotidien des interactions et rendez-vous'})).toBeVisible();
  await expect(page.getByText('Valorisations et définition financière approuvée indisponibles.')).toBeVisible();
  await page.route('**/api/opportunities/?page_size=1',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.getByRole('button',{name:'Actualiser les rapports'}).click();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toBeVisible();
  await page.unroute('**/api/opportunities/?page_size=1');
  await page.getByRole('button',{name:'Actualiser les rapports'}).click();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toHaveText(String(opportunities.count));
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/live-dashboard-mobile.png',fullPage:true});
});

test('All three synthetic workbooks upload and publish through the UI without creating CRM clients',async({page,browser})=>{
  test.setTimeout(120000);
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'),'Synthetic policy creation is restricted to the isolated stack.');
  await login(page,'operator');
  const before=await(await page.request.get('/api/clients/?page_size=1')).json();
  const context=await(await page.request.get('/api/imports/context/')).json();
  const org=context.organizations.find((item:{upload:boolean})=>item.upload).id;
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const reviewerContext=await browser.newContext({baseURL:process.env.AICED_E2E_URL});
  const reviewer=await reviewerContext.newPage();
  const manifest=[];
  try{
    await login(reviewer,'reviewer');
    const reviewCsrf=(await(await reviewer.request.get('/api/auth/csrf/')).json()).csrfToken;
    for(const template of ['physical','legal','accounts']){
      const root=`/api/imports/${org}/`;
      const policyResponse=await page.request.post(root+'policies/',{headers:{'X-CSRFToken':csrf},data:{template,key_column:template==='accounts'?5:2,data_scope:'synthetic',date_format:'ISO',rationale:`SYNTHETIC REVIEW ${template}: snapshots only, no CRM mapping approved.`}});
      expect(policyResponse.status()).toBe(201);
      const policy=await policyResponse.json();
      const duplicate=await page.request.post(root+'policies/',{headers:{'X-CSRFToken':csrf},data:{template,key_column:template==='accounts'?5:2,data_scope:'synthetic',date_format:'ISO',rationale:`SYNTHETIC REVIEW ${template}: snapshots only, no CRM mapping approved.`}});
      expect(duplicate.status()).toBe(201);
      expect((await duplicate.json()).id).toBe(policy.id);
      expect((await reviewer.request.post(root+`policies/${policy.id}/approve/`,{headers:{'X-CSRFToken':reviewCsrf},data:{}})).status()).toBe(200);
      await page.goto('/gestion-donnees');
      await page.getByLabel('Usage d\u00e9clar\u00e9 du fichier').selectOption('synthetic');
      await page.getByLabel('Modèle versionné').selectOption(template);
      await page.getByLabel('Date de situation source',{exact:true}).fill('2026-03-01');
      await page.getByLabel('Fichier XLSX',{exact:true}).setInputFiles(`../.local/ui-review/synthetic-review-${template}.xlsx`);
      const response=page.waitForResponse(r=>r.url().includes('/upload/')&&r.request().method()==='POST');
      await page.getByRole('button',{name:'Valider et prévisualiser'}).click();
      expect((await response).status()).toBe(201);
      await expect(page.getByRole('heading',{name:'Prévisualisation du lot'})).toBeVisible();
      const batch=(await(await page.request.get(root+'batches/')).json()).results[0];
      expect(batch.template).toBe(template);
      expect(batch.status).toBe('staged');expect(batch.total).toBe(1);expect(batch.rejected).toBe(0);
      const state=page.getByRole('region',{name:'État de publication'});
      await expect(state).toContainText('une revue par un autre utilisateur habilité est obligatoire');
      await expect(page.getByRole('button',{name:'Examiner la publication'})).toBeDisabled();
      expect((await page.request.post(root+`batches/${batch.id}/publish/`,{headers:{'X-CSRFToken':csrf},data:{policy_id:policy.id}})).status()).toBe(403);
      await reviewer.goto('/gestion-donnees');
      await reviewer.getByRole('button',{name:`Examiner le lot ${batch.id}`,exact:true}).click();
      await reviewer.getByRole('button',{name:'Examiner la publication'}).click();
      await expect(reviewer.getByLabel('Règle approuvée',{exact:true})).toHaveValue(policy.id);
      await reviewer.getByLabel('Règle approuvée',{exact:true}).selectOption(policy.id);
      await reviewer.getByRole('button',{name:'Confirmer la publication'}).click();
      await expect(reviewer.getByRole('region',{name:'État de publication'})).toContainText('Publication enregistrée');
      await expect(reviewer.getByRole('region',{name:'État de publication'})).toContainText(policy.id);
      await reviewer.reload();
      await reviewer.getByRole('button',{name:`Examiner le lot ${batch.id}`,exact:true}).click();
      await expect(reviewer.getByRole('region',{name:'État de publication'})).toContainText('1 snapshot(s) conservé(s)');
      manifest.push({template,batch_id:batch.id,policy_id:policy.id});
      if(template==='legal'){
        // A second compatible upload reuses the same approval, but not the review.
        await page.getByLabel('Date de situation source',{exact:true}).fill('2026-03-02');
        const nextUpload=page.waitForResponse(r=>r.url().includes('/upload/')&&r.request().method()==='POST');
        await page.getByRole('button',{name:'Valider et prévisualiser'}).click();
        expect((await nextUpload).status()).toBe(201);
        const second=(await(await page.request.get(root+'batches/')).json()).results.find((b:{source_as_of:string;template:string;data_scope:string})=>b.source_as_of==='2026-03-02'&&b.template==='legal'&&b.data_scope==='synthetic');
        expect(second.id).not.toBe(batch.id);expect(second.status).toBe('staged');
        await expect(page.getByRole('status')).toContainText(policy.id);
        expect((await page.request.post(root+`batches/${second.id}/publish/`,{headers:{'X-CSRFToken':csrf},data:{policy_id:policy.id}})).status()).toBe(403);
        await reviewer.goto('/gestion-donnees');
        await reviewer.getByRole('button',{name:`Examiner le lot ${second.id}`,exact:true}).click();
        await reviewer.getByRole('button',{name:'Examiner la publication'}).click();
        await expect(reviewer.getByLabel('Règle approuvée',{exact:true})).toHaveValue(policy.id);
        await reviewer.getByRole('button',{name:'Confirmer la publication'}).click();
        await expect(reviewer.getByRole('region',{name:'État de publication'})).toContainText('Publication enregistrée');
        // Incompatible operational declaration: no synthetic rule suggested/usable.
        await page.getByLabel('Usage déclaré du fichier').selectOption('operational');
        const incompatibleUpload=page.waitForResponse(r=>r.url().includes('/upload/')&&r.request().method()==='POST');
        await page.getByRole('button',{name:'Valider et prévisualiser'}).click();
        expect((await incompatibleUpload).status()).toBe(201);
        const incompatible=(await(await page.request.get(root+'batches/')).json()).results.find((b:{source_as_of:string;template:string;data_scope:string})=>b.source_as_of==='2026-03-02'&&b.template==='legal'&&b.data_scope==='operational');
        await expect(page.getByRole('status')).toContainText('Aucune règle approuvée active');
        await expect(page.getByRole('button',{name:'Examiner la publication'})).toBeDisabled();
        expect((await reviewer.request.post(root+`batches/${incompatible.id}/publish/`,{headers:{'X-CSRFToken':reviewCsrf},data:{policy_id:policy.id}})).status()).toBe(400);
      }
    }
    const after=await(await page.request.get('/api/clients/?page_size=1')).json();
    expect(after.count).toBe(before.count);
    await writeFile('../.local/compose-test/import-dashboard-manifest.json',JSON.stringify(manifest,null,2));
  }finally{await reviewerContext.close();}
});

test('Published synthetic workbook history remains visible on a fresh browser visit',async({page})=>{
  test.skip(!process.env.AICED_E2E_URL?.endsWith(':5188'),'Isolated stack only.');
  const manifest=JSON.parse(await readFile('../.local/compose-test/import-dashboard-manifest.json','utf8'));
  await login(page,'reviewer');
  for(const item of manifest){
    await page.goto('/gestion-donnees');
    await page.getByRole('button',{name:`Examiner le lot ${item.batch_id}`,exact:true}).click();
    await expect(page.getByRole('region',{name:'État de publication'})).toContainText(item.policy_id);
    await expect(page.getByRole('region',{name:'État de publication'})).toContainText('1 snapshot(s) conservé(s)');
    await expect(page.getByRole('button',{name:'Examiner la publication'})).toBeDisabled();
  }
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
