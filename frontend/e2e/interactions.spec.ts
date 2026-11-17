import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('Scoped interaction history persists real exchanges, filters, pagination and Client 360 navigation',async({page})=>{
  await page.goto('/interactions');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Historique des interactions',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.getByRole('button',{name:'Nouveau client',exact:true}).click();
  const name=`SYNTHETIQUE HISTORIQUE ${Date.now()}`;
  await page.getByLabel('Prénom (personne physique)',{exact:true}).fill('TEST');
  await page.getByLabel('Nom (personne physique)',{exact:true}).fill(name);
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByRole('heading',{name:`TEST ${name}`,exact:true})).toBeVisible();
  const id=new URL(page.url()).pathname.split('/').pop()!;
  await page.getByRole('button',{name:'Ajouter une interaction',exact:true}).click();
  await page.getByLabel('Objet',{exact:true}).fill(name);
  await page.getByLabel('Date et heure de l’interaction réalisée').fill('2026-01-01T10:00');
  await page.getByLabel('Compte rendu').fill('Compte rendu synthétique historique');
  await page.getByRole('button',{name:'Enregistrer',exact:true}).click();
  await expect(page.getByText(name,{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Interactions',exact:true}).click();
  await page.getByLabel('Rechercher par client, objet ou compte rendu').fill(name);
  await page.getByRole('button',{name:'Rechercher',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByText('Lire le compte rendu',{exact:true}).click();
  await expect(page.getByText('Compte rendu synthétique historique',{exact:true})).toBeVisible();
  await page.getByLabel('Type d’interaction',{exact:true}).selectOption('email');
  await expect(page.getByRole('heading',{name:'Aucune interaction dans cette sélection'})).toBeVisible();
  await page.getByLabel('Type d’interaction',{exact:true}).selectOption('call');
  await page.getByLabel('Depuis le',{exact:true}).fill('2026-01-02');
  await expect(page.getByRole('heading',{name:'Aucune interaction dans cette sélection'})).toBeVisible();
  await page.getByLabel('Depuis le',{exact:true}).fill('2026-01-01');
  await page.getByLabel('Jusqu’au',{exact:true}).fill('2026-01-01');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  const csrf=await(await page.request.get('/api/auth/csrf/')).json();
  for(let i=0;i<8;i++) {
    const r=await page.request.post(`/api/clients/${id}/interactions/`,{headers:{'X-CSRFToken':csrf.csrfToken},
      data:{kind:'call',subject:`${name} ${i}`,notes:'Synthétique',occurred_at:'2026-01-01T09:00:00Z'}});
    expect(r.status()).toBe(201);
  }
  await page.reload();
  await expect(page.locator('tbody tr')).toHaveCount(8);
  await page.getByRole('button',{name:'Suivant',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await mkdir('../.local/ui-review/screens',{recursive:true});
  await page.screenshot({path:'../.local/ui-review/screens/interaction-history-mobile.png',fullPage:true});
  await page.getByRole('link',{name:`Ouvrir la fiche de TEST ${name}`,exact:true}).click();
  await expect(page.getByRole('heading',{name:`TEST ${name}`,exact:true})).toBeVisible();
  await expect(page.getByText(name,{exact:true})).toBeVisible();
});

test('IT cannot read the global history or discover client data through filters',async({page})=>{
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.it.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
  await page.goto('/interactions?search=SYNTHETIQUE');
  await expect(page.getByRole('heading',{name:'Historique des interactions non autorisé'})).toBeVisible();
  expect((await page.request.get('/api/interactions/?search=SYNTHETIQUE')).status()).toBe(403);
  await expect(page.locator('tbody')).toHaveCount(0);
});

test('History hides previously cached rows on service error and retries against the real API',async({page})=>{
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await page.getByRole('link',{name:'Interactions',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.route('**/api/interactions/**',route=>route.fulfill({status:503,contentType:'application/json',body:'{"error":{"status":503}}'}));
  await page.getByRole('link',{name:'Interactions',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Impossible de charger les interactions'})).toBeVisible();
  await expect(page.locator('tbody')).toHaveCount(0);
  await page.unroute('**/api/interactions/**');
  await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.locator('tbody tr').first()).toBeVisible();
});
