import { test, expect, type Page } from "@playwright/test";

test("Client 360 stale editor refuses to overwrite a concurrent CRM update", async ({
  page,
}) => {
  await login(page, "operator");
  await page.goto("/clients");
  await page
    .getByLabel("Rechercher un client", { exact: true })
    .fill("CLIENT SYNTHÉTIQUE A");
  // A fresh database already has one visible row before the debounced search.
  // Wait for the filter itself, so clicking cannot race the URL update.
  await expect.poll(() => new URL(page.url()).searchParams.get('recherche')).toBe('CLIENT SYNTHÉTIQUE A');
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("link", { name: /Voir la fiche de/ }).click();
  await expect(
    page.getByRole("button", { name: "Modifier le profil CRM" }),
  ).toBeEnabled();
  const id = new URL(page.url()).pathname.split("/").pop()!;
  await page.goto(`/clients/${id}?apercu=maquette`);
  await expect(page.getByRole('button',{name:'Modifier le profil CRM'})).toBeEnabled();
  await expect(page.locator('.preview-notice')).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Aperçu maquette'})).toHaveCount(0);
  const workspace = await (
    await page.request.get(`/api/clients/${id}/workspace/`)
  ).json();
  await expect(
    page.getByRole("button", { name: "Modifier l’identité AICED" }),
  ).toHaveCount(0);
  const csrf = await (await page.request.get("/api/auth/csrf/")).json();
  const denied = await page.request.patch(`/api/clients/${id}/identity/`, {
    headers: { "X-CSRFToken": csrf.csrfToken },
    data: { version: 1, first_name: "Forbidden", last_name: "Source" },
  });
  expect(denied.status()).toBe(403);
  await page.getByRole("button", { name: "Modifier le profil CRM" }).click();
  await page.getByLabel("Notes CRM").fill("Synthetic stale browser editor");
  const concurrent = await page.request.patch(`/api/clients/${id}/profile/`, {
    headers: { "X-CSRFToken": csrf.csrfToken },
    data: {
      version: workspace.crm.version,
      notes: "Synthetic concurrent update",
    },
  });
  expect(concurrent.status()).toBe(200);
  const refreshed = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/clients/${id}/workspace/`) &&
      response.request().method() === "GET",
  );
  await page.evaluate(() =>
    window.dispatchEvent(new Event("visibilitychange")),
  );
  await refreshed;
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "Version obsolète",
  );
  await page.getByRole("button", { name: "Annuler", exact: true }).click();
  await page.reload();
  await expect(
    page.getByText("Synthetic concurrent update", { exact: true }),
  ).toBeVisible();
});
async function login(page: Page, role: string) {
  await page.goto("/connexion");
  await page
    .getByLabel("Identifiant professionnel")
    .fill(`synthetic.${role}.a`);
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Connexion", exact: true }).click();
  await expect(page.locator(".profile-text strong")).toHaveText(
    `synthetic.${role}.a`,
  );
  await page.goto("/tableau-de-bord");
  await expect(
    page.getByRole("heading", { name: "Tableau de bord", exact: true }),
  ).toBeVisible();
}
async function logout(page: Page) {
  await page.locator(".profile-menu summary").click();
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/connexion/);
}

test("Client 360 actual AICED creation, profile, interaction and opportunity editing", async ({
  page,
}) => {
  await login(page, "operator");
  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await page.getByRole("button", { name: "Nouveau client" }).click();
  const name = `Navigateur ${Date.now()}`;
  await page
    .getByLabel("Prénom (personne physique)", { exact: true })
    .fill("Synthétique");
  await page.getByLabel("Nom (personne physique)", { exact: true }).fill(name);
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: `Synthétique ${name}`, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Modifier le profil CRM" }).click();
  await page
    .getByLabel("Email commercial AICED")
    .fill("browser@example.invalid");
  await page
    .getByLabel("Profession déclarée au CRM")
    .fill("Profession synthétique");
  await page
    .getByLabel("Notes CRM")
    .fill("Note synthétique du test navigateur");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("browser@example.invalid", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Modifier l’identité AICED" }).click();
  await page.getByLabel("Prénom", { exact: true }).fill("Synthétique édité");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: `Synthétique édité ${name}` }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Ajouter une interaction", exact: true })
    .click();
  await page
    .getByLabel("Objet", { exact: true })
    .fill("Appel synthétique navigateur");
  await page
    .getByLabel("Date et heure de l’interaction réalisée")
    .fill("2026-01-01T10:00");
  await page.getByLabel("Compte rendu").fill("Compte rendu synthétique");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("Appel synthétique navigateur", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Sections de la fiche client" })
    .getByRole("button", { name: "Opportunités", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ajouter une opportunité", exact: true })
    .click();
  await page
    .getByLabel("Intitulé", { exact: true })
    .fill("Opportunité synthétique");
  await page
    .getByLabel("Estimation commerciale en TND (facultatif)")
    .fill("123.456");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("123.456 TND · estimation commerciale AICED"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Modifier Opportunité synthétique" })
    .click();
  await page
    .getByLabel("Intitulé", { exact: true })
    .fill("Opportunité synthétique modifiée");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("Opportunité synthétique modifiée", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Vue générale" }).click();
  await page.setViewportSize({ width: 1440, height: 1260 });
  await page.screenshot({
    path: "../.local/ui-review/screens/client-360.png",
    fullPage: true,
  });
  await page.reload();
  await expect(
    page.getByText("browser@example.invalid", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../.local/ui-review/screens/client-360-mobile.png",
    fullPage: true,
  });
});

test("Data Management malformed upload, preview, duplicate replay, independent approval and publication", async ({
  page,
}) => {
  await login(page, "operator");
  await page
    .getByRole("link", { name: "Gestion des données", exact: true })
    .click();
  await page.getByLabel("Usage d\u00e9clar\u00e9 du fichier").selectOption("synthetic");
  await page.getByLabel("Fichier XLSX", { exact: true }).setInputFiles({
    name: "bad.xlsx",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("not xlsx"),
  });
  await page.getByRole("button", { name: "Valider et prévisualiser" }).click();
  await expect(page.getByRole("alert")).toContainText("invalide");
  await page
    .getByLabel("Fichier XLSX", { exact: true })
    .setInputFiles("../.local/ui-review/synthetic-legal.xlsx");
  await page
    .getByLabel("Date de situation source", { exact: true })
    .fill("2026-03-01");
  await page
    .getByLabel("Format des dates source", { exact: true })
    .selectOption("DMY");
  await page.getByRole("button", { name: "Valider et prévisualiser" }).click();
  await expect(
    page.getByRole("heading", { name: "Prévisualisation du lot" }),
  ).toBeVisible();
  await expect(page.getByText("2 rejet(s)", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Date normalisée : 2026-02-13", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Examiner la publication" }),
  ).toBeDisabled();
  const batchId = await page
    .locator(".card-subtitle")
    .filter({ hasText: /· Tiers personnes morales · source manuelle Excel/ })
    .textContent();
  await page.getByRole("button", { name: "Valider et prévisualiser" }).click();
  await expect(
    page
      .locator(".card-subtitle")
      .filter({ hasText: /· Tiers personnes morales · source manuelle Excel/ }),
  ).toHaveText(batchId!);
  await expect(page.getByRole('button',{name:'Valider et prévisualiser',exact:true})).toBeEnabled();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Rapport des rejets CSV" }).click();
  expect((await download).suggestedFilename()).toBe("rejets.csv");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.locator("#main").focus();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.local/ui-review/screens/data-upload-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1260 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.local/ui-review/screens/data-upload.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Règles de publication", exact: true })
    .click();
  const importContext = await (await page.request.get('/api/imports/context/')).json();
  const importOrg = importContext.organizations[0].id;
  const prior = await (await page.request.get(`/api/imports/${importOrg}/policies/?view=available`)).json();
  // Approval/revocation is performed by the independent reviewer below.
  await page.getByRole("button", { name: "Proposer une règle" }).click();
  await expect(
    page.getByLabel("Interprétation des dates à approuver"),
  ).toHaveValue("DMY");
  const rationale = `Règle synthétique navigateur ${Date.now()} : colonne 2, snapshots immuables, aucune fusion.`;
  await page
    .getByLabel(
      "Justification de propriété et d’unicité (20 caractères minimum)",
    )
    .fill(rationale);
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByText(rationale, { exact: true })).toBeVisible();
  await logout(page);
  await login(page, "reviewer");
  await page
    .getByRole("link", { name: "Gestion des données", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Règles de publication", exact: true })
    .click();
  const ruleCsrf = (await (await page.request.get('/api/auth/csrf/')).json()).csrfToken;
  for (const previous of prior.filter((p:{template:string;date_format:string;data_scope:string;approved_at:string|null}) => p.template==='legal' && p.date_format==='DMY' && p.data_scope==='synthetic' && p.approved_at)) {
    expect((await page.request.post(`/api/imports/${importOrg}/policies/${previous.id}/revoke/`, {headers:{'X-CSRFToken':ruleCsrf},data:{}})).status()).toBe(200);
  }
  await page.getByLabel("Afficher les r\u00e8gles").selectOption("pending");
  const rule = page
    .locator(".policy-list article")
    .filter({ hasText: rationale });
  await rule
    .getByRole("button", { name: "Approuver la règle", exact: true })
    .click();
  await page.getByRole("button", { name: "Confirmer la décision" }).click();
  await expect(rule.getByText("Approuvée", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Imports & historique" }).click();
  await page
    .getByRole("button", { name: /Examiner le lot/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Examiner la publication" }).click();
  await page
    .getByLabel("Règle approuvée", { exact: true })
    .selectOption({ label: `Colonne 2 · ${rationale.slice(0, 70)}` });
  await expect(
    page.getByRole("button", { name: "Confirmer la publication" }),
  ).toBeDisabled();
  await page.getByLabel(/J’exclus explicitement/).check();
  await page.getByRole("button", { name: "Confirmer la publication" }).click();
  await expect(
    page.getByText("Snapshot publié · aucun client fusionné", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("1 snapshot(s) publié(s)", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("#main")).toBeFocused();
  await page.setViewportSize({ width: 1440, height: 1260 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.local/ui-review/screens/data-management.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../.local/ui-review/screens/data-management-mobile.png",
    fullPage: true,
  });
});
