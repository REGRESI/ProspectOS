import { defineConfig } from "@playwright/test";

// Browser tests create workspaces and data. They run only against the isolated E2E stack
// (infra/scripts/e2e.sh, port 3100, throw-away database), never against the dev stack.
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3100";
const port = new URL(baseURL).port;
if (process.env.E2E_ISOLATED !== "1" || port === "3000" || port === "8000") {
  throw new Error(
    "Browser-Tests laufen nur gegen den isolierten Teststack: infra/scripts/e2e.sh " +
      "(nie gegen localhost:3000 und die echte Datenbank).",
  );
}

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  reporter: "list",
});
