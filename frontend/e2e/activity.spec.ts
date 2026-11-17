import {test,expect} from '@playwright/test';
test.use({timezoneId:'America/Los_Angeles'});
async function login(page:import('@playwright/test').Page,user='synthetic.operator.a'){
  await page.goto('/clients');await page.getByLabel('Identifiant professionnel').fill(user);await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:user==='synthetic.it.a'?'Accès non autorisé':'Panorama Clients',exact:true})).toBeVisible();
}

test('Operational report charts equal real authorized APIs, period/type filters and Client navigation',async({page})=>{
  await login(page);
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const party=(await(await page.request.get('/api/clients/?page_size=1')).json()).results[0].id;
  const report='/api/clients/activity-report/?date_from=2024-06-19&date_to=2024-06-19&kind=call';
  const before=await(await page.request.get(report)).json();
  const created=await page.request.post(`/api/clients/${party}/interactions/`,{headers:{'X-CSRFToken':csrf},data:{kind:'call',subject:`SYNTHETIC S16 BROWSER ${Date.now()}`,occurred_at:'2024-06-18T23:00:00Z'}});
  expect(created.status()).toBe(201);
  await page.getByRole('link',{name:'Activité commerciale',exact:true}).click();
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toBeVisible();
  await page.getByLabel('Début du rapport',{exact:true}).fill('2024-06-19');await page.getByLabel('Fin du rapport',{exact:true}).fill('2024-06-19');await page.getByLabel('Type d’activité du rapport',{exact:true}).selectOption('call');
  await page.getByRole('button',{name:'Appliquer la période',exact:true}).click();
  await expect(page.getByRole('region',{name:'Interactions de la période'}).locator('.report-total')).toHaveText(String(before.interactions.total+1));
  await expect(page.getByText(/Fuseau : Africa\/Tunis/)).toBeVisible();
  await page.getByText('Voir les valeurs du graphique',{exact:true}).click();
  const table=page.getByRole('table',{name:'Valeurs quotidiennes CRM'});
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.locator('tbody tr').first().locator('td').first()).toHaveText(String(before.interactions.total+1));
  await expect(page.getByRole('img',{name:'Graphique quotidien des interactions et rendez-vous'}).locator('svg')).toBeVisible();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toBeVisible();
  const pipeline=await(await page.request.get('/api/opportunities/?page_size=1')).json();
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toHaveText(String(pipeline.count));
  const drafts=await(await page.request.get('/api/campaigns/?page_size=1')).json();
  await expect(page.getByRole('region',{name:'Brouillons actuels'}).locator('.report-total')).toHaveText(String(drafts.count));
  await page.reload();
  await page.getByText('Voir les valeurs du graphique',{exact:true}).click();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.locator('tbody tr').first().locator('td').first()).toHaveText(String(before.interactions.total+1));
  await page.getByLabel('Début du rapport',{exact:true}).fill('2024-06-20');await page.getByLabel('Fin du rapport',{exact:true}).fill('2024-06-19');await page.getByRole('button',{name:'Appliquer la période',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Activité CRM indisponible'})).toBeVisible();
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toHaveCount(0);
  await page.getByRole('button',{name:'Réinitialiser le rapport',exact:true}).click();
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toBeVisible();
  await page.setViewportSize({width:390,height:844});await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/activity-mobile.png',fullPage:true});
  await page.getByRole('link',{name:'Consulter les interactions',exact:true}).click();await expect(page).toHaveURL(/\/interactions/);
});

test('Report hides old metrics on denied/failed sources and recovers without fallback',async({page})=>{
  await login(page);await page.goto('/activite-commerciale');
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toBeVisible();
  await page.route('**/api/clients/activity-report/**',route=>route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.route('**/api/opportunities/?page_size=1',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.getByRole('button',{name:'Actualiser les rapports',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Activité CRM indisponible'})).toBeVisible();
  await expect(page.getByRole('region',{name:'Interactions de la période'})).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Opportunités actuelles'}).locator('.report-total')).toHaveCount(0);
  await expect(page.getByRole('region',{name:'Brouillons actuels'}).locator('.report-total')).toBeVisible();
  await page.unroute('**/api/clients/activity-report/**');await page.unroute('**/api/opportunities/?page_size=1');
  await page.getByRole('button',{name:'Actualiser les rapports',exact:true}).click();await expect(page.getByRole('region',{name:'Interactions de la période'})).toBeVisible();
});

test('IT cannot retrieve operational report or turn it into managerial access',async({page})=>{
  await login(page,'synthetic.it.a');expect((await page.request.get('/api/clients/activity-report/')).status()).toBe(403);
  await page.goto('/activite-commerciale');await expect(page.getByRole('heading',{name:'Accès non autorisé',exact:true})).toBeVisible();
  await expect(page.locator('.report-total')).toHaveCount(0);
});
