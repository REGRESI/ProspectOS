import { createHmac } from "node:crypto";
import { test, expect, Page } from "@playwright/test";

/*
 * M9 external outreach tools at the user's own risk, on the isolated stack. Synthetic
 * people, keys and URLs only. No request reaches HeyReach, lemlist, LinkedIn or any other
 * vendor: the E2E stack has no outbound network for the API, and the test only exercises
 * the risk dialog, encrypted key storage, the one-time webhook URL and a signed inbound
 * event from our own generic webhook.
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

const RISK =
  "Diese Tools automatisieren LinkedIn über dein Konto. Das verstößt gegen die LinkedIn-Nutzervereinbarung und kann zur Einschränkung oder Sperre deines Accounts führen. Du nutzt sie auf eigene Gefahr.";
const SIGNING = "e2e-synthetic-signing-secret";

async function setup(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Heute", level: 1 })).toBeVisible();
  const me = await (await page.request.get("/api/v1/me")).json();
  const headers = { "X-CSRF-Token": me.csrf_token };
  const ws = await (
    await page.request.post("/api/v1/workspaces", { headers, data: { name: `E2E M9 ${Date.now()}` } })
  ).json();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  return { base: `/api/v1/workspaces/${ws.id}`, headers, wsId: ws.id };
}

test("M9: risk dialog, encrypted keys, one-time webhook URL, signed event, handoff box", async ({ page }) => {
  const { base, headers } = await setup(page);
  const contact = await (
    await page.request.post(`${base}/contacts`, {
      headers,
      data: { first_name: "Mira", last_name: "Fiktiv", company: "Fiktive Praxis M9", location: "Lahr" },
    })
  ).json();
  const profile = await page.request.put(`${base}/contacts/${contact.id}/linkedin-profile`, {
    headers,
    data: { url: "https://www.linkedin.com/in/fiktiv-mira-m9" },
  });
  expect(profile.ok()).toBeTruthy();
  await page.request.post(`${base}/channels/refresh`, { headers });

  await page.goto("/settings/connectors");
  await expect(page.getByRole("heading", { name: "Anschlüsse", level: 1 })).toBeVisible();
  await expect(page.getByTestId("connector-switch")).toContainText("sind aus");
  for (const name of ["HeyReach", "Waalaxy", "La Growth Machine", "Expandi", "lemlist"]) {
    await expect(page.getByTestId("connector-tools")).toContainText(name);
  }
  await expect(page.getByTestId("tool-heyreach")).toContainText("Kann nicht");

  // Risk dialog: exact text, confirm button only after the checkbox.
  await page.getByRole("button", { name: "Einschalten …" }).click();
  const risk = page.getByTestId("connector-risk");
  await expect(risk).toContainText(RISK);
  const confirm = page.getByRole("button", { name: "Bestätigen und einschalten" });
  await expect(confirm).toBeDisabled();
  await page.screenshot({ path: "test-results/m9-risk-dialog.png", fullPage: true });
  await risk.getByRole("checkbox").check();
  await confirm.click();
  await expect(page.getByTestId("connector-switch")).toContainText("sind eingeschaltet");
  await expect(page.getByTestId("connector-ack")).toContainText("Bestätigt von");
  const audit = await (await page.request.get(`${base}/audit`)).json();
  expect(JSON.stringify(audit)).toContain("auf eigene Gefahr");

  // Own webhook: keys stored encrypted, URL shown once.
  await page.getByTestId("tool-webhook").getByRole("button", { name: "Verbinden" }).click();
  const form = page.getByTestId("connector-form");
  await form.getByLabel("Signatur-Geheimnis").fill(SIGNING);
  await form.getByLabel("Ziel-URL (https)").fill("https://hooks.example.test/prospectos");
  await form.getByRole("button", { name: "Speichern" }).click();
  const hookUrl = (await page.getByTestId("webhook-url").textContent()) || "";
  expect(hookUrl).toMatch(/\/api\/v1\/hooks\/[0-9a-f-]+\/[A-Za-z0-9_-]+$/);
  await page.getByRole("button", { name: "Fertig" }).click();
  await expect(page.getByTestId("tool-webhook")).toContainText("nicht getestet");
  const overview = await (await page.request.get(`${base}/connectors`)).json();
  expect(JSON.stringify(overview)).not.toContain(SIGNING);
  await page.screenshot({ path: "test-results/m9-connectors.png", fullPage: true });

  // Unsigned inbound call is refused; a signed one is matched to the contact.
  const path = new URL(hookUrl).pathname;
  const body = JSON.stringify({
    event: "accepted",
    linkedin_url: "https://www.linkedin.com/in/fiktiv-mira-m9",
    id: `e2e-${Date.now()}`,
  });
  expect((await page.request.post(path, { data: body, headers: { "Content-Type": "application/json" } })).status()).toBe(401);
  const stamp = String(Math.floor(Date.now() / 1000));
  const signature = "sha256=" + createHmac("sha256", SIGNING).update(`${stamp}.${body}`).digest("hex");
  const signed = await page.request.post(path, {
    data: body,
    headers: {
      "Content-Type": "application/json",
      "X-ProspectOS-Timestamp": stamp,
      "X-ProspectOS-Signature": signature,
    },
  });
  expect(signed.status()).toBe(200);
  expect((await signed.json()).matched).toBe(1);

  // The contact's Kanäle tab offers the handoff to a connected tool.
  await page.goto("/contacts");
  await page.getByRole("cell", { name: /Mira Fiktiv/ }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Kanäle", exact: true }).click();
  const box = dialog.getByTestId("handoff-box");
  await expect(box).toContainText("Externes Tool (eigene Gefahr)");
  await expect(box.getByLabel("Tool")).toContainText("Allgemeiner Webhook");
  await expect(box).toContainText("E-Mail nur mit Rechtsgrundlage");
  await page.keyboard.press("Escape");

  // Phone width: no horizontal scroll; switch off again.
  await page.goto("/settings/connectors");
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole("button", { name: "Ausschalten" }).click();
  await expect(page.getByTestId("connector-switch")).toContainText("sind aus");
});
