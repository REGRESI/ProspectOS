import { test, expect, Page } from "@playwright/test";

/*
 * LinkedIn profiles, email list, data quality, content strategy, brand templates, writing
 * profile and team invites. Synthetic data only; nothing calls Brave, LinkedIn or OpenAI
 * and nothing is sent or posted.
 */
let sessionCookies: Awaited<ReturnType<import("@playwright/test").BrowserContext["cookies"]>> = [];
test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://localhost:3100" });
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
  await expect(page.getByRole("heading", { name: "Heute", level: 1 })).toBeVisible();
  const me = await (await page.request.get("/api/v1/me")).json();
  const headers = { "X-CSRF-Token": me.csrf_token };
  const ws = await (
    await page.request.post("/api/v1/workspaces", { headers, data: { name: `E2E Profile ${Date.now()}` } })
  ).json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { base: `/api/v1/workspaces/${ws.id}`, headers, ws };
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test("data quality counts, email campaign stays locked, Heute explains missing profiles", async ({ page }) => {
  const { base, headers } = await setup(page);
  const a = await (
    await page.request.post(`${base}/contacts`, {
      headers,
      data: { first_name: "Mara", last_name: "Fiktiv", company: "Fiktive Praxis E2E", location: "Lahr" },
    })
  ).json();
  const fact = await page.request.post(`${base}/companies/${a.company_id}/facts`, {
    headers,
    data: {
      field: "E-Mail allgemein (Impressum)",
      value: "info@praxis.example.test, m.fiktiv@praxis.example.test",
      source_url: "https://praxis.example.test/impressum",
    },
  });
  expect(fact.ok()).toBeTruthy();
  await page.goto("/contacts/quality");
  const counts = page.getByTestId("quality-counts");
  await expect(counts).toContainText("Firmen");
  await expect(counts).toContainText("Nur E-Mail");
  await expect(page.getByTestId("quality-sample")).toContainText("Fiktive Praxis E2E");
  await page.goto("/contacts/email");
  await expect(page.getByTestId("email-locked")).toContainText("Versand gesperrt");
  const table = page.getByTestId("email-campaign");
  await expect(table).toContainText("m.fiktiv@praxis.example.test");
  await expect(table.locator("tr", { hasText: "m.fiktiv@" })).toContainText("persönlich");
  await expect(table.locator("tr", { hasText: "info@" })).toContainText("allgemein");
  await expect(page.getByRole("button", { name: /senden|versenden/i })).toHaveCount(0);
  await page.goto("/today");
  await expect(page.getByTestId("profile-check-notice")).toContainText("noch kein geprüftes LinkedIn-Profil");
  // No Brave key in the isolated stack: the notice points to the connection instead.
  await expect(page.getByTestId("profile-check-notice")).toContainText("Brave Search verbinden");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/contacts/email");
  await noOverflow(page);
});

test("campaign with seven dated slots, text pasted into part 1", async ({ page }) => {
  await setup(page);
  await page.goto("/content/campaigns");
  await page.getByRole("button", { name: "Neue Kampagne" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("Die neue CleanStar-Website");
  await dialog.getByLabel("Ziel", { exact: true }).selectOption("leads");
  await dialog.getByLabel("Zielgruppe").selectOption("ortenau_ceo");
  await dialog.getByLabel("Themensäule").fill("CleanStar-Einblicke");
  await dialog.getByLabel("Start").fill("2026-11-10");
  await dialog.getByLabel("Ende").fill("2026-11-24");
  await dialog.getByLabel("Anzahl Beiträge (Termine)").fill("7");
  await dialog.getByRole("button", { name: "Anlegen" }).click();
  const section = page.locator("[data-testid^=campaign-]").first();
  await expect(section).toContainText("Die neue CleanStar-Website");
  await expect(section).toContainText("Ziel: Anfragen gewinnen");
  await expect(section.locator("tbody tr")).toHaveCount(7);
  await expect(section.locator("tbody tr").first()).toContainText("10.11");
  await section.getByRole("button", { name: /Teil 1: Text folgt/ }).click();
  await page.getByRole("dialog").getByLabel("Text").fill("Unsere neue Website ist online. Fiktiver Testtext.");
  await page.getByRole("dialog").getByRole("button", { name: "Speichern" }).click();
  await expect(section.locator("tbody tr").first()).toContainText("Unsere neue Website ist online");
  await expect(section.locator("tbody tr").first()).toContainText("Entwurf");
});

test("brand templates export a PNG, a carousel PDF and save to the media library", async ({ page }) => {
  await setup(page);
  await page.goto("/content/templates");
  const preview = page.getByTestId("template-preview").locator("img");
  await expect(preview).toBeVisible();
  await page.getByLabel("Zahl").fill("7 Tage");
  const png = page.waitForEvent("download");
  await page.getByRole("button", { name: "Als PNG speichern" }).click();
  const file = await png;
  expect(file.suggestedFilename()).toMatch(/^cleanstar-number-.*\.png$/);
  const bytes = await (await import("node:fs/promises")).readFile(await file.path());
  expect(bytes.subarray(1, 4).toString()).toBe("PNG");
  await page.getByRole("button", { name: "In Mediathek speichern" }).click();
  await expect(page.getByRole("status")).toContainText("In der Mediathek gespeichert");
  await page.getByRole("tab", { name: "Karussell" }).click();
  await expect(page.getByText("Seite 1 von 5")).toBeVisible();
  const pdf = page.waitForEvent("download");
  await page.getByRole("button", { name: "Als PDF speichern" }).click();
  const doc = await pdf;
  const pdfBytes = await (await import("node:fs/promises")).readFile(await doc.path());
  expect(pdfBytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect((pdfBytes.toString("latin1").match(/\/Type \/Page /g) || []).length).toBe(5);
  await page.goto("/social/library");
  await expect(page.locator("body")).toContainText("7 Tage");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/content/templates");
  await noOverflow(page);
});

test("writing profile learns from an edit; rules and style references are editable", async ({ page }) => {
  const { base, headers } = await setup(page);
  const post = await (
    await page.request.post(`${base}/social/posts`, {
      headers,
      data: { caption: "Ganz ehrlich, wir revolutionieren die Reinigung! 🚀" },
    })
  ).json();
  const edited = await page.request.patch(`${base}/social/posts/${post.id}`, {
    headers,
    data: { caption: "Wir machen Reinigung planbar.", version: post.version },
  });
  expect(edited.ok()).toBeTruthy();
  await page.goto("/content/voice");
  await expect(page.getByTestId("profile-counts")).toContainText("1 Änderungen");
  await expect(page.getByTestId("recent-edits")).toContainText("Wir machen Reinigung planbar.");
  await page.getByLabel("Neue Regel").fill("Immer mit einem Beispiel aus der Ortenau.");
  await page.getByRole("button", { name: "Regel hinzufügen" }).click();
  await expect(page.getByTestId("profile-rules")).toContainText("Immer mit einem Beispiel aus der Ortenau.");
  await page.getByText("Stil-Vorbild ablegen").click();
  await page.getByLabel("Von wem").fill("Beispiel Autorin");
  await page.getByLabel("Text des Posts").fill("Ein fiktiver fremder Post mit kurzen Sätzen und einer Frage am Ende?");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByTestId("inspirations")).toContainText("Beispiel Autorin");
});

test("team: invite link, new user registers and lands in the workspace", async ({ page, browser }) => {
  const { ws } = await setup(page);
  await page.goto("/settings/team");
  await expect(page.getByTestId("team-members")).toContainText("Inhaber");
  await page.getByRole("button", { name: "Person einladen" }).click();
  const email = `lino.e2e.${Date.now()}@example.test`;
  await page.getByRole("dialog").getByLabel("E-Mail-Adresse").fill(email);
  await page.getByRole("dialog").getByLabel("Rolle").selectOption("member");
  await page.getByRole("dialog").getByRole("button", { name: "Link erstellen" }).click();
  const link = await page.getByLabel("Einladungslink").inputValue();
  expect(link).toContain("/einladung#");
  await expect(page.getByTestId("team-members")).toContainText(email);
  const guest = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://localhost:3100" });
  const g = await guest.newPage();
  await g.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await expect(g.getByRole("region", { name: "Einladung" })).toContainText("Mitglied");
  await g.getByLabel("Dein Name").fill("Lino Fiktiv");
  await g.getByLabel("Passwort (mindestens 10 Zeichen)").fill("LangesPasswort2026");
  await g.getByLabel("Passwort wiederholen").fill("LangesPasswort2026");
  await g.getByRole("button", { name: "Konto anlegen und beitreten" }).click();
  await expect(g).toHaveURL(/today/);
  const me = await (await g.request.get("/api/v1/me")).json();
  expect(me.workspaces.map((w: { id: string }) => w.id)).toEqual([ws.id]);
  await guest.close();
  await page.reload();
  await expect(page.getByTestId("team-members")).toContainText("Lino Fiktiv");
});
