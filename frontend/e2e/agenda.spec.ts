import { test,expect } from '@playwright/test';
test.use({timezoneId:'America/Los_Angeles'});

test('Personal agenda creates, validates, edits and displays Tunis calendar times',async({page})=>{
  const name=`SYNTHETIQUE AGENDA ${Date.now()}`;
  await page.goto(`/agenda?month=2030-04&search=${encodeURIComponent(name)}`);
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Mon agenda',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Nouveau rendez-vous',exact:true}).click();
  await page.getByLabel('Titre',{exact:true}).fill(name);
  await page.getByLabel('Date du rendez-vous',{exact:true}).fill('2030-04-17');
  await page.getByLabel('Heure de début',{exact:true}).fill('10:00');
  await page.getByLabel('Heure de fin',{exact:true}).fill('10:00');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('La fin doit suivre le début');
  await page.getByLabel('Heure de fin',{exact:true}).fill('11:00');
  await page.getByLabel('Notes personnelles').fill('SYNTHETIQUE notes agenda');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'2030-04-17 : 1 rendez-vous',exact:true})).toBeVisible();
  await page.getByRole('button',{name:`Modifier ${name}`,exact:true}).click();
  await page.getByLabel('Heure de début',{exact:true}).fill('10:30');
  await page.getByLabel('Heure de fin',{exact:true}).fill('11:30');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const context=await(await page.request.get('/api/agenda/context/')).json();
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  expect((await page.request.post('/api/agenda/',{headers:{'X-CSRFToken':csrf},data:{organization_id:context.organizations[0].id,title:name+' overlap',kind:'call',date:'2030-04-17',start_time:'11:00',end_time:'12:00'}})).status()).toBe(201);
  await page.reload();
  await page.getByRole('button',{name:'2030-04-17 : 2 rendez-vous',exact:true}).click();
  await expect(page.locator('.workspace-activities article')).toHaveCount(2);
  await expect(page.locator('.workspace-activities').first()).toContainText('10:30–11:30');
  await expect(page.getByRole('button',{name:'Annulation indisponible'})).toBeDisabled();
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/agenda-mobile.png',fullPage:true});
  await page.getByRole('button',{name:'Tout le mois',exact:true}).click();
  await expect(page.locator('.workspace-activities article')).toHaveCount(2);
});

test('Agenda error hides cached calendar and appointments and recovers',async({page})=>{
  await page.goto('/agenda?month=2030-04');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Mon agenda',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.route('**/api/agenda/**',route=>route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.getByRole('link',{name:'Agenda',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Agenda inaccessible'})).toBeVisible();
  await expect(page.locator('.agenda-calendar')).toHaveCount(0);
  await expect(page.locator('.workspace-activities article')).toHaveCount(0);
  await page.unroute('**/api/agenda/**');
  await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Mon agenda',exact:true})).toBeVisible();
});

test('IT cannot read personal agenda',async({page})=>{
  await page.goto('/agenda');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.it.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Agenda non autorisé'})).toBeVisible();
  expect((await page.request.get('/api/agenda/?month=2030-04')).status()).toBe(403);
});
