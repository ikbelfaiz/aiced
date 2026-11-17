import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
test.use({timezoneId:'America/Los_Angeles'});

test('Prospect follow-ups: real qualification, buckets, filters, sorting, pagination and detail navigation',async({page})=>{
  await page.goto('/prospects');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await page.getByRole('button',{name:'Nouveau prospect',exact:true}).click();
  const name=`SYNTHETIQUE S9 ${Date.now()}`;
  const today=(await(await page.request.get('/api/prospects/follow-ups/')).json()).business_date;
  await page.getByLabel('Prénom (personne physique)',{exact:true}).fill('TEST');
  await page.getByLabel('Nom (personne physique)',{exact:true}).fill(name);
  await page.getByLabel('Prochaine action',{exact:true}).fill('Appel synthétique S9');
  await page.getByLabel('Date de la prochaine action').fill(today);
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const org=(await(await page.request.get('/api/prospects/context/')).json()).organizations[0].id;
  for(let i=0;i<9;i++){
    const r=await page.request.post('/api/prospects/',{headers:{'X-CSRFToken':csrf},data:{organization_id:org,kind:'physical',first_name:'TEST',last_name:`${name} ${i}`,
      qualification:{status:i===0?'closed':'contact',next_action:i===8?'':'Action synthétique',next_action_date:i===8?null:i===0?'2000-01-01':i===1?'2099-01-01':today}}});
    expect(r.status()).toBe(201);
  }
  await page.getByRole('link',{name:'Relances prospects',exact:true}).click();
  await page.getByLabel('Rechercher un prospect ou une action').fill(name);
  await page.getByRole('button',{name:'Rechercher',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(8);
  await expect(page.getByLabel('Compteurs des échéances')).toContainText('En retard : 1');
  await expect(page.getByLabel('Compteurs des échéances')).toContainText('Sans date : 1');
  await page.getByRole('button',{name:'Suivant',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await page.getByLabel('Échéance',{exact:true}).selectOption('overdue');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).toContainText('Clos');
  await page.getByLabel('Statut',{exact:true}).selectOption('qualified');
  await expect(page.getByRole('heading',{name:'Aucun prospect dans cette sélection'})).toBeVisible();
  await page.getByLabel('Statut',{exact:true}).selectOption('');
  for(const [bucket,count] of [['today',7],['upcoming',1],['unscheduled',1]] as const){
    await page.getByLabel('Échéance',{exact:true}).selectOption(bucket);
    await expect(page.locator('tbody tr')).toHaveCount(count);
  }
  await page.getByLabel('Depuis le',{exact:true}).fill(today);
  await expect(page.getByRole('heading',{name:'Aucun prospect dans cette sélection'})).toBeVisible();
  await page.getByLabel('Depuis le',{exact:true}).fill('');
  await page.getByLabel('Échéance',{exact:true}).selectOption('today');
  await page.getByLabel('Jusqu’au',{exact:true}).fill(today);
  await page.getByLabel('Trier par',{exact:true}).selectOption('-display_name');
  await page.reload();
  await expect(page.locator('tbody tr')).toHaveCount(7);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await mkdir('../.local/ui-review/screens',{recursive:true});
  await page.screenshot({path:'../.local/ui-review/screens/followups-mobile.png',fullPage:true});
  await page.locator('tbody a').first().click();
  await expect(page.getByRole('heading',{name:new RegExp(name)})).toBeVisible();
});

test('Follow-ups deny IT even with forged filters',async({page})=>{
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.it.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
  await page.goto('/prospects/relances');
  await expect(page.getByRole('heading',{name:'Relances non autorisées'})).toBeVisible();
  expect((await page.request.get('/api/prospects/follow-ups/?bucket=overdue&page_size=1')).status()).toBe(403);
  await expect(page.locator('tbody tr')).toHaveCount(0);
});

test('Follow-ups fail closed on request failure and recover on retry',async({page})=>{
  await page.goto('/prospects/relances');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.route('**/api/prospects/follow-ups/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.getByRole('link',{name:'Relances prospects',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Impossible de charger les relances'})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await page.unroute('**/api/prospects/follow-ups/**');
  await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
});
