import { test, expect, Page } from "@playwright/test";
async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/overview/);
  await expect(
    page.getByRole("heading", { name: /auf gute Verbindungen/ }),
  ).toBeVisible();
  await expect(page.locator(".stat-card").first()).not.toContainText("—");
}
async function workspace(page: Page) {
  const me = await (await page.request.get("/api/v1/me")).json();
  const response = await page.request.post("/api/v1/workspaces", {
    headers: { "X-CSRF-Token": me.csrf_token },
    data: { name: `E2E Demo ${Date.now()}` },
  });
  expect(response.ok()).toBeTruthy();
  const ws = await response.json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return ws;
}
async function nav(page: Page, label: string) {
  if (
    await page
      .getByRole("button", { name: "Navigation öffnen", exact: true })
      .isVisible()
  )
    await page
      .getByRole("button", { name: "Navigation öffnen", exact: true })
      .click();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: label, exact: true })
    .click();
}
test("CSV 773 rows → preview → idempotent import → search → score details", async ({
  page,
}) => {
  await login(page);
  await workspace(page);
  await nav(page, "Kontakte");
  const headers = [
    "First Name",
    "Last Name",
    "Company Name",
    "Job title",
    "Email",
    "Email deliverability",
    "Phone",
    "Gender",
    "Company Location",
    "Company domain",
    "Linkedin Profile Url",
    "Linkedin Company Url",
    "Open?",
    "Premium?",
  ];
  const rows = Array.from({ length: 773 }, (_, i) =>
    [
      `Synthetisch${i + 1}`,
      "Demo",
      `Fiktiv Büro ${Math.floor(i / 5)}`,
      "Office Management",
      "",
      "",
      "",
      "",
      "Offenburg",
      "",
      `https://www.linkedin.com/in/synthetic-e2e-${i + 1}`,
      `https://www.linkedin.com/company/synthetic-e2e-${Math.floor(i / 5)}`,
      "",
      "",
    ].join(";"),
  );
  const buffer = Buffer.from(
    "\uFEFF" + headers.join(";") + "\n" + rows.join("\n"),
  );
  async function preview() {
    await page
      .getByRole("button", { name: "CSV importieren", exact: true })
      .click();
    await page.locator("input[type=file]").setInputFiles({
      name: "synthetic-773.csv",
      mimeType: "text/csv",
      buffer,
    });
    await page.getByRole("button", { name: "Datei prüfen" }).click();
    await expect(
      page.getByRole("dialog").getByText("Zeilen insgesamt"),
    ).toBeVisible();
  }
  await preview();
  await expect(page.locator(".import-totals>div").first()).toContainText("773");
  await page
    .getByRole("button", { name: "Gültige Kontakte importieren" })
    .click();
  await expect(page.getByText("773 Kontakte · Seite 1 von 31")).toBeVisible();
  await preview();
  await expect(page.locator(".import-totals>div").nth(2)).toContainText("773");
  await page
    .getByRole("button", { name: "Gültige Kontakte importieren" })
    .click();
  await expect(page.getByText("773 Kontakte · Seite 1 von 31")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Kontakte suchen" })
    .fill("Synthetisch773");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: /Synthetisch773 Demo/ }).click();
  await expect(
    page.getByRole("heading", { name: "ICP-Fit verstehen" }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("Kaufabsicht");
  await page
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption("qualified");
  await page.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("Qualifiziert");
});
test("Discovery → import, pipeline stage → social review/schedule/edit invalidation", async ({
  page,
}) => {
  await login(page);
  await workspace(page);
  await nav(page, "Lead Discovery");
  await page.getByRole("button", { name: "Beispielsuche starten" }).click();
  await expect(
    page.getByRole("heading", { name: "5 synthetische Beispiele" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Beispiele importieren" }).click();
  await expect(
    page.getByRole("button", { name: "Importiert", exact: true }),
  ).toBeDisabled();
  await nav(page, "CRM / Pipeline");
  await page
    .getByRole("button", { name: "Verkaufschance", exact: true })
    .click();
  await page.getByLabel("Titel", { exact: true }).fill("Fiktive Chance E2E");
  await page.getByLabel("Wert in Euro").fill("1234");
  await page.getByRole("button", { name: "Anlegen", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Fiktive Chance E2E" }),
  ).toBeVisible();
  await page.getByLabel("Phase ändern").selectOption("qualified");
  await expect(
    page.locator(".kanban-column").filter({
      has: page.getByRole("heading", { name: "Qualifiziert", exact: true }),
    }),
  ).toContainText("Fiktive Chance E2E");
  await nav(page, "Social Studio");
  await page
    .getByRole("textbox", { name: "Worüber möchtest du sprechen?" })
    .fill("Synthetischer Team-Alltag");
  await page.getByRole("button", { name: "Ideen entwickeln" }).click();
  await expect(page.getByRole("button", { name: "Variante 1" })).toBeVisible();
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  await page.getByRole("button", { name: "Zur Prüfung" }).click();
  await page.getByRole("button", { name: "Freigeben", exact: true }).click();
  await page.getByRole("button", { name: "Planen", exact: true }).click();
  const future = new Date(Date.now() + 3 * 86400000);
  const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  await page
    .getByLabel("Zeitpunkt in deiner lokalen Browser-Zeitzone")
    .fill(local);
  await page
    .getByRole("button", { name: "Intern planen", exact: true })
    .click();
  await expect(page.locator(".post-list")).toContainText(
    "Redaktionell geplant",
  );
  await page.getByRole("button", { name: "Bearbeiten", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Beitragstext", exact: true })
    .fill("Nach der Freigabe geänderter synthetischer Beitrag.");
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  await expect(page.locator(".post-list")).toContainText("In Prüfung");
});
test("Responsive dashboard, keyboard modal and transparent integrations", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1050 });
  await login(page);
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  for (const size of [
    { width: 768, height: 1024 },
    { width: 375, height: 812 },
  ]) {
    await page.setViewportSize(size);
    await expect(
      page.getByRole("heading", { name: /auf gute Verbindungen/ }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/dashboard-${size.width}.png`,
      fullPage: true,
    });
  }
  await nav(page, "Kontakte");
  await page.getByRole("button", { name: "Kontakt hinzufügen" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await nav(page, "Integrationen");
  await expect(
    page.getByText("Keine Verbindung wird simuliert."),
  ).toBeVisible();
  await expect(
    page.getByText(
      "OAuth und Freigaben fehlen. Veröffentlichung nicht verfügbar.",
    ),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
