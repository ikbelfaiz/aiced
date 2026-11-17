import { test,expect } from '@playwright/test';

test('Panorama segments real CRM fields with combined filters, pages, sorting and Client 360',async({page})=>{
  await page.goto('/clients');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await page.getByRole('button',{name:'Nouveau client',exact:true}).click();
  const name=`SYNTHETIQUE S10 ${Date.now()}`;
  const profession=`Profession ${name}`;
  const sector=`Secteur ${name}`;
  await page.getByLabel('Prénom (personne physique)',{exact:true}).fill('TEST');
  await page.getByLabel('Nom (personne physique)',{exact:true}).fill(name);
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('heading',{name:`TEST ${name}`,exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Modifier le profil CRM'}).click();
  await page.getByLabel('Profession déclarée au CRM').fill(profession);
  await page.getByLabel('Secteur déclaré au CRM').fill(sector);
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  const org=(await(await page.request.get('/api/clients/context/')).json()).organizations[0].id;
  for(let i=0;i<8;i++){
    const response=await page.request.post('/api/clients/create/',{headers:{'X-CSRFToken':csrf},data:{organization_id:org,kind:'physical',first_name:'TEST',last_name:`${name} ${i}`}});
    expect(response.status()).toBe(201);
    const id=(await response.json()).id;
    const workspace=await(await page.request.get(`/api/clients/${id}/workspace/`)).json();
    const updated=await page.request.patch(`/api/clients/${id}/profile/`,{headers:{'X-CSRFToken':csrf},data:{version:workspace.crm.version,profession,sector:i===7?'':sector}});
    expect(updated.status()).toBe(200);
  }
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.getByLabel('Rechercher un client',{exact:true}).fill(name);
  await expect.poll(()=>new URL(page.url()).searchParams.get('recherche')).toBe(name);
  await page.getByLabel('Profession',{exact:true}).selectOption(JSON.stringify(profession));
  await expect(page.locator('tbody tr')).toHaveCount(8);
  await page.getByRole('button',{name:'Page suivante',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByLabel('Secteur',{exact:true}).selectOption('missing');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByLabel('Secteur',{exact:true}).selectOption(JSON.stringify(sector));
  await page.getByLabel('Type de personne',{exact:true}).selectOption('physical');
  await page.getByLabel('Trier les clients',{exact:true}).selectOption('-display_name');
  await page.reload();
  await expect(page.locator('tbody tr')).toHaveCount(8);
  await expect(page.locator('tbody tr').first()).toContainText(`${name} 6`);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/segmentation-mobile.png',fullPage:true});
  await page.locator('tbody a').first().click();
  await expect(page.getByText(profession,{exact:true})).toBeVisible();
  await expect(page.getByText(sector,{exact:true})).toBeVisible();
});

test('Segmentation options fail closed and IT cannot retrieve them',async({page})=>{
  await page.goto('/clients');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.getByRole('link',{name:'Interactions',exact:true}).click();
  await page.route('**/api/clients/filter-options/',route=>route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Impossible de charger les clients'})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await expect(page.getByLabel('Profession',{exact:true}).locator('option')).toHaveCount(3);
  await page.unroute('**/api/clients/filter-options/');
  await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  const other=await page.context().browser()!.newContext();
  try{
    const it=await other.newPage();await it.goto(new URL('/connexion',page.url()).toString());
    await it.getByLabel('Identifiant professionnel').fill('synthetic.it.a');
    await it.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
    await it.getByRole('button',{name:'Connexion',exact:true}).click();
    await expect(it.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
    expect((await it.request.get(new URL('/api/clients/filter-options/',page.url()).toString())).status()).toBe(403);
  }finally{await other.close();}
});
