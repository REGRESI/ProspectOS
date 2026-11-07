import { ROUTES } from "./routes";
import { test, expect, Page } from "@playwright/test";
async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
  const me = await (await page.request.get("/api/v1/me")).json();
  const created = await page.request.post("/api/v1/workspaces", {
    headers: { "X-CSRF-Token": me.csrf_token },
    data: { name: `E2E Social Experience ${Date.now()}` },
  });
  expect(created.ok()).toBeTruthy();
  const ws = await created.json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { ws, csrf: me.csrf_token };
}
async function nav(page: Page, label: string) {
  if (ROUTES[label]) {
    await page.goto(ROUTES[label]);
    return;
  }
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
test("calendar views → stored revision → edit invalidates approval → reschedule", async ({
  page,
}) => {
  const { ws, csrf } = await login(page);
  const base = `/api/v1/workspaces/${ws.id}`;
  const headers = { "X-CSRF-Token": csrf };
  const created = await page.request.post(`${base}/social/posts`, {
    headers,
    data: { caption: "Persistierter Beitrag für Kalenderprüfung" },
  });
  expect(created.ok()).toBeTruthy();
  const post = await created.json();
  for (const action of ["submit-review", "approve"])
    expect(
      (
        await page.request.post(`${base}/social/posts/${post.id}/${action}`, {
          headers,
        })
      ).ok(),
    ).toBeTruthy();
  expect(
    (
      await page.request.post(`${base}/social/posts/${post.id}/schedule`, {
        headers,
        data: { scheduled_at: new Date(Date.now() + 86400000).toISOString() },
      })
    ).ok(),
  ).toBeTruthy();
  await nav(page, "Content-Kalender");
  await expect(page.locator(".calendar-grid")).toContainText(
    "Persistierter Beitrag",
  );
  await page.getByRole("button", { name: "Woche", exact: true }).click();
  await expect(page.locator(".calendar-week-grid")).toBeVisible();
  await page.getByRole("button", { name: "Liste", exact: true }).click();
  await page
    .getByRole("button", { name: /Beitrag öffnen: Persistierter Beitrag/ })
    .click();
  const dialog = page.getByRole("dialog", { name: "Beitrag im Kalender" });
  await expect(
    dialog.getByRole("heading", { name: "Gespeicherte Revisionen" }),
  ).toBeVisible();
  await dialog
    .getByRole("textbox", { name: "Beitrag im Kalender bearbeiten" })
    .fill("Nach Prüfung geänderter Kalenderbeitrag.");
  await dialog
    .getByRole("button", {
      name: "Änderung speichern und Freigabe zurücksetzen",
    })
    .click();
  await expect(dialog.getByText("In Prüfung", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Freigeben", exact: true }).click();
  const future = new Date(Date.now() + 2 * 86400000);
  const local = new Date(future.getTime() - future.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
  await dialog
    .getByLabel("Redaktionellen Termin ändern (lokale Browser-Zeitzone)")
    .fill(local);
  await dialog
    .getByRole("button", { name: "Redaktionellen Termin speichern" })
    .click();
  await expect(
    dialog.getByText("Redaktionell geplant", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Schließen", exact: true }).click();
  const stored = await (await page.request.get(`${base}/social/posts`)).json();
  expect(stored.items[0].caption).toBe(
    "Nach Prüfung geänderter Kalenderbeitrag.",
  );
  expect(stored.items[0].version).toBe(2);
  expect(stored.items[0].approved_revision).toBe(2);
  expect(stored.items[0].publish_enabled).toBe(false);
  await page.screenshot({
    path: "test-results/social-calendar-list.png",
    fullPage: true,
  });
});
test("Social real AI/image requirements stay honest and preview is selectable", async ({
  page,
}) => {
  const { ws } = await login(page);
  await nav(page, "Social Studio");
  await page.getByRole("button", { name: "KI-Assistent öffnen" }).click();
  await page
    .getByLabel("Thema für KI-Vorschläge")
    .fill("Ein sorgfältig geprüfter Beitrag ohne erfundene Fakten");
  const integrations = await (
    await page.request.get(`/api/v1/workspaces/${ws.id}/integrations`)
  ).json();
  if (
    !integrations.items.some(
      (item: { name: string; status: string }) =>
        item.name === "KI-Text" && item.status === "configured",
    )
  ) {
    await page
      .getByRole("button", { name: "Drei KI-Varianten anfordern" })
      .click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText(
      /LLM|Anbieter|konfiguriert/,
    );
  }
  await page.getByRole("button", { name: "KI-Bild", exact: true }).click();
  const requirements = await (
    await page.request.get(
      `/api/v1/workspaces/${ws.id}/social/images/requirements`,
    )
  ).json();
  if (!requirements.configured) {
    await expect(page.getByText("Bildanbieter einrichten")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Echtes Bild anfordern" }),
    ).toBeDisabled();
  }
  await page
    .getByRole("textbox", { name: "Beitragstext", exact: true })
    .fill("Manueller Social-Entwurf bleibt ohne Anbieter möglich.");
  await page
    .getByRole("button", { name: "Mobile Vorschau", exact: true })
    .click();
  await expect(page.locator(".linkedin-preview")).toContainText(
    "Manueller Social-Entwurf",
  );
  await page
    .getByRole("button", { name: "Desktop-Vorschau", exact: true })
    .click();
  await page.screenshot({
    path: "test-results/social-studio-upgrade.png",
    fullPage: true,
  });
});
