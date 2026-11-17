import {test,expect,type Page} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
test.use({timezoneId:'America/Los_Angeles'});
async function login(page:Page,user='synthetic.operator.a'){
  await page.goto('/pilotage-crm');
  await page.getByLabel('Identifiant professionnel').fill(user);
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page).toHaveURL(/\/pilotage-crm(?:\?|$)/);
}

test('Managerial CRM cards and charts match authorized APIs, real activity creation and Tunis period filters',async({page})=>{
  await login(page);
  await expect(page.getByRole('heading',{name:'Pilotage CRM',exact:true})).toBeVisible();
  const path='/api/clients/managerial-report/?date_from=2024-06-19&date_to=2024-06-19&kind=call';
  const before=await(await page.request.get(path)).json();
  const party=(await(await page.request.get('/api/clients/?page_size=1')).json()).results[0].id;
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  expect((await page.request.post(`/api/clients/${party}/interactions/`,{headers:{'X-CSRFToken':csrf},data:{kind:'call',subject:`SYNTHETIC S17 ${Date.now()}`,occurred_at:'2024-06-18T23:00:00Z'}})).status()).toBe(201);
  await page.getByLabel('Début du rapport',{exact:true}).fill('2024-06-19');
  await page.getByLabel('Fin du rapport',{exact:true}).fill('2024-06-19');
  await page.getByLabel('Type d’activité du rapport',{exact:true}).selectOption('call');
  await page.getByRole('button',{name:'Appliquer la période',exact:true}).click();
  await expect(page.getByRole('region',{name:'Interactions de la période',exact:true}).locator('.report-total')).toHaveText(String(before.interactions.total+1));
  await expect(page.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toHaveText(String(before.portfolio.quality.total));
  await expect(page.getByRole('region',{name:'Profils complets',exact:true}).locator('.report-total')).toHaveText(String(before.portfolio.quality.complete));
  await expect(page.getByText(/Fuseau : Africa\/Tunis/)).toBeVisible();
  await page.getByText('Voir les valeurs du graphique',{exact:true}).click();
  await expect(page.getByRole('table',{name:'Valeurs quotidiennes CRM'}).locator('tbody tr td').first()).toHaveText(String(before.interactions.total+1));
  for(const title of ['Clients par type','Champs CRM absents','Échéances actuelles des prospects','Statuts actuels des opportunités']){
    await expect(page.getByRole('img',{name:`Graphique : ${title}`,exact:true}).locator('svg')).toBeVisible();
  }
  await page.getByText('Valeurs : Clients par type',{exact:true}).click();
  const table=page.getByRole('table',{name:'Valeurs : Clients par type',exact:true});
  await expect(table.locator('tbody tr').first().locator('td')).toHaveText(String(before.portfolio.by_kind.physical));
  await page.getByText('Valeurs : Champs CRM absents',{exact:true}).click();
  const missing=page.getByRole('table',{name:'Valeurs : Champs CRM absents',exact:true});
  for(const field of before.portfolio.quality.fields)await expect(missing.getByRole('row').filter({has:page.getByRole('rowheader',{name:field.label,exact:true})}).locator('td')).toHaveText(String(before.portfolio.quality.missing_counts[field.key]));
  const pipeline=await(await page.request.get('/api/opportunities/?page_size=1')).json();
  await expect(page.getByRole('region',{name:'Opportunités actuelles',exact:true}).locator('.report-total')).toHaveText(String(pipeline.count));
  await page.getByText('Valeurs : Statuts actuels des opportunités',{exact:true}).click();
  const statuses=page.getByRole('table',{name:'Valeurs : Statuts actuels des opportunités',exact:true});
  for(const [index,key] of ['open','won','lost'].entries())await expect(statuses.locator('tbody tr').nth(index).locator('td')).toHaveText(String(pipeline.statuses[key]));
  await page.getByText('Valeurs : Échéances actuelles des prospects',{exact:true}).click();
  const followups=page.getByRole('table',{name:'Valeurs : Échéances actuelles des prospects',exact:true});
  for(const [index,key] of ['overdue','today','upcoming','unscheduled'].entries())await expect(followups.locator('tbody tr').nth(index).locator('td')).toHaveText(String(before.followups[key]));
  const drafts=await(await page.request.get('/api/campaigns/?page_size=1')).json();
  await expect(page.getByRole('region',{name:'Brouillons actuels',exact:true}).locator('.report-total')).toHaveText(String(drafts.count));
  await page.reload();
  await expect(page.getByRole('region',{name:'Interactions de la période',exact:true}).locator('.report-total')).toHaveText(String(before.interactions.total+1));
  await expect(page.getByRole('region',{name:'Opportunités actuelles',exact:true}).locator('.report-total')).toHaveText(String(pipeline.count));
  await expect(page.getByRole('region',{name:'Brouillons actuels',exact:true}).locator('.report-total')).toHaveText(String(drafts.count));
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/managerial-mobile.png',fullPage:true});
  await page.getByRole('link',{name:'Consulter les clients',exact:true}).click();
  await expect(page).toHaveURL(/\/clients$/);
});

test('Managerial CRM hides stale cards and charts on failures, preserves independent owner panels and recovers',async({page})=>{
  await login(page);
  await expect(page.getByRole('region',{name:'Portefeuille CRM actuel',exact:true})).toBeVisible();
  await page.route('**/api/clients/managerial-report/**',route=>route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.route('**/api/opportunities/?page_size=1',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.getByRole('button',{name:'Actualiser les rapports',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Activité CRM indisponible',exact:true})).toBeVisible();
  await expect(page.getByRole('region',{name:'Portefeuille CRM actuel',exact:true})).toHaveCount(0);
  await expect(page.getByRole('img',{name:'Graphique : Statuts actuels des opportunités',exact:true})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Brouillons actuels',exact:true}).locator('.report-total')).toBeVisible();
  await page.unroute('**/api/clients/managerial-report/**');await page.unroute('**/api/opportunities/?page_size=1');
  await page.getByRole('button',{name:'Actualiser les rapports',exact:true}).click();
  await expect(page.getByRole('region',{name:'Portefeuille CRM actuel',exact:true})).toBeVisible();
  await page.getByLabel('Début du rapport',{exact:true}).fill('2024-06-20');await page.getByLabel('Fin du rapport',{exact:true}).fill('2024-06-19');
  await page.getByRole('button',{name:'Appliquer la période',exact:true}).click();
  await expect(page.getByRole('region',{name:'Portefeuille CRM actuel',exact:true})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Activité CRM indisponible',exact:true})).toBeVisible();
});

test('Managerial CRM shows real empty datasets and denies IT without assuming management privileges',async({page})=>{
  await login(page,'synthetic.s17.empty');
  for(const region of ['Clients autorisés','Profils complets','Interactions de la période','Rendez-vous de la période','Opportunités actuelles','Brouillons actuels']){
    await expect(page.getByRole('region',{name:region,exact:true}).locator('.report-total')).toHaveText('0');
  }
  await expect(page.getByText('Aucun enregistrement dans ce périmètre.').first()).toBeVisible();
  const other=await page.context().browser()!.newContext();
  try{
    const it=await other.newPage();await it.goto(new URL('/pilotage-crm',page.url()).toString());
    await it.getByLabel('Identifiant professionnel').fill('synthetic.it.a');await it.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
    await it.getByRole('button',{name:'Connexion',exact:true}).click();
    await expect(it.getByRole('heading',{name:'Accès non autorisé',exact:true})).toBeVisible();
    expect((await it.request.get(new URL('/api/clients/managerial-report/',page.url()).toString())).status()).toBe(403);
    await expect(it.locator('.report-total')).toHaveCount(0);
  }finally{await other.close();}
});

test('Restricted reader portfolio equals visible client scope without unauthorized activity panels',async({page})=>{
  await login(page,'synthetic.reader.a');
  const clients=await(await page.request.get('/api/clients/?page_size=1')).json();
  await expect(page.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toHaveText(String(clients.count));
  const data=await(await page.request.get('/api/clients/managerial-report/')).json();
  expect(data.portfolio.quality.total).toBe(clients.count);
  expect(data.interactions).toBeNull();expect(data.appointments).toBeNull();expect(data.followups).toBeNull();
  await expect(page.getByRole('region',{name:'Interactions de la période',exact:true}).locator('.report-total')).toHaveCount(0);
  await expect(page.getByRole('img',{name:'Graphique quotidien des interactions et rendez-vous',exact:true})).toHaveCount(0);
  const disjoint=await page.context().browser()!.newContext({baseURL:new URL(page.url()).origin});
  try{
    const restricted=await disjoint.newPage();await login(restricted,'synthetic.s17.disjoint');
    await expect(restricted.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toHaveText('0');
    const response=await restricted.request.get('/api/clients/managerial-report/');
    expect(response.status()).toBe(200);
    const scoped=await response.json();
    expect(scoped.interactions).toBeNull();expect(scoped.appointments).toBeNull();expect(scoped.followups).toBeNull();
    await expect(restricted.getByRole('region',{name:'Interactions de la période',exact:true}).locator('.report-total')).toHaveCount(0);
  }finally{await disjoint.close();}
});

test('Managerial CRM actual isolated Docker outages fail closed and recover persisted records',async({page})=>{
  test.skip(process.env.AICED_E2E_ISOLATED!=='1','Stops services only in the explicitly isolated Docker test stack');
  test.setTimeout(150000); // Four real stop/start cycles, including PostgreSQL readiness.
  const root=resolve(process.cwd(),'..');
  const compose=['compose','-f',resolve(root,'compose.yaml'),'-f',resolve(root,'compose.test.yaml')];
  const docker=(...args:string[])=>execFileSync('docker',[...compose,...args],{cwd:root,stdio:'pipe',timeout:30000});
  const path='/api/clients/managerial-report/?date_from=2024-06-19&date_to=2024-06-19';
  await login(page);
  await page.goto('/pilotage-crm?date_from=2024-06-19&date_to=2024-06-19');
  await expect(page.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toBeVisible();
  const response=await page.request.get(path);expect(response.status()).toBe(200);
  const {generated_at:_,...before}=await response.json();
  try{
    for(const service of ['client','commercial','iam','db']){
      docker('stop',service);
      await page.getByRole('button',{name:'Actualiser les rapports',exact:true}).click();
      if(service==='commercial'){
        await expect(page.getByRole('heading',{name:'Opportunités indisponibles',exact:true})).toBeVisible({timeout:15000});
        await expect(page.getByRole('region',{name:'Opportunités actuelles',exact:true}).locator('.report-total')).toHaveCount(0);
        await expect(page.getByRole('region',{name:'Brouillons actuels',exact:true}).locator('.report-total')).toHaveCount(0);
        await expect(page.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toBeVisible();
      }else if(service==='client'){
        await expect(page.getByRole('region',{name:'Portefeuille CRM actuel',exact:true})).toHaveCount(0,{timeout:15000});
        await expect(page.getByRole('img',{name:'Graphique quotidien des interactions et rendez-vous',exact:true})).toHaveCount(0);
        await expect(page.getByRole('region',{name:'Brouillons actuels',exact:true}).locator('.report-total')).toBeVisible();
      }else{
        await expect(page.locator('.report-total')).toHaveCount(0,{timeout:15000});
      }
      docker('start',service);
      docker('up','-d','--no-deps','--wait','--wait-timeout','25',service);
      await page.reload();
      await expect(page.getByRole('region',{name:'Clients autorisés',exact:true}).locator('.report-total')).toHaveText(String(before.portfolio.quality.total),{timeout:15000});
      await expect(page.getByRole('region',{name:'Opportunités actuelles',exact:true}).locator('.report-total')).toBeVisible({timeout:15000});
      const recovered=await page.request.get(path);expect(recovered.status()).toBe(200);
      const {generated_at:__,...after}=await recovered.json();
      expect(after).toEqual(before);
    }
  }finally{
    docker('start','db','iam','client','commercial');
    docker('up','-d','--no-deps','--wait','--wait-timeout','25','db','iam','client','commercial');
  }
});
