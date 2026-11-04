import { test, expect, Page } from "@playwright/test";

/*
 * Internal Sales Agent V1 browser flows against the running API + worker + web.
 * Only synthetic data: simulator personas and fictional companies. Nothing contacts
 * LinkedIn or OpenStreetMap. The worker must run with a short LINKEDIN_SIM_DELAY_SECONDS.
 */
let sessionCookies: Awaited<
  ReturnType<import("@playwright/test").BrowserContext["cookies"]>
> = [];
test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000",
  });
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
    await page.request.post("/api/v1/workspaces", {
      headers,
      data: { name: `E2E Sales Agent ${Date.now()}` },
    })
  ).json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { base: `/api/v1/workspaces/${ws.id}`, headers, ws };
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

test("discovery shows OSM as a disclosed, configurable source with ODbL categories", async ({
  page,
}) => {
  const { base } = await setup(page);
  const providers = await (
    await page.request.get(`${base}/discovery/providers`)
  ).json();
  const osm = providers.items.find((p: { id: string }) => p.id === "osm");
  await nav(page, "Lead Discovery");
  await page.getByLabel("Datenquelle").selectOption("osm");
  const capability = page.getByTestId("provider-capability");
  await expect(capability).toContainText("ODbL 1.0");
  await expect(capability).toContainText(
    osm.available ? "Verfügbar" : "Nicht verfügbar",
  );
  await expect(capability).toContainText("Mitarbeiterzahl");
  await page.getByRole("button", { name: "Steuerberatung", exact: true }).click();
  await expect(page.getByLabel("Branchen", { exact: true })).toHaveValue(
    "Steuerberatung",
  );
  await page.screenshot({
    path: "test-results/sales-agent-discovery.png",
    fullPage: true,
  });
});

test("cited company evidence → evidence draft → approval → simulated LinkedIn connection, message and reply → CRM", async ({
  page,
}) => {
  const { base, headers } = await setup(page);
  // Synthetic simulator accounts and a campaign containing them.
  expect(
    (await page.request.post(`${base}/linkedin/simulator/seed`, { headers })).ok(),
  ).toBeTruthy();
  const accounts = (
    await (await page.request.get(`${base}/linkedin/simulator/accounts`)).json()
  ).items as { handle: string; contact_id: string }[];
  const anna = accounts.find((a) => a.handle === "sim-anna-keller")!;
  const companyId = (
    await (await page.request.get(`${base}/contacts/${anna.contact_id}/context`)).json()
  ).company.id as string;
  const campaign = await (
    await page.request.post(`${base}/campaigns`, {
      headers,
      data: { name: "E2E Sim Kampagne", goal: "Kurzer Austausch", contact_ids: [] },
    })
  ).json();
  await page.request.post(`${base}/leads/bulk`, {
    headers,
    data: { contact_ids: [anna.contact_id], campaign_id: campaign.id },
  });
  await page.request.put(`${base}/campaigns/${campaign.id}/sequence`, {
    headers,
    data: {
      channel: "linkedin_manual",
      steps: [
        { position: 0, template: "Hallo {first_name}, {evidence} Kurzer Austausch?" },
        { position: 1, delay_days: 3, template: "Hallo {first_name}, kurze Nachfrage." },
      ],
    },
  });

  // Evidence through the company profile UI.
  await page.goto(`/companies/${companyId}`);
  const evidence = page.getByTestId("company-evidence");
  await expect(evidence).toBeVisible();
  await evidence.getByText("Angabe mit Quelle hinzufügen").click();
  await evidence.getByLabel("Feld").fill("Kategorie");
  await evidence.getByLabel("Quelle (HTTPS)").fill("https://example.test/synthetisch");
  await evidence.getByLabel("Angabe").fill("Steuerberatung");
  await evidence.getByRole("button", { name: "Speichern" }).click();
  await expect(evidence.locator(".evidence-list")).toContainText("Steuerberatung");

  // Personalize with evidence and approve in the campaign.
  await page.goto(`/campaigns/${campaign.id}`);
  const agent = page.getByTestId("campaign-agent");
  await expect(agent).toContainText("Offizielle API: nicht verfügbar");
  await agent.getByRole("button", { name: /Mit Belegen personalisieren/ }).click();
  await expect(page.getByRole("status")).toContainText("1 belegte Entwürfe");
  await expect(page.locator(".journey-draft-card").first()).toContainText(
    "im Bereich Steuerberatung",
  );
  const inbox = await (await page.request.get(`${base}/outreach/inbox`)).json();
  const draft = inbox.items[0];
  const cited = await (
    await page.request.get(`${base}/outreach/drafts/${draft.id}/evidence`)
  ).json();
  expect(cited.items[0].source_url).toBe("https://example.test/synthetisch");
  await page.getByRole("button", { name: "Revision freigeben", exact: true }).first().click();
  await expect(page.locator(".journey-draft-card").first()).toContainText("Freigegeben");

  // Simulated connection request, resolved by the durable worker.
  const row = agent.getByTestId(/agent-row-Anna/);
  await row.getByRole("button", { name: /Anfrage simulieren/ }).click();
  await expect(page.getByRole("status")).toContainText("nichts wurde an LinkedIn gesendet");
  await expect(row).toContainText("Verbunden", { timeout: 30000 });

  // Message with the approved draft; persona replies -> sequence stops, CRM updated.
  await row.getByRole("button", { name: /Nachricht simulieren/ }).click();
  await expect(row).toContainText("Antwort", { timeout: 30000 });
  await expect(row).toContainText("Beantwortet – Sequenz gestoppt");
  const deals = await (await page.request.get(`${base}/deals`)).json();
  const items = deals.items ?? deals;
  expect(
    items.some(
      (d: { contact_id: string; stage: string }) =>
        d.contact_id === anna.contact_id && d.stage === "conversation",
    ),
  ).toBe(true);
  const actions = await (
    await page.request.get(`${base}/linkedin/actions?contact_id=${anna.contact_id}`)
  ).json();
  expect(actions.items.every((a: { simulated: boolean }) => a.simulated)).toBe(true);
  await page.screenshot({
    path: "test-results/sales-agent-campaign.png",
    fullPage: true,
  });

  // Official channel is refused; a foreign workspace cannot read the actions.
  const refused = await page.request.post(`${base}/linkedin/actions`, {
    headers,
    data: { contact_id: anna.contact_id, channel: "official", action: "connection_request" },
  });
  expect(refused.status()).toBe(403);
  const other = await (
    await page.request.post("/api/v1/workspaces", {
      headers,
      data: { name: `E2E Foreign ${Date.now()}` },
    })
  ).json();
  expect(
    (await page.request.get(`/api/v1/workspaces/${other.id}/campaigns/${campaign.id}/linkedin`)).status(),
  ).toBe(404);
});

test("manual handoff for a real-style contact requires self-reported outcomes", async ({
  page,
}) => {
  const { base, headers } = await setup(page);
  const contact = await (
    await page.request.post(`${base}/contacts`, {
      headers,
      data: {
        first_name: "Manuell",
        last_name: "Fixture",
        company: "Fiktive Handoff GmbH",
        linkedin_url: "https://www.linkedin.com/in/fiktiv-e2e-handoff",
      },
    })
  ).json();
  const campaign = await (
    await page.request.post(`${base}/campaigns`, {
      headers,
      data: { name: "E2E Manuell", goal: "Austausch", contact_ids: [] },
    })
  ).json();
  await page.request.post(`${base}/leads/bulk`, {
    headers,
    data: { contact_ids: [contact.id], campaign_id: campaign.id },
  });
  await page.goto(`/campaigns/${campaign.id}`);
  const row = page.getByTestId("campaign-agent").getByTestId(/agent-row-Manuell/);
  await expect(row).toContainText("Echter Kontakt · nur manuell");
  await row.getByRole("button", { name: /Anfrage manuell übergeben/ }).click();
  const card = page.getByRole("dialog", { name: "Manuelle LinkedIn-Übergabe" });
  await expect(card.getByRole("link", { name: /Profil öffnen/ })).toHaveAttribute(
    "href",
    "https://www.linkedin.com/in/fiktiv-e2e-handoff",
  );
  await card.getByRole("button", { name: "Verstanden" }).click();
  await row.getByRole("button", { name: "Gesendet", exact: true }).click();
  await row.getByRole("button", { name: "Angenommen", exact: true }).click();
  await expect(row).toContainText("Verbunden");
  await expect(row).toContainText("Entwurf für nächsten Schritt erstellen");
  await page.setViewportSize({ width: 375, height: 800 });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  await page.screenshot({
    path: "test-results/sales-agent-mobile.png",
    fullPage: true,
  });
});
