import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });

test("voice examples → gallery modes → preview → save/reload → revision → duplicate/archive", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/overview/);
  const me = await (await page.request.get("/api/v1/me")).json();
  const headers = { "X-CSRF-Token": me.csrf_token };
  const created = await page.request.post("/api/v1/workspaces", {
    headers,
    data: { name: `Synthetisch Studio V2 ${Date.now()}` },
  });
  expect(created.ok()).toBeTruthy();
  const ws = await created.json();
  const base = `/api/v1/workspaces/${ws.id}`;
  // Explicitly synthetic PNG; never persist session cookies or real private assets as artifacts.
  const png = readFileSync("tests/fixtures/synthetic-studio-team.png");
  const upload = await page.request.post(`${base}/assets/upload`, {
    headers,
    multipart: {
      file: {
        name: "Synthetisch-Team.png",
        mimeType: "image/png",
        buffer: png,
      },
      alt_text: "Synthetisches Team-Motiv",
      rights_confirmed: "true",
    },
  });
  expect(upload.ok()).toBeTruthy();
  const asset = await upload.json();
  expect(
    (
      await page.request.patch(`${base}/assets/${asset.id}/metadata`, {
        headers,
        data: {
          title: "Team Zusammenarbeit",
          description: "Synthetische Redaktion",
          alt_text: asset.alt_text,
          tags: ["Team", "Zusammenarbeit"],
          rights_note: "Synthetischer Test",
        },
      })
    ).ok(),
  ).toBeTruthy();
  await page.reload();
  await page.getByLabel("Workspace", { exact: true }).selectOption(ws.id);
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Social Studio", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Schreibprofil erstellen", exact: true })
    .click();
  const profile = page.getByRole("dialog", {
    name: "Schreibprofil erstellen",
    exact: true,
  });
  await profile
    .getByLabel("Profilname")
    .fill("Synthetische persönliche Stimme");
  await profile.getByLabel("Stimme / Ton").fill("direkt, nahbar und konkret");
  await profile.getByRole("button", { name: "Beispiel hinzufügen" }).click();
  await profile.getByLabel("Beispiel 1 · Bezeichnung").fill("persönlich");
  await profile
    .getByLabel("Beispiel 1 · Beitrag")
    .fill(
      "Ich fange lieber mit einer konkreten Frage an. Kleine Schritte helfen mir beim Planen.",
    );
  await page.screenshot({
    path: "test-results/studio-v2-voice.png",
    fullPage: true,
  });
  await profile
    .getByRole("button", { name: "Schreibprofil speichern" })
    .click();
  await expect(profile).not.toBeVisible();
  await expect(page.getByText(/1 Stilbeispiele/)).toBeVisible();
  await page.getByLabel("Bildquelle", { exact: true }).selectOption("manual");
  await page.getByLabel("Bilder durchsuchen").fill("Zusammenarbeit");
  await page
    .getByRole("button", { name: "Bild wählen: Team Zusammenarbeit" })
    .click();
  await expect(page.locator(".preview-asset img")).toBeVisible();
  await page.getByLabel("Bildquelle", { exact: true }).selectOption("auto");
  await page
    .getByRole("button", { name: "Passendes Bild vorschlagen" })
    .click();
  await expect(
    page.getByText(/Metadaten-Abgleich:|Keine passenden Metadaten/),
  ).toBeVisible();
  await page.getByLabel("Bildquelle", { exact: true }).selectOption("random");
  await page.getByRole("button", { name: "Zufälliges Bild wählen" }).click();
  await expect(page.getByText(/Zufällig aus bis zu 1000/)).toBeVisible();
  await page.getByLabel("Bildquelle", { exact: true }).selectOption("none");
  await expect(page.locator(".preview-asset")).toHaveCount(0);
  await page.getByLabel("Bildquelle", { exact: true }).selectOption("manual");
  await page
    .getByRole("button", { name: "Bild wählen: Team Zusammenarbeit" })
    .click();
  await page
    .getByRole("textbox", { name: "Beitragstext", exact: true })
    .fill(
      "Eine konkrete Frage hilft unserem Redaktionsteam weiter.\n\nWelchen kleinen Schritt geht ihr heute?",
    );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/studio-v2-workspace.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Entwurf speichern", exact: true })
    .click();
  await expect(page.locator(".post-row")).toContainText("Eine konkrete Frage");
  await page.reload();
  await page.getByRole("button", { name: "Bearbeiten", exact: true }).click();
  await expect(page.getByLabel("Bildquelle", { exact: true })).toHaveValue(
    "manual",
  );
  await expect(
    page.getByLabel("Schreibprofil", { exact: true }),
  ).not.toHaveValue("");
  await expect(page.locator(".preview-asset img")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Beitragstext", exact: true })
    .fill("Eine überarbeitete konkrete Frage an unser Team.");
  await page
    .getByRole("button", {
      name: /Änderung speichern|Entwurf speichern/,
      exact: true,
    })
    .click();
  await expect(page.locator(".post-row")).toContainText(
    "Eine überarbeitete konkrete Frage an unser Team.",
  );
  const stored = await (await page.request.get(`${base}/social/posts`)).json();
  expect(stored.items[0].version).toBe(2);
  const revisions = await (
    await page.request.get(
      `${base}/social/posts/${stored.items[0].id}/revisions`,
    )
  ).json();
  expect(revisions.items).toHaveLength(2);
  await page.getByRole("button", { name: "Duplizieren", exact: true }).click();
  await expect(page.locator(".post-row")).toHaveCount(2);
  await page
    .getByRole("button", { name: "Archivieren", exact: true })
    .first()
    .click();
  await expect(page.locator(".post-list")).toContainText("Archiviert");
  await page
    .getByRole("button", { name: "KI-Assistent öffnen", exact: true })
    .click();
  await page
    .getByLabel("Thema für KI-Vorschläge")
    .fill("Zusammenarbeit im Redaktionsteam");
  await page
    .getByRole("button", { name: "Drei KI-Varianten anfordern" })
    .click();
  await expect(page.getByText(/LLM_API_KEY und LLM_MODEL/)).toBeVisible();
  await page.getByRole("button", { name: "KI-Bild", exact: true }).click();
  await expect(
    page.getByText("Bildanbieter einrichten", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Echtes Bild anfordern", exact: true }),
  ).toBeDisabled();
  await page.screenshot({
    path: "test-results/studio-v2-image-configuration.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect
    .poll(async () =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBeTruthy();
  await expect
    .poll(async () =>
      page
        .locator(".sidebar")
        .evaluate((element) => element.getBoundingClientRect().right),
    )
    .toBeLessThanOrEqual(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/studio-v2-mobile.png",
    fullPage: true,
  });
});
