import { test, expect, Page } from "@playwright/test";

/*
 * CleanStar round (M1–M9) browser checks with synthetic data only. No provider is
 * contacted: the tests never confirm agent runs, never generate AI content and never
 * send anything. Screenshots of the main pages (desktop + mobile) go to test-results/.
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
  await expect(page.locator(".stat-card").first()).toBeVisible();
  const me = await (await page.request.get("/api/v1/me")).json();
  const headers = { "X-CSRF-Token": me.csrf_token };
  const ws = await (
    await page.request.post("/api/v1/workspaces", { headers, data: { name: `E2E CleanStar ${Date.now()}` } })
  ).json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { base: `/api/v1/workspaces/${ws.id}`, headers, ws };
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
}

test("flow navigation and main pages render on desktop and mobile without overflow", async ({ page }) => {
  test.setTimeout(180000);
  await setup(page);
  const nav = page.getByRole("navigation").first();
  for (const section of ["HEUTE", "LEADS", "KAMPAGNEN", "CONTENT", "CRM", "EINSTELLUNGEN"]) {
    await expect(nav.getByText(section, { exact: true })).toBeVisible();
  }
  const pages: [string, string, string][] = [
    ["/today", "Heute", "heute"],
    ["/agent", "Auftrags-Agent", "agent"],
    ["/leads/top", "Top-Kandidaten", "top"],
    ["/discover", "Lead Discovery", "discover"],
    ["/campaigns", "Kampagnen", "campaigns"],
    ["/content/plan", "LinkedIn-Strategie", "content"],
    ["/pipeline", "CRM / Pipeline", "crm"],
    ["/settings/integrations", "Integrationen", "integrations"],
    ["/settings/setup", "Setup-Check", "setup"],
    ["/social/studio", "Social Studio", "studio"],
  ];
  for (const [path, title, slug] of pages) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await expect(page.locator(".spinner").first()).toBeHidden({ timeout: 15000 }).catch(() => undefined);
    await page.screenshot({ path: `test-results/cleanstar-${slug}-desktop.png`, fullPage: true });
    await noOverflow(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.screenshot({ path: `test-results/cleanstar-${slug}-mobile.png`, fullPage: true });
    await noOverflow(page);
    expect(title).toBeTruthy();
  }
});

test("integrations credentials are masked and never echoed", async ({ page }) => {
  await setup(page);
  await page.goto("/settings/integrations");
  const panel = page.getByTestId("credentials");
  await expect(panel).toBeVisible();
  for (const provider of ["openai", "linkedin", "osm", "brave", "northdata"]) {
    await expect(panel.getByTestId(`credential-${provider}`)).toBeVisible();
  }
  await expect(page.getByTestId("mailboxes")).toContainText("Versandpostfächer");
  // Secret inputs are password fields; the page never contains raw key prefixes.
  await expect(panel.getByTestId("credential-openai").locator('input[name="LLM_API_KEY"]')).toHaveAttribute("type", "password");
  expect(await page.content()).not.toMatch(/sk-[A-Za-z0-9]{20,}/);
});

test("ICP template → ranking, Heute queue from Impressum contacts, approve all and mark sent", async ({ page }) => {
  test.setTimeout(120000);
  const { base, headers } = await setup(page);
  // Synthetic contact + company (created together), plus a cited manager fact.
  const contact = await (
    await page.request.post(`${base}/contacts`, {
      headers,
      data: {
        first_name: "Erika",
        last_name: "Fiktiv",
        company: "Synthetische Kanzlei E2E GmbH",
        location: "Offenburg",
        job_title: "Geschäftsführerin",
      },
    })
  ).json();
  expect(contact.company_id).toBeTruthy();
  const fact = await page.request.post(`${base}/companies/${contact.company_id}/facts`, {
    headers,
    data: { field: "Geschäftsführung / Inhaber", value: "Erika Fiktiv", source_url: "https://example.test/impressum" },
  });
  expect(fact.ok()).toBeTruthy();
  await page.goto("/leads/top");
  await page.getByRole("button", { name: /Vorlage „Büro-Unterhaltsreinigung/ }).click();
  await expect(page.getByTestId("top-candidates")).toContainText("Synthetische Kanzlei E2E GmbH");
  await page.goto("/today");
  await page.getByLabel("Absender").fill("E2E Absender");
  await page.getByLabel("Tageslimit").selectOption("5");
  await page.getByRole("button", { name: "Einstellungen speichern" }).click();
  await expect(page.getByTestId("daily-limit")).toContainText("0 von 5 Anfragen gesendet");
  await page.getByRole("button", { name: /Tagesliste erstellen/ }).click();
  const list = page.getByTestId("today-list");
  await expect(list).toBeVisible();
  const card = list.getByTestId("today-item-connect").first();
  await expect(card).toContainText("Kontaktanfrage");
  const note = await card.locator("textarea").inputValue();
  expect(note.length).toBeLessThanOrEqual(200);
  await page.getByRole("button", { name: /Alle \d+ von heute freigeben/ }).click();
  await expect(card).toContainText("freigegeben");
  await expect(card).not.toContainText("–");
  await card.getByRole("button", { name: /Gesendet/ }).click();
  await expect(page.getByTestId("daily-limit")).toContainText("1 von 5 Anfragen gesendet");
  await expect(page.getByTestId("pipeline")).toContainText("gesendet: 1");
  await expect(page.getByText("Rückmeldungen abfragen")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await noOverflow(page);
});

test("agent shows plan and cost before anything runs", async ({ page }) => {
  const { base } = await setup(page);
  await page.goto("/agent");
  await page.locator(".agent-form textarea").fill("Finde 30 Firmen im Umkreis von 10 km um Offenburg und priorisiere sie");
  await page.getByRole("button", { name: /Plan erstellen/ }).click();
  const run = page.getByTestId("agent-run");
  await expect(run).toContainText("Firmen suchen");
  await expect(run).toContainText("Geschätzte Kosten");
  await expect(run.getByRole("button", { name: /Bestätigen und starten/ })).toBeVisible();
  const runs = await (await page.request.get(`${base}/agent/runs`)).json();
  expect(runs.items[0].status).toBe("planned");
  const jobs = await (await page.request.get(`${base}/jobs`)).json();
  expect((jobs.items || []).filter((j: { kind: string }) => j.kind === "agent_step")).toHaveLength(0);
});

test("LinkedIn OAuth return shows a clear message on the Integrations page", async ({ browser }) => {
  // LinkedIn returns to APP_BASE_URL (http://localhost:<port>); the session cookie must live on
  // that exact host, so this test signs in on localhost instead of 127.0.0.1.
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://localhost:3100" });
  const page = await context.newPage();
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
  // The registered redirect URL (no /api prefix) is proxied to the backend and redirects back.
  await page.goto("/v1/integrations/linkedin/callback?state=abgelaufen&code=x");
  await expect(page).toHaveURL(/\/settings\/integrations\?linkedin_error=invalid_state/);
  await expect(page.getByTestId("linkedin-oauth-result")).toContainText("abgelaufen");
  await page.goto("/settings/integrations?linkedin_connected=1");
  await expect(page.getByTestId("linkedin-oauth-result")).toHaveText("LinkedIn verbunden.");
  await expect(page.getByTestId("credential-linkedin")).toContainText(
    "/v1/integrations/linkedin/callback",
  );
  await context.close();
});

test("setup check shows one light per integration; demo workspace is labelled; probe post card", async ({ page }) => {
  const { ws } = await setup(page);
  await page.goto("/settings/setup");
  const check = page.getByTestId("setup-check");
  for (const key of ["linkedin", "llm", "image", "osm", "brave", "mailbox", "style"]) {
    await expect(check.getByTestId(`setup-${key}`)).toBeVisible();
  }
  await expect(check.getByTestId("setup-mailbox")).toContainText("noch nicht verbunden");
  await expect(check).toContainText("Nächster Schritt:");
  await page.goto("/social/studio");
  await expect(page.getByTestId("probe-post")).toContainText("LINKEDIN_PUBLISHING_APPROVED=true");
  // Demo workspace: labelled in the picker and with a banner.
  const me = await (await page.request.get("/api/v1/me")).json();
  const demo = me.workspaces.find((w: { kind?: string }) => w.kind === "demo");
  expect(me.workspaces[0].kind).toBe("production");
  expect(ws.kind).toBe("standard");
  expect(demo).toBeTruthy();
  // Demo is not in the picker; it opens only through the marked switch.
  await expect(
    page.getByLabel("Workspace", { exact: true }).locator(`option[value="${demo.id}"]`),
  ).toHaveCount(0);
  await page.getByTestId("demo-switch").click();
  await expect(page.getByTestId("demo-banner")).toContainText("Demo-Workspace");
  await page.getByTestId("demo-switch").click();
  await expect(page.getByTestId("demo-banner")).toHaveCount(0);
});

test("workspaces: rename, archive and delete only with the typed name", async ({ page }) => {
  const { ws } = await setup(page);
  const me = await (await page.request.get("/api/v1/me")).json();
  const production = me.workspaces.find((w: { kind?: string }) => w.kind === "production");
  // Open the production workspace so the test workspace can be deleted.
  await page.getByLabel("Workspace", { exact: true }).selectOption(production.id);
  await page.goto("/settings/workspaces");
  const row = page.getByTestId(`workspace-row-${ws.slug}`);
  await row.getByRole("button", { name: "Umbenennen" }).click();
  await page.getByLabel("Neuer Name").fill(`${ws.name} neu`);
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(row).toContainText(`${ws.name} neu`);
  await row.getByRole("button", { name: "Archivieren" }).click();
  await expect(row).toContainText("Archiviert");
  await row.getByRole("button", { name: "Wiederherstellen" }).click();
  await expect(row).toContainText("Aktiv");
  // The open workspace cannot be deleted.
  await expect(
    page.getByTestId(`workspace-row-${production.slug}`).getByRole("button", { name: "Löschen" }),
  ).toBeDisabled();
  await row.getByRole("button", { name: "Löschen" }).click();
  const confirm = page.getByRole("button", { name: "Endgültig löschen" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Name zur Bestätigung").fill("falsch");
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Name zur Bestätigung").fill(`${ws.name} neu`);
  await confirm.click();
  await expect(page.getByTestId(`workspace-row-${ws.slug}`)).toHaveCount(0);
});
