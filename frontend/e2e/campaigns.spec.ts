import { test,expect } from '@playwright/test';
test.use({timezoneId:'America/Los_Angeles'});

async function login(page:any,user='synthetic.operator.a'){
  await page.goto('/clients');
  await page.getByLabel('Identifiant professionnel').fill(user);
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:user==='synthetic.it.a'?'Accès non autorisé':'Panorama Clients',exact:true})).toBeVisible();
}

test('Manual campaign draft creates, validates, persists, edits and rejects a stale version',async({page})=>{
  await login(page);
  const name=`SYNTHETIQUE CAMPAGNE ${Date.now()}`;
  await page.goto('/campagnes?search='+encodeURIComponent(name));
  await expect(page.getByRole('heading',{name:'Mes brouillons de campagnes',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Nouveau brouillon',exact:true}).click();
  await page.getByLabel('Nom de la campagne',{exact:true}).fill(name);
  await page.getByLabel('Description',{exact:true}).fill('SYNTHETIQUE : préparation privée');
  await page.getByLabel('Début prévu',{exact:true}).fill('2031-06-30');
  await page.getByLabel('Fin prévue',{exact:true}).fill('2031-06-29');
  await page.getByLabel('Préparation du ciblage (notes non exécutées)').fill('SYNTHETIQUE : profession à discuter ; aucune cible sélectionnée');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('La fin doit être postérieure');
  await page.getByLabel('Fin prévue',{exact:true}).fill('2031-07-01');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.campaign-draft')).toHaveCount(1);
  await expect(page.locator('.campaign-draft')).toContainText('30/06/2031');
  await expect(page.getByRole('button',{name:'Activation indisponible'})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Envoi indisponible'})).toBeDisabled();
  await page.reload();
  await page.getByRole('button',{name:`Modifier ${name}`,exact:true}).click();
  await page.getByLabel('Description',{exact:true}).fill('SYNTHETIQUE : édition persistée');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.campaign-draft')).toContainText('édition persistée');
  await page.getByRole('button',{name:`Modifier ${name}`,exact:true}).click();
  const item=(await(await page.request.get('/api/campaigns/?search='+encodeURIComponent(name))).json()).results[0];
  const csrf=(await(await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  expect((await page.request.patch(`/api/campaigns/${item.id}/`,{headers:{'X-CSRFToken':csrf},data:{version:item.version,description:'SYNTHETIQUE : mise à jour concurrente'}})).status()).toBe(200);
  await page.getByLabel('Description',{exact:true}).fill('MUST NOT OVERWRITE');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('Version obsolète');
  await page.getByRole('button',{name:'Annuler',exact:true}).click();
  await page.reload();
  await expect(page.locator('.campaign-draft')).toContainText('mise à jour concurrente');
  for(let i=0;i<8;i++)expect((await page.request.post('/api/campaigns/',{headers:{'X-CSRFToken':csrf},data:{organization_id:item.organization_id,name:`${name} ${i}`}})).status()).toBe(201);
  await page.reload();
  await expect(page.locator('.pagination')).toContainText('9 brouillon(s) · page 1');
  await page.getByRole('button',{name:'Suivant',exact:true}).click();
  await expect(page.locator('.campaign-draft')).toHaveCount(1);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/campaigns-mobile.png',fullPage:true});
});

test('Campaign page hides cached private drafts on denial and recovers',async({page})=>{
  await login(page);await page.getByRole('link',{name:'Campagnes',exact:true}).click();
  await expect(page.locator('.campaign-draft').first()).toBeVisible();
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.route('**/api/campaigns/**',route=>route.fulfill({status:403,contentType:'application/json',body:'{}'}));
  await page.getByRole('link',{name:'Campagnes',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Campagnes inaccessibles'})).toBeVisible();
  await expect(page.locator('.campaign-draft')).toHaveCount(0);
  await page.unroute('**/api/campaigns/**');await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.locator('.campaign-draft').first()).toBeVisible();
});

test('IT cannot discover draft names, counts or create campaigns',async({page})=>{
  await page.goto('/campagnes');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.it.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Campagnes non autorisées'})).toBeVisible();
  expect((await page.request.get('/api/campaigns/')).status()).toBe(403);
  expect((await page.request.get('/api/campaigns/context/')).status()).toBe(403);
});
