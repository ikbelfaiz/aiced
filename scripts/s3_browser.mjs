// Actual unchanged React screens against the isolated Integration service.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium, expect } = require('@playwright/test');
const state = JSON.parse(readFileSync(process.env.AICED_S3_STATE, 'utf8'));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
const base = process.env.AICED_S3_URL;
try {
  await page.goto(`${base}/gestion-donnees`);
  await page.getByLabel('Identifiant professionnel').fill(state.uploader.username);
  await page.getByLabel('Mot de passe', { exact: true }).fill(process.env.AICED_S3_PASSWORD);
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Gestion des données', exact: true })).toBeVisible();
  await page.getByRole('button', { name: `Examiner le lot ${state.batch_id}`, exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Prévisualisation du lot' })).toBeVisible();
  await expect(page.getByText('Snapshot publié · aucun client fusionné', { exact: true })).toBeVisible();
  console.log('PASS: login, existing import list, restored immutable snapshot preview');
  await page.getByLabel('Fichier XLSX', { exact: true }).setInputFiles(process.env.AICED_S3_WORKBOOK);
  await page.getByRole('button', { name: 'Valider et prévisualiser' }).click();
  await expect(page.getByText('Staging · aucun effet métier', { exact: true })).toBeVisible();
  await expect(page.getByText('2 rejet(s)', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Rapport des rejets CSV' })).toBeVisible();
  await page.screenshot({ path: `${process.env.AICED_S3_REPORT_DIR}/integration-ui.png`, fullPage: true });
  console.log('PASS: actual upload, Zod contract, duplicate-row preview and rejection report link');
  await page.locator('.profile-menu summary').click();
  await page.getByRole('button', { name: 'Se déconnecter' }).click();
  await page.getByLabel('Identifiant professionnel').fill(state.it.username);
  await page.getByLabel('Mot de passe', { exact: true }).fill(process.env.AICED_S3_PASSWORD);
  await page.getByRole('button', { name: 'Connexion', exact: true }).click();
  await expect(page).not.toHaveURL(/\/connexion/);
  await page.goto(`${base}/gestion-donnees`);
  await expect(page.getByRole('heading', { name: 'Gestion des données non autorisée' })).toBeVisible();
  console.log('PASS: IT/superuser without finance receives permission-aware denial');
} catch (error) {
  await page.screenshot({ path: `${process.env.AICED_S3_REPORT_DIR}/integration-ui-failed.png`, fullPage: true });
  throw error;
} finally {
  await browser.close();
}
