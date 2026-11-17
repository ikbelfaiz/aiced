import {test,expect,type Page} from '@playwright/test';

async function login(page:Page,role='operator'){
  await page.goto('/clients');
  await page.getByLabel('Identifiant professionnel').fill(`synthetic.${role}.a`);
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:role==='it'?'Accès non autorisé':'Panorama Clients',exact:true})).toBeVisible();
}
async function openClient(page:Page){
  const client=(await(await page.request.get('/api/clients/?page_size=1')).json()).results[0];
  await page.goto(`/clients/${client.id}`);
  await expect(page.getByRole('heading',{name:'Rapprochement source · préparation synthétique',exact:true})).toBeVisible();
  return client.id;
}

test('Client 360 synthetic source preview covers every candidate case without confirmed identities',async({page})=>{
  await login(page);const id=await openClient(page);
  const root=`/api/clients/${id}/source-mapping-preview/`;
  const panel=page.getByRole('region',{name:'Préparation du rapprochement source'});
  await expect(panel).toContainText('Les données Excel réelles restent bloquées');
  await panel.getByRole('button',{name:'Voir la démonstration synthétique'}).click();
  await expect(panel.getByRole('table',{name:'Candidats synthétiques'})).toBeVisible();
  for(const [scenario,status,count] of [['unique','Candidat unique — non approuvé',1],['ambiguous','Plusieurs candidats — aucun choix',1],['missing','Identifiant manquant — aucun lien',1],['duplicate','Doublon — aucun lien confirmé',2],['multiple_accounts','Candidat unique — non approuvé',2],['conflicting_identifiers','Références contradictoires — aucun lien',1]] as const){
    await panel.getByLabel('Cas de rapprochement synthétique').selectOption(scenario);
    await expect(panel.getByRole('table').locator('tbody tr')).toHaveCount(count);
    await expect(panel.getByRole('table').locator('tbody tr').first()).toContainText(status);
    const response=await page.request.get(root+'?scenario='+scenario);expect(response.status()).toBe(200);
    const data=await response.json();expect(data.mapping_approved).toBe(false);expect(data.real_source_access).toBe(false);expect(data.relationships_persisted).toBe(false);
  }
  await panel.getByText('Identifiants, provenance et validation des exemples',{exact:true}).click();
  await expect(panel.getByText(/Ce jeu versionné n’est pas un import publié/).first()).toBeVisible();
  await expect(panel).toContainText('SYNTH-BATCH-physical');
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/source-mapping-mobile.png',fullPage:true});
  await page.reload();await expect(panel.getByRole('table')).toHaveCount(0);
  await panel.getByRole('button',{name:'Voir la démonstration synthétique'}).click();
  await expect(panel.getByRole('table').locator('tbody tr')).toHaveCount(1);
  expect((await page.request.get(root+'?mode=published')).status()).toBe(400);
});

test('Source preview hides old candidates when the source fails and recovers',async({page})=>{
  await login(page);await openClient(page);
  const panel=page.getByRole('region',{name:'Préparation du rapprochement source'});
  await panel.getByRole('button',{name:'Voir la démonstration synthétique'}).click();
  await expect(panel.getByRole('table')).toBeVisible();
  await page.route('**/source-mapping-preview/**',r=>r.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await panel.getByRole('button',{name:'Voir la démonstration synthétique'}).click();
  await expect(panel.getByRole('heading',{name:'Prévisualisation source indisponible'})).toBeVisible();
  await expect(panel.getByRole('table')).toHaveCount(0);
  await page.unroute('**/source-mapping-preview/**');
  await panel.getByRole('button',{name:'Voir la démonstration synthétique'}).click();
  await expect(panel.getByRole('table')).toBeVisible();
});

test('Ordinary reader cannot request source preview even on an accessible dossier',async({page})=>{
  await login(page,'reader');const id=await openClient(page);
  await expect(page.getByRole('button',{name:'Voir la démonstration synthétique'})).toHaveCount(0);
  expect((await page.request.get(`/api/clients/${id}/source-mapping-preview/`)).status()).toBe(403);
});
