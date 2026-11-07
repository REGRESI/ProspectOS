import { test, expect, Page } from "@playwright/test";
let sessionCookies: Awaited<
  ReturnType<import("@playwright/test").BrowserContext["cookies"]>
> = [];
test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3100",
  });
  const page = await context.newPage();
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
  sessionCookies = await context.cookies();
  await context.close();
});
test.beforeEach(async ({ context }) => {
  await context.addCookies(sessionCookies);
});
async function setup(page: Page) {
  await page.goto("/");
  await expect(page.locator(".stat-card").first()).toBeVisible();
  const me = await (await page.request.get("/api/v1/me")).json();
  const response = await page.request.post("/api/v1/workspaces", {
    headers: { "X-CSRF-Token": me.csrf_token },
    data: { name: `E2E Journey ${Date.now()}` },
  });
  expect(response.ok()).toBeTruthy();
  const ws = await response.json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return {
    base: `/api/v1/workspaces/${ws.id}`,
    headers: { "X-CSRF-Token": me.csrf_token },
    ws,
  };
}
async function nav(page: Page, label: string) {
  const menu = page.getByRole("button", {
    name: "Navigation öffnen",
    exact: true,
  });
  if (await menu.isVisible()) await menu.click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}
test("guided business onboarding → confirmed discovery job → selected import → real company count", async ({
  page,
}) => {
  const { base } = await setup(page);
  await nav(page, "Workspace-Einrichtung");
  await page.getByLabel("Was bietest du an?").fill("Synthetischer Testservice");
  await page.getByLabel("Region", { exact: true }).fill("Berlin");
  await page
    .getByLabel("Wen möchtest du erreichen?")
    .fill("Synthetische Testunternehmen");
  await page
    .getByRole("button", { name: "Geschäftskontext speichern" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Workspace-Profil gespeichert",
  );
  await nav(page, "Lead Discovery");
  await expect(
    page.getByRole("button", { name: "Suche starten", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("checkbox", {
      name: "Ich habe Filter und zulässigen Nutzungszweck geprüft.",
    })
    .check();
  await page
    .getByRole("button", { name: "Suche starten", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", {
      name: "Alle sichtbaren Ergebnisse auswählen",
    }),
  ).toBeVisible({ timeout: 15000 });
  await page
    .getByRole("checkbox", { name: "Alle sichtbaren Ergebnisse auswählen" })
    .check();
  await page.getByRole("button", { name: /Auswahl übernehmen/ }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`${base}/contacts`)).json()).total,
    )
    .toBe(5);
  await page.screenshot({
    path: "test-results/experience-discovery.png",
    fullPage: true,
  });
  await nav(page, "Unternehmen");
  await expect(page.locator("tbody tr")).toHaveCount(5);
  const summary = await (
    await page.request.get(`${base}/companies/summary`)
  ).json();
  expect(
    summary.items.every(
      (company: { contact_count: number }) => company.contact_count === 1,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/experience-companies.png",
    fullPage: true,
  });
});
test("contact profile → campaign enrollment → sequence → approved draft; foreign workspace denies context", async ({
  page,
}) => {
  const { base, headers } = await setup(page);
  const contact = await (
    await page.request.post(`${base}/contacts`, {
      headers,
      data: {
        first_name: "Synthetisch",
        last_name: "Journey",
        company: "Fiktive Journey GmbH",
        job_title: "Office Management",
        location: "Berlin",
      },
    })
  ).json();
  const campaign = await (
    await page.request.post(`${base}/campaigns`, {
      headers,
      data: {
        name: "Synthetische Sequenz",
        goal: "Manuellen Test prüfen",
        contact_ids: [],
      },
    })
  ).json();
  await nav(page, "Kontakte");
  await page.getByRole("button", { name: /Synthetisch Journey/ }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Outreach & Verlauf" }).click();
  await dialog
    .getByLabel("Kampagne für diesen Kontakt")
    .selectOption(campaign.id);
  await dialog
    .getByRole("button", { name: "Kontakt zur Kampagne hinzufügen" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Kontakt zur Kampagne hinzugefügt",
  );
  await dialog.getByRole("button", { name: "Schließen", exact: true }).click();
  await page.goto(`/campaigns/${campaign.id}`);
  await expect(
    page.getByRole("heading", { name: "Geplante Gesprächssequenz" }),
  ).toBeVisible();
  await page
    .getByLabel("Nachrichtenvorlage")
    .fill("Hallo {{first_name}}, wir prüfen {{company}} manuell.");
  await page
    .getByRole("button", { name: "Sequenz speichern", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Sequenz gespeichert");
  await page
    .getByRole("button", { name: "Entwürfe aus Sequenz erstellen" })
    .click();
  await expect(page.locator(".journey-draft-card")).toContainText(
    "Hallo Synthetisch, wir prüfen Fiktive Journey GmbH manuell.",
  );
  await page
    .getByRole("button", { name: "Revision freigeben", exact: true })
    .click();
  await expect(page.locator(".journey-draft-card")).toContainText(
    "Freigegeben",
  );
  await page.screenshot({
    path: "test-results/experience-outreach.png",
    fullPage: true,
  });
  const inbox = await (await page.request.get(`${base}/outreach/inbox`)).json();
  expect(inbox.items[0].approved_revision).toBe(inbox.items[0].revision);
  const other = await (
    await page.request.post("/api/v1/workspaces", {
      headers,
      data: { name: `E2E Foreign ${Date.now()}` },
    })
  ).json();
  expect(
    (
      await page.request.get(
        `/api/v1/workspaces/${other.id}/contacts/${contact.id}/context`,
      )
    ).status(),
  ).toBe(404);
});
test("structured ICP create/update → list application and responsive product views", async ({
  page,
}) => {
  const { base } = await setup(page);
  await nav(page, "Zielgruppen & ICP");
  await page.getByLabel("Profilname").fill("Synthetisches ICP");
  await page
    .getByLabel("Regionen und Standorte", { exact: true })
    .fill("Berlin");
  await page
    .getByRole("button", { name: "Regionen und Standorte hinzufügen" })
    .click();
  await page.getByRole("button", { name: "ICP-Profil speichern" }).click();
  await expect(page.getByRole("status")).toContainText(
    "ICP-Profil gespeichert",
  );
  await page.getByLabel("Profilname").fill("Synthetisches ICP aktualisiert");
  await page.getByRole("button", { name: "ICP-Profil speichern" }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`${base}/icp-profiles`)).json()).items[0]
          .version,
    )
    .toBe(2);
  await page.getByRole("button", { name: "Auf Leadliste anwenden" }).click();
  await expect(page).toHaveURL(/contacts\?icp=/);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [375, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [label, slug] of [
      ["Übersicht", "home"],
      ["Lead Discovery", "discovery"],
      ["Kontakte", "leads"],
      ["Outreach-Entwürfe", "outreach"],
      ["Social Studio", "social"],
      ["CRM / Pipeline", "crm"],
    ]) {
      await nav(page, label);
      await expect(page.getByRole("main")).toBeVisible();
      await expect(page.getByRole("main").locator(".spin")).toHaveCount(0);
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= window.innerWidth + 1,
          ),
        )
        .toBe(true);
      await page.screenshot({
        path: `test-results/experience-${slug}-${width}.png`,
        fullPage: true,
      });
    }
  }
  expect(errors).toEqual([]);
});
