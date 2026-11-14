import { test, expect } from "@playwright/test";

test("Prospects vertical slice persists qualification, interaction and opportunity", async ({
  page,
}) => {
  await page.goto("/connexion");
  await page
    .getByLabel("Identifiant professionnel")
    .fill("synthetic.operator.a");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Connexion", exact: true }).click();
  await page.getByRole("link", { name: "Prospects", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Prospects", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Nouveau prospect", exact: true })
    .click();
  const name = `Prospect navigateur ${Date.now()}`;
  await page
    .getByLabel("Prénom (personne physique)", { exact: true })
    .fill("SYNTHÉTIQUE");
  await page.getByLabel("Nom (personne physique)", { exact: true }).fill(name);
  await page
    .getByLabel("Source du contact")
    .fill("Événement synthétique navigateur");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("Rechercher un prospect", { exact: true }).fill(name);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Qualifier", exact: true }).click();
  await page.getByLabel("Statut", { exact: true }).selectOption("qualified");
  await page
    .getByLabel("Prochaine action", { exact: true })
    .fill("Rendez-vous synthétique");
  await page.getByLabel("Date de la prochaine action").fill("2026-12-01");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator("tbody")).toContainText("Qualifié");
  await page
    .getByRole("link", { name: `SYNTHÉTIQUE ${name}`, exact: true })
    .click();
  await page
    .getByRole("button", { name: "Ajouter une interaction", exact: true })
    .click();
  await page
    .getByLabel("Objet", { exact: true })
    .fill("Appel prospect synthétique");
  await page
    .getByLabel("Date et heure de l’interaction réalisée")
    .fill("2026-01-01T10:00");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("Appel prospect synthétique", { exact: true }),
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
    .fill("Proposition prospect synthétique");
  await page
    .getByLabel("Estimation commerciale en TND (facultatif)")
    .fill("321.125");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(
    page.getByText("321.125 TND · estimation commerciale AICED"),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Proposition prospect synthétique", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Retour aux prospects" }).click();
  await page.getByLabel("Rechercher un prospect", { exact: true }).fill(name);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody")).toContainText("01/01/2026");
  await page.getByRole('heading', {name:'Prospects', exact:true}).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../.local/ui-review/screens/prospects-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "../.local/ui-review/screens/prospects-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByLabel("Rechercher un prospect", { exact: true })
    .fill("SYNTHETIC-NO-SUCH-PROSPECT");
  await expect(
    page.getByRole("heading", { name: "Aucun prospect dans cette sélection" }),
  ).toBeVisible();
});

test("Prospects route denies IT and handles API failure without exposing cached rows", async ({
  page,
}) => {
  await page.goto("/connexion");
  await page.getByLabel("Identifiant professionnel").fill("synthetic.it.a");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Connexion", exact: true }).click();
  await expect(page.locator(".profile-text strong")).toHaveText(
    "synthetic.it.a",
  );
  await page.goto("/prospects");
  await expect(
    page.getByRole("heading", { name: "Accès aux prospects non autorisé" }),
  ).toBeVisible();
  expect((await page.request.get("/api/prospects/")).status()).toBe(403);
  await page.locator(".profile-menu summary").click();
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await page
    .getByLabel("Identifiant professionnel")
    .fill("synthetic.operator.a");
  await page
    .getByLabel("Mot de passe", { exact: true })
    .fill(process.env.AICED_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Connexion", exact: true }).click();
  await expect(page.locator(".profile-text strong")).toHaveText(
    "synthetic.operator.a",
  );
  await page.route("**/api/prospects/?*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { status: 503, details: "Synthetic failure" },
      }),
    }),
  );
  await page.goto("/prospects");
  await expect(
    page.getByRole("heading", { name: "Impossible de charger les prospects" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(0);
  await page.unroute("**/api/prospects/?*");
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(page.locator("tbody tr").first()).toBeVisible();
});
