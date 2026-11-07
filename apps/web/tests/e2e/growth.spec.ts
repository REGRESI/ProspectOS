import { test, expect, Page } from "@playwright/test";
import { deflateSync } from "node:zlib";
let browserErrors: string[] = [];
test.beforeEach(async ({ page }) => {
  browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("response", (response) => {
    if (
      response.url().includes("/api/") &&
      response.status() >= 400 &&
      !(response.status() === 401 && response.url().endsWith("/v1/me"))
    )
      browserErrors.push(
        `HTTP ${response.status()}: ${new URL(response.url()).pathname}`,
      );
  });
  page.on("requestfailed", (request) => {
    if (
      request.url().includes("/api/") &&
      request.failure()?.errorText !== "net::ERR_ABORTED"
    )
      browserErrors.push(`Request failed: ${new URL(request.url()).pathname}`);
  });
});
test.afterEach(() => expect(browserErrors).toEqual([]));
async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
  await page.goto("/overview");
  await expect(page.locator(".stat-card").first()).not.toContainText("—");
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
function syntheticPng() {
  const crc32 = (bytes: Buffer) => {
    let crc = 0xffffffff;
    for (const byte of bytes) {
      crc ^= byte;
      for (let j = 0; j < 8; j++)
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    return (crc ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const name = Buffer.from(type);
    const head = Buffer.alloc(4);
    head.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(Buffer.concat([name, data])));
    return Buffer.concat([head, name, data, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(2, 0);
  header.writeUInt32BE(2, 4);
  header[8] = 8;
  header[9] = 6;
  const row = Buffer.from([0, 104, 84, 217, 255, 36, 132, 107, 255]);
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(Buffer.concat([row, row]))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
test("workspace onboarding → private media/brand → social attachment → calendar", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Workspace", { exact: true }).selectOption("__new");
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Wie heißt dein Unternehmen oder Team?")
    .fill(`E2E Kreativ ${Date.now()}`);
  await dialog
    .getByRole("button", { name: "Workspace erstellen", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await nav(page, "Markenprofile");
  await page.getByRole("button", { name: "Markenprofil", exact: true }).click();
  await page
    .getByLabel("Markenname", { exact: true })
    .fill("Fiktive Marke E2E");
  await page
    .getByLabel("Zielgruppe", { exact: true })
    .fill("Synthetische Testunternehmen");
  await page
    .getByLabel("Tonalität", { exact: true })
    .fill("Klar, nahbar, sachlich");
  await page
    .getByLabel("Content-Säulen (kommagetrennt)")
    .fill("Team, Wissen, Alltag");
  await page.getByRole("button", { name: "Markenprofil speichern" }).click();
  await expect(
    page.getByRole("heading", { name: "Fiktive Marke E2E", exact: true }),
  ).toBeVisible();
  await nav(page, "Bildbibliothek");
  await page
    .getByRole("button", { name: "Bild hochladen", exact: true })
    .click();
  await page.locator("input[type=file]").setInputFiles({
    name: "synthetische-farbkacheln.png",
    mimeType: "image/png",
    buffer: syntheticPng(),
  });
  await page
    .getByLabel("Bildbeschreibung / Alt-Text")
    .fill("Zwei synthetische Farbkacheln in Violett und Grün.");
  await page
    .getByRole("checkbox", { name: /Ich verfüge über die nötigen Rechte/ })
    .check();
  await page.getByRole("button", { name: "Privat speichern" }).click();
  await expect(
    page.getByRole("heading", {
      name: "synthetische-farbkacheln.png",
      exact: true,
    }),
  ).toBeVisible();
  const image = page.getByRole("img", {
    name: "Zwei synthetische Farbkacheln in Violett und Grün.",
  });
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
    )
    .toBeTruthy();
  await nav(page, "Social Studio");
  await page
    .getByRole("combobox", { name:"Markenprofil", exact:true })
    .selectOption({ label: "Fiktive Marke E2E" });
  await page
    .getByRole("combobox", { name:"Bild aus privater Bibliothek", exact:true })
    .selectOption({ label: "synthetische-farbkacheln.png" });
  await page
    .getByRole("textbox", { name: "Beitragstext", exact: true })
    .fill("Synthetischer Beitrag mit privatem Bild und Markenprofil.");
  await page.getByRole("button", { name: "Entwurf speichern" }).click();
  await expect(page.locator(".post-list")).toContainText(
    "Synthetischer Beitrag",
  );
  await page.getByRole("button", { name: "Zur Prüfung" }).click();
  await page.getByRole("button", { name: "Freigeben", exact: true }).click();
  await page.getByRole("button", { name: "Planen", exact: true }).click();
  const future = new Date(Date.now() + 86400000);
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
  await nav(page, "Content-Kalender");
  await expect(page.locator(".calendar-grid")).toContainText(
    "Synthetischer Beitrag",
  );
  await page.screenshot({
    path: "test-results/calendar-media.png",
    fullPage: true,
  });
  const me = await (await page.request.get("/api/v1/me")).json();
  const ws = await page.getByLabel("Workspace", { exact: true }).inputValue();
  const posts = await (
    await page.request.get(`/api/v1/workspaces/${ws}/social/posts`)
  ).json();
  expect(posts.items[0].asset_ids).toHaveLength(1);
  expect(posts.items[0].brand_id).toBeTruthy();
  expect(me.user.id).toBeTruthy();
});
test("CRM task/notes → campaign audience → offline draft without send", async ({
  page,
}) => {
  await login(page);
  await page.getByLabel("Workspace", { exact: true }).selectOption("__new");
  await page
    .getByLabel("Wie heißt dein Unternehmen oder Team?")
    .fill(`E2E Gespräche ${Date.now()}`);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Workspace erstellen", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await nav(page, "Kontakte");
  await page.getByRole("button", { name: "Kontakt hinzufügen" }).click();
  await page.getByLabel("Vorname", { exact: true }).fill("Synthetisch");
  await page.getByLabel("Nachname", { exact: true }).fill("Beziehung");
  await page
    .getByRole("textbox", { name: "Unternehmen", exact: true })
    .fill("Fiktive Testfirma");
  await page.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(page.locator("tbody")).toContainText("Synthetisch Beziehung");
  await nav(page, "Aufgaben & Notizen");
  await page.getByRole("button", { name: "Aufgabe hinzufügen" }).click();
  await page
    .getByLabel("Aufgabentitel")
    .fill("Synthetisches Gespräch vorbereiten");
  await page.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Synthetisches Gespräch vorbereiten" }),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Aufgabe Synthetisches Gespräch vorbereiten erledigen",
    })
    .click();
  await expect(page.locator(".task-row")).toContainText("Erledigt");
  await page.getByRole("button", { name: "Notizen", exact: true }).click();
  await page.getByRole("button", { name: "Notiz hinzufügen" }).click();
  await page
    .getByLabel("Notiz", { exact: true })
    .fill(
      "Fiktive Gesprächsnotiz: keine tatsächliche Einwilligung oder Kundeninformation.",
    );
  await page.getByRole("button", { name: "Speichern", exact: true }).click();
  await expect(page.locator(".note-card")).toContainText(
    "Fiktive Gesprächsnotiz",
  );
  await nav(page, "Kampagnen");
  await page
    .getByRole("button", { name: "Kampagne erstellen", exact: true })
    .click();
  await page.getByLabel("Kampagnenname").fill("Fiktive Kontakte kennenlernen");
  await page.getByLabel("Gesprächsziel").fill("Synthetischen Workflow prüfen");
  await page.getByRole("checkbox", { name: /Synthetisch Beziehung/ }).check();
  await page.getByRole("button", { name: "Kampagne speichern" }).click();
  await expect(
    page.getByRole("heading", { name: "Fiktive Kontakte kennenlernen" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Offline-Entwürfe" }).click();
  await nav(page, "Outreach-Entwürfe");
  await expect(page.locator(".outreach-card")).toContainText("Synthetisch");
  await expect(page.getByText("Manueller Übergabepunkt.")).toBeVisible();
});
