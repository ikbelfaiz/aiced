import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

async function login(page:Page, role='reader') {
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill(`synthetic.${role}.a`);
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
}
test('real session, validation, client search, detail, denied finance and logout',async({page})=>{
  await page.goto('/clients'); await expect(page).toHaveURL(/connexion/);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByText('Renseignez votre identifiant professionnel.')).toBeVisible();
  await page.getByLabel('Identifiant professionnel').fill('synthetic.reader.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Panorama Clients'})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  let financialRequests=0; page.on('request',r=>{if(r.url().includes('/accounts/'))financialRequests++;});
  await page.getByRole('link',{name:/Voir la fiche de/}).click();
  await expect(page.getByText('Consultation financière non autorisée.')).toBeVisible();
  expect(financialRequests).toBe(0); await page.goto('/clients');
  await page.getByLabel('Rechercher un client',{exact:true}).fill('ABSENT_SYNTHETIC');
  await expect(page.getByRole('heading',{name:'Aucun client ne correspond à votre recherche'})).toBeVisible();
  await page.getByRole('button',{name:'Réinitialiser les filtres'}).first().click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.locator('.profile-menu summary').click(); await page.getByRole('button',{name:'Se déconnecter'}).click();
  await expect(page).toHaveURL(/connexion/); expect(await page.evaluate(()=>localStorage.length)).toBe(0);
});
test('IT cannot enter clients or enable financial preview',async({page})=>{
  await login(page,'it'); await page.goto('/clients?apercu=maquette');
  await expect(page.getByRole('heading',{name:'Accès non autorisé'})).toBeVisible();
  await expect(page.getByText('Karim Ben Youssef')).toHaveCount(0);
});
test('client loading, service failure and retry',async({page})=>{
  await login(page); let release!:()=>void; const held=new Promise<void>(resolve=>release=resolve);
  await page.route('**/api/clients/?**',async route=>{await held; await route.fulfill({status:503,json:{}});});
  await page.getByRole('link',{name:'Clients',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Chargement des clients…'})).toBeVisible(); release();
  await expect(page.getByRole('heading',{name:'Impossible de charger les clients'})).toBeVisible();
  await page.unroute('**/api/clients/?**'); await page.getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
});
test('revoked permissions and expired sessions remove protected screens',async({page})=>{
  await login(page); await page.getByRole('link',{name:'Clients',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.route('**/api/auth/access/',r=>r.fulfill({json:{assignments:[]}}));
  await page.locator('.profile-menu summary').click(); await page.getByRole('button',{name:'Actualiser mes droits'}).click();
  await expect(page.getByRole('heading',{name:'Accès non autorisé'})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(0);
  await page.route('**/api/session/',r=>r.fulfill({status:403,json:{detail:'Synthetic expired session'}}));
  await page.getByRole('button',{name:'Actualiser mes droits'}).click();
  await expect(page).toHaveURL(/connexion/);
});
test('server pagination, type filter and account read contract',async({page})=>{
  await login(page,'manager'); await page.getByRole('link',{name:'Clients',exact:true}).click();
  await page.getByLabel('Rechercher un client',{exact:true}).fill('CLIENT SYNTHÉTIQUE A');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('link',{name:/Voir la fiche de/}).click();
  await expect(page.locator('.account-list li')).toHaveCount(1);
  await page.goto('/clients');
  await page.getByLabel('Type de personne',{exact:true}).selectOption('legal');
  await expect(page.getByRole('heading',{name:'Aucun client ne correspond à votre recherche'})).toBeVisible();
  await page.getByRole('button',{name:'Réinitialiser les filtres'}).first().click();
  await page.route('**/api/clients/?**',r=>{
    const query=new URL(r.request().url()).searchParams;
    return r.fulfill({json:{count:9,next:null,previous:null,results:Array.from({length:query.get('page')==='2'?1:8},(_,i)=>({id:`00000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`,display_name:`SYNTHETIC PAGE ${query.get('page')} ${i}`,kind:'physical'}))}});
  });
  await page.getByLabel('Lignes par page').selectOption('16');
  await expect(page.locator('tbody tr')).toHaveCount(8);
  await page.getByLabel('Lignes par page').selectOption('8');
  await page.getByRole('button',{name:'Page suivante'}).click();
  await expect(page).toHaveURL(/page=2/); await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('tbody')).toContainText('SYNTHETIC PAGE 2');
});
test('reference screenshots and responsive navigation',async({page})=>{
  await mkdir('../.local/ui-review/screens',{recursive:true});
  await page.goto('/connexion'); await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'../.local/ui-review/screens/connexion.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/connexion-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1080});
  await login(page,'manager');
  await page.setViewportSize({width:1440,height:1231}); await page.goto('/tableau-de-bord?apercu=maquette');
  await expect(page.locator('.preview-notice')).toBeVisible();
  await expect(page.locator('.trend-plot svg')).toBeVisible(); await page.evaluate(()=>document.fonts.ready);
  await page.screenshot({path:'../.local/ui-review/screens/dashboard.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1272}); await page.getByRole('link',{name:'Clients',exact:true}).click();
  await expect(page.locator('tbody tr')).toHaveCount(8); await page.screenshot({path:'../.local/ui-review/screens/clients.png',fullPage:true});
  for (const width of [768,390]) {
    await page.setViewportSize({width,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:`../.local/ui-review/screens/clients-${width}.png`,fullPage:true});
  }
  await page.getByRole('button',{name:'Ouvrir la navigation'}).click();
  await page.getByRole('link',{name:'Tableau de bord',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../.local/ui-review/screens/dashboard-mobile.png',fullPage:true});
});
test('production build ignores synthetic design preview parameter',async({page})=>{
  test.skip(!process.env.AICED_E2E_PRODUCTION,'Requires the compiled production build.');
  await login(page,'manager'); await page.goto('/clients?apercu=maquette&recherche=CLIENT%20SYNTH%C3%89TIQUE%20A');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await expect(page.locator('.preview-notice')).toHaveCount(0);
  await expect(page.getByText('Karim Ben Youssef',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Non calculé',{exact:true}).first()).toBeVisible();
});
