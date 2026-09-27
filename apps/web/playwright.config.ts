import { defineConfig, devices } from "@playwright/test";

// Runs against the static export, the same files `loupe serve` ships. Build first: pnpm build.
export default defineConfig({
  testDir: "e2e",
  outputDir: "test-results",
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    colorScheme: "dark",
    // A preinstalled Chromium instead of Playwright's download, for sandboxes without one.
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "python3 -m http.server 4173 --bind 127.0.0.1 --directory out",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
