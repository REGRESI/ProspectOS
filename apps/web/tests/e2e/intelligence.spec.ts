import { test, expect } from "@playwright/test";

test("durable discovery job → attributed import; missing AI credentials fail honestly", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
  const me = await (await page.request.get("/api/v1/me")).json();
  const workspace = await page.request.post("/api/v1/workspaces", {
    headers: { "X-CSRF-Token": me.csrf_token },
    data: { name: `E2E Intelligence ${Date.now()}` },
  });
  expect(workspace.ok()).toBeTruthy();
  const ws = await workspace.json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  await page.getByRole("navigation").getByRole("button", { name: "Recherche & KI", exact: true }).click();
  await page.getByRole("button", { name: "Suchauftrag anlegen" }).click();
  await expect(page.getByText("succeeded", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("heading", { name: "Demo-Unternehmen 1 (synthetisch)" })).toBeVisible();
  await page.getByRole("button", { name: "Ergebnisse mit Herkunft übernehmen" }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Kontakte", exact: true }).click();
  await expect(page.getByText("5 Kontakte · Seite 1 von 1")).toBeVisible();
  await page.getByRole("navigation").getByRole("button", { name: "Recherche & KI", exact: true }).click();
  const integrations=await (await page.request.get(`/api/v1/workspaces/${ws.id}/integrations`)).json();
  if (integrations.items.some((item:{name:string;status:string})=>item.name==="KI-Text"&&item.status==="configured")) return;
  await page.getByLabel("Aufgabe", { exact: true }).fill("Schreibe einen Vorschlag ohne erfundene Fakten.");
  await page.getByRole("button", { name: "KI-Auftrag anlegen" }).click();
  await expect(page.getByText(/Kein LLM-Anbieter konfiguriert/)).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true })).not.toBeVisible();
});
