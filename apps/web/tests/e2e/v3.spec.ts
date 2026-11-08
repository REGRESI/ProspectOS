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

test("M2: campaign from a recipe in one click; due steps appear in Heute; edits apply from the next step", async ({ page }) => {
  const ctx = await setup(page, "E2E V3 Ansprache");
  await seedPeople(page, ctx);
  const started = Date.now();
  await page.goto("/flows");
  const recipes = page.getByTestId("recipes");
  await recipes
    .locator(".recipe-card", { hasText: "Büro Ortenau mit LinkedIn" })
    .getByRole("button", { name: "Starten" })
    .click();
  await expect(page.getByRole("status").filter({ hasText: "2 Kontakte gestartet" })).toBeVisible();
  expect(Date.now() - started).toBeLessThan(120_000);
  await expect(page.getByTestId("flow-step-0")).toContainText("LinkedIn-Aufgabe");
  await expect(page.getByTestId("flow-step-0")).toContainText("1 offen");
  await page.screenshot({ path: "test-results/v3-m2-builder.png", fullPage: true });

  // Edit a later step of the running campaign and save.
  const step = page.getByTestId("flow-step-3");
  await step.getByLabel("Aufgabe").fill("Nachricht nach Annahme (geändert)");
  await page.getByRole("button", { name: "Ablauf speichern" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Ablauf gespeichert" })).toBeVisible();
  const flow = await (await page.request.get(`${ctx.base}/flow-campaigns`)).json();
  const detail = await (await page.request.get(`${ctx.base}/campaigns/${flow.items[0].id}/flow`)).json();
  expect(detail.steps.find((s: { position: number }) => s.position === 30).title).toBe("Nachricht nach Annahme (geändert)");

  // Heute: one LinkedIn task (Lina) and one letter task (Leo), each person exactly one path.
  await page.goto("/today");
  const tasks = page.getByTestId("flow-tasks");
  await expect(tasks.getByTestId("flow-task-Lina Fiktiv")).toContainText("Vernetzen");
  await expect(tasks.getByTestId("flow-task-Leo Fiktiv")).toContainText("Persönlichen Brief");
  await page.screenshot({ path: "test-results/v3-m2-heute.png", fullPage: true });
  await tasks.getByTestId("flow-task-Leo Fiktiv").getByRole("button", { name: "Erledigt" }).click();
  await expect(tasks.getByTestId("flow-task-Leo Fiktiv")).toHaveCount(0);
  await page.setViewportSize({ width: 375, height: 800 });
  await noOverflow(page);
  await page.goto("/flows");
  await noOverflow(page);
});

test("M3: a QR scan stops the letter path, lands in the inbox and creates a task in Heute", async ({ page }) => {
  const ctx = await setup(page, "E2E V3 Reaktion");
  const { leo } = await seedPeople(page, ctx);
  const started = await page.request.post(`${ctx.base}/campaigns/from-recipe`, {
    headers: ctx.headers,
    data: { recipe: "letter_only", contact_ids: [leo.id] },
  });
  expect(started.ok()).toBeTruthy();
  const code = await (
    await page.request.post(`${ctx.base}/companies/${leo.company_id}/ref-code`, {
      headers: ctx.headers,
      data: { target_url: "https://www.cleanstar.example.test/reinigungs-check/" },
    })
  ).json();
  // Public scan, no session: a fresh request context without cookies.
  const anonymous = await (await import("@playwright/test")).request.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3100",
  });
  const scan = await anonymous.get(`/r/${code.code}`, { maxRedirects: 0 });
  expect(scan.status()).toBe(302);
  expect(scan.headers()["location"]).toBe(`https://www.cleanstar.example.test/reinigungs-check/?ref=${code.code}`);
  await anonymous.dispose();

  await page.goto("/inbox");
  const item = page.getByTestId("inbox").getByTestId("reaction-Leo Fiktiv");
  await expect(item).toContainText("QR-Code gescannt");
  await page.screenshot({ path: "test-results/v3-m3-inbox.png", fullPage: true });
  await item.getByLabel("Status für Leo Fiktiv").selectOption("meeting");
  await expect(item).toContainText("Termin");

  await page.goto("/today");
  const tasks = page.getByTestId("flow-tasks");
  await expect(tasks.getByTestId("flow-task-Leo Fiktiv")).toContainText("Termin vereinbaren");
  await expect(tasks).not.toContainText("Persönlichen Brief schicken");
});

test("M4: ten letters as one print PDF with labels; a scan creates a call task", async ({ page }) => {
  const ctx = await setup(page, "E2E V3 Briefe");
  const ids: string[] = [];
  for (let i = 0; i < 10; i++) {
    const c = await (
      await page.request.post(`${ctx.base}/contacts`, {
        headers: ctx.headers,
        data: { first_name: `Person${i}`, last_name: "Fiktiv", company: `Fiktive Praxis Brief ${i}` },
      })
    ).json();
    for (const [field, value] of [
      ["Adresse (Impressum)", `Briefweg ${i + 1}, 77933 Lahr`],
      ["Telefon (Impressum)", `+49 7821 00000${i}`],
    ]) {
      await page.request.post(`${ctx.base}/companies/${c.company_id}/facts`, {
        headers: ctx.headers,
        data: { field, value, source_url: "https://fiktiv.example.test/impressum" },
      });
    }
    ids.push(c.id);
  }
  await page.request.post(`${ctx.base}/channels/refresh`, { headers: ctx.headers });
  const run = await page.request.post(`${ctx.base}/campaigns/from-recipe`, {
    headers: ctx.headers,
    data: { recipe: "letter_only", audience: "letter" },
  });
  expect((await run.json()).started.started).toBe(10);

  await page.goto("/letters");
  const settings = page.locator(".letter-settings");
  await settings.getByLabel("Firma").fill("CleanStar (Test)");
  await settings.getByLabel("Unterschrift").fill("Nico Test");
  await settings.getByLabel("Zielseite für den QR-Code").fill("https://www.cleanstar.example.test/reinigungs-check/");
  await settings.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Brief-Einstellungen gespeichert" })).toBeVisible();
  await page.getByRole("button", { name: "Briefe vorbereiten" }).click();
  await expect(page.getByTestId("letter-list").locator("li")).toHaveCount(10);
  await page.getByRole("button", { name: "Alle Entwürfe freigeben" }).click();
  await expect(page.getByTestId("letter-toolbar")).toContainText("10 freigegeben");
  await page.screenshot({ path: "test-results/v3-m4-letters.png", fullPage: true });

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Sammel-PDF" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("briefe-druck.pdf");
  const pdf = (await (await import("node:fs/promises")).readFile(await download.path())).toString("latin1");
  expect(pdf.startsWith("%PDF")).toBe(true);
  expect((pdf.match(/\/Type \/Page[^s]/g) || []).length).toBe(10);
  const [labels] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Etiketten" }).click()]);
  expect(labels.suggestedFilename()).toBe("adressetiketten-3474.pdf");
  await page.getByRole("button", { name: "Als gedruckt markieren" }).click();
  await expect(page.getByTestId("letter-toolbar")).toContainText("10 gedruckt");

  const letters = await (await page.request.get(`${ctx.base}/letters`)).json();
  const first = letters.items.find((l: { contact: { name: string } }) => l.contact.name === "Person0 Fiktiv");
  const anonymous = await (await import("@playwright/test")).request.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3100",
  });
  expect((await anonymous.get(`/r/${first.code}`, { maxRedirects: 0 })).status()).toBe(302);
  await anonymous.dispose();
  await page.goto("/today");
  await expect(page.getByTestId("flow-tasks").getByTestId("flow-task-Person0 Fiktiv")).toContainText(
    "Anrufen und Termin vereinbaren",
  );
});
