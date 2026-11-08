import { test, expect, Page } from "@playwright/test";

/*
 * Design screenshots (docs/design/<phase>/) of the main pages on desktop (1440 px) and
 * phone (390 px), light and dark. Runs only via infra/scripts/design-shots.sh against
 * the isolated E2E stack with the synthetic design fixture (no real contacts).
 */
const dir = process.env.DESIGN_SHOTS_DIR;
test.skip(!dir, "nur über infra/scripts/design-shots.sh");

const pages: [string, string][] = (process.env.DESIGN_SHOTS_PAGES || "")
  .split(",")
  .filter(Boolean)
  .map((p) => p.split("=") as [string, string]);

// Pages whose desktop shot is full page too (e.g. the builder editor below the fold).
const full = (process.env.DESIGN_SHOTS_FULL || "").split(",").filter(Boolean);

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Demo-Workspace öffnen" }).click();
  await expect(page).toHaveURL(/today/);
}

for (const theme of ["light", "dark"] as const) {
  for (const [label, width] of [
    ["desktop", 1440],
    ["mobile", 390],
  ] as const) {
    if (theme === "dark" && label === "mobile") continue;
    test(`${theme} ${label}`, async ({ page }) => {
      test.setTimeout(180000);
      await page.setViewportSize({ width, height: label === "desktop" ? 900 : 844 });
      await page.addInitScript((t) => {
        try {
          localStorage.setItem("prospectos.theme", t);
        } catch {}
      }, theme);
      await login(page);
      for (const [name, path] of pages) {
        await page.goto(path);
        await page.waitForLoadState("networkidle");
        await expect(page.locator(".spin")).toHaveCount(0, { timeout: 15000 });
        await page.waitForTimeout(300);
        await page.screenshot({
          path: `${dir}/${name}-${label}${theme === "dark" ? "-dark" : ""}.png`,
          fullPage: label === "mobile" || full.includes(name),
        });
      }
    });
  }
}
