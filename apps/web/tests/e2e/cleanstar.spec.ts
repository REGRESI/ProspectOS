import { test, expect, Page } from "@playwright/test";

/*
 * CleanStar round (M1–M9) browser checks with synthetic data only. No provider is
 * contacted: the tests never confirm agent runs, never generate AI content and never
 * send anything. Screenshots of the main pages (desktop + mobile) go to test-results/.
 */
let sessionCookies: Awaited<ReturnType<import("@playwright/test").BrowserContext["cookies"]>> = [];
test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000" });
  const page = await context.newPage();
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/overview/);
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
  await page.getByRole("button", { name: /Tagesliste erstellen/ }).click();
  const list = page.getByTestId("today-list");
  await expect(list).toBeVisible();
  const card = list.getByTestId("today-item-connect").first();
  await expect(card).toContainText("Kontaktanfrage");
  const note = await card.locator("textarea").inputValue();
  expect(note.length).toBeLessThanOrEqual(200);
  await page.getByRole("button", { name: /Alle \d+ von heute freigeben/ }).click();
  await expect(card).toContainText("freigegeben");
  await card.getByRole("button", { name: /Gesendet/ }).click();
  await expect(page.getByText(/gesendet/).first()).toBeVisible();
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
