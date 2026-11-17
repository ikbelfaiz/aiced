import { test,expect } from '@playwright/test';
import { pipelineDiagnostics } from './pipeline-diagnostics';
pipelineDiagnostics();

test('Large synthetic pipeline keeps exact counts, deep pages and Client 360 navigation',async({page})=>{
  test.skip(process.env.AICED_E2E_SCALE!=='1','Requires the isolated S13 synthetic benchmark fixture');
  test.setTimeout(90000);
  await page.goto('/clients');
  await page.getByLabel('Identifiant professionnel').fill('synthetic.reader.b');
  await page.getByLabel('Mot de passe',{exact:true}).fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole('button',{name:'Connexion',exact:true}).click();
  await expect(page.getByRole('link',{name:'Opportunités',exact:true})).toBeVisible();
  // Login returns to the application landing route; open the requested page.
  await page.goto('/opportunites?search=S13-SYNTHETIC&ordering=title&page_size=50&page=200');
  await expect(page.locator('.pagination')).toContainText('10000 opportunité(s) · page 200',{timeout:15000});
  await expect(page.locator('.pipeline-card')).toHaveCount(50);
  await expect(page.getByRole('button',{name:'Suivant',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Précédent',exact:true}).click();
  await expect(page.locator('.pagination')).toContainText('page 199',{timeout:15000});
  await page.getByLabel('Statut',{exact:true}).selectOption('won');
  await expect(page.locator('.pagination')).toContainText('3333 opportunité(s) · page 1',{timeout:15000});
  await expect(page.locator('.pipeline-column')).toContainText('Gagnées (3333)');
  await page.locator('.pipeline-card').first().getByRole('link').click();
  await expect(page).toHaveURL(/\/clients\/.+onglet=opportunities&opportunite=/);
  await expect(page.getByRole('heading',{name:/S13-SYNTHETIC/}).first()).toBeVisible();
});
