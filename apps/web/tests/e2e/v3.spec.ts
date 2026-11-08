import { test, expect, Page } from "@playwright/test";

/*
 * V3 multichannel flows on the isolated stack. Synthetic people and companies only
 * ("Fiktiv", example.test). Nothing contacts LinkedIn, a printer or a mail server.
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

type Ctx = { base: string; headers: Record<string, string> };

async function setup(page: Page, name = "E2E V3"): Promise<Ctx> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Heute", level: 1 })).toBeVisible();
  const me = await (await page.request.get("/api/v1/me")).json();
  const headers = { "X-CSRF-Token": me.csrf_token };
  const ws = await (
    await page.request.post("/api/v1/workspaces", { headers, data: { name: `${name} ${Date.now()}` } })
  ).json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { base: `/api/v1/workspaces/${ws.id}`, headers };
}

/** One contact with a confirmed LinkedIn profile and one that only has a postal address. */
async function seedPeople(page: Page, { base, headers }: Ctx) {
  const make = async (first: string, company: string) =>
    (
      await page.request.post(`${base}/contacts`, {
        headers,
        data: { first_name: first, last_name: "Fiktiv", company, location: "Offenburg" },
      })
    ).json();
  const lina = await make("Lina", "Fiktive Kanzlei V3");
  const leo = await make("Leo", "Fiktive Praxis V3");
  for (const c of [lina, leo]) {
    const fact = await page.request.post(`${base}/companies/${c.company_id}/facts`, {
      headers,
      data: {
        field: "Adresse (Impressum)",
        value: `Testweg ${c.first_name === "Lina" ? 1 : 2}, 77652 Offenburg`,
        source_url: "https://fiktiv.example.test/impressum",
      },
    });
    expect(fact.ok()).toBeTruthy();
  }
  const profile = await page.request.put(`${base}/contacts/${lina.id}/linkedin-profile`, {
    headers,
    data: { url: "https://www.linkedin.com/in/fiktiv-lina-v3" },
  });
  expect(profile.ok()).toBeTruthy();
  const refreshed = await (await page.request.post(`${base}/channels/refresh`, { headers })).json();
  expect(refreshed.routes).toMatchObject({ linkedin: 1, letter: 1 });
  return { lina, leo };
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

test("M1: channel switch shows one route, sources and permissions; an objection locks every channel", async ({ page }) => {
  const ctx = await setup(page, "E2E V3 Kanäle");
  const { leo } = await seedPeople(page, ctx);
  await page.goto("/contacts");
  await page.getByRole("cell", { name: /Leo Fiktiv/ }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Kanäle", exact: true }).click();
  const panel = dialog.getByTestId("channel-panel");
  await expect(panel.locator(".route-name")).toHaveText("Brief");
  await expect(panel).toContainText("Testweg 2, 77652 Offenburg");
  await expect(panel).toContainText("Kein geprüftes LinkedIn-Profil.");
  await page.screenshot({ path: "test-results/v3-m1-channels.png", fullPage: true });
  await panel.getByText("Widerspruch eintragen").click();
  await panel.getByLabel("Grund").fill("Bitte keine Werbung (Test)");
  await panel.getByRole("button", { name: "Alle Kanäle sperren" }).click();
  await expect(panel).toContainText("Alle Kanäle sind gesperrt");
  const channels = await (await page.request.get(`${ctx.base}/contacts/${leo.id}/channels`)).json();
  expect(Object.values(channels.permissions).every((p) => !(p as { allowed: boolean }).allowed)).toBe(true);
});
