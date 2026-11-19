import {test,expect} from '@playwright/test';
import {mkdir} from 'node:fs/promises';

test('commercial layouts show authorized data on desktop and mobile',async({page})=>{
  await page.goto('/connexion');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.operator.a');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Tableau de bord',exact:true})).toBeVisible();
  await mkdir('../.local/ui-review/screens',{recursive:true});
  for(const [path,title,name] of [['/interactions','Historique des interactions','interactions'],['/campagnes','Mes brouillons de campagnes','campagnes'],['/pilotage-crm','Pilotage CRM','pilotage']]){
    await page.setViewportSize({width:1440,height:1000});
    await page.goto(path);
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    if(name==='interactions') await expect(page.getByRole('region',{name:'Synthèse des interactions'})).toBeVisible();
    if(name==='campagnes') await expect(page.getByRole('region',{name:'Synthèse des campagnes'})).toBeVisible();
    if(name==='pilotage') await expect(page.getByRole('region',{name:'Portefeuille CRM actuel'})).toBeVisible();
    await page.screenshot({path:`../.local/ui-review/screens/${name}-desktop.png`,fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    await page.screenshot({path:`../.local/ui-review/screens/${name}-mobile.png`,fullPage:true});
  }
});
